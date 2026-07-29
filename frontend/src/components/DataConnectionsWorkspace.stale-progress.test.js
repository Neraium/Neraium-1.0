/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DataConnectionsWorkspace, { formatAnalysisUpdateTime, frontendPollingTiming, queuedWorkerMessage, resolveOpenBaselineIdentity } from "./DataConnectionsWorkspace";
import IntakeFlowPanel, { baselineCompletionSummary, failedImportStageRows, resolveBaselineProcessingStage } from "./setup/IntakeFlowPanel";
import { uploadTelemetryFileWithProgress } from "../services/api/uploadApi";
import { clearBaselineResultCache } from "../services/api/baselineApi";
import { persistBaselineSelection } from "../viewModels/baselineSelection";
import { SERVICE_UNAVAILABLE_UPLOAD_MESSAGE } from "../viewModels/uploadFlow";

const h = React.createElement;

vi.mock("../services/api/uploadApi", () => ({
  DIRECT_UPLOAD_MAX_BYTES: 250 * 1024 * 1024,
  LARGE_UPLOAD_MAX_BYTES: 512 * 1024 * 1024,
  uploadTelemetryFileWithProgress: vi.fn(),
  retryUploadAnalysisJob: vi.fn(),
}));

function selectedCsv(name = "plant-history.csv") {
  return new File(["timestamp,flow,power\n2026-06-22,1,2\n"], name, { type: "text/csv" });
}

function jsonResponse(payload, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    headers: { get: () => "application/json" },
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  };
}

function learnedBaseline(overrides = {}) {
  return {
    job_id: "baseline-job",
    upload_id: "baseline-job",
    dataset_id: "baseline-job",
    baseline_candidate_id: "bdm-v1-baseline",
    established_baseline_id: "bdm-v1-baseline",
    portfolio_id: "default",
    system_id: "default",
    workflow: "create_baseline",
    filename: "plant-history.csv",
    status: "COMPLETE",
    processing_state: "complete",
    candidate_model: {
      model_id: "bdm-v1-baseline",
      baseline_id: "bdm-v1-baseline",
      baseline_candidate_id: "bdm-v1-baseline",
      version: 1,
      status: "awaiting_approval",
      source: { job_id: "baseline-job", upload_id: "baseline-job", dataset_id: "baseline-job", portfolio_id: "default", system_id: "default", filename: "plant-history.csv", row_count: 2400 },
      telemetry_schema: {
        numeric_columns: ["flow", "power", "pressure", "temperature"],
      },
      timestamp_quality: {
        first_timestamp: "2026-06-01T00:00:00Z",
        last_timestamp: "2026-06-30T23:55:00Z",
      },
      data_quality: {
        reliability_rating: "strong",
        reliability_score: 94,
      },
      relationship_graph: {
        nodes: [{ signal: "flow" }, { signal: "power" }],
        edges: [{ edge_id: "flow:power" }, { edge_id: "pressure:flow" }, { edge_id: "temperature:power" }],
      },
      suitability: { decision: "suitable", score: 91 },
      activation: { state: "awaiting_approval" },
    },
    baseline_suitability: { decision: "suitable", score: 91, eligible_for_activation: true },
    activation: { state: "awaiting_approval" },
    ...overrides,
  };
}

function renderPanel(overrides = {}) {
  return render(h(IntakeFlowPanel, {
    handleUpload: vi.fn((event) => event?.preventDefault?.()),
    uploadInputRef: { current: null },
    handleFileSelection: vi.fn(),
    selectedFiles: [],
    pendingUploadKind: "csv",
    selectedFileSize: "No file",
    isUploadProcessing: (state) => [
      "uploading",
      "accepted",
      "queued",
      "processing",
      "running_sii",
      "structural_scoring",
      "building_fingerprint",
      "saving_results",
      "navigation_pending",
    ].includes(String(state)),
    uploadState: "idle",
    openFilePicker: vi.fn(),
    uploadJob: null,
    latestMessage: "",
    visibleProgressPercent: null,
    propagationLabel: "",
    queuedWorkerDetail: "",
    uploadTransfer: null,
    uploadStateMessage: vi.fn(),
    onRetryFailedUploads: vi.fn(),
    onResetWorkspace: vi.fn(),
    onViewResults: vi.fn(),
    onOpenBaseline: vi.fn(),
    onImportComparisonDataset: vi.fn(),
    ...overrides,
  }));
}

function workspaceElement(props = {}) {
  return h(DataConnectionsWorkspace, {
    accessCode: "",
    apiFetch: vi.fn(async () => jsonResponse({})),
    latestUploadSnapshot: { status: "empty" },
    latestUploadResult: null,
    hasActiveSession: false,
    hasResumedSession: false,
    sessionStore: null,
    onUploadComplete: vi.fn(),
    onOpenBaseline: vi.fn(),
    onBaselineSelected: vi.fn(),
    currentUser: { id: "engineer-1" },
    ...props,
  });
}

function renderWorkspace(props = {}) {
  return render(workspaceElement(props));
}

function namedBaseline({ id, jobId, filename, portfolioId = "default", signalCount = 4, relationshipCount = 3 }) {
  const base = learnedBaseline();
  return learnedBaseline({
    job_id: jobId,
    upload_id: jobId,
    dataset_id: jobId,
    baseline_candidate_id: id,
    established_baseline_id: id,
    portfolio_id: portfolioId,
    system_id: portfolioId,
    filename,
    activation: { state: "active", activated_at: "2026-07-29T00:00:00Z" },
    candidate_model: {
      ...base.candidate_model,
      model_id: id,
      baseline_id: id,
      baseline_candidate_id: id,
      status: "active",
      activation: { state: "active", activated_at: "2026-07-29T00:00:00Z" },
      source: { ...base.candidate_model.source, job_id: jobId, upload_id: jobId, dataset_id: jobId, portfolio_id: portfolioId, system_id: portfolioId, filename },
      telemetry_schema: { numeric_columns: Array.from({ length: signalCount }, (_, index) => `signal-${index}`) },
      relationship_graph: { edges: Array.from({ length: relationshipCount }, (_, index) => ({ edge_id: `edge-${index}` })) },
    },
  });
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.clearAllMocks();
  clearBaselineResultCache();
  vi.useRealTimers();
});

describe("initial baseline experience", () => {
  it("leads with a compact initial-baseline upload workflow", () => {
    const { container } = renderPanel();

    expect(screen.getByRole("heading", { name: "Establish Initial Baseline" })).toBeTruthy();
    expect(screen.getByText("Upload representative historical operating data so Neraium can learn how the system normally behaves.")).toBeTruthy();
    expect(screen.getByText("SOURCE OPERATING HISTORY")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Upload historical data" })).toBeTruthy();
    expect(screen.getByText("CSV, SCADA export, or historian export")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continue" })).toBeTruthy();

    expect(screen.queryByText("This dataset becomes Neraium's first learned operating model.")).toBeNull();
    expect(screen.queryByText(/discovers persistent relationships between signals/i)).toBeNull();
    expect(screen.queryByText(/normal only evolves when new operating behavior/i)).toBeNull();
    expect(screen.queryByText("Supported data sources")).toBeNull();

    const workflow = Array.from(container.querySelectorAll(".baseline-learning-path strong")).map((node) => node.textContent);
    expect(workflow).toEqual([
      "Upload Data",
      "Validate Signals",
      "Learn Relationships",
      "Establish Baseline",
      "Begin Learning",
    ]);
    expect(container.textContent).not.toMatch(/\bEvidence\b|\bFindings\b|\bAlerts\b|\bInvestigation\b|Drift Detection|Anomaly summaries/i);
  });

  it("waits for an empty Continue attempt before showing file validation", () => {
    renderWorkspace();

    expect(screen.queryByText("Choose a telemetry file.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("alert").textContent).toBe("Choose a telemetry file.");
  });

  it("uses one focused baseline action after a dataset is selected", () => {
    const handleUpload = vi.fn((event) => event?.preventDefault?.());
    const openFilePicker = vi.fn();
    renderPanel({
      handleUpload,
      openFilePicker,
      uploadState: "validated",
      selectedFiles: [selectedCsv("operators.csv")],
      selectedFileSize: "15.7 MB",
    });

    expect(screen.getByLabelText("operators.csv, 15.7 MB, Ready")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Analyze New Data" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Extend Baseline" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(handleUpload).toHaveBeenCalledWith(expect.anything(), "create_baseline");
    fireEvent.click(screen.getByRole("button", { name: "Replace file" }));
    expect(openFilePicker).toHaveBeenCalledWith("csv");
  });

  it("opens the file picker from the compact drop zone", () => {
    const openFilePicker = vi.fn();
    renderPanel({ openFilePicker });

    fireEvent.click(screen.getByRole("button", { name: /choose historical dataset/i }));
    expect(openFilePicker).toHaveBeenCalledWith("csv");
  });

  it("keeps comparison datasets in an explicitly separate workflow", () => {
    const handleUpload = vi.fn((event) => event?.preventDefault?.());
    renderPanel({
      workflow: "analyze_new_data",
      handleUpload,
      uploadState: "validated",
      selectedFiles: [selectedCsv("comparison.csv")],
      selectedFileSize: "1.2 MB",
    });

    expect(screen.getByRole("heading", { name: "Import Comparison Dataset" })).toBeTruthy();
    expect(screen.getByText(/does not automatically redefine normal/i)).toBeTruthy();
    expect(screen.queryByText("How Neraium learns")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Evaluate Against Baseline" }));
    expect(handleUpload).toHaveBeenCalledWith(expect.anything(), "analyze_new_data");
  });
});

describe("backend state presentation", () => {
  it.each([
    ["queued", "Upload"],
    ["uploading", "Upload"],
    ["validating_schema", "Validate"],
    ["checking_signal_quality", "Validate"],
    ["mapping_signals", "Validate"],
    ["baseline_relationship_learning", "Learn"],
    ["baseline_model_fitting", "Learn"],
    ["baseline_candidate_persistence", "Learn"],
  ])("maps %s into %s without changing the backend state", (processingState, label) => {
    const stage = resolveBaselineProcessingStage({
      viewState: processingState === "uploading" ? "uploading" : "processing",
      uploadJob: { processing_state: processingState },
      uploadState: processingState,
      uploadTransfer: null,
    });
    expect(stage.label).toBe(label);
  });

  it("shows the four concise stages as a single progress indicator", () => {
    const { container } = renderPanel({
      uploadState: "running_sii",
      selectedFiles: [selectedCsv("learning.csv")],
      uploadJob: {
        job_id: "learning-job",
        status: "PROCESSING",
        processing_state: "baseline_relationship_learning",
        propagation_stage: "baseline_relationship_learning",
        percent: 78,
      },
    });

    expect(screen.getByLabelText("Initial baseline processing: Learn")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Learn, stage 3 of 4" })).toBeTruthy();
    expect(screen.getByText("Securely transferring historical operating data.")).toBeTruthy();
    expect(screen.getByText("Verifying dataset integrity, timestamps, signal consistency, and data quality.")).toBeTruthy();
    expect(screen.getAllByText(/identifying persistent operating relationships across the dataset/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Initial operating model successfully established.")).toBeTruthy();
    expect(container.querySelectorAll('[role="progressbar"]')).toHaveLength(1);
    expect(container.querySelector(".baseline-learning-path")).toBeNull();
    expect(container.querySelector(".baseline-learning-visual")).toBeTruthy();
  });

  it("keeps final persistence in Learn until the backend reports completion", () => {
    renderPanel({
      uploadState: "saving_results",
      selectedFiles: [selectedCsv("saving.csv")],
      uploadJob: { processing_state: "saving_result", percent: 100 },
    });

    expect(screen.getByLabelText("Initial baseline processing: Learn")).toBeTruthy();
    expect(screen.queryByText("Initial Baseline Established")).toBeNull();
  });

  it("shows queued work as Upload", () => {
    renderPanel({
      uploadState: "queued",
      selectedFiles: [selectedCsv("queued.csv")],
      uploadJob: { status: "QUEUED", worker_state: "starting" },
    });

    expect(screen.getByLabelText("Initial baseline processing: Upload")).toBeTruthy();
  });
});

describe("completion and recovery", () => {
  it("replaces processing with a stable initial-baseline success experience", () => {
    const onOpenBaseline = vi.fn();
    const onImportComparisonDataset = vi.fn();
    const result = learnedBaseline();
    const { container } = renderPanel({
      uploadState: "complete",
      selectedFiles: [selectedCsv()],
      selectedFileSize: "8.4 MB",
      baselineResult: result,
      uploadJob: { job_id: "baseline-job", status: "COMPLETE", workflow: "create_baseline" },
      onOpenBaseline,
      onImportComparisonDataset,
    });

    expect(screen.getByRole("heading", { name: "Initial Baseline Established" })).toBeTruthy();
    expect(screen.getByText("Jun 1, 2026, 12:00 AM – Jun 30, 2026, 11:55 PM UTC")).toBeTruthy();
    expect(screen.getByText("Signals analyzed").closest("div").textContent).toContain("4");
    expect(screen.getByText("Relationships learned").closest("div").textContent).toContain("3");
    expect(screen.getByText("Data quality").closest("div").textContent).toContain("Strong · 94/100");
    expect(screen.getByText("Learning confidence").closest("div").textContent).toContain("91/100");
    expect(screen.getByText(/foundation for continuous learning/i)).toBeTruthy();
    expect(screen.getByText(/preserving enough historical context/i)).toBeTruthy();
    expect(container.querySelector(".baseline-learning-visual.is-complete")).toBeTruthy();
    expect(container.querySelector('[role="progressbar"]')).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Open Baseline" }));
    fireEvent.click(screen.getByRole("button", { name: "Import Comparison Dataset" }));
    expect(onOpenBaseline).toHaveBeenCalledTimes(1);
    expect(onImportComparisonDataset).toHaveBeenCalledTimes(1);
  });

  it("derives the requested baseline summary from the real candidate contract", () => {
    const rows = baselineCompletionSummary({
      result: learnedBaseline(),
      analysisResult: null,
      uploadJob: null,
      selectedFileLabel: "fallback.csv",
    });
    expect(Object.fromEntries(rows.map((row) => [row.label, row.value]))).toMatchObject({
      Dataset: "plant-history.csv",
      "Signals analyzed": "4",
      "Relationships learned": "3",
      "Data quality": "Strong · 94/100",
      "Learning confidence": "91/100",
    });
  });

  it("provides actionable recovery without exposing raw service responses", () => {
    const onRetryFailedUploads = vi.fn();
    renderPanel({
      uploadState: "error",
      selectedFiles: [selectedCsv("bad.csv")],
      selectedFileSize: "3.2 MB",
      latestMessage: "The timestamp column could not be parsed.",
      uploadJob: { job_id: "failed-job", processing_state: "failed" },
      onRetryFailedUploads,
    });

    expect(screen.getByRole("heading", { name: "Unexpected server error" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Choose Another File" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry Import" }));
    expect(onRetryFailedUploads).toHaveBeenCalledTimes(1);
  });

  it("shows a completed transfer with only Import Dataset failed", () => {
    const onRetryFailedUploads = vi.fn();
    renderPanel({
      uploadState: "error",
      selectedFiles: [selectedCsv("mobile-production.csv")],
      selectedFileSize: "369.7 KB",
      latestMessage: "The file was transferred successfully, but Neraium could not begin processing it.",
      uploadTransfer: {
        stage: "upload_transferred",
        loaded: 378573,
        total: 378573,
        percent: 100,
        label: "Transfer complete · 369.7 KB of 369.7 KB",
      },
      uploadJob: {
        job_id: "stored-mobile-upload",
        processing_state: "failed",
        error_code: "dataset_record_creation_failed",
        failed_stage: "dataset_creation",
        transfer_succeeded: true,
        file_stored: true,
        retryable: true,
      },
      onRetryFailedUploads,
    });

    expect(screen.getByRole("heading", { name: "Dataset import failed" })).toBeTruthy();
    expect(screen.getAllByText("The file was transferred successfully, but Neraium could not begin processing it.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Transfer complete · 369.7 KB of 369.7 KB").length).toBeGreaterThan(0);
    const workflowStatus = within(screen.getByRole("list", { name: "Import workflow status" }));
    expect(workflowStatus.getByText("Import Dataset").closest("li").textContent).toContain("Failed");
    for (const label of ["Validate Signals", "Learn Relationships", "Establish Baseline", "Begin Learning"]) {
      expect(workflowStatus.getByText(label).closest("li").textContent).toContain("Not started");
    }
    fireEvent.click(screen.getByRole("button", { name: "Retry Import" }));
    expect(onRetryFailedUploads).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Choose Another File" })).toBeTruthy();
  });

  it("marks only the failed stage and leaves downstream work not started", () => {
    expect(failedImportStageRows({ failed_stage: "dataset_creation" }).map(({ label, status }) => [label, status])).toEqual([
      ["Import Dataset", "Failed"],
      ["Validate Signals", "Not started"],
      ["Learn Relationships", "Not started"],
      ["Establish Baseline", "Not started"],
      ["Begin Learning", "Not started"],
    ]);
    expect(failedImportStageRows({ failed_stage: "csv_parsing" }).map(({ status }) => status)).toEqual([
      "Complete",
      "Failed",
      "Not started",
      "Not started",
      "Not started",
    ]);
  });

  it("does not leak stale complete progress into a new idle selection", () => {
    const { container } = renderPanel({
      uploadState: "idle",
      selectedFiles: [],
      uploadJob: { job_id: "old-job", status: "complete", percent: 100, processing_state: "complete" },
    });
    expect(container.querySelector('[role="progressbar"]')).toBeNull();
    expect(screen.queryByText("Initial Baseline Established")).toBeNull();
  });
});

describe("exact baseline selection regression", () => {
  it("opens the selected baseline from cache without a completed job object", () => {
    persistBaselineSelection({ baselineId: "bdm-v4-04f9195e", portfolioId: "default", stateSource: "completion_response" });
    const identity = resolveOpenBaselineIdentity({ uploadJob: null, uploadResult: null, latestUploadResult: null, latestUploadSnapshot: null });

    expect(identity).toEqual(expect.objectContaining({
      baselineId: "bdm-v4-04f9195e",
      portfolioId: "default",
      stateSource: "cache",
    }));
    expect(identity.jobId).toBeNull();
    expect(identity.datasetId).toBeNull();
  });

  it("shows a route-specific not-found error", async () => {
    const apiFetch = vi.fn(async () => jsonResponse({ detail: "Baseline was not found." }, { ok: false, status: 404 }));
    renderWorkspace({ apiFetch, selectedBaselineIdentity: { portfolioId: "default", baselineId: "missing-baseline" } });

    expect(await screen.findByRole("heading", { name: "Baseline Not Found" })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Baseline missing-baseline was not found in portfolio default.");
  });

  it("keeps completed baseline A authoritative when a stale baseline B hydration arrives", async () => {
    const baselineA = namedBaseline({ id: "baseline-a", jobId: "job-a", filename: "resort chw baseline.csv", signalCount: 27, relationshipCount: 200 });
    const baselineB = namedBaseline({ id: "baseline-b", jobId: "job-b", filename: "commercial water system.csv", signalCount: 31, relationshipCount: 169 });
    uploadTelemetryFileWithProgress.mockResolvedValue({
      ok: true,
      status: 202,
      payload: { job_id: "job-a", dataset_id: "job-a", upload_id: "job-a", workflow: "create_baseline", status: "PENDING", status_url: "/api/data/upload-status/job-a", baseline_result_url: "/api/data/baselines/jobs/job-a" },
    });
    const apiFetch = vi.fn(async (path) => {
      if (String(path).includes("/upload-status/")) return jsonResponse({ job_id: "job-a", dataset_id: "job-a", upload_id: "job-a", workflow: "create_baseline", job_state: "completed", status: "COMPLETE", processing_state: "complete", baseline_result_url: "/api/data/baselines/jobs/job-a" });
      if (String(path).includes("/baselines/jobs/job-a")) return jsonResponse(baselineA);
      if (String(path).includes("/baselines/baseline-a")) return jsonResponse(baselineA);
      return jsonResponse({});
    });
    const onOpenBaseline = vi.fn(() => true);
    const props = { apiFetch, latestUploadResult: baselineB, onOpenBaseline };
    const { rerender } = renderWorkspace(props);

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv("resort chw baseline.csv")] } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("resort chw baseline.csv")).toBeTruthy();
    expect(screen.getByText("27")).toBeTruthy();
    expect(screen.getByText("200")).toBeTruthy();
    rerender(workspaceElement({ ...props, latestUploadResult: baselineB }));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(screen.getByText("resort chw baseline.csv")).toBeTruthy();
    expect(screen.queryByText("commercial water system.csv")).toBeNull();
    expect(onOpenBaseline).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Open Baseline" }));
    expect(onOpenBaseline).toHaveBeenCalledWith(expect.objectContaining({ jobId: "job-a", datasetId: "job-a", baselineId: "baseline-a", portfolioId: "default" }));

    fireEvent.click(screen.getByText("Processing details"));
    expect(screen.getByText("Selected baseline ID")).toBeTruthy();
    expect(screen.getByText("baseline-a")).toBeTruthy();
    expect(screen.getByText("completion response")).toBeTruthy();
  });

  it("restores the exact baseline route and scopes the request by portfolio", async () => {
    const baselineA = namedBaseline({ id: "baseline-a", jobId: "job-a", filename: "resort chw baseline.csv", portfolioId: "resort-portfolio" });
    const apiFetch = vi.fn(async (path) => String(path).endsWith("/baselines/baseline-a") ? jsonResponse(baselineA) : jsonResponse({}));
    renderWorkspace({ apiFetch, selectedBaselineIdentity: { portfolioId: "resort-portfolio", baselineId: "baseline-a" } });

    expect(await screen.findByText("resort chw baseline.csv")).toBeTruthy();
    expect(apiFetch).toHaveBeenCalledWith(
      "/api/data/baselines/baseline-a",
      expect.objectContaining({ headers: { "X-Neraium-Workspace-Id": "resort-portfolio" } }),
    );
  });

  it("ignores an older exact hydration response after baseline B is selected", async () => {
    const baselineA = namedBaseline({ id: "baseline-a", jobId: "job-a", filename: "baseline A.csv" });
    const baselineB = namedBaseline({ id: "baseline-b", jobId: "job-b", filename: "baseline B.csv" });
    let resolveA;
    const delayedA = new Promise((resolve) => { resolveA = () => resolve(jsonResponse(baselineA)); });
    const apiFetch = vi.fn(async (path) => {
      if (String(path).endsWith("/baselines/baseline-a")) return delayedA;
      if (String(path).endsWith("/baselines/baseline-b")) return jsonResponse(baselineB);
      return jsonResponse({});
    });
    const common = { apiFetch };
    const { rerender } = renderWorkspace({ ...common, selectedBaselineIdentity: { portfolioId: "default", baselineId: "baseline-a" } });
    rerender(workspaceElement({ ...common, selectedBaselineIdentity: { portfolioId: "default", baselineId: "baseline-b" } }));

    expect(await screen.findByText("baseline B.csv")).toBeTruthy();
    resolveA();
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(screen.getByText("baseline B.csv")).toBeTruthy();
    expect(screen.queryByText("baseline A.csv")).toBeNull();
  });
});

describe("upload and polling behavior", () => {
  it("hydrates a baseline result and stops polling after the terminal state", async () => {
    uploadTelemetryFileWithProgress.mockResolvedValue({
      ok: true,
      status: 202,
      payload: {
        job_id: "baseline-job",
        dataset_id: "baseline-job",
        workflow: "create_baseline",
        status: "PENDING",
        status_url: "/api/data/upload-status/baseline-job",
        baseline_result_url: "/api/data/baselines/jobs/baseline-job",
      },
    });
    let statusCalls = 0;
    const apiFetch = vi.fn(async (path) => {
      if (String(path).includes("/upload-status/")) {
        statusCalls += 1;
        return jsonResponse({
          job_id: "baseline-job",
          dataset_id: "baseline-job",
          workflow: "create_baseline",
          job_state: "completed",
          status: "COMPLETE",
          processing_state: "complete",
          baseline_result_url: "/api/data/baselines/jobs/baseline-job",
        });
      }
      if (String(path).includes("/baselines/jobs/")) return jsonResponse(learnedBaseline());
      return jsonResponse({});
    });
    const onUploadComplete = vi.fn();
    renderWorkspace({ apiFetch, onUploadComplete });

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv()] } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("heading", { name: "Initial Baseline Established" })).toBeTruthy();
    await new Promise((resolve) => window.setTimeout(resolve, 30));
    expect(statusCalls).toBe(1);
    expect(onUploadComplete).not.toHaveBeenCalled();
  });

  it("resumes an existing processing job after reload", async () => {
    let statusCalls = 0;
    const apiFetch = vi.fn(async (path) => {
      if (String(path).includes("/upload-status/resume-job")) {
        statusCalls += 1;
        return jsonResponse({
          job_id: "resume-job",
          dataset_id: "resume-job",
          workflow: "create_baseline",
          job_state: "completed",
          status: "COMPLETE",
          processing_state: "complete",
          baseline_result_url: "/api/data/baselines/jobs/resume-job",
        });
      }
      if (String(path).includes("/baselines/jobs/resume-job")) {
        return jsonResponse(learnedBaseline({ job_id: "resume-job", dataset_id: "resume-job" }));
      }
      return jsonResponse({});
    });

    renderWorkspace({
      apiFetch,
      hasActiveSession: true,
      hasResumedSession: true,
      sessionStore: {
        jobId: "resume-job",
        uiState: "processing",
        latestUploadSnapshot: {
          job_id: "resume-job",
          workflow: "create_baseline",
          status: "PROCESSING",
          processing_state: "baseline_relationship_learning",
          status_url: "/api/data/upload-status/resume-job",
        },
        latestUploadResult: null,
      },
    });

    expect(await screen.findByRole("heading", { name: "Initial Baseline Established" })).toBeTruthy();
    expect(statusCalls).toBe(1);
  });

  it("restores a processing job from local storage when server hydration is not ready", async () => {
    window.localStorage.setItem("neraium.last_upload_job_id", "stored-resume-job");
    let statusCalls = 0;
    const apiFetch = vi.fn(async (path) => {
      if (String(path).includes("/upload-status/stored-resume-job")) {
        statusCalls += 1;
        return jsonResponse({
          job_id: "stored-resume-job",
          dataset_id: "stored-resume-job",
          workflow: "create_baseline",
          status: "COMPLETE",
          processing_state: "complete",
          baseline_result_url: "/api/data/baselines/jobs/stored-resume-job",
        });
      }
      if (String(path).includes("/baselines/jobs/stored-resume-job")) {
        return jsonResponse(learnedBaseline({ job_id: "stored-resume-job", dataset_id: "stored-resume-job" }));
      }
      return jsonResponse({});
    });

    renderWorkspace({ apiFetch });

    expect(await screen.findByRole("heading", { name: "Initial Baseline Established" })).toBeTruthy();
    expect(statusCalls).toBe(1);
  });

  it("approves a controlled baseline before opening it", async () => {
    const result = learnedBaseline();
    const onOpenBaseline = vi.fn();
    const apiFetch = vi.fn(async (path) => {
      if (String(path).includes("/approve")) {
        return jsonResponse({
          active_model: {
            ...result.candidate_model,
            status: "active",
            activation: { state: "active", activated_at: "2026-07-28T00:00:00Z" },
          },
        });
      }
      return jsonResponse({});
    });
    renderWorkspace({
      apiFetch,
      onOpenBaseline,
      hasActiveSession: true,
      hasResumedSession: true,
      latestUploadResult: result,
      sessionStore: {
        jobId: "baseline-job",
        uiState: "verified",
        latestUploadSnapshot: result,
        latestUploadResult: result,
      },
    });

    fireEvent.click(await screen.findByRole("button", { name: "Open Baseline" }));
    await waitFor(() => expect(onOpenBaseline).toHaveBeenCalledTimes(1));
    expect(apiFetch).toHaveBeenCalledWith(
      "/api/data/baselines/candidates/bdm-v1-baseline/approve",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("prevents duplicate baseline navigation from rapid activation", async () => {
    const result = learnedBaseline();
    result.activation = { state: "active" };
    result.candidate_model = { ...result.candidate_model, status: "active", activation: { state: "active" } };
    let finishNavigation;
    const onOpenBaseline = vi.fn(() => new Promise((resolve) => { finishNavigation = resolve; }));
    renderWorkspace({
      onOpenBaseline,
      hasActiveSession: true,
      hasResumedSession: true,
      latestUploadResult: result,
      sessionStore: {
        jobId: "baseline-job",
        uiState: "verified",
        latestUploadSnapshot: result,
        latestUploadResult: result,
      },
    });

    const button = await screen.findByRole("button", { name: "Open Baseline" });
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(onOpenBaseline).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "Opening Baseline…" }).disabled).toBe(true);
    finishNavigation(true);
    await waitFor(() => expect(screen.getByRole("button", { name: "Open Baseline" }).disabled).toBe(false));
  });

  it("shows a visible error when the router rejects navigation", async () => {
    const result = learnedBaseline();
    result.activation = { state: "active" };
    result.candidate_model = { ...result.candidate_model, status: "active", activation: { state: "active" } };
    renderWorkspace({
      onOpenBaseline: vi.fn(() => false),
      hasActiveSession: true,
      hasResumedSession: true,
      latestUploadResult: result,
      sessionStore: {
        jobId: "baseline-job",
        uiState: "verified",
        latestUploadSnapshot: result,
        latestUploadResult: result,
      },
    });

    fireEvent.click(await screen.findByRole("button", { name: "Open Baseline" }));
    expect(await screen.findByRole("heading", { name: "Baseline Saved, Workspace Not Opened" })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Baseline bdm-v1-baseline could not be opened. Please retry.");
  });

  it("does not substitute a job or dataset ID when the baseline ID is missing", async () => {
    const result = learnedBaseline();
    delete result.established_baseline_id;
    delete result.baseline_candidate_id;
    result.activation = { state: "active" };
    result.candidate_model = { ...result.candidate_model, model_id: null, baseline_id: null, baseline_candidate_id: null, status: "active", activation: { state: "active" } };
    renderWorkspace({
      onOpenBaseline: vi.fn(() => true),
      hasActiveSession: true,
      hasResumedSession: true,
      latestUploadResult: result,
      sessionStore: {
        jobId: "baseline-job",
        uiState: "verified",
        latestUploadSnapshot: result,
        latestUploadResult: result,
      },
    });

    fireEvent.click(await screen.findByRole("button", { name: "Open Baseline" }));
    expect(await screen.findByRole("heading", { name: "Baseline Saved, Workspace Not Opened" })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("baseline ID is unavailable");
  });

  it("moves the completed page into a separate comparison workflow without resetting the baseline", async () => {
    const result = learnedBaseline();
    renderWorkspace({
      hasActiveSession: true,
      hasResumedSession: true,
      latestUploadResult: result,
      sessionStore: {
        jobId: "baseline-job",
        uiState: "verified",
        latestUploadSnapshot: result,
        latestUploadResult: result,
      },
    });

    fireEvent.click(await screen.findByRole("button", { name: "Import Comparison Dataset" }));
    expect(screen.getByRole("heading", { name: "Import Comparison Dataset" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Initial Baseline Established" })).toBeNull();
  });

  it("shows a clean service failure and keeps retry available", async () => {
    const error = new Error("<html>503</html>");
    error.name = "UploadRequestError";
    error.status = 503;
    error.phase = "upload";
    error.errorType = "service_unavailable";
    error.payload = {
      status: "FAILED",
      processing_state: "failed",
      error_type: "service_unavailable",
      message: "<html>503</html>",
      response_status: 503,
      html_response: true,
    };
    uploadTelemetryFileWithProgress.mockRejectedValue(error);
    renderWorkspace();

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv("unavailable.csv")] } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(SERVICE_UNAVAILABLE_UPLOAD_MESSAGE);
    expect(alert.textContent).not.toContain("<html>");
    expect(screen.getByRole("button", { name: "Retry Import" })).toBeTruthy();
  });

  it("rejects a CSV above the supported upload limit before submission", () => {
    renderWorkspace();
    const tooLarge = selectedCsv("too-large.csv");
    Object.defineProperty(tooLarge, "size", { value: 512 * 1024 * 1024 + 1 });

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [tooLarge] } });

    expect(screen.getByRole("alert").textContent).toBe("File is larger than the supported upload limit of 512.0 MB.");
    expect(screen.getByRole("button", { name: "Continue" }).disabled).toBe(true);
    expect(uploadTelemetryFileWithProgress).not.toHaveBeenCalled();
  });
});

describe("status utilities", () => {
  it("measures backend-stage-to-frontend polling latency", () => {
    const receivedAt = Date.parse("2026-07-26T10:00:02.000Z");
    const timing = frontendPollingTiming({
      stage_changed_at: "2026-07-26T10:00:00.800Z",
      status_server_sent_at: "2026-07-26T10:00:01.950Z",
    }, receivedAt - 180, receivedAt);
    expect(timing.poll_request_ms).toBe(180);
    expect(timing.frontend_polling_latency_ms).toBe(1200);
    expect(timing.status_transport_latency_ms).toBe(50);
  });

  it("keeps worker diagnostics available as secondary detail", () => {
    const now = Date.parse("2026-07-22T21:30:01.070Z");
    expect(queuedWorkerMessage({ worker_state: "starting" }, now)).toBe("Preparing analysis resources");
    expect(queuedWorkerMessage({ worker_state: "active", worker_last_update_at: "2026-07-22T21:28:01.070289+00:00" }, now)).toBe("Analysis active · updated 2 minutes ago");
    expect(formatAnalysisUpdateTime("2026-07-22T19:30:01Z", now)).toBe("2 hours ago");
  });
});
