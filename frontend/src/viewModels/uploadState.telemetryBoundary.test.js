import { describe, expect, it } from "vitest";
import { extractTelemetryBoundaryMeta, normalizeLatestUploadPayload, resolveCurrentUploadResult } from "./uploadState";

function validResult(overrides = {}) {
  return {
    job_id: "job-valid",
    filename: "valid.csv",
    row_count: 10,
    sii_completed: true,
    sii_reliable_enough_to_show: true,
    sii_intelligence: { facility_state: "stable" },
    analysis_result: {
      schema_version: "2026-07",
      systems: [{ id: "pump", name: "Pump" }],
      relationships: [{ id: "r1", columns: ["pressure", "flow"] }],
      insights: [],
      fingerprint: { status: "stable" },
    },
    ...overrides,
  };
}

describe("telemetry workspace boundary normalization", () => {
  it("normalizes missing telemetry fields without rejecting the workspace", () => {
    const payload = normalizeLatestUploadPayload({ status: "complete", latest_result: validResult({ columns: undefined, detected_columns: undefined }) });
    const result = resolveCurrentUploadResult(payload);

    expect(payload._neraiumTelemetryBoundary.renderable).toBe(true);
    expect(result.columns).toEqual([]);
    expect(result.detected_columns).toEqual([]);
  });

  it("coerces null values in system and relationship collections", () => {
    const payload = normalizeLatestUploadPayload({
      status: "complete",
      latest_result: validResult({
        analysis_result: {
          systems: [null, "legacy system", { id: "valid", name: "Valid System" }],
          relationships: [null, "pressure / flow"],
          insights: [null],
        },
      }),
    });
    const analysis = resolveCurrentUploadResult(payload).analysis_result;

    expect(analysis.systems.map((system) => system.name)).toContain("legacy system");
    expect(analysis.relationships.map((relationship) => relationship.name)).toContain("pressure / flow");
    expect(payload._neraiumTelemetryBoundary.issues.some((issue) => issue.reason === "missing_collection_entry")).toBe(true);
  });

  it("keeps unknown system and relationship types renderable", () => {
    const payload = normalizeLatestUploadPayload({
      status: "complete",
      latest_result: validResult({
        analysis_result: {
          systems: [{ id: "mystery", name: "Mystery Source", type: "vendor_specific_live_connection" }],
          relationships: [{ id: "rel", change_type: "vendor_specific_relationship" }],
        },
      }),
    });

    expect(payload._neraiumTelemetryBoundary.renderable).toBe(true);
    expect(resolveCurrentUploadResult(payload).analysis_result.systems[0].type).toBe("vendor_specific_live_connection");
  });

  it("normalizes partial API responses to an empty renderable snapshot", () => {
    const payload = normalizeLatestUploadPayload({ status: "active", latest_result: null, history: null });

    expect(payload.history).toEqual([]);
    expect(resolveCurrentUploadResult(payload)).toBeNull();
    expect(payload._neraiumTelemetryBoundary.renderable).toBe(true);
  });

  it("retains stale cached state metadata for diagnostics", () => {
    const payload = normalizeLatestUploadPayload({
      status: "complete",
      last_processed_at: "2026-07-01T00:00:00Z",
      request_correlation_id: "corr-stale",
      latest_result: validResult(),
    });
    const meta = extractTelemetryBoundaryMeta(payload, resolveCurrentUploadResult(payload));

    expect(meta.telemetryTimestamp).toBe("2026-07-01T00:00:00Z");
    expect(meta.requestCorrelationId).toBe("corr-stale");
    expect(meta.referenceId).toMatch(/^NRA-/);
  });

  it("flags schema-version mismatch without crashing valid telemetry", () => {
    const payload = normalizeLatestUploadPayload({ status: "complete", latest_result: validResult({ schema_version: "2099-x" }) });

    expect(payload._neraiumTelemetryBoundary.renderable).toBe(true);
    expect(payload._neraiumTelemetryBoundary.issues.some((issue) => issue.reason === "schema_version_mismatch")).toBe(true);
  });
});
