import { describe, expect, it } from "vitest";
import { SERVICE_UNAVAILABLE_UPLOAD_MESSAGE, buildUploadRequestError, classifyUploadError, readJsonPayload } from "../uploadFlow";


describe("uploadFlow poll error classification", () => {

  it("sanitizes HTML 503 payloads and keeps raw details out of the user message", async () => {
    const html = "<html><head><title>503 Service Temporarily Unavailable</title></head><body>nginx</body></html>";
    const response = {
      ok: false,
      status: 503,
      url: "/api/data/upload-status/job-503",
      headers: { get: () => "text/html" },
      text: async () => html,
    };

    const payload = await readJsonPayload(response, { route: "/api/data/upload-status/job-503", phase: "poll" });
    expect(payload).toMatchObject({
      status: "FAILED",
      processing_state: "failed",
      error_type: "service_unavailable",
      message: SERVICE_UNAVAILABLE_UPLOAD_MESSAGE,
      failure_url: "/api/data/upload-status/job-503",
      failure_phase: "poll",
      response_status: 503,
      html_response: true,
    });
    expect(payload.raw_response_body).toContain("<html>");

    const requestError = buildUploadRequestError(response, payload, "poll");
    expect(requestError.detail).toBe(SERVICE_UNAVAILABLE_UPLOAD_MESSAGE);
    expect(requestError.detail).not.toContain("<html>");
    expect(requestError.failureUrl).toBe("/api/data/upload-status/job-503");
  });
  it("keeps upload job-not-found errors distinct from endpoint misses", () => {
    const error = new Error("Upload job missing");
    error.name = "UploadRequestError";
    error.errorType = "job_not_found";

    expect(classifyUploadError(error, "upload")).toMatchObject({
      state: "error",
      retryable: false,
      errorType: "job_not_found",
      message: "Analysis status unavailable.",
    });
  });

  it("keeps polling on API timeout errors", () => {
    const error = new Error("API request timed out after 45000ms while calling /api/upload-status/job-123.");
    error.name = "ApiTimeoutError";
    error.path = "/api/upload-status/job-123";

    expect(classifyUploadError(error, "poll")).toMatchObject({
      state: "running_sii",
      retryable: true,
      errorType: "timeout",
    });
  });

  it("keeps polling on API network errors", () => {
    const error = new Error("API network unavailable while calling /api/data/upload-status/job-123.");
    error.name = "ApiNetworkError";
    error.path = "/api/data/upload-status/job-123";

    expect(classifyUploadError(error, "poll")).toMatchObject({
      state: "running_sii",
      retryable: true,
      errorType: "network",
    });
  });

  it("shows the concrete upload network failure during the upload phase", () => {
    const error = new Error("Upload network error before server accepted the file. Failed URL: /api/data/upload");
    error.name = "ApiNetworkError";

    expect(classifyUploadError(error, "upload")).toMatchObject({
      state: "error",
      retryable: false,
      errorType: "network",
      message: "Upload network error before server accepted the file. Failed URL: /api/data/upload",
    });
  });

  it("uses the backend 413 payload for oversized upload failures", () => {
    const error = new Error("Unexpected response: 413");
    error.name = "UploadRequestError";
    error.status = 413;
    error.payload = {
      error_type: "upload_too_large",
      message: "File too large. Maximum supported size is 10 GB.",
    };

    expect(classifyUploadError(error, "upload")).toMatchObject({
      state: "error",
      retryable: false,
      status: 413,
      errorType: "upload_too_large",
      message: "File too large. Maximum supported size is 10 GB.",
    });
  });

  it("reports a missing upload endpoint instead of a generic interruption", () => {
    const error = new Error("Unexpected response: 404");
    error.name = "UploadRequestError";
    error.status = 404;
    error.payload = { detail: "Not Found" };

    expect(classifyUploadError(error, "upload")).toMatchObject({
      state: "error",
      retryable: false,
      status: 404,
      message: "Telemetry intake unavailable.",
    });
  });

  it("reports upload timeouts specifically", () => {
    const error = new Error("Upload request timed out before server accepted the file.");
    error.name = "ApiTimeoutError";
    error.status = 408;

    expect(classifyUploadError(error, "upload")).toMatchObject({
      state: "error",
      retryable: false,
      errorType: "timeout",
      message: "Upload timed out.",
    });
  });

});
