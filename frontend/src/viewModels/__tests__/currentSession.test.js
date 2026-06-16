import { describe, expect, it } from "vitest";
import { deriveCurrentSession, resolveSessionJobId } from "../currentSession";

describe("currentSession view model", () => {
  it("derives a stable session contract", () => {
    const session = deriveCurrentSession({
      latestUploadResult: { job_id: "job-1", sii_reliable_enough_to_show: true },
      latestUploadSnapshot: {
        history: [{ job_id: "job-0" }],
        current_upload: { job_id: "job-1" },
        system_interpretation: {
          lineage: { job_id: "job-1", aligned: true },
          run_alignment_verified: true,
        },
      },
      hasActiveSession: true,
      hasCurrentUploadResult: true,
      hasResumedSession: false,
      hasRealSiiOutput: true,
    });

    expect(session.hasActiveSession).toBe(true);
    expect(session.latestUploadResult?.job_id).toBe("job-1");
    expect(session.hasReliableOperatorEvidence).toBe(true);
    expect(session.reviewReadiness).toBe("ready");
  });

  it("does not mark operator evidence ready when the reliability gate is not satisfied", () => {
    const session = deriveCurrentSession({
      latestUploadResult: { job_id: "job-1", sii_reliable_enough_to_show: false },
      latestUploadSnapshot: {
        current_upload: { job_id: "job-1" },
        system_interpretation: {
          lineage: { job_id: "job-1", aligned: true },
          run_alignment_verified: true,
        },
      },
      hasActiveSession: true,
      hasCurrentUploadResult: true,
      hasResumedSession: false,
      hasRealSiiOutput: true,
    });

    expect(session.hasReliableOperatorEvidence).toBe(false);
    expect(session.reviewReadiness).toBe("quality_gate");
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
