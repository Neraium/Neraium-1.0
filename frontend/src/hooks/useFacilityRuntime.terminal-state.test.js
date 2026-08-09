/* @vitest-environment jsdom */
import React, { useCallback, useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import useFacilityRuntime from "./useFacilityRuntime";
import useWorkspaceSessionController from "./useWorkspaceSessionController";
import { fetchLatestUploadState } from "../services/api/uploadApi";

const h = React.createElement;
const formatClockTime = () => "now";
const formatEndpoint = (value) => String(value);
const buildProtectedRequestMessage = async () => "Unauthorized";
const apiFetch = vi.fn();

vi.mock("./useStableInterval", () => ({ default: () => {} }));

vi.mock("../services/api/healthApi", () => ({
  fetchApiHealth: vi.fn(async () => ({ ready: {} })),
}));

vi.mock("../services/api/systemApi", () => ({
  fetchDomainMode: vi.fn(() => new Promise(() => {})),
  fetchEngineIdentity: vi.fn(async () => ({})),
  fetchFacilitySystems: vi.fn(async () => ({
    systems: [],
    domain_mode: null,
    intelligence_status: {},
  })),
}));

vi.mock("../services/api/uploadApi", () => ({
  clearLatestUploadStateCache: vi.fn(),
  fetchLatestUploadState: vi.fn(),
}));

function completedPayload(jobId = "job-monotonic") {
  const result = {
    job_id: jobId,
    status: "COMPLETE",
    completed_at: "2026-08-09T06:30:00Z",
    sii_reliable_enough_to_show: true,
    analysis_result: {
      fingerprint: { status: "stable" },
      systems: [],
      insights: [],
    },
    sii_intelligence: { facility_state: "Monitoring" },
  };
  return {
    job_id: jobId,
    status: "COMPLETE",
    processing_state: "complete",
    job_state: "completed",
    result_available: true,
    last_processed_at: "2026-08-09T06:30:00Z",
    latest_result: result,
    current_upload: { job_id: jobId, result },
  };
}

function staleProcessingPayload(jobId = "job-monotonic") {
  return {
    snapshot: {
      job_id: jobId,
      status: "PROCESSING",
      processing_state: "processing",
      session_state: "processing",
      state_available: true,
      current_upload: { job_id: jobId },
      message: "Delayed worker snapshot",
    },
    latestResult: null,
  };
}

function IntakeWorkspace({ onComplete }) {
  return h("section", { "data-testid": "data-connections" },
    h("button", { type: "button", onClick: onComplete }, "Complete upload"),
  );
}

function ResultsWorkspace({ controller, runtime }) {
  return h("section", { "data-testid": "results" },
    h("span", { "data-testid": "effective-status" }, controller.effectiveLatestUploadSnapshot.status),
    h("span", { "data-testid": "canonical-status" }, runtime.sessionStore.latestUploadSnapshot.status),
    h("span", { "data-testid": "canonical-job" }, runtime.sessionStore.jobId ?? "none"),
    h("span", { "data-testid": "canonical-ui-state" }, runtime.sessionStore.uiState),
    h("span", { "data-testid": "canonical-processing" }, String(runtime.sessionStore.isProcessing)),
    h("span", { "data-testid": "gate-processing" }, String(controller.gateProcessing.active)),
    h("button", {
      type: "button",
      onClick: () => void runtime.loadLatestUploadState({ includePersisted: true, forceRefresh: true }),
    }, "Run background refetch"),
  );
}

function RuntimeHandoffHarness() {
  const [activeWorkspace, setActiveWorkspace] = useState("data-connections");
  const [activeAnalysisIdentity, setActiveAnalysisIdentity] = useState(null);
  const navigateWorkspace = useCallback((workspace) => {
    setActiveWorkspace(workspace);
    if (workspace === "system-body") {
      setActiveAnalysisIdentity({
        portfolioId: "default",
        baselineId: "baseline-terminal",
        analysisRunId: "job-monotonic",
      });
    }
  }, []);
  const runtime = useFacilityRuntime({
    hasAccess: true,
    accessCode: "",
    formatClockTime,
    formatEndpoint,
    buildProtectedRequestMessage,
    datasetScopeKey: "terminal-test-scope",
    activeAnalysisIdentity,
  });
  const controller = useWorkspaceSessionController({
    activeWorkspace,
    datasetScopeKey: "terminal-test-scope",
    setActiveWorkspace: navigateWorkspace,
    apiFetch,
    accessCode: "",
    sessionStore: runtime.sessionStore,
    loadFacilitySystems: runtime.loadFacilitySystems,
    loadLatestUploadState: runtime.loadLatestUploadState,
    allowPersistedLatest: runtime.allowPersistedLatest,
    setAllowPersistedLatest: runtime.setAllowPersistedLatest,
    commitCompletedUploadState: runtime.commitCompletedUploadState,
    clearUploadSessionState: runtime.clearUploadSessionState,
    setIsDemoMode: runtime.setIsDemoMode,
  });

  if (activeWorkspace === "data-connections") {
    return h(IntakeWorkspace, {
      onComplete: () => void controller.handleGateUploadComplete(completedPayload()),
    });
  }

  return h(ResultsWorkspace, { controller, runtime });
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
  delete window.__NERAIUM_UPLOAD_IN_PROGRESS__;
  vi.clearAllMocks();
});

describe("terminal latest-upload runtime ownership", () => {
  it("keeps Results and canonical completion after intake unmount and delayed stale refetches", async () => {
    fetchLatestUploadState.mockResolvedValue(staleProcessingPayload());
    render(h(RuntimeHandoffHarness));

    fireEvent.click(screen.getByRole("button", { name: "Complete upload" }));

    await waitFor(() => expect(screen.getByTestId("results")).toBeTruthy());
    expect(screen.queryByTestId("data-connections")).toBeNull();
    expect(screen.getByTestId("effective-status").textContent).toBe("COMPLETE");
    expect(screen.getByTestId("canonical-status").textContent).toBe("COMPLETE");
    expect(screen.getByTestId("canonical-job").textContent).toBe("job-monotonic");
    expect(screen.getByTestId("canonical-ui-state").textContent).toBe("verified");
    expect(screen.getByTestId("canonical-processing").textContent).toBe("false");
    expect(screen.getByTestId("gate-processing").textContent).toBe("false");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run background refetch" }));
    });
    await waitFor(() => expect(fetchLatestUploadState).toHaveBeenCalledTimes(2));

    expect(screen.getByTestId("results")).toBeTruthy();
    expect(screen.queryByTestId("data-connections")).toBeNull();
    expect(screen.getByTestId("effective-status").textContent).toBe("COMPLETE");
    expect(screen.getByTestId("canonical-status").textContent).toBe("COMPLETE");
    expect(screen.getByTestId("canonical-ui-state").textContent).toBe("verified");
    expect(screen.getByTestId("canonical-processing").textContent).toBe("false");
    expect(screen.getByTestId("gate-processing").textContent).toBe("false");
  });
});
