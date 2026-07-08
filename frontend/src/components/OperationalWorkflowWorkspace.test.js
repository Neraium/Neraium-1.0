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

function clickNav(label) {
  const button = screen.getAllByRole("button").find((node) => node.textContent.includes(label));
  expect(button).toBeTruthy();
  fireEvent.click(button);
  return button;
}

function analysisWithRelationshipEvidence() {
  return {
    analysis_id: "analysis-1",
    source_file: "canonical.csv",
    generated_at: "2026-06-23T12:00:00Z",
    data_quality: { warnings: [] },
    executive_summary: {
      overall_operational_status: "Current behavior changed",
      highest_priority_finding: "Pressure and flow relationship shifted",
      recommended_action: "Check pump schedule and valve position",
    },
    systems: [{ id: "flow-pressure", name: "Flow and pressure system" }],
    relationships: [{ id: "relationship-0", columns: ["pressure", "flow"], change_type: "weakened" }],
    fingerprint: {
      status: "changed",
      meaning: "The operating fingerprint is changing because pressure and flow stopped moving together like the baseline window.",
      evidence_refs: ["ev-1"],
    },
    insights: [{
      id: "pressure-flow",
      title: "Pressure and flow relationship shifted",
      severity: "high",
      confidence: "high",
      confidence_score: 0.91,
      system: "Flow and pressure system",
      what_changed: "Pressure increased while flow decreased in the recent window.",
      why_it_matters: "The system is moving away from its normal operating behavior.",
      recommended_check: "Check pump schedule and valve position",
      contributing_relationships: [{ id: "relationship-0", columns: ["pressure", "flow"], change_type: "weakened" }],
      evidence_refs: ["ev-1"],
    }],
    evidence_index: {
      "ev-1": {
        evidence_id: "ev-1",
        type: "relationship_change",
        description: "Pressure and flow relationship weakened.",
        supporting_signals: ["Pressure increased 18%", "Flow decreased 9%"],
        relevant_metric_changes: ["Pump runtime increased 14%"],
        source_columns: ["pressure", "flow"],
        source_time_ranges: [{ label: "relationship_comparison", baseline_start: "2026-06-23T09:00:00Z", baseline_end: "2026-06-23T21:00:00Z", current_start: "2026-06-24T09:00:00Z", current_end: "2026-06-24T21:00:00Z" }],
        calculated_delta: 1.111111,
        persistence_duration: "Pattern persisted for 36 hours",
        confidence: "high",
        confidence_score: 0.91,
      },
    },
  };
}

afterEach(() => {
  cleanup();
});

describe("OperationalWorkflowWorkspace system-first architecture", () => {
  it("opens to Command Center with Neraium branding, orb, and fingerprint empty state", () => {
    renderWorkspace();

    expect(screen.getByRole("heading", { name: "Command Center" })).toBeTruthy();
    expect(screen.getAllByText("Neraium").length).toBeGreaterThan(0);
    expect(screen.getByTestId("operational-orb")).toBeTruthy();
    expect(screen.getAllByText("Awaiting Operational Fingerprint").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Connect telemetry or analyze historical data to establish an Operational Fingerprint.").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Analyze Historical Data" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Connect Live Data" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /CSV Import/i })).toBeNull();
  });

  it("Analyze Historical Data opens the existing hidden file picker path", () => {
    const onCsvSelected = vi.fn();
    renderWorkspace({ onCsvSelected });

    const input = screen.getByTestId("overview-csv-upload-input");
    const inputClick = vi.spyOn(input, "click");
    fireEvent.click(screen.getByRole("button", { name: "Analyze Historical Data" }));
    expect(inputClick).toHaveBeenCalledTimes(1);

    const file = new File(["timestamp,flow\n2026-01-01,1"], "ops.csv", { type: "text/csv" });
    fireEvent.change(input, { target: { files: [file] } });
    expect(onCsvSelected).toHaveBeenCalledTimes(1);
    expect(onCsvSelected.mock.calls[0][0]).toEqual([file]);
  });

  it("Data Sources owns CSV import and planned telemetry connectors", () => {
    renderWorkspace();

    clickNav("Data Sources");
    expect(screen.getByRole("heading", { name: "Data Sources" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /CSV Import/i })).toBeTruthy();
    expect(screen.getByText("Analyze Historical Data")).toBeTruthy();
    expect(screen.getByText("Connect Live Telemetry")).toBeTruthy();
    expect(screen.getByText("OPC-UA")).toBeTruthy();
    expect(screen.getByText("MQTT")).toBeTruthy();
    expect(screen.getByText("PI System")).toBeTruthy();
    expect(screen.getByText("SCADA/BMS connectors")).toBeTruthy();
    expect(screen.getByText("Control-system writeback")).toBeTruthy();
    expect(screen.getByText("Disabled")).toBeTruthy();
  });

  it("Systems view uses resort infrastructure placeholders before telemetry", () => {
    renderWorkspace();

    clickNav("Systems");
    expect(screen.getByRole("heading", { name: "Awaiting Telemetry" })).toBeTruthy();
    expect(screen.getByText("HVAC and Central Plant")).toBeTruthy();
    expect(screen.getByText("Pools, Spas, and Water Features")).toBeTruthy();
    expect(screen.getByText("Cooling Towers and Heat Rejection")).toBeTruthy();
    expect(screen.getAllByText("Awaiting Operational Fingerprint").length).toBeGreaterThan(0);
  });

  it("six primary views have distinct responsibilities and layouts", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisWithRelationshipEvidence() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getByRole("heading", { name: "Command Center" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Current Operating Picture" })).toBeTruthy();

    clickNav("Systems");
    expect(screen.getAllByRole("heading", { name: "Systems" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Relationship Drift")).toBeTruthy();

    clickNav("Insights");
    expect(screen.getByRole("heading", { name: "Operational Insights" })).toBeTruthy();
    expect(screen.getByText("What Changed")).toBeTruthy();

    clickNav("Fingerprint");
    expect(screen.getAllByRole("heading", { name: "Operational Fingerprint" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Behavior Windows")).toBeTruthy();
    expect(screen.getByText("System Relationship Changes")).toBeTruthy();

    clickNav("Data Sources");
    expect(screen.getByRole("heading", { name: "Telemetry Sources" })).toBeTruthy();

    clickNav("Advanced");
    expect(screen.getAllByRole("heading", { name: "Advanced Details" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Raw Result JSON")).toBeTruthy();
  });

  it("keeps insights system-level and maps relationship claims to relationship evidence", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisWithRelationshipEvidence() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Insights");
    expect(screen.getAllByText(/Flow and pressure system relationship shift detected/i).length).toBeGreaterThan(0);
    expect(screen.getByText("What Changed")).toBeTruthy();
    expect(screen.getByText("Evidence")).toBeTruthy();
    expect(screen.getByText("Changed Relationships")).toBeTruthy();
    expect(screen.getByText("Recommended Review")).toBeTruthy();
    expect(screen.getAllByText("pressure \u2194 flow").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pressure and flow relationship weakened.").length).toBeGreaterThan(0);
    expect(screen.queryByText("[object Object]")).toBeNull();
    expect(screen.queryByText(/1\.111111/)).toBeNull();
  });

  it("keeps raw identifiers and JSON in Advanced instead of Command Center", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisWithRelationshipEvidence() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.queryByText("Raw Result JSON")).toBeNull();
    clickNav("Advanced");
    expect(screen.getByText("Raw Result JSON")).toBeTruthy();
    expect(screen.getByText("Raw Relationship Identifiers")).toBeTruthy();
    expect(screen.getByText("Source signals")).toBeTruthy();
    expect(screen.getByText("Source time ranges")).toBeTruthy();
  });
});
