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
    why_it_matters: "Operational impact: This relationship change is consistent with conditions such as increasing hydraulic resistance, equipment degradation, operational changes, or recent maintenance. Investigation is recommended to determine the cause.",
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
      why_it_matters: "Operational impact: This relationship change is consistent with conditions such as increasing hydraulic resistance, equipment degradation, operational changes, or recent maintenance. Investigation is recommended to determine the cause.",
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
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("OperationalWorkflowWorkspace system-first architecture", () => {
  it("opens to a focused Command Center with status, insights, and system sections", () => {
    renderWorkspace();

    expect(screen.getByText("Watching")).toBeTruthy();
    expect(screen.getAllByText("Neraium").length).toBeGreaterThan(0);
    expect(screen.queryByTestId("operational-orb")).toBeNull();
    expect(screen.getByRole("heading", { name: "Operational Fingerprint Summary" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Subsystem Behavior" })).toBeTruthy();
    expect(screen.getAllByRole("heading", { name: "Engineering Findings" }).length).toBeGreaterThan(0);
    expect(screen.getByText("None active")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Selected Investigation" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Discovered Systems" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Analysis Details" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Import and Analyze Dataset" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Open Insight" })).toBeNull();
    expect(screen.queryByLabelText("Systems requiring attention")).toBeNull();
    expect(screen.getByRole("button", { name: "Connect Live Telemetry" })).toBeTruthy();
    expect(screen.getByLabelText("Neraium platform workspace").textContent).not.toMatch(/PLACEHOLDER|Placeholder|Current\s+Site/);
    expect(screen.queryByRole("heading", { name: /Choose Dataset/i })).toBeNull();
  });

  it("Datasets & Connectors analysis action opens the existing hidden file picker path", () => {
    const onCsvSelected = vi.fn();
    renderWorkspace({ onCsvSelected });

    const input = screen.getByTestId("overview-csv-upload-input");
    const inputClick = vi.spyOn(input, "click");
    clickNav("Datasets & Connectors");
    fireEvent.click(screen.getByRole("button", { name: /Choose Dataset/i }));
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
    expect(screen.getByRole("heading", { name: "Data Source Status" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Baseline Needed" })).toBeNull();
  });

  it("Datasets & Connectors CSV Import uses the same hidden file-selection path", () => {
    const onCsvSelected = vi.fn();
    renderWorkspace({ onCsvSelected });

    clickNav("Datasets & Connectors");
    const input = screen.getByTestId("overview-csv-upload-input");
    const inputClick = vi.spyOn(input, "click");
    fireEvent.click(screen.getByRole("button", { name: /Choose Dataset/i }));
    expect(inputClick).toHaveBeenCalledTimes(1);

    const file = new File(["timestamp,flow\n2026-01-01,2"], "sources.csv", { type: "text/csv" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(onCsvSelected).toHaveBeenCalledTimes(1);
    expect(onCsvSelected.mock.calls[0][0]).toEqual([file]);
    expect(screen.getByRole("heading", { name: "Data Source Status" })).toBeTruthy();
  });

  it("Datasets & Connectors owns CSV import, dataset status, and connector catalog only", () => {
    renderWorkspace();

    clickNav("Datasets & Connectors");
    expect(screen.getByRole("heading", { name: "Data Source Status" })).toBeTruthy();
    expect(screen.getByText("Dataset import")).toBeTruthy();
    expect(screen.getByText("Imported rows")).toBeTruthy();
    expect(screen.getByText("Last dataset import")).toBeTruthy();
    expect(screen.getByText("Connector health")).toBeTruthy();
    expect(screen.getByText("Last connector sync")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Choose Dataset/i })).toBeTruthy();
    expect(screen.getAllByText("Import and Analyze a Dataset").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Available Imports" })).toBeTruthy();
    expect(screen.getByText("CSV dataset import")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Configured Connectors" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Planned Connectors" })).toBeTruthy();
    expect(screen.getByText("OPC UA")).toBeTruthy();
    expect(screen.getByText("MQTT")).toBeTruthy();
    expect(screen.getByText("Enterprise historians")).toBeTruthy();
    expect(screen.getByText("BACnet")).toBeTruthy();
    expect(screen.queryByText("Historical Analysis")).toBeNull();
    expect(screen.queryByText("Analyze New Dataset")).toBeNull();
    expect(screen.queryByRole("button", { name: /Import Historical CSV/i })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Facility Status" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Analysis Summary" })).toBeNull();
    expect(screen.queryByText("PLC commands disabled")).toBeNull();
    expect(screen.queryByText("SCADA commands disabled")).toBeNull();
    expect(screen.queryByText("BMS commands disabled")).toBeNull();
    expect(screen.queryByText("Equipment controller commands disabled")).toBeNull();
    expect(screen.queryByText("Read-only Control Boundary")).toBeNull();
    expect(screen.queryByText("Current workspace")).toBeNull();
    expect(screen.getByText("Import and analyze a dataset")).toBeTruthy();
  });

  it("keeps the mobile Datasets & Connectors layout compact and usable", () => {
    window.innerWidth = 390;
    renderWorkspace();

    clickNav("Datasets & Connectors");
    expect(screen.getByRole("button", { name: /Choose Dataset/i })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Data Source Status" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Available Imports" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Configured Connectors" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Planned Connectors" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Facility Status" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Analysis Summary" })).toBeNull();
  });

  it("Systems view shows discovery guidance before telemetry", () => {
    renderWorkspace();

    clickNav("Systems");
    expect(screen.getByRole("heading", { name: "0 Systems Discovered" })).toBeTruthy();
    expect(screen.getAllByText("Systems will be identified automatically after the first successful telemetry analysis.").length).toBeGreaterThan(0);
    expect(screen.queryByText("Central Plant and Airside Systems")).toBeNull();
    expect(screen.queryByText("Aquatic Amenities and Water Features")).toBeNull();
    expect(screen.queryByText("Heat Rejection Systems")).toBeNull();
    expect(screen.queryByText("Expected resort domain example, not a detected system")).toBeNull();
    expect(screen.queryByText("Example, not detected")).toBeNull();
  });

  it("shows no numeric systems nav metric before telemetry analysis", () => {
    renderWorkspace();

    expect(screen.getAllByRole("button", { name: /Systems\s+0 Discovered/ }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Systems\s+7\b/ })).toBeNull();
    const systemsNavText = screen.getAllByRole("button")
      .filter((button) => button.textContent.includes("Systems"))
      .map((button) => button.textContent.trim());
    expect(systemsNavText).not.toContain("Systems7");
  });

  it("counts only real detected systems after telemetry analysis", () => {
    const placeholderSystems = [
      "Central Plant and Airside Systems",
      "Aquatic Amenities and Water Features",
      "Process Water and Pumping",
      "Heat Rejection Systems",
      "Building Control Systems",
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
    expect(screen.queryByText("Central Plant and Airside Systems")).toBeNull();
  });

  it("opens the top Command Center insight inline in the selected investigation", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisWithoutInsightIds() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getByRole("button", { name: "Open finding" })).toBeTruthy();

    expect(screen.getAllByRole("heading", { name: "Engineering Findings" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Selected Investigation" })).toBeNull();
    expect(screen.getByLabelText("Selected investigation detail")).toBeTruthy();
    expect(screen.getByText("What happened")).toBeTruthy();
    expect(screen.getByText("Key evidence")).toBeTruthy();
    expect(screen.getAllByText(/degraded operating performance/).length).toBeGreaterThan(0);
    expect(screen.getByText("Recommended checks")).toBeTruthy();
    expect(screen.getByText("Advanced details")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Similar Verified Investigations" })).toBeTruthy();
    expect(screen.getByText("No verified similar investigations are available yet.")).toBeTruthy();
    expect(screen.queryByText("Confidence Breakdown")).toBeNull();
    expect(screen.queryByRole("button", { name: "Open Insight" })).toBeNull();
    expect(hasActiveNavButton(/Command Center/)).toBe(true);
    expect(hasActiveNavButton(/Engineering Findings\s+1\b/)).toBe(false);
  });

  it("keeps Systems card Open Insight wired to the command-center selected investigation", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisWithoutInsightIds() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Systems");
    fireEvent.click(screen.getByRole("button", { name: "Open Insight" }));

    expect(screen.getAllByRole("heading", { name: "Engineering Findings" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: "Selected Investigation" })).toBeNull();
    expect(screen.getByLabelText("Selected investigation detail")).toBeTruthy();
    expect(screen.getByText("What happened")).toBeTruthy();
    expect(screen.getByText("Key evidence")).toBeTruthy();
    expect(hasActiveNavButton(/Command Center/)).toBe(true);
    expect(hasActiveNavButton(/Systems\s+1\b/)).toBe(false);
  });

  it("six primary views have distinct responsibilities and layouts", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisWithRelationshipEvidence() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getAllByText("Engineering Findings").length).toBeGreaterThan(0);
    expect(screen.queryByText("Selected Investigation")).toBeNull();

    clickNav("Systems");
    expect(screen.getAllByRole("heading", { name: "Operational Systems Identified" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Primary Insight")).toBeTruthy();

    clickNav("Engineering Findings");
    expect(screen.getAllByRole("heading", { name: "Engineering Findings" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Key evidence")).toBeTruthy();

    clickNav("Behavior Baseline");
    expect(screen.getAllByRole("heading", { name: "Behavior Baseline" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Behavior Windows")).toBeTruthy();
    expect(screen.getByText("What changed")).toBeTruthy();

    clickNav("Datasets & Connectors");
    expect(screen.getByRole("heading", { name: "Data Source Status" })).toBeTruthy();

    clickNav("Analysis Details");
    expect(screen.getAllByRole("heading", { name: "Analysis Details" }).length).toBeGreaterThan(0);
    expect(screen.getByText("Analysis Result JSON")).toBeTruthy();
  });

  it("keeps insights system-level and maps relationship claims to relationship evidence", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisWithRelationshipEvidence() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Engineering Findings");
    expect(screen.getAllByText(/Pressure and Flow Behavior Changed/i).length).toBeGreaterThan(0);
    expect(screen.getByText("What happened")).toBeTruthy();
    expect(screen.getByText("Key evidence")).toBeTruthy();
    expect(screen.getByText("Recommended checks")).toBeTruthy();
    expect(screen.getByText("Technical evidence")).toBeTruthy();
    expect(screen.getByText("Advanced details")).toBeTruthy();
    expect(screen.getAllByText(/Confidence/).length).toBeGreaterThan(0);
    expect(screen.queryByText("Investigation Timeline")).toBeNull();
    expect(screen.getAllByText("pressure \u2194 flow").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pressure and flow relationship weakened.").length).toBeGreaterThan(0);
    expect(screen.queryByText("[object Object]")).toBeNull();
    expect(screen.getByText(/1\.111111/)).toBeTruthy();
  });

  it("provides the operator-first investigation workflow", async () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysis() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Engineering Findings");
    expect(screen.getByText("What happened")).toBeTruthy();
    expect(screen.getByText(/Affected subsystem:/)).toBeTruthy();
    expect(screen.getByText("Key evidence")).toBeTruthy();
    expect(screen.getByText("Largest relationship change")).toBeTruthy();
    expect(screen.getByText("Recommended checks")).toBeTruthy();
    expect(screen.getByText("Technical evidence")).toBeTruthy();
    expect(screen.getByText("Advanced details")).toBeTruthy();
    expect(screen.queryByText("Investigation Timeline")).toBeNull();
    expect(screen.queryByText("Prioritized Investigation Workflow")).toBeNull();
    expect(screen.getByRole("button", { name: "Inspect affected equipment" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Compare baseline" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Related systems" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Export report" })).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Ã|â|Â/);
  });

  it("exports the selected investigation as a JSON download", () => {
    const createObjectURL = vi.fn(() => "blob:investigation-report");
    const revokeObjectURL = vi.fn();
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });

    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysis() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });
    clickNav("Engineering Findings");
    fireEvent.click(screen.getByRole("button", { name: "Export report" }));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(anchorClick).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:investigation-report");
    anchorClick.mockRestore();
  });

  it("maps two changed relationships to two evidence lines", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysis() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Engineering Findings");
    expect(screen.getAllByText("Pump Power \u2194 Filter DP").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pump Power \u2194 Flow").length).toBeGreaterThan(0);
    expect(screen.getByText("Largest relationship change")).toBeTruthy();
    expect(screen.getAllByText("Largest relationship change")).toHaveLength(1);
  });

  it("shows an explicit message when relationship evidence is missing", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysis({ second: false }) }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Engineering Findings");
    expect(screen.getByText(/Pump Power \u2194 Flow: no quantitative measurement was included/)).toBeTruthy();
  });

  it("formats evidence to two decimals and explains weakening", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysis() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Engineering Findings");
    const text = screen.getByLabelText("Neraium platform workspace").textContent;
    expect(text).toContain("0.84");
    expect(screen.getByText("Technical evidence")).toBeTruthy();
    expect(screen.getByText("Advanced details")).toBeTruthy();
    expect(text).toMatch(/0\.775497|0\.063807|0\.839304/);
  });

  it("describes coupling sign reversal explicitly", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysis({ reverse: true }) }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Engineering Findings");
    expect(screen.getByText(/Pump Power \u2194 Flow: the relationship reversed direction/)).toBeTruthy();
  });

  it("keeps raw identifiers and JSON in Advanced instead of Command Center", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: analysisWithRelationshipEvidence() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.queryByText("Analysis Result JSON")).toBeNull();
    clickNav("Analysis Details");
    expect(screen.getByText("Analysis Result JSON")).toBeTruthy();
    expect(screen.getByText("Relationship Identifiers")).toBeTruthy();
    expect(screen.getByText("Source signals")).toBeTruthy();
    expect(screen.getByText("Source time ranges")).toBeTruthy();
  });
});


function bugRegressionAnalysis() {
  return {
    systems: [{ id: "flow", name: "Flow & Pressure" }, { id: "disinfection", name: "Disinfection" }],
    relationships: [],
    fingerprint: { status: "changed", meaning: "Operational fingerprint changed." },
    insights: [
      {
        id: "flow-cum",
        title: "Flow & Pressure Degrading",
        severity: "high",
        confidence: "high",
        confidence_score: 1,
        system: "Flow & Pressure",
        what_changed: "The historical relationship between Filter Diff Pressure and Cum Chemical Feed Gal shifted from its established operating pattern.",
        contributing_relationships: [{ columns: ["filter_diff_pressure_psi", "cum_chemical_feed_gal"], display_columns: ["Filter Diff Pressure", "Cum Chemical Feed Gal"] }],
        affected_relationships: ["The Historical Relationship Between Filter Diff Pressure and Cum Chemical Feed Gal Shifted From Its Established Operating Pattern."],
        evidence_items: [{ source_columns: ["filter_diff_pressure_psi", "cum_chemical_feed_gal"] }],
      },
      {
        id: "orp-chlorine",
        title: "Disinfection Control Drift",
        severity: "high",
        confidence: "high",
        confidence_score: 0.88,
        system: "Disinfection",
        what_changed: "ORP decoupled from free chlorine during the current window.",
        contributing_relationships: [{ columns: ["orp_mv", "free_chlorine_ppm"], display_columns: ["ORP MV", "Free Chlorine PPM"] }],
        evidence_items: [{ source_columns: ["orp_mv", "free_chlorine_ppm"] }],
      },
    ],
  };
}

describe("OperationalWorkflowWorkspace bug regressions", () => {
  it("renders raw relationship pairs without nesting headline sentences and caps cumulative confidence", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: bugRegressionAnalysis() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    const flowButton = screen.getAllByRole("button").find((button) => button.textContent.includes("Flow & Pressure Degrading"));
    expect(flowButton).toBeTruthy();
    fireEvent.click(flowButton);

    const workspaceText = screen.getByLabelText("Neraium platform workspace").textContent;
    expect(workspaceText).toContain("The historical relationship between Filter Diff Pressure and Cum Chemical Feed Gal shifted from its established operating pattern.");
    expect(workspaceText).not.toContain("The relationship between The Historical Relationship Between");
    expect(workspaceText).toContain("74%");
  });

  it("lists each insight subsystem in operational insights and discovered systems", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: bugRegressionAnalysis() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    const workspaceText = screen.getByLabelText("Neraium platform workspace").textContent;
    expect(screen.getAllByText("Engineering Findings").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Discovered Systems" })).toBeTruthy();
    expect(workspaceText).toContain("Flow & Pressure");
    expect(workspaceText).toContain("Disinfection");
  });

  it("uses evidence source identifiers instead of Signal N fallback titles", () => {
    const metricAnalysis = {
      systems: [{ id: "quality", name: "Water Quality" }],
      relationships: [],
      fingerprint: { status: "changed", meaning: "Water quality changed." },
      insights: [{
        id: "delta-ph",
        title: "Water Quality Operating Behavior Changed",
        severity: "moderate",
        confidence: "moderate",
        confidence_score: 0.68,
        system: "Water Quality",
        metric_name: "Signal 4",
        evidence_items: [{ source_columns: ["delta_ph"] }],
      }],
    };

    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: metricAnalysis }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    clickNav("Engineering Findings");
    expect(screen.getAllByText(/Delta pH Operating Behavior Changed/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Signal 4/)).toBeNull();
  });
});
