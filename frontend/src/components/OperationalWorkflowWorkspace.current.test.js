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

function completeResult(analysisResult) {
  return {
    job_id: "ready-job",
    processed_at: "2026-06-23T12:00:00Z",
    columns: ["flow", "temperature"],
    result_source: "uploaded telemetry.csv",
    row_count: 120,
    sii_reliable_enough_to_show: true,
    sii_completed: true,
    sii_intelligence: { facility_state: "stable", baseline: { state: "stable" } },
    baseline_analysis: { status: "available" },
    analysis_result: analysisResult,
  };
}

function completeSnapshot() {
  return {
    status: "complete",
    sii_completed: true,
    processed_at: "2026-06-23T12:00:00Z",
    current_upload: { job_id: "ready-job", filename: "uploaded telemetry.csv", row_count: 120 },
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
        { display_columns: ["Pump Power", "Filter DP"] },
        { display_columns: ["Pump Power", "Flow"] },
      ],
      evidence_items: evidence,
    }],
    systems: [{ id: "pump", name: "Pump system" }],
    relationships: [],
    fingerprint: { status: "changed", meaning: "Pump behavior changed." },
  };
}

afterEach(() => cleanup());

describe("OperationalWorkflowWorkspace critical flows", () => {
  it("opens the native CSV picker and forwards the selected file", () => {
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

  it("maps two changed relationships to two evidence lines", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult(relationshipAnalysis()),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    const insightsButton = screen.getAllByRole("button").find((button) => button.textContent.includes("Insights"));
    fireEvent.click(insightsButton);

    expect(screen.getByText(/Pump Power ↔ Filter DP: Unitless coupling score changed from 0.78 to 0.06/)).toBeTruthy();
    expect(screen.getByText(/Pump Power ↔ Flow: Unitless coupling score changed from 0.72 to 0.31/)).toBeTruthy();
  });

  it("shows an explicit message when a relationship has no quantitative evidence", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult(relationshipAnalysis({ secondEvidence: false })),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    const insightsButton = screen.getAllByRole("button").find((button) => button.textContent.includes("Insights"));
    fireEvent.click(insightsButton);

    expect(screen.getByText(/Pump Power ↔ Flow: change detected, but no quantitative measurement was included in this result/)).toBeTruthy();
  });

  it("formats evidence to two decimals and explains the weakening direction", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult(relationshipAnalysis()),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    const insightsButton = screen.getAllByRole("button").find((button) => button.textContent.includes("Insights"));
    fireEvent.click(insightsButton);
    const text = screen.getByLabelText("Neraium operational workspace").textContent;

    expect(text).toContain("0.78");
    expect(text).toContain("0.06");
    expect(text).toContain("0.84");
    expect(text).toContain("weakened sharply toward little linear coupling");
    expect(text).not.toMatch(/0\.775497|0\.063807|0\.839304/);
  });

  it("describes a coupling sign reversal explicitly", () => {
    renderWorkspace({
      effectiveLatestUploadResult: completeResult(relationshipAnalysis({ signReversal: true })),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    const insightsButton = screen.getAllByRole("button").find((button) => button.textContent.includes("Insights"));
    fireEvent.click(insightsButton);

    expect(screen.getByText(/the relationship reversed direction/)).toBeTruthy();
  });
});
