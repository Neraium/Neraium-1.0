/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import DataConnectionsWorkspace from "./DataConnectionsWorkspace";
import IntakeFlowPanel from "./setup/IntakeFlowPanel";
import { uploadTelemetryFileWithProgress } from "../services/api/uploadApi";

const h = React.createElement;

vi.mock("../services/api/uploadApi", () => ({
  uploadTelemetryFileWithProgress: vi.fn(),
}));

const legacyUploadCompleteLabels = [
  "Upload 100% complete",
  "Telemetry transfer 100% complete",
];
const legacyProcessingCompleteLabels = [
  "Processing 100% complete",
  "Analysis 100% complete",
];

function expectNoCompleteProgressBars() {
  for (const label of legacyUploadCompleteLabels) {
    expect(screen.queryByLabelText(label)).toBeNull();
  }
  for (const label of legacyProcessingCompleteLabels) {
    expect(screen.queryByLabelText(label)).toBeNull();
  }
}

function renderPanel(overrides = {}) {
  return render(h(IntakeFlowPanel, {
    handleUpload: vi.fn((event) => event?.preventDefault?.()),
    uploadInputRef: { current: null },
    handleFileSelection: vi.fn(),
    selectedFiles: [],
    pendingUploadKind: "csv",
    selectedFileSize: "Awaiting file",
    isUploadProcessing: (state) => ["uploading", "processing", "running_sii"].includes(String(state)),
    uploadState: "idle",
    openFilePicker: vi.fn(),
    uploadJob: null,
    latestMessage: "Choose a telemetry file to begin.",
    visibleProgressPercent: null,
    propagationLabel: "",
    queuedWorkerDetail: "",
    uploadTransfer: null,
    uploadStateMessage: (state) => state === "idle" ? "Choose a telemetry file to begin." : "Telemetry file ready.",
    batchResults: [],
    onRetryFailedUploads: vi.fn(),
    onReprocessCurrentBatch: vi.fn(),
    onResetWorkspace: vi.fn(),
    ...overrides,
  }));
}

function completedSessionStore() {
  return {
    jobId: "completed-job-1",
    uiState: "verified",
    latestUploadSnapshot: {
      status: "complete",
      processing_state: "complete",
      percent: 100,
      progress: 100,
      progress_label: "Analysis ready.",
    },
    latestUploadResult: { job_id: "completed-job-1", filename: "old.csv" },
  };
}

function renderWorkspace(props = {}) {
  return render(h(DataConnectionsWorkspace, {
    accessCode: "",
    apiFetch: vi.fn(async () => ({ ok: true, json: async () => ({}) })),
    latestUploadSnapshot: { status: "empty" },
    latestUploadResult: null,
    hasActiveSession: false,
    hasResumedSession: false,
    sessionStore: null,
    onUploadComplete: vi.fn(),
    onResetDemo: vi.fn(async () => ({})),
    ...props,
  }));
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.clearAllMocks();
});

it("idle no-file state does not render stale complete upload progress", () => {
  renderPanel({
    uploadState: "idle",
    selectedFiles: [],
    uploadJob: { job_id: "old-job", status: "complete", percent: 100, processing_state: "complete" },
  });

  expect(screen.getByText(/No telemetry file selected|No file selected/i)).toBeTruthy();
  expect(screen.getByText(/Select a telemetry file to begin|Select a CSV telemetry file to begin/i)).toBeTruthy();
  expectNoCompleteProgressBars();
});

it("idle no-file state does not render stale complete processing progress", () => {
  renderPanel({
    uploadState: "idle",
    selectedFiles: [],
    uploadJob: { job_id: "old-job", status: "complete", progress: 100, processing_state: "complete" },
  });

  expectNoCompleteProgressBars();
  expect(screen.queryAllByRole("progressbar")).toHaveLength(0);
});

it("selecting a file clears stale complete progress", async () => {
  renderWorkspace({
    hasActiveSession: true,
    sessionStore: completedSessionStore(),
  });

  const input = screen.getByTestId("csv-upload-input");
  const file = new File(["timestamp,value\n2026-06-22,1\n"], "fresh.csv", { type: "text/csv" });
  fireEvent.change(input, { target: { files: [file] } });

  await waitFor(() => {
    expect(screen.getByText("fresh.csv")).toBeTruthy();
  });
  expectNoCompleteProgressBars();
});

it("reset workspace hides progress bars", async () => {
  const onResetDemo = vi.fn(async () => ({}));
  renderWorkspace({
    hasResumedSession: true,
    sessionStore: completedSessionStore(),
    onResetDemo,
  });

  await waitFor(() => {
    expect(screen.getByLabelText(/Telemetry transfer 100% complete|Upload 100% complete/i)).toBeTruthy();
  });

  fireEvent.click(screen.getByRole("button", { name: /Clear Analysis|Clear Upload Workspace/i }));

  await waitFor(() => {
    expect(onResetDemo).toHaveBeenCalledTimes(1);
  });
  expectNoCompleteProgressBars();
});

it("previous completed upload does not leak progress into new idle upload screen", () => {
  renderWorkspace({
    hasActiveSession: false,
    hasResumedSession: false,
    sessionStore: completedSessionStore(),
  });

  expect(screen.getByText(/No telemetry file selected|No file selected/i)).toBeTruthy();
  expect(screen.getByText(/Select a telemetry file to begin|Select a CSV telemetry file to begin/i)).toBeTruthy();
  expectNoCompleteProgressBars();
});

it("treats the first complete payload with a saved result as terminal even if replay is still finalizing", async () => {
  uploadTelemetryFileWithProgress.mockResolvedValue({
    ok: true,
    status: 202,
    payload: { job_id: "job-complete", status_url: "/api/data/upload-status/job-complete", status: "queued", message: "Upload accepted." },
  });

  const apiFetch = vi.fn(async (path) => {
    if (String(path).includes("/api/data/upload-status/job-complete")) {
      return {
        ok: true,
        json: async () => ({
          job_id: "job-complete",
          status: "COMPLETE",
          processing_state: "complete",
          result_available: true,
          replay_ready: false,
          progress_label: "Analysis ready.",
          message: "Analysis ready.",
        }),
      };
    }
    return { ok: true, json: async () => ({}) };
  });
  const onUploadComplete = vi.fn(async () => {});

  renderWorkspace({ apiFetch, onUploadComplete });

  const input = screen.getByTestId("csv-upload-input");
  const file = new File(["timestamp,value\n2026-06-22,1\n"], "fresh.csv", { type: "text/csv" });
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.click(screen.getByTestId("process-upload-button"));

  await waitFor(() => {
    expect(onUploadComplete).toHaveBeenCalledWith(expect.objectContaining({ job_id: "job-complete" }), { navigateToGate: true });
  });
});

it("renders backend stage labels ahead of worker status detail", () => {
  const file = new File(["timestamp,value\n2026-06-22,1\n"], "stage.csv", { type: "text/csv" });

  renderPanel({
    uploadState: "running_sii",
    selectedFiles: [file],
    selectedFileSize: "1.0 KB",
    uploadJob: {
      job_id: "stage-job",
      status: "PROCESSING",
      processing_state: "scoring_drift_relationships",
      percent: 75,
      progress: 75,
      progress_label: "Mapping relationships...",
      propagation_stage: "scoring_drift_relationships",
      propagation_progress: 75,
      propagation_label: "Mapping relationships...",
      worker_state: "starting",
    },
    latestMessage: "Mapping relationships...",
    propagationLabel: "Mapping relationships...",
    queuedWorkerDetail: "Worker starting...",
  });

  expect(screen.getByText("Mapping relationships...")).toBeTruthy();
  expect(screen.queryByText("Worker starting...")).toBeNull();
  expect(screen.getByLabelText(/Analysis 75% complete|Processing 75% complete/i)).toBeTruthy();
});

it("renders intermediate backend processing progress without jumping to complete", () => {
  const file = new File(["timestamp,value\n2026-06-22,1\n"], "progress.csv", { type: "text/csv" });

  renderPanel({
    uploadState: "running_sii",
    selectedFiles: [file],
    selectedFileSize: "1.0 KB",
    uploadJob: {
      job_id: "progress-job",
      status: "PROCESSING",
      processing_state: "building_baseline",
      percent: 65,
      progress: 65,
      progress_label: "Identifying systems...",
      result_available: false,
    },
    latestMessage: "Identifying systems...",
  });

  expect(screen.getByLabelText(/Telemetry transfer 100% complete|Upload 100% complete/i)).toBeTruthy();
  expect(screen.getByLabelText(/Analysis 65% complete|Processing 65% complete/i)).toBeTruthy();
  expect(screen.queryByLabelText(/Analysis 100% complete|Processing 100% complete/i)).toBeNull();
});

it("does not show processing 100 until backend status is complete", () => {
  const file = new File(["timestamp,value\n2026-06-22,1\n"], "not-complete.csv", { type: "text/csv" });

  renderPanel({
    uploadState: "running_sii",
    selectedFiles: [file],
    selectedFileSize: "1.0 KB",
    uploadJob: {
      job_id: "not-complete-job",
      status: "PROCESSING",
      processing_state: "writing_result_replay",
      percent: 95,
      progress: 95,
      progress_label: "Saving result...",
      result_available: true,
      replay_ready: true,
    },
    latestMessage: "Saving result...",
  });

  expect(screen.getByLabelText(/Analysis 95% complete|Processing 95% complete/i)).toBeTruthy();
  expect(screen.queryByLabelText(/Analysis 100% complete|Processing 100% complete/i)).toBeNull();
});
