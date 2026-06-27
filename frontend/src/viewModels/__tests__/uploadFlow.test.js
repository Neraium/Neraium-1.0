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
});
