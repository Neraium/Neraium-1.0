/* @vitest-environment jsdom */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DataConnectionsWorkspace, { formatAnalysisUpdateTime, frontendPollingTiming, queuedWorkerMessage, resolveOpenBaselineIdentity } from "./DataConnectionsWorkspace";
import IntakeFlowPanel, { baselineCompletionSummary, failedImportStageRows, resolveBaselineProcessingStage } from "./setup/IntakeFlowPanel";
import { retryUploadAnalysisJob, uploadTelemetryFileWithProgress } from "../services/api/uploadApi";
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
    dataset_id: "baseline-dataset",
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
      source: { job_id: "baseline-job", upload_id: "baseline-job", dataset_id: "baseline-dataset", portfolio_id: "default", system_id: "default", filename: "plant-history.csv", row_count: 2400 },
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

function backendProgress(overrides = {}) {
  return {
    contract_version: "job-progress.v1",
    job_id: "progress-job",
    workflow: "create_baseline",
    status: "processing",
    stage: "validate",
    substage: "signal_inventory",
    completed_units: 6,
    total_units: 10,
    percent_complete: 60,
    unit_type: "signals",
    message: "Profiling signal inventory.",
    started_at: "2026-08-08T12:00:00Z",
    updated_at: "2026-08-08T12:00:10Z",
    elapsed_seconds: 10,
    last_worker_heartbeat_at: "2026-08-08T12:00:10Z",
    seconds_since_worker_heartbeat: 0,
    seconds_since_update: 0,
    stalled: false,
    retryable: null,
    error: null,
    metadata: {},
    workflow_steps: [
      { id: "upload", label: "Upload", status: "completed", completed_work_units: 2, total_work_units: 2, percent_complete: 100 },
      { id: "validate", label: "Validate", status: "processing", completed_work_units: 4, total_work_units: 11, percent_complete: 42 },
      { id: "learn", label: "Learn", status: "pending", completed_work_units: 0, total_work_units: 6, percent_complete: 0 },
      { id: "ready", label: "Baseline Ready", status: "pending", completed_work_units: 0, total_work_units: 1, percent_complete: 0 },
    ],
    operations: [
      { id: "receiving", stage: "upload", label: "Receiving file", status: "completed", percent_complete: 100 },
      { id: "parse_source", stage: "validate", label: "Parse source", status: "completed", percent_complete: 100 },
      { id: "signal_inventory", stage: "validate", label: "Signal inventory", status: "processing", completed_units: 6, total_units: 10, percent_complete: 60 },
      { id: "semantic_mapping", stage: "validate", label: "Semantic mapping", status: "pending", percent_complete: null },
      { id: "learn_relationships", stage: "learn", label: "Learn relationships", status: "pending", percent_complete: null },
    ],
    overall_percent_complete: 32,
    overall_basis: "equal_completed_declared_substages",
    ...overrides,
  };
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
    dataset_id: `${jobId}-dataset`,
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
      source: { ...base.candidate_model.source, job_id: jobId, upload_id: jobId, dataset_id: `${jobId}-dataset`, portfolio_id: portfolioId, system_id: portfolioId, filename },
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
    expect(container.querySelector(".baseline-learning-visual")).toBeNull();
  });

  it("keeps final persistence in Learn until the backend reports completion", () => {
    renderPanel({
      uploadState: "saving_results",
      selectedFiles: [selectedCsv("saving.csv")],
      uploadJob: { processing_state: "saving_result", percent: 100 },
    });

    expect(screen.getByLabelText("Initial baseline processing: Learn")).toBeTruthy();
    expect(screen.queryByText("Baseline Established")).toBeNull();
  });

  it("shows queued work as Upload", () => {
    renderPanel({
      uploadState: "queued",
      selectedFiles: [selectedCsv("queued.csv")],
      uploadJob: { status: "QUEUED", worker_state: "starting" },
    });

    expect(screen.getByLabelText("Initial baseline processing: Upload")).toBeTruthy();
  });

  it("shows measured file-transfer progress before a backend job exists", () => {
    renderPanel({
      uploadState: "uploading",
      selectedFiles: [selectedCsv("transfer.csv")],
      uploadTransfer: {
        percent: 25,
        loaded: 256,
        total: 1024,
        label: "Sending telemetry 256 B of 1 KB",
      },
    });

    const transfer = within(screen.getByLabelText("File transfer progress"));
    expect(transfer.getByRole("progressbar", { name: "File transfer" }).value).toBe(25);
    expect(transfer.getByText("Sending telemetry 256 B of 1 KB")).toBeTruthy();
  });

  it("renders exact backend units and progress semantics", () => {
    renderPanel({
      uploadState: "running_sii",
      selectedFiles: [selectedCsv("measurable.csv")],
      uploadJob: {
        job_id: "progress-job",
        execution_state: "processing",
        job_progress: backendProgress(),
      },
    });

    const progress = within(screen.getByLabelText("Backend job progress"));
    expect(progress.getByRole("status").textContent).toContain("Processing");
    expect(progress.getByRole("progressbar", { name: "Overall backend workflow" }).getAttribute("aria-valuenow")).toBe("32");
    expect(progress.getByRole("progressbar", { name: "Signal inventory" }).getAttribute("aria-valuenow")).toBe("60");
    expect(progress.getByText("6 / 10 signals")).toBeTruthy();
    expect(progress.getByRole("list", { name: "Overall workflow steps" }).textContent).toContain("42% · processing");
    expect(progress.getByRole("list", { name: "Detailed backend operations" }).textContent).toContain("Semantic mappingPending");
  });

  it("uses the named operation projection consistently for relationship-pair progress", () => {
    const { container } = renderPanel({
      selectedFiles: [selectedCsv()],
      uploadState: "processing",
      uploadJob: {
        job_id: "progress-job",
        status: "PROCESSING",
        execution_state: "processing",
        job_progress: backendProgress({
          stage: "learn",
          substage: "learn_relationships",
          completed_units: 100,
          total_units: 1_710,
          percent_complete: 5,
          unit_type: "relationship_pairs",
          overall_percent_complete: 83,
          workflow_steps: [
            { id: "upload", label: "Upload", status: "completed", completed_work_units: 2, total_work_units: 2, percent_complete: 100 },
            { id: "validate", label: "Validate", status: "completed", completed_work_units: 13, total_work_units: 13, percent_complete: 100 },
            { id: "learn", label: "Learn", status: "processing", completed_work_units: 3, total_work_units: 6, percent_complete: 57 },
            { id: "ready", label: "Baseline Ready", status: "pending", completed_work_units: 0, total_work_units: 1, percent_complete: 0 },
          ],
          operations: [
            { id: "receiving", stage: "upload", label: "Receiving file", status: "completed", percent_complete: 100 },
            { id: "parse_source", stage: "validate", label: "Parse source", status: "completed", percent_complete: 100 },
            {
              id: "learn_relationships",
              stage: "learn",
              label: "Learn relationships",
              status: "processing",
              completed_units: 775,
              total_units: 1_710,
              percent_complete: 45,
              unit_type: "relationship_pairs",
            },
          ],
        }),
      },
    });

    const progress = within(screen.getByLabelText("Backend job progress"));
    expect(progress.getByRole("progressbar", { name: "Overall backend workflow" }).getAttribute("aria-valuenow")).toBe("83");
    expect(progress.getByRole("progressbar", { name: "Learn relationships" }).getAttribute("aria-valuenow")).toBe("45");
    expect(progress.getByText("775 / 1,710 relationship pairs")).toBeTruthy();
    expect(progress.getByRole("list", { name: "Overall workflow steps" }).textContent).toContain("Learn57% · processing");
    expect(progress.getByRole("list", { name: "Detailed backend operations" }).textContent).toContain("Learn relationships45% · Processing");
    expect(container.textContent).not.toContain("100 / 1,710 relationship pairs");
  });

  it("keeps unknown totals indeterminate without generating a percentage", () => {
    renderPanel({
      uploadState: "running_sii",
      selectedFiles: [selectedCsv("indeterminate.csv")],
      uploadJob: {
        job_id: "indeterminate-job",
        execution_state: "processing",
        job_progress: backendProgress({
          substage: "parse_source",
          completed_units: 5_000,
          total_units: null,
          percent_complete: null,
          unit_type: "rows",
          message: "Parsed 5,000 rows; discovering the source total.",
          operations: [
            { id: "receiving", stage: "upload", label: "Receiving file", status: "completed", percent_complete: 100 },
            { id: "parse_source", stage: "validate", label: "Parse source", status: "processing", completed_units: 5_000, total_units: null, percent_complete: null },
            { id: "semantic_mapping", stage: "validate", label: "Semantic mapping", status: "pending", percent_complete: null },
          ],
        }),
      },
    });

    const progress = within(screen.getByLabelText("Backend job progress"));
    expect(progress.getByText("Measuring work")).toBeTruthy();
    expect(progress.getByText("5,000 rows processed")).toBeTruthy();
    expect(progress.queryByRole("progressbar", { name: "Parse source" })).toBeNull();
    expect(progress.getByText("The backend has not established a safe total for this operation.")).toBeTruthy();
  });

  it("distinguishes stalled worker visibility from a failed job", () => {
    renderPanel({
      uploadState: "running_sii",
      selectedFiles: [selectedCsv("stalled.csv")],
      uploadJob: {
        job_id: "stalled-job",
        execution_state: "waiting",
        job_progress: backendProgress({
          stalled: true,
          seconds_since_update: 185,
          visibility_message: "No progress update received for 3 minute(s).",
        }),
      },
    });

    const progress = within(screen.getByLabelText("Backend job progress"));
    expect(progress.getByRole("status").textContent).toContain("Waiting for worker progress");
    expect(progress.getByText("No progress update received for 3 minute(s).")).toBeTruthy();
    expect(progress.queryByText("Failed")).toBeNull();
  });

  it("shows status-connection recovery while preserving the latest backend counters", () => {
    renderPanel({
      uploadState: "running_sii",
      selectedFiles: [selectedCsv("recovering.csv")],
      uploadJob: {
        job_id: "recovering-job",
        execution_state: "processing",
        poll_connection_state: "retrying",
        message: "Analysis status connection interrupted. Retrying.",
        job_progress: backendProgress(),
      },
    });

    const progress = within(screen.getByLabelText("Backend job progress"));
    expect(progress.getByRole("status").textContent).toContain("Retrying status connection");
    expect(progress.getByText("Analysis status connection interrupted. Retrying.")).toBeTruthy();
    expect(progress.getByText("6 / 10 signals")).toBeTruthy();
  });
});

describe("completion and recovery", () => {
  it("replaces processing with a stable initial-baseline success experience", () => {
    const onImportComparisonDataset = vi.fn();
    const onReturnToPortfolio = vi.fn();
    const result = learnedBaseline();
    const { container } = renderPanel({
      uploadState: "complete",
      selectedFiles: [selectedCsv()],
      selectedFileSize: "8.4 MB",
      baselineResult: result,
      uploadJob: { job_id: "baseline-job", status: "COMPLETE", workflow: "create_baseline" },
      onImportComparisonDataset,
      onReturnToPortfolio,
    });

    expect(screen.getByRole("heading", { name: "Baseline Established" })).toBeTruthy();
    expect(screen.getByText("Jun 1, 2026, 12:00 AM – Jun 30, 2026, 11:55 PM UTC")).toBeTruthy();
    expect(screen.getByText("Signals analyzed").closest("div").textContent).toContain("4");
    expect(screen.getByText("Relationships learned").closest("div").textContent).toContain("3");
    expect(screen.getByText("Data quality").closest("div").textContent).toContain("Strong · 94/100");
    expect(screen.getByText("Learning confidence").closest("div").textContent).toContain("91/100");
    expect(screen.getByText("Neraium has learned the system’s normal operating relationships. Upload a later operating dataset to compare against this baseline.")).toBeTruthy();
    expect(container.querySelector(".baseline-learning-visual.is-complete")).toBeTruthy();
    expect(container.querySelector('[role="progressbar"]')).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Upload Comparison Dataset" }));
    fireEvent.click(screen.getByRole("button", { name: "Return to Portfolio" }));
    expect(onImportComparisonDataset).toHaveBeenCalledTimes(1);
    expect(onReturnToPortfolio).toHaveBeenCalledTimes(1);
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

    expect(screen.getByRole("heading", { name: "Processing failed during: Processing" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Choose Another File" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry Processing" }));
    expect(onRetryFailedUploads).toHaveBeenCalledTimes(1);
  });

  it("preserves completed operation detail when a backend stage fails", () => {
    renderPanel({
      uploadState: "error",
      selectedFiles: [selectedCsv("failed-progress.csv")],
      latestMessage: "Signal mapping could not continue.",
      uploadJob: {
        job_id: "failed-progress-job",
        processing_state: "failed",
        execution_state: "failed",
        retryable: true,
        job_progress: backendProgress({
          status: "failed",
          substage: "semantic_mapping",
          completed_units: 4,
          total_units: 10,
          percent_complete: 40,
          retryable: true,
          error: "Signal mapping could not continue.",
          message: "Signal mapping could not continue.",
          operations: [
            { id: "receiving", stage: "upload", label: "Receiving file", status: "completed", percent_complete: 100 },
            { id: "parse_source", stage: "validate", label: "Parse source", status: "completed", percent_complete: 100 },
            { id: "semantic_mapping", stage: "validate", label: "Semantic mapping", status: "failed", completed_units: 4, total_units: 10, percent_complete: 40 },
            { id: "canonical_dataset_build", stage: "validate", label: "Canonical dataset build", status: "pending", percent_complete: null },
          ],
        }),
      },
    });

    const detail = within(screen.getByLabelText("Detailed backend operations"));
    expect(detail.getByText("Parse source").closest("li").textContent).toContain("Complete");
    expect(detail.getByText("Semantic mapping").closest("li").textContent).toContain("40% · Failed");
    expect(detail.getByText("Canonical dataset build").closest("li").textContent).toContain("Pending");
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
    expect(screen.queryByText("Baseline Established")).toBeNull();
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
      payload: { job_id: "job-a", dataset_id: "job-a-dataset", upload_id: "job-a", workflow: "create_baseline", status: "PENDING", status_url: "/api/data/upload-status/job-a", baseline_result_url: "/api/data/baselines/jobs/job-a" },
    });
    const apiFetch = vi.fn(async (path) => {
      if (String(path).includes("/upload-status/")) return jsonResponse({ job_id: "job-a", dataset_id: "job-a-dataset", upload_id: "job-a", workflow: "create_baseline", job_state: "completed", status: "COMPLETE", processing_state: "complete", result_available: true, baseline_result_available: true, baseline_result_url: "/api/data/baselines/jobs/job-a" });
      if (String(path).includes("/baselines/jobs/job-a")) return jsonResponse(baselineA);
      if (String(path).includes("/baselines/baseline-a")) return jsonResponse(baselineA);
      return jsonResponse({});
    });
    const onOpenBaseline = vi.fn(() => true);
    const props = { apiFetch, latestUploadResult: baselineB, onOpenBaseline, autoOpenBaselineReady: true };
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
    await waitFor(() => expect(onOpenBaseline).toHaveBeenCalledWith(
      expect.objectContaining({ jobId: "job-a", datasetId: "job-a-dataset", baselineId: "baseline-a", portfolioId: "default" }),
      { replace: true },
    ));

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
      "/api/data/portfolios/resort-portfolio/baselines/baseline-a",
      expect.objectContaining({ headers: expect.objectContaining({ "X-Neraium-Workspace-Id": "resort-portfolio" }) }),
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
        dataset_id: "baseline-dataset",
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
          dataset_id: "baseline-dataset",
          workflow: "create_baseline",
          job_state: "completed",
          status: "COMPLETE",
          processing_state: "complete",
          result_available: true,
          baseline_result_available: true,
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

    expect(await screen.findByRole("heading", { name: "Baseline Established" })).toBeTruthy();
    await new Promise((resolve) => window.setTimeout(resolve, 30));
    expect(statusCalls).toBe(1);
    expect(onUploadComplete).not.toHaveBeenCalled();
  });

  it("cleans up an outstanding polling delay when the workspace unmounts", async () => {
    uploadTelemetryFileWithProgress.mockResolvedValue({
      ok: true,
      status: 202,
      payload: {
        job_id: "cleanup-job",
        dataset_id: "cleanup-dataset",
        workflow: "create_baseline",
        status: "PENDING",
        status_url: "/api/data/upload-status/cleanup-job",
      },
    });
    const apiFetch = vi.fn(async () => jsonResponse({
      job_id: "cleanup-job",
      dataset_id: "cleanup-dataset",
      workflow: "create_baseline",
      status: "PROCESSING",
      processing_state: "parsing_telemetry",
      result_available: false,
    }));
    const setTimeoutSpy = vi.spyOn(window, "setTimeout");
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout");
    const { unmount } = renderWorkspace({ apiFetch });

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv("cleanup.csv")] } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    await waitFor(() => expect(setTimeoutSpy.mock.calls.some(([, delay]) => Number(delay) >= 1_000)).toBe(true));
    const pollTimerIndex = setTimeoutSpy.mock.calls.findIndex(([, delay]) => Number(delay) >= 1_000);
    const pollTimer = setTimeoutSpy.mock.results[pollTimerIndex].value;
    unmount();

    expect(clearTimeoutSpy).toHaveBeenCalledWith(pollTimer);
    setTimeoutSpy.mockRestore();
    clearTimeoutSpy.mockRestore();
  });

  it("resumes an existing processing job after reload", async () => {
    let statusCalls = 0;
    const apiFetch = vi.fn(async (path) => {
      if (String(path).includes("/upload-status/resume-job")) {
        statusCalls += 1;
        return jsonResponse({
          job_id: "resume-job",
          dataset_id: "resume-dataset",
          workflow: "create_baseline",
          job_state: "completed",
          status: "COMPLETE",
          processing_state: "complete",
          result_available: true,
          baseline_result_available: true,
          baseline_result_url: "/api/data/baselines/jobs/resume-job",
        });
      }
      if (String(path).includes("/baselines/jobs/resume-job")) {
        return jsonResponse(learnedBaseline({ job_id: "resume-job", dataset_id: "resume-dataset" }));
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

    expect(await screen.findByRole("heading", { name: "Baseline Established" })).toBeTruthy();
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
          dataset_id: "stored-resume-dataset",
          workflow: "create_baseline",
          status: "COMPLETE",
          processing_state: "complete",
          result_available: true,
          baseline_result_available: true,
          baseline_result_url: "/api/data/baselines/jobs/stored-resume-job",
        });
      }
      if (String(path).includes("/baselines/jobs/stored-resume-job")) {
        return jsonResponse(learnedBaseline({ job_id: "stored-resume-job", dataset_id: "stored-resume-dataset" }));
      }
      return jsonResponse({});
    });

    renderWorkspace({ apiFetch });

    expect(await screen.findByRole("heading", { name: "Baseline Established" })).toBeTruthy();
    expect(statusCalls).toBe(1);
  });

  it("reconciles a queued baseline after refresh without trusting cached worker activity or locking new uploads", async () => {
    const pollingStarted = vi.spyOn(console, "info");
    let statusCalls = 0;
    const apiFetch = vi.fn(async (path) => {
      if (String(path).includes("/upload-status/refresh-queued-job")) {
        statusCalls += 1;
        return jsonResponse({
          job_id: "refresh-queued-job",
          dataset_id: "refresh-queued-dataset",
          filename: "production-baseline.csv",
          workflow: "create_baseline",
          status: "PENDING",
          processing_state: "queued",
          execution_state: "queued",
          queue_state: "pending",
          worker_state: "queued",
          worker_claimed: false,
          progress_label: "Baseline construction queued",
          propagation_label: "Baseline construction queued",
        });
      }
      return jsonResponse({});
    });

    renderWorkspace({
      apiFetch,
      hasActiveSession: true,
      hasResumedSession: true,
      sessionStore: {
        jobId: "refresh-queued-job",
        uiState: "processing",
        latestUploadSnapshot: {
          job_id: "refresh-queued-job",
          filename: "cached-file.csv",
          workflow: "create_baseline",
          status: "PENDING",
          processing_state: "queued",
          worker_state: "running",
        },
        latestUploadResult: null,
      },
    });

    expect(await screen.findByText("production-baseline.csv")).toBeTruthy();
    expect(screen.getByTestId("csv-upload-input").files).toHaveLength(0);
    expect(screen.queryByText(/Analysis active/i)).toBeNull();
    expect(within(screen.getByRole("status", { name: "Backend job status" })).getByText("Queued · waiting for worker claim")).toBeTruthy();
    expect(screen.getAllByText("Baseline construction queued").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Start another upload" }).disabled).toBe(false);
    await waitFor(() => expect(statusCalls).toBeGreaterThanOrEqual(2));
    expect(pollingStarted.mock.calls.filter(([message]) => message === "[neraium] telemetry job polling started")).toHaveLength(1);
    expect(uploadTelemetryFileWithProgress).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Start another upload" }));
    expect(screen.getByRole("heading", { name: "Upload historical data" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "production-baseline.csv" })).toBeTruthy();
    expect(screen.getByText("Status:").parentElement.textContent).toContain("Queued");
    expect(screen.getByRole("button", { name: "View active job" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Dismiss job" })).toBeTruthy();
    expect(uploadTelemetryFileWithProgress).not.toHaveBeenCalled();
  });

  it.each([
    ["claimed", "claimed", "Claimed by worker · processing has not started"],
    ["processing", "baseline_relationship_learning", "Analysis active"],
    ["stalled", "baseline_relationship_learning", "Stalled · no recent job heartbeat"],
  ])("restores a %s job from the backend after refresh", async (executionState, processingState, workerMessage) => {
    const jobId = `refresh-${executionState}-job`;
    const apiFetch = vi.fn(async (path) => String(path).includes(`/upload-status/${jobId}`)
      ? jsonResponse({
        job_id: jobId,
        dataset_id: `${jobId}-dataset`,
        filename: `${executionState}.csv`,
        workflow: "create_baseline",
        status: executionState === "claimed" ? "PENDING" : "PROCESSING",
        processing_state: processingState,
        execution_state: executionState,
        queue_state: "processing",
        worker_state: executionState === "processing" ? "running" : executionState,
        worker_claimed: true,
        worker_heartbeat_stale: executionState === "stalled",
        updated_at: "2026-08-08T00:00:00Z",
      })
      : jsonResponse({}));

    renderWorkspace({
      apiFetch,
      sessionStore: {
        jobId,
        uiState: "processing",
        latestUploadSnapshot: { job_id: jobId, status: "PROCESSING" },
        latestUploadResult: null,
      },
    });

    expect(await screen.findByText(`${executionState}.csv`)).toBeTruthy();
    expect(within(screen.getByRole("status", { name: "Backend job status" })).getByText(new RegExp(workerMessage, "i"))).toBeTruthy();
    expect(screen.getByRole("button", { name: "Start another upload" })).toBeTruthy();
    if (executionState !== "processing") expect(screen.queryByText(/Analysis active/i)).toBeNull();
  });

  it("clears a nonexistent remembered job and restores usable upload controls", async () => {
    window.localStorage.setItem("neraium.last_upload_job_id", "deleted-refresh-job");
    const apiFetch = vi.fn(async () => jsonResponse({ detail: "not found" }, { ok: false, status: 404 }));

    renderWorkspace({ apiFetch });

    expect(await screen.findByText("The previous processing job no longer exists. You can start a new upload.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Upload historical data" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continue" }).disabled).toBe(false);
    expect(window.localStorage.getItem("neraium.last_upload_job_id")).toBeNull();
    expect(uploadTelemetryFileWithProgress).not.toHaveBeenCalled();
  });

  it("keeps controls usable and preserves the cached job separately when initial reconciliation is transiently unavailable", async () => {
    const apiFetch = vi.fn(async () => jsonResponse(
      { error_type: "service_unavailable", message: "temporarily unavailable" },
      { ok: false, status: 503 },
    ));

    renderWorkspace({
      apiFetch,
      sessionStore: {
        jobId: "transient-refresh-job",
        uiState: "processing",
        latestUploadSnapshot: {
          job_id: "transient-refresh-job",
          filename: "cached-transient.csv",
          workflow: "create_baseline",
          status: "PROCESSING",
          processing_state: "baseline_relationship_learning",
        },
        latestUploadResult: null,
      },
    });

    expect(await screen.findByText(/previous job could not be verified/i)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Upload historical data" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "cached-transient.csv" })).toBeTruthy();
    expect(screen.getByText("Status:").parentElement.textContent).toContain("Waiting");
    expect(screen.getByRole("button", { name: "View active job" })).toBeTruthy();
    expect(screen.queryByText(/Analysis active/i)).toBeNull();
  });

  it("preserves the last valid queued state through a transient polling failure", async () => {
    let statusCalls = 0;
    const apiFetch = vi.fn(async (path) => {
      if (!String(path).includes("/upload-status/transient-poll-job")) return jsonResponse({});
      statusCalls += 1;
      if (statusCalls === 2) throw new TypeError("temporary network interruption");
      return jsonResponse({
        job_id: "transient-poll-job",
        dataset_id: "transient-poll-dataset",
        filename: "transient-poll.csv",
        workflow: "create_baseline",
        status: "PENDING",
        processing_state: "queued",
        execution_state: "queued",
        queue_state: "pending",
        worker_state: "queued",
        worker_claimed: false,
      });
    });

    renderWorkspace({
      apiFetch,
      sessionStore: {
        jobId: "transient-poll-job",
        uiState: "processing",
        latestUploadSnapshot: { job_id: "transient-poll-job", status: "PENDING" },
        latestUploadResult: null,
      },
    });

    expect(await screen.findByText("transient-poll.csv")).toBeTruthy();
    await waitFor(() => expect(statusCalls).toBe(2));
    const status = screen.getByRole("status", { name: "Backend job status" });
    expect(within(status).getByText("Queued")).toBeTruthy();
    expect(within(status).getByText("Queued · waiting for worker claim")).toBeTruthy();
    expect(screen.queryByText(/Analysis active/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Start another upload" })).toBeTruthy();
  });

  it("stops the old polling owner and keeps remembered IDs scoped when the workspace changes", async () => {
    let statusCalls = 0;
    const apiFetch = vi.fn(async (path) => {
      if (!String(path).includes("/upload-status/workspace-a-job")) return jsonResponse({});
      statusCalls += 1;
      return jsonResponse({
        job_id: "workspace-a-job",
        dataset_id: "workspace-a-dataset",
        filename: "workspace-a.csv",
        workflow: "create_baseline",
        status: "PENDING",
        processing_state: "queued",
        execution_state: "queued",
        queue_state: "pending",
        worker_state: "queued",
      });
    });
    const view = renderWorkspace({
      apiFetch,
      datasetScopeKey: "workspace-a",
      sessionStore: {
        jobId: "workspace-a-job",
        uiState: "processing",
        latestUploadSnapshot: { job_id: "workspace-a-job", status: "PENDING" },
        latestUploadResult: null,
      },
    });

    expect(await screen.findByText("workspace-a.csv")).toBeTruthy();
    await waitFor(() => expect(statusCalls).toBeGreaterThanOrEqual(2));
    view.rerender(workspaceElement({ apiFetch, datasetScopeKey: "workspace-b", sessionStore: null }));
    expect(await screen.findByRole("heading", { name: "Upload historical data" })).toBeTruthy();
    const callsAfterScopeChange = statusCalls;
    await new Promise((resolve) => window.setTimeout(resolve, 1100));
    expect(statusCalls).toBe(callsAfterScopeChange);
    expect(window.localStorage.getItem("neraium.upload_job.remembered.v2:engineer-1:workspace-a")).toBe("workspace-a-job");
    expect(window.localStorage.getItem("neraium.upload_job.remembered.v2:engineer-1:workspace-b")).toBeNull();
  });

  it("restores a failed remembered job as terminal with retry and recovery actions", async () => {
    window.localStorage.setItem("neraium.last_upload_job_id", "failed-refresh-job");
    const apiFetch = vi.fn(async () => jsonResponse({
      job_id: "failed-refresh-job",
      dataset_id: "failed-refresh-dataset",
      filename: "failed-refresh.csv",
      workflow: "create_baseline",
      status: "FAILED",
      processing_state: "failed",
      execution_state: "failed",
      job_state: "failed",
      error_type: "relationship_learning_failed",
      message: "Relationship learning failed.",
      retryable: true,
      file_stored: true,
      transfer_succeeded: true,
    }));

    renderWorkspace({ apiFetch });

    expect(await screen.findByRole("heading", { name: /Processing failed during:/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry Processing" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Choose Another File" })).toBeTruthy();
    expect(screen.queryByText(/Analysis active/i)).toBeNull();
    expect(screen.getByText("failed-refresh.csv was transferred and stored successfully.")).toBeTruthy();
    expect(screen.queryByText(/No file selected was transferred/i)).toBeNull();
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
      autoOpenBaselineReady: true,
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
      autoOpenBaselineReady: true,
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

    await waitFor(() => expect(onOpenBaseline).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "Opening Baseline…" }).disabled).toBe(true);
    finishNavigation(true);
    await waitFor(() => expect(screen.getByRole("button", { name: "Upload Comparison Dataset" }).disabled).toBe(false));
  });

  it("shows a visible error when the router rejects navigation", async () => {
    const result = learnedBaseline();
    result.activation = { state: "active" };
    result.candidate_model = { ...result.candidate_model, status: "active", activation: { state: "active" } };
    renderWorkspace({
      onOpenBaseline: vi.fn(() => false),
      autoOpenBaselineReady: true,
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

    expect(await screen.findByRole("heading", { name: "Baseline Created, Workspace Not Opened" })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Baseline created successfully. We could not open the workspace automatically.");
    expect(screen.getByRole("button", { name: "Return to Portfolio" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Import Comparison Dataset" })).toBeNull();
  });

  it("does not substitute a job or dataset ID when recovery cannot find baselineId", async () => {
    const result = learnedBaseline();
    delete result.established_baseline_id;
    delete result.baseline_candidate_id;
    result.activation = { state: "active" };
    result.candidate_model = { ...result.candidate_model, model_id: null, baseline_id: null, baseline_candidate_id: null, status: "active", activation: { state: "active" } };
    const onOpenBaseline = vi.fn(() => true);
    const apiFetch = vi.fn(async () => jsonResponse({}));
    renderWorkspace({
      apiFetch,
      onOpenBaseline,
      autoOpenBaselineReady: true,
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

    expect(await screen.findByRole("heading", { name: "Baseline Created, Workspace Not Opened" })).toBeTruthy();
    expect(apiFetch.mock.calls.map(([path]) => path)).toContain("/api/data/jobs/baseline-job/result");
    expect(apiFetch.mock.calls.map(([path]) => path)).toContain("/api/data/datasets/baseline-dataset/baseline");
    expect(onOpenBaseline).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Import Comparison Dataset" })).toBeNull();
  });

  it("recovers baselineId from jobId and opens the canonical baseline route", async () => {
    const result = learnedBaseline();
    delete result.established_baseline_id;
    delete result.baseline_candidate_id;
    result.activation = { state: "active" };
    result.candidate_model = { ...result.candidate_model, model_id: null, baseline_id: null, baseline_candidate_id: null, status: "active", activation: { state: "active" } };
    const onOpenBaseline = vi.fn(() => true);
    const apiFetch = vi.fn(async (path) => {
      if (path === "/api/data/jobs/baseline-job/result") {
        return jsonResponse({
          status: "completed",
          jobId: "baseline-job",
          datasetId: "baseline-dataset",
          baselineId: "recovered-baseline",
          portfolioId: "default",
          systemId: "default",
          workspacePath: "/portfolio/default/baselines/recovered-baseline",
          createdAt: "2026-07-30T00:00:00Z",
        });
      }
      return jsonResponse({});
    });
    renderWorkspace({
      apiFetch,
      onOpenBaseline,
      autoOpenBaselineReady: true,
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

    await waitFor(() => expect(onOpenBaseline).toHaveBeenCalledWith(expect.objectContaining({
      jobId: "baseline-job",
      datasetId: "baseline-dataset",
      baselineId: "recovered-baseline",
      portfolioId: "default",
    }), { replace: true }));
    expect(onOpenBaseline.mock.calls[0][0].baselineId).not.toBe("baseline-job");
    expect(onOpenBaseline.mock.calls[0][0].baselineId).not.toBe("baseline-dataset");
  });

  it("restores a completed baseline from the canonical terminal snapshot after refresh", async () => {
    const onOpenBaseline = vi.fn(() => true);
    const snapshot = {
      status: "COMPLETE",
      processing_state: "complete",
      job_state: "completed",
      workflow: "create_baseline",
      jobId: "refresh-job",
      datasetId: "refresh-dataset",
      baselineId: "refresh-baseline",
      portfolioId: "default",
      systemId: "default",
      workspacePath: "/portfolio/default/baselines/refresh-baseline",
      createdAt: "2026-07-30T00:00:00Z",
      filename: "refresh.csv",
    };
    renderWorkspace({
      onOpenBaseline,
      autoOpenBaselineReady: true,
      hasActiveSession: false,
      hasResumedSession: false,
      latestUploadResult: null,
      sessionStore: {
        jobId: "refresh-job",
        uiState: "stale",
        latestUploadSnapshot: snapshot,
        latestUploadResult: null,
      },
    });

    await waitFor(() => expect(onOpenBaseline).toHaveBeenCalledWith(
      expect.objectContaining({ baselineId: "refresh-baseline" }),
      { replace: true },
    ));
  });

  it("preserves baselineId across a mobile completion rerender", async () => {
    const result = learnedBaseline();
    result.activation = { state: "active" };
    result.candidate_model = { ...result.candidate_model, status: "active", activation: { state: "active" } };
    const onOpenBaseline = vi.fn(() => true);
    const props = {
      onOpenBaseline,
      autoOpenBaselineReady: true,
      hasActiveSession: true,
      hasResumedSession: true,
      latestUploadResult: result,
      sessionStore: {
        jobId: "baseline-job",
        uiState: "verified",
        latestUploadSnapshot: result,
        latestUploadResult: result,
      },
    };
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    const view = renderWorkspace(props);
    expect(await screen.findByRole("heading", { name: "Baseline Established" })).toBeTruthy();

    view.rerender(workspaceElement({ ...props, currentUser: { id: "engineer-1" } }));
    fireEvent(window, new Event("resize"));

    await waitFor(() => expect(onOpenBaseline).toHaveBeenCalledWith(
      expect.objectContaining({ baselineId: "bdm-v1-baseline" }),
      { replace: true },
    ));
  });

  it("moves the completed page into a separate comparison workflow without resetting the baseline", async () => {
    const result = learnedBaseline();
    uploadTelemetryFileWithProgress.mockImplementation(() => new Promise(() => {}));
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

    fireEvent.click(await screen.findByRole("button", { name: "Upload Comparison Dataset" }));
    expect(screen.getByRole("heading", { name: "Import Comparison Dataset" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Baseline Established" })).toBeNull();

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv("comparison.csv")] } });
    fireEvent.click(screen.getByRole("button", { name: "Evaluate Against Baseline" }));
    await waitFor(() => expect(uploadTelemetryFileWithProgress).toHaveBeenCalledWith(expect.objectContaining({
      workflow: "analyze_new_data",
      baselineIdentity: expect.objectContaining({ baselineId: "bdm-v1-baseline" }),
    })));
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
    expect(screen.getByRole("button", { name: "Retry Processing" })).toBeTruthy();
  });



  it("polls the processing job id when the dataset id is different", async () => {
    const result = learnedBaseline({ job_id: "poll-job", dataset_id: "stored-dataset" });
    uploadTelemetryFileWithProgress.mockResolvedValue({
      ok: true,
      status: 202,
      payload: {
        job_id: "poll-job",
        dataset_id: "stored-dataset",
        workflow: "create_baseline",
        status: "PENDING",
        status_url: "/api/data/upload-status/poll-job",
        baseline_result_url: "/api/data/baselines/jobs/poll-job",
      },
    });
    const apiFetch = vi.fn(async (path) => {
      if (path === "/api/data/upload-status/poll-job") return jsonResponse({
        job_id: "poll-job",
        dataset_id: "stored-dataset",
        workflow: "create_baseline",
        job_state: "completed",
        status: "COMPLETE",
        processing_state: "complete",
        result_available: true,
        baseline_result_available: true,
        baseline_result_url: "/api/data/baselines/jobs/poll-job",
      });
      if (path === "/api/data/baselines/jobs/poll-job") return jsonResponse(result);
      return jsonResponse({}, { ok: false, status: 404 });
    });
    renderWorkspace({ apiFetch });

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv()] } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("heading", { name: "Baseline Established" })).toBeTruthy();
    expect(apiFetch).toHaveBeenCalledWith("/api/data/upload-status/poll-job", expect.any(Object));
    expect(apiFetch.mock.calls.some(([path]) => String(path).includes("upload-status/stored-dataset"))).toBe(false);
    fireEvent.click(screen.getByText("Processing details"));
    expect(screen.getByText("poll-job")).toBeTruthy();
    expect(screen.getByText("stored-dataset")).toBeTruthy();
  });

  it("continues polling when terminal status temporarily has no result", async () => {
    uploadTelemetryFileWithProgress.mockResolvedValue({
      ok: true,
      status: 202,
      payload: { job_id: "eventual-job", dataset_id: "eventual-dataset", workflow: "create_baseline", status: "PENDING" },
    });
    let statusCalls = 0;
    const apiFetch = vi.fn(async (path) => {
      if (String(path).includes("/upload-status/eventual-job")) {
        statusCalls += 1;
        return jsonResponse({
          job_id: "eventual-job",
          dataset_id: "eventual-dataset",
          workflow: "create_baseline",
          job_state: "completed",
          status: "COMPLETE",
          processing_state: "complete",
          result_available: statusCalls > 1,
          baseline_result_available: statusCalls > 1,
          baseline_result_url: "/api/data/baselines/jobs/eventual-job",
        });
      }
      if (String(path).includes("/baselines/jobs/eventual-job")) {
        return jsonResponse(learnedBaseline({ job_id: "eventual-job", dataset_id: "eventual-dataset" }));
      }
      return jsonResponse({});
    });
    renderWorkspace({ apiFetch });

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv()] } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("heading", { name: "Baseline Established" }, { timeout: 3500 })).toBeTruthy();
    expect(statusCalls).toBe(2);
  });

  it("retries a temporarily missing committed result before failing", async () => {
    uploadTelemetryFileWithProgress.mockResolvedValue({
      ok: true,
      status: 202,
      payload: { job_id: "delayed-result-job", dataset_id: "delayed-result-dataset", workflow: "create_baseline", status: "PENDING" },
    });
    let resultCalls = 0;
    const apiFetch = vi.fn(async (path) => {
      if (String(path).includes("/upload-status/delayed-result-job")) return jsonResponse({
        job_id: "delayed-result-job",
        dataset_id: "delayed-result-dataset",
        workflow: "create_baseline",
        job_state: "completed",
        status: "COMPLETE",
        processing_state: "complete",
        result_available: true,
        baseline_result_available: true,
        baseline_result_url: "/api/data/baselines/jobs/delayed-result-job",
      });
      if (String(path).includes("/baselines/jobs/delayed-result-job")) {
        resultCalls += 1;
        return resultCalls === 1
          ? jsonResponse({ detail: "not visible yet" }, { ok: false, status: 404 })
          : jsonResponse(learnedBaseline({ job_id: "delayed-result-job", dataset_id: "delayed-result-dataset" }));
      }
      return jsonResponse({});
    });
    renderWorkspace({ apiFetch });

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv()] } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("heading", { name: "Baseline Established" })).toBeTruthy();
    expect(resultCalls).toBe(2);
  });

  it("treats an HTTP 200 failed job as terminal and shows its processing stage", async () => {
    uploadTelemetryFileWithProgress.mockResolvedValue({
      ok: true,
      status: 202,
      payload: { job_id: "failed-job-200", dataset_id: "stored-dataset-200", workflow: "create_baseline", status: "PENDING" },
    });
    const apiFetch = vi.fn(async (path) => String(path).includes("/upload-status/")
      ? jsonResponse({
        status: "FAILED",
        job_state: "failed",
        processing_state: "failed",
        stage: "relationship_learning",
        errorCode: "relationship_learning_failed",
        userMessage: "The uploaded telemetry did not contain stable learnable relationships.",
        technicalMessage: "ArithmeticError: singular relationship matrix",
        retryable: true,
        datasetId: "stored-dataset-200",
        dataset_id: "stored-dataset-200",
        jobId: "failed-job-200",
        job_id: "failed-job-200",
        requestId: "request-200",
        request_id: "request-200",
        file_stored: true,
        transfer_succeeded: true,
      })
      : jsonResponse({}));
    renderWorkspace({ apiFetch });

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv()] } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("heading", { name: "Processing failed during: Relationship learning" })).toBeTruthy();
    expect(screen.getAllByText("File uploaded").length).toBeGreaterThan(0);
    expect(screen.getAllByText("The uploaded telemetry did not contain stable learnable relationships.").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Retry Processing" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Choose Another File" })).toBeTruthy();
    const processingDetails = screen.getByText("Processing details").closest("details");
    expect(processingDetails?.hasAttribute("open")).toBe(false);
    fireEvent.click(screen.getByText("Processing details"));
    expect(processingDetails?.hasAttribute("open")).toBe(true);
    expect(screen.getByText("ArithmeticError: singular relationship matrix")).toBeTruthy();
  });

  it("retry processing reuses the stored dataset and does not upload again", async () => {
    uploadTelemetryFileWithProgress.mockResolvedValue({
      ok: true,
      status: 202,
      payload: { job_id: "retry-job", dataset_id: "retry-dataset", workflow: "create_baseline", status: "PENDING" },
    });
    let statusCalls = 0;
    const apiFetch = vi.fn(async (path) => {
      if (String(path).includes("/upload-status/retry-job")) {
        statusCalls += 1;
        if (statusCalls === 1) return jsonResponse({
          job_id: "retry-job",
          dataset_id: "retry-dataset",
          workflow: "create_baseline",
          status: "FAILED",
          job_state: "failed",
          processing_state: "failed",
          stage: "relationship_learning",
          errorCode: "relationship_learning_failed",
          userMessage: "Relationship learning was interrupted.",
          technicalMessage: "RuntimeError: worker restarted",
          retryable: true,
          file_stored: true,
          transfer_succeeded: true,
        });
        return jsonResponse({
          job_id: "retry-job",
          dataset_id: "retry-dataset",
          workflow: "create_baseline",
          status: "COMPLETE",
          job_state: "completed",
          processing_state: "complete",
          result_available: true,
          baseline_result_available: true,
          baseline_result_url: "/api/data/baselines/jobs/retry-job",
        });
      }
      if (String(path).includes("/baselines/jobs/retry-job")) {
        return jsonResponse(learnedBaseline({ job_id: "retry-job", dataset_id: "retry-dataset" }));
      }
      return jsonResponse({});
    });
    retryUploadAnalysisJob.mockResolvedValue({
      ok: true,
      status: 202,
      payload: { job_id: "retry-job", dataset_id: "retry-dataset", workflow: "create_baseline", status: "PENDING" },
    });
    renderWorkspace({ apiFetch });

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv()] } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(await screen.findByRole("button", { name: "Retry Processing" }));

    expect(await screen.findByRole("heading", { name: "Baseline Established" })).toBeTruthy();
    expect(retryUploadAnalysisJob).toHaveBeenCalledWith(expect.objectContaining({ jobId: "retry-job" }));
    expect(uploadTelemetryFileWithProgress).toHaveBeenCalledTimes(1);
  });

  it("does not create a duplicate upload when stored-job retry is unavailable", async () => {
    uploadTelemetryFileWithProgress.mockResolvedValue({
      ok: true,
      status: 202,
      payload: { job_id: "missing-retry-job", dataset_id: "preserved-dataset", workflow: "create_baseline", status: "PENDING" },
    });
    const apiFetch = vi.fn(async (path) => String(path).includes("/upload-status/")
      ? jsonResponse({
        job_id: "missing-retry-job",
        dataset_id: "preserved-dataset",
        workflow: "create_baseline",
        status: "FAILED",
        processing_state: "failed",
        stage: "validation",
        errorCode: "validation_failed",
        userMessage: "A required telemetry signal is missing.",
        retryable: true,
        file_stored: true,
        transfer_succeeded: true,
      })
      : jsonResponse({}));
    const retryError = Object.assign(new Error("Stored processing job was not found."), {
      name: "UploadRequestError",
      status: 404,
      phase: "retry",
      errorType: "not_found",
      jobId: "missing-retry-job",
      datasetId: "preserved-dataset",
      fileStored: true,
      transferSucceeded: true,
      retryable: false,
    });
    retryUploadAnalysisJob.mockRejectedValue(retryError);
    renderWorkspace({ apiFetch });

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv()] } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(await screen.findByRole("button", { name: "Retry Processing" }));

    await waitFor(() => expect(retryUploadAnalysisJob).toHaveBeenCalledTimes(1));
    expect(uploadTelemetryFileWithProgress).toHaveBeenCalledTimes(1);
  });

  it("choose another file clears failed workflow and polling identity", async () => {
    const error = Object.assign(new Error("Relationship learning failed."), {
      name: "UploadRequestError",
      status: 200,
      phase: "poll",
      errorType: "relationship_learning_failed",
      jobId: "abandoned-job",
      datasetId: "abandoned-dataset",
      failedStage: "relationship_learning",
      fileStored: true,
      transferSucceeded: true,
      retryable: true,
    });
    uploadTelemetryFileWithProgress.mockRejectedValue(error);
    renderWorkspace();

    fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv()] } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(await screen.findByRole("button", { name: "Choose Another File" }));

    expect(screen.queryByRole("heading", { name: /Processing failed during:/ })).toBeNull();
    expect(screen.getByRole("heading", { name: "Upload historical data" })).toBeTruthy();
    expect(window.localStorage.getItem("neraium.last_upload_job_id")).toBeNull();
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
    expect(queuedWorkerMessage({ worker_state: "starting" }, now)).toBe("");
    expect(queuedWorkerMessage({ execution_state: "queued", worker_state: "running", status: "PENDING" }, now)).toBe("Queued · waiting for worker claim");
    expect(queuedWorkerMessage({ execution_state: "processing", worker_state: "active", worker_last_update_at: "2026-07-22T21:28:01.070289+00:00" }, now)).toBe("Analysis active · updated 2 minutes ago");
    expect(formatAnalysisUpdateTime("2026-07-22T19:30:01Z", now)).toBe("2 hours ago");
  });
});
