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
    expect(screen.queryByText("No Operating Fingerprint Yet")).toBeNull();
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
    expect(screen.queryByText("No Operating Fingerprint Yet")).toBeNull();
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
    expect(screen.getByText("Systems identified")).toBeTruthy();
    expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    expect(screen.getByText("Insights found")).toBeTruthy();
    expect(screen.getByText("Fingerprint status")).toBeTruthy();
    expect(screen.getByText("Stable")).toBeTruthy();
    expect(screen.getByText("Top recommendation")).toBeTruthy();
    expect(screen.getAllByText("Continue monitoring").length).toBeGreaterThan(0);
    expect(screen.queryByText("Relationships mapped")).toBeNull();
    expect(screen.queryByText("Baseline confidence")).toBeNull();
    expect(screen.queryByText("Top risk")).toBeNull();
    expect(screen.queryByText("Recommended action")).toBeNull();
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
    expect(screen.getByText("Systems identified")).toBeTruthy();
    expect(screen.queryByText("systems monitored")).toBeNull();
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
});
