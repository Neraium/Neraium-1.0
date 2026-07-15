/* @vitest-environment jsdom */
import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import DataConnectionsWorkspace from "./DataConnectionsWorkspace";
import IntakeFlowPanel from "./setup/IntakeFlowPanel";
import { uploadTelemetryFileWithProgress } from "../services/api/uploadApi";
import { SERVICE_UNAVAILABLE_RETRY_MESSAGE, SERVICE_UNAVAILABLE_UPLOAD_MESSAGE } from "../viewModels/uploadFlow";

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
    isUploadProcessing: (state) => ["uploading", "processing", "running_sii", "structural_scoring", "building_fingerprint", "saving_results", "navigation_pending"].includes(String(state)),
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


const HTML_503 = "<html><head><title>503 Service Temporarily Unavailable</title></head><body>nginx</body></html>";

function htmlResponse(status = 503) {
  return {
    ok: false,
    status,
    headers: { get: () => "text/html" },
    text: async () => HTML_503,
  };
}

function jsonResponse(payload, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    json: async () => payload,
  };
}

function uploadHtml503Error() {
  const error = new Error(HTML_503);
  error.name = "UploadRequestError";
  error.status = 503;
  error.phase = "upload";
  error.errorType = "service_unavailable";
  error.detail = HTML_503;
  error.payload = {
    status: "FAILED",
    processing_state: "failed",
    error_type: "service_unavailable",
    message: HTML_503,
    failure_url: "/api/data/upload",
    failure_phase: "upload",
    response_status: 503,
    raw_response_body: HTML_503,
    html_response: true,
  };
  error.responseText = HTML_503;
  error.uploadUrl = "/api/data/upload";
  return error;
}


afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  vi.useRealTimers();
});


it("shows a clean service unavailable upload failure while keeping raw HTML in Advanced Details", async () => {
  uploadTelemetryFileWithProgress.mockRejectedValue(uploadHtml503Error());

  renderWorkspace();

  fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv("html-503.csv")] } });
  fireEvent.click(screen.getByTestId("process-upload-button"));

  await waitFor(() => {
    expect(screen.getByRole("alert").textContent).toContain(SERVICE_UNAVAILABLE_UPLOAD_MESSAGE);
  });
  const alert = screen.getByRole("alert");
  expect(alert.textContent).toContain(SERVICE_UNAVAILABLE_UPLOAD_MESSAGE);
  expect(alert.textContent).not.toContain("<html>");

  const details = screen.getByText("Advanced Details").closest("details");
  expect(details.textContent).toContain("/api/data/upload");
  expect(details.textContent).toContain(HTML_503);
});

it("continues polling after temporary stream and status HTML 503 responses", async () => {
  uploadTelemetryFileWithProgress.mockResolvedValue({
    ok: true,
    status: 202,
    payload: { job_id: "job-temporary-503", status_url: "/api/data/upload-status/job-temporary-503", status: "queued", message: "Upload accepted." },
  });
  let statusCalls = 0;
  const apiFetch = vi.fn(async (path) => {
    if (String(path).includes("/api/data/upload-stream/job-temporary-503")) return htmlResponse(503);
    if (String(path).includes("/api/data/upload-status/job-temporary-503")) {
      statusCalls += 1;
      if (statusCalls === 1) return htmlResponse(503);
      return jsonResponse({
        job_id: "job-temporary-503",
        status: "COMPLETE",
        processing_state: "complete",
        result_available: true,
        first_usable_available: true,
        progress_label: "Analysis ready.",
        message: "Analysis ready.",
        analysis_result: {
          systems: [{ name: "Recovered system" }],
          insights: [{ title: "Recovered insight" }],
          fingerprint: { status: "Established" },
        },
      });
    }
    return jsonResponse({});
  });
  const onUploadComplete = vi.fn(async () => {});

  renderWorkspace({ apiFetch, onUploadComplete });
  fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv("temporary.csv")] } });
  fireEvent.click(screen.getByTestId("process-upload-button"));

  expect(await screen.findByLabelText(`Analysis progress: ${SERVICE_UNAVAILABLE_RETRY_MESSAGE}`)).toBeTruthy();

  await waitFor(() => {
    expect(onUploadComplete).toHaveBeenCalledWith(expect.objectContaining({ job_id: "job-temporary-503" }), { navigateToGate: false });
  }, { timeout: 3500 });
});

it("eventually fails persistent polling HTML 503 responses with a clean message", async () => {
  vi.useFakeTimers();
  uploadTelemetryFileWithProgress.mockResolvedValue({
    ok: true,
    status: 202,
    payload: { job_id: "job-persistent-503", status_url: "/api/data/upload-status/job-persistent-503", status: "queued", message: "Upload accepted." },
  });
  const apiFetch = vi.fn(async (path) => {
    if (String(path).includes("/api/data/upload-stream/job-persistent-503")) return htmlResponse(503);
    if (String(path).includes("/api/data/upload-status/job-persistent-503")) return htmlResponse(503);
    return jsonResponse({});
  });

  renderWorkspace({ apiFetch });
  fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv("persistent.csv")] } });
  fireEvent.click(screen.getByTestId("process-upload-button"));

  await act(async () => {
    await vi.advanceTimersByTimeAsync(70000);
  });
  vi.useRealTimers();

  await waitFor(() => {
    expect(screen.getByRole("alert").textContent).toContain(SERVICE_UNAVAILABLE_UPLOAD_MESSAGE);
  });
  const alert = screen.getByRole("alert");
  expect(alert.textContent).toContain(SERVICE_UNAVAILABLE_UPLOAD_MESSAGE);
  expect(alert.textContent).not.toContain("<html>");
});

it("mobile upload screen does not render backend milestone cards by default", () => {
  window.innerWidth = 390;
  renderPanel();

  expect(screen.getAllByRole("heading", { name: "Historical Data Analysis" }).length).toBeGreaterThan(0);
  expect(screen.queryByLabelText("Backend milestones")).toBeNull();
  expect(screen.queryByText("Backend milestones")).toBeNull();
  expect(screen.queryByText("What this run returns")).toBeNull();
  expect(screen.queryByText("Current run at a glance")).toBeNull();
});

it("selected file state shows filename, size, and Analyze Dataset", () => {
  renderPanel({
    uploadState: "validated",
    selectedFiles: [selectedCsv("operators.csv")],
    selectedFileSize: "15.7 MB",
  });

  expect(screen.getByText("operators.csv")).toBeTruthy();
  expect(screen.getByText("CSV telemetry - 15.7 MB")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Choose File" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Analyze Dataset" })).toBeTruthy();
  expect(screen.getByText("Historical Data Ready")).toBeTruthy();
});

it("drag-over and drop use the premium upload card", () => {
  const handleFileSelection = vi.fn();
  renderPanel({ handleFileSelection });

  const card = screen.getByLabelText("Historical data upload");
  fireEvent.dragOver(card, { dataTransfer: { dropEffect: "" } });
  expect(card.classList.contains("upload-analysis-card--drag-active")).toBe(true);

  const file = selectedCsv("dropped.csv");
  fireEvent.drop(card, { dataTransfer: { files: [file] } });
  expect(handleFileSelection).toHaveBeenCalledTimes(1);
  expect(handleFileSelection.mock.calls[0][0].dataTransfer.files[0]).toBe(file);
  expect(card.classList.contains("upload-analysis-card--drag-active")).toBe(false);
});

it("processing state uses the behavior baseline as the progress indicator", () => {
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
      progress_label: "Building behavior baseline...",
      result_available: false,
    },
    latestMessage: "Building behavior baseline...",
  });

  expect(screen.getByText("Learning Operational Relationships")).toBeTruthy();
  expect(screen.getByText("Stage 2 of 4")).toBeTruthy();
  expect(screen.getByText("progress.csv")).toBeTruthy();
  expect(screen.getByText("1.0 KB")).toBeTruthy();
  expect(screen.getAllByRole("progressbar")).toHaveLength(1);
  expect(screen.getByLabelText("Analysis 65% complete")).toBeTruthy();
  expect(screen.queryByText("65% complete")).toBeNull();
});


it("baseline renderer fallback keeps the active analysis job visible", () => {
  window.localStorage.setItem("neraium.upload_fingerprint.compatibility_mode", "black-screen-recovery");

  renderPanel({
    uploadState: "running_sii",
    selectedFiles: [selectedCsv("fallback.csv")],
    selectedFileSize: "1.0 KB",
    uploadJob: {
      job_id: "active-job",
      status: "PROCESSING",
      processing_state: "building_fingerprint",
      percent: 65,
      progress: 65,
      result_available: false,
    },
    latestMessage: "Building behavior baseline...",
  });

  expect(screen.getByText("Using an alternate processing path.")).toBeTruthy();
  expect(screen.getByText("fallback.csv")).toBeTruthy();
  expect(screen.getByLabelText("Analysis 65% complete")).toBeTruthy();
  const renderer = document.querySelector(".upload-fingerprint-build");
  expect(renderer?.getAttribute("data-render-tier")).toBe("safe");
  expect(renderer?.querySelector(".upload-fingerprint-build__particles")).toBeNull();
});

it("baseline renderer uses enhanced mode on mobile-capable constraints", () => {
  vi.stubGlobal("matchMedia", (query) => ({
    matches: /max-width: 760px|hover: none/.test(query),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));

  renderPanel({
    uploadState: "running_sii",
    selectedFiles: [selectedCsv("mobile.csv")],
    selectedFileSize: "1.0 KB",
    uploadJob: {
      job_id: "mobile-job",
      status: "PROCESSING",
      processing_state: "building_fingerprint",
      percent: 65,
      progress: 65,
      result_available: false,
    },
    latestMessage: "Building behavior baseline...",
  });

  const renderer = document.querySelector(".upload-fingerprint-build");
  expect(renderer?.getAttribute("data-render-tier")).toBe("enhanced");
  expect(renderer?.querySelectorAll(".upload-fingerprint-build__particles span")).toHaveLength(3);
  expect(screen.getByText("Learning Operational Relationships")).toBeTruthy();
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

  expect(screen.getByRole("heading", { name: "Upload Error" })).toBeTruthy();
  expect(screen.getAllByText("CSV could not be parsed.").length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Choose File" })).toBeTruthy();
});

it("complete state shows the behavior baseline completion moment", () => {
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

  expect(screen.getByRole("heading", { name: "Behavior Baseline Established" })).toBeTruthy();
  expect(screen.getByText("Learned operational behavior is ready for command center review.")).toBeTruthy();
  const labels = Array.from(document.querySelectorAll(".upload-result-summary__item span")).map((node) => node.textContent);
  expect(labels).toEqual(["Systems", "Insights", "Baseline"]);
  expect(screen.getByRole("button", { name: "Open Command Center" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Analyze Another Source" })).toBeTruthy();
  const details = screen.getByText("Advanced Details").closest("details");
  expect(details.open).toBe(false);
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

  const item = Array.from(document.querySelectorAll(".upload-result-summary__item")).find((node) => node.textContent?.includes("Systems"));
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
          fingerprint: { status: "changed" },
        },
      },
    },
    uploadJob: { job_id: "complete-job", status: "COMPLETE", result_available: true },
  });

  const item = screen.getByText("Insights").closest(".upload-result-summary__item");
  expect(item.textContent).toContain("4");

  const baselineItem = Array.from(document.querySelectorAll(".upload-result-summary__item"))
    .find((item) => item.textContent.startsWith("Baseline"));
  expect(baselineItem.textContent).toContain("Changed");
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

  expect(screen.getByLabelText("Analysis progress: Generating Operational Insights...")).toBeTruthy();
  expect(screen.getByText("Establishing Behavioral Baseline")).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Analysis Complete" })).toBeNull();
  expect(document.querySelector(".upload-result-summary")).toBeNull();
  expect(screen.getByLabelText("Analysis 99% complete")).toBeTruthy();
});

it("idle no-file state does not render stale complete progress", () => {
  renderPanel({
    uploadState: "idle",
    selectedFiles: [],
    uploadJob: { job_id: "old-job", status: "complete", percent: 100, processing_state: "complete" },
  });

  expect(screen.getAllByText("No file selected").length).toBeGreaterThan(0);
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
  expect(screen.getByRole("button", { name: "Analyze Dataset" })).toBeTruthy();
});

it("analyze another CSV resets the completed workspace", async () => {
  const onResetDemo = vi.fn(async () => ({}));
  renderWorkspace({
    hasResumedSession: true,
    sessionStore: completedSessionStore(),
    onResetDemo,
  });

  await waitFor(() => {
    expect(screen.getByRole("button", { name: "Analyze Another Source" })).toBeTruthy();
  });

  fireEvent.click(screen.getByRole("button", { name: "Analyze Another Source" }));

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

  expect(screen.getAllByText("No file selected").length).toBeGreaterThan(0);
  expect(screen.queryAllByRole("progressbar")).toHaveLength(0);
});

it("treats the first complete payload with a saved result as terminal and auto-opens Command Center after the fallback is visible", async () => {
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

  expect(await screen.findByRole("button", { name: "Open Command Center" })).toBeTruthy();
  expect(screen.getByText("Learned operational behavior is ready for command center review.")).toBeTruthy();

  await waitFor(() => {
    expect(onUploadComplete).toHaveBeenCalledWith(expect.objectContaining({ job_id: "job-complete" }), { navigateToGate: true });
  }, { timeout: 4000 });
});

it("continues polling when stream status includes a placeholder analysis result", async () => {
  uploadTelemetryFileWithProgress.mockResolvedValue({
    ok: true,
    status: 202,
    payload: { job_id: "job-stream", status_url: "/api/data/upload-status/job-stream", status: "queued", message: "Upload accepted." },
  });

  const streamPayload = {
    job_id: "job-stream",
    status: "PENDING",
    processing_state: "queued",
    result_available: false,
    first_usable_available: false,
    analysis_result: { status: "queued", systems: [], insights: [], fingerprint: {} },
  };
  const apiFetch = vi.fn(async (path) => {
    if (String(path).includes("/api/data/upload-stream/job-stream")) {
      const encoder = new TextEncoder();
      return {
        ok: true,
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify(streamPayload)}\n\n`));
            controller.close();
          },
        }),
      };
    }
    if (String(path).includes("/api/data/upload-status/job-stream")) {
      return {
        ok: true,
        json: async () => ({
          job_id: "job-stream",
          status: "COMPLETE",
          processing_state: "complete",
          result_available: true,
          first_usable_available: true,
          replay_ready: false,
          progress_label: "Analysis ready.",
          message: "Analysis ready.",
          analysis_result: {
            status: "complete",
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
    expect(apiFetch).toHaveBeenCalledWith("/api/data/upload-status/job-stream", { accessCode: "" });
  });
  await waitFor(() => {
    expect(onUploadComplete).toHaveBeenCalledWith(expect.objectContaining({ job_id: "job-stream", status: "COMPLETE" }), { navigateToGate: false });
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
  expect(screen.getByText("Identifying Operational Systems")).toBeTruthy();
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


it("continues polling when a result is available but backend state is still processing", async () => {
  uploadTelemetryFileWithProgress.mockResolvedValue({
    ok: true,
    status: 202,
    payload: { job_id: "job-nonterminal-result", status_url: "/api/data/upload-status/job-nonterminal-result", status: "queued", message: "Upload accepted." },
  });

  const events = [];
  const streamPayload = {
    job_id: "job-nonterminal-result",
    status: "PROCESSING",
    job_state: "processing",
    processing_state: "saving_result",
    result_available: true,
    first_usable_available: true,
    progress_label: "Saving result...",
    message: "Saving result...",
    analysis_result: {
      systems: [{ name: "Premature system" }],
      insights: [{ title: "Premature insight" }],
      fingerprint: { status: "Established" },
    },
  };
  const apiFetch = vi.fn(async (path) => {
    if (String(path).includes("/api/data/upload-stream/job-nonterminal-result")) {
      events.push("stream");
      const encoder = new TextEncoder();
      return {
        ok: true,
        body: new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify(streamPayload)}\n\n`));
            controller.close();
          },
        }),
      };
    }
    if (String(path).includes("/api/data/upload-status/job-nonterminal-result")) {
      events.push("status");
      return jsonResponse({
        job_id: "job-nonterminal-result",
        status: "COMPLETE",
        job_state: "completed",
        terminal: true,
        processing_state: "complete",
        result_available: true,
        first_usable_available: true,
        progress_label: "Analysis ready.",
        message: "Analysis ready.",
        analysis_result: {
          systems: [{ name: "Completed system" }],
          insights: [{ title: "Completed insight" }],
          fingerprint: { status: "Established" },
        },
      });
    }
    return jsonResponse({});
  });
  const onUploadComplete = vi.fn(async () => { events.push("complete"); });

  renderWorkspace({ apiFetch, onUploadComplete });
  fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv("nonterminal.csv")] } });
  fireEvent.click(screen.getByTestId("process-upload-button"));

  await waitFor(() => {
    expect(onUploadComplete).toHaveBeenCalledWith(expect.objectContaining({ job_id: "job-nonterminal-result", status: "COMPLETE" }), { navigateToGate: false });
  });
  expect(events.indexOf("status")).toBeGreaterThan(events.indexOf("stream"));
  expect(events.indexOf("complete")).toBeGreaterThan(events.indexOf("status"));
});

it("prevents duplicate upload and polling events from repeated process clicks", async () => {
  let releaseUpload;
  uploadTelemetryFileWithProgress.mockImplementation(() => new Promise((resolve) => {
    releaseUpload = () => resolve({
      ok: true,
      status: 202,
      payload: { job_id: "job-duplicate-click", status_url: "/api/data/upload-status/job-duplicate-click", status: "queued", message: "Upload accepted." },
    });
  }));

  const apiFetch = vi.fn(async (path) => {
    if (String(path).includes("/api/data/upload-stream/job-duplicate-click")) return jsonResponse({}, { ok: false, status: 404 });
    if (String(path).includes("/api/data/upload-status/job-duplicate-click")) {
      return jsonResponse({
        job_id: "job-duplicate-click",
        status: "COMPLETE",
        job_state: "completed",
        terminal: true,
        processing_state: "complete",
        result_available: true,
        first_usable_available: true,
        progress_label: "Analysis ready.",
        message: "Analysis ready.",
        analysis_result: {
          systems: [{ name: "Completed system" }],
          insights: [{ title: "Completed insight" }],
          fingerprint: { status: "Established" },
        },
      });
    }
    return jsonResponse({});
  });
  const onUploadComplete = vi.fn(async () => {});

  renderWorkspace({ apiFetch, onUploadComplete });
  fireEvent.change(screen.getByTestId("csv-upload-input"), { target: { files: [selectedCsv("duplicate.csv")] } });
  const processButton = screen.getByTestId("process-upload-button");
  fireEvent.click(processButton);
  fireEvent.click(processButton);

  expect(uploadTelemetryFileWithProgress).toHaveBeenCalledTimes(1);

  await act(async () => {
    releaseUpload();
  });

  await waitFor(() => {
    expect(onUploadComplete).toHaveBeenCalledWith(expect.objectContaining({ job_id: "job-duplicate-click" }), { navigateToGate: false });
  });
  expect(uploadTelemetryFileWithProgress).toHaveBeenCalledTimes(1);
  expect(apiFetch.mock.calls.filter(([path]) => String(path).includes("/api/data/upload-status/job-duplicate-click"))).toHaveLength(1);
});
