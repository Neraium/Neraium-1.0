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
  retryUploadAnalysisJob: vi.fn(),
}));

function renderPanel(overrides = {}) {
  return render(h(IntakeFlowPanel, {
    handleUpload: vi.fn((event) => event?.preventDefault?.()),
    uploadInputRef: { current: null },
    handleFileSelection: vi.fn(),
    selectedFiles: [],
    pendingUploadKind: "csv",
    selectedFileSize: "Awaiting file",
    isUploadProcessing: (state) => ["uploading", "processing", "running_sii", "structural_scoring", "building_fingerprint"].includes(String(state)),
    uploadState: "idle",
    openFilePicker: vi.fn(),
    uploadJob: null,
    latestMessage: "Choose a CSV to analyze.",
    visibleProgressPercent: null,
    propagationLabel: "",
    queuedWorkerDetail: "",
    uploadTransfer: null,
    uploadStateMessage: (state) => state === "idle" ? "Choose a CSV to analyze." : "CSV ready.",
    batchResults: [],
    onRetryFailedUploads: vi.fn(),
    onReprocessCurrentBatch: vi.fn(),
    onResetWorkspace: vi.fn(),
    onViewResults: vi.fn(),
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
    latestUploadResult: {
      job_id: "completed-job-1",
      filename: "old.csv",
      analysis_result: {
        systems: [{ name: "Recovered system" }],
        insights: [{ title: "Recovered insight" }],
        fingerprint: { status: "Established" },
      },
    },
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

function selectedCsv(name = "fresh.csv") {
  return new File(["timestamp,value\n2026-06-22,1\n"], name, { type: "text/csv" });
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  vi.clearAllMocks();
});

it("mobile upload screen does not render backend milestone cards by default", () => {
  window.innerWidth = 390;
  renderPanel();

  expect(screen.getByRole("heading", { name: "Analyze System" })).toBeTruthy();
  expect(screen.queryByLabelText("Backend milestones")).toBeNull();
  expect(screen.queryByText("Backend milestones")).toBeNull();
  expect(screen.queryByText("What this run returns")).toBeNull();
  expect(screen.queryByText("Current run at a glance")).toBeNull();
});

it("selected file state shows filename, size, and Upload and Analyze", () => {
  renderPanel({
    uploadState: "validated",
    selectedFiles: [selectedCsv("operators.csv")],
    selectedFileSize: "15.7 MB",
  });

  expect(screen.getByText("operators.csv")).toBeTruthy();
  expect(screen.getByText("CSV - 15.7 MB")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Choose Another File" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Upload and Analyze" })).toBeTruthy();
});

it("processing state shows one progress bar", () => {
  renderPanel({
    uploadState: "running_sii",
    selectedFiles: [selectedCsv("progress.csv")],
    selectedFileSize: "1.0 KB",
    uploadJob: {
      job_id: "progress-job",
      status: "PROCESSING",
      processing_state: "building_fingerprint",
      percent: 65,
      progress: 65,
      progress_label: "Building fingerprint...",
      result_available: false,
    },
    latestMessage: "Building fingerprint...",
  });

  expect(screen.getByText("Building operating fingerprint...")).toBeTruthy();
  expect(screen.getAllByRole("progressbar")).toHaveLength(1);
  expect(screen.getByLabelText("Analysis 65% complete")).toBeTruthy();
});

it("failed state shows retry and choose another file", () => {
  renderPanel({
    uploadState: "error",
    selectedFiles: [selectedCsv("bad.csv")],
    selectedFileSize: "3.2 MB",
    latestMessage: "CSV could not be parsed.",
    uploadJob: {
      job_id: "failed-job",
      status: "FAILED",
      processing_state: "failed",
      error: "CSV could not be parsed.",
    },
  });

  expect(screen.getByRole("heading", { name: "Analysis failed" })).toBeTruthy();
  expect(screen.getAllByText("CSV could not be parsed.").length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Choose Another File" })).toBeTruthy();
});

it("complete state shows View Results", () => {
  renderPanel({
    uploadState: "complete",
    selectedFiles: [selectedCsv("complete.csv")],
    selectedFileSize: "8.4 MB",
    latestUploadSnapshot: {
      latest_result: {
        analysis_result: {
          systems: [{ name: "Pumping" }, { name: "Storage" }],
          insights: [{ title: "Pump cycling changed." }],
          fingerprint: { status: "Established" },
        },
      },
    },
    uploadJob: { job_id: "complete-job", status: "COMPLETE", result_available: true },
  });

  expect(screen.getByRole("heading", { name: "Analysis Complete" })).toBeTruthy();
  expect(screen.getByText("Systems identified")).toBeTruthy();
  expect(screen.getByText("Insights found")).toBeTruthy();
  expect(screen.getByText("Fingerprint status")).toBeTruthy();
  expect(screen.getByRole("button", { name: "View Results" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Analyze Another CSV" })).toBeTruthy();
});


it("completed upload screen count matches AnalysisResult systems length", () => {
  renderPanel({
    uploadState: "complete",
    selectedFiles: [selectedCsv("systems-count.csv")],
    selectedFileSize: "8.4 MB",
    latestUploadSnapshot: {
      latest_result: {
        identified_systems: [{ name: "Legacy single system" }],
        analysis_result: {
          systems: [
            { name: "Chilled Water" },
            { name: "Condenser Water" },
            { name: "Pumps" },
          ],
          insights: [],
          fingerprint: { status: "Established" },
        },
      },
    },
    uploadJob: { job_id: "complete-job", status: "COMPLETE", result_available: true },
  });

  const item = screen.getByText("Systems identified").closest(".upload-result-summary__item");
  expect(item.textContent).toContain("3");
});

it("completed upload screen count matches AnalysisResult insights length", () => {
  renderPanel({
    uploadState: "complete",
    selectedFiles: [selectedCsv("insights-count.csv")],
    selectedFileSize: "8.4 MB",
    latestUploadSnapshot: {
      latest_result: {
        insights: [{ title: "Legacy finding" }],
        analysis_result: {
          systems: [],
          insights: [
            { title: "Pump vibration increased sharply" },
            { title: "Thermal response behavior changed" },
            { title: "Pump power increased" },
            { title: "Flow behavior changed" },
          ],
          fingerprint: { status: "Changed" },
        },
      },
    },
    uploadJob: { job_id: "complete-job", status: "COMPLETE", result_available: true },
  });

  const item = screen.getByText("Insights found").closest(".upload-result-summary__item");
  expect(item.textContent).toContain("4");
});

it("shows finalizing results instead of fake zero counts before AnalysisResult is available", () => {
  renderPanel({
    uploadState: "complete",
    selectedFiles: [selectedCsv("finalizing.csv")],
    selectedFileSize: "8.4 MB",
    latestUploadSnapshot: {
      latest_result: {
        identified_systems: [],
        insights: [],
        fingerprint_status: "Pending",
      },
    },
    uploadJob: { job_id: "complete-job", status: "COMPLETE", result_available: true },
  });

  expect(screen.getByText("Finalizing results...")).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Analysis Complete" })).toBeNull();
  expect(screen.queryByText("Systems identified")).toBeNull();
  expect(screen.queryByText("Insights found")).toBeNull();
  expect(screen.getByLabelText("Analysis 99% complete")).toBeTruthy();
});

it("idle no-file state does not render stale complete progress", () => {
  renderPanel({
    uploadState: "idle",
    selectedFiles: [],
    uploadJob: { job_id: "old-job", status: "complete", percent: 100, processing_state: "complete" },
  });

  expect(screen.getByText("No CSV selected")).toBeTruthy();
  expect(screen.getByText("Choose a CSV to analyze.")).toBeTruthy();
  expect(screen.queryAllByRole("progressbar")).toHaveLength(0);
});

it("selecting a file clears stale complete progress", async () => {
  renderWorkspace({
    hasActiveSession: true,
    sessionStore: completedSessionStore(),
  });

  const input = screen.getByTestId("csv-upload-input");
  fireEvent.change(input, { target: { files: [selectedCsv()] } });

  await waitFor(() => {
    expect(screen.getByText("fresh.csv")).toBeTruthy();
  });
  expect(screen.queryAllByRole("progressbar")).toHaveLength(0);
  expect(screen.getByRole("button", { name: "Upload and Analyze" })).toBeTruthy();
});

it("analyze another CSV resets the completed workspace", async () => {
  const onResetDemo = vi.fn(async () => ({}));
  renderWorkspace({
    hasResumedSession: true,
    sessionStore: completedSessionStore(),
    onResetDemo,
  });

  await waitFor(() => {
    expect(screen.getByRole("button", { name: "Analyze Another CSV" })).toBeTruthy();
  });

  fireEvent.click(screen.getByRole("button", { name: "Analyze Another CSV" }));

  await waitFor(() => {
    expect(onResetDemo).toHaveBeenCalledTimes(1);
  });
  expect(screen.queryAllByRole("progressbar")).toHaveLength(0);
});

it("previous completed upload does not leak progress into new idle upload screen", () => {
  renderWorkspace({
    hasActiveSession: false,
    hasResumedSession: false,
    sessionStore: completedSessionStore(),
  });

  expect(screen.getByText("No CSV selected")).toBeTruthy();
  expect(screen.getByText("Choose a CSV to analyze.")).toBeTruthy();
  expect(screen.queryAllByRole("progressbar")).toHaveLength(0);
});

it("treats the first complete payload with a saved result as terminal and waits for View Results navigation", async () => {
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
          analysis_result: {
            systems: [{ name: "Completed system" }],
            insights: [{ title: "Completed insight" }],
            fingerprint: { status: "Established" },
          },
        }),
      };
    }
    return { ok: true, json: async () => ({}) };
  });
  const onUploadComplete = vi.fn(async () => {});

  renderWorkspace({ apiFetch, onUploadComplete });

  const input = screen.getByTestId("csv-upload-input");
  fireEvent.change(input, { target: { files: [selectedCsv()] } });
  fireEvent.click(screen.getByTestId("process-upload-button"));

  await waitFor(() => {
    expect(onUploadComplete).toHaveBeenCalledWith(expect.objectContaining({ job_id: "job-complete" }), { navigateToGate: false });
  });

  expect(await screen.findByRole("button", { name: "View Results" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "View Results" }));

  await waitFor(() => {
    expect(onUploadComplete).toHaveBeenCalledWith(expect.objectContaining({ job_id: "job-complete" }), { navigateToGate: true });
  });
});

it("renders intermediate processing progress without jumping to complete", () => {
  renderPanel({
    uploadState: "running_sii",
    selectedFiles: [selectedCsv("progress.csv")],
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

  expect(screen.getAllByRole("progressbar")).toHaveLength(1);
  expect(screen.getByLabelText("Analysis 65% complete")).toBeTruthy();
  expect(screen.queryByLabelText("Analysis 100% complete")).toBeNull();
});

it("does not show processing 100 until status is complete", () => {
  renderPanel({
    uploadState: "running_sii",
    selectedFiles: [selectedCsv("not-complete.csv")],
    selectedFileSize: "1.0 KB",
    uploadJob: {
      job_id: "not-complete-job",
      status: "PROCESSING",
      processing_state: "saving_result",
      percent: 100,
      progress: 100,
      progress_label: "Saving result...",
      result_available: true,
      replay_ready: false,
    },
    latestMessage: "Saving result...",
  });

  expect(screen.getByLabelText("Analysis 99% complete")).toBeTruthy();
  expect(screen.queryByLabelText("Analysis 100% complete")).toBeNull();
  expect(screen.queryByText(/replay/i)).toBeNull();
  expect(screen.queryByText("Replay status")).toBeNull();
});
