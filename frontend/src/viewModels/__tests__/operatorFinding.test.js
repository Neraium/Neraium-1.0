import { describe, expect, it } from "vitest";
import { containsDisallowedOperatorTerms, deriveCanonicalFinding, OPERATOR_EMPTY_STATE } from "../operatorFinding";

function buildSession(result = null, snapshot = null) {
  return {
    latestUploadResult: result,
    latestUploadSnapshot: snapshot,
    hasRealSiiOutput: Boolean(result),
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
        operator_report: {
          evidence_summary: ["latest_result shows upload_state changes in the observation grammar."],
        },
        sii_intelligence: { facility_state: "drift", confidence: 0.7 },
      }, { status: "complete", current_upload: { job_id: "job-1" } }),
    });

    expect(finding.exists).toBe(true);
    expect(finding.confidence).toBe("Moderate");
    expect(finding.status).toBe("Behavior Change Detected");
    expect(containsDisallowedOperatorTerms(finding.summary)).toBe(false);
    expect(containsDisallowedOperatorTerms(finding.whyItMatters)).toBe(false);
    expect(finding.supportingEvidence.some((item) => /current observation|current analysis|historical comparison evidence|observation method/i.test(item))).toBe(true);
  });
});
