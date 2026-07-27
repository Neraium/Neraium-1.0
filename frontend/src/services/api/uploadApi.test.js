/* @vitest-environment jsdom */
/* global globalThis */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SERVICE_UNAVAILABLE_RETRY_MESSAGE, SERVICE_UNAVAILABLE_UPLOAD_MESSAGE } from "../../viewModels/uploadFlow";
import { setCurrentWorkspaceId } from "../datasetSessionCache";
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

    send(body) {
      this.sentBody = body;
      const response = responses.shift();
      if (!response) throw new Error("Unexpected XHR send");
      this._response = response;
      this.status = response.status;
      this.responseText = response.body;
      if (response.uploaded) {
        this.upload.onprogress?.({ loaded: response.uploaded, total: response.uploaded, lengthComputable: true });
        this.upload.onload?.();
      }
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

  it("does not reuse a latest-upload response after the workspace changes", async () => {
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(createResponse({
        status: "complete",
        latest_result: { job_id: "workspace-a-job", filename: "a.csv" },
      }))
      .mockResolvedValueOnce(createResponse({ status: "empty", latest_result: null }));

    setCurrentWorkspaceId("workspace-a");
    const workspaceA = await fetchLatestUploadState({ apiFetch, accessCode: "", includePersisted: true });
    setCurrentWorkspaceId("workspace-b");
    const workspaceB = await fetchLatestUploadState({ apiFetch, accessCode: "", includePersisted: true });

    expect(workspaceA.latestResult?.job_id).toBe("workspace-a-job");
    expect(workspaceB.latestResult).toBeNull();
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });

  it("does not retry a non-idempotent upload after all bytes transferred", async () => {
    const body = "timestamp,value\n2026-06-22,1\n";
    const xhr = installXhrSequence([
      {
        status: 503,
        body: "<html><body>temporarily unavailable</body></html>",
        headers: { "content-type": "text/html" },
        uploaded: body.length,
      },
    ]);

    try {
      await expect(uploadTelemetryFileWithProgress({
        file: new File([body], "transferred.csv", { type: "text/csv" }),
        accessCode: "",
      })).rejects.toMatchObject({ status: 503 });
      expect(xhr.instances).toHaveLength(1);
    } finally {
      xhr.restore();
    }
  });

  it("reports dispatch, transfer, and backend confirmation timings", async () => {
    const body = "timestamp,value\n2026-06-22,1\n";
    const xhr = installXhrSequence([{
      status: 202,
      body: JSON.stringify({ job_id: "timed-job", status: "PENDING", timings: { job_creation_ms: 12 } }),
      headers: { "content-type": "application/json" },
      uploaded: body.length,
    }]);
    const timings = [];

    try {
      await uploadTelemetryFileWithProgress({
        file: new File([body], "timed.csv", { type: "text/csv" }),
        onTiming: (timing) => timings.push(timing),
        requestStartedAt: Date.now() - 5,
        accessCode: "",
      });
      expect(timings.map((timing) => timing.event)).toEqual([
        "frontend_request_dispatched",
        "upload_transfer_complete",
        "upload_response_received",
      ]);
      expect(timings[2]).toMatchObject({
        backend_timings: { job_creation_ms: 12 },
        status: 202,
      });
      expect(timings[2].frontend_request_dispatch_ms).toBeGreaterThanOrEqual(0);
      expect(timings[2].upload_transfer_ms).toBeGreaterThanOrEqual(0);
      expect(timings[2].backend_confirmation_ms).toBeGreaterThanOrEqual(0);
    } finally {
      xhr.restore();
    }
  });

  it("sends the selected telemetry workflow as upload routing metadata", async () => {
    const xhr = installXhrSequence([{
      status: 202,
      body: JSON.stringify({ job_id: "workflow-job", status: "PENDING" }),
      headers: { "content-type": "application/json" },
    }]);

    try {
      await uploadTelemetryFileWithProgress({
        file: new File(["timestamp,value\n2026-06-22,1\n"], "extension.csv", { type: "text/csv" }),
        workflow: "extend_baseline",
        approvalRequired: true,
        accessCode: "",
      });
      expect(xhr.instances[0].sentBody.get("workflow")).toBe("extend_baseline");
      expect(xhr.instances[0].sentBody.get("approval_required")).toBe("true");
    } finally {
      xhr.restore();
    }
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

describe("latest telemetry retry and failure handling", () => {
  beforeEach(() => {
    clearLatestUploadStateCache();
    vi.useRealTimers();
  });

  it("recovers latest telemetry after a transient live connection failure", async () => {
    vi.useFakeTimers();
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(createHtmlResponse(503))
      .mockResolvedValueOnce(createResponse({
        status: "complete",
        request_correlation_id: "corr-retry-success",
        latest_result: { job_id: "job-after-retry", filename: "live.csv", sii_intelligence: { facility_state: "stable" } },
      }));

    const promise = fetchLatestUploadState({ apiFetch, accessCode: "", includePersisted: true, forceRefresh: true });
    await vi.advanceTimersByTimeAsync(500);
    const result = await promise;

    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(result.latestResult.job_id).toBe("job-after-retry");
    expect(result.snapshot._neraiumTelemetryBoundary.requestCorrelationId).toBe("corr-retry-success");
    vi.useRealTimers();
  });

  it("retries network timeout before returning latest telemetry", async () => {
    vi.useFakeTimers();
    const timeout = Object.assign(new Error("timeout"), { name: "ApiTimeoutError", status: 408 });
    const apiFetch = vi.fn()
      .mockRejectedValueOnce(timeout)
      .mockResolvedValueOnce(createResponse({
        status: "complete",
        latest_result: { job_id: "job-timeout-recovered", filename: "timeout.csv", sii_intelligence: { facility_state: "stable" } },
      }));

    const promise = fetchLatestUploadState({ apiFetch, accessCode: "", includePersisted: true, forceRefresh: true });
    await vi.advanceTimersByTimeAsync(500);
    const result = await promise;

    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(result.latestResult.job_id).toBe("job-timeout-recovered");
    vi.useRealTimers();
  });

  it("stops retrying failed latest live connection after sensible limits", async () => {
    vi.useFakeTimers();
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(createHtmlResponse(503))
      .mockResolvedValueOnce(createHtmlResponse(503))
      .mockResolvedValueOnce(createHtmlResponse(503));

    const promise = fetchLatestUploadState({ apiFetch, accessCode: "", includePersisted: true, forceRefresh: true });
    const rejection = expect(promise).rejects.toMatchObject({ status: 503 });
    await vi.advanceTimersByTimeAsync(500);
    await vi.advanceTimersByTimeAsync(1200);
    await rejection;
    expect(apiFetch).toHaveBeenCalledTimes(3);
    vi.useRealTimers();
  });
});

describe("upload dataset scope", () => {
  it("sends the selected workspace on the XHR upload request", async () => {
    setCurrentWorkspaceId("central-plant");
    const xhr = installXhrSequence([{
      status: 202,
      body: JSON.stringify({ job_id: "scoped-job", status: "PENDING", analysis_state: "analysis_queued" }),
      headers: { "content-type": "application/json" },
    }]);

    try {
      await uploadTelemetryFileWithProgress({
        file: new File(["timestamp,value\n2026-06-22,1\n"], "scoped.csv", { type: "text/csv" }),
        accessCode: "",
      });
      expect(xhr.instances[0].headers["X-Neraium-Workspace-Id"]).toBe("central-plant");
    } finally {
      xhr.restore();
    }
  });
});

describe("file ingestion failure handling", () => {
  it("surfaces failed file-based ingestion without retrying non-transient validation errors", async () => {
    const xhr = installXhrSequence([{ status: 400, body: JSON.stringify({ detail: "Invalid telemetry file" }), headers: { "content-type": "application/json" } }]);

    try {
      await expect(uploadTelemetryFileWithProgress({
        file: new File(["not,csv"], "bad.csv", { type: "text/csv" }),
        accessCode: "",
      })).rejects.toMatchObject({ status: 400 });
      expect(xhr.instances).toHaveLength(1);
    } finally {
      xhr.restore();
    }
  });
});
