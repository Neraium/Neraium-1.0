import { describe, expect, it } from "vitest";
import { classifyUploadError } from "../uploadFlow";


describe("uploadFlow poll error classification", () => {
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
    const error = new Error("Upload network error before server accepted the file. Failed URL: https://api.neraium.com/api/data/upload");
    error.name = "ApiNetworkError";

    expect(classifyUploadError(error, "upload")).toMatchObject({
      state: "error",
      retryable: false,
      errorType: "network",
      message: "Upload network error before server accepted the file. Failed URL: https://api.neraium.com/api/data/upload",
    });
  });

  it("uses the backend 413 payload for oversized upload failures", () => {
    const error = new Error("Unexpected response: 413");
    error.name = "UploadRequestError";
    error.status = 413;
    error.payload = {
      error_type: "upload_too_large",
      message: "File too large. Maximum supported size is 250 MB.",
    };

    expect(classifyUploadError(error, "upload")).toMatchObject({
      state: "error",
      retryable: false,
      status: 413,
      errorType: "upload_too_large",
      message: "File too large. Maximum supported size is 250 MB.",
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
      message: "Upload endpoint unavailable.",
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
