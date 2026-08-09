import { describe, expect, it } from "vitest";
import { buildOperationsBrief, deriveEscalationReadiness, deriveWorkspacePresentationState } from "../operationsBrief";

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
    classification: { type: "unexplained_systemic_change", confidence: "high" },
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

  it("keeps legacy and missing context conservative", () => {
    expect(deriveEscalationReadiness({ ...finding, classification: null }, result).serious).toBe(false);
    expect(deriveEscalationReadiness(finding, { data_quality: { coverage_percent: 100 }, analysis_explanation: { insights: [{ id: "f-1" }] } }).serious).toBe(false);
  });

  it("honors governed condition escalation for isolated evidence", () => {
    const condition = {
      ...finding,
      id: "condition-1",
      objectType: "condition",
      relationships: [{ id: "r-1" }],
      corroboration: { relationship_count: 1, corroboration_strength: "isolated" },
      escalation: {
        level: "hold",
        eligible: false,
        prompt_engineering_review: false,
        rule_version: "deterministic_condition_escalation_v1",
        inputs: {
          classification: "unexplained_systemic_change",
          operating_mode_match: "strong",
          data_quality: "high",
          criticality: "critical",
          trajectory: "Strengthening",
        },
      },
    };

    const readiness = deriveEscalationReadiness(condition, {
      analysis_explanation: { conditions: [{ ...condition, object_type: "condition" }] },
    });

    expect(readiness.serious).toBe(false);
    expect(readiness.eligible).toBe(false);
    expect(readiness.multipleSupportingRelationships).toBe(false);
    expect(readiness.level).toBe("hold");
  });
});

describe("operations brief grouping and ranking", () => {
  const systemic = (id, generatedAt) => ({
    id,
    title: id,
    tier: "Qualified",
    generatedAt,
    classification: { type: "unexplained_systemic_change", confidence: "high" },
    persistence: { persistent: true },
    relationships: [{ id: `${id}-r1` }],
  });

  it("keeps new, attention, monitoring, and resolved items distinct", () => {
    const newFinding = systemic("new", "2026-07-26T05:00:00Z");
    const olderFinding = systemic("older", "2026-07-24T05:00:00Z");
    const checkingFinding = systemic("checking", "2026-07-23T05:00:00Z");
    const explainedFinding = systemic("explained", "2026-07-22T05:00:00Z");
    const brief = buildOperationsBrief({
      findings: [olderFinding, checkingFinding, explainedFinding, newFinding],
      gaps: [{ id: "gap-1" }],
      result: { resolved_items: [{ id: "r-1", title: "Prior change resolved" }] },
    }, {
      checking: { state: "investigating" },
      explained: { state: "explained", reviewedAt: "2026-07-25T08:00:00Z" },
    }, new Date("2026-07-26T06:00:00Z"));

    expect(brief.newFindings.map((item) => item.id)).toEqual(["new"]);
    expect(brief.needsAttention.map((item) => item.id)).toEqual(["older"]);
    expect(brief.monitoringFindings.map((item) => item.id)).toEqual(["checking"]);
    expect(brief.monitoringIssues).toHaveLength(1);
    expect(brief.recentlyResolved.map((item) => item.id)).toEqual(["explained", "r-1"]);
  });

  it("does not call an undated or reviewed finding new", () => {
    const undated = systemic("undated", "");
    const reviewed = systemic("reviewed", "2026-07-26T05:00:00Z");
    const brief = buildOperationsBrief({ findings: [undated, reviewed], result: {} }, { reviewed: { state: "acknowledged" } }, new Date("2026-07-26T06:00:00Z"));
    expect(brief.newFindings).toHaveLength(0);
    expect(brief.needsAttention.map((item) => item.id)).toEqual(["undated", "reviewed"]);
  });

  it("orders contextual findings ahead of legacy labels without exposing a score", () => {
    const legacy = { id: "legacy", title: "Critical legacy label", tier: "Confirmed", generatedAt: "2026-07-25T05:00:00Z", relationships: [] };
    const contextual = systemic("contextual", "2026-07-25T05:00:00Z");
    const brief = buildOperationsBrief({ findings: [legacy, contextual], result: {} }, {}, new Date("2026-07-26T06:00:00Z"));
    expect(brief.priorityFinding.id).toBe("contextual");
    expect(brief.priorityExplanation).not.toMatch(/score|\d+/i);
  });

  it("labels a strengthening trajectory as evidence rather than behavior direction", () => {
    const finding = systemic("evidence-trend", "2026-07-25T05:00:00Z");
    const brief = buildOperationsBrief({
      findings: [finding],
      result: {
        analysis_explanation: {
          insights: [{ id: finding.id, trajectory: { state: "Strengthening", scope: "evidence_support" } }],
        },
      },
    }, {}, new Date("2026-07-26T06:00:00Z"));

    expect(brief.priorityExplanation).toContain("strengthening evidence");
    expect(brief.priorityExplanation).not.toContain("strengthening change");
  });

  it("keeps recently resolved history restrained", () => {
    const findings = Array.from({ length: 7 }, (_, index) => systemic(`resolved-${index}`, "2026-07-20T05:00:00Z"));
    const records = Object.fromEntries(findings.map((finding, index) => [finding.id, { state: "explained", reviewedAt: index === 6 ? "2026-07-01T05:00:00Z" : `2026-07-2${index}T05:00:00Z` }]));
    const brief = buildOperationsBrief({ findings, result: {} }, records, new Date("2026-07-26T06:00:00Z"));
    expect(brief.recentlyResolved).toHaveLength(5);
    expect(brief.recentlyResolved.map((item) => item.id)).not.toContain("resolved-6");
  });
});
