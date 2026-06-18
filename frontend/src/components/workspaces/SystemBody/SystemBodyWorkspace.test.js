/* @vitest-environment jsdom */
import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SystemBodyWorkspace from "./SystemBodyWorkspace";

const h = React.createElement;

vi.mock("./SystemOrbPanel", () => ({
  default: () => h("div", { "data-testid": "system-orb-panel" }),
}));

vi.mock("../../layout/PageContainer", () => ({
  default: ({ children, className }) => h("div", { className }, children),
}));

function readSnapshotValue(label) {
  const snapshot = screen.getByLabelText("Structural stability snapshot");
  const labelNode = within(snapshot).getByText(label);
  return labelNode.nextElementSibling?.textContent;
}

function renderWorkspace(overrides = {}) {
  return render(
    h(SystemBodyWorkspace, Object.assign({
      systemState: "idle",
      uiState: "ready",
      coherence: 1,
      stateLabel: "No data yet",
      subtitle: "Upload data to begin.",
      connectionStatus: "idle",
      connectionTone: "pending",
      primaryMessage: "Upload data to begin.",
      lastUpdate: null,
      focusLabel: "No data yet",
      latestUploadSnapshot: { status: "empty" },
      latestUploadResult: null,
      liveSnapshot: null,
      latestReplayFrame: null,
    }, overrides)),
  );
}

afterEach(() => {
  cleanup();
});

describe("SystemBodyWorkspace empty state", () => {
  it("shows the awaiting telemetry state when no analysis exists", () => {
    renderWorkspace();

    expect(screen.getAllByText("Awaiting Telemetry").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "No Analysis" })).toBeTruthy();
    expect(screen.getAllByText("Upload telemetry to generate an assessment.").length).toBeGreaterThan(0);
    expect(screen.getByText("Not Assessed")).toBeTruthy();
    expect(screen.getByText("Unknown")).toBeTruthy();
    expect(readSnapshotValue("Current operating pattern")).toBe("No telemetry");
    expect(readSnapshotValue("Behavior has persisted")).toBe("No telemetry");
    expect(screen.getByRole("button", { name: "Review Findings" }).disabled).toBe(true);
  });

  it("enables review metrics after a completed analysis exists", () => {
    renderWorkspace({
      latestUploadSnapshot: { status: "complete", sii_completed: true, current_upload: { job_id: "job-42" } },
      latestUploadResult: {
        job_id: "job-42",
        observation_type: "trajectory_drift",
        drift_status: "elevated",
        timestamp_profile: { first_timestamp: "2026-06-15T00:00:00Z" },
        sii_completed: true,
        sii_intelligence: {
          baseline_regime: "State Group B",
          instability_index: 0.72,
        },
      },
    });

    expect(readSnapshotValue("Current operating pattern")).toBe("State Group B");
    expect(readSnapshotValue("Behavior has persisted")).not.toBe("No telemetry");
    expect(screen.getByRole("button", { name: "Review Findings" }).disabled).toBe(false);
  });
});
