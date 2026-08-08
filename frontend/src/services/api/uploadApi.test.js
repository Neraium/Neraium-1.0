/* @vitest-environment jsdom */
/* global globalThis */
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

    send(body) {
      this.body = body;
      this.sentBody = body;
      const response = responses.shift();
      if (!response) throw new Error("Unexpected XHR send");
      this._response = response;
      this.status = response.status;
      this.responseText = response.body;
      if (response.networkError) {
        this.upload.onloadstart?.();
        this.upload.onprogress?.({
          loaded: response.progress?.loaded || 0,
          total: response.progress?.total || body?.size || 0,
          lengthComputable: true,
        });
        this.onerror?.();
        return;
      }
      if (response.timeout) {
        this.upload.onloadstart?.();
        this.upload.onprogress?.({
          loaded: response.progress?.loaded || 0,
          total: response.progress?.total || body?.size || 0,
          lengthComputable: true,
        });
        this.ontimeout?.();
        return;
      }
      if (response.uploaded) {
        this.upload.onprogress?.({ loaded: response.uploaded, total: response.uploaded, lengthComputable: true });
        this.upload.onload?.();
      }
      this.readyState = 4;
      if (response.progress) {
        this.upload.onloadstart?.();
        this.upload.onprogress?.({
          loaded: response.progress.loaded,
          total: response.progress.total,
          lengthComputable: true,
        });
      }
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

  it("does not reuse latest results across authenticated scopes", async () => {
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(createResponse({ status: "complete", latest_result: { job_id: "user-a-run", filename: "a.csv" } }))
      .mockResolvedValueOnce(createResponse({ status: "complete", latest_result: { job_id: "user-b-run", filename: "b.csv" } }));

    const userA = await fetchLatestUploadState({ apiFetch, accessCode: "", scopeKey: "user-a::default", includePersisted: true });
    const userB = await fetchLatestUploadState({ apiFetch, accessCode: "", scopeKey: "user-b::default", includePersisted: true });

    expect(userA.latestResult?.job_id).toBe("user-a-run");
    expect(userB.latestResult?.job_id).toBe("user-b-run");
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });

  it("loads and caches only the exact analysis run from an analysis route", async () => {
    const result = {
      job_id: "run-a",
      run_id: "run-a",
      upload_id: "run-a",
      dataset_id: "comparison-dataset-a",
      baseline_dataset_id: "baseline-dataset-a",
      comparison_dataset_id: "comparison-dataset-a",
      comparison_analysis_id: "run-a",
      analysis_run_id: "run-a",
      organization_id: "user-a",
      portfolio_id: "portfolio-a",
      system_id: "system-a",
      baseline_id: "baseline-a",
      workflow: "analyze_new_data",
      status: "COMPLETE",
      processing_state: "complete",
      sii_completed: true,
      active_baseline_reference: { model_id: "baseline-a", dataset_id: "baseline-dataset-a" },
      data_quality: { readiness: "ready" },
    };
    const apiFetch = vi.fn().mockResolvedValue(createResponse(result));
    const exactAnalysisIdentity = {
      portfolioId: "portfolio-a",
      systemId: "system-a",
      baselineId: "baseline-a",
      analysisRunId: "run-a",
    };

    const first = await fetchLatestUploadState({ apiFetch, scopeKey: "user-a::portfolio-a", exactAnalysisIdentity });
    const cached = await fetchLatestUploadState({ apiFetch, scopeKey: "user-a::portfolio-a", exactAnalysisIdentity });

    expect(first.latestResult?.analysis_run_id).toBe("run-a");
    expect(cached.latestResult?.analysis_run_id).toBe("run-a");
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(apiFetch.mock.calls[0][0]).toBe("/api/data/analyses/run-a");
    expect(apiFetch.mock.calls[0][1].headers).toEqual({ "X-Neraium-Workspace-Id": "portfolio-a" });
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

  it("sends exact baseline identity with a direct comparison upload", async () => {
    const xhr = installXhrSequence([{
      status: 202,
      body: JSON.stringify({ job_id: "comparison-job", status: "PENDING" }),
      headers: { "content-type": "application/json" },
    }]);

    try {
      await uploadTelemetryFileWithProgress({
        file: new File(["timestamp,value\n2026-06-22,1\n"], "comparison.csv", { type: "text/csv" }),
        workflow: "analyze_new_data",
        baselineIdentity: { portfolioId: "portfolio-a", systemId: "system-a", baselineId: "baseline-a" },
        accessCode: "",
      });
      const body = xhr.instances[0].sentBody;
      expect(body.get("workflow")).toBe("analyze_new_data");
      expect(body.get("portfolio_id")).toBe("portfolio-a");
      expect(body.get("system_id")).toBe("system-a");
      expect(body.get("baseline_id")).toBe("baseline-a");
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
      expect(progress.find((event) => event.message === SERVICE_UNAVAILABLE_RETRY_MESSAGE)).toMatchObject({ loaded: 0, percent: 0 });
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


describe("large telemetry upload transport", () => {
  it("uses stored object transport for a production-sized small CSV", async () => {
    const file = new File(["timestamp,value\n2026-06-22,1\n"], "mobile.csv", { type: "text/csv" });
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(createResponse({
        upload_session_id: "mobile-session",
        upload_url: "https://upload.example.test/mobile",
        upload_headers: { "Content-Type": "text/csv" },
      }, { status: 201 }))
      .mockResolvedValueOnce(createResponse({
        job_id: "mobile-session",
        status: "PENDING",
        status_url: "/api/data/upload-status/mobile-session",
      }, { status: 202 }));
    const xhr = installXhrSequence([{
      status: 200,
      body: "",
      headers: { etag: '"mobile-etag"' },
      progress: { loaded: file.size, total: file.size },
    }]);

    try {
      const result = await uploadTelemetryFileWithProgress({ file, apiFetch, preferStoredUpload: true });

      expect(result.payload.job_id).toBe("mobile-session");
      expect(apiFetch.mock.calls.map(([path]) => path)).toEqual([
        "/api/data/upload-session",
        "/api/data/upload-session/mobile-session/complete",
      ]);
      expect(xhr.instances).toHaveLength(1);
      expect(xhr.instances[0].method).toBe("PUT");
    } finally {
      xhr.restore();
    }
  });

  it("reports a genuine network failure during object transfer as an upload transfer failure", async () => {
    const file = new File(["timestamp,value\n2026-06-22,1\n"], "offline.csv", { type: "text/csv" });
    const apiFetch = vi.fn().mockResolvedValueOnce(createResponse({
      upload_session_id: "offline-session",
      upload_url: "https://upload.example.test/offline",
      upload_headers: { "Content-Type": "text/csv" },
    }, { status: 201 }));
    const xhr = installXhrSequence([{
      status: 0,
      body: "",
      networkError: true,
      progress: { loaded: 0, total: file.size },
    }]);

    try {
      await expect(uploadTelemetryFileWithProgress({ file, apiFetch, preferStoredUpload: true })).rejects.toMatchObject({
        name: "ApiNetworkError",
        failedStage: "upload_transfer",
        transferSucceeded: false,
      });
      expect(apiFetch).toHaveBeenCalledTimes(1);
    } finally {
      xhr.restore();
    }
  });

  it("routes a synthetic 409.5 MiB CSV directly to object storage and creates the exact job", async () => {
    const file = new File(["timestamp,value\n2026-06-22,1\n"], "ChillerPlant.csv", { type: "text/csv" });
    Object.defineProperty(file, "size", { configurable: true, value: Math.round(409.5 * 1024 * 1024) });
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(createResponse({
        upload_session_id: "large-session-4095",
        upload_url: "https://upload-bucket.s3.us-east-2.amazonaws.com/object?signed=redacted",
        upload_headers: {
          "Content-Type": "text/csv",
          "x-amz-tagging": "neraium-upload-source=true",
          "If-None-Match": "*",
        },
        upload_method: "PUT",
      }, { status: 201 }))
      .mockResolvedValueOnce(createResponse({
        job_id: "large-session-4095",
        status: "PENDING",
        processing_state: "queued",
        status_url: "/api/data/upload-status/large-session-4095",
        filename: "ChillerPlant.csv",
        upload_transport: "presigned_s3_put",
      }, { status: 202 }));
    const xhr = installXhrSequence([{
      status: 200,
      body: "",
      headers: { etag: '"etag-4095"' },
      progress: { loaded: file.size, total: file.size },
    }]);
    const progress = [];

    try {
      const response = await uploadTelemetryFileWithProgress({
        file,
        workflow: "create_baseline",
        approvalRequired: true,
        apiFetch,
        accessCode: "",
        onProgress: (event) => progress.push(event),
      });

      expect(apiFetch).toHaveBeenCalledTimes(2);
      expect(apiFetch.mock.calls[0][0]).toBe("/api/data/upload-session");
      expect(JSON.parse(apiFetch.mock.calls[0][1].body)).toEqual({
        filename: "ChillerPlant.csv",
        size_bytes: file.size,
        content_type: "text/csv",
        workflow: "create_baseline",
        approval_required: true,
      });
      expect(apiFetch.mock.calls[1][0]).toBe("/api/data/upload-session/large-session-4095/complete");
      expect(JSON.parse(apiFetch.mock.calls[1][1].body)).toEqual({ etag: "etag-4095" });
      expect(xhr.instances).toHaveLength(1);
      expect(xhr.instances[0].method).toBe("PUT");
      expect(xhr.instances[0].body).toBe(file);
      expect(xhr.instances[0].withCredentials).toBe(false);
      expect(xhr.instances[0].headers).toMatchObject({
        "Content-Type": "text/csv",
        "x-amz-tagging": "neraium-upload-source=true",
        "If-None-Match": "*",
      });
      expect(progress.some((event) => event.stage === "uploading" || event.stage === "upload_transferred")).toBe(true);
      expect(progress.filter((event) => event.loaded === 0).every((event) => event.percent === 0)).toBe(true);
      expect(progress.at(-1)).toMatchObject({ stage: "validating", message: "Transfer complete. Creating dataset record." });
      expect(response.payload).toMatchObject({
        job_id: "large-session-4095",
        filename: "ChillerPlant.csv",
      });
    } finally {
      xhr.restore();
    }
  });



  it("reuses a completed object upload when Retry follows a lost job-creation response", async () => {
    const file = new File(["timestamp,value\n2026-06-22,1\n"], "resume.csv", { type: "text/csv" });
    Object.defineProperty(file, "size", { configurable: true, value: (250 * 1024 * 1024) + 1 });
    const lostResponse = Object.assign(new Error("connection lost"), { name: "ApiNetworkError" });
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(createResponse({
        upload_session_id: "resume-session",
        upload_url: "https://upload.example.test/resume",
        upload_headers: { "Content-Type": "text/csv" },
      }, { status: 201 }))
      .mockRejectedValueOnce(lostResponse)
      .mockResolvedValueOnce(createResponse({
        job_id: "resume-session",
        status: "PENDING",
        status_url: "/api/data/upload-status/resume-session",
      }, { status: 202 }));
    const xhr = installXhrSequence([{ status: 200, body: "", headers: { etag: '"resume-etag"' } }]);

    try {
      await expect(uploadTelemetryFileWithProgress({ file, apiFetch })).rejects.toMatchObject({
        name: "ApiNetworkError",
        phase: "job_creation",
      });
      const result = await uploadTelemetryFileWithProgress({ file, apiFetch });

      expect(result.payload.job_id).toBe("resume-session");
      expect(xhr.instances).toHaveLength(1);
      expect(apiFetch).toHaveBeenCalledTimes(3);
      expect(apiFetch.mock.calls.map(([path]) => path)).toEqual([
        "/api/data/upload-session",
        "/api/data/upload-session/resume-session/complete",
        "/api/data/upload-session/resume-session/complete",
      ]);
    } finally {
      xhr.restore();
    }
  });

  it("shows a safe failure when upload completion does not return a job ID", async () => {
    const file = new File(["timestamp,value\n2026-06-22,1\n"], "large.csv", { type: "text/csv" });
    Object.defineProperty(file, "size", { configurable: true, value: (250 * 1024 * 1024) + 1 });
    const apiFetch = vi.fn()
      .mockResolvedValueOnce(createResponse({
        upload_session_id: "missing-job-session",
        upload_url: "https://upload.example.test/object",
        upload_headers: { "Content-Type": "text/csv" },
      }, { status: 201 }))
      .mockResolvedValueOnce(createResponse({ status: "PENDING" }, { status: 202 }));
    const xhr = installXhrSequence([{ status: 200, body: "", headers: { etag: '"etag"' } }]);

    try {
      await expect(uploadTelemetryFileWithProgress({ file, apiFetch })).rejects.toMatchObject({
        name: "UploadRequestError",
        errorType: "dataset_record_creation_failed",
        detail: "The file was transferred successfully, but Neraium could not begin processing it.",
        failedStage: "dataset_creation",
        transferSucceeded: true,
        fileStored: true,
      });
    } finally {
      xhr.restore();
    }
  });
});
