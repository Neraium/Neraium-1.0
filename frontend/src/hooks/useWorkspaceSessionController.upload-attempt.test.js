/* @vitest-environment jsdom */
import React, { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import useWorkspaceSessionController from "./useWorkspaceSessionController";

const h = React.createElement;

function completedResult(jobId, datasetId, readiness) {
  return {
    job_id: jobId,
    dataset_id: datasetId,
    filename: `${datasetId}.csv`,
    status: "complete",
    processing_state: "complete",
    completed_at: jobId === "previous-job" ? "2026-08-01T00:00:00Z" : "2026-08-10T00:00:00Z",
    data_quality: { readiness: "ready", analysis_gate_state: "READY" },
    ingestion_trust: {
      dataset_id: datasetId,
      readiness: { outcome: readiness, limitations: [] },
      summary: { signal_counts: { detected: jobId === "previous-job" ? 26 : 31 } },
    },
  };
}

function completedStore(result) {
  return {
    jobId: result.job_id,
    uiState: "verified",
    latestUploadResult: result,
    latestUploadSnapshot: {
      job_id: result.job_id,
      dataset_id: result.dataset_id,
      status: "complete",
      processing_state: "complete",
      session_state: "verified",
      state_available: true,
      latest_result: result,
      current_upload: { job_id: result.job_id, dataset_id: result.dataset_id, result },
    },
  };
}

function AttemptHarness({ previousResult, currentResult }) {
  const [sessionStore, setSessionStore] = useState(() => completedStore(previousResult));
  const loadLatestUploadState = vi.fn(async () => ({
    hasRuntimeData: true,
    latestResult: previousResult,
    snapshot: completedStore(previousResult).latestUploadSnapshot,
  }));
  const controller = useWorkspaceSessionController({
    activeWorkspace: "system-body",
    datasetScopeKey: "attempt-regression",
    setActiveWorkspace: vi.fn(),
    apiFetch: vi.fn(),
    accessCode: "",
    sessionStore,
    loadFacilitySystems: vi.fn(async () => true),
    loadLatestUploadState,
    allowPersistedLatest: true,
    setAllowPersistedLatest: vi.fn(),
    commitCompletedUploadState: vi.fn(() => true),
    clearUploadSessionState: vi.fn(),
    setIsDemoMode: vi.fn(),
  });
  const visibleTrust = controller.effectiveLatestUploadResult?.ingestion_trust ?? null;
  const previousRecord = controller.analysisHistory.find((record) => record.jobId === previousResult.job_id);

  return h("section", {},
    h("span", { "data-testid": "visible-job" }, controller.effectiveLatestUploadResult?.job_id ?? "none"),
    h("span", { "data-testid": "visible-trust" }, visibleTrust?.readiness?.outcome ?? "none"),
    h("span", { "data-testid": "visible-status" }, controller.effectiveLatestUploadSnapshot?.status ?? "none"),
    h("span", { "data-testid": "processing-active" }, String(controller.gateProcessing.active)),
    h("span", { "data-testid": "attempt-id" }, controller.activeUploadAttempt?.attemptId ?? "none"),
    h("button", {
      type: "button",
      onClick: () => controller.handleUploadAttemptStarted({
        files: [new File(["timestamp,flow\n2026-08-10,1"], "new-upload.csv", { type: "text/csv" })],
        workflow: "create_baseline",
      }),
    }, "Start new upload"),
    h("button", {
      type: "button",
      onClick: () => controller.handleUploadAttemptIdentified({
        attemptId: controller.activeUploadAttempt?.attemptId,
        jobId: currentResult.job_id,
        datasetId: currentResult.dataset_id,
      }),
    }, "Identify current upload"),
    h("button", {
      type: "button",
      onClick: () => setSessionStore(completedStore({ ...previousResult })),
    }, "Apply delayed previous hydration"),
    h("button", {
      type: "button",
      onClick: () => void controller.handleGateUploadComplete({
        ...previousResult,
        result_available: true,
        latest_result: previousResult,
        current_upload: { job_id: previousResult.job_id, dataset_id: previousResult.dataset_id, result: previousResult },
      }, { navigateToGate: false, attemptId: "detached-previous-attempt" }),
    }, "Apply delayed previous completion"),
    h("button", {
      type: "button",
      onClick: () => void controller.handleGateUploadComplete({
        ...currentResult,
        result_available: true,
        latest_result: currentResult,
        current_upload: { job_id: currentResult.job_id, dataset_id: currentResult.dataset_id, result: currentResult },
      }, { navigateToGate: false }),
    }, "Complete current upload"),
    h("button", {
      type: "button",
      disabled: !previousRecord,
      onClick: () => previousRecord && controller.handleReopenHistoricalAnalysis(previousRecord.id),
    }, "Open previous historical upload"),
  );
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.clearAllMocks();
});

describe("workspace upload-attempt presentation ownership", () => {
  it("suppresses stale readiness through delayed hydration and restores intentional history", async () => {
    const previousResult = completedResult("previous-job", "previous-dataset", "ready_with_limitations");
    const currentResult = completedResult("current-job", "current-dataset", "ready");
    render(h(AttemptHarness, { previousResult, currentResult }));

    await waitFor(() => expect(screen.getByTestId("visible-job").textContent).toBe("previous-job"));
    expect(screen.getByTestId("visible-trust").textContent).toBe("ready_with_limitations");
    expect(screen.getByTestId("processing-active").textContent).toBe("false");

    fireEvent.click(screen.getByRole("button", { name: "Start new upload" }));

    expect(screen.getByTestId("attempt-id").textContent).not.toBe("none");
    expect(screen.getByTestId("visible-job").textContent).toBe("none");
    expect(screen.getByTestId("visible-trust").textContent).toBe("none");
    expect(screen.getByTestId("visible-status").textContent).toBe("uploading");
    expect(screen.getByTestId("processing-active").textContent).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "Apply delayed previous hydration" }));
    expect(screen.getByTestId("visible-job").textContent).toBe("none");
    expect(screen.getByTestId("visible-trust").textContent).toBe("none");
    expect(screen.getByTestId("processing-active").textContent).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: "Apply delayed previous completion" }));
    expect(screen.getByTestId("visible-job").textContent).toBe("none");
    expect(screen.getByTestId("visible-trust").textContent).toBe("none");

    fireEvent.click(screen.getByRole("button", { name: "Identify current upload" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply delayed previous hydration" }));
    expect(screen.getByTestId("visible-job").textContent).toBe("none");
    expect(screen.getByTestId("visible-trust").textContent).toBe("none");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Complete current upload" }));
    });
    await waitFor(() => expect(screen.getByTestId("visible-job").textContent).toBe("current-job"));
    expect(screen.getByTestId("visible-trust").textContent).toBe("ready");
    expect(screen.getByTestId("processing-active").textContent).toBe("false");

    await waitFor(() => expect(screen.getByRole("button", { name: "Open previous historical upload" }).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Open previous historical upload" }));

    expect(screen.getByTestId("attempt-id").textContent).toBe("none");
    expect(screen.getByTestId("visible-job").textContent).toBe("previous-job");
    expect(screen.getByTestId("visible-trust").textContent).toBe("ready_with_limitations");
  });
});
