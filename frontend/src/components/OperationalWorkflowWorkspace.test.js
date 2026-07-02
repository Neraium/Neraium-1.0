/* @vitest-environment jsdom */
import React from "react";
import fs from "node:fs";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import OperationalWorkflowWorkspace from "./OperationalWorkflowWorkspace";

const h = React.createElement;

function renderWorkspace(props = {}) {
  return render(h(OperationalWorkflowWorkspace, {
    liveOps: {},
    canonicalFinding: { exists: false },
    currentSession: { hasReliableOperatorEvidence: false },
    effectiveLatestUploadResult: null,
    effectiveLatestUploadSnapshot: { status: "empty" },
    roomContext: { primary: "Primary System" },
    domainDetection: { mode: "water_system" },
    gateProcessing: null,
    ...props,
  }));
}

function telemetryResult(overrides = {}) {
  return {
    job_id: "telemetry-job",
    processed_at: "2026-06-23T12:00:00Z",
    columns: ["flow", "temperature"],
    result_source: "uploaded telemetry.csv",
    row_count: 120,
    data_quality: { warnings: [] },
    ...overrides,
  };
}

function completeResult(overrides = {}) {
  return {
    ...telemetryResult(),
    job_id: "ready-job",
    sii_reliable_enough_to_show: true,
    sii_completed: true,
    sii_intelligence: { facility_state: "stable", baseline: { state: "stable", confidence: 0.82 } },
    baseline_analysis: { status: "available" },
    operator_report: { recommended_action: "Continue monitoring" },
    ...overrides,
  };
}

function completeSnapshot(overrides = {}) {
  return {
    status: "complete",
    sii_completed: true,
    processed_at: "2026-06-23T12:00:00Z",
    current_upload: { job_id: "ready-job", filename: "uploaded telemetry.csv", row_count: 120 },
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("OperationalWorkflowWorkspace product story states", () => {
  it("shows a truthful empty state before telemetry is loaded", () => {
    renderWorkspace();

    expect(screen.queryByText("No Telemetry Loaded")).toBeNull();
    expect(screen.queryByText("Waiting for Telemetry")).toBeNull();
    expect(screen.queryByText("Waiting for telemetry")).toBeNull();
    expect(screen.queryByText("No telemetry uploaded")).toBeNull();
    expect(screen.getAllByText("Neraium").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Current Site").length).toBeGreaterThan(0);
    expect(screen.getByText("Start Analysis")).toBeTruthy();
    expect(screen.getByText("Upload a CSV to begin.")).toBeTruthy();
    expect(screen.getByText("No file selected.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Upload CSV" })).toBeTruthy();
    expect(screen.queryByText(/Command Pulse/i)).toBeNull();
    expect(screen.queryByText("Current Picture")).toBeNull();
    expect(screen.queryByText("Data source")).toBeNull();
    expect(screen.queryByText("Active Insights")).toBeNull();
    expect(screen.queryByText("Systems Pending")).toBeNull();
    expect(screen.queryByText("No Operating Fingerprint Yet")).toBeNull();
    expect(screen.queryByText("Fingerprint Status")).toBeNull();
    expect(screen.queryByText("Last analysis: No analysis yet")).toBeNull();
    expect(screen.queryByText(/systems monitored/i)).toBeNull();
    expect(screen.queryByText(/systems identified/i)).toBeNull();
    expect(screen.queryByText("Baseline Established")).toBeNull();
    expect(screen.queryByRole("button", { name: /Systems\s+Pending/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Fingerprint\s+No Operating Fingerprint Yet/i })).toBeNull();
    expect(screen.getAllByRole("button", { name: /Insights\s+—/ }).every((button) => button.disabled)).toBe(true);
    expect(screen.getAllByRole("button", { name: /Systems\s+—/ }).every((button) => button.disabled)).toBe(true);
    expect(screen.getAllByRole("button", { name: /Fingerprint\s+—/ }).every((button) => button.disabled)).toBe(true);
    expect(screen.getAllByRole("button", { name: /Evidence\s+—/ }).every((button) => button.disabled)).toBe(true);
  });

  it("does not treat an empty data source as loaded telemetry", () => {
    renderWorkspace({
      effectiveLatestUploadResult: telemetryResult({ result_source: "empty" }),
      effectiveLatestUploadSnapshot: { status: "empty", current_upload: null },
    });

    expect(screen.queryByText("No Telemetry Loaded")).toBeNull();
    expect(screen.queryByText("Waiting for Telemetry")).toBeNull();
    expect(screen.queryByText("No telemetry uploaded")).toBeNull();
    expect(screen.getAllByText("Start Analysis")).toHaveLength(1);
    expect(screen.getByText("Upload a CSV to begin.")).toBeTruthy();
    expect(screen.queryByText("Data source")).toBeNull();
    expect(screen.queryByText("Telemetry Loaded")).toBeNull();
    expect(screen.queryByText("CSV loaded / Ready to analyze")).toBeNull();
  });

  it("does not show ready to analyze when upload metadata is missing", () => {
    renderWorkspace({
      effectiveLatestUploadResult: telemetryResult({ job_id: undefined, upload_id: undefined }),
      effectiveLatestUploadSnapshot: { status: "complete", current_upload: null },
    });

    expect(screen.queryByText("No Telemetry Loaded")).toBeNull();
    expect(screen.getAllByText("Start Analysis")).toHaveLength(1);
    expect(screen.queryByText("CSV loaded / Ready to analyze")).toBeNull();
    expect(screen.queryByText("Telemetry Loaded")).toBeNull();
  });

  it("shows telemetry loaded for a valid upload before analysis", () => {
    renderWorkspace({
      effectiveLatestUploadResult: telemetryResult(),
      effectiveLatestUploadSnapshot: {
        status: "complete",
        current_upload: { job_id: "telemetry-job", filename: "uploaded telemetry.csv", row_count: 120 },
      },
    });

    expect(screen.getAllByText("Telemetry Loaded").length).toBeGreaterThan(0);
    expect(screen.queryByText("No Telemetry Loaded")).toBeNull();
  });

  it("shows telemetry loaded but not analyzed as ready to analyze", () => {
    renderWorkspace({
      effectiveLatestUploadResult: telemetryResult({ sii_intelligence: { facility_state: "stable" } }),
      effectiveLatestUploadSnapshot: { status: "uploaded", current_upload: { job_id: "telemetry-job" } },
      liveOps: {
        systems: [{ id: "system-1", name: "Chilled Water Loop" }],
      },
    });

    expect(screen.getAllByText("CSV loaded / Ready to analyze").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Upload is available. Run analysis to identify systems, relationships, anomalies, and baseline behavior.").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Analyze CSV" })).toBeTruthy();
    expect(screen.queryByText("Systems Pending")).toBeNull();
    expect(screen.queryByText("1 system identified")).toBeNull();
    expect(screen.queryByText(/systems monitored/i)).toBeNull();
  });

  it("shows analysis running and disables duplicate analyze actions", () => {
    const onWorkspaceNavigate = vi.fn();
    renderWorkspace({
      effectiveLatestUploadResult: telemetryResult({ processing_state: "processing" }),
      effectiveLatestUploadSnapshot: { status: "processing", current_upload: { job_id: "telemetry-job" } },
      gateProcessing: { active: true, status: "processing" },
      onWorkspaceNavigate,
    });

    const analyzeButton = screen.getByRole("button", { name: "Building Fingerprint" });
    expect(screen.getAllByText("Building Operating Fingerprint").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Analyzing telemetry, identifying system behavior, and mapping relationships.").length).toBeGreaterThan(0);
    expect(analyzeButton.disabled).toBe(true);
    fireEvent.click(analyzeButton);
    expect(onWorkspaceNavigate).not.toHaveBeenCalled();
  });

  it("shows completed analysis with compact results and historical telemetry copy", () => {
    renderWorkspace({
      liveOps: {
        systems: [
          { id: "system-1", name: "Chilled Water Loop" },
          { id: "system-2", name: "Condenser Water Loop" },
          { id: "system-3", name: "Boiler Loop" },
          { id: "system-4", name: "Air Handling" },
          { id: "system-5", name: "Electrical" },
          { id: "system-6", name: "Pumps" },
        ],
        relationshipRows: [{ columns: ["flow", "temperature"] }, { columns: ["pressure", "valve"] }],
        siiVerification: { verified: true },
      },
      effectiveLatestUploadResult: completeResult(),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getAllByText("Analysis Complete").length).toBeGreaterThan(0);
    expect(screen.getByText("Historical telemetry analyzed.")).toBeTruthy();
    expect(screen.getByText("Systems identified")).toBeTruthy();
    expect(screen.getByText("Relationship changes detected")).toBeTruthy();
    expect(screen.getByText("Baseline updated")).toBeTruthy();
    expect(screen.getByText("Overall Status")).toBeTruthy();
    expect(screen.getByText("Recommended Next Check")).toBeTruthy();
    expect(screen.queryByText("Telemetry Needs Review")).toBeNull();
    expect(screen.queryByText("Telemetry acceptable")).toBeNull();
    expect(screen.queryByText("Analysis completed with minor data quality warnings")).toBeNull();
    expect(screen.getAllByText("Continue monitoring").length).toBeGreaterThan(0);
    expect(screen.queryByText("Relationships mapped")).toBeNull();
    expect(screen.queryByText("Baseline confidence")).toBeNull();
    expect(screen.queryByText("Top risk")).toBeNull();
    expect(screen.queryByText("Active Insights")).toBeNull();
    expect(screen.queryByText("Fingerprint Status")).toBeNull();
    expect(screen.queryByText(/systems monitored/i)).toBeNull();
  });

  it("uses monitored copy only when completed analysis has live telemetry", () => {
    renderWorkspace({
      liveOps: {
        systems: [{ id: "system-1", name: "Chilled Water Loop" }],
        relationshipRows: [],
        siiVerification: { verified: true },
        telemetryConnected: true,
        connectionStatusLine: "Live telemetry connected",
      },
      effectiveLatestUploadResult: completeResult(),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getAllByText("Monitoring Live").length).toBeGreaterThan(0);
    expect(screen.getByText("Live telemetry is connected and current behavior is being monitored.")).toBeTruthy();
    expect(screen.queryByText("Telemetry Needs Review")).toBeNull();
    expect(screen.getByText("Overall Status")).toBeTruthy();
    expect(screen.queryByText("systems monitored")).toBeNull();
  });

  it("renders explanatory analysis outputs with evidence and hides unavailable fields", () => {
    const analysisExplanation = {
      executive_summary: {
        overall_operational_status: "Structural drift observed",
        highest_priority_finding: "Pressure and flow relationship shifted",
        biggest_emerging_risk: "Pump cycling may increase",
        recommended_action: "Check pump schedule and valve position",
      },
      insights: [{
        id: "pressure-flow",
        title: "Pressure and flow relationship shifted",
        severity: "high",
        explanation: "Pressure increased while flow decreased in the recent window.",
        likely_cause: "The signals stopped moving together like the baseline window.",
        possible_consequence: "Pump cycling may increase",
        recommended_action: "Check pump schedule and valve position",
        operator_check: "Inspect pump runtime and downstream valve position.",
        confidence: "high",
        confidence_score: 0.91,
        evidence_summary: "Pressure increased 18%; Flow decreased 9%",
        system: "Flow and pressure system",
        contributing_metrics: [{ name: "pressure", source_column: "pressure" }, { name: "flow", source_column: "flow" }],
        contributing_relationships: [{ id: "relationship-0", columns: ["pressure", "flow"], change_type: "weakened" }],
        evidence_items: [{
          type: "relationship_change",
          summary: "Pressure and flow relationship weakened.",
          confidence: "high",
          confidence_score: 0.91,
          supporting_signals: ["Pressure increased 18%", "Flow decreased 9%"],
          relevant_metric_changes: ["Pump runtime increased 14%"],
          source_columns: ["pressure", "flow"],
          source_time_ranges: [{ label: "relationship_comparison", baseline_start: "2026-06-23T09:00:00Z", baseline_end: "2026-06-23T21:00:00Z", current_start: "2026-06-24T09:00:00Z", current_end: "2026-06-24T21:00:00Z" }],
          calculated_delta: 1.11,
          time_window: "2026-06-23T09:00:00Z to 2026-06-24T21:00:00Z",
          persistence_duration: "Pattern persisted for 36 hours",
        }],
      }],
      systems: [{
        id: "flow-pressure",
        name: "Flow and pressure system",
        health_status: "Needs review",
        confidence: "high",
        key_behaviors: ["Pressure is rising while flow is falling."],
        what_changed: ["Pressure/flow coupling diverged from baseline."],
        relationships: ["Pressure / flow relationship changed."],
      }],
      fingerprint: {
        status: "changed",
        meaning: "The operating fingerprint is changing. The largest deviation is increased pump cycling beginning around 09:30.",
        largest_deviation: "increased pump cycling",
        confidence: "high",
      },
    };

    const view = renderWorkspace({
      liveOps: { relationshipRows: [{ columns: ["pressure", "flow"], summary: "Pressure / flow relationship changed." }] },
      effectiveLatestUploadResult: completeResult({
        operating_state: "Structural drift observed",
        analysis_explanation: analysisExplanation,
      }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getByText("Overall Status")).toBeTruthy();
    expect(screen.getByText("Operational instability observed")).toBeTruthy();
    expect(screen.getByText("Pressure and flow relationship shifted")).toBeTruthy();
    expect(screen.getByText("Pump cycling may increase")).toBeTruthy();
    expect(screen.getAllByText("Check pump schedule and valve position").length).toBeGreaterThan(0);
    expect(screen.getByText("Systems identified")).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Insights")));
    expect(screen.getByRole("heading", { name: "Operator Briefing" })).toBeTruthy();
    expect(screen.getByText("What Changed")).toBeTruthy();
    expect(screen.getByText("Why It Matters")).toBeTruthy();
    expect(screen.queryByText("Why Neraium believes this matters")).toBeNull();
    expect(screen.queryByText("Evidence summary")).toBeNull();
    expect(screen.getByText("One operating relationship within the Flow and pressure system deviated from its historical operating pattern during the analysis period.")).toBeTruthy();
    expect(screen.getByText("The subsystem is no longer behaving the way it normally does.")).toBeTruthy();
    expect(screen.getByText("Possible Operational Causes")).toBeTruthy();
    expect(screen.getByText("Pump operating point changed")).toBeTruthy();
    expect(screen.getByText("Relationships Observed")).toBeTruthy();
    expect(screen.getByText("pressure ↔ flow")).toBeTruthy();
    expect(screen.queryByText(/correlation delta/i)).toBeNull();
    const drawer = view.container.querySelector("details.insight-evidence-drawer");
    expect(drawer).toBeTruthy();
    expect(drawer.open).toBe(false);
    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Evidence")));
    expect(screen.getByRole("heading", { name: "Supporting Telemetry" })).toBeTruthy();
    const details = view.container.querySelector("details.evidence-panel");
    expect(details).toBeTruthy();
    expect(details.open).toBe(false);
    expect(screen.getAllByText("Evidence").length).toBeGreaterThan(0);
    expect(screen.getByText("Source signals")).toBeTruthy();
    expect(screen.getByText("Source time ranges")).toBeTruthy();
    expect(screen.getByText("Pressure increased 18%")).toBeTruthy();
    expect(screen.getByText("Pattern persisted for 36 hours")).toBeTruthy();
    expect(screen.queryByText("Maintenance correlation will appear when maintenance history is connected.")).toBeNull();
  });

  it("keeps overall status consistent when a finding contradicts baseline wording", () => {
    const analysisResult = {
      executive_summary: {
        overall_operational_status: "Baseline-aligned",
        highest_priority_finding: "Flow / Pressure subsystem behavior changed",
        biggest_emerging_risk: "Pressure response may drift from normal control behavior.",
        recommended_action: "Check pressure valve response.",
      },
      insights: [{
        id: "flow-pressure-change",
        title: "Flow / Pressure subsystem behavior changed",
        severity: "moderate",
        possible_consequence: "Pressure response may drift from normal control behavior.",
        operator_check: "Check pressure valve response.",
        system: "Flow / Pressure subsystem",
      }],
      systems: [{ id: "flow-pressure", name: "Flow / Pressure subsystem" }],
      relationships: [{ columns: ["flow", "pressure"], change_type: "changed" }],
      fingerprint: { status: "changed", meaning: "Flow and pressure behavior changed against baseline." },
    };

    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisResult }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getByText("Localized subsystem change detected")).toBeTruthy();
    expect(screen.getByText("Flow / Pressure subsystem behavior changed")).toBeTruthy();
    expect(screen.queryByText("Baseline-aligned")).toBeNull();
    expect(screen.queryByText("Telemetry Needs Review")).toBeNull();
  });

  it("formats confidence, dedupes factors, and summarizes missing telemetry", () => {
    const analysisResult = {
      executive_summary: {
        overall_operational_status: "Persistent structural drift",
        highest_priority_finding: "Pump vibration increased sharply",
        recommended_action: "Prioritize pump mechanical review.",
      },
      data_quality: {
        warnings: [],
        signal_integrity: [
          { signal_id: "supply_pressure", gap_type: "short_drop", completeness: 0.996, suppress_confidence: false },
          { signal_id: "pump_vibration", gap_type: "short_drop", completeness: 0.996, suppress_confidence: false },
        ],
        missing_values: [],
      },
      insights: [{
        id: "pump-vibration",
        title: "Pump vibration increased sharply",
        severity: "high",
        what_happened: "Pump vibration increased by 440% versus baseline.",
        why_neraium_thinks_it_happened: "Baseline/current comparison and recent-window persistence support the change.",
        possible_operational_consequence: "Bearing wear may accelerate if the vibration persists.",
        operator_check: "Inspect pump bearings and mounting condition.",
        recommended_action: "Prioritize pump mechanical review and trend the vibration signal.",
        confidence: "high",
        confidence_score: 1,
        evidence_summary: "Percent change: 440%",
        system: "Flow and pressure system",
        contributing_factors: ["pump vibration", "pump vibration"],
      }],
      systems: [],
      relationships: [],
      fingerprint: { drift_status: "changed", explanation: "Persistent structural drift is present." },
    };

    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisResult }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
    });

    expect(screen.getByText("2 telemetry signals contained intermittent missing values")).toBeTruthy();
    expect(screen.queryByText("Telemetry Needs Review")).toBeNull();

    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("More")));
    expect(screen.getAllByText("0.4% missing values detected in supply pressure and pump vibration. Confidence reduced slightly.").length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Insights")));
    expect(screen.getAllByText("High").length).toBeGreaterThan(0);
    expect(screen.queryByText("high (1)")).toBeNull();
    expect(screen.queryByText("pump vibration")).toBeNull();
    expect(screen.queryByText("Supporting measurements are available in Evidence.")).toBeNull();
  });

  it("shows reduced-confidence copy only when quality materially affects interpretation", () => {
    const analysisResult = {
      executive_summary: {
        recommended_action: "Confirm source historian export.",
      },
      data_quality: {
        warnings: [],
        signal_integrity: [
          { signal_id: "flow", gap_type: "extended_gap", completeness: 0.72, suppress_confidence: true },
        ],
        missing_values: [],
      },
      insights: [],
      systems: [],
      relationships: [],
      fingerprint: { status: "stable", meaning: "Current behavior remains close to the baseline." },
    };

    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisResult }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getByText("Analysis completed with reduced confidence.")).toBeTruthy();
    expect(screen.queryByText("Telemetry Needs Review")).toBeNull();
  });

  it("disables result tabs before analysis", () => {
    renderWorkspace({
      effectiveLatestUploadResult: telemetryResult(),
      effectiveLatestUploadSnapshot: {
        status: "complete",
        current_upload: { job_id: "telemetry-job", filename: "uploaded telemetry.csv", row_count: 120 },
      },
      liveOps: {
        systems: [{ id: "system-1", name: "Chilled Water Loop" }],
      },
    });

    const systemButtons = screen.getAllByRole("button", { name: /Systems\s+—/ });
    expect(systemButtons.every((button) => button.disabled)).toBe(true);
    fireEvent.click(systemButtons[0]);

    expect(screen.getAllByText("CSV loaded / Ready to analyze").length).toBeGreaterThan(0);
    expect(screen.queryByText("Systems Pending")).toBeNull();
    expect(screen.queryByText("Run analysis to identify systems and relationships.")).toBeNull();
    expect(screen.queryByText("Chilled Water Loop")).toBeNull();
  });

  it("renders canonical analysis evidence and hides unavailable fields", () => {
    const analysisResult = {
      analysis_id: "analysis-1",
      upload_id: "upload-1",
      source_file: "canonical.csv",
      generated_at: "2026-06-23T12:00:00Z",
      data_quality: { warnings: [] },
      executive_summary: {
        overall_operational_status: "Current behavior changed",
        highest_priority_finding: "Pump subsystem behavior changed",
        recommended_action: "Check pump schedule",
      },
      systems: [{ id: "pump", name: "Pump system", relationship_changes: [] }],
      relationships: [],
      fingerprint: {
        drift_status: "changed",
        explanation: "The operating fingerprint changed against the baseline window.",
        confidence: "moderate",
        evidence_refs: ["ev-1"],
      },
      insights: [{
        id: "insight-1",
        title: "Pump subsystem behavior changed",
        severity: "moderate",
        confidence: "moderate",
        affected_systems: ["Pump system"],
        what_changed: "Pump power increased in the current window.",
        why_it_matters: "The system is moving away from its normal operating behavior.",
        recommended_check: "Check pump schedule",
        possible_consequence: "Pump runtime may increase.",
        source_tags: ["pump_power"],
        time_window: "2026-06-23T09:00:00Z to 2026-06-23T12:00:00Z",
        evidence_refs: ["ev-1"],
      }],
      recommendations: [{ id: "rec-1", recommendation: "Check pump schedule", evidence_refs: ["ev-1"] }],
      evidence_index: {
        "ev-1": {
          evidence_id: "ev-1",
          type: "metric_delta",
          description: "Pump power baseline average increased in the current window.",
          source_tags: ["pump_power"],
          metric_delta: [{ tag_name: "pump_power", percent_change: 22 }],
          time_window: "2026-06-23T09:00:00Z to 2026-06-23T12:00:00Z",
          confidence: "moderate",
          calculation_method: "Metric delta from baseline average versus current average.",
        },
      },
      warnings: [],
      errors: [],
    };

    const view = renderWorkspace({
      effectiveLatestUploadResult: completeResult({
        analysis_result: analysisResult,
        analysis_explanation: null,
      }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Insights")));

    expect(screen.getAllByText("Pump subsystem behavior changed").length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Evidence")));
    const details = view.container.querySelector("details.evidence-panel");
    expect(details).toBeTruthy();
    expect(details.open).toBe(false);
    expect(screen.getAllByText("Evidence").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pump power baseline average increased in the current window.").length).toBeGreaterThan(0);
    expect(screen.getByText(/percent change: 22/)).toBeTruthy();
    expect(screen.queryByText("Unavailable")).toBeNull();
  });

  it("does not render replay artifacts in normal result sections", () => {
    const analysisResult = {
      change_onset: "2026-06-23T09:00:00Z",
      stable_window: { label: "Stable window", time_window: "2026-06-23T00:00:00Z to 2026-06-23T09:00:00Z" },
      deviation_window: { label: "Deviation window", time_window: "2026-06-23T09:00:00Z to 2026-06-23T12:00:00Z" },
      current_state_window: { label: "Current state window", time_window: "2026-06-23T11:00:00Z to 2026-06-23T12:00:00Z" },
      executive_summary: {
        overall_operational_status: "Current behavior changed",
        highest_priority_finding: "Pump power moved up",
        recommended_action: "Check pump schedule",
      },
      insights: [{
        id: "insight-1",
        title: "Pump power moved up",
        severity: "moderate",
        confidence: "moderate",
        what_changed: "Pump power increased in the current window.",
        recommended_check: "Check pump schedule",
        evidence_refs: ["ev-1"],
      }],
      systems: [{ id: "pump", name: "Pump system", health_status: "Needs review" }],
      relationships: [],
      fingerprint: { status: "changed", explanation: "The operating fingerprint changed." },
      recommendations: [],
      evidence_index: {
        "ev-1": { evidence_id: "ev-1", description: "Pump power increased in the current window." },
      },
    };

    renderWorkspace({
      effectiveLatestUploadResult: completeResult({
        analysis_result: analysisResult,
        replay_ready: true,
        replay_frame_count: 3,
        replay_timeline: { timeline: [{ frame_number: 0, summary: "legacy replay frame" }] },
        sii_intelligence: { facility_state: "stable", replay_timeline: { timeline: [{ frame_number: 0 }] } },
      }),
      effectiveLatestUploadSnapshot: completeSnapshot({ replay_ready: true, replay_frame_count: 3 }),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.queryByText(/replay/i)).toBeNull();
    expect(screen.queryByText(/Advanced Details/i)).toBeNull();

    for (const label of ["More", "Insights", "Systems", "Fingerprint", "Evidence"]) {
      const tab = screen.getAllByRole("button").find((button) => button.textContent.includes(label));
      expect(tab).toBeTruthy();
      fireEvent.click(tab);
      expect(screen.queryByText(/replay/i)).toBeNull();
      expect(screen.queryByText(/Advanced Details/i)).toBeNull();
    }
  });

  it("removes internal pipeline copy from rendered result pages", () => {
    const analysisResult = {
      executive_summary: {
        overall_operational_status: "Backend pipeline replay requires review",
        highest_priority_finding: "Raw tag-pair pressure_flow headline",
        biggest_emerging_risk: "Pipeline replay drift may confuse operators",
        recommended_action: "Check Column 3 against pump pressure",
      },
      insights: [{
        id: "internal-copy",
        title: "Raw tag-pair pressure_flow headline",
        severity: "high",
        confidence: "high",
        what_changed: "Backend pipeline replay changed Column 3",
        why_it_matters: "Raw replay output should not appear to operators",
        recommended_check: "Check Column 3 against pump pressure",
        evidence_items: [{
          description: "Backend pipeline replay evidence for Column 3",
          confidence: "high",
          source_columns: ["Column 3", "pump_pressure"],
        }],
      }],
      systems: [{ id: "pump", name: "Pump system" }],
      relationships: [{ pair: "tag:pump_pressure::tag:flow", detail: "backend pipeline replay pair" }],
      fingerprint: { status: "changed", explanation: "Raw replay fingerprint text" },
    };

    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisResult }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    const main = screen.getByLabelText("Neraium operational workspace");
    expect(main.textContent).not.toMatch(/\bbackend\b|\bpipeline\b|\breplay\b|\braw\b|tag-pair|Column 3|SII/i);

    for (const label of ["Insights", "Systems", "Fingerprint", "Evidence", "More"]) {
      const tab = screen.getAllByRole("button").find((button) => button.textContent.includes(label));
      fireEvent.click(tab);
      expect(main.textContent).not.toMatch(/\bbackend\b|\bpipeline\b|\breplay\b|\braw\b|tag-pair|Column 3|SII/i);
    }
  });

  it("keeps mobile result cards from crowding", () => {
    const css = fs.readFileSync("src/styles/operational-workflow.css", "utf8");

    expect(css.includes("(max-width: 520px)")).toBe(true);
    expect(css.includes("grid-template-columns: repeat(3, minmax(0, 1fr));")).toBe(true);
    expect(css.includes("grid-template-columns: 1fr;")).toBe(true);
    expect(css.includes(".insight-card__actions > *")).toBe(true);
  });
});
