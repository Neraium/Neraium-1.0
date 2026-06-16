/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const h = React.createElement;
const runtimeMocks = vi.hoisted(() => ({
  loadFacilitySystems: vi.fn(async () => true),
  loadLatestUploadState: vi.fn(async () => true),
  setAllowPersistedLatest: vi.fn(),
  setIsDemoMode: vi.fn(),
  clearUploadSessionState: vi.fn(),
}));
const runtimeState = vi.hoisted(() => ({
  latestUploadResult: null,
  latestUploadSnapshot: { status: "empty" },
}));

vi.mock("./config", () => ({
  apiFetch: vi.fn(),
  ENABLE_ADMISSION_GATE: false,
}));

vi.mock("./services/api/authApi", () => ({ logoutUser: vi.fn() }));

vi.mock("./hooks/useFacilityRuntime", () => ({
  default: () => ({
    apiStatus: { state: "online" },
    systems: [],
    systemsState: "ready",
    intelligenceStatus: {},
    latestUploadResult: runtimeState.latestUploadResult,
    latestUploadSnapshot: runtimeState.latestUploadSnapshot,
    domainDetection: null,
    allowPersistedLatest: true,
    telemetryTick: 0,
    domainMode: "aquatic",
    ...runtimeMocks,
  }),
}));

vi.mock("./components/SystemTopologyWorkspace", () => ({
  default: ({ liveOps, onWorkspaceNavigate }) => h(
    "div",
    { "data-testid": "gate-workspace" },
    h("span", { "data-testid": "gate-result" }, liveOps.latestUploadResult?.job_id ?? "empty"),
    h("span", { "data-testid": "gate-finding-summary" }, liveOps.canonicalFinding?.summary ?? "none"),
    h("span", { "data-testid": "gate-finding-confidence" }, liveOps.canonicalFinding?.confidence ?? "none"),
    h("span", { "data-testid": "gate-heartbeat-summary" }, liveOps.connectionSummary ?? "none"),
    h("span", { "data-testid": "gate-heartbeat-status" }, liveOps.connectionStatusLine ?? "none"),
    h("button", { type: "button", onClick: () => onWorkspaceNavigate("data-connections") }, "Open uploads"),
    h("button", { type: "button", onClick: () => onWorkspaceNavigate("observation-center") }, "Open findings"),
  ),
}));


vi.mock("./components/ObservationCenterWorkspace", () => ({
  default: ({ canonicalFinding }) => h(
    "div",
    { "data-testid": "observation-workspace" },
    h("span", { "data-testid": "observation-finding-summary" }, canonicalFinding?.summary ?? "none"),
    h("span", { "data-testid": "observation-finding-confidence" }, canonicalFinding?.confidence ?? "none"),
  ),
}));

vi.mock("./components/DataConnectionsWorkspace", () => ({
  default: ({ onUploadComplete }) => h(
    "div",
    { "data-testid": "upload-workspace" },
    h("button", {
      type: "button",
      onClick: () => onUploadComplete({
        status: "complete",
        latest_result: {
          job_id: "persisted-job-42",
          sii_intelligence: { facility_state: "Monitoring" },
        },
      }),
    }, "Finish upload"),
    h("button", {
      type: "button",
      onClick: () => onUploadComplete({
        latest_result: { job_id: "restored-job-7", sii_intelligence: { facility_state: "Monitoring" } },
      }, { navigateToGate: false }),
    }, "Restore upload"),
  ),
}));

beforeEach(() => {
  window.localStorage.clear();
  runtimeState.latestUploadResult = null;
  runtimeState.latestUploadSnapshot = { status: "empty" };
  Object.values(runtimeMocks).forEach((mock) => mock.mockClear());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});


it("treats persisted metadata without a heartbeat timestamp as awaiting telemetry", () => {
  runtimeState.latestUploadSnapshot = {
    status: "complete",
    last_filename: "cached-upload.csv",
  };

  render(h(App));

  expect(screen.getByTestId("gate-heartbeat-summary").textContent).toBe("none");
  expect(screen.getByTestId("gate-heartbeat-status").textContent).toBe("Awaiting telemetry data");
});

describe("App upload completion navigation", () => {
  it("refreshes persisted upload state and returns to the Gate", async () => {
    render(h(App));

    fireEvent.click(screen.getByRole("button", { name: "Open uploads" }));
    expect(screen.getByTestId("upload-workspace")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Finish upload" }));

    await waitFor(() => {
      expect(screen.getByTestId("gate-workspace")).toBeTruthy();
    });

    expect(screen.getByTestId("gate-result").textContent).toBe("persisted-job-42");
    expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true });
    expect(runtimeMocks.loadFacilitySystems).toHaveBeenCalledTimes(1);
  });

  it("does not leave Data Connections when an existing upload is restored", async () => {
    render(h(App));

    fireEvent.click(screen.getByRole("button", { name: "Open uploads" }));
    fireEvent.click(screen.getByRole("button", { name: "Restore upload" }));

    await waitFor(() => {
      expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true });
    });

    expect(screen.getByTestId("upload-workspace")).toBeTruthy();
    expect(screen.queryByTestId("gate-workspace")).toBeNull();
  });

  it("passes the same canonical finding to Gate and Findings", async () => {
    runtimeState.latestUploadResult = {
      job_id: "finding-job-9",
      observation_type: "trajectory_drift",
      relationship_summary: "relationship divergence detected across chilled water supply.",
      drift_status: "elevated",
      drift_metrics: { baseline_distance: 0.7, confidence: 0.83 },
      sii_reliable_enough_to_show: true,
      operator_report: { evidence_summary: ["replay/relationship evidence supports the shift."] },
      sii_intelligence: { facility_state: "drift", confidence: 0.83 },
    };
    runtimeState.latestUploadSnapshot = {
      status: "complete",
      sii_completed: true,
      current_upload: { job_id: "finding-job-9" },
      system_interpretation: {
        lineage: { job_id: "finding-job-9", aligned: true },
        run_alignment_verified: true,
      },
    };

    render(h(App));

    const gateSummary = screen.getByTestId("gate-finding-summary").textContent;
    expect(gateSummary).toMatch(/historical operating pattern/i);
    expect(screen.getByTestId("gate-finding-confidence").textContent).toBe("High");

    fireEvent.click(screen.getByRole("button", { name: "Open findings" }));

    await waitFor(() => expect(screen.getByTestId("observation-workspace")).toBeTruthy());
    expect(screen.getByTestId("observation-finding-summary").textContent).toBe(gateSummary);
    expect(screen.getByTestId("observation-finding-confidence").textContent).toBe("High");
  });

  it("keeps findings pending when telemetry exists but operator review is not yet evidence-ready", async () => {
    runtimeState.latestUploadResult = {
      job_id: "pending-job-3",
      observation_type: "trajectory_drift",
      drift_status: "elevated",
      drift_metrics: { baseline_distance: 0.71, confidence: 0.8 },
      sii_reliable_enough_to_show: false,
      sii_intelligence: { facility_state: "drift", confidence: 0.8 },
    };
    runtimeState.latestUploadSnapshot = {
      status: "complete",
      current_upload: { job_id: "pending-job-3" },
      system_interpretation: {
        lineage: { job_id: "pending-job-3", aligned: true },
        run_alignment_verified: true,
      },
    };

    render(h(App));

    expect(screen.getByTestId("gate-finding-summary").textContent).toBe("Analysis pending verification.");

    fireEvent.click(screen.getByRole("button", { name: "Open findings" }));
    await waitFor(() => expect(screen.getByTestId("observation-workspace")).toBeTruthy());
    expect(screen.getByTestId("observation-finding-summary").textContent).toBe("Analysis pending verification.");
  });
});
