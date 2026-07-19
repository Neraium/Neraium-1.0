/* @vitest-environment jsdom */
import { afterEach, describe, expect, it } from "vitest";
import { readAnalysisHistory } from "../analysisHistory";

const HISTORY_KEY = "neraium.completed_analysis_history";

function productionLegacyHistoryRecord() {
  const analysis = {
    analysis_id: "6978182b61ab41e6898a259e31070fac",
    generated_at: "2026-07-18T14:24:12.697477+00:00",
    source_file: "neraium chilled water dataset blind.csv",
    fingerprint: { status: "changed" },
    systems: Array.from({ length: 4 }, (_, index) => ({ id: `system-${index}`, name: `System ${index + 1}` })),
    insights: Array.from({ length: 4 }, (_, index) => ({ id: `insight-${index}`, title: `Insight ${index + 1}` })),
  };
  const result = {
    job_id: "6978182b61ab41e6898a259e31070fac",
    filename: "neraium chilled water dataset blind.csv",
    status: "complete",
    processing_state: "complete",
    completed_at: "2026-07-18T14:24:12.697477+00:00",
    row_count: 5856,
    sii_completed: true,
    sii_reliable_enough_to_show: true,
    data_quality: { warnings: ["chiller_power_kW recent window is highly variable."] },
    analysis_result: analysis,
  };
  const currentUpload = {
    job_id: "6978182b61ab41e6898a259e31070fac",
    filename: "neraium chilled water dataset blind.csv",
    status: "complete",
    result,
  };
  const snapshot = {
    status: "complete",
    processing_state: "complete",
    session_state: "verified",
    sii_completed: true,
    rows_processed: 5856,
    columns_detected: 19,
    last_processed_at: "2026-07-18T14:24:12.697477+00:00",
    current_upload: currentUpload,
  };

  return {
    id: "legacy-production-payload-object-display",
    jobId: { job_id: currentUpload.job_id },
    datasetName: currentUpload,
    timestamp: { processed_at: snapshot.last_processed_at },
    fingerprintStatus: analysis.fingerprint,
    systemsCount: { count: 4 },
    insightsCount: { count: 4 },
    savedAt: { processed_at: snapshot.last_processed_at },
    result,
    snapshot,
  };
}

afterEach(() => {
  window.localStorage.clear();
});

describe("analysis history storage", () => {
  it("normalizes the production latest-upload legacy object display payload", () => {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify([productionLegacyHistoryRecord()]));

    const [record] = readAnalysisHistory();

    expect(record).toMatchObject({
      jobId: "6978182b61ab41e6898a259e31070fac",
      datasetName: "neraium chilled water dataset blind.csv",
      timestamp: "2026-07-18T14:24:12.697477+00:00",
      fingerprintStatus: "Changed",
      systemsCount: 4,
      insightsCount: 4,
    });
    expect(Object.values(record).some((value) => value && typeof value === "object" && !Array.isArray(value))).toBe(true);
    expect(typeof record.datasetName).toBe("string");
    expect(typeof record.timestamp).toBe("string");
    expect(typeof record.fingerprintStatus).toBe("string");
  });
});
