/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { apiFetch } from "./config";

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
  sessionStore: null,
  throwGateError: false,
}));

function expectOnlyExpectedRenderErrors(spy) {
  const messages = spy.mock.calls.map(([firstArg]) => {
    if (typeof firstArg === "string") return firstArg;
    if (firstArg instanceof Error) return firstArg.message;
    return String(firstArg ?? "");
  });
  expect(messages.length).toBeGreaterThan(0);
  expect(messages.every((message) => (
    message.includes("gate render failed")
    || message.includes("[neraium] render fallback activated")
    || message.includes("The above error occurred")
  ))).toBe(true);
}

function suppressExpectedGateRenderWindowError() {
  const handleWindowError = (event) => {
    const message = String(event?.error?.message ?? event?.message ?? "");
    if (message.includes("gate render failed")) {
      event.preventDefault();
    }
  };
  window.addEventListener("error", handleWindowError);
  return () => window.removeEventListener("error", handleWindowError);
}

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
    sessionStore: runtimeState.sessionStore,
    domainDetection: null,
    allowPersistedLatest: true,
    telemetryTick: 0,
    domainMode: "aquatic",
    ...runtimeMocks,
  }),
}));

vi.mock("./components/SystemTopologyWorkspace", () => ({
  default: ({ liveOps, onWorkspaceNavigate, gateProcessing }) => {
    if (runtimeState.throwGateError) {
      throw new Error("gate render failed");
    }
    return h(
      "div",
      { "data-testid": "gate-workspace" },
      h("span", { "data-testid": "gate-result" }, liveOps.latestUploadResult?.job_id ?? "empty"),
      h("span", { "data-testid": "gate-session-job" }, liveOps.currentSession?.sessionJobId ?? "empty"),
      h("span", { "data-testid": "gate-finding-summary" }, liveOps.canonicalFinding?.summary ?? "none"),
      h("span", { "data-testid": "gate-finding-confidence" }, liveOps.canonicalFinding?.confidence ?? "none"),
      h("span", { "data-testid": "gate-heartbeat-summary" }, liveOps.connectionSummary ?? "none"),
      h("span", { "data-testid": "gate-heartbeat-status" }, liveOps.connectionStatusLine ?? "none"),
      h("span", { "data-testid": "gate-processing-active" }, String(Boolean(gateProcessing?.active))),
      h("span", { "data-testid": "gate-processing-label" }, gateProcessing?.label ?? "none"),
      h("button", { type: "button", onClick: () => onWorkspaceNavigate("data-connections") }, "Open uploads"),
      h("button", { type: "button", onClick: () => onWorkspaceNavigate("observation-center") }, "Open findings"),
    );
  },
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
  default: ({ onUploadComplete, onResetWorkspace, onLoadLatestWorkspace, workspaceStatusMessage }) => h(
    "div",
    { "data-testid": "upload-workspace" },
    h("span", { "data-testid": "workspace-status-message" }, workspaceStatusMessage || "none"),
    h("button", {
      type: "button",
      onClick: () => onLoadLatestWorkspace(),
    }, "Load latest workspace"),
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
        job_id: "pending-job-11",
        status: "running_sii",
        message: "Telemetry active. Analysis pending.",
      }),
    }, "Finish pending upload"),
    h("button", {
      type: "button",
      onClick: () => onUploadComplete({
        latest_result: { job_id: "restored-job-7", sii_intelligence: { facility_state: "Monitoring" } },
      }, { navigateToGate: false }),
    }, "Restore upload"),
    h("button", {
      type: "button",
      onClick: () => onResetWorkspace(),
    }, "Reset workspace"),
  ),
}));

beforeEach(() => {
  window.localStorage.clear();
  runtimeState.latestUploadResult = null;
  runtimeState.latestUploadSnapshot = { status: "empty" };
  runtimeState.sessionStore = null;
  runtimeState.throwGateError = false;
  Object.values(runtimeMocks).forEach((mock) => mock.mockClear());
  apiFetch.mockReset();
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
  expect(screen.getByTestId("gate-heartbeat-status").textContent).toBe("Persisted telemetry available");
});

it("keeps a fresh visit empty when stale upload payloads exist but no session is active", () => {
  runtimeState.latestUploadResult = {
    job_id: "stale-job-9",
    filename: "chilled_water_system_data.csv",
    sii_intelligence: { facility_state: "Monitoring" },
  };
  runtimeState.latestUploadSnapshot = {
    status: "complete",
    last_filename: "chilled_water_system_data.csv",
    last_processed_at: "2026-06-20T00:00:00Z",
  };
  runtimeState.sessionStore = {
    loaded: true,
    uiState: "empty",
    backendState: "empty",
    latestUploadSnapshot: { status: "empty" },
    latestUploadResult: null,
    hasActiveSession: false,
    isProcessing: false,
    jobId: null,
  };

  render(h(App));

  expect(screen.getByTestId("gate-result").textContent).toBe("empty");
  expect(screen.getByTestId("gate-heartbeat-status").textContent).toBe("Awaiting telemetry data");
  expect(screen.getByTestId("gate-finding-summary").textContent).not.toMatch(/analysis pending verification/i);
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
    expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true, forceRefresh: true });
    expect(runtimeMocks.loadFacilitySystems).toHaveBeenCalledTimes(1);
  });


  it("shows an explicit empty state when latest workspace has no active session", async () => {
    runtimeMocks.loadLatestUploadState.mockResolvedValueOnce(false);
    runtimeMocks.loadFacilitySystems.mockResolvedValueOnce(true);

    render(h(App));

    fireEvent.click(screen.getByRole("button", { name: "Open uploads" }));
    fireEvent.click(screen.getByRole("button", { name: "Load latest workspace" }));

    await waitFor(() => {
      expect(screen.getByTestId("workspace-status-message").textContent).toBe("No latest workspace is available.");
    });
    expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true, forceRefresh: true });
    expect(screen.getByTestId("upload-workspace")).toBeTruthy();
  });

  it("shows an explicit error when latest workspace restore fails", async () => {
    runtimeMocks.loadLatestUploadState.mockRejectedValueOnce(new Error("Latest workspace unavailable."));

    render(h(App));

    fireEvent.click(screen.getByRole("button", { name: "Open uploads" }));
    fireEvent.click(screen.getByRole("button", { name: "Load latest workspace" }));

    await waitFor(() => {
      expect(screen.getByTestId("workspace-status-message").textContent).toBe("Latest workspace unavailable.");
    });
    expect(screen.getByTestId("upload-workspace")).toBeTruthy();
  });

  it("does not leave Data Connections when an existing upload is restored", async () => {
    render(h(App));

    fireEvent.click(screen.getByRole("button", { name: "Open uploads" }));
    fireEvent.click(screen.getByRole("button", { name: "Restore upload" }));

    await waitFor(() => {
      expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true, forceRefresh: true });
    });

    expect(screen.getByTestId("upload-workspace")).toBeTruthy();
    expect(screen.queryByTestId("gate-workspace")).toBeNull();
  });

  it("forces a canonical current-upload refetch after upload completion", async () => {
    render(h(App));

    fireEvent.click(screen.getByRole("button", { name: "Open uploads" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish upload" }));

    await waitFor(() => {
      expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true, forceRefresh: true });
    });
    expect(runtimeMocks.loadFacilitySystems).toHaveBeenCalledWith({ forceRefresh: true });
  });

  it("shows analysis pending instead of a blank screen when canonical state is still settling", async () => {
    runtimeMocks.loadLatestUploadState.mockResolvedValueOnce(false);
    runtimeMocks.loadFacilitySystems.mockResolvedValueOnce(true);

    render(h(App));

    fireEvent.click(screen.getByRole("button", { name: "Open uploads" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish pending upload" }));

    await waitFor(() => {
      expect(screen.getByTestId("gate-workspace")).toBeTruthy();
    });

    expect(screen.getByTestId("gate-session-job").textContent).toBe("pending-job-11");
    expect(screen.getByTestId("gate-processing-active").textContent).toBe("true");
    expect(screen.getByTestId("gate-processing-label").textContent).toMatch(/analysis pending/i);
  });

  it("shows a safe fallback when the post-upload route render throws", async () => {
    runtimeState.throwGateError = true;
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const restoreWindowError = suppressExpectedGateRenderWindowError();

    try {
      render(h(App));

      await waitFor(() => {
        expect(screen.getByTestId("app-render-fallback")).toBeTruthy();
      });
      expect(screen.getByText(/workspace recovery/i)).toBeTruthy();
      expectOnlyExpectedRenderErrors(consoleErrorSpy);
    } finally {
      restoreWindowError();
      consoleErrorSpy.mockRestore();
    }
  });

  it("retries the workspace from the render fallback", async () => {
    runtimeState.throwGateError = true;
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const restoreWindowError = suppressExpectedGateRenderWindowError();

    try {
      render(h(App));

      await waitFor(() => {
        expect(screen.getByTestId("app-render-fallback")).toBeTruthy();
      });

      runtimeState.throwGateError = false;
      fireEvent.click(screen.getByRole("button", { name: "Retry Workspace" }));

      await waitFor(() => {
        expect(screen.getByTestId("gate-workspace")).toBeTruthy();
      });
      expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: false, forceRefresh: true });
      expect(runtimeMocks.loadFacilitySystems).toHaveBeenCalledWith({ forceRefresh: true });
      expectOnlyExpectedRenderErrors(consoleErrorSpy);
    } finally {
      restoreWindowError();
      consoleErrorSpy.mockRestore();
    }
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
    runtimeState.sessionStore = {
      loaded: true,
      uiState: "verified",
      backendState: "verified",
      latestUploadSnapshot: runtimeState.latestUploadSnapshot,
      latestUploadResult: runtimeState.latestUploadResult,
      hasActiveSession: true,
      isProcessing: false,
      jobId: "finding-job-9",
    };
    window.localStorage.setItem("neraium.allow_persisted_latest", "1");
    window.localStorage.setItem("neraium.session_intent", "current");

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
    runtimeState.sessionStore = {
      loaded: true,
      uiState: "verified",
      backendState: "verified",
      latestUploadSnapshot: runtimeState.latestUploadSnapshot,
      latestUploadResult: runtimeState.latestUploadResult,
      hasActiveSession: true,
      isProcessing: false,
      jobId: "pending-job-3",
    };
    window.localStorage.setItem("neraium.allow_persisted_latest", "1");
    window.localStorage.setItem("neraium.session_intent", "current");

    render(h(App));

    expect(screen.getByTestId("gate-finding-summary").textContent).toBe("Analysis pending verification.");

    fireEvent.click(screen.getByRole("button", { name: "Open findings" }));
    await waitFor(() => expect(screen.getByTestId("observation-workspace")).toBeTruthy());
    expect(screen.getByTestId("observation-finding-summary").textContent).toBe("Analysis pending verification.");
  });
});
