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
    current_upload: { job_id: "ready-job" },
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("OperationalWorkflowWorkspace product story states", () => {
  it("shows a truthful empty state before telemetry is loaded", () => {
    renderWorkspace();

    expect(screen.getAllByText("No Telemetry Loaded").length).toBeGreaterThan(0);
    expect(screen.getByText("Site: Current Site | Data source: No telemetry uploaded")).toBeTruthy();
    expect(screen.getByText("No telemetry uploaded")).toBeTruthy();
    expect(screen.getByText("Waiting for telemetry")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Upload or Connect Telemetry" })).toBeTruthy();
    expect(screen.getAllByText("Systems Pending").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Run analysis to identify systems and relationships.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No Operating Fingerprint Yet").length).toBeGreaterThan(0);
    expect(screen.queryByText(/systems monitored/i)).toBeNull();
    expect(screen.queryByText(/systems identified/i)).toBeNull();
    expect(screen.queryByText("Baseline Established")).toBeNull();
  });

  it("shows telemetry loaded but not analyzed as ready to analyze", () => {
    renderWorkspace({
      effectiveLatestUploadResult: telemetryResult({ sii_intelligence: { facility_state: "stable" } }),
      effectiveLatestUploadSnapshot: { status: "uploaded", current_upload: { job_id: "telemetry-job" } },
      liveOps: {
        systems: [{ id: "system-1", name: "Chilled Water Loop" }],
      },
    });

    expect(screen.getAllByText("Ready to Analyze").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Telemetry is available. Run analysis to identify systems, relationships, anomalies, and baseline behavior.").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Analyze Telemetry" })).toBeTruthy();
    expect(screen.getAllByText("Systems Pending").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No Operating Fingerprint Yet").length).toBeGreaterThan(0);
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
    expect(screen.getByText("Historical telemetry analyzed")).toBeTruthy();
    expect(screen.getByText("Systems identified")).toBeTruthy();
    expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    expect(screen.getByText("Relationships mapped")).toBeTruthy();
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    expect(screen.getByText("Baseline confidence")).toBeTruthy();
    expect(screen.getByText("82%")).toBeTruthy();
    expect(screen.getByText("Top risk")).toBeTruthy();
    expect(screen.getByText("No major risk detected")).toBeTruthy();
    expect(screen.getByText("Recommended action")).toBeTruthy();
    expect(screen.getAllByText("Continue monitoring").length).toBeGreaterThan(0);
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
    expect(screen.getAllByText("1 system monitored").length).toBeGreaterThan(0);
    expect(screen.getByText("systems monitored")).toBeTruthy();
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
