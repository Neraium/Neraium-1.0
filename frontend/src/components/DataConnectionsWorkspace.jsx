import { lazy, startTransition, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL, API_ROUTE_MODE, CONFIGURED_API_BASE_URL } from "../config";
import {
  normalizeUploadJob,
  uploadStagePercent,
} from "../viewModels/uploadContract";
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
import { LARGE_UPLOAD_MAX_BYTES, retryUploadAnalysisJob, uploadTelemetryFileWithProgress } from "../services/api/uploadApi";
import { clearBaselineResultCache, fetchBaselineResultById } from "../services/api/baselineApi";
import { baselineIdentityFromResult, baselineRoutePath, persistBaselineSelection, readPersistedBaselineSelection } from "../viewModels/baselineSelection";
import { getCurrentWorkspaceId } from "../services/datasetSessionCache";
import IntakeFlowPanel from "./setup/IntakeFlowPanel";

const MAX_UPLOAD_BYTES = LARGE_UPLOAD_MAX_BYTES;
const LARGE_OPERATIONAL_UPLOAD_BYTES = 100 * 1024 * 1024;
const UPLOAD_REQUEST_TIMEOUT_MS = 4 * 60 * 60 * 1000;
const LAST_UPLOAD_JOB_ID_STORAGE_KEY = "neraium.last_upload_job_id";
const MAX_STATUS_POLL_FAILURES = 8;
const SERVER_ANALYSIS_TIMEOUT_MS = 30 * 60 * 1000;
const RESULT_AVAILABILITY_GRACE_MS = 5000;
const RESULT_FETCH_RETRY_INTERVAL_MS = 250;
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
  const transferComplete = Number(progress?.percent) >= 100
    || ["upload_transferred", "validating", "backend_starting"].includes(String(progress?.stage || ""));
  if (transferComplete) return `Transfer complete · ${loaded} of ${total}`;
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
  if (!file) return "";
  if (isLargeOperationalUpload(file)) {
    return "Large telemetry export detected. Processing continues in the background.";
  }
  return UPLOAD_OPERATOR_COPY.telemetryExportValidated;
}

function validateTelemetryFile(file, kind) {
  if (!file) return "Choose a telemetry file.";
  if (file.size > MAX_UPLOAD_BYTES) return `File is larger than the supported upload limit of ${formatFileSize(MAX_UPLOAD_BYTES)}.`;
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
    requestId: value.requestId ?? value.request_id ?? null,
    diagnosticTimestamp: value.diagnosticTimestamp ?? value.diagnostic_timestamp ?? null,
    jobId: value.jobId ?? value.job_id ?? null,
    datasetId: value.datasetId ?? value.dataset_id ?? null,
    uploadSessionId: value.uploadSessionId ?? value.upload_session_id ?? null,
    failedStage: value.stage ?? value.failedStage ?? value.failed_stage ?? null,
    technicalMessage: value.technicalMessage ?? value.technical_message ?? null,
    transferSucceeded: value.transferSucceeded === true || value.transfer_succeeded === true,
    fileStored: value.fileStored === true || value.file_stored === true,
    retryUrl: value.retryUrl ?? value.retry_url ?? null,
    retryable: value.retryable !== false,
  };
}

function logUploadFailureDiagnostics(value = {}) {
  const diagnostics = uploadFailureDiagnosticsFrom(value);
  console.warn("[neraium] upload request failure", {
    url: diagnostics.failureUrl,
    phase: diagnostics.failurePhase,
    status: diagnostics.responseStatus,
    errorType: value.errorType ?? value.error_type ?? null,
  });
  if (import.meta.env.DEV && diagnostics.rawResponseBody) {
    console.warn("[neraium] upload development response", diagnostics.rawResponseBody);
  }
}

function isFinalAnalysisResult(value) {
  return Boolean(
    value
    && typeof value === "object"
    && Array.isArray(value.systems)
    && Array.isArray(value.insights)
  );
}

function resolveFinalAnalysisResult(...candidates) {
  for (const candidate of candidates) {
    const result = candidate?.analysis_result
      ?? candidate?.latest_result?.analysis_result
      ?? candidate?.current_upload?.result?.analysis_result
      ?? candidate?.result?.analysis_result
      ?? candidate?.result;
    if (isFinalAnalysisResult(result)) return result;
    if (isFinalAnalysisResult(candidate)) return candidate;
  }
  return null;
}


function canonicalJobState(payload = {}) {
  const raw = String(payload?.job_state ?? payload?.jobState ?? "").trim().toLowerCase();
  if (raw) return raw;
  const normalizedStatus = normalizeUploadStatus(payload?.status ?? payload?.processing_state ?? payload?.worker_state);
  if (normalizedStatus === "complete") return "completed";
  if (["failed", "error", "validation_error", "timeout"].includes(normalizedStatus)) return "failed";
  if (normalizedStatus === "cancelled") return "cancelled";
  if (normalizedStatus === "queued") return "queued";
  return "processing";
}

function isTerminalCompletedPayload(payload = {}) {
  const state = canonicalJobState(payload);
  return state === "completed" || state === "completed_compatibility";
}

function isTerminalFailedPayload(payload = {}) {
  const state = canonicalJobState(payload);
  return state === "failed" || state === "cancelled";
}

function normalizedBaselineStateSource(value, fallback = "hydration") {
  const normalized = String(value ?? "").trim().toLowerCase().replaceAll(" ", "_");
  return ["completion_response", "hydration", "cache", "active_baseline_fetch"].includes(normalized)
    ? normalized
    : fallback;
}

export function resolveOpenBaselineIdentity({
  selectedBaselineIdentity = null,
  uploadJob = null,
  uploadResult = null,
  latestUploadResult = null,
  latestUploadSnapshot = null,
} = {}) {
  const candidates = [
    uploadJob?.baseline_result,
    uploadResult,
    latestUploadResult,
    latestUploadSnapshot?.baseline_result,
    latestUploadSnapshot,
  ].filter(Boolean);
  const selectedBaselineId = String(
    uploadJob?.selected_baseline_id
      ?? uploadResult?.selected_baseline_id
      ?? latestUploadResult?.selected_baseline_id
      ?? selectedBaselineIdentity?.baselineId
      ?? "",
  ).trim();
  const portfolioHint = String(
    uploadJob?.portfolio_id
      ?? uploadJob?.system_id
      ?? uploadResult?.portfolio_id
      ?? latestUploadResult?.portfolio_id
      ?? selectedBaselineIdentity?.portfolioId
      ?? getCurrentWorkspaceId(),
  ).trim();
  const persisted = portfolioHint
    ? readPersistedBaselineSelection(portfolioHint, selectedBaselineId || null)
    : null;
  const stateSource = normalizedBaselineStateSource(
    uploadJob?.state_source ?? selectedBaselineIdentity?.stateSource ?? persisted?.stateSource,
    persisted ? "cache" : "hydration",
  );
  const fallback = {
    ...persisted,
    ...selectedBaselineIdentity,
    ...(selectedBaselineId ? { baselineId: selectedBaselineId } : {}),
    ...(portfolioHint ? { portfolioId: portfolioHint, systemId: selectedBaselineIdentity?.systemId ?? portfolioHint } : {}),
  };

  for (const candidate of candidates) {
    const identity = baselineIdentityFromResult(candidate, fallback, stateSource);
    if (identity && (!selectedBaselineId || identity.baselineId === selectedBaselineId)) return identity;
  }
  return baselineIdentityFromResult({}, fallback, stateSource);
}

function logBaselineNavigation(event, identity, targetRoute, reason = null) {
  const details = {
    event,
    baselineId: String(identity?.baselineId ?? "").trim() || null,
    targetRoute: String(targetRoute ?? "").trim() || null,
  };
  if (reason) details.reason = reason;
  if (event === "navigation failure") console.warn("[neraium] baseline navigation", details);
  else console.info("[neraium] baseline navigation", details);
}

const BaselineDetailView = lazy(() => import("./BaselineDetailView"));

export default function DataConnectionsWorkspace({
  accessCode,
  apiFetch,
  latestUploadSnapshot,
  latestUploadResult,
  hasActiveSession = false,
  hasResumedSession = false,
  sessionStore,
  onUploadComplete,
  initialSelectedFiles = [],
  onInitialSelectedFilesConsumed,
  autoStartInitialFiles = false,
  headless = false,
  currentUser = null,
  onOpenBaseline,
  selectedBaselineIdentity = null,
}) {
  const seededSelectedFiles = useMemo(() => (Array.isArray(initialSelectedFiles) ? initialSelectedFiles : []), [initialSelectedFiles]);
  const [selectedFiles, setSelectedFiles] = useState(() => seededSelectedFiles);
  const [pendingUploadKind, setPendingUploadKind] = useState("csv");
  const [uploadState, setUploadState] = useState(() => seededSelectedFiles.length ? "validated" : "idle");
  const [uploadError, setUploadError] = useState("");
  const [completionError, setCompletionError] = useState("");
  const [uploadResult, setUploadResult] = useState(latestUploadResult);
  const [uploadJob, setUploadJob] = useState(null);
  const [currentWorkflow, setCurrentWorkflow] = useState("create_baseline");
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
  const [baselineNavigationPending, setBaselineNavigationPending] = useState(false);
  const [baselineDetailReloadKey, setBaselineDetailReloadKey] = useState(0);
  const [baselineDetailState, setBaselineDetailState] = useState(() => ({
    status: selectedBaselineIdentity?.baselineId ? "loading" : "idle",
    result: null,
    identity: null,
    message: "",
  }));
  void uploadResult;
  const uploadJobIdRef = useRef(null);
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
  const storedJobRestoreRef = useRef(false);
  const completionNavigationTimerRef = useRef(null);
  const completionNavigationEligibleRef = useRef(false);
  const baselineNavigationPendingRef = useRef(false);
  const flowOwnerRef = useRef(String(currentUser?.email ?? currentUser?.id ?? ""));
  const flowSessionRef = useRef(0);
  const selectedBaselineIdRef = useRef(String(selectedBaselineIdentity?.baselineId ?? "").trim() || null);
  const exactBaselineRequestVersionRef = useRef(0);
  const exactBaselineAbortRef = useRef(null);

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

  // Session hydration is centralized in useFacilityRuntime via
  // apiFetch("/api/data/latest-upload?include_persisted=1", { accessCode }).
  useEffect(() => {
    if (typeof window === "undefined" || selectedBaselineIdRef.current) return;
    const sessionJobId = String(sessionStore?.jobId ?? "").trim();
    if (!sessionJobId) return;
    if (!hasActiveSession && !hasResumedSession) return;
    const normalizedSessionJob = normalizeUploadJob({
      ...(sessionStore?.latestUploadSnapshot ?? {}),
      latest_result: sessionStore?.latestUploadResult ?? null,
      job_id: sessionJobId,
    });
    const sessionResult = sessionStore?.latestUploadResult ?? null;
    const hydrationSource = String(sessionStore?.uiState ?? "") === "restored" ? "cache" : "hydration";
    const hydratedIdentity = baselineIdentityFromResult(sessionResult ?? normalizedSessionJob, {}, hydrationSource);
    if (hydratedIdentity) persistBaselineSelection(hydratedIdentity);
    uploadJobIdRef.current = sessionJobId;
    uploadStatusPathRef.current = normalizeUploadStatusPath(normalizedSessionJob?.status_url, sessionJobId);
    window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, sessionJobId);
    setUploadJob({
      ...normalizedSessionJob,
      ...(hydratedIdentity ? {
        selected_baseline_id: hydratedIdentity.baselineId,
        established_baseline_id: hydratedIdentity.baselineId,
        portfolio_id: hydratedIdentity.portfolioId,
        system_id: hydratedIdentity.systemId,
        state_source: hydratedIdentity.stateSource,
      } : {}),
    });
    setUploadResult(sessionResult);
    if (["verified", "restored"].includes(String(sessionStore?.uiState ?? ""))) {
      setUploadState("complete");
      setUploadProcessingFlag(false);
      return;
    }
    if (["queued", "processing"].includes(String(sessionStore?.uiState ?? ""))) {
      setUploadState("running_sii");
      setUploadProcessingFlag(true);
      pollUploadStatus(sessionJobId, normalizedSessionJob?.status_url).catch(() => {});
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasActiveSession, hasResumedSession, sessionStore?.jobId, sessionStore?.uiState, sessionStore?.latestUploadSnapshot, sessionStore?.latestUploadResult]);

  useEffect(() => {
    if (typeof window === "undefined" || storedJobRestoreRef.current || selectedBaselineIdRef.current) return;
    if (String(sessionStore?.jobId ?? "").trim()) return;
    const storedJobId = String(window.localStorage.getItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY) ?? "").trim();
    if (!storedJobId) return;
    storedJobRestoreRef.current = true;
    const restoreStoredJob = async () => {
      const path = `/api/data/upload-status/${encodeURIComponent(storedJobId)}`;
      const response = await apiFetch(path, { accessCode });
      const payload = await readJsonPayload(response, { route: path, phase: "poll" });
      if (response.status === 404) {
        window.localStorage.removeItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY);
        return;
      }
      if (!response.ok) throw buildUploadRequestError(response, payload, "poll");
      const normalized = normalizeStatusPayload(payload, storedJobId);
      uploadJobIdRef.current = storedJobId;
      uploadStatusPathRef.current = normalizeUploadStatusPath(normalized?.status_url, storedJobId);
      setUploadJob(normalized);
      const state = normalizeUploadStatus(normalized?.processing_state ?? normalized?.status);
      if (state === "complete") {
        setUploadState("complete");
        await completeUploadHandoff(normalized, storedJobId, "cache");
      } else if (["failed", "error", "timeout", "cancelled"].includes(state)) {
        markUploadFailed({
          message: normalized?.message ?? normalized?.error ?? "Dataset import failed.",
          errorType: normalized?.error_code ?? normalized?.error_type ?? null,
          jobId: storedJobId,
          keepStoredJobId: true,
          diagnostics: normalized,
        });
      } else {
        setUploadState("running_sii");
        setUploadProcessingFlag(true);
        await pollUploadStatus(storedJobId, normalized?.status_url);
      }
    };
    restoreStoredJob().catch((error) => {
      const classified = classifyUploadError(error, "poll");
      markUploadFailed({
        message: classified.message,
        errorType: classified.errorType,
        jobId: storedJobId,
        keepStoredJobId: true,
        diagnostics: classified,
      });
    });
  // Restore is deliberately one-shot; pollUploadStatus owns subsequent state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessCode, apiFetch, sessionStore?.jobId]);

  useEffect(() => {
    if (selectedFiles.length > 0 || hasResumedSession || uploadJobIdRef.current) return;
    setUploadTransfer(null);
    setUploadJob(null);
    if (uploadStateRef.current === "validated") {
      setUploadState("idle");
    }
  }, [hasResumedSession, selectedFiles.length]);

  useEffect(() => {
    const owner = String(currentUser?.email ?? currentUser?.id ?? "");
    if (owner === flowOwnerRef.current) return;
    flowOwnerRef.current = owner;
    flowSessionRef.current += 1;
    stopUploadPolling("session_identity_changed");
    uploadInFlightRef.current = false;
    uploadJobIdRef.current = null;
    uploadStatusPathRef.current = null;
    setSelectedFiles([]);
    setUploadTransfer(null);
    setUploadJob(null);
    setUploadResult(null);
    setUploadError("");
    setCompletionError("");
    setUploadState("idle");
    clearStoredUploadJobId();
    if (uploadInputRef.current) uploadInputRef.current.value = "";
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUser?.email, currentUser?.id]);

  useEffect(() => () => {
    flowSessionRef.current += 1;
    exactBaselineRequestVersionRef.current += 1;
    exactBaselineAbortRef.current?.abort();
    uploadInFlightRef.current = false;
    pollSessionRef.current += 1;
    if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
    clearCompletionNavigationTimer();
    pollTimerRef.current = null;
    pollInFlightRef.current = null;
    pollOwnerJobIdRef.current = null;
  }, []);

  useEffect(() => {
    if (selectedBaselineIdRef.current || uploadResult?.candidate_model) return;
    setUploadResult(latestUploadResult);
  }, [latestUploadResult, uploadResult?.candidate_model]);

  useEffect(() => {
    const routeBaselineId = String(selectedBaselineIdentity?.baselineId ?? "").trim();
    const routePortfolioId = String(selectedBaselineIdentity?.portfolioId ?? "").trim();
    if (!routeBaselineId || !routePortfolioId) {
      exactBaselineRequestVersionRef.current += 1;
      exactBaselineAbortRef.current?.abort();
      selectedBaselineIdRef.current = null;
      setBaselineDetailState({ status: "idle", result: null, identity: null, message: "", notFound: false });
      return undefined;
    }

    selectedBaselineIdRef.current = routeBaselineId;
    const persisted = readPersistedBaselineSelection(routePortfolioId, routeBaselineId);
    const requestedIdentity = {
      ...persisted,
      ...selectedBaselineIdentity,
      baselineId: routeBaselineId,
      portfolioId: routePortfolioId,
    };
    exactBaselineRequestVersionRef.current += 1;
    const requestVersion = exactBaselineRequestVersionRef.current;
    exactBaselineAbortRef.current?.abort();
    const controller = new AbortController();
    exactBaselineAbortRef.current = controller;
    setBaselineDetailState({ status: "loading", result: null, identity: requestedIdentity, message: "", notFound: false });

    fetchBaselineResultById({
      apiFetch,
      accessCode,
      portfolioId: routePortfolioId,
      baselineId: routeBaselineId,
      forceRefresh: baselineDetailReloadKey > 0,
      signal: controller.signal,
    }).then(({ result, source }) => {
      if (controller.signal.aborted || exactBaselineRequestVersionRef.current !== requestVersion) return;
      if (selectedBaselineIdRef.current !== routeBaselineId) return;
      const identity = baselineIdentityFromResult(result, requestedIdentity, source);
      if (!identity || identity.baselineId !== routeBaselineId || identity.portfolioId !== routePortfolioId) {
        throw new Error("The baseline response did not match the selected route.");
      }
      persistBaselineSelection(identity);
      setBaselineDetailState({ status: "ready", result, identity, message: "", notFound: false });
    }).catch((error) => {
      if (controller.signal.aborted || error?.name === "AbortError") return;
      if (exactBaselineRequestVersionRef.current !== requestVersion || selectedBaselineIdRef.current !== routeBaselineId) return;
      const notFound = Number(error?.status ?? 0) === 404;
      setBaselineDetailState({
        status: "error",
        result: null,
        identity: requestedIdentity,
        notFound,
        message: notFound
          ? `Baseline ${routeBaselineId} was not found in portfolio ${routePortfolioId}.`
          : `Baseline ${routeBaselineId} could not be loaded. Check the connection and retry.`,
      });
    });

    return () => controller.abort();
  }, [accessCode, apiFetch, baselineDetailReloadKey, selectedBaselineIdentity]);

  useEffect(() => {
    if (headless || uploadState !== "save_complete" || typeof onUploadComplete !== "function") return undefined;
    if (!completionNavigationEligibleRef.current) return undefined;
    const hasResults = Boolean(resolveFinalAnalysisResult(uploadJob, uploadResult, latestUploadResult, latestUploadSnapshot));
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
  }, [headless, latestUploadResult, latestUploadSnapshot, onUploadComplete, uploadJob, uploadResult, uploadState]);

  function clearCompletionNavigationTimer() {
    if (completionNavigationTimerRef.current && typeof window !== "undefined") {
      window.clearTimeout(completionNavigationTimerRef.current);
    }
    completionNavigationTimerRef.current = null;
  }

  function clearStoredUploadJobId() {
    if (typeof window !== "undefined") window.localStorage.removeItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY);
  }

  function resetLocalUploadClientState(nextWorkflow = "create_baseline") {
    flowSessionRef.current += 1;
    stopUploadPolling("reset_upload_client_state");
    uploadJobIdRef.current = null;
    uploadStatusPathRef.current = null;
    pollFailureCountRef.current = 0;
    setSelectedFiles([]);
    setUploadTransfer(null);
    setUploadJob(null);
    setUploadResult(null);
    setUploadError("");
    setCompletionError("");
    setUploadState("idle");
    setCurrentWorkflow(nextWorkflow);
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

  function beginComparisonDataset() {
    resetLocalUploadClientState("analyze_new_data");
    uploadInputRef.current?.click();
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
    const resolvedJobId = jobId ?? failureDiagnostics.jobId ?? failureDiagnostics.uploadSessionId ?? null;
    setUploadError(safeMessage);
    setCompletionError("");
    setUploadState("error");
    setUploadJob((current) => ({
      ...(current ?? {}),
      job_id: resolvedJobId ?? current?.job_id ?? null,
      dataset_id: failureDiagnostics.datasetId ?? current?.dataset_id ?? null,
      upload_session_id: failureDiagnostics.uploadSessionId ?? current?.upload_session_id ?? null,
      status: "FAILED",
      processing_state: "failed",
      progress_label: safeMessage,
      message: safeMessage,
      error: safeMessage,
      error_type: errorType,
      error_code: errorType,
      failed_stage: failureDiagnostics.failedStage ?? current?.failed_stage ?? "unexpected",
      retryable: failureDiagnostics.retryable,
      transfer_succeeded: failureDiagnostics.transferSucceeded,
      file_stored: failureDiagnostics.fileStored,
      retry_url: failureDiagnostics.retryUrl ?? current?.retry_url ?? null,
      response_status: failureDiagnostics.responseStatus ?? current?.response_status ?? null,
      failure_url: failureDiagnostics.failureUrl ?? current?.failure_url ?? null,
      failure_phase: failureDiagnostics.failurePhase ?? current?.failure_phase ?? null,
      raw_response_body: failureDiagnostics.rawResponseBody || current?.raw_response_body || "",
      response_content_type: failureDiagnostics.responseContentType ?? current?.response_content_type ?? null,
      request_id: failureDiagnostics.requestId ?? current?.request_id ?? null,
      technicalMessage: failureDiagnostics.technicalMessage ?? current?.technicalMessage ?? null,
      diagnostic_timestamp: failureDiagnostics.diagnosticTimestamp ?? current?.diagnostic_timestamp ?? new Date().toISOString(),
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
    if (resolvedJobId && (keepStoredJobId || failureDiagnostics.fileStored)) {
      uploadJobIdRef.current = resolvedJobId;
      if (typeof window !== "undefined") window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, resolvedJobId);
    } else if (!keepStoredJobId) {
      clearStoredUploadJobId();
    }
  }

  async function completeUploadHandoff(completedPayload, requestedJobId, identitySource = "completion_response") {
    const jobId = completedPayload?.job_id ?? requestedJobId ?? uploadJobIdRef.current ?? null;
    const datasetId = completedPayload?.dataset_id ?? null;
    const completedWorkflow = completedPayload?.workflow ?? "legacy_analysis";
    if (isBaselineWorkflow(completedWorkflow)) {
      const resultPath = completedPayload?.baseline_result_url ?? `/api/data/baselines/jobs/${encodeURIComponent(jobId)}`;
      const resultDeadline = Date.now() + RESULT_AVAILABILITY_GRACE_MS;
      let response;
      let baselineResult;
      do {
        response = await apiFetch(resultPath, { accessCode });
        baselineResult = await readJsonPayload(response, { route: resultPath, phase: "baseline_result" });
        if (response.ok && baselineResult?.candidate_model) break;
        if (response.status !== 404 || Date.now() >= resultDeadline) {
          throw buildUploadRequestError(response, baselineResult, "baseline_result");
        }
        await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, RESULT_FETCH_RETRY_INTERVAL_MS); });
      } while (Date.now() < resultDeadline);
      if (!response?.ok || !baselineResult?.candidate_model) {
        throw buildUploadRequestError(response ?? { status: 404 }, baselineResult ?? {}, "baseline_result");
      }
      const returnedJobId = String(baselineResult?.job_id ?? "").trim();
      if (returnedJobId && String(jobId) !== returnedJobId) {
        throw new Error("The completed baseline did not match the requested import job.");
      }
      const identity = baselineIdentityFromResult(baselineResult, {
        jobId,
        uploadId: completedPayload?.upload_id ?? jobId,
        datasetId,
      }, identitySource);
      if (!identity) throw new Error("The completed baseline identifiers were unavailable.");
      uploadJobIdRef.current = identity.jobId ?? jobId;
      clearBaselineResultCache({ portfolioId: identity.portfolioId, baselineId: identity.baselineId });
      persistBaselineSelection(identity);

      const activationState = baselineResult?.activation?.state ?? baselineResult?.candidate_model?.status;
      setUploadProcessingFlag(false);
      setCompletionError("");
      setUploadResult(baselineResult);
      setUploadJob({
        ...completedPayload,
        job_id: identity.jobId,
        upload_id: identity.uploadId,
        dataset_id: identity.datasetId,
        baseline_candidate_id: identity.candidateId,
        established_baseline_id: identity.baselineId,
        selected_baseline_id: identity.baselineId,
        portfolio_id: identity.portfolioId,
        system_id: identity.systemId,
        state_source: identity.stateSource,
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
      return { ...completedPayload, ...identity, baseline_result: baselineResult };
    }
    const savedResult = uploadStateView.resolveCurrentUploadResult(completedPayload) ?? (uploadStateView.hasFullUploadResult(completedPayload) ? completedPayload : null);
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
      const hydratedResult = hydration?.latestResult ?? savedResult ?? uploadStateView.resolveCurrentUploadResult(hydration?.latestSnapshot) ?? null;
      const hydratedSnapshot = hydration?.latestSnapshot ?? latestUploadSnapshot ?? null;
      const payloadValid = Boolean(resolveFinalAnalysisResult(completedPayload, hydratedResult, hydratedSnapshot, uploadResult, latestUploadResult, latestUploadSnapshot));
      logTelemetryStage("payload validation result", { jobId, valid: payloadValid });
      if (!payloadValid) {
        throw new Error("The saved analysis result could not be opened. Refresh and retry.");
      }
      const finalResult = hydratedResult ?? savedResult ?? completedPayload;
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
    logTelemetryStage("job polling started", { jobId: requestedJobId, statusPath: pollingPath });
    const runPoll = async () => {
      const pollingStartedAt = Date.now();
      let terminalWithoutResultAt = null;
      while (shouldContinuePolling(requestedJobId) && pollSessionRef.current === pollSessionId) {
        if (Date.now() - pollingStartedAt > SERVER_ANALYSIS_TIMEOUT_MS) {
          throw Object.assign(new Error("The server did not finish processing within 30 minutes."), {
            name: "UploadRequestError",
            phase: "poll",
            errorType: "server_timeout",
            failedStage: "baseline_creation",
            retryable: true,
            jobId: requestedJobId,
          });
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
          const returnedJobId = String(payload?.job_id ?? "").trim();
          if (returnedJobId && returnedJobId !== requestedJobId) {
            throw Object.assign(new Error("The status response did not match the requested processing job."), {
              name: "UploadRequestError",
              phase: "poll",
              errorType: "job_identity_mismatch",
              failedStage: "import",
              retryable: false,
              jobId: requestedJobId,
              datasetId: payload?.dataset_id ?? null,
              technicalMessage: `Expected job ${requestedJobId}, received ${returnedJobId}`,
              terminalJobFailure: true,
            });
          }
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
          const terminalSuccess = isTerminalCompletedPayload(normalizedPayload);
          const resultAvailable = normalizedPayload?.result_available === true
            && (!isBaselineWorkflow(normalizedPayload?.workflow) || normalizedPayload?.baseline_result_available === true);
          if (terminalSuccess && resultAvailable) {
            terminalWithoutResultAt = null;
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
          if (isTerminalFailedPayload(normalizedPayload)) {
            const terminalError = buildUploadRequestError({ status: response.status }, normalizedPayload, "poll");
            terminalError.terminalJobFailure = true;
            throw terminalError;
          }
          if (terminalSuccess && !resultAvailable) {
            terminalWithoutResultAt ??= Date.now();
            if (Date.now() - terminalWithoutResultAt >= RESULT_AVAILABILITY_GRACE_MS) {
              throw Object.assign(new Error("Processing completed, but the committed result is not retrievable."), {
                name: "UploadRequestError",
                status: response.status,
                phase: "poll",
                errorType: "result_persistence_failed",
                failedStage: "baseline_creation",
                retryable: true,
                jobId: requestedJobId,
                datasetId: normalizedPayload?.dataset_id ?? null,
                requestId: normalizedPayload?.request_id ?? null,
                technicalMessage: "Terminal job state remained visible without result availability.",
                terminalJobFailure: true,
              });
            }
            setUploadJob({
              ...normalizedPayload,
              status: "PROCESSING",
              processing_state: "saving_result",
              progress_label: "Waiting for the committed baseline result...",
              message: "Waiting for the committed baseline result...",
            });
          } else {
            terminalWithoutResultAt = null;
          }
          setUploadState("running_sii");
          await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, STATUS_POLL_INTERVAL_MS); });
        } catch (error) {
          if (error?.terminalJobFailure === true) throw error;
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
        markUploadFailed({
          message: classified.message || normalizeErrorMessage(error, "Telemetry analysis failed."),
          errorType: classified.errorType,
          jobId: requestedJobId,
          keepStoredJobId: true,
          diagnostics: { ...classified, fileStored: classified.fileStored || classified.errorType !== "file_storage_failed" },
        });
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
    const normalized = normalizeUploadStatus(payload?.status ?? payload?.processing_state ?? payload?.worker_state);
    return {
      ...(payload ?? {}),
      job_id: payload?.job_id ?? requestedJobId,
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
    const flowSessionId = flowSessionRef.current;
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
    console.info("[neraium] baseline submission initiated", {
      filename: file.name,
      size: file.size,
      transport: import.meta.env.PROD || file.size > 250 * 1024 * 1024 ? "presigned_s3_put" : "direct_multipart",
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
        preferStoredUpload: import.meta.env.PROD,
        requestStartedAt: uploadInteractionStartedAt,
        accessCode,
        timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS,
        onProgress: (progress) => {
          if (flowSessionRef.current !== flowSessionId) return;
          startTransition(() => {
            setUploadTransfer({ ...progress, label: formatUploadTransferLabel(progress) });
          });
        },
        onDebug: (debug) => {
          if (flowSessionRef.current !== flowSessionId) return;
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
      if (flowSessionRef.current !== flowSessionId) return;
      const payload = uploadResponse.payload;
      const jobId = String(payload?.job_id ?? "").trim() || null;
      console.info("[neraium] analysis job response received", {
        jobId: jobId ?? null,
        filename: file.name,
        size: file.size,
        status: normalizeUploadStatus(payload?.status ?? payload?.processing_state ?? payload?.worker_state),
      });
      if (!jobId) {
        markUploadFailed({
          message: "The file was transferred successfully, but Neraium could not begin processing it.",
          errorType: "dataset_record_creation_failed",
          jobId: payload?.upload_session_id ?? null,
          keepStoredJobId: payload?.file_stored === true,
          diagnostics: {
            failedStage: "dataset_creation",
            transferSucceeded: payload?.transfer_succeeded === true,
            fileStored: payload?.file_stored === true,
            retryable: true,
          },
        });
        return;
      }
      logTelemetryStageOnce("parsing started", { filename: file.name, jobId });
      const initialPayload = normalizeStatusPayload(payload, jobId);
      logTelemetryStatusProgress(initialPayload.status ?? initialPayload.processing_state, initialPayload);
      setUploadJob(initialPayload);
      setUploadTransfer((current) => ({
        ...(current ?? {}),
        stage: "upload_transferred",
        loaded: file.size,
        total: file.size,
        percent: 100,
        speedBytesPerSecond: 0,
        label: `Transfer complete · ${formatFileSize(file.size)} of ${formatFileSize(file.size)}`,
        message: "File transferred successfully.",
      }));
      setUploadState("running_sii");
      await pollUploadStatus(jobId, payload?.status_url);
    } catch (error) {
      if (flowSessionRef.current !== flowSessionId) return;
      const classified = classifyUploadError(error, error?.phase || "upload");
      logUploadFailureDiagnostics(classified);
      logTelemetryStage("error", { message: classified.message || error?.message || "Telemetry analysis failed." });
      markUploadFailed({
        message: classified.message || normalizeErrorMessage(error, "Telemetry analysis failed."),
        errorType: classified.errorType,
        jobId: classified.jobId ?? classified.uploadSessionId ?? null,
        keepStoredJobId: classified.fileStored || classified.transferSucceeded,
        diagnostics: classified,
      });
    } finally {
      if (flowSessionRef.current === flowSessionId) {
        uploadInFlightRef.current = false;
        setUploadProcessingFlag(false);
      }
    }
  }

  useEffect(() => {
    if (!autoStartInitialFiles || !selectedFiles.length) return;
    if (uploadInFlightRef.current || isUploadProcessing(uploadStateRef.current)) return;
    if (uploadStateRef.current !== "validated") return;
    void handleUpload();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStartInitialFiles, selectedFiles, uploadState]);

  const selectedFileValidationError = selectedFiles.length
    ? validateTelemetryFile(selectedFiles[0], pendingUploadKind)
    : uploadError;
  const readiness = selectedFileValidationError || uploadReadinessMessage(selectedFiles[0]);
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
  const resultBaselineId = String(
    uploadResult?.established_baseline_id
      ?? uploadResult?.candidate_model?.baseline_id
      ?? uploadResult?.candidate_model?.model_id
      ?? uploadJob?.baseline_result?.established_baseline_id
      ?? uploadJob?.baseline_result?.candidate_model?.model_id
      ?? "",
  ).trim();
  const selectedCompletionBaselineId = String(uploadJob?.selected_baseline_id ?? "").trim();
  const baselineResult = selectedCompletionBaselineId && resultBaselineId && selectedCompletionBaselineId !== resultBaselineId
    ? null
    : uploadResult?.candidate_model ? uploadResult : uploadJob?.baseline_result ?? null;

  function handleFileSelection(event) {
    if (uploadInFlightRef.current || isUploadProcessing(uploadStateRef.current)) {
      logTelemetryStage("duplicate processing prevented", { action: "file selection", state: uploadStateRef.current });
      if (event?.target) event.target.value = "";
      return;
    }
    const files = Array.from(event?.target?.files ?? event?.dataTransfer?.files ?? []);
    flowSessionRef.current += 1;
    resetTelemetryStageLogs();
    completionNavigationEligibleRef.current = false;
    clearCompletionNavigationTimer();
    if (files[0]) {
      logTelemetryStage("file selected", { filename: files[0].name, size: files[0].size });
    }
    stopUploadPolling("file_selection_changed");
    uploadJobIdRef.current = null;
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

  function chooseAnotherFile() {
    resetLocalUploadClientState(currentWorkflow === "analyze_new_data" ? "analyze_new_data" : "create_baseline");
    window.setTimeout(() => uploadInputRef.current?.click(), 0);
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
    const payload = uploadJob ?? uploadResult ?? latestUploadResult ?? latestUploadSnapshot ?? null;
    const hasResults = Boolean(resolveFinalAnalysisResult(uploadJob, uploadResult, latestUploadResult, latestUploadSnapshot));
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
      const jobId = String(payload?.job_id ?? "").trim() || currentJobId;
      setUploadJob(normalizeStatusPayload(payload, jobId));
      await pollUploadStatus(jobId, payload?.status_url);
    } catch (error) {
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
      return false;
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
      return null;
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
    const identity = baselineIdentityFromResult(updated, selectedBaselineIdentity ?? {}, "completion_response");
    if (identity) persistBaselineSelection(identity);
    return updated;
  }

  async function openCompletedBaseline() {
    if (baselineNavigationPendingRef.current) return;

    let selectedResult = uploadResult?.candidate_model ? uploadResult : uploadJob?.baseline_result ?? null;
    const activationState = selectedResult?.activation?.state ?? selectedResult?.candidate_model?.status;
    if (selectedResult?.candidate_model && activationState === "awaiting_approval") {
      selectedResult = await approveBaselineCandidate();
      if (!selectedResult) return;
    }

    const identity = resolveOpenBaselineIdentity({
      selectedBaselineIdentity,
      uploadJob,
      uploadResult: selectedResult ?? uploadResult,
      latestUploadResult,
      latestUploadSnapshot,
    });
    const targetRoute = baselineRoutePath(identity?.portfolioId, identity?.baselineId);
    logBaselineNavigation("button activated", identity, targetRoute);
    logBaselineNavigation("selected baseline ID", identity, targetRoute);
    logBaselineNavigation("generated target route", identity, targetRoute);

    if (!identity?.baselineId || !targetRoute) {
      const message = "The selected baseline cannot be opened because its baseline ID is unavailable.";
      setCompletionError(message);
      setUploadError("");
      setUploadState("completion_error");
      logBaselineNavigation("navigation failure", identity, targetRoute, "missing_baseline_identity");
      return;
    }
    if (typeof onOpenBaseline !== "function") {
      const message = `Baseline ${identity.baselineId} could not be opened because navigation is unavailable.`;
      setCompletionError(message);
      setUploadError("");
      setUploadState("completion_error");
      logBaselineNavigation("navigation failure", identity, targetRoute, "navigation_unavailable");
      return;
    }

    baselineNavigationPendingRef.current = true;
    setBaselineNavigationPending(true);
    setCompletionError("");
    try {
      const navigated = await onOpenBaseline(identity);
      if (navigated !== true) throw new Error("The application router rejected the baseline route.");
      baselineNavigationPendingRef.current = false;
      setBaselineNavigationPending(false);
      logBaselineNavigation("navigation success", identity, targetRoute);
    } catch {
      baselineNavigationPendingRef.current = false;
      setBaselineNavigationPending(false);
      const message = `Baseline ${identity.baselineId} could not be opened. Please retry.`;
      setCompletionError(message);
      setUploadError("");
      setUploadState("completion_error");
      logBaselineNavigation("navigation failure", identity, targetRoute, "router_rejected");
    }
  }

  if (headless) {
    return (
      <div className="data-connections-workspace data-connections-workspace--headless" data-testid="headless-upload-workspace" aria-live="polite">
        <span className="sr-only">{latestStatusMessage}</span>
      </div>
    );
  }

  if (selectedBaselineIdentity?.baselineId && selectedBaselineIdentity?.portfolioId) {
    return (
      <Suspense fallback={<div className="baseline-detail-route" role="status" aria-live="polite">Opening selected baseline…</div>}>
        <BaselineDetailView
          routeIdentity={selectedBaselineIdentity}
          detailState={baselineDetailState}
          onRetry={() => setBaselineDetailReloadKey((value) => value + 1)}
        />
      </Suspense>
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
        latestUploadSnapshot={latestUploadSnapshot}
        baselineResult={baselineResult}
        workflow={uploadJob?.workflow ?? currentWorkflow}
        pendingUploadKind={pendingUploadKind}
        selectedFileSize={formatFileSize(selectedFiles[0]?.size ?? 0)}
        fileValidationError={selectedFileValidationError}
        isUploadProcessing={isUploadProcessing}
        uploadState={uploadState}
        openFilePicker={openFilePicker}
        uploadJob={uploadJob}
        latestMessage={announcedStatusMessage}
        visibleProgressPercent={visibleProgressPercent}
        propagationLabel={propagationLabel}
        queuedWorkerDetail={queuedWorkerDetail}
        uploadTransfer={uploadTransfer}
        uploadDebug={uploadDebug}
        uploadStateMessage={uploadStateMessage}
        batchResults={batchResults}
        onRetryFailedUploads={() => { void retryCurrentBatch(); }}
        onReprocessCurrentBatch={() => { void retryCurrentBatch(); }}
        onResetWorkspace={() => { resetLocalUploadClientState(currentWorkflow === "analyze_new_data" ? "analyze_new_data" : "create_baseline"); }}
        onChooseAnotherFile={chooseAnotherFile}
        onViewResults={() => { void viewCompletedResults(); }}
        onOpenBaseline={() => { void openCompletedBaseline(); }}
        baselineNavigationPending={baselineNavigationPending}
        onImportComparisonDataset={beginComparisonDataset}
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
