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
    sii_reliable_enough_to_show: true,
    sii_completed: true,
    sii_intelligence: { facility_state: "stable", baseline: { state: "stable" } },
    baseline_analysis: { status: "available" },
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

function relationshipAnalysis({ secondEvidence = true, signReversal = false } = {}) {
  const evidence = [{
    description: "Pump power and filter pressure relationship changed.",
    metric_delta: [{
      tag_name: "pump_power_filter_dp",
      baseline_strength: 0.775497,
      current_strength: 0.063807,
      correlation_delta: 0.839304,
    }],
  }];

  if (secondEvidence) {
    evidence.push({
      description: "Pump power and flow relationship changed.",
      metric_delta: [{
        tag_name: "pump_power_flow",
        baseline_strength: signReversal ? 0.61 : 0.72,
        current_strength: signReversal ? -0.44 : 0.31,
        correlation_delta: signReversal ? -1.05 : 0.41,
      }],
    });
  }

  return {
    insights: [{
      id: "pump-relationships",
      title: "Pump relationships changed",
      severity: "high",
      confidence: "high",
      system: "Pump system",
      contributing_relationships: [
        { display_columns: ["Pump Power", "Filter DP"], columns: ["pump_power", "filter_dp"] },
        { display_columns: ["Pump Power", "Flow"], columns: ["pump_power", "flow"] },
      ],
      evidence_items: evidence,
    }],
    systems: [{ id: "pump", name: "Pump system" }],
    relationships: [],
    fingerprint: { status: "changed", meaning: "Pump behavior changed." },
  };
}

afterEach(() => cleanup());

describe("OperationalWorkflowWorkspace current UI", () => {
  it("opens the native CSV picker without navigating away", () => {
    const onWorkspaceNavigate = vi.fn();
    const onCsvSelected = vi.fn();
    renderWorkspace({ onWorkspaceNavigate, onCsvSelected });

    const input = screen.getByTestId("overview-csv-upload-input");
    const inputClick = vi.spyOn(input, "click");
    fireEvent.click(screen.getByRole("button", { name: "Select CSV" }));
    expect(inputClick).toHaveBeenCalledTimes(1);
    expect(onWorkspaceNavigate).not.toHaveBeenCalled();

    const file = new File(["timestamp,flow\n2026-01-01,1"], "ops.csv", { type: "text/csv" });
    fireEvent.change(input, { target: { files: [file] } });
    expect(onCsvSelected).toHaveBeenCalledWith([file]);
  });

  it("shows upload ready and analysis running states", () => {
    const { unmount } = renderWorkspace({
      effectiveLatestUploadResult: telemetryResult(),
      effectiveLatestUploadSnapshot: { status: "uploaded", current_upload: { job_id: "telemetry-job" } },
    });
    expect(screen.getAllByText("CSV loaded / Ready to analyze").length).toBeGreaterThan(0);
    expect(screen.getByText("Telemetry is ready for analysis.")).toBeTruthy();
    unmount();

    renderWorkspace({
      effectiveLatestUploadResult: telemetryResult({ processing_state: "processing" }),
      effectiveLatestUploadSnapshot: { status: "processing", current_upload: { job_id: "telemetry-job" } },
      gateProcessing: { active: true, status: "processing" },
    });
    const button = screen.getByRole("button", { name: "Analyzing" });
    expect(button.disabled).toBe(true);
    expect(screen.getByText("Building the operational view.")).toBeTruthy();
  });

  it("renders the completed analysis workspace", () => {
    renderWorkspace({
      liveOps: { systems: [{ id: "one", name: "Loop One" }, { id: "two", name: "Loop Two" }] },
      effectiveLatestUploadResult: completeResult(),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getByText("Analysis Complete")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /Overview Summary/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Systems 2/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Insights 0/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Signals 2/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: /Advanced Details Raw/i }).length).toBeGreaterThan(0);
  });

  it("maps two relationships to two evidence lines", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: relationshipAnalysis() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });
    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Insights")));

    expect(screen.getByText(/Pump Power ↔ Filter DP: Unitless coupling score changed from 0.78 to 0.06/)).toBeTruthy();
    expect(screen.getByText(/Pump Power ↔ Flow: Unitless coupling score changed from 0.72 to 0.31/)).toBeTruthy();
    expect(screen.getByText("Changed Relationships")).toBeTruthy();
  });

  it("shows explicit missing quantitative evidence for an unmatched relationship", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: relationshipAnalysis({ secondEvidence: false }) }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });
    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Insights")));
    expect(screen.getByText(/Pump Power ↔ Flow: change detected, but no quantitative measurement was included in this result/)).toBeTruthy();
  });

  it("formats relationship evidence to two decimals and explains weakening", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: relationshipAnalysis() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });
    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Insights")));
    const text = screen.getByLabelText("Neraium operational workspace").textContent;
    expect(text).toContain("0.78");
    expect(text).toContain("0.06");
    expect(text).toContain("0.84");
    expect(text).toContain("weakened sharply toward little linear coupling");
    expect(text).not.toMatch(/0\.775497|0\.063807|0\.839304/);
  });

  it("describes a coupling sign reversal", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: relationshipAnalysis({ signReversal: true }) }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });
    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Insights")));
    expect(screen.getByText(/the relationship reversed direction/)).toBeTruthy();
  });

  it("does not leak object stringification into operator pages", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult({ analysis_result: relationshipAnalysis() }),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });
    fireEvent.click(screen.getAllByRole("button").find((button) => button.textContent.includes("Insights")));
    expect(screen.getByLabelText("Neraium operational workspace").textContent).not.toContain("[object Object]");
  });
});
