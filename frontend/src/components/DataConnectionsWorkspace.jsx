import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL, API_ROUTE_MODE, CONFIGURED_API_BASE_URL } from "../config";
import { uploadStagePercent } from "../viewModels/uploadContract";
import {
  SERVICE_UNAVAILABLE_RETRY_MESSAGE,
  buildUploadRequestError,
  classifyUploadError,
  isTransientUploadServiceStatus,
  isUploadProcessing,
  normalizeErrorMessage,
  normalizeUploadStatus,
  readJsonPayload,
  uploadStateMessage,
} from "../viewModels/uploadFlow";
import * as uploadStateView from "../viewModels/uploadState";
import {
  BASELINE_ANALYSIS_STATES,
  backendAnalysisState,
  canRenderCompletedAnalysis,
  completedAnalysisForDataset,
  datasetIdFromPayload,
  payloadMatchesDataset,
  resolveBaselineAnalysisState,
} from "../viewModels/baselineAnalysisState";
import { retryUploadAnalysisJob, uploadTelemetryFileWithProgress } from "../services/api/uploadApi";
import IntakeFlowPanel from "./setup/IntakeFlowPanel";

const MAX_UPLOAD_BYTES = 250 * 1024 * 1024;
const LARGE_OPERATIONAL_UPLOAD_BYTES = 100 * 1024 * 1024;
const UPLOAD_REQUEST_TIMEOUT_MS = 4 * 60 * 60 * 1000;
const LAST_UPLOAD_JOB_ID_STORAGE_KEY = "neraium.last_upload_job_id";
const MAX_STATUS_POLL_FAILURES = 8;
const MAX_STATUS_POLL_ATTEMPTS = 240;
const STATUS_ENDPOINT_FAILURE_BASE_DELAY_MS = 1000;
const STATUS_POLL_INTERVAL_MS = 1000;
const COMPLETION_HOLD_MS = 2500;
const PARSING_COMPLETE_STATUSES = new Set([
  "validating_schema",
  "processing",
  "baseline_modeling",
  "structural_scoring",
  "running_sii",
  "building_fingerprint",
  "writing_state",
  "cognition_ready",
  "saving_result",
  "complete",
]);
const ANALYSIS_STARTED_STATUSES = new Set([
  "baseline_modeling",
  "structural_scoring",
  "running_sii",
  "building_fingerprint",
  "writing_state",
  "cognition_ready",
  "saving_result",
  "complete",
]);

const UPLOAD_OPERATOR_COPY = Object.freeze({
  telemetryExportValidated: "Telemetry export validated.",
  queuedWorkerLine: "Preparing analysis resources",
  queuedWorkerAnnouncement: "Preparing analysis resources...",
});
const BASELINE_WORKFLOWS = new Set(["create_baseline", "extend_baseline"]);

function isBaselineWorkflow(value) {
  return BASELINE_WORKFLOWS.has(String(value || "").trim().toLowerCase());
}


function formatTransferSpeed(bytesPerSecond) {
  const speed = Number(bytesPerSecond);
  if (!Number.isFinite(speed) || speed <= 0) return null;
  if (speed >= 1024 * 1024) return `${(speed / (1024 * 1024)).toFixed(1)} MB/s`;
  return `${Math.max(speed / 1024, 1).toFixed(1)} KB/s`;
}

function formatUploadTransferLabel(progress) {
  const loaded = formatFileSize(progress?.loaded ?? 0);
  const total = formatFileSize(progress?.total ?? 0);
  const speed = formatTransferSpeed(progress?.speedBytesPerSecond ?? progress?.bytesPerSecond);
  return speed ? `Sending telemetry ${loaded} of ${total} at ${speed}` : `Sending telemetry ${loaded} of ${total}`;
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "No file";
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(bytes / 1024, 1).toFixed(1)} KB`;
}

function isLargeOperationalUpload(file) {
  return (file?.size ?? 0) >= LARGE_OPERATIONAL_UPLOAD_BYTES;
}

function uploadReadinessMessage(file) {
  if (!file) return "Choose a telemetry file.";
  if (isLargeOperationalUpload(file)) {
    return "Large telemetry export detected. Processing continues in the background.";
  }
  return UPLOAD_OPERATOR_COPY.telemetryExportValidated;
}

function validateTelemetryFile(file, kind) {
  if (!file) return "Choose a telemetry file.";
  if (file.size > MAX_UPLOAD_BYTES) return `High-volume export above ${formatFileSize(MAX_UPLOAD_BYTES)}. Use partitioned export or enterprise batch intake.`;
  const filename = String(file.name ?? "").toLowerCase();
  const mime = String(file.type ?? "").toLowerCase();
  const looksCsv = filename.endsWith(".csv") || mime.includes("csv") || mime === "text/plain" || mime === "";
  if (kind === "csv" && !looksCsv) return "Choose a CSV telemetry file.";
  return "";
}

function fallbackPercentFromStatus(status) {
  return uploadStagePercent(status);
}

function boundedFailureDelay(failureCount) {
  const failureIndex = Math.max(0, Number(failureCount || 1) - 1);
  const backoff = Math.min(15000, STATUS_POLL_INTERVAL_MS * (1.5 ** failureIndex));
  return Math.max(backoff, STATUS_POLL_INTERVAL_MS);
}

export function frontendPollingTiming(payload, requestStartedAt, receivedAt = Date.now()) {
  const requestStarted = Number(requestStartedAt);
  const stageChangedAt = Date.parse(String(payload?.stage_changed_at ?? payload?.updated_at ?? ""));
  const serverSentAt = Date.parse(String(payload?.status_server_sent_at ?? payload?.status_checked_at ?? ""));
  return {
    poll_request_ms: Number.isFinite(requestStarted) ? Math.max(0, receivedAt - requestStarted) : null,
    frontend_polling_latency_ms: Number.isFinite(stageChangedAt) ? Math.max(0, receivedAt - stageChangedAt) : null,
    status_transport_latency_ms: Number.isFinite(serverSentAt) ? Math.max(0, receivedAt - serverSentAt) : null,
    received_at: new Date(receivedAt).toISOString(),
  };
}

export function formatAnalysisUpdateTime(value, now = Date.now()) {
  const updatedAt = Date.parse(String(value ?? ""));
  if (!Number.isFinite(updatedAt)) return "just now";
  const elapsedSeconds = Math.max(0, Math.floor((Number(now) - updatedAt) / 1000));
  if (elapsedSeconds < 60) return "just now";
  const minutes = Math.floor(elapsedSeconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export function queuedWorkerMessage(uploadJob, now = Date.now()) {
  const workerState = String(uploadJob?.worker_state ?? uploadJob?.workerState ?? "").toLowerCase();
  const lastUpdate = uploadJob?.worker_last_update_at ?? uploadJob?.worker_last_update ?? uploadJob?.updated_at ?? "";
  if (workerState === "starting") return UPLOAD_OPERATOR_COPY.queuedWorkerLine;
  if (workerState === "active" || workerState === "running") return `Analysis active · updated ${formatAnalysisUpdateTime(lastUpdate, now)}`;
  if (workerState === "queued" || normalizeUploadStatus(uploadJob?.status) === "queued") return UPLOAD_OPERATOR_COPY.queuedWorkerLine;
  if (workerState === "stalled") return "No recent progress update; analysis may still be continuing.";
  return "";
}

function isActiveUploadProgressState(uploadState) {
  return ["uploading", "running_sii", "processing", "saving_results", "save_complete", "navigation_pending", "completion_error", "complete"].includes(String(uploadState || "").toLowerCase());
}

function uploadFailureDiagnosticsFrom(value = {}) {
  return {
    failureUrl: value.failureUrl ?? value.failure_url ?? null,
    failurePhase: value.failurePhase ?? value.failure_phase ?? null,
    rawResponseBody: value.rawResponseBody ?? value.raw_response_body ?? "",
    responseStatus: value.responseStatus ?? value.response_status ?? value.status ?? null,
    responseContentType: value.responseContentType ?? value.response_content_type ?? null,
  };
}

function logUploadFailureDiagnostics(value = {}) {
  if (!import.meta.env.DEV) return;
  const diagnostics = uploadFailureDiagnosticsFrom(value);
  console.warn("[neraium] upload request failure", {
    url: diagnostics.failureUrl,
    phase: diagnostics.failurePhase,
    status: diagnostics.responseStatus,
    errorType: value.errorType ?? value.error_type ?? null,
  });
}



export default function DataConnectionsWorkspace({
  accessCode,
  apiFetch,
  onUploadComplete,
  initialSelectedFiles = [],
  onInitialSelectedFilesConsumed,
  autoStartInitialFiles = false,
  headless = false,
}) {
  const seededSelectedFiles = useMemo(() => (Array.isArray(initialSelectedFiles) ? initialSelectedFiles : []), [initialSelectedFiles]);
  const [selectedFiles, setSelectedFiles] = useState(() => seededSelectedFiles);
  const [pendingUploadKind, setPendingUploadKind] = useState("csv");
  const [uploadState, setUploadState] = useState(() => seededSelectedFiles.length ? "validated" : "idle");
  const [uploadError, setUploadError] = useState("");
  const [completionError, setCompletionError] = useState("");
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadJob, setUploadJob] = useState(null);
  const [currentWorkflow, setCurrentWorkflow] = useState("create_baseline");
  const [activeDatasetId, setActiveDatasetId] = useState(null);
  const [uploadTransfer, setUploadTransfer] = useState(null);
  const [uploadDebug, setUploadDebug] = useState({
    apiBaseConfig: CONFIGURED_API_BASE_URL || "",
    runtimeApiBaseUrl: API_BASE_URL || "",
    routeMode: API_ROUTE_MODE,
    uploadUrl: "",
    responseStatus: null,
    responseBodyOrError: "",
  });
  const [batchResults, setBatchResults] = useState([]);
  const [heartbeatTick, setHeartbeatTick] = useState(0);
  const [lastProgressAt, setLastProgressAt] = useState(() => Date.now());
  const uploadJobIdRef = useRef(null);
  const activeDatasetIdRef = useRef(null);
  const pollTimerRef = useRef(null);
  const pollFailureCountRef = useRef(0);
  const pollInFlightRef = useRef(null);
  const pollOwnerJobIdRef = useRef(null);
  const missingStatusCooldownUntilRef = useRef(0);
  const statusEndpointCooldownUntilRef = useRef(0);
  const statusEndpointFailureCountRef = useRef(0);
  const uploadStatusPathRef = useRef(null);
  const uploadInputRef = useRef(null);
  const uploadStateRef = useRef("idle");
  const pollSessionRef = useRef(0);
  const lastProgressSignatureRef = useRef("");
  const uploadInFlightRef = useRef(false);
  const telemetryStageLogRef = useRef(new Set());
  const autoStartedSignatureRef = useRef("");
  const completionNavigationTimerRef = useRef(null);
  const completionNavigationEligibleRef = useRef(false);

  const setUploadProcessingFlag = (active) => {
    if (typeof window !== "undefined") {
      window.__NERAIUM_UPLOAD_IN_PROGRESS__ = Boolean(active);
    }
  };

  const resetTelemetryStageLogs = () => {
    telemetryStageLogRef.current = new Set();
  };

  const logTelemetryStage = (stage, details = {}) => {
    console.info(`[neraium] telemetry ${stage}`, details);
  };

  const logTelemetryStageOnce = (stage, details = {}) => {
    if (telemetryStageLogRef.current.has(stage)) return;
    telemetryStageLogRef.current.add(stage);
    logTelemetryStage(stage, details);
  };

  const logTelemetryStatusProgress = (status, payload = {}) => {
    const normalized = normalizeUploadStatus(status);
    if (PARSING_COMPLETE_STATUSES.has(normalized)) {
      logTelemetryStageOnce("parsing complete", { jobId: payload?.job_id ?? uploadJobIdRef.current ?? null, status: normalized });
    }
    if (ANALYSIS_STARTED_STATUSES.has(normalized)) {
      logTelemetryStageOnce("analysis started", { jobId: payload?.job_id ?? uploadJobIdRef.current ?? null, status: normalized });
    }
  };

  useEffect(() => {
    if (seededSelectedFiles.length && typeof onInitialSelectedFilesConsumed === "function") {
      onInitialSelectedFilesConsumed();
    }
  }, [onInitialSelectedFilesConsumed, seededSelectedFiles.length]);

  useEffect(() => {
    if (!autoStartInitialFiles || seededSelectedFiles.length === 0) return;
    const signature = seededSelectedFiles
      .map((file) => [file?.name ?? "", file?.size ?? "", file?.lastModified ?? ""].join(":"))
      .join("|");
    if (!signature || signature === autoStartedSignatureRef.current) return;
    autoStartedSignatureRef.current = signature;
    resetTelemetryStageLogs();
    completionNavigationEligibleRef.current = false;
    clearCompletionNavigationTimer();
    setSelectedFiles(seededSelectedFiles);
    setUploadError("");
    setCompletionError("");
    setUploadTransfer(null);
    setUploadJob(null);
    setUploadResult(null);
    setUploadState("validated");
  }, [autoStartInitialFiles, seededSelectedFiles]);

  useEffect(() => {
    uploadStateRef.current = uploadState;
  }, [uploadState]);

  useEffect(() => {
    const active = ["running_sii", "processing", "uploading", "saving_results", "navigation_pending"].includes(String(uploadState || "").toLowerCase());
    if (!active || typeof window === "undefined") return undefined;
    const timer = window.setInterval(() => setHeartbeatTick((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [uploadState]);

  useEffect(() => {
    const signature = [
      uploadJob?.job_id ?? "",
      uploadJob?.status ?? "",
      uploadJob?.processing_state ?? "",
      uploadJob?.percent ?? uploadJob?.progress ?? "",
      uploadJob?.propagation_progress ?? "",
      uploadJob?.progress_label ?? uploadJob?.message ?? "",
    ].join("|");
    if (signature && signature !== lastProgressSignatureRef.current) {
      lastProgressSignatureRef.current = signature;
      setLastProgressAt(Date.now());
    }
  }, [uploadJob?.job_id, uploadJob?.status, uploadJob?.processing_state, uploadJob?.percent, uploadJob?.progress, uploadJob?.propagation_progress, uploadJob?.progress_label, uploadJob?.message]);

  useEffect(() => {
    if (selectedFiles.length > 0) return;
    stopUploadPolling("no_dataset_selected");
    activeDatasetIdRef.current = null;
    setActiveDatasetId(null);
    setUploadTransfer(null);
    setUploadJob(null);
    setUploadResult(null);
    setUploadError("");
    setCompletionError("");
    setUploadState("idle");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFiles.length]);

  useEffect(() => () => {
    pollSessionRef.current += 1;
    if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
    clearCompletionNavigationTimer();
    pollTimerRef.current = null;
    pollInFlightRef.current = null;
    pollOwnerJobIdRef.current = null;
  }, []);


  useEffect(() => {
    if (headless || uploadState !== "save_complete" || typeof onUploadComplete !== "function") return undefined;
    if (!completionNavigationEligibleRef.current) return undefined;
    const hasResults = Boolean(completedAnalysisForDataset(activeDatasetIdRef.current, uploadJob, uploadResult));
    if (!hasResults) return undefined;

    clearCompletionNavigationTimer();
    completionNavigationTimerRef.current = window.setTimeout(() => {
      completionNavigationTimerRef.current = null;
      void viewCompletedResults();
    }, COMPLETION_HOLD_MS);

    return () => {
      clearCompletionNavigationTimer();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headless, onUploadComplete, uploadJob, uploadResult, uploadState]);

  function clearCompletionNavigationTimer() {
    if (completionNavigationTimerRef.current && typeof window !== "undefined") {
      window.clearTimeout(completionNavigationTimerRef.current);
    }
    completionNavigationTimerRef.current = null;
  }

  function clearStoredUploadJobId() {
    if (typeof window !== "undefined") window.localStorage.removeItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY);
  }

  async function clearUploadClientState() {
    stopUploadPolling("reset_upload_client_state");
    uploadJobIdRef.current = null;
    activeDatasetIdRef.current = null;
    setActiveDatasetId(null);
    uploadStatusPathRef.current = null;
    pollFailureCountRef.current = 0;
    setSelectedFiles([]);
    setUploadTransfer(null);
    setUploadJob(null);
    setUploadResult(null);
    setUploadError("");
    setCompletionError("");
    setUploadState("idle");
    setBatchResults([]);
    completionNavigationEligibleRef.current = false;
    clearCompletionNavigationTimer();
    clearStoredUploadJobId();
    if (uploadInputRef.current) uploadInputRef.current.value = "";
    if (typeof window !== "undefined") {
      window.__NERAIUM_UPLOAD_COMPLETE__ = false;
      window.__NERAIUM_UPLOAD_IN_PROGRESS__ = false;
    }
  }

  function shouldContinuePolling(jobId) {
    return Boolean(jobId) && String(uploadJobIdRef.current ?? "") === String(jobId);
  }

  function stopUploadPolling(reason = "manual") {
    pollSessionRef.current += 1;
    if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
    pollTimerRef.current = null;
    pollInFlightRef.current = null;
    pollOwnerJobIdRef.current = null;
    if (reason !== "component_unmount") {
      setUploadProcessingFlag(false);
    }
  }

  function markUploadFailed({ message, errorType = null, jobId = null, keepStoredJobId = false, diagnostics = null }) {
    stopUploadPolling("upload_failed");
    const safeMessage = normalizeErrorMessage(message || "Telemetry analysis failed.");
    const failureDiagnostics = uploadFailureDiagnosticsFrom(diagnostics ?? {});
    setUploadError(safeMessage);
    setCompletionError("");
    setUploadState("error");
    setUploadJob((current) => ({
      ...(current ?? {}),
      job_id: jobId ?? current?.job_id ?? null,
      status: "FAILED",
      processing_state: "failed",
      progress_label: safeMessage,
      message: safeMessage,
      error: safeMessage,
      error_type: errorType,
      response_status: failureDiagnostics.responseStatus ?? current?.response_status ?? null,
      failure_url: failureDiagnostics.failureUrl ?? current?.failure_url ?? null,
      failure_phase: failureDiagnostics.failurePhase ?? current?.failure_phase ?? null,
      raw_response_body: failureDiagnostics.rawResponseBody || current?.raw_response_body || "",
      response_content_type: failureDiagnostics.responseContentType ?? current?.response_content_type ?? null,
    }));
    if (failureDiagnostics.failureUrl || failureDiagnostics.responseStatus) {
      setUploadDebug((current) => ({
        ...current,
        uploadUrl: failureDiagnostics.failureUrl ?? current.uploadUrl,
        responseStatus: failureDiagnostics.responseStatus ?? current.responseStatus,
        responseBodyOrError: failureDiagnostics.rawResponseBody || current.responseBodyOrError,
        failurePhase: failureDiagnostics.failurePhase ?? current.failurePhase ?? null,
        responseContentType: failureDiagnostics.responseContentType ?? current.responseContentType ?? null,
      }));
    }
    if (!keepStoredJobId) clearStoredUploadJobId();
  }

  async function completeUploadHandoff(completedPayload, requestedJobId) {
    const jobId = completedPayload?.dataset_id ?? completedPayload?.job_id ?? requestedJobId ?? uploadJobIdRef.current ?? null;
    if (!payloadMatchesDataset(completedPayload, jobId) || backendAnalysisState(completedPayload) !== BASELINE_ANALYSIS_STATES.COMPLETED) {
      throw new Error("The backend did not return a completed analysis for the selected dataset.");
    }
    const completedWorkflow = completedPayload?.workflow ?? "legacy_analysis";
    if (isBaselineWorkflow(completedWorkflow)) {
      const resultPath = completedPayload?.baseline_result_url ?? `/api/data/baselines/jobs/${encodeURIComponent(jobId)}`;
      const response = await apiFetch(resultPath, { accessCode });
      const baselineResult = await readJsonPayload(response, { route: resultPath, phase: "baseline_result" });
      if (!response.ok || !baselineResult?.candidate_model) {
        throw buildUploadRequestError(response, baselineResult, "baseline_result");
      }
      const activationState = baselineResult?.activation?.state ?? baselineResult?.candidate_model?.status;
      setUploadProcessingFlag(false);
      setCompletionError("");
      setUploadResult(baselineResult);
      setUploadJob({
        ...completedPayload,
        baseline_result: baselineResult,
        status: "COMPLETE",
        processing_state: "save_complete",
        percent: 100,
        progress: 100,
        progress_label: activationState === "active" ? "Behavioral Baseline Active" : "Baseline Candidate Ready",
        message: activationState === "active" ? "Behavioral Baseline Active" : "Baseline Candidate Ready",
      });
      completionNavigationEligibleRef.current = false;
      setUploadState("save_complete");
      return completedPayload;
    }
    const savedAnalysis = completedAnalysisForDataset(jobId, completedPayload);
    const savedResult = savedAnalysis ? completedPayload : null;
    setUploadProcessingFlag(false);
    setCompletionError("");
    setUploadResult(savedResult ?? completedPayload ?? null);
    setUploadJob((current) => ({
      ...(current ?? {}),
      ...(completedPayload ?? {}),
      job_id: jobId,
      status: "COMPLETE",
      processing_state: "saving_results",
      percent: 100,
      progress: 100,
      progress_label: "Persisting Behavior Baseline",
      message: "Persisting Behavior Baseline",
    }));
    setUploadState("saving_results");
    logTelemetryStage("save request started", { jobId });

    try {
      const hydration = typeof onUploadComplete === "function"
        ? await onUploadComplete(completedPayload, { navigateToGate: false })
        : null;
      logTelemetryStage("save response received", { jobId });
      const hydratedResult = hydration?.latestResult ?? null;
      const hydratedSnapshot = hydration?.latestSnapshot ?? null;
      const hydratedCurrentId = datasetIdFromPayload(hydratedSnapshot) ?? datasetIdFromPayload(hydratedResult);
      const canonicalAnalysis = completedAnalysisForDataset(jobId, hydratedSnapshot, hydratedResult, completedPayload);
      const payloadValid = hydratedCurrentId === String(jobId) && Boolean(canonicalAnalysis);
      logTelemetryStage("payload validation result", { jobId, hydratedCurrentId, valid: payloadValid });
      if (!payloadValid) {
        throw new Error("The saved analysis result did not match the selected dataset.");
      }
      const finalResult = payloadMatchesDataset(hydratedResult, jobId) ? hydratedResult : completedPayload;
      setUploadResult(finalResult);
      setUploadJob((current) => ({
        ...(current ?? {}),
        latest_result: finalResult,
        status: "COMPLETE",
        processing_state: "save_complete",
        percent: 100,
        progress: 100,
        progress_label: "Behavior Baseline Established",
        message: "Behavior Baseline Established",
      }));
      logTelemetryStage("state hydration completed", { jobId });
      completionNavigationEligibleRef.current = true;
      setUploadState("save_complete");
      return completedPayload;
    } catch (error) {
      const message = "Results were saved, but the results view could not be loaded.";
      logTelemetryStage("exception", { jobId, message: error?.message || String(error) });
      completionNavigationEligibleRef.current = false;
      setCompletionError(message);
      setUploadError("");
      setUploadJob((current) => ({
        ...(current ?? {}),
        ...(completedPayload ?? {}),
        job_id: jobId,
        status: "COMPLETE",
        processing_state: "completion_error",
        progress_label: message,
        message,
        error: error?.message || String(error),
      }));
      setUploadState("completion_error");
      return completedPayload;
    }
  }

  async function pollUploadStatus(jobId, statusUrl = null) {
    const requestedJobId = String(jobId ?? "").trim();
    if (!requestedJobId) {
      markUploadFailed({ message: "Analysis session was not created. Try again.", errorType: "missing_job_id" });
      return null;
    }
    if (pollInFlightRef.current && pollOwnerJobIdRef.current === requestedJobId) return pollInFlightRef.current;
    const pollSessionId = pollSessionRef.current + 1;
    pollSessionRef.current = pollSessionId;
    pollFailureCountRef.current = 0;
    missingStatusCooldownUntilRef.current = 0;
    statusEndpointCooldownUntilRef.current = 0;
    statusEndpointFailureCountRef.current = 0;
    uploadJobIdRef.current = requestedJobId;
    let pollingPath = normalizeUploadStatusPath(statusUrl, requestedJobId) ?? `/api/data/upload-status/${requestedJobId}`;
    uploadStatusPathRef.current = pollingPath;
    if (typeof window !== "undefined") window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, requestedJobId);
    const runPoll = async () => {
      let attempts = 0;
      while (shouldContinuePolling(requestedJobId) && pollSessionRef.current === pollSessionId) {
        attempts += 1;
        if (attempts > MAX_STATUS_POLL_ATTEMPTS) {
          throw new Error("Telemetry analysis did not report completion before the status polling timeout.");
        }
        try {
          const now = Date.now();
          const activeCooldownUntil = Math.max(Number(missingStatusCooldownUntilRef.current || 0), Number(statusEndpointCooldownUntilRef.current || 0));
          if (activeCooldownUntil > now) {
            await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, Math.max(1000, activeCooldownUntil - now)); });
            continue;
          }
          const requestPath = pollingPath;
          const pollRequestStartedAt = Date.now();
          const response = await apiFetch(requestPath, { accessCode });
          const payload = await readJsonPayload(response, { route: requestPath, phase: "poll" });
          const pollTiming = frontendPollingTiming(payload, pollRequestStartedAt);
          console.info("[neraium] frontend polling timing", {
            jobId: requestedJobId,
            stage: payload?.processing_state ?? payload?.status ?? null,
            ...pollTiming,
          });
          uploadJobIdRef.current = payload.job_id ?? requestedJobId;
          if (!response.ok) {
            if (response.status === 404 || response.status >= 500) {
              statusEndpointFailureCountRef.current += 1;
              if (isTransientUploadServiceStatus(response.status)) {
                setUploadState("running_sii");
                setUploadJob((current) => ({
                  ...(current ?? {}),
                  ...(payload ?? {}),
                  job_id: requestedJobId,
                  status: "PROCESSING",
                  processing_state: "processing",
                  progress_label: SERVICE_UNAVAILABLE_RETRY_MESSAGE,
                  message: SERVICE_UNAVAILABLE_RETRY_MESSAGE,
                  error_type: payload?.error_type ?? "service_unavailable",
                  response_status: response.status,
                  failure_url: payload?.failure_url ?? requestPath,
                  failure_phase: payload?.failure_phase ?? "poll",
                  raw_response_body: payload?.raw_response_body ?? "",
                  response_content_type: payload?.response_content_type ?? null,
                }));
              }
              if (statusEndpointFailureCountRef.current > MAX_STATUS_POLL_FAILURES) {
                pollFailureCountRef.current = MAX_STATUS_POLL_FAILURES;
                throw buildUploadRequestError(
                  response,
                  {
                    ...payload,
                    error_type: payload?.error_type || "upload_status_unavailable",
                    message: payload?.message || "Analysis status is temporarily unavailable. Retry the analysis.",
                  },
                  "poll",
                );
              }
              const cooldownMs = Math.min(15000, STATUS_ENDPOINT_FAILURE_BASE_DELAY_MS * statusEndpointFailureCountRef.current);
              statusEndpointCooldownUntilRef.current = Date.now() + cooldownMs;
              await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, cooldownMs); });
              continue;
            }
            throw buildUploadRequestError(response, payload, "poll");
          }
          statusEndpointFailureCountRef.current = 0;
          const normalizedPayload = normalizeStatusPayload({ ...payload, frontend_polling_timing: pollTiming }, requestedJobId);
          pollingPath = normalizeUploadStatusPath(normalizedPayload?.status_url, requestedJobId) ?? pollingPath;
          uploadStatusPathRef.current = pollingPath;
          setUploadJob(normalizedPayload);
          const normalizedStatus = normalizeUploadStatus(normalizedPayload.status ?? normalizedPayload.processing_state ?? normalizedPayload.worker_state);
          logTelemetryStatusProgress(normalizedStatus, normalizedPayload);
          const progressPercent = normalizedPayload.percent ?? normalizedPayload.progress ?? fallbackPercentFromStatus(normalizedStatus);
          const terminalSuccess = payloadMatchesDataset(normalizedPayload, requestedJobId) && backendAnalysisState(normalizedPayload) === BASELINE_ANALYSIS_STATES.COMPLETED;
          if (terminalSuccess) {
            logTelemetryStageOnce("analysis complete", { jobId: requestedJobId });
            const completePayload = {
              ...normalizedPayload,
              status: "COMPLETE",
              processing_state: "saving_results",
              percent: 100,
              progress: 100,
              progress_label: "Persisting Behavior Baseline",
              message: "Persisting Behavior Baseline",
            };
            setUploadJob(completePayload);
            completionNavigationEligibleRef.current = false;
            setUploadState("saving_results");
            setUploadProcessingFlag(false);
            return completePayload;
          }
          if ([BASELINE_ANALYSIS_STATES.FAILED, BASELINE_ANALYSIS_STATES.CANCELLED].includes(backendAnalysisState(normalizedPayload))) {
            throw buildUploadRequestError({ status: 500 }, normalizedPayload, "poll");
          }
          setUploadState("running_sii");
          if (typeof progressPercent === "number") {
            setUploadTransfer((current) => ({ ...(current ?? {}), percent: Math.max(current?.percent ?? 0, Math.min(progressPercent, 99)) }));
          }
          await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, STATUS_POLL_INTERVAL_MS); });
        } catch (error) {
          pollFailureCountRef.current += 1;
          console.warn("[neraium] upload status poll failed; retrying", {
            jobId: requestedJobId,
            failureCount: pollFailureCountRef.current,
            name: error?.name ?? null,
            status: error?.status ?? null,
          });
          setUploadJob((current) => ({
            ...(current ?? {}),
            poll_connection_state: "retrying",
            poll_failure_count: pollFailureCountRef.current,
            progress_label: "Analysis status connection interrupted. Retrying.",
            message: "Analysis status connection interrupted. Retrying.",
          }));
          if (pollFailureCountRef.current >= MAX_STATUS_POLL_FAILURES) {
            throw error;
          }
          const retryDelay = boundedFailureDelay(pollFailureCountRef.current);
          await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, retryDelay); });
        }
      }
      return null;
    };
    pollInFlightRef.current = runPoll()
      .then((completedPayload) => {
        if (!completedPayload) return completedPayload;
        return completeUploadHandoff(completedPayload, requestedJobId);
      })
      .catch((error) => {
        const classified = classifyUploadError(error, "poll");
        logUploadFailureDiagnostics(classified);
        logTelemetryStage("error", { jobId: requestedJobId, message: classified.message || error?.message || "Telemetry analysis failed." });
        markUploadFailed({ message: classified.message || normalizeErrorMessage(error, "Telemetry analysis failed."), errorType: classified.errorType, jobId: requestedJobId, keepStoredJobId: false, diagnostics: classified });
        throw error;
      })
      .finally(() => {
        pollInFlightRef.current = null;
        pollOwnerJobIdRef.current = null;
      });
    pollOwnerJobIdRef.current = requestedJobId;
    return pollInFlightRef.current;
  }

  function normalizeStatusPayload(payload, requestedJobId) {
    const responseDatasetId = datasetIdFromPayload(payload);
    if (!responseDatasetId) {
      throw new Error("Analysis status did not identify the selected dataset.");
    }
    if (String(responseDatasetId) !== String(requestedJobId)) {
      throw new Error("Analysis status did not match the selected dataset.");
    }
    const normalized = normalizeUploadStatus(payload?.status ?? payload?.processing_state ?? payload?.worker_state);
    return {
      ...(payload ?? {}),
      dataset_id: payload?.dataset_id ?? responseDatasetId,
      job_id: payload?.job_id ?? responseDatasetId,
      status: payload?.status ?? normalized,
      percent: payload?.percent ?? payload?.progress ?? fallbackPercentFromStatus(normalized),
      progress_label: payload?.progress_label ?? payload?.message ?? uploadStateMessage(normalized),
      message: payload?.message ?? payload?.progress_label ?? uploadStateMessage(normalized),
    };
  }

  async function handleUpload(workflow = "create_baseline") {
    if (uploadInFlightRef.current || isUploadProcessing(uploadStateRef.current)) {
      logTelemetryStage("duplicate processing prevented", { state: uploadStateRef.current });
      return;
    }
    if (!selectedFiles.length) {
      setUploadError("Choose a telemetry file.");
      return;
    }
    const file = selectedFiles[0];
    const selectedWorkflow = String(workflow || "create_baseline");
    setCurrentWorkflow(selectedWorkflow);
    const validationError = validateTelemetryFile(file, pendingUploadKind);
    if (validationError) {
      setUploadError(validationError);
      return;
    }
    uploadInFlightRef.current = true;
    setUploadError("");
    setCompletionError("");
    console.info("[neraium] upload start", {
      filename: file.name,
      size: file.size,
    });
    setUploadState("uploading");
    setUploadProcessingFlag(true);
    setUploadTransfer({ percent: 5, loaded: 0, total: file.size, label: `Sending telemetry ${formatFileSize(0)} of ${formatFileSize(file.size)}` });
    try {
      const uploadInteractionStartedAt = Date.now();
      const uploadResponse = await uploadTelemetryFileWithProgress({
        file,
        workflow: selectedWorkflow,
        apiFetch,
        requestStartedAt: uploadInteractionStartedAt,
        accessCode,
        timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS,
        onProgress: (progress) => {
          startTransition(() => {
            setUploadTransfer({ ...progress, label: formatUploadTransferLabel(progress) });
          });
        },
        onDebug: (debug) => {
          setUploadDebug((current) => ({
            ...current,
            ...debug,
          }));
        },
        onTiming: (timing) => {
          setUploadDebug((current) => ({
            ...current,
            timings: { ...(current?.timings ?? {}), [timing.event]: timing },
          }));
        },
      });
      const payload = uploadResponse.payload;
      const jobId = uploadStateView.resolveCurrentUploadJobId(payload) || payload?.job_id;
      console.info("[neraium] upload success response", {
        jobId: jobId ?? null,
        status: normalizeUploadStatus(payload?.status ?? payload?.processing_state ?? payload?.worker_state),
      });
      if (!jobId) {
        markUploadFailed({ message: "Telemetry was accepted but no analysis job was returned. Try again.", errorType: "missing_job_id" });
        return;
      }
      activeDatasetIdRef.current = String(jobId);
      setActiveDatasetId(String(jobId));
      logTelemetryStageOnce("parsing started", { filename: file.name, jobId });
      const initialPayload = normalizeStatusPayload(payload, jobId);
      logTelemetryStatusProgress(initialPayload.status ?? initialPayload.processing_state, initialPayload);
      setUploadJob(initialPayload);
      setUploadTransfer(null);
      setUploadState("running_sii");
      const completedPayload = await pollUploadStatus(jobId, payload?.status_url);
      if (!completedPayload) {
        throw new Error("Telemetry analysis ended before results were available.");
      }
    } catch (error) {
      const classified = classifyUploadError(error, error?.phase || "upload");
      logUploadFailureDiagnostics(classified);
      logTelemetryStage("error", { message: classified.message || error?.message || "Telemetry analysis failed." });
      markUploadFailed({ message: classified.message || normalizeErrorMessage(error, "Telemetry analysis failed."), errorType: classified.errorType, diagnostics: classified });
    } finally {
      uploadInFlightRef.current = false;
      setUploadProcessingFlag(false);
    }
  }

  useEffect(() => {
    if (!autoStartInitialFiles || !selectedFiles.length) return;
    if (uploadInFlightRef.current || isUploadProcessing(uploadStateRef.current)) return;
    if (uploadStateRef.current !== "validated") return;
    void handleUpload();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStartInitialFiles, selectedFiles, uploadState]);

  const readiness = uploadReadinessMessage(selectedFiles[0]);
  const hasActiveProgress = isActiveUploadProgressState(uploadState);
  const progressUploadJob = hasActiveProgress ? uploadJob : null;
  const isUploadingState = String(uploadState || "").toLowerCase() === "uploading";
  const progressUploadTransfer = hasActiveProgress && isUploadingState ? uploadTransfer : null;
  const uploadTransferPercent = progressUploadTransfer?.percent;
  const propagationPercent = progressUploadJob?.propagation_progress ?? progressUploadJob?.propagationProgress;
  const backendPercent = progressUploadJob?.percent ?? progressUploadJob?.progress;
  const statusFallbackPercent = hasActiveProgress ? fallbackPercentFromStatus(uploadState) : null;
  const uploadPercentCandidates = isUploadingState
    ? [uploadTransferPercent, backendPercent, statusFallbackPercent]
    : [propagationPercent, backendPercent, statusFallbackPercent];
  const uploadPercent = uploadPercentCandidates.find((value) => Number.isFinite(Number(value))) ?? null;
  const propagationLabel = progressUploadJob?.propagation_label ?? progressUploadJob?.propagationLabel ?? progressUploadJob?.propagation_stage ?? "";
  const statusLabel = progressUploadJob?.progress_label ?? progressUploadJob?.message ?? progressUploadTransfer?.message ?? uploadStateMessage(uploadState);
  const isProcessingQuiet = ["running_sii", "processing"].includes(String(uploadState || "").toLowerCase())
    && normalizeUploadStatus(progressUploadJob?.status ?? progressUploadJob?.processing_state) !== "complete"
    && Date.now() - lastProgressAt > 6000
    && heartbeatTick >= 0;
  const visibleStatusLabel = isProcessingQuiet ? "Analysis is still progressing..." : statusLabel;
  const queuedWorkerDetail = queuedWorkerMessage(progressUploadJob);
  const visibleProgressPercent = Number.isFinite(Number(uploadPercent))
    ? Math.max(0, Math.min(100, Math.round(Number(uploadPercent))))
    : null;
  const latestStatusMessage = completionError || uploadError || visibleStatusLabel || readiness;
  const announcedStatusMessage = latestStatusMessage;
  const analysisState = resolveBaselineAnalysisState({ selectedFiles, uploadState, uploadJob, activeDatasetId });
  const analysisResult = completedAnalysisForDataset(activeDatasetId, uploadJob, uploadResult);
  const baselineResult = uploadResult?.candidate_model ? uploadResult : uploadJob?.baseline_result ?? null;
  const baselineCompletionReady = isBaselineWorkflow(uploadJob?.workflow ?? currentWorkflow)
    && analysisState === BASELINE_ANALYSIS_STATES.COMPLETED
    && Boolean(baselineResult?.candidate_model);
  const completionReady = (
    baselineCompletionReady
    || canRenderCompletedAnalysis({ analysisState, activeDatasetId, selectedFiles, analysisResult })
  ) && ["save_complete", "complete", "navigation_pending", "completion_error"].includes(String(uploadState || "").toLowerCase());

  function handleFileSelection(event) {
    if (uploadInFlightRef.current || isUploadProcessing(uploadStateRef.current)) {
      logTelemetryStage("duplicate processing prevented", { action: "file selection", state: uploadStateRef.current });
      if (event?.target) event.target.value = "";
      return;
    }
    const files = Array.from(event?.target?.files ?? event?.dataTransfer?.files ?? []);
    resetTelemetryStageLogs();
    completionNavigationEligibleRef.current = false;
    clearCompletionNavigationTimer();
    if (files[0]) {
      logTelemetryStage("file selected", { filename: files[0].name, size: files[0].size });
    }
    stopUploadPolling("file_selection_changed");
    uploadJobIdRef.current = null;
    activeDatasetIdRef.current = null;
    setActiveDatasetId(null);
    uploadStatusPathRef.current = null;
    pollFailureCountRef.current = 0;
    setUploadTransfer(null);
    setUploadJob(null);
    setUploadResult(null);
    clearStoredUploadJobId();
    setSelectedFiles(files);
    setUploadError("");
    setCompletionError("");
    setUploadState(files.length ? "validated" : "idle");
  }

  function openFilePicker(kind = "csv") {
    if (uploadInFlightRef.current || isUploadProcessing(uploadStateRef.current)) {
      logTelemetryStage("duplicate processing prevented", { action: "open file picker", state: uploadStateRef.current });
      return;
    }
    setPendingUploadKind(kind);
    uploadInputRef.current?.click();
  }

  async function viewCompletedResults() {
    if (typeof onUploadComplete !== "function") return;
    completionNavigationEligibleRef.current = false;
    clearCompletionNavigationTimer();
    const payload = uploadJob ?? uploadResult ?? null;
    const hasResults = Boolean(completedAnalysisForDataset(activeDatasetIdRef.current, uploadJob, uploadResult));
    if (!payload || !hasResults) {
      setCompletionError("Results were saved, but the results view could not be loaded.");
      setUploadError("");
      setUploadState("completion_error");
      return;
    }

    setCompletionError("");
    setUploadState("navigation_pending");
    setUploadJob((current) => ({
      ...(current ?? {}),
      status: "COMPLETE",
      processing_state: "navigation_pending",
      progress_label: "Opening Results",
      message: "Opening Results",
    }));
    try {
      await onUploadComplete(payload, { navigateToGate: true });
      setUploadState("complete");
    } catch (error) {
      const message = "Results were saved, but the results view could not be loaded.";
      logTelemetryStage("exception", { jobId: payload?.job_id ?? payload?.current_upload?.job_id ?? uploadJobIdRef.current ?? null, message: error?.message || String(error) });
      setCompletionError(message);
      setUploadError("");
      setUploadState("completion_error");
      setUploadJob((current) => ({
        ...(current ?? {}),
        processing_state: "completion_error",
        progress_label: message,
        message,
        error: error?.message || String(error),
      }));
    }
  }

  async function retryCurrentBatch() {
    const currentJobId = String(uploadJob?.job_id ?? uploadJobIdRef.current ?? "").trim();
    if (!currentJobId) {
      await handleUpload();
      return;
    }
    setUploadError("");
    setCompletionError("");
    setUploadState("running_sii");
    setUploadProcessingFlag(true);
    try {
      const retryResponse = await retryUploadAnalysisJob({ jobId: currentJobId, apiFetch, accessCode });
      const payload = retryResponse.payload;
      const jobId = uploadStateView.resolveCurrentUploadJobId(payload) || payload?.job_id || currentJobId;
      setUploadJob(normalizeStatusPayload(payload, jobId));
      await pollUploadStatus(jobId, payload?.status_url);
    } catch (error) {
      const status = Number(error?.status ?? 0);
      if ((status === 404 || status === 410) && selectedFiles.length) {
        await handleUpload();
        return;
      }
      const classified = classifyUploadError(error, error?.phase || "upload");
      logUploadFailureDiagnostics(classified);
      markUploadFailed({ message: classified.message || normalizeErrorMessage(error, "Telemetry analysis failed."), errorType: classified.errorType, jobId: currentJobId, keepStoredJobId: true, diagnostics: classified });
    }
  }

  async function approveBaselineCandidate() {
    const candidateResult = uploadResult?.candidate_model ? uploadResult : uploadJob?.baseline_result;
    const modelId = String(candidateResult?.candidate_model?.model_id ?? "").trim();
    if (!modelId) {
      setCompletionError("The baseline candidate identifier is unavailable.");
      return;
    }
    const path = `/api/data/baselines/candidates/${encodeURIComponent(modelId)}/approve`;
    const response = await apiFetch(path, {
      method: "POST",
      accessCode,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const payload = await readJsonPayload(response, { route: path, phase: "baseline_approval" });
    if (!response.ok || !payload?.active_model) {
      setCompletionError(normalizeErrorMessage(payload?.message || "The baseline candidate could not be activated."));
      return;
    }
    const updated = {
      ...candidateResult,
      candidate_model: payload.active_model,
      activation: payload.active_model.activation,
    };
    setCompletionError("");
    setUploadResult(updated);
    setUploadJob((current) => ({
      ...(current ?? {}),
      baseline_result: updated,
      baseline_activation_state: "active",
      workflow_state: "active",
      progress_label: "Behavioral Baseline Active",
      message: "Behavioral Baseline Active",
    }));
  }

  if (headless) {
    return (
      <div className="data-connections-workspace data-connections-workspace--headless" data-testid="headless-upload-workspace" aria-live="polite">
        <span className="sr-only">{latestStatusMessage}</span>
      </div>
    );
  }

  return (
    <div className="data-connections-workspace" data-testid="upload-workspace">
      <IntakeFlowPanel
        handleUpload={(event, workflow) => {
          event?.preventDefault?.();
          void handleUpload(workflow || event?.nativeEvent?.submitter?.value || "create_baseline");
        }}
        uploadInputRef={uploadInputRef}
        handleFileSelection={handleFileSelection}
        selectedFiles={selectedFiles}
        analysisState={analysisState}
        analysisResult={analysisResult}
        baselineResult={baselineResult}
        workflow={uploadJob?.workflow ?? currentWorkflow}
        completionReady={completionReady}
        pendingUploadKind={pendingUploadKind}
        selectedFileSize={formatFileSize(selectedFiles[0]?.size ?? 0)}
        isUploadProcessing={isUploadProcessing}
        uploadState={uploadState}
        openFilePicker={openFilePicker}
        uploadJob={progressUploadJob}
        latestMessage={announcedStatusMessage}
        visibleProgressPercent={visibleProgressPercent}
        propagationLabel={propagationLabel}
        queuedWorkerDetail={queuedWorkerDetail}
        uploadTransfer={progressUploadTransfer}
        uploadDebug={uploadDebug}
        uploadStateMessage={uploadStateMessage}
        batchResults={batchResults}
        onRetryFailedUploads={() => { void retryCurrentBatch(); }}
        onReprocessCurrentBatch={() => { void retryCurrentBatch(); }}
        onResetWorkspace={() => { void clearUploadClientState(); }}
        onViewResults={() => { void viewCompletedResults(); }}
        onApproveBaseline={() => { void approveBaselineCandidate(); }}
      />
    </div>
  );
}

function normalizeUploadStatusPath(path, jobId) {
  const cleanJobId = String(jobId ?? "").trim();
  if (!path && cleanJobId) return `/api/data/upload-status/${cleanJobId}`;
  const text = String(path ?? "").trim();
  if (!text) return null;
  try {
    const url = new URL(text);
    return `${url.pathname}${url.search}`;
  } catch {
    return text.startsWith("/") ? text : `/${text}`;
  }
}
