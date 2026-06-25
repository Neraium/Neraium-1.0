/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

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

function completeResult(overrides = {}) {
  return {
    job_id: "ready-job",
    sii_reliable_enough_to_show: true,
    sii_completed: true,
    processed_at: "2026-06-23T12:00:00Z",
    sii_intelligence: { facility_state: "stable", baseline: { state: "stable" } },
    baseline_analysis: { status: "available" },
    data_quality: { warnings: [] },
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

describe("OperationalWorkflowWorkspace analysis gating", () => {
  it("shows pending systems and telemetry for an empty site", () => {
    renderWorkspace();

    expect(screen.getAllByText("Awaiting Analysis").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Systems Pending").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Run analysis to identify systems and relationships.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("--").length).toBeGreaterThan(0);
    expect(screen.queryByText(/systems monitored/i)).toBeNull();
    expect(screen.queryByText("Telemetry Available")).toBeNull();
    expect(screen.queryByText("Telemetry Verified")).toBeNull();
  });

  it("does not present configured systems as identified while awaiting analysis", () => {
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
        relationshipRows: [],
      },
      effectiveLatestUploadResult: {
        job_id: "pending-job",
        operating_state: "stable",
        drift_status: "stable",
        sii_intelligence: { facility_state: "stable" },
        baseline_analysis: {},
        data_quality: { warnings: [] },
      },
      effectiveLatestUploadSnapshot: {
        status: "complete",
        current_upload: { job_id: "pending-job" },
      },
      currentSession: { hasReliableOperatorEvidence: false },
    });

    expect(screen.getAllByText("Awaiting Analysis").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Telemetry Available").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Systems Pending").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Run analysis to identify systems and relationships.").length).toBeGreaterThan(0);
    expect(screen.queryByText("6 systems monitored")).toBeNull();
    expect(screen.queryByText("6 systems identified")).toBeNull();
    expect(screen.queryByText("Normal")).toBeNull();
    expect(screen.queryByText("Stable")).toBeNull();
    expect(screen.queryByText("Telemetry Verified")).toBeNull();
    expect(screen.queryByText("Healthy")).toBeNull();
    expect(screen.queryByText("Good")).toBeNull();
  });

  it("shows identified systems after completed SII analysis without calling them monitored", () => {
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
        relationshipRows: [],
        siiVerification: { verified: true },
      },
      effectiveLatestUploadResult: completeResult(),
      effectiveLatestUploadSnapshot: completeSnapshot(),
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getAllByText("Normal").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Stable").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Telemetry Verified").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Systems Identified").length).toBeGreaterThan(0);
    expect(screen.getAllByText("6 systems identified").length).toBeGreaterThan(0);
    expect(screen.queryByText(/systems monitored/i)).toBeNull();
    expect(screen.queryByText("No Baseline Available")).toBeNull();
  });

  it("uses monitored copy only when completed analysis also has connected live telemetry", () => {
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

    expect(screen.getAllByText("1 system monitored").length).toBeGreaterThan(0);
    expect(screen.getByText("systems monitored")).toBeTruthy();
  });

  it("keeps the Systems section pending before analysis", () => {
    renderWorkspace({
      liveOps: {
        systems: [{ id: "system-1", name: "Chilled Water Loop" }],
      },
    });

    fireEvent.click(screen.getAllByRole("button", { name: /Systems--/i })[0]);

    expect(screen.getAllByText("Systems Pending").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Run analysis to identify systems and relationships.").length).toBeGreaterThan(0);
    expect(screen.queryByText("Chilled Water Loop")).toBeNull();
  });
});
