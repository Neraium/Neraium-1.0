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
    isUploadProcessing: (state) => ["uploading", "processing"].includes(String(state)),
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
