import { describe, expect, it } from "vitest";
import {
  SERVICE_UNAVAILABLE_UPLOAD_MESSAGE,
  buildUploadRequestError,
  classifyUploadError,
  operatorUploadMessage,
  readJsonPayload,
  uploadErrorPresentation,
} from "../uploadFlow";


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
  it("uses generic protected-route messages without reflecting backend details", () => {
    const backendDetail = "token=do-not-render internal auth middleware failed";

    expect(operatorUploadMessage({ status: 401, errorType: "auth", detail: backendDetail, phase: "upload" }))
      .toBe("Your session has expired. Sign in again, then retry the import.");
    expect(operatorUploadMessage({ status: 404, errorType: "upload_session_missing", detail: backendDetail, phase: "upload" }))
      .toBe("Analysis status is unavailable. Refresh and retry.");
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

  it("sanitizes an upload network failure without exposing its route", () => {
    const error = new Error("Network failed at https://internal.example.test/api/data/upload?token=secret");
    error.name = "ApiNetworkError";

    expect(classifyUploadError(error, "upload")).toMatchObject({
      state: "error",
      retryable: true,
      errorType: "network",
      message: "The file transfer failed. Check the connection and try again.",
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
      retryable: true,
      errorType: "timeout",
      message: "The file transfer timed out. Check the connection and try again.",
    });
  });

  it.each([
    ["auth_session_expired", "authentication", "Authentication expired"],
    ["dataset_record_creation_failed", "dataset_creation", "Dataset record creation failed"],
    ["file_storage_failed", "file_storage", "File storage failed"],
    ["csv_parsing_failed", "csv_parsing", "CSV parsing failed"],
    ["validation_failed", "validation", "Validation failed"],
    ["baseline_processing_failed", "baseline_processing", "Baseline processing failed"],
    ["server_timeout", "baseline_processing", "Server timeout"],
    ["server_unavailable", "server", "Server unavailable"],
    ["unexpected_server_error", "unexpected", "Unexpected server error"],
  ])("presents %s as a specific safe state", (errorCode, failedStage, title) => {
    expect(uploadErrorPresentation({
      error_code: errorCode,
      failed_stage: failedStage,
      retryable: true,
    })).toMatchObject({ errorCode, failedStage, title });
  });

  it("preserves a structured stored-upload failure instead of replacing it with a connection error", () => {
    const response = { status: 503, url: "/api/data/upload-session/stored/complete" };
    const payload = {
      error_code: "dataset_record_creation_failed",
      error_type: "upload_enqueue_failed",
      message: "The file was transferred successfully, but Neraium could not begin processing it.",
      failed_stage: "dataset_creation",
      retryable: true,
      transfer_succeeded: true,
      file_stored: true,
      job_id: "stored",
    };

    const error = buildUploadRequestError(response, payload, "job_creation");
    expect(error).toMatchObject({
      errorType: "dataset_record_creation_failed",
      failedStage: "dataset_creation",
      retryable: true,
      transferSucceeded: true,
      fileStored: true,
      jobId: "stored",
    });
    expect(classifyUploadError(error, "job_creation")).toMatchObject({
      errorType: "dataset_record_creation_failed",
      retryable: true,
      message: "The file was transferred successfully, but Neraium could not begin processing it.",
    });
  });

});
