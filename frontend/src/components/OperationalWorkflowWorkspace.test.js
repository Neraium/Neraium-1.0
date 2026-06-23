/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
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

afterEach(() => {
  cleanup();
});

describe("OperationalWorkflowWorkspace analysis gating", () => {
  it("shows honest pre-analysis states instead of health defaults", () => {
    renderWorkspace({
      liveOps: {
        systems: [{ id: "system-1", name: "Chilled Water Loop" }],
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
    expect(screen.getAllByText("No Baseline Available").length).toBeGreaterThan(0);
    expect(screen.queryByText("Normal")).toBeNull();
    expect(screen.queryByText("Stable")).toBeNull();
    expect(screen.queryByText("Telemetry Verified")).toBeNull();
    expect(screen.queryByText("Healthy")).toBeNull();
    expect(screen.queryByText("Good")).toBeNull();
  });

  it("allows operational labels after verified SII intelligence exists", () => {
    renderWorkspace({
      liveOps: {
        systems: [{ id: "system-1", name: "Chilled Water Loop" }],
        relationshipRows: [],
        siiVerification: { verified: true },
      },
      effectiveLatestUploadResult: {
        job_id: "ready-job",
        sii_reliable_enough_to_show: true,
        sii_completed: true,
        processed_at: "2026-06-23T12:00:00Z",
        sii_intelligence: { facility_state: "stable", baseline: { state: "stable" } },
        baseline_analysis: { status: "available" },
        data_quality: { warnings: [] },
      },
      effectiveLatestUploadSnapshot: {
        status: "complete",
        sii_completed: true,
        processed_at: "2026-06-23T12:00:00Z",
        current_upload: { job_id: "ready-job" },
      },
      currentSession: { hasReliableOperatorEvidence: true },
    });

    expect(screen.getAllByText("Normal").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Stable").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Telemetry Verified").length).toBeGreaterThan(0);
    expect(screen.queryByText("No Baseline Available")).toBeNull();
  });
});
