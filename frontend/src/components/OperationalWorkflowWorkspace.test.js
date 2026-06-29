/* @vitest-environment jsdom */
import React from "react";
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
    expect(screen.queryByText("No telemetry uploaded")).toBeNull();
    expect(screen.getByText("NERAIUM SII")).toBeTruthy();
    expect(screen.getAllByText("Waiting for telemetry")).toHaveLength(1);
    expect(screen.getAllByText("Start with telemetry")).toHaveLength(1);
    expect(screen.getByText("Upload a CSV to begin analysis.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Upload CSV" })).toBeTruthy();
    expect(screen.queryByText("Current Picture")).toBeNull();
    expect(screen.queryByText("Data source")).toBeNull();
    expect(screen.queryByText("Active Insights")).toBeNull();
    expect(screen.queryByText("Systems Pending")).toBeNull();
    expect(screen.queryByText("Fingerprint Status")).toBeNull();
    expect(screen.queryByText(/systems monitored/i)).toBeNull();
    expect(screen.queryByText(/systems identified/i)).toBeNull();
    expect(screen.queryByText("Baseline Established")).toBeNull();
  });

  it("does not treat an empty data source as loaded telemetry", () => {
    renderWorkspace({
      effectiveLatestUploadResult: telemetryResult({ result_source: "empty" }),
      effectiveLatestUploadSnapshot: { status: "empty", current_upload: null },
    });

    expect(screen.queryByText("No Telemetry Loaded")).toBeNull();
    expect(screen.queryByText("Waiting for Telemetry")).toBeNull();
    expect(screen.queryByText("No telemetry uploaded")).toBeNull();
    expect(screen.getAllByText("Start with telemetry")).toHaveLength(1);
    expect(screen.getByText("Upload a CSV to begin analysis.")).toBeTruthy();
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
    expect(screen.getAllByText("Start with telemetry")).toHaveLength(1);
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
    expect(screen.getAllByText("SII is analyzing telemetry, identifying system behavior, and mapping relationships.").length).toBeGreaterThan(0);
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
    expect(screen.getByText("Analysis based on uploaded telemetry")).toBeTruthy();
    expect(screen.getByText("Historical telemetry analyzed.")).toBeTruthy();
    expect(screen.getByText("Overall operational status")).toBeTruthy();
    expect(screen.getByText("Recommended action")).toBeTruthy();
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
    expect(screen.getAllByText("Live telemetry connected").length).toBeGreaterThan(0);
    expect(screen.getByText("Overall operational status")).toBeTruthy();
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
        confidence_rationale: "Confidence score 0.91 is based on 18 baseline samples, 18 current samples, and correlation delta 1.11.",
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

    renderWorkspace({
      liveOps: { relationshipRows: [{ columns: ["pressure", "flow"], summary: "Pressure / flow relationship changed." }] },
      effectiveLatestUploadResult: completeResult({
        operating_state: "Structural drift observed",
        analysis_explanation: analysisExplanation,
      }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getByText("Overall operational status")).toBeTruthy();
    expect(screen.getByText("Pressure and flow relationship shifted")).toBeTruthy();
    expect(screen.getByText("Pump cycling may increase")).toBeTruthy();
    expect(screen.getAllByText("Check pump schedule and valve position").length).toBeGreaterThan(0);
    expect(screen.queryByText("Systems identified")).toBeNull();

    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Insights")));
    expect(screen.getByText("Why Neraium thinks it happened")).toBeTruthy();
    expect(screen.getByText("The signals stopped moving together like the baseline window.")).toBeTruthy();
    expect(screen.getByText("What could happen next")).toBeTruthy();
    expect(screen.getByText("Evidence (high)")).toBeTruthy();
    expect(screen.getByText("Confidence rationale")).toBeTruthy();
    expect(screen.getByText("Pressure increased 18%; Flow decreased 9%")).toBeTruthy();
    expect(screen.getByText("Source columns")).toBeTruthy();
    expect(screen.getByText("Source time ranges")).toBeTruthy();
    expect(screen.getByText("Pressure increased 18%")).toBeTruthy();
    expect(screen.getByText("Pattern persisted for 36 hours")).toBeTruthy();
    expect(screen.queryByText("Maintenance correlation will appear when maintenance history is connected.")).toBeNull();
  });

  it("keeps the Systems section pending before analysis", () => {
    renderWorkspace({
      liveOps: {
        systems: [{ id: "system-1", name: "Chilled Water Loop" }],
      },
    });

    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Systems")));

    expect(screen.getAllByText("Systems Pending").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Run analysis to identify systems and relationships.").length).toBeGreaterThan(0);
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
        highest_priority_finding: "Pump power moved up",
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
        title: "Pump power moved up",
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

    renderWorkspace({
      effectiveLatestUploadResult: completeResult({
        analysis_result: analysisResult,
        analysis_explanation: null,
      }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Insights")));

    expect(screen.getAllByText("Pump power moved up").length).toBeGreaterThan(0);
    expect(screen.getByText("Evidence (moderate)")).toBeTruthy();
    expect(screen.getAllByText("Pump power baseline average increased in the current window.").length).toBeGreaterThan(0);
    expect(screen.getByText(/percent change: 22/)).toBeTruthy();
    expect(screen.queryByText("Unavailable")).toBeNull();
  });
});
