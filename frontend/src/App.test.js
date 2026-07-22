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

async function launchWorkspace() {
  const launchButtons = screen.queryAllByRole("button", { name: "Open Command Center" });
  if (launchButtons.length) {
    fireEvent.click(launchButtons[0]);
  }
  await waitFor(() => {
    expect(screen.queryByTestId("gate-workspace") ?? screen.queryByTestId("app-render-fallback")).toBeTruthy();
  });
}

vi.mock("./config", () => ({
  apiFetch: vi.fn(),
  ENABLE_ADMISSION_GATE: false,
}));

vi.mock("./services/api/authApi", () => ({
  fetchCurrentUser: vi.fn().mockResolvedValue({ authenticated: true, user: { email: "operator@facility.com", name: "Operator", role: "operator" } }),
  logoutUser: vi.fn().mockResolvedValue({ authenticated: false }),
}));

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

vi.mock("./components/OperationalWorkflowWorkspace", () => ({
  default: ({ liveOps, onWorkspaceNavigate, onResumePreviousSession, onSignOut, gateProcessing, onCsvSelected }) => {
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
      h("span", { "data-testid": "gate-previous-upload" }, liveOps.persistedLatestUpload?.jobId ?? "none"),
      liveOps.persistedLatestUpload ? h("button", { type: "button", onClick: onResumePreviousSession }, "Resume Previous Analysis") : null,
      h("input", {
        "data-testid": "mock-overview-csv-upload-input",
        type: "file",
        onChange: (event) => onCsvSelected?.(Array.from(event.target.files ?? [])),
      }),
      h("button", { type: "button", onClick: () => onWorkspaceNavigate("data-connections") }, "Open telemetry intake"),
      h("button", { type: "button", onClick: () => onWorkspaceNavigate("observation-center") }, "Open insights"),
      h("button", { type: "button", onClick: onSignOut }, "Sign out test user"),
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
  default: ({ onUploadComplete, onResetDemo, initialSelectedFiles = [], autoStartInitialFiles = false }) => h(
    "div",
    { "data-testid": "telemetry-workspace" },
    h("span", { "data-testid": "telemetry-initial-file-count" }, String(initialSelectedFiles.length)),
    h("span", { "data-testid": "telemetry-auto-start" }, String(Boolean(autoStartInitialFiles))),
    h("button", {
      type: "button",
      onClick: () => onUploadComplete({
        status: "complete",
        latest_result: {
          job_id: "persisted-job-42",
          sii_intelligence: { facility_state: "Monitoring" },
        },
      }),
    }, "Finish analysis"),
    h("button", {
      type: "button",
      onClick: () => onUploadComplete({
        job_id: "pending-job-11",
        status: "running_sii",
        message: "Telemetry active. Analysis pending.",
      }),
    }, "Finish pending analysis"),
    h("button", {
      type: "button",
      onClick: () => onUploadComplete({
        latest_result: { job_id: "restored-job-7", sii_intelligence: { facility_state: "Monitoring" } },
      }, { navigateToGate: false }),
    }, "Restore analysis"),
    h("button", { type: "button", onClick: onResetDemo }, "Clear Telemetry Workspace"),
  ),
}));

beforeEach(() => {
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
  window.sessionStorage.clear();
  runtimeState.latestUploadResult = null;
  runtimeState.latestUploadSnapshot = { status: "empty" };
  runtimeState.throwGateError = false;
  Object.values(runtimeMocks).forEach((mock) => mock.mockClear());
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});


it("does not restore stale local analysis history as the active dataset", async () => {
  window.localStorage.setItem("neraium.dataset_cache_scope", "operator@facility.com::default");
  window.localStorage.setItem("neraium.completed_analysis_history", JSON.stringify([{
    id: "stale-history-record",
    jobId: "stale-job-4032",
    datasetName: "resort chw hvac synthetic fouling.csv",
    timestamp: "2026-07-20T06:32:53.260378+00:00",
    savedAt: "2026-07-20T06:32:53.260378+00:00",
    result: {
      job_id: "stale-job-4032",
      filename: "resort chw hvac synthetic fouling.csv",
      row_count: 4032,
      status: "complete",
      sii_completed: true,
      sii_intelligence: { facility_state: "Monitoring" },
    },
    snapshot: { status: "complete", sii_completed: true, current_upload: { job_id: "stale-job-4032" } },
  }]));

  render(h(App));
  await launchWorkspace();

  expect(screen.getByTestId("gate-result").textContent).toBe("empty");
  expect(screen.getByTestId("gate-session-job").textContent).toBe("empty");
});

it("starts on the operational workspace at the root route", async () => {
  render(h(App));

  await launchWorkspace();

  expect(window.location.pathname).toBe("/");
  expect(screen.getByTestId("gate-workspace")).toBeTruthy();
  expect(screen.queryByTestId("home-page")).toBeNull();
});

it("renders the operational workspace without a landing-page launch step", async () => {
  render(h(App));

  await launchWorkspace();

  expect(window.location.pathname).toBe("/");
  expect(screen.getByTestId("gate-workspace")).toBeTruthy();
});

it("opens the operational workspace only for direct workspace route entry", async () => {
  window.history.replaceState({}, "", "/workspace");

  render(h(App));

  await waitFor(() => {
    expect(screen.getByTestId("gate-workspace")).toBeTruthy();
  });
  expect(screen.queryByTestId("home-page")).toBeNull();
});

it("routes Command Center CSV selections into the visible auto-start upload workflow", async () => {
  render(h(App));
  await launchWorkspace();

  const file = new File(["timestamp,flow\n2026-01-01,1"], "ops.csv", { type: "text/csv" });
  fireEvent.change(screen.getByTestId("mock-overview-csv-upload-input"), { target: { files: [file] } });

  await waitFor(() => {
    expect(screen.getByTestId("telemetry-workspace")).toBeTruthy();
  });
  expect(screen.queryByTestId("gate-workspace")).toBeNull();
  expect(screen.getByTestId("telemetry-initial-file-count").textContent).toBe("1");
  expect(screen.getByTestId("telemetry-auto-start").textContent).toBe("true");
});

it("automatically restores a completed persisted latest analysis", async () => {
  runtimeState.latestUploadResult = {
    job_id: "persisted-job-42",
    row_count: 51841,
    data_quality: { analysis_gate_state: "DEGRADED_READY", warnings: ["cached warning"] },
    sii_intelligence: { facility_state: "Monitoring" },
  };
  runtimeState.latestUploadSnapshot = {
    status: "complete",
    last_filename: "cached-upload.csv",
    rows_processed: 51841,
    current_upload: { job_id: "persisted-job-42" },
  };

  render(h(App));
  await launchWorkspace();

  await waitFor(() => {
    expect(screen.getByTestId("gate-result").textContent).toBe("persisted-job-42");
  });
  expect(screen.getByTestId("gate-session-job").textContent).toBe("persisted-job-42");
  expect(screen.getByTestId("gate-previous-upload").textContent).toBe("none");
  expect(screen.queryByRole("button", { name: "Resume Previous Analysis" })).toBeNull();
  expect(screen.getByTestId("gate-heartbeat-status").textContent).toBe("Data stream active");
});

it("opens a completed persisted analysis without explicit resume", async () => {
  runtimeState.latestUploadResult = {
    job_id: "persisted-job-99",
    sii_reliable_enough_to_show: true,
    operator_report: { evidence_summary: ["persisted evidence"] },
    sii_intelligence: { facility_state: "Monitoring" },
  };
  runtimeState.latestUploadSnapshot = {
    status: "complete",
    sii_completed: true,
    current_upload: { job_id: "persisted-job-99" },
  };

  render(h(App));
  await launchWorkspace();

  await waitFor(() => {
    expect(screen.getByTestId("gate-result").textContent).toBe("persisted-job-99");
  });
  expect(screen.queryByRole("button", { name: "Resume Previous Analysis" })).toBeNull();
});

describe("App telemetry completion navigation", () => {
  it("refreshes persisted upload state and returns to the Gate", async () => {
    render(h(App));
    await launchWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Open telemetry intake" }));
    await waitFor(() => {
      expect(screen.getByTestId("telemetry-workspace")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Finish analysis" }));

    await waitFor(() => {
      expect(screen.getByTestId("gate-workspace")).toBeTruthy();
    });

    expect(screen.getByTestId("gate-result").textContent).toBe("persisted-job-42");
    expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true, forceRefresh: true, returnPayload: true });
    expect(runtimeMocks.loadFacilitySystems).toHaveBeenCalledTimes(1);
  });

  it("reset workspace clears the current analysis state", async () => {
    render(h(App));
    await launchWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Open telemetry intake" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear Telemetry Workspace" }));

    await waitFor(() => {
      expect(runtimeMocks.clearUploadSessionState).toHaveBeenCalledTimes(1);
    });
    expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: false });
  });

  it("does not leave Data Connections when an existing analysis is restored", async () => {
    render(h(App));
    await launchWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Open telemetry intake" }));
    fireEvent.click(screen.getByRole("button", { name: "Restore analysis" }));

    await waitFor(() => {
      expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true, forceRefresh: true, returnPayload: true });
    });

    expect(screen.getByTestId("telemetry-workspace")).toBeTruthy();
    expect(screen.queryByTestId("gate-workspace")).toBeNull();
  });

  it("forces a canonical current telemetry refetch after upload completion", async () => {
    render(h(App));
    await launchWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Open telemetry intake" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish analysis" }));

    await waitFor(() => {
      expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true, forceRefresh: true, returnPayload: true });
    });
    expect(runtimeMocks.loadFacilitySystems).toHaveBeenCalledWith({ forceRefresh: true });
  });

  it("shows analysis pending instead of a blank screen when canonical state is still settling", async () => {
    runtimeMocks.loadLatestUploadState.mockResolvedValueOnce(false);
    runtimeMocks.loadFacilitySystems.mockResolvedValueOnce(true);

    render(h(App));
    await launchWorkspace();

    fireEvent.click(screen.getByRole("button", { name: "Open telemetry intake" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish pending analysis" }));

    await waitFor(() => {
      expect(screen.getByTestId("gate-workspace")).toBeTruthy();
    });

    expect(screen.getByTestId("gate-session-job").textContent).toBe("pending-job-11");
    expect(screen.getByTestId("gate-processing-active").textContent).toBe("true");
    expect(screen.getByTestId("gate-processing-label").textContent).toMatch(/analysis pending/i);
  });

  it("shows a safe fallback when the post-analysis route render throws", async () => {
    runtimeState.throwGateError = true;
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const restoreWindowError = suppressExpectedGateRenderWindowError();

    try {
      render(h(App));
    await launchWorkspace();

      await waitFor(() => {
        expect(screen.getByTestId("app-render-fallback")).toBeTruthy();
      });
      expect(screen.getAllByText(/Workspace temporarily unavailable/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/connected data and existing analysis/i)).toBeTruthy();
      expect(screen.queryByText(/reopen the upload view/i)).toBeNull();
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
    await launchWorkspace();

      await waitFor(() => {
        expect(screen.getByTestId("app-render-fallback")).toBeTruthy();
      });

      runtimeState.throwGateError = false;
      fireEvent.click(screen.getByRole("button", { name: "Retry latest telemetry" }));

      await waitFor(() => {
        expect(screen.getByTestId("gate-workspace")).toBeTruthy();
      });
      expect(runtimeMocks.loadLatestUploadState).toHaveBeenCalledWith({ includePersisted: true, forceRefresh: true });
      expect(runtimeMocks.loadFacilitySystems).toHaveBeenCalledWith({ forceRefresh: true });
      expectOnlyExpectedRenderErrors(consoleErrorSpy);
    } finally {
      restoreWindowError();
      consoleErrorSpy.mockRestore();
    }
  });


  it("uses the last available state from the render fallback without forcing a telemetry refetch", async () => {
    runtimeState.throwGateError = true;
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const restoreWindowError = suppressExpectedGateRenderWindowError();

    try {
      render(h(App));
      await launchWorkspace();

      await waitFor(() => {
        expect(screen.getByTestId("app-render-fallback")).toBeTruthy();
      });

      runtimeState.throwGateError = false;
      fireEvent.click(screen.getByRole("button", { name: "Use last available state" }));

      await waitFor(() => {
        expect(screen.getByTestId("gate-workspace")).toBeTruthy();
      });
      expect(runtimeMocks.loadLatestUploadState).not.toHaveBeenCalledWith({ includePersisted: true, forceRefresh: true });
      expectOnlyExpectedRenderErrors(consoleErrorSpy);
    } finally {
      restoreWindowError();
      consoleErrorSpy.mockRestore();
    }
  });

  it("passes the same canonical insight to Command Center and Insights", async () => {
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

    window.sessionStorage.setItem("neraium.session_intent", "current");
    render(h(App));
    await launchWorkspace();

    const gateSummary = screen.getByTestId("gate-finding-summary").textContent;
    expect(gateSummary).toMatch(/historical operating pattern/i);
    expect(screen.getByTestId("gate-finding-confidence").textContent).toBe("High");

    fireEvent.click(screen.getByRole("button", { name: "Open insights" }));

    await waitFor(() => expect(screen.getByTestId("observation-workspace")).toBeTruthy());
    expect(screen.getByTestId("observation-finding-summary").textContent).toBe(gateSummary);
    expect(screen.getByTestId("observation-finding-confidence").textContent).toBe("High");
  });

  it("clears stale dataset cache when the authenticated session is revoked", async () => {
    render(h(App));
    await launchWorkspace();
    window.localStorage.setItem("neraium.completed_analysis_history", "[{\"rows\":4032}]");
    window.localStorage.setItem("neraium.last_upload_job_id", "stale-job");
    window.sessionStorage.setItem("neraium.session_intent", "current");

    window.dispatchEvent(new CustomEvent("neraium:session-expired"));

    expect(await screen.findByTestId("auth-screen")).toBeTruthy();
    expect(window.localStorage.getItem("neraium.completed_analysis_history")).toBeNull();
    expect(window.localStorage.getItem("neraium.last_upload_job_id")).toBeNull();
    expect(window.localStorage.getItem("neraium.dataset_cache_scope")).toBeNull();
    expect(window.sessionStorage.getItem("neraium.session_intent")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("session expired");
  });

  it("clears stale dataset cache on logout before showing the sign-in screen", async () => {
    render(h(App));
    await launchWorkspace();
    window.localStorage.setItem("neraium.completed_analysis_history", "[{\"rows\":4032}]");
    window.localStorage.setItem("neraium.last_upload_job_id", "stale-job");
    window.sessionStorage.setItem("neraium.session_intent", "resumed");

    fireEvent.click(screen.getByRole("button", { name: "Sign out test user" }));

    expect(await screen.findByTestId("auth-screen")).toBeTruthy();
    expect(window.localStorage.getItem("neraium.completed_analysis_history")).toBeNull();
    expect(window.localStorage.getItem("neraium.last_upload_job_id")).toBeNull();
    expect(window.localStorage.getItem("neraium.dataset_cache_scope")).toBeNull();
    expect(window.sessionStorage.getItem("neraium.session_intent")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("signed out");
  });

  it("keeps insights pending when telemetry exists but operator review is not yet evidence-ready", async () => {
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

    window.sessionStorage.setItem("neraium.session_intent", "current");
    render(h(App));
    await launchWorkspace();

    expect(screen.getByTestId("gate-finding-summary").textContent).toBe("Insights are not ready.");

    fireEvent.click(screen.getByRole("button", { name: "Open insights" }));
    await waitFor(() => expect(screen.getByTestId("observation-workspace")).toBeTruthy());
    expect(screen.getByTestId("observation-finding-summary").textContent).toBe("Insights are not ready.");
  });
});
