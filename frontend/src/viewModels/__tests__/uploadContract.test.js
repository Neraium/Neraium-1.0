import { describe, expect, it } from "vitest";
import { hasSupportedSiiClaims, normalizeUploadJob } from "../uploadContract";

describe("upload reliability contract", () => {
  it("preserves cleaning, runtime, evidence, and display reliability fields", () => {
    const job = normalizeUploadJob({
      status: "complete",
      ingestion_report: {
        rows_received: 20,
        rows_used: 17,
        rows_dropped: 3,
        drop_reasons: { duplicate_timestamp: 2, invalid_timestamp: 1 },
      },
      processing_stats: { processing_time_seconds: 1.25 },
      data_quality: { warnings: ["3 rows were dropped during safe cleaning."] },
      evidence_persistence: { persisted: true },
      sii_reliable_enough_to_show: false,
    });

    expect(job.rows_received).toBe(20);
    expect(job.rows_used).toBe(17);
    expect(job.rows_dropped).toBe(3);
    expect(job.drop_reasons.duplicate_timestamp).toBe(2);
    expect(job.processing_time_seconds).toBe(1.25);
    expect(job.quality_warning).toContain("3 rows");
    expect(job.evidence_persisted).toBe(true);
    expect(job.sii_reliable_enough_to_show).toBe(false);
  });
});


describe("unsupported SII claim guard", () => {
  it("does not mark claims as supported without persisted evidence and display reliability", () => {
    expect(hasSupportedSiiClaims({
      sii_reliable_enough_to_show: true,
      evidence_persistence: { persisted: false },
    })).toBe(false);

    const job = normalizeUploadJob({
      status: "complete",
      sii_reliable_enough_to_show: false,
      evidence_persistence: { persisted: true },
      primary_driver: "unsupported drift claim",
    });

    expect(job.supported_sii_claims).toBe(false);
  });

  it("marks claims as supported only after reliability and evidence persistence are both true", () => {
    const job = normalizeUploadJob({
      status: "complete",
      sii_reliable_enough_to_show: true,
      evidence_persistence: { persisted: true },
    });

    expect(job.supported_sii_claims).toBe(true);
  });
});
