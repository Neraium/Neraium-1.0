import { describe, expect, it } from "vitest";
import { buildShiftBrief, deriveEscalationReadiness, deriveWorkspacePresentationState } from "../shiftBrief";

describe("workspace presentation states", () => {
  it("keeps no-data language separate from post-analysis evidence language", () => {
    expect(deriveWorkspacePresentationState({ hasAnalysis: false, processing: false }).key).toBe("noDataset");
    expect(deriveWorkspacePresentationState({ hasAnalysis: false, processing: false }).status).toBe("Baseline Needed");
    expect(deriveWorkspacePresentationState({ hasAnalysis: true, processing: true, result: {} }).key).toBe("analysisRunning");
    expect(deriveWorkspacePresentationState({ hasAnalysis: true, processing: false, status: "Evidence insufficient", result: { filename: "ready.csv" } }).key).toBe("datasetReady");
    expect(deriveWorkspacePresentationState({ hasAnalysis: true, processing: false, status: "Evidence insufficient", result: { sii_completed: true } }).key).toBe("insufficientEvidence");
    expect(deriveWorkspacePresentationState({ hasAnalysis: true, processing: false, status: "Normal", result: { sii_completed: true } }).key).toBe("noMeaningfulChanges");
    expect(deriveWorkspacePresentationState({ hasAnalysis: true, processing: false, status: "Normal", result: { sii_completed: true, legacy_analysis: true } }).key).toBe("legacyAnalysis");
  });
});

describe("serious escalation presentation gate", () => {
  const finding = {
    id: "f-1",
    tier: "Qualified",
    relationships: [{ id: "r-1" }, { id: "r-2" }],
  };
  const raw = {
    id: "f-1",
    strong_mode_match: true,
    persistent_change: true,
    critical_asset: true,
    known_operational_explanation: false,
  };
  const result = {
    data_quality: { coverage_percent: 90 },
    analysis_explanation: { insights: [raw] },
  };

  it("speaks up only when every requested condition is present", () => {
    expect(deriveEscalationReadiness(finding, result).serious).toBe(true);
    expect(deriveEscalationReadiness({ ...finding, relationships: [{ id: "r-1" }] }, result).serious).toBe(false);
    expect(deriveEscalationReadiness(finding, { ...result, data_quality: { coverage_percent: 50 } }).serious).toBe(false);
    expect(deriveEscalationReadiness(finding, { ...result, analysis_explanation: { insights: [{ ...raw, known_operational_explanation: true }] } }).serious).toBe(false);
  });

  it("does not infer missing operational context", () => {
    expect(deriveEscalationReadiness(finding, { data_quality: { coverage_percent: 100 }, analysis_explanation: { insights: [{ id: "f-1" }] } }).serious).toBe(false);
  });
});

describe("shift brief grouping", () => {
  it("keeps new, attention, monitoring, quiet, and resolved counts distinct", () => {
    const finding = { id: "f-1", tier: "Narrowed", relationships: [] };
    const brief = buildShiftBrief({
      findings: [finding],
      gaps: [{ id: "gap-1" }],
      subsystems: [{ id: "s-1", status: "Normal" }],
      result: { processed_at: "2026-07-26T05:00:00Z", resolved_items: [{ id: "r-1" }] },
    }, [], new Date("2026-07-26T06:00:00Z"));

    expect(brief.counts).toEqual({ newFindings: 1, escalations: 0, resolved: 1, monitoring: 1 });
    expect(brief.quietSystems).toHaveLength(1);
    const acknowledged = buildShiftBrief({ findings: [finding], result: { processed_at: "2026-07-26T05:00:00Z" } }, ["f-1"], new Date("2026-07-26T06:00:00Z"));
    expect(acknowledged.newFindings).toHaveLength(0);
    expect(acknowledged.needsAttention).toHaveLength(1);
  });
});
