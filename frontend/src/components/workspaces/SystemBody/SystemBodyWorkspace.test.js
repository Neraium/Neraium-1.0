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
  it("keeps review metrics empty when no active dataset exists", () => {
    renderWorkspace();

    expect(screen.getAllByText("No current observations.").length).toBeGreaterThan(0);
    expect(screen.queryByText("State Group A")).toBeNull();
    expect(readSnapshotValue("Current operating pattern")).toBe("—");
    expect(readSnapshotValue("Behavior has persisted")).toBe("—");
  });

  it("derives review metrics from loaded observation data", () => {
    renderWorkspace({
      latestUploadSnapshot: { status: "complete", current_upload: { job_id: "job-42" } },
      latestUploadResult: {
        job_id: "job-42",
        observation_type: "trajectory_drift",
        drift_status: "elevated",
        timestamp_profile: { first_timestamp: "2026-06-15T00:00:00Z" },
        sii_intelligence: {
          baseline_regime: "State Group B",
          instability_index: 0.72,
        },
      },
    });

    expect(readSnapshotValue("Current operating pattern")).toBe("State Group B");
    expect(readSnapshotValue("Behavior has persisted")).not.toBe("—");
  });
});
