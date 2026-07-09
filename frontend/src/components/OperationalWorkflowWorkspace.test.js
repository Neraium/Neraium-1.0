/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import OperationalWorkflowWorkspace from "./OperationalWorkflowWorkspace";

const h = React.createElement;
const snapshot = { status: "complete", sii_completed: true, processed_at: "2026-06-23T12:00:00Z", current_upload: { job_id: "ready-job", filename: "uploaded telemetry.csv", row_count: 120 } };

function renderWorkspace(props = {}) {
  return render(h(OperationalWorkflowWorkspace, {
    liveOps: {}, canonicalFinding: { exists: false }, currentSession: { hasReliableOperatorEvidence: false },
    effectiveLatestUploadResult: null, effectiveLatestUploadSnapshot: { status: "empty" },
    roomContext: { primary: "Primary System" }, domainDetection: { mode: "water_system" }, gateProcessing: null, ...props,
  }));
}

function result(analysisResult) {
  return { job_id: "ready-job", processed_at: "2026-06-23T12:00:00Z", columns: ["flow", "temperature"], result_source: "uploaded telemetry.csv", row_count: 120,
    sii_reliable_enough_to_show: true, sii_completed: true, sii_intelligence: { facility_state: "stable", baseline: { state: "stable" } },
    baseline_analysis: { status: "available" }, analysis_result: analysisResult };
}

function completeResult(overrides = {}) {
  return {
    ...result(overrides.analysis_result ?? {}),
    sii_intelligence: { facility_state: "stable", baseline: { state: "stable", confidence: 0.82 } },
    operator_report: { recommended_action: "Continue monitoring" },
    ...overrides,
  };
}

function completeSnapshot(overrides = {}) {
  return { ...snapshot, ...overrides };
}

function analysis({ second = true, reverse = false } = {}) {
  const evidence = [{ description: "Pump power and filter pressure relationship changed.", metric_delta: [{ tag_name: "pump_power_filter_dp", baseline_strength: 0.775497, current_strength: 0.063807, correlation_delta: 0.839304 }] }];
  if (second) evidence.push({ description: "Pump power and flow relationship changed.", metric_delta: [{ tag_name: "pump_power_flow", baseline_strength: reverse ? 0.61 : 0.72, current_strength: reverse ? -0.44 : 0.31, correlation_delta: reverse ? -1.05 : 0.41 }] });
  return { insights: [{ id: "pump-relationships", title: "Pump relationships changed", severity: "high", confidence: "high", system: "Pump system",
    contributing_relationships: [{ display_columns: ["Pump Power", "Filter DP"] }, { display_columns: ["Pump Power", "Flow"] }], evidence_items: evidence }],
    systems: [{ id: "pump", name: "Pump system" }], relationships: [], fingerprint: { status: "changed", meaning: "Pump behavior changed." } };
}

function analysisWithoutInsightIds() {
  const base = analysis();
  return {
    ...base,
    insights: base.insights.map((insight) => {
      const withoutId = { ...insight };
      delete withoutId.id;
      return withoutId;
    }),
  };
}


function clickNav(label) {
  const button = screen.getAllByRole("button").find((node) => node.textContent.includes(label));
  expect(button).toBeTruthy();
  fireEvent.click(button);
  return button;
}

function hasActiveNavButton(labelPattern) {
  return screen.getAllByRole("button", { name: labelPattern }).some((button) => button.getAttribute("aria-current") === "page");
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

    expect(screen.getByRole("heading", { name: "No Operational Fingerprint Established" })).toBeTruthy();
    expect(screen.getAllByText("Neraium").length).toBeGreaterThan(0);
    expect(screen.getByTestId("operational-orb")).toBeTruthy();
    expect(screen.getAllByText("Ready for Analysis")).toHaveLength(1);
    expect(screen.getByText("Connect historical or live telemetry to begin learning operational behavior.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Operational Fingerprint Not Yet Established" })).toBeTruthy();
    expect(screen.getByText("Connect live telemetry or analyze historical operational data to establish a behavioral baseline for this facility.")).toBeTruthy();
    expect(screen.getAllByText("Systems").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Insights").length).toBeGreaterThan(0);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Fingerprint").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not Established").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Data Sources").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not Connected").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Advanced").length).toBeGreaterThan(0);
    const commandCenterSystems = screen.getByLabelText("Systems requiring attention");
    expect(commandCenterSystems.querySelectorAll(".system-summary-row--dashboard")).toHaveLength(1);
    expect(commandCenterSystems.textContent).toContain("Systems Awaiting Discovery");
    expect(commandCenterSystems.textContent).toContain("Operational systems will automatically be identified after telemetry has been analyzed.");
    expect(commandCenterSystems.textContent).not.toContain("HVAC and Central Plant");
    expect(commandCenterSystems.textContent).not.toContain("Pools, Spas, and Water Features");
    expect(commandCenterSystems.textContent).not.toContain("Water Treatment and Pumping");
    expect(commandCenterSystems.textContent).not.toContain("Cooling Towers and Heat Rejection");
    expect(commandCenterSystems.textContent).not.toContain("Building Automation");
    expect(commandCenterSystems.textContent).not.toContain("Energy Infrastructure");
    expect(commandCenterSystems.textContent).not.toContain("Utility Distribution");
    expect(screen.getByLabelText("Neraium operational workspace").textContent).not.toMatch(/PLACEHOLDER|Placeholder/);
    expect(screen.getByRole("button", { name: "Analyze Historical Data" })).toBeTruthy();
    expect(screen.getByText("Platform initialized")).toBeTruthy();
    expect(screen.getByText("Waiting for telemetry connection")).toBeTruthy();
    expect(screen.getByText("Operational Fingerprint will be created after the first successful analysis")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Connect Live Data" })).toBeTruthy();
    expect(screen.getByLabelText("Neraium operational workspace").textContent).not.toMatch(/Current\s+Site/);
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

  it("Selecting a CSV prefers onCsvSelected, clears the input, and does not reset to Command Center", () => {
    const onCsvSelected = vi.fn();
    const onTelemetrySelected = vi.fn();
    renderWorkspace({ onCsvSelected, onTelemetrySelected });

    const input = screen.getByTestId("overview-csv-upload-input");
    const file = new File(["timestamp,flow\n2026-01-01,1"], "ops.csv", { type: "text/csv" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(onCsvSelected).toHaveBeenCalledTimes(1);
    expect(onCsvSelected.mock.calls[0][0]).toEqual([file]);
    expect(onTelemetrySelected).not.toHaveBeenCalled();
    expect(input.value).toBe("");
    expect(screen.getByRole("heading", { name: "Telemetry Sources" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Operational Fingerprint Not Yet Established" })).toBeNull();
  });

  it("Data Sources CSV Import uses the same hidden file-selection path", () => {
    const onCsvSelected = vi.fn();
    renderWorkspace({ onCsvSelected });

    clickNav("Data Sources");
    const input = screen.getByTestId("overview-csv-upload-input");
    const inputClick = vi.spyOn(input, "click");
    fireEvent.click(screen.getByRole("button", { name: /CSV Import/i }));
    expect(inputClick).toHaveBeenCalledTimes(1);

    const file = new File(["timestamp,flow\n2026-01-01,2"], "sources.csv", { type: "text/csv" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(onCsvSelected).toHaveBeenCalledTimes(1);
    expect(onCsvSelected.mock.calls[0][0]).toEqual([file]);
    expect(screen.getByRole("heading", { name: "Telemetry Sources" })).toBeTruthy();
  });

  it("Data Sources owns CSV import and planned telemetry connectors", () => {
    renderWorkspace();

    clickNav("Data Sources");
    expect(screen.getByRole("heading", { name: "Telemetry Sources" })).toBeTruthy();
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

  it("Systems view shows discovery guidance before telemetry", () => {
    renderWorkspace();

    clickNav("Systems");
    expect(screen.getByRole("heading", { name: "Systems Awaiting Discovery" })).toBeTruthy();
    expect(screen.getAllByText("Operational systems will automatically be identified after telemetry has been analyzed.").length).toBeGreaterThan(0);
    expect(screen.queryByText("HVAC and Central Plant")).toBeNull();
    expect(screen.queryByText("Pools, Spas, and Water Features")).toBeNull();
    expect(screen.queryByText("Cooling Towers and Heat Rejection")).toBeNull();
    expect(screen.queryByText("Expected resort domain example, not a detected system")).toBeNull();
    expect(screen.queryByText("Example, not detected")).toBeNull();
  });

  it("shows no numeric systems nav metric before telemetry analysis", () => {
    renderWorkspace();

    expect(screen.getAllByRole("button", { name: /Systems\s+(Pending|—)/ }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Systems\s+7\b/ })).toBeNull();
    const systemsNavText = screen.getAllByRole("button")
      .filter((button) => button.textContent.includes("Systems"))
      .map((button) => button.textContent.trim());
    expect(systemsNavText).not.toContain("Systems7");
  });

  it("counts only real detected systems after telemetry analysis", () => {
    const placeholderSystems = [
      "HVAC and Central Plant",
      "Pools, Spas, and Water Features",
      "Water Treatment and Pumping",
      "Cooling Towers and Heat Rejection",
      "Building Automation",
      "Energy Infrastructure",
      "Utility Distribution",
    ].map((name, index) => ({ id: "placeholder-" + index, name, placeholder: true }));

    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: {
        ...analysis(),
        systems: [...placeholderSystems, { id: "pump", name: "Pump system" }],
      } }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getAllByRole("button", { name: /Systems\s+1\b/ }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Systems\s+7\b/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Systems\s+8\b/ })).toBeNull();

    clickNav("Systems");
    expect(screen.getByText("Pump system")).toBeTruthy();
    expect(screen.queryByText("HVAC and Central Plant")).toBeNull();
  });

  it("opens the top Command Center insight in the Insights view", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisWithoutInsightIds() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    fireEvent.click(screen.getByRole("button", { name: "Open Insight" }));

    expect(screen.getByRole("heading", { name: "Operational Insights" })).toBeTruthy();
    expect(screen.getByLabelText("Insight detail")).toBeTruthy();
    expect(screen.getByText("What Changed")).toBeTruthy();
    expect(screen.getAllByText(/Pump system relationship shift detected/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Current Operating Picture" })).toBeNull();
    expect(hasActiveNavButton(/Insights\s+1\b/)).toBe(true);
    expect(hasActiveNavButton(/Command Center/)).toBe(false);
  });

  it("keeps Systems card Open Insight wired to the shared insight selection flow", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisWithoutInsightIds() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Systems");
    fireEvent.click(screen.getByRole("button", { name: "Open Insight" }));

    expect(screen.getByRole("heading", { name: "Operational Insights" })).toBeTruthy();
    expect(screen.getByLabelText("Insight detail")).toBeTruthy();
    expect(screen.getByText("What Changed")).toBeTruthy();
    expect(screen.getAllByText(/Pump system relationship shift detected/i).length).toBeGreaterThan(0);
    expect(hasActiveNavButton(/Insights\s+1\b/)).toBe(true);
    expect(hasActiveNavButton(/Systems\s+1\b/)).toBe(false);
  });

  it("six primary views have distinct responsibilities and layouts", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisWithRelationshipEvidence() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

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

  it("maps two changed relationships to two evidence lines", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysis() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Insights");
    expect(screen.getByText(/Pump Power \u2194 Filter DP: Unitless coupling score changed from 0\.78 to 0\.06/)).toBeTruthy();
    expect(screen.getByText(/Pump Power \u2194 Flow: Unitless coupling score changed from 0\.72 to 0\.31/)).toBeTruthy();
  });

  it("shows an explicit message when relationship evidence is missing", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysis({ second: false }) }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Insights");
    expect(screen.getByText(/Pump Power \u2194 Flow: change detected, but no quantitative measurement was included in this result/)).toBeTruthy();
  });

  it("formats evidence to two decimals and explains weakening", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysis() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Insights");
    const text = screen.getByLabelText("Neraium operational workspace").textContent;
    expect(text).toContain("0.78");
    expect(text).toContain("0.06");
    expect(text).toContain("0.84");
    expect(text).toContain("weakened sharply toward little linear coupling");
    expect(text).not.toMatch(/0\.775497|0\.063807|0\.839304/);
  });

  it("describes coupling sign reversal explicitly", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysis({ reverse: true }) }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Insights");
    expect(screen.getAllByText(/the relationship reversed direction/).length).toBeGreaterThan(0);
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
