/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import DataConnectionsWorkspace from "./DataConnectionsWorkspace";
import IntakeFlowPanel from "./setup/IntakeFlowPanel";

const h = React.createElement;

vi.mock("../services/api/uploadApi", () => ({
  uploadTelemetryFileWithProgress: vi.fn(),
}));

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
    latestMessage: "Awaiting file selection",
    visibleProgressPercent: null,
    propagationLabel: "",
    queuedWorkerDetail: "",
    uploadTransfer: null,
    uploadStateMessage: (state) => state === "idle" ? "Awaiting file selection" : "Telemetry export validated",
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
      progress_label: "Telemetry processing complete.",
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

it("idle no-file state does not render Upload 100%", () => {
  renderPanel({
    uploadState: "idle",
    selectedFiles: [],
    uploadJob: { job_id: "old-job", status: "complete", percent: 100, processing_state: "complete" },
  });

  expect(screen.getByText("No file selected")).toBeTruthy();
  expect(screen.getByText("Select a CSV telemetry file to begin.")).toBeTruthy();
  expect(screen.queryByLabelText("Upload 100% complete")).toBeNull();
});

it("idle no-file state does not render Processing 100%", () => {
  renderPanel({
    uploadState: "idle",
    selectedFiles: [],
    uploadJob: { job_id: "old-job", status: "complete", progress: 100, processing_state: "complete" },
  });

  expect(screen.queryByLabelText("Processing 100% complete")).toBeNull();
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
  expect(screen.queryByLabelText("Upload 100% complete")).toBeNull();
  expect(screen.queryByLabelText("Processing 100% complete")).toBeNull();
});

it("reset workspace hides progress bars", async () => {
  const onResetDemo = vi.fn(async () => ({}));
  renderWorkspace({
    hasResumedSession: true,
    sessionStore: completedSessionStore(),
    onResetDemo,
  });

  await waitFor(() => {
    expect(screen.getByLabelText("Upload 100% complete")).toBeTruthy();
  });

  fireEvent.click(screen.getByRole("button", { name: "Clear Upload Workspace" }));

  await waitFor(() => {
    expect(onResetDemo).toHaveBeenCalledTimes(1);
  });
  expect(screen.queryByLabelText("Upload 100% complete")).toBeNull();
  expect(screen.queryByLabelText("Processing 100% complete")).toBeNull();
});

it("previous completed upload does not leak progress into new idle upload screen", () => {
  renderWorkspace({
    hasActiveSession: false,
    hasResumedSession: false,
    sessionStore: completedSessionStore(),
  });

  expect(screen.getByText("No file selected")).toBeTruthy();
  expect(screen.getByText("Select a CSV telemetry file to begin.")).toBeTruthy();
  expect(screen.queryByLabelText("Upload 100% complete")).toBeNull();
  expect(screen.queryByLabelText("Processing 100% complete")).toBeNull();
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
      progress_label: "Scoring operating changes...",
      propagation_stage: "scoring_drift_relationships",
      propagation_progress: 75,
      propagation_label: "Scoring operating changes...",
      worker_state: "starting",
    },
    latestMessage: "Scoring operating changes...",
    propagationLabel: "Scoring operating changes...",
    queuedWorkerDetail: "Worker starting...",
  });

  expect(screen.getByText("Scoring operating changes...")).toBeTruthy();
  expect(screen.queryByText("Worker starting...")).toBeNull();
  expect(screen.getByLabelText("Processing 75% complete")).toBeTruthy();
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
      progress_label: "Building baseline...",
      result_available: false,
    },
    latestMessage: "Building baseline...",
  });

  expect(screen.getByLabelText("Upload 100% complete")).toBeTruthy();
  expect(screen.getByLabelText("Processing 65% complete")).toBeTruthy();
  expect(screen.queryByLabelText("Processing 100% complete")).toBeNull();
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
      progress_label: "Writing result and replay...",
      result_available: true,
      replay_ready: true,
    },
    latestMessage: "Writing result and replay...",
  });

  expect(screen.getByLabelText("Processing 95% complete")).toBeTruthy();
  expect(screen.queryByLabelText("Processing 100% complete")).toBeNull();
});
