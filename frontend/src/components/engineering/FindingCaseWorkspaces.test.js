/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { FindingReviewWorkspace, InvestigationWorkspace, SiiEvidenceRecord } from "./FindingCaseWorkspaces";

afterEach(cleanup);

describe("authoritative SII evidence disclosure", () => {
  it("keeps uncertainty, quality, Phase 3/4, propagation, and provenance in structured disclosure", () => {
    render(React.createElement(SiiEvidenceRecord, { evidence: {
      source: "sii_result",
      status: "complete",
      engine: { name: "SII", version: "4.2" },
      relationship_changes: [{ id: "rel-1", source: "Flow", target: "Pressure", change_type: "weakened", baseline_correlation: 0.91, current_correlation: 0.42 }],
      operating_context: { status: "comparable", baseline_mode: "running", recent_mode: "running", match: "strong" },
      persistence: { status: "persistent", method: "elapsed_time_support" },
      uncertainty: { status: "limited", limitations: ["Missing samples reduce confidence."] },
      data_quality: { status: "degraded", analysis_gate_state: "DEGRADED_READY", warnings: ["Historian coverage was reduced."] },
      sensor_health: { status: "limited", signals: [{ signal: "Pressure", health: "suspect" }] },
      configured_prior_observations: [{ observation_id: "prior-1", behavioral_status: "not_consistent_with_configured_expectation", human_review_required: true }],
      phase_4: {
        status: "complete",
        available: true,
        behavioral_evolution: { status: "complete", evidence_classification: "persistent_behavioral_change", limitations: ["Evolution does not establish future failure."] },
        propagation: { status: "complete", candidate_paths: [{ path_id: "path-1", nodes: ["Flow", "Pressure"], compatibility: 0.81, causal_claim: false }] },
      },
      provenance: { analysis_run_id: "run-42", baseline_id: "baseline-7", input_hash: "input-hash" },
    } }));

    const record = screen.getByTestId("sii-evidence-record");
    for (const heading of ["Relationship evidence", "Operating context", "Persistence", "Uncertainty and data quality", "Sensor health", "Configured-prior evidence · Phase 3", "Behavioral evolution · Phase 4", "Provenance"]) {
      expect(within(record).getByRole("heading", { name: heading })).toBeTruthy();
    }
    expect(record.textContent).toContain("Missing samples reduce confidence");
    expect(record.textContent).toContain("Historian coverage was reduced");
    expect(record.textContent).toContain("Pressure · Suspect");
    expect(record.textContent).toContain("Flow → Pressure");
    expect(record.textContent).toContain("baseline-7");
    expect(record.textContent).toContain("Separate canonical SII comparison");
  });

  it("states unavailable Phase 4 evidence without inventing propagation", () => {
    render(React.createElement(SiiEvidenceRecord, { evidence: {
      source: "sii_result",
      status: "limited",
      phase_4: { status: "unavailable", available: false, limitations: ["Authenticated workspace identity unavailable."], propagation: {} },
      provenance: {},
    } }));

    const record = screen.getByTestId("sii-evidence-record");
    expect(record.textContent).toContain("Authenticated workspace identity unavailable");
    expect(within(record).queryByText("Propagation evidence")).toBeNull();
  });
});

function evidenceFinding() {
  return {
    id: "finding-evidence",
    title: "Cooling relationship changed",
    system: "Cooling plant",
    status: "Change detected",
    tier: "Qualified",
    objectType: "condition",
    observedChange: "Return temperature and chiller power no longer follow the learned relationship.",
    whyItMatters: "The change affects two connected operating signals.",
    primaryLimitation: "Operating context differs from baseline.",
    confidenceReason: "Operating context differs from baseline.",
    supporting: ["Return temperature / power changed during the current window."],
    visibleSupporting: ["Return temperature / power changed during the current window."],
    rawVariables: ["chw_return_temp_f", "chiller_power_kw"],
    variables: ["Return temperature", "Chiller power"],
    location: { label: "Cooling plant", system: "Cooling plant" },
    comparison: { metric: "pearson_correlation", baselineValue: 0.88, currentValue: 0.2, signedChange: -0.68, absoluteChange: 0.68, direction: "decreased", baseline: "Learned baseline", current: "Current comparison" },
    relationships: [{ id: "rel-1", source: "Return temperature", target: "Chiller power", rawSource: "chw_return_temp_f", rawTarget: "chiller_power_kw", metric: "pearson_correlation", baseline: 0.88, current: 0.2, signedChange: -0.68, absoluteChange: 0.68, relationshipDirection: "decreased", baselineSampleCount: 120, currentSampleCount: 48, windows: [{ start: "2026-08-25T04:00:00Z", end: "2026-08-25T05:23:56.206210+00:00" }] }],
    classification: { type: "context_limited_relationship_change", confidence: "limited", reasons: ["Operating conditions differed from baseline."], certainty_limit: "The evidence does not establish a cause." },
    dataConfidence: { rating: "medium", summary: "Usable with limits." },
    operatingMode: { match: "weak", confidence: "limited", baseline_mode_label: "Mid load", recent_mode_label: "High load", reasons: ["Load differed from baseline."] },
    persistence: { status: "observing", persistent: false },
    investigationGuidance: [{ rank: 1, check: "Verify the relevant source signals.", reason: "Source validation bounds interpretation.", category: "instrumentation" }],
    activityTimeline: [{ event_type: "finding_generated", title: "Finding generated", time: "2026-08-25T05:23:56.206210+00:00" }],
    generatedAt: "2026-08-25T05:23:56.206210+00:00",
    evidenceObjects: [],
    technicalLimitations: [],
    contradictions: [],
    limitations: ["Operating context differs from baseline."],
    confidenceDimensions: { changeDetection: { level: "high" }, interpretation: { level: "low", attribution_status: "unattributed" }, evidenceQuality: { level: "medium" }, operatingContext: { level: "low" } },
    corroboration: { corroboration_strength: "limited", relationship_count: 1 },
    comparableOperation: {},
    conflictingRelationships: [],
    uncertainRelationships: [],
  };
}

describe("review and investigation hierarchy", () => {
  it("keeps review decision-oriented with mapped classification explanation and guidance", () => {
    render(React.createElement(FindingReviewWorkspace, { finding: evidenceFinding(), reviewRecord: { state: "new" } }));
    for (const heading of ["What changed", "Why this deserves attention", "Important limitations", "What to check first"]) expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    expect(screen.getByText("The relationship changed, but recent operating conditions differ too much from the learned baseline to determine why.")).toBeTruthy();
    expect(screen.getByText("Verify the relevant source signals.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Relationships changed" })).toBeNull();
  });

  it("reveals relationship values, samples, source signals, and localized evidence time in investigation", () => {
    render(React.createElement(InvestigationWorkspace, { model: { result: {}, facilityTimeZone: "America/Los_Angeles", nodes: [] }, finding: evidenceFinding(), reviewRecord: { state: "new" } }));
    expect(screen.getByText("Correlation strength decreased by 0.68 from the learned baseline.")).toBeTruthy();
    expect(screen.getByText("120 baseline · 48 current")).toBeTruthy();
    expect(screen.getAllByText("chw_return_temp_f").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Aug 24, 2026 · 10:23 PM PDT").length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Investigation guidance" })).toBeNull();
  });
});
