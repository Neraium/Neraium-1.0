import { lazy, startTransition, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL, API_ROUTE_MODE, CONFIGURED_API_BASE_URL } from "../config";
import { normalizeUploadJob } from "../viewModels/uploadContract";
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
import { clearBaselineResultCache, fetchBaselineResultById, recoverBaselineCreation } from "../services/api/baselineApi";
import { normalizeBaselineCreationResponse } from "../contracts/baselineCreation";
import { baselineIdentityFromResult, baselineRoutePath, persistBaselineSelection, readPersistedBaselineSelection } from "../viewModels/baselineSelection";
import { getCurrentWorkspaceId } from "../services/datasetSessionCache";
import { authoritativeJobState, isPollableJobState } from "../viewModels/uploadJobState";
import IntakeFlowPanel from "./setup/IntakeFlowPanel";

const MAX_UPLOAD_BYTES = LARGE_UPLOAD_MAX_BYTES;
const LARGE_OPERATIONAL_UPLOAD_BYTES = 100 * 1024 * 1024;
const UPLOAD_REQUEST_TIMEOUT_MS = 4 * 60 * 60 * 1000;
const LEGACY_LAST_UPLOAD_JOB_ID_STORAGE_KEY = "neraium.last_upload_job_id";
const UPLOAD_JOB_STORAGE_VERSION = "v2";
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

function uploadJobStorageKey(kind, datasetScopeKey, currentUser) {
  const workspace = encodeURIComponent(String(datasetScopeKey || "anonymous"));
  const owner = encodeURIComponent(String(currentUser?.id ?? currentUser?.email ?? "anonymous"));
  return `neraium.upload_job.${kind}.${UPLOAD_JOB_STORAGE_VERSION}:${owner}:${workspace}`;
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
  if (!Number.isFinite(updatedAt)) return "at an unknown time";
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
  const executionState = authoritativeJobState(uploadJob);
  const workerState = String(uploadJob?.worker_state ?? uploadJob?.workerState ?? "").toLowerCase();
  const lastUpdate = uploadJob?.job_progress?.updated_at ?? uploadJob?.worker_last_update_at ?? uploadJob?.worker_last_update ?? uploadJob?.updated_at ?? "";
  if (executionState === "queued") return uploadJob?.queue_position ? `Queued · position ${uploadJob.queue_position}` : "Queued · waiting for worker claim";
  if (executionState === "claimed") return "Claimed by worker · processing has not started";
  if (executionState === "processing" && ["active", "running"].includes(workerState)) {
    return `Analysis active · updated ${formatAnalysisUpdateTime(lastUpdate, now)}`;
  }
  if (executionState === "processing") return "Processing confirmed by backend";
  if (executionState === "waiting") return uploadJob?.job_progress?.visibility_message || "Status connection interrupted · backend state preserved";
  if (executionState === "stalled") return "Stalled · no recent job heartbeat";
  return "";
}

function isActiveUploadProgressState(uploadState) {
  return ["uploading", "queued", "claimed", "running_sii", "processing", "waiting", "stalled", "saving_results", "save_complete", "navigation_pending", "completion_error", "complete"].includes(String(uploadState || "").toLowerCase());
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
  completedBaselineIdentity = null,
} = {}) {
  const candidates = [
    completedBaselineIdentity,
    uploadJob?.baseline_result,
    uploadResult,
    latestUploadResult,
    latestUploadSnapshot?.baseline_result,
    latestUploadSnapshot,
  ].filter(Boolean);
  const selectedBaselineId = String(
    uploadJob?.baselineId
      ?? uploadResult?.baselineId
      ?? latestUploadResult?.baselineId
      ?? completedBaselineIdentity?.baselineId
      ?? selectedBaselineIdentity?.baselineId
      ?? "",
  ).trim();
  const portfolioHint = String(
    uploadJob?.portfolioId
      ?? uploadResult?.portfolioId
      ?? latestUploadResult?.portfolioId
      ?? completedBaselineIdentity?.portfolioId
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
    ...completedBaselineIdentity,
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
  onCloseBaseline = null,
  onReturnToPortfolio = null,
  selectedBaselineIdentity = null,
  activeBaselineIdentity = null,
  comparisonMode = false,
  autoOpenBaselineReady = false,
  datasetScopeKey = "anonymous",
}) {
  const seededSelectedFiles = useMemo(() => (Array.isArray(initialSelectedFiles) ? initialSelectedFiles : []), [initialSelectedFiles]);
  const [selectedFiles, setSelectedFiles] = useState(() => seededSelectedFiles);
  const [pendingUploadKind, setPendingUploadKind] = useState("csv");
  const [uploadState, setUploadState] = useState(() => seededSelectedFiles.length ? "validated" : "idle");
  const [uploadError, setUploadError] = useState("");
  const [completionError, setCompletionError] = useState("");
  const [uploadResult, setUploadResult] = useState(latestUploadResult);
  const [uploadJob, setUploadJob] = useState(null);
  const [recentJob, setRecentJob] = useState(null);
  const [reconciliationMessage, setReconciliationMessage] = useState("");
  const initialWorkflow = comparisonMode ? "analyze_new_data" : "create_baseline";
  const [currentWorkflow, setCurrentWorkflow] = useState(initialWorkflow);
  const currentWorkflowRef = useRef(initialWorkflow);
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
  const pollDelayResolveRef = useRef(null);
  const pollFailureCountRef = useRef(0);
  const pollInFlightRef = useRef(null);
  const pollOwnerJobIdRef = useRef(null);
  const pollAbortControllerRef = useRef(null);
  const missingStatusCooldownUntilRef = useRef(0);
  const statusEndpointCooldownUntilRef = useRef(0);
  const statusEndpointFailureCountRef = useRef(0);
  const uploadStatusPathRef = useRef(null);
  const uploadInputRef = useRef(null);
  const uploadStateRef = useRef("idle");
  const pollSessionRef = useRef(0);
  const uploadInFlightRef = useRef(false);
  const telemetryStageLogRef = useRef(new Set());
  const autoStartedSignatureRef = useRef("");
  const reconciledJobRef = useRef("");
  const reconcileAbortControllerRef = useRef(null);
  const completionNavigationTimerRef = useRef(null);
  const completionNavigationEligibleRef = useRef(false);
  const baselineNavigationPendingRef = useRef(false);
  const completedBaselineIdentityRef = useRef(null);
  const openCompletedBaselineRef = useRef(null);
  const flowOwnerRef = useRef(`${String(currentUser?.email ?? currentUser?.id ?? "")}:${String(datasetScopeKey)}`);
  const flowSessionRef = useRef(0);
  const selectedBaselineIdRef = useRef(String(selectedBaselineIdentity?.baselineId ?? "").trim() || null);
  const exactBaselineRequestVersionRef = useRef(0);
  const exactBaselineAbortRef = useRef(null);
  const rememberedJobStorageKey = useMemo(
    () => uploadJobStorageKey("remembered", datasetScopeKey, currentUser),
    [currentUser, datasetScopeKey],
  );
  const ignoredJobStorageKey = useMemo(
    () => uploadJobStorageKey("ignored", datasetScopeKey, currentUser),
    [currentUser, datasetScopeKey],
  );

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
      logTelemetryStageOnce("parsing complete", { jobId: payload?.jobId ?? payload?.job_id ?? uploadJobIdRef.current ?? null, status: normalized });
    }
    if (ANALYSIS_STARTED_STATUSES.has(normalized)) {
      logTelemetryStageOnce("analysis started", { jobId: payload?.jobId ?? payload?.job_id ?? uploadJobIdRef.current ?? null, status: normalized });
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
    completedBaselineIdentityRef.current = null;
    setUploadState("validated");
  }, [autoStartInitialFiles, seededSelectedFiles]);

  useEffect(() => {
    uploadStateRef.current = uploadState;
  }, [uploadState]);

  // A latest-upload snapshot or browser key is only a candidate. The job-specific
  // endpoint must confirm it in the current authenticated scope before the UI is
  // allowed to enter a blocking/progress state.
  useEffect(() => {
    if (typeof window === "undefined" || selectedBaselineIdRef.current) return;
    const sessionJobId = String(sessionStore?.jobId ?? "").trim();
    const rememberedJobId = readRememberedUploadJobId();
    const candidateJobId = sessionJobId || rememberedJobId;
    if (!candidateJobId) return;
    const reconciliationKey = `${rememberedJobStorageKey}:${candidateJobId}`;
    if (reconciledJobRef.current === reconciliationKey) return;
    reconciledJobRef.current = reconciliationKey;
    reconcileAbortControllerRef.current?.abort();
    const controller = new AbortController();
    reconcileAbortControllerRef.current = controller;
    const sourcePayload = sessionJobId
      ? {
        ...(sessionStore?.latestUploadSnapshot ?? {}),
        latest_result: sessionStore?.latestUploadResult ?? null,
        job_id: sessionJobId,
      }
      : null;
    const identitySource = String(sessionStore?.uiState ?? "") === "restored" ? "cache" : "hydration";
    const normalizedSource = sourcePayload ? normalizeStatusPayload(sourcePayload, sessionJobId) : null;
    if (normalizedSource && authoritativeJobState(normalizedSource) === "completed") {
      const sessionResult = sessionStore?.latestUploadResult ?? null;
      const hydratedIdentity = baselineIdentityFromResult(sessionResult ?? normalizedSource, {}, identitySource);
      if (hydratedIdentity) {
        completedBaselineIdentityRef.current = hydratedIdentity;
        persistBaselineSelection(hydratedIdentity);
      }
      setUploadJob({
        ...normalizedSource,
        ...(hydratedIdentity ? {
          baselineId: hydratedIdentity.baselineId,
          portfolioId: hydratedIdentity.portfolioId,
          systemId: hydratedIdentity.systemId,
          state_source: hydratedIdentity.stateSource,
        } : {}),
      });
      uploadJobIdRef.current = sessionJobId;
      uploadStatusPathRef.current = normalizeUploadStatusPath(normalizedSource?.status_url, sessionJobId);
      setUploadResult(sessionResult);
      setUploadState("complete");
      setUploadProcessingFlag(false);
      return;
    }
    void reconcileRememberedJob(candidateJobId, { sourcePayload, identitySource, signal: controller.signal });
    return () => controller.abort();
  // Polling owns changes after the one job-specific reconciliation request.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessCode, apiFetch, rememberedJobStorageKey, sessionStore?.jobId, sessionStore?.uiState]);

  useEffect(() => {
    if (selectedFiles.length > 0 || hasResumedSession || uploadJobIdRef.current) return;
    setUploadTransfer(null);
    setUploadJob(null);
    if (uploadStateRef.current === "validated") {
      setUploadState("idle");
    }
  }, [hasResumedSession, selectedFiles.length]);

  useEffect(() => {
    const owner = `${String(currentUser?.email ?? currentUser?.id ?? "")}:${String(datasetScopeKey)}`;
    if (owner === flowOwnerRef.current) return;
    flowOwnerRef.current = owner;
    flowSessionRef.current += 1;
    reconciledJobRef.current = "";
    reconcileAbortControllerRef.current?.abort();
    stopUploadPolling("session_identity_changed");
    uploadInFlightRef.current = false;
    uploadJobIdRef.current = null;
    uploadStatusPathRef.current = null;
    setSelectedFiles([]);
    setUploadTransfer(null);
    setUploadJob(null);
    setUploadResult(null);
    setRecentJob(null);
    setReconciliationMessage("");
    completedBaselineIdentityRef.current = null;
    setUploadError("");
    setCompletionError("");
    setUploadState("idle");
    if (uploadInputRef.current) uploadInputRef.current.value = "";
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUser?.email, currentUser?.id, datasetScopeKey]);

  useEffect(() => () => {
    flowSessionRef.current += 1;
    exactBaselineRequestVersionRef.current += 1;
    exactBaselineAbortRef.current?.abort();
    reconcileAbortControllerRef.current?.abort();
    pollAbortControllerRef.current?.abort();
    uploadInFlightRef.current = false;
    pollSessionRef.current += 1;
    clearPollDelay();
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
      scopeKey: datasetScopeKey,
      portfolioId: routePortfolioId,
      baselineId: routeBaselineId,
      forceRefresh: baselineDetailReloadKey > 0,
      signal: controller.signal,
    }).then(({ result, source, diagnostics }) => {
      if (controller.signal.aborted || exactBaselineRequestVersionRef.current !== requestVersion) return;
      if (selectedBaselineIdRef.current !== routeBaselineId) return;
      const identity = baselineIdentityFromResult(result, requestedIdentity, source);
      if (!identity || identity.baselineId !== routeBaselineId || identity.portfolioId !== routePortfolioId) {
        throw new Error("The baseline response did not match the selected route.");
      }
      persistBaselineSelection(identity);
      setBaselineDetailState({ status: "ready", result, identity, diagnostics, message: "", notFound: false });
    }).catch((error) => {
      if (controller.signal.aborted || error?.name === "AbortError") return;
      if (exactBaselineRequestVersionRef.current !== requestVersion || selectedBaselineIdRef.current !== routeBaselineId) return;
      const notFound = Number(error?.status ?? 0) === 404;
      setBaselineDetailState({
        status: "error",
        result: null,
        identity: requestedIdentity,
        notFound,
        errorType: error?.errorType ?? "baseline_request_failed",
        httpStatus: Number(error?.status ?? 0) || null,
        requestId: error?.requestId ?? null,
        elapsedMs: error?.elapsedMs ?? null,
        message: notFound
          ? `Baseline ${routeBaselineId} was not found in portfolio ${routePortfolioId}.`
          : error?.message || `Baseline ${routeBaselineId} could not be loaded. Check the connection and retry.`,
      });
    });

    return () => controller.abort();
  }, [accessCode, apiFetch, baselineDetailReloadKey, datasetScopeKey, selectedBaselineIdentity]);

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

  function readRememberedUploadJobId() {
    if (typeof window === "undefined") return "";
    try {
      return String(
        window.localStorage.getItem(rememberedJobStorageKey)
          ?? window.localStorage.getItem(LEGACY_LAST_UPLOAD_JOB_ID_STORAGE_KEY)
          ?? "",
      ).trim();
    } catch {
      return "";
    }
  }

  function rememberUploadJobId(jobId) {
    if (typeof window === "undefined" || !jobId) return;
    try {
      window.localStorage.setItem(rememberedJobStorageKey, String(jobId));
      window.localStorage.removeItem(LEGACY_LAST_UPLOAD_JOB_ID_STORAGE_KEY);
      if (window.localStorage.getItem(ignoredJobStorageKey) === String(jobId)) {
        window.localStorage.removeItem(ignoredJobStorageKey);
      }
    } catch {
      // Backend reconciliation remains authoritative when storage is unavailable.
    }
  }

  function readIgnoredUploadJobId() {
    if (typeof window === "undefined") return "";
    try {
      return String(window.localStorage.getItem(ignoredJobStorageKey) ?? "").trim();
    } catch {
      return "";
    }
  }

  function ignoreUploadJobId(jobId) {
    if (typeof window === "undefined" || !jobId) return;
    try {
      window.localStorage.setItem(ignoredJobStorageKey, String(jobId));
    } catch {
      // The action still detaches the current render if storage is unavailable.
    }
  }

  function clearIgnoredUploadJobId(jobId = null) {
    if (typeof window === "undefined") return;
    try {
      if (!jobId || window.localStorage.getItem(ignoredJobStorageKey) === String(jobId)) {
        window.localStorage.removeItem(ignoredJobStorageKey);
      }
    } catch {
      // Ignore unavailable browser storage.
    }
  }

  function clearStoredUploadJobId(jobId = null) {
    if (typeof window === "undefined") return;
    try {
      if (!jobId || window.localStorage.getItem(rememberedJobStorageKey) === String(jobId)) {
        window.localStorage.removeItem(rememberedJobStorageKey);
      }
      if (!jobId || window.localStorage.getItem(LEGACY_LAST_UPLOAD_JOB_ID_STORAGE_KEY) === String(jobId)) {
        window.localStorage.removeItem(LEGACY_LAST_UPLOAD_JOB_ID_STORAGE_KEY);
      }
    } catch {
      // Ignore unavailable browser storage.
    }
  }

  function restoreUsableUploadControls(message, detachedJob = null) {
    stopUploadPolling("job_reconciled_to_controls");
    uploadJobIdRef.current = null;
    uploadStatusPathRef.current = null;
    setUploadJob(null);
    setUploadResult(null);
    setUploadTransfer(null);
    setUploadError("");
    setCompletionError("");
    setUploadState(selectedFiles.length ? "validated" : "idle");
    setUploadProcessingFlag(false);
    setRecentJob(detachedJob);
    setReconciliationMessage(message);
  }

  async function reconcileRememberedJob(jobId, { sourcePayload = null, identitySource = "hydration", signal = null } = {}) {
    const requestedJobId = String(jobId ?? "").trim();
    if (!requestedJobId) return null;
    const path = `/api/data/upload-status/${encodeURIComponent(requestedJobId)}`;
    try {
      const response = await apiFetch(path, { accessCode, signal });
      const payload = await readJsonPayload(response, { route: path, phase: "poll" });
      if (signal?.aborted) return null;
      if (response.status === 404) {
        clearStoredUploadJobId(requestedJobId);
        clearIgnoredUploadJobId(requestedJobId);
        restoreUsableUploadControls("The previous processing job no longer exists. You can start a new upload.");
        return null;
      }
      if (!response.ok) throw buildUploadRequestError(response, payload, "poll");
      const returnedJobId = String(payload?.jobId ?? payload?.job_id ?? "").trim();
      if (!returnedJobId || returnedJobId !== requestedJobId) {
        throw Object.assign(new Error("The status response did not match the remembered processing job."), {
          name: "UploadRequestError",
          phase: "poll",
          errorType: "job_identity_mismatch",
          retryable: false,
          jobId: requestedJobId,
        });
      }
      const normalized = normalizeStatusPayload(payload, requestedJobId);
      const state = authoritativeJobState(normalized);
      if (readIgnoredUploadJobId() === requestedJobId) {
        restoreUsableUploadControls("A backend job is available, but it is detached from the new upload controls.", normalized);
        return normalized;
      }

      const cachedResult = sourcePayload?.latest_result ?? null;
      const hydratedIdentity = baselineIdentityFromResult(cachedResult ?? normalized, {}, identitySource);
      if (hydratedIdentity) {
        completedBaselineIdentityRef.current = hydratedIdentity;
        persistBaselineSelection(hydratedIdentity);
      }
      rememberUploadJobId(requestedJobId);
      setRecentJob(null);
      setReconciliationMessage("");
      uploadJobIdRef.current = requestedJobId;
      uploadStatusPathRef.current = normalizeUploadStatusPath(normalized?.status_url, requestedJobId);
      setUploadJob({
        ...normalized,
        ...(hydratedIdentity ? {
          baselineId: hydratedIdentity.baselineId,
          portfolioId: hydratedIdentity.portfolioId,
          systemId: hydratedIdentity.systemId,
          state_source: hydratedIdentity.stateSource,
        } : {}),
      });
      setUploadResult(cachedResult);

      if (state === "failed") {
        markUploadFailed({
          message: normalized?.message ?? normalized?.error ?? "Dataset import failed.",
          errorType: normalized?.error_code ?? normalized?.error_type ?? null,
          jobId: requestedJobId,
          keepStoredJobId: true,
          diagnostics: normalized,
        });
        return normalized;
      }
      if (state === "completed") {
        setUploadProcessingFlag(false);
        if (normalized?.result_available === true && (!isBaselineWorkflow(normalized?.workflow) || normalized?.baseline_result_available === true)) {
          setUploadState("saving_results");
          await completeUploadHandoff(normalized, requestedJobId, identitySource);
        } else {
          setUploadState("saving_results");
          void pollUploadStatus(requestedJobId, normalized?.status_url);
        }
        return normalized;
      }
      if (isPollableJobState(state)) {
        setUploadState(state);
        setUploadProcessingFlag(true);
        void pollUploadStatus(requestedJobId, normalized?.status_url);
        return normalized;
      }
      restoreUsableUploadControls("The remembered job is not active. You can start a new upload.", normalized);
      return normalized;
    } catch (error) {
      if (signal?.aborted || error?.name === "AbortError") return null;
      const classified = classifyUploadError(error, "poll");
      if (classified.errorType === "job_identity_mismatch") {
        clearStoredUploadJobId(requestedJobId);
        clearIgnoredUploadJobId(requestedJobId);
      }
      const cached = sourcePayload
        ? {
          ...normalizeStatusPayload(sourcePayload, requestedJobId),
          execution_state: "waiting",
          poll_connection_state: "interrupted",
        }
        : null;
      restoreUsableUploadControls(
        "The previous job could not be verified. Upload controls remain available; retry viewing the job when the connection recovers.",
        cached,
      );
      console.warn("[neraium] remembered upload reconciliation failed", {
        jobId: requestedJobId,
        status: classified.responseStatus ?? null,
        errorType: classified.errorType ?? null,
      });
      return null;
    }
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
    if (nextWorkflow !== "analyze_new_data") completedBaselineIdentityRef.current = null;
    setUploadError("");
    setCompletionError("");
    setReconciliationMessage("");
    setUploadState("idle");
    currentWorkflowRef.current = nextWorkflow;
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

  function startAnotherUpload() {
    const detached = uploadJob;
    const detachedJobId = String(detached?.jobId ?? detached?.job_id ?? uploadJobIdRef.current ?? "").trim();
    resetLocalUploadClientState(currentWorkflowRef.current);
    if (detachedJobId) ignoreUploadJobId(detachedJobId);
    setRecentJob(detached ? { ...detached, execution_state: authoritativeJobState(detached) } : null);
    setReconciliationMessage(
      detachedJobId
        ? "The existing backend job is preserved. Choose a file to start another upload."
        : "Choose a file to start another upload.",
    );
    window.setTimeout(() => uploadInputRef.current?.click(), 0);
  }

  function dismissCurrentJob() {
    const jobId = String(uploadJob?.jobId ?? uploadJob?.job_id ?? uploadJobIdRef.current ?? "").trim();
    if (jobId) ignoreUploadJobId(jobId);
    resetLocalUploadClientState(currentWorkflowRef.current);
    setRecentJob(null);
    setReconciliationMessage("The job was dismissed from this browser. Backend data was not deleted.");
  }

  function dismissRecentJob() {
    const jobId = String(recentJob?.jobId ?? recentJob?.job_id ?? "").trim();
    if (jobId) ignoreUploadJobId(jobId);
    setRecentJob(null);
    setReconciliationMessage("The job was dismissed from this browser. Backend data was not deleted.");
  }

  async function viewRecentJob() {
    const jobId = String(recentJob?.jobId ?? recentJob?.job_id ?? "").trim();
    if (!jobId) return;
    clearIgnoredUploadJobId(jobId);
    reconciledJobRef.current = "";
    setRecentJob(null);
    setReconciliationMessage("Checking the backend job state…");
    await reconcileRememberedJob(jobId, { identitySource: "hydration" });
  }

  async function resumeCurrentJob() {
    const jobId = String(uploadJob?.jobId ?? uploadJob?.job_id ?? uploadJobIdRef.current ?? "").trim();
    if (!jobId) return;
    stopUploadPolling("resume_job_status");
    uploadJobIdRef.current = jobId;
    setReconciliationMessage("Checking the backend job state…");
    await reconcileRememberedJob(jobId, { sourcePayload: uploadJob, identitySource: "hydration" });
  }

  async function beginComparisonDataset() {
    if (typeof onCloseBaseline !== "function") {
      resetLocalUploadClientState("analyze_new_data");
      uploadInputRef.current?.click();
      return;
    }
    if (baselineNavigationPendingRef.current) return;
    baselineNavigationPendingRef.current = true;
    setBaselineNavigationPending(true);
    setCompletionError("");
    try {
      let selectedResult = uploadResult?.candidate_model ? uploadResult : uploadJob?.baseline_result ?? latestUploadResult;
      const activationState = selectedResult?.activation?.state ?? selectedResult?.candidate_model?.status;
      if (selectedResult?.candidate_model && activationState === "awaiting_approval") {
        selectedResult = await approveBaselineCandidate();
        if (!selectedResult) throw new Error("The baseline candidate could not be activated.");
      }
      const identity = resolveOpenBaselineIdentity({
        selectedBaselineIdentity,
        completedBaselineIdentity: completedBaselineIdentityRef.current,
        uploadJob,
        uploadResult: selectedResult ?? uploadResult,
        latestUploadResult,
        latestUploadSnapshot,
      });
      if (!identity?.baselineId) throw new Error("The completed baseline response did not provide a baselineId.");
      const navigated = await onCloseBaseline(identity);
      if (navigated !== true) throw new Error("The application router rejected the comparison route.");
      resetLocalUploadClientState("analyze_new_data");
    } catch (error) {
      setCompletionError("Baseline established, but the comparison upload screen could not be opened.");
      console.warn("[neraium] comparison navigation failed", { reason: error?.message ?? String(error) });
    } finally {
      baselineNavigationPendingRef.current = false;
      setBaselineNavigationPending(false);
    }
  }

  function shouldContinuePolling(jobId) {
    return Boolean(jobId) && String(uploadJobIdRef.current ?? "") === String(jobId);
  }

  function clearPollDelay() {
    if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
    pollTimerRef.current = null;
    const resolve = pollDelayResolveRef.current;
    pollDelayResolveRef.current = null;
    resolve?.();
  }

  function waitForPollDelay(milliseconds) {
    clearPollDelay();
    return new Promise((resolve) => {
      pollDelayResolveRef.current = resolve;
      pollTimerRef.current = window.setTimeout(() => {
        pollTimerRef.current = null;
        pollDelayResolveRef.current = null;
        resolve();
      }, milliseconds);
    });
  }

  function stopUploadPolling(reason = "manual") {
    pollSessionRef.current += 1;
    pollAbortControllerRef.current?.abort();
    pollAbortControllerRef.current = null;
    clearPollDelay();
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
      rememberUploadJobId(resolvedJobId);
    } else if (!keepStoredJobId) {
      clearStoredUploadJobId();
    }
  }

  async function completeUploadHandoff(completedPayload, requestedJobId, identitySource = "completion_response") {
    const jobId = completedPayload?.jobId ?? completedPayload?.job_id ?? requestedJobId ?? uploadJobIdRef.current ?? null;
    const datasetId = completedPayload?.datasetId ?? completedPayload?.dataset_id ?? null;
    const completedWorkflow = completedPayload?.workflow ?? "legacy_analysis";
    if (isBaselineWorkflow(completedWorkflow)) {
      const resultPath = completedPayload?.baseline_result_url ?? `/api/data/baselines/jobs/${encodeURIComponent(jobId)}`;
      const resultDeadline = Date.now() + RESULT_AVAILABILITY_GRACE_MS;
      let response;
      let baselineResult;
      let rawBaselineResult;
      do {
        response = await apiFetch(resultPath, { accessCode });
        rawBaselineResult = await readJsonPayload(response, { route: resultPath, phase: "baseline_result" });
        if (response.ok) {
          baselineResult = normalizeBaselineCreationResponse(rawBaselineResult, { jobId, datasetId }, { requireBaselineId: true });
          if (baselineResult?.candidate_model) break;
        }
        if (response.status !== 404 || Date.now() >= resultDeadline) {
          throw buildUploadRequestError(response, rawBaselineResult, "baseline_result");
        }
        await waitForPollDelay(RESULT_FETCH_RETRY_INTERVAL_MS);
      } while (Date.now() < resultDeadline);
      if (!response?.ok || !baselineResult?.candidate_model) {
        throw buildUploadRequestError(response ?? { status: 404 }, rawBaselineResult ?? {}, "baseline_result");
      }
      const returnedJobId = String(baselineResult?.jobId ?? "").trim();
      if (returnedJobId && String(jobId) !== returnedJobId) {
        throw new Error("The completed baseline did not match the requested import job.");
      }
      const identity = baselineIdentityFromResult(baselineResult, {
        jobId,
        uploadId: completedPayload?.uploadId ?? completedPayload?.upload_id ?? jobId,
        datasetId,
      }, identitySource);
      if (!identity) throw new Error("The completed baseline identifiers were unavailable.");
      uploadJobIdRef.current = identity.jobId ?? jobId;
      completedBaselineIdentityRef.current = identity;
      clearBaselineResultCache({ scopeKey: datasetScopeKey, portfolioId: identity.portfolioId, baselineId: identity.baselineId });
      persistBaselineSelection(identity);
      console.info("[neraium] baseline creation handoff", {
        datasetId: identity.datasetId,
        jobId: identity.jobId,
        baselineId: identity.baselineId,
        returnedResponseBody: {
          status: baselineResult.status,
          datasetId: baselineResult.datasetId,
          jobId: baselineResult.jobId,
          baselineId: baselineResult.baselineId,
          workspacePath: baselineResult.workspacePath,
          createdAt: baselineResult.createdAt,
        },
        routeDestination: baselineRoutePath(identity.portfolioId, identity.baselineId),
        persistenceResult: "readback_confirmed_by_backend",
        requestId: baselineResult.requestId ?? baselineResult.request_id ?? null,
      });

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
        baselineId: identity.baselineId,
        portfolioId: identity.portfolioId,
        systemId: identity.systemId,
        workspacePath: baselineResult.workspacePath,
        createdAt: baselineResult.createdAt,
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
    pollAbortControllerRef.current?.abort();
    const pollController = new AbortController();
    pollAbortControllerRef.current = pollController;
    let pollingPath = normalizeUploadStatusPath(statusUrl, requestedJobId) ?? `/api/data/upload-status/${requestedJobId}`;
    uploadStatusPathRef.current = pollingPath;
    rememberUploadJobId(requestedJobId);
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
            await waitForPollDelay(Math.max(1000, activeCooldownUntil - now));
            continue;
          }
          const requestPath = pollingPath;
          const pollRequestStartedAt = Date.now();
          const response = await apiFetch(requestPath, { accessCode, signal: pollController.signal });
          const payload = await readJsonPayload(response, { route: requestPath, phase: "poll" });
          if (pollController.signal.aborted || pollSessionRef.current !== pollSessionId) return null;
          const pollTiming = frontendPollingTiming(payload, pollRequestStartedAt);
          console.info("[neraium] frontend polling timing", {
            jobId: requestedJobId,
            stage: payload?.processing_state ?? payload?.status ?? null,
            ...pollTiming,
          });
          const returnedJobId = String(payload?.jobId ?? payload?.job_id ?? "").trim();
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
              setUploadJob((current) => ({
                ...(current ?? {}),
                job_id: requestedJobId,
                poll_connection_state: "retrying",
                poll_message: isTransientUploadServiceStatus(response.status)
                  ? SERVICE_UNAVAILABLE_RETRY_MESSAGE
                  : "The job status endpoint is not available yet. Retrying.",
                response_status: response.status,
                failure_url: payload?.failure_url ?? requestPath,
                failure_phase: payload?.failure_phase ?? "poll",
              }));
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
              await waitForPollDelay(cooldownMs);
              continue;
            }
            throw buildUploadRequestError(response, payload, "poll");
          }
          statusEndpointFailureCountRef.current = 0;
          pollFailureCountRef.current = 0;
          const normalizedPayload = normalizeStatusPayload({
            ...payload,
            frontend_polling_timing: pollTiming,
            poll_connection_state: "connected",
          }, requestedJobId);
          pollingPath = normalizeUploadStatusPath(normalizedPayload?.status_url, requestedJobId) ?? pollingPath;
          uploadStatusPathRef.current = pollingPath;
          setUploadJob(normalizedPayload);
          const normalizedStatus = normalizeUploadStatus(normalizedPayload.status ?? normalizedPayload.processing_state);
          const authoritativeState = authoritativeJobState(normalizedPayload);
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
                datasetId: normalizedPayload?.datasetId ?? normalizedPayload?.dataset_id ?? null,
                requestId: normalizedPayload?.request_id ?? null,
                technicalMessage: "Terminal job state remained visible without result availability.",
                terminalJobFailure: true,
              });
            }
            setUploadJob({
              ...normalizedPayload,
              result_commit_state: "waiting",
              progress_label: "Waiting for the committed baseline result...",
              message: "Waiting for the committed baseline result...",
            });
            setUploadState("saving_results");
          } else {
            terminalWithoutResultAt = null;
            setUploadState(authoritativeState);
          }
          await waitForPollDelay(STATUS_POLL_INTERVAL_MS);
        } catch (error) {
          if (pollController.signal.aborted || error?.name === "AbortError") return null;
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
            poll_message: "Analysis status connection interrupted. Retrying.",
          }));
          if (pollFailureCountRef.current >= MAX_STATUS_POLL_FAILURES) {
            throw error;
          }
          const retryDelay = boundedFailureDelay(pollFailureCountRef.current);
          await waitForPollDelay(retryDelay);
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
        if (pollController.signal.aborted || error?.name === "AbortError") return null;
        const classified = classifyUploadError(error, "poll");
        logUploadFailureDiagnostics(classified);
        if (Number(classified.responseStatus ?? error?.status ?? 0) === 404) {
          clearStoredUploadJobId(requestedJobId);
          clearIgnoredUploadJobId(requestedJobId);
          restoreUsableUploadControls("The previous processing job no longer exists. You can start a new upload.");
          return null;
        }
        if (error?.terminalJobFailure === true) {
          logTelemetryStage("error", { jobId: requestedJobId, message: classified.message || error?.message || "Telemetry analysis failed." });
          markUploadFailed({
            message: classified.message || normalizeErrorMessage(error, "Telemetry analysis failed."),
            errorType: classified.errorType,
            jobId: requestedJobId,
            keepStoredJobId: true,
            diagnostics: { ...classified, fileStored: classified.fileStored || classified.errorType !== "file_storage_failed" },
          });
          return null;
        }
        stopUploadPolling("poll_connection_interrupted");
        setUploadProcessingFlag(false);
        setUploadState("waiting");
        setUploadJob((current) => ({
          ...(current ?? {}),
          job_id: requestedJobId,
          execution_state: "waiting",
          poll_connection_state: "interrupted",
          poll_failure_count: pollFailureCountRef.current,
          poll_message: "Analysis status connection interrupted. Resume status when the connection recovers.",
        }));
        setReconciliationMessage("Backend status is temporarily unavailable. The last valid job state is preserved.");
        return null;
      })
      .finally(() => {
        if (pollSessionRef.current === pollSessionId) {
          pollInFlightRef.current = null;
          pollOwnerJobIdRef.current = null;
          if (pollAbortControllerRef.current === pollController) pollAbortControllerRef.current = null;
        }
      });
    pollOwnerJobIdRef.current = requestedJobId;
    return pollInFlightRef.current;
  }

  function normalizeStatusPayload(payload, requestedJobId) {
    const normalizedJob = normalizeUploadJob({ ...(payload ?? {}), jobId: payload?.jobId ?? payload?.job_id ?? requestedJobId });
    const normalized = normalizeUploadStatus(normalizedJob.status ?? normalizedJob.processing_state ?? normalizedJob.worker_state);
    return {
      ...normalizedJob,
      job_id: normalizedJob.jobId ?? requestedJobId,
      status: payload?.status ?? normalized,
      percent: payload?.job_progress?.overall_percent_complete ?? payload?.percent ?? payload?.progress ?? null,
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
    currentWorkflowRef.current = selectedWorkflow;
    setCurrentWorkflow(selectedWorkflow);
    const validationError = validateTelemetryFile(file, pendingUploadKind);
    if (validationError) {
      setUploadError(validationError);
      return;
    }
    uploadInFlightRef.current = true;
    setUploadError("");
    setCompletionError("");
    const preferStoredUpload = import.meta.env.PROD && import.meta.env.VITE_PREFER_STORED_UPLOAD !== "false";
    console.info("[neraium] baseline submission initiated", {
      filename: file.name,
      size: file.size,
      transport: preferStoredUpload || file.size > 250 * 1024 * 1024 ? "presigned_s3_put" : "direct_multipart",
    });
    setUploadState("uploading");
    setUploadProcessingFlag(true);
    setUploadTransfer({ percent: 0, loaded: 0, total: file.size, label: `Sending telemetry ${formatFileSize(0)} of ${formatFileSize(file.size)}` });
    try {
      const uploadInteractionStartedAt = Date.now();
      const uploadResponse = await uploadTelemetryFileWithProgress({
        file,
        workflow: selectedWorkflow,
        baselineIdentity: selectedWorkflow === "analyze_new_data"
          ? (activeBaselineIdentity ?? completedBaselineIdentityRef.current)
          : null,
        apiFetch,
        preferStoredUpload,
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
      const jobId = String(payload?.jobId ?? payload?.job_id ?? "").trim() || null;
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
      setUploadState(authoritativeJobState(normalizeStatusPayload(payload, jobId)));
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
  const propagationLabel = progressUploadJob?.propagation_label ?? progressUploadJob?.propagationLabel ?? progressUploadJob?.propagation_stage ?? "";
  const statusLabel = progressUploadJob?.poll_message
    ?? progressUploadJob?.job_progress?.visibility_message
    ?? progressUploadJob?.job_progress?.message
    ?? progressUploadJob?.progress_label
    ?? progressUploadJob?.message
    ?? progressUploadTransfer?.message
    ?? uploadStateMessage(uploadState);
  const visibleStatusLabel = statusLabel;
  const queuedWorkerDetail = queuedWorkerMessage(progressUploadJob);
  const latestStatusMessage = completionError || uploadError || visibleStatusLabel || readiness;
  const announcedStatusMessage = latestStatusMessage;
  const resultBaselineId = String(
    uploadResult?.baselineId
      ?? uploadJob?.baseline_result?.baselineId
      ?? completedBaselineIdentityRef.current?.baselineId
      ?? "",
  ).trim();
  const selectedCompletionBaselineId = String(uploadJob?.baselineId ?? completedBaselineIdentityRef.current?.baselineId ?? "").trim();
  const baselineResult = selectedCompletionBaselineId && resultBaselineId && selectedCompletionBaselineId !== resultBaselineId
    ? null
    : uploadResult?.candidate_model
      ? uploadResult
      : uploadJob?.baseline_result ?? (uploadJob?.baselineId ? uploadJob : null);

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
    if (currentWorkflowRef.current !== "analyze_new_data") completedBaselineIdentityRef.current = null;
    clearStoredUploadJobId();
    setSelectedFiles(files);
    setUploadError("");
    setCompletionError("");
    setReconciliationMessage("");
    setUploadState(files.length ? "validated" : "idle");
  }

  function chooseAnotherFile() {
    startAnotherUpload();
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
    const currentJobId = String(uploadJob?.jobId ?? uploadJob?.job_id ?? uploadJobIdRef.current ?? "").trim();
    if (!currentJobId) {
      await handleUpload();
      return;
    }
    setUploadError("");
    setCompletionError("");
    setUploadState("waiting");
    setUploadProcessingFlag(true);
    try {
      const retryResponse = await retryUploadAnalysisJob({ jobId: currentJobId, apiFetch, accessCode });
      const payload = retryResponse.payload;
      const jobId = String(payload?.jobId ?? payload?.job_id ?? "").trim() || currentJobId;
      setUploadJob(normalizeStatusPayload(payload, jobId));
      setUploadState(authoritativeJobState(payload));
      await pollUploadStatus(jobId, payload?.status_url);
    } catch (error) {
      const classified = classifyUploadError(error, error?.phase || "upload");
      logUploadFailureDiagnostics(classified);
      markUploadFailed({ message: classified.message || normalizeErrorMessage(error, "Telemetry analysis failed."), errorType: classified.errorType, jobId: currentJobId, keepStoredJobId: true, diagnostics: classified });
    }
  }

  async function approveBaselineCandidate() {
    const candidateResult = uploadResult?.candidate_model
      ? uploadResult
      : uploadJob?.baseline_result ?? baselineDetailState.result;
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
    if (identity) {
      completedBaselineIdentityRef.current = identity;
      persistBaselineSelection(identity);
    }
    return updated;
  }

  async function openCompletedBaseline(options = {}) {
    if (baselineNavigationPendingRef.current) return;
    baselineNavigationPendingRef.current = true;
    setBaselineNavigationPending(true);
    setCompletionError("");

    let identity = null;
    let targetRoute = null;
    try {
      let selectedResult = uploadResult?.candidate_model ? uploadResult : uploadJob?.baseline_result ?? null;
      const activationState = selectedResult?.activation?.state ?? selectedResult?.candidate_model?.status;
      if (selectedResult?.candidate_model && activationState === "awaiting_approval") {
        selectedResult = await approveBaselineCandidate();
        if (!selectedResult) throw new Error("The baseline candidate could not be activated.");
      }

      identity = resolveOpenBaselineIdentity({
        selectedBaselineIdentity,
        completedBaselineIdentity: completedBaselineIdentityRef.current,
        uploadJob,
        uploadResult: selectedResult ?? uploadResult,
        latestUploadResult,
        latestUploadSnapshot,
      });

      if (!identity?.baselineId) {
        const recovery = await recoverBaselineCreation({
          apiFetch,
          accessCode,
          identity: {
            ...completedBaselineIdentityRef.current,
            jobId: identity?.jobId ?? uploadJob?.jobId ?? uploadJob?.job_id ?? uploadJobIdRef.current,
            datasetId: identity?.datasetId ?? uploadJob?.datasetId ?? uploadJob?.dataset_id,
            portfolioId: identity?.portfolioId ?? uploadJob?.portfolioId ?? getCurrentWorkspaceId(),
          },
        });
        identity = baselineIdentityFromResult(recovery, {
          ...completedBaselineIdentityRef.current,
          portfolioId: recovery.portfolioId ?? getCurrentWorkspaceId(),
        }, "active_baseline_fetch");
        if (identity) {
          completedBaselineIdentityRef.current = identity;
          persistBaselineSelection(identity);
          setUploadJob((current) => ({
            ...(current ?? {}),
            jobId: identity.jobId,
            job_id: identity.jobId,
            datasetId: identity.datasetId,
            dataset_id: identity.datasetId,
            baselineId: identity.baselineId,
            portfolioId: identity.portfolioId,
            systemId: identity.systemId,
            workspacePath: recovery.workspacePath,
            createdAt: recovery.createdAt,
            state_source: identity.stateSource,
          }));
          console.info("[neraium] baseline recovery handoff", {
            datasetId: identity.datasetId,
            jobId: identity.jobId,
            baselineId: identity.baselineId,
            returnedResponseBody: recovery,
            routeDestination: baselineRoutePath(identity.portfolioId, identity.baselineId),
          });
        }
      }

      targetRoute = baselineRoutePath(identity?.portfolioId, identity?.baselineId);
      logBaselineNavigation("button activated", identity, targetRoute);
      logBaselineNavigation("selected baseline ID", identity, targetRoute);
      logBaselineNavigation("generated target route", identity, targetRoute);
      if (!identity?.baselineId || !targetRoute) throw new Error("The completed baseline response did not provide a recoverable baselineId.");
      if (typeof onOpenBaseline !== "function") throw new Error("Baseline navigation is unavailable.");

      const navigated = await onOpenBaseline(identity, options);
      if (navigated !== true) throw new Error("The application router rejected the baseline route.");
      logBaselineNavigation("navigation success", identity, targetRoute);
    } catch (error) {
      const message = "Baseline created successfully. We could not open the workspace automatically.";
      setCompletionError(message);
      setUploadError("");
      setUploadState("completion_error");
      logBaselineNavigation(
        "navigation failure",
        identity,
        targetRoute,
        identity?.baselineId ? "router_rejected" : "baseline_recovery_failed",
      );
      console.warn("[neraium] baseline navigation handoff failed", {
        datasetId: identity?.datasetId ?? uploadJob?.datasetId ?? uploadJob?.dataset_id ?? null,
        jobId: identity?.jobId ?? uploadJob?.jobId ?? uploadJob?.job_id ?? uploadJobIdRef.current ?? null,
        baselineId: identity?.baselineId ?? null,
        routeDestination: targetRoute,
        requestId: error?.requestId ?? null,
        reason: error?.message ?? String(error),
      });
    } finally {
      baselineNavigationPendingRef.current = false;
      setBaselineNavigationPending(false);
    }
  }

  openCompletedBaselineRef.current = openCompletedBaseline;

  useEffect(() => {
    if (!autoOpenBaselineReady || headless || !["complete", "save_complete"].includes(uploadState) || !isBaselineWorkflow(uploadJob?.workflow)) return;
    const identity = completedBaselineIdentityRef.current;
    const targetRoute = baselineRoutePath(identity?.portfolioId, identity?.baselineId);
    if (targetRoute && typeof window !== "undefined" && window.location.pathname === targetRoute) return;
    void openCompletedBaselineRef.current?.({ replace: true });
  }, [autoOpenBaselineReady, headless, onOpenBaseline, uploadJob?.workflow, uploadState]);

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
          apiFetch={apiFetch}
          accessCode={accessCode}
          onRetry={() => setBaselineDetailReloadKey((value) => value + 1)}
          onImportComparison={async () => {
            const detailResult = baselineDetailState.result;
            const activationState = detailResult?.activation?.state ?? detailResult?.candidate_model?.status;
            if (activationState === "awaiting_approval") {
              const activated = await approveBaselineCandidate();
              if (!activated) return;
            }
            resetLocalUploadClientState("analyze_new_data");
            if (typeof onCloseBaseline === "function") onCloseBaseline(baselineDetailState.identity ?? selectedBaselineIdentity);
          }}
          onReturnToPortfolio={onReturnToPortfolio}
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
        propagationLabel={propagationLabel}
        queuedWorkerDetail={queuedWorkerDetail}
        uploadTransfer={uploadTransfer}
        uploadDebug={uploadDebug}
        uploadStateMessage={uploadStateMessage}
        batchResults={batchResults}
        onRetryFailedUploads={() => { void retryCurrentBatch(); }}
        onReprocessCurrentBatch={() => { void retryCurrentBatch(); }}
        onResetWorkspace={dismissCurrentJob}
        onChooseAnotherFile={chooseAnotherFile}
        onViewResults={() => { void viewCompletedResults(); }}
        onOpenBaseline={() => { void openCompletedBaseline(); }}
        onReturnToPortfolio={onReturnToPortfolio}
        baselineNavigationPending={baselineNavigationPending}
        onImportComparisonDataset={() => { void beginComparisonDataset(); }}
        recentJob={recentJob}
        reconciliationMessage={reconciliationMessage}
        onViewRecentJob={() => { void viewRecentJob(); }}
        onDismissRecentJob={dismissRecentJob}
        onResumeJob={() => { void resumeCurrentJob(); }}
        onStartAnotherUpload={startAnotherUpload}
        apiFetch={apiFetch}
        accessCode={accessCode}
        onIngestionReviewUpdated={(profile) => {
          const trust = profile?.summary ?? profile;
          setUploadResult((current) => current ? { ...current, ingestion_trust: trust } : current);
          setUploadJob((current) => current ? { ...current, ingestion_trust: trust } : current);
        }}
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
