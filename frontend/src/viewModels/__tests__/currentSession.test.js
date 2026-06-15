import { describe, expect, it } from "vitest";
import { deriveCurrentSession, resolveSessionJobId } from "../currentSession";

describe("currentSession view model", () => {
  it("derives a stable session contract", () => {
    const session = deriveCurrentSession({
      latestUploadResult: { job_id: "job-1" },
      latestUploadSnapshot: { history: [{ job_id: "job-0" }] },
      hasActiveSession: true,
      hasCurrentUploadResult: true,
      hasResumedSession: false,
      hasRealSiiOutput: true,
    });

    expect(session.hasActiveSession).toBe(true);
    expect(session.latestUploadResult?.job_id).toBe("job-1");
  });

  it("resolves job id from canonical current upload identity and does not fall back to stale history", () => {
    expect(resolveSessionJobId({
      latestUploadResult: { job_id: "job-primary" },
      latestUploadSnapshot: { history: [{ job_id: "job-history" }] },
    })).toBe("job-primary");

    expect(resolveSessionJobId({
      latestUploadResult: null,
      latestUploadSnapshot: {
        current_upload: { job_id: "job-current" },
        history: [{ job_id: "job-history" }],
      },
    })).toBe("job-current");

    expect(resolveSessionJobId({
      latestUploadResult: null,
      latestUploadSnapshot: { history: [{ job_id: "job-history" }] },
    })).toBe(null);
  });
});
