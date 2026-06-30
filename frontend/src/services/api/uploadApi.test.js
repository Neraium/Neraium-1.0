/* @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SERVICE_UNAVAILABLE_RETRY_MESSAGE, SERVICE_UNAVAILABLE_UPLOAD_MESSAGE } from "../../viewModels/uploadFlow";
import { clearLatestUploadStateCache, fetchLatestUploadState, uploadTelemetryFileWithProgress } from "./uploadApi";

function createResponse(payload, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    json: async () => payload,
  };
}

function createHtmlResponse(status = 503) {
  return {
    ok: false,
    status,
    headers: { get: () => "text/html" },
    text: async () => "<html><head><title>503 Service Temporarily Unavailable</title></head><body>nginx</body></html>",
  };
}

function installXhrSequence(responses) {
  const originalWindowXhr = window.XMLHttpRequest;
  const originalGlobalXhr = globalThis.XMLHttpRequest;
  const instances = [];

  class FakeXMLHttpRequest {
    constructor() {
      this.upload = {};
      this.headers = {};
      this.status = 0;
      this.responseText = "";
      this.readyState = 0;
      this._response = null;
      instances.push(this);
    }

    open(method, url) {
      this.method = method;
      this.url = url;
    }

    setRequestHeader(key, value) {
      this.headers[key] = value;
    }

    getResponseHeader(key) {
      return this._response?.headers?.[String(key).toLowerCase()] ?? "";
    }

    send() {
      const response = responses.shift();
      if (!response) throw new Error("Unexpected XHR send");
      this._response = response;
      this.status = response.status;
      this.responseText = response.body;
      this.readyState = 4;
      this.onload?.();
    }

    abort() {
      this.onabort?.();
    }
  }

  window.XMLHttpRequest = FakeXMLHttpRequest;
  globalThis.XMLHttpRequest = FakeXMLHttpRequest;

  return {
    instances,
    restore() {
      window.XMLHttpRequest = originalWindowXhr;
      globalThis.XMLHttpRequest = originalGlobalXhr;
    },
  };
}

describe("fetchLatestUploadState", () => {
  beforeEach(() => {
    clearLatestUploadStateCache();
    vi.useRealTimers();
  });

  it("bypasses the stale latest-upload cache when forceRefresh is requested", async () => {
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(createResponse({ status: "empty" }))
      .mockResolvedValueOnce(createResponse({
        status: "complete",
        current_upload: { job_id: "job-42", result: { job_id: "job-42", filename: "telemetry.csv" } },
        latest_result: { job_id: "job-42", filename: "telemetry.csv" },
      }));

    const first = await fetchLatestUploadState({ apiFetch, accessCode: "", includePersisted: true });
    const second = await fetchLatestUploadState({ apiFetch, accessCode: "", includePersisted: true, forceRefresh: true });

    expect(first.latestResult).toBeNull();
    expect(second.latestResult?.job_id).toBe("job-42");
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });

  it("sanitizes HTML 503 latest-upload result failures", async () => {
    const apiFetch = vi.fn().mockResolvedValue(createHtmlResponse(503));

    await expect(fetchLatestUploadState({ apiFetch, accessCode: "", includePersisted: true, forceRefresh: true })).rejects.toMatchObject({
      name: "UploadRequestError",
      errorType: "service_unavailable",
      detail: SERVICE_UNAVAILABLE_UPLOAD_MESSAGE,
      failureUrl: "/api/data/latest-upload?include_persisted=1",
      failurePhase: "result",
      status: 503,
    });
  });

  it("retries transient HTML 503 upload responses before resolving", async () => {
    vi.useFakeTimers();
    const xhr = installXhrSequence([
      {
        status: 503,
        body: "<html><head><title>503 Service Temporarily Unavailable</title></head><body>nginx</body></html>",
        headers: { "content-type": "text/html" },
      },
      {
        status: 202,
        body: JSON.stringify({ job_id: "job-retry", status: "PENDING", status_url: "/api/data/upload-status/job-retry", message: "Worker starting..." }),
        headers: { "content-type": "application/json" },
      },
    ]);
    const progress = [];

    try {
      const promise = uploadTelemetryFileWithProgress({
        file: new File(["timestamp,value\n2026-06-22,1\n"], "retry.csv", { type: "text/csv" }),
        onProgress: (event) => progress.push(event),
        accessCode: "",
      });

      expect(xhr.instances).toHaveLength(1);
      await vi.advanceTimersByTimeAsync(600);
      const result = await promise;

      expect(xhr.instances).toHaveLength(2);
      expect(result.payload.job_id).toBe("job-retry");
      expect(progress.some((event) => event.message === SERVICE_UNAVAILABLE_RETRY_MESSAGE)).toBe(true);
    } finally {
      xhr.restore();
      vi.useRealTimers();
    }
  });
});
