import { describe, expect, it } from "vitest";
import { containsDisallowedOperatorTerms, deriveCanonicalFinding, normalizeFindingPresentation, OPERATOR_EMPTY_STATE } from "../operatorFinding";

function buildSession(result = null, snapshot = null) {
  return {
    latestUploadResult: result,
    latestUploadSnapshot: snapshot,
    hasRealSiiOutput: Boolean(result),
    hasReliableOperatorEvidence: Boolean(result?.sii_reliable_enough_to_show),
    reviewReadiness: result?.sii_reliable_enough_to_show ? "ready" : "quality_gate",
  };
}

describe("deriveCanonicalFinding", () => {
  it("returns the shared empty state when no current finding exists", () => {
    const finding = deriveCanonicalFinding({ currentSession: buildSession(null, { status: "empty" }) });

    expect(finding.exists).toBe(false);
    expect(finding.summary).toBe(OPERATOR_EMPTY_STATE.title);
    expect(finding.whyItMatters).toBe(OPERATOR_EMPTY_STATE.subtitle);
    expect(finding.emptyState.detail).toBe(OPERATOR_EMPTY_STATE.detail);
  });

  it("normalizes operator confidence and removes implementation terminology", () => {
    const finding = deriveCanonicalFinding({
      currentSession: buildSession({
        job_id: "job-1",
        observation_type: "trajectory_drift",
        drift_status: "elevated",
        relationship_summary: "relationship divergence detected from State Group A in replay/relationship evidence.",
        drift_metrics: { baseline_distance: 0.69, confidence: 0.7 },
        sii_reliable_enough_to_show: true,
        operator_report: {
          evidence_summary: ["latest_result shows upload_state changes in the observation grammar."],
        },
        sii_intelligence: { facility_state: "drift", confidence: 0.7 },
      }, { status: "complete", current_upload: { job_id: "job-1" } }),
    });

    expect(finding.exists).toBe(true);
    expect(finding.confidence).toBe("Moderate");
    expect(finding.status).toBe("High");
    expect(containsDisallowedOperatorTerms(finding.summary)).toBe(false);
    expect(containsDisallowedOperatorTerms(finding.whyItMatters)).toBe(false);
    expect(finding.supportingEvidence.some((item) => /current observation|current analysis|historical comparison evidence|observation method/i.test(item))).toBe(true);
  });

  it("holds insights in a pending state when telemetry is not yet reviewable", () => {
    const finding = deriveCanonicalFinding({
      currentSession: buildSession({
        job_id: "job-pending",
        observation_type: "trajectory_drift",
        drift_status: "elevated",
        drift_metrics: { baseline_distance: 0.69, confidence: 0.7 },
        sii_reliable_enough_to_show: false,
        sii_intelligence: { facility_state: "drift", confidence: 0.7 },
      }, { status: "complete", current_upload: { job_id: "job-pending" } }),
    });

    expect(finding.exists).toBe(false);
    expect(finding.status).toBe("Processing");
    expect(finding.confidence).toBe("Pending");
    expect(finding.summary).toMatch(/insights are not ready/i);
    expect(finding.reviewNext).toMatch(/complete dataset|data-quality warnings|run the analysis again/i);
  });
});

describe("normalizeFindingPresentation", () => {
  it("uses evidence-safe defaults for a legacy finding and structures plain guidance", () => {
    const normalized = normalizeFindingPresentation({
      title: "Historical finding",
      recommended_investigation: ["Review the original operator notes."],
    });

    expect(normalized.type).toBe("insufficient_evidence");
    expect(normalized.legacy).toBe(true);
    expect(normalized.classificationConfidence).toBe("Unavailable");
    expect(normalized.dataConfidence.rating).toBe("Unavailable");
    expect(normalized.operatingMode.match).toBe("Unavailable");
    expect(normalized.reasons[0]).toMatch(/before contextual classification was available/i);
    expect(normalized.investigationGuidance).toEqual([{
      rank: 1,
      check: "Review the original operator notes.",
      reason: "This check was retained from the historical finding; supporting rationale was not recorded.",
      category: "documentation",
      editable: true,
    }]);
  });

  it("preserves structured guidance without treating an unbounded duration as persistence", () => {
    const normalized = normalizeFindingPresentation({
      classification: { type: "unexplained_systemic_change", confidence: "high", reasons: ["Comparable modes matched."] },
      data_confidence: { rating: "high", summary: "Quality checks passed." },
      operating_mode: { match: "strong", confidence: "high" },
      persistence: { persistent: true, duration: "18 days" },
      investigation_guidance: [{ rank: 2, check: "Review the timeline.", reason: "The change persisted.", category: "operating_context", editable: true }],
    });

    expect(normalized.label).toBe("Unexplained systemic change");
    expect(normalized.persistence.label).toBe("Persistent");
    expect(normalized.persistence.duration).toBe("");
    expect(normalized.investigationGuidance[0].reason).toBe("The change persisted.");
  });

  it("does not create timeline milestones from persistence alone", () => {
    const withoutTimes = normalizeFindingPresentation({ persistence: { persistent: true } });
    const withRanges = normalizeFindingPresentation({
      source_time_ranges: [{
        baseline_start: "2026-06-01T00:00:00Z",
        baseline_end: "2026-06-30T23:59:00Z",
        current_start: "2026-07-01T00:00:00Z",
        current_end: "2026-07-18T23:59:00Z",
      }],
    });

    expect(withoutTimes.timeline).toEqual([]);
    expect(withRanges.timeline.map((item) => item.eventType)).toEqual(["baseline_reference", "analysis_window"]);
    expect(withRanges.timeline.every((item) => item.start || item.end)).toBe(true);
  });
});
