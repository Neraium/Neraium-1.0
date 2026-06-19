/* @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearLatestUploadStateCache, fetchLatestUploadState } from "./uploadApi";

function createResponse(payload) {
  return {
    ok: true,
    json: async () => payload,
  };
}

describe("fetchLatestUploadState", () => {
  beforeEach(() => {
    clearLatestUploadStateCache();
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
});
