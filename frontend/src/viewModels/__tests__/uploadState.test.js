import { describe, expect, it } from "vitest";
import { connectionStateLabel, deriveRoomContext, deriveTimeCoverage, hasVerifiedSiiCompletion, resolveCurrentUploadResult } from "../uploadState";

describe("uploadState normalization", () => {
  it("resolves room aliases from messy column names", () => {
    const result = {
      columns: ["Zone Name", "Growth-Stage", "Temp_C"],
      preview_rows: [
        { "Zone Name": "Flower-1", "Growth-Stage": "Late" },
      ],
      cultivation_mapping: { categories: { irrigation: [] } },
    };
    const context = deriveRoomContext(result);
    expect(context.primary).toBe("Flower-1");
    expect(context.cycle).toBe("Late");
  });

  it("derives timestamp coverage from preview rows when timestamp profile is missing", () => {
    const result = {
      columns: ["event_time", "Zone Name"],
      preview_rows: [
        { event_time: "2026-05-18T12:00:00Z" },
        { event_time: "2026-05-18T12:05:00Z" },
      ],
    };
    const coverage = deriveTimeCoverage(result);
    expect(coverage.hasCoverage).toBe(true);
    expect(coverage.summary).toContain("2026-05-18T12:00:00.000Z");
  });

  it("does not verify SII from a completion flag without a persisted backend result", () => {
    expect(hasVerifiedSiiCompletion({
      latestResult: null,
      latestSnapshot: {
        status: "COMPLETE",
        sii_completed: true,
        state_available: true,
      },
    })).toBe(false);
  });

  it("does not verify a synthetic result from replay shape alone", () => {
    expect(hasVerifiedSiiCompletion({
      latestResult: {
        sii_intelligence: {
          replay_timeline: {
            timeline: [{ cognition_state: { canonical_phase: "stable_topology" } }],
          },
        },
      },
      latestSnapshot: {
        status: "COMPLETE",
        sii_completed: false,
        state_available: false,
      },
    })).toBe(false);
  });

  it("labels an active upload as pending verification until review evidence is ready", () => {
    expect(connectionStateLabel("active", "complete", "", {
      status: "active",
      current_upload: {
        result: {
          job_id: "job-pending",
          sii_reliable_enough_to_show: false,
          engine_result: { overall_result: "drift" },
        },
      },
    })).toBe("Analysis pending verification");
  });

  it("keeps the active session label once operator review evidence is ready", () => {
    expect(connectionStateLabel("active", "complete", "", {
      status: "active",
      current_upload: {
        result: {
          job_id: "job-ready",
          sii_reliable_enough_to_show: true,
          engine_result: { overall_result: "stable" },
        },
      },
    })).toBe("Active Session");
  });

  it("prefers current_upload.result over legacy latest_result when both are present", () => {
    const resolved = resolveCurrentUploadResult({
      current_upload: {
        result: {
          job_id: "current-upload-job",
          engine_result: { overall_result: "stable" },
        },
      },
      latest_result: {
        job_id: "legacy-latest-job",
        engine_result: { overall_result: "stale" },
      },
    });

    expect(resolved?.job_id).toBe("current-upload-job");
  });

  it("falls back to legacy latest_result when canonical current_upload.result is absent", () => {
    const resolved = resolveCurrentUploadResult({
      current_upload: {
        result: null,
      },
      latest_result: {
        job_id: "legacy-latest-job",
        engine_result: { overall_result: "stable" },
      },
    });

    expect(resolved?.job_id).toBe("legacy-latest-job");
  });
});
