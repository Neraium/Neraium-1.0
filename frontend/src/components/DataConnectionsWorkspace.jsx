import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  buildUploadRequestError,
  classifyUploadError,
  isUploadProcessing,
  normalizeErrorMessage,
  normalizeUploadStatus,
  readJsonPayload,
  uploadStateMessage,
} from "../viewModels/uploadFlow";
import * as uploadStateView from "../viewModels/uploadState";
import { uploadTelemetryFileWithProgress } from "../services/api/uploadApi";
import { buildApiCandidateUrls } from "../config";
import IntakeFlowPanel from "./setup/IntakeFlowPanel";
import ConnectionsHeaderPanel from "./dataConnections/ConnectionsHeaderPanel";

const MAX_UPLOAD_BYTES = 250 * 1024 * 1024;
const LARGE_OPERATIONAL_UPLOAD_BYTES = 100 * 1024 * 1024;
const UPLOAD_REQUEST_TIMEOUT_MS = 10 * 60 * 1000;
const DATA_CONNECTIONS_TAB_STORAGE_KEY = "neraium.data_connections.active_tab";
const LAST_UPLOAD_JOB_ID_STORAGE_KEY = "neraium.last_upload_job_id";
const TERMINAL_UPLOAD_STATES = new Set(["complete", "error", "failed", "cancelled", "validation_error"]);
const MAX_STATUS_POLL_FAILURES = 8;

function readStoredDataConnectionsTab() {
  if (typeof window === "undefined") return "upload";
  const value = window.localStorage.getItem(DATA_CONNECTIONS_TAB_STORAGE_KEY);
  return value === "upload" ? value : "upload";
}

function formatTransferSpeed(bytesPerSecond) {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) return "measuring speed";
  if (bytesPerSecond >= 1024 * 1024) return `${(bytesPerSecond / (1024 * 1024)).toFixed(1)} MB/s`;
  return `${Math.max(bytesPerSecond / 1024, 1).toFixed(1)} KB/s`;
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "Awaiting file";
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(bytes / 1024, 1).toFixed(1)} KB`;
}

function isLargeOperationalUpload(file) {
  return (file?.size ?? 0) >= LARGE_OPERATIONAL_UPLOAD_BYTES;
}

function uploadReadinessMessage(file) {
  if (!file) return "Choose telemetry export data to begin pilot intake analysis.";
  if (isLargeOperationalUpload(file)) {
    return "Large telemetry export detected. Transfer is secure and processing continues in the background while status is tracked in Intake Status.";
  }
  return "Telemetry export is ready for secure intake and analysis.";
}

function validateTelemetryFile(file, kind) {
  if (!file) return "Choose a CSV or JSON telemetry file to upload.";
  if (file.size > MAX_UPLOAD_BYTES) return `High-volume export above ${formatFileSize(MAX_UPLOAD_BYTES)}. Use partitioned export or enterprise batch intake.`;
  const filename = String(file.name ?? "").toLowerCase();
  const mime = String(file.type ?? "").toLowerCase();
  const looksJson = filename.endsWith(".json") || mime.includes("json");
  const looksCsv = filename.endsWith(".csv") || mime.includes("csv") || mime === "text/plain" || mime === "";
  if (kind === "json" && !looksJson) return "Selected file does not look like JSON telemetry.";
  if (kind === "csv" && !looksCsv) return "Selected file does not look like CSV telemetry.";
  return "";
}

function fallbackPercentFromStatus(status) {
  const normalized = normalizeUploadStatus(status);
  const stagedPercent = {
    idle: 0,
    validated: 3,
    uploading: 12,
    upload_started: 12,
    accepted: 18,
    queued: 22,
    pending: 28,
    validating_schema: 36,
    parsing: 48,
    baseline_modeling: 62,
    structural_scoring: 74,
    running_sii: 82,
    cognition_ready: 90,
    generating_replay: 94,
    writing_state: 97,
    complete: 100,
    failed: 100,
    error: 100,
  };
  return stagedPercent[normalized] ?? null;
}

export default function DataConnectionsWorkspace({
  accessCode,
  apiFetch,
  apiStatus,
  latestUploadSnapshot,
  latestUploadResult,
  hasActiveSession,
  hasResumedSession,
  hasCurrentUploadResult,
  roomContext,
  onUploadComplete,
  onResetDemo,
  onResumePreviousSession,
  formatClockTime,
}) {
  const tabs = useMemo(() => [
    { id: "upload", label: "Upload" },
  ], []);

  const [selectedFiles, setSelectedFiles] = useState([]);
  const [activeTab, setActiveTab] = useState(() => readStoredDataConnectionsTab());
  const [pendingUploadKind, setPendingUploadKind] = useState("csv");
  const [uploadState, setUploadState] = useState("idle");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(latestUploadResult);
  const [uploadJob, setUploadJob] = useState(null);
  const [uploadTransfer, setUploadTransfer] = useState(null);
  const [batchResults, setBatchResults] = useState([]); 
  const [isJsonSchemaOpen, setIsJsonSchemaOpen] = useState(false); 
  const [copyState, setCopyState] = useState("idle"); 
  const [feedbackState, setFeedbackState] = useState({ status: "idle", category: null, message: "" });
  void uploadResult;
  void feedbackState;
  const [isResetViewActive, setIsResetViewActive] = useState(false);
  const uploadJobIdRef = useRef(null); 
  const pollTimerRef = useRef(null);
  const pollFailureCountRef = useRef(0);
  const pollInFlightRef = useRef(null);
  const pollOwnerJobIdRef = useRef(null);
  const missingStatusCooldownUntilRef = useRef(0);
  const statusEndpointCooldownUntilRef = useRef(0);
  const statusEndpointFailureCountRef = useRef(0);
  const lastRecoveryProbeAtRef = useRef(0);
  const lastRecoveryPayloadRef = useRef(null);
  const uploadStatusPathRef = useRef(null);
  const uploadInputRef = useRef(null);
  const uploadInFlightRef = useRef(false);
  const uploadStateRef = useRef("idle");
  const pollSessionRef = useRef(0);
  const setUploadProcessingFlag = (active) => {
    if (typeof window !== "undefined") {
      window.__NERAIUM_UPLOAD_IN_PROGRESS__ = Boolean(active);
    }
  };

  useEffect(() => {
    uploadStateRef.current = uploadState;
  }, [uploadState]);

  const loadLatestUpload = useCallback(async () => {
    try {
      const response = await apiFetch("/api/data/latest-upload?include_persisted=1", { accessCode });
      const payload = await readJsonPayload(response);
      return response.ok ? payload : null;
    } catch {
      return null;
    }
  }, [accessCode, apiFetch]);
// eslint-disable-next-line react-hooks/exhaustive-deps
useEffect(() => {
  if (typeof window === "undefined") return;

  let cancelled = false;

  const restoreUploadSession = async () => {
    const storedJobId = String(window.localStorage.getItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY) ?? "").trim();

    const latestPayload = await loadLatestUpload();
    if (cancelled) return;

    const latestJobId = String(
      latestPayload?.latest_result?.job_id
      ?? latestPayload?.history?.[0]?.job_id
      ?? latestPayload?.job_id
      ?? "",
    ).trim();

    const restoreJobId = storedJobId || latestJobId;
    const latestStatus = normalizeUploadStatus(latestPayload?.status ?? latestPayload?.snapshot?.status ?? "");
    const latestResult = latestPayload?.latest_result;

    if (!restoreJobId && !latestResult) return;

    uploadJobIdRef.current = restoreJobId || null;
    uploadStatusPathRef.current = normalizeUploadStatusPath(latestPayload?.status_url, restoreJobId);

    if (restoreJobId) {
      window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, restoreJobId);
    }

    if (latestResult || ["complete", "active", "running_sii"].includes(latestStatus)) {
      const restoredPayload = {
        ...(latestPayload ?? {}),
        job_id: restoreJobId || latestJobId || null,
        status: latestResult || latestStatus === "complete" ? "COMPLETE" : "PENDING",
        processing_state: latestResult || latestStatus === "complete" ? "complete" : "processing",
        percent: latestResult || latestStatus === "complete" ? 100 : undefined,
        progress: latestResult || latestStatus === "complete" ? 100 : undefined,
        result_available: Boolean(latestResult),
        progress_label: latestResult
          ? "Telemetry processing complete."
          : "Restored upload session. Checking processing status.",
        message: latestResult
          ? "Telemetry processing complete."
          : "Restored upload session. Checking processing status.",
      };

      setUploadJob(restoredPayload);
      setUploadResult(latestResult ?? latestPayload ?? null);

      if (latestResult || latestStatus === "complete") {
        setUploadState("complete");
        setUploadProcessingFlag(false);
        if (typeof onUploadComplete === "function") {
          await onUploadComplete(latestResult ?? latestPayload);
        }
        return;
      }

      setUploadState("running_sii");
      pollUploadStatus(restoreJobId, latestPayload?.status_url).catch(() => {});
    }
  };

  restoreUploadSession();

  return () => {
    cancelled = true;
  };
// eslint-disable-next-line react-hooks/exhaustive-deps
}, [loadLatestUpload, onUploadComplete]);
  useEffect(() => () => {
    pollSessionRef.current += 1;
    if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
    pollTimerRef.current = null;
    pollInFlightRef.current = null;
    pollOwnerJobIdRef.current = null;
  }, []);

  useEffect(() => {
    setUploadResult(latestUploadResult);
  }, [latestUploadResult]);

  useEffect(() => {
    if (!latestUploadSnapshot) return;
    const currentJobId = uploadJob?.job_id ?? uploadJobIdRef.current;
    // Do not let background snapshot polling overwrite an active in-flight upload job.
    if (pollInFlightRef.current) {
      console.info("upload_status_poll_tick", {
        job_id: String(currentJobId ?? ""),
        attempt: null,
        request_path: null,
        stream_path: null,
        failure_count: pollFailureCountRef.current,
        note: "latest_upload_hydration_skipped_inflight_poll",
      });
      return;
    }
    if (currentJobId && isUploadProcessing(uploadState)) {
      console.info("upload_status_poll_tick", {
        job_id: String(currentJobId ?? ""),
        attempt: null,
        request_path: null,
        stream_path: null,
        failure_count: pollFailureCountRef.current,
        note: "latest_upload_hydration_skipped_processing_state",
      });
      return;
    }
    const snapshotStatus = normalizeUploadStatus(latestUploadSnapshot.status);
    const snapshotReplayFrameCount =
      Number(
        latestUploadSnapshot?.replay_frame_count
        ?? latestUploadSnapshot?.latest_result?.replay_timeline?.timeline?.length
        ?? latestUploadSnapshot?.latest_result?.sii_intelligence?.replay_timeline?.timeline?.length
        ?? 0,
      ) || 0;
    const snapshotReplayReady = Boolean(latestUploadSnapshot?.replay_ready) || snapshotReplayFrameCount > 0;
    const snapshotSiiCompleted = Boolean(latestUploadSnapshot?.sii_completed);
    const restoredUploadState = snapshotStatus === "active"
      ? (snapshotSiiCompleted
        ? (snapshotReplayReady ? "complete" : "generating_replay")
        : "structural_scoring")
      : snapshotStatus;
    const restoredBackendStatus = {
      complete: "COMPLETE",
      generating_replay: "GENERATING_REPLAY",
      structural_scoring: "RUNNING_SII",
      writing_state: "GENERATING_EVIDENCE",
    }[restoredUploadState] ?? String(latestUploadSnapshot.status ?? "PENDING").toUpperCase();
    const hasPersistedSession =
      snapshotStatus === "complete"
      || snapshotStatus === "active"
      || snapshotStatus === "running_sii"
      || snapshotStatus === "parsing"
      || snapshotStatus === "baseline_modeling"
      || Boolean(latestUploadSnapshot.last_filename)
      || Boolean(latestUploadSnapshot.latest_result);

    if (!hasPersistedSession) return;

    console.info("upload_status_poll_tick", {
      job_id: String(currentJobId ?? ""),
      attempt: null,
      request_path: null,
      stream_path: null,
      failure_count: pollFailureCountRef.current,
      note: "latest_upload_hydration_applied",
      restored_state: restoredUploadState || "idle",
    });
    setUploadState(restoredUploadState || "idle");
    setUploadJob((current) => ({
      ...(current ?? {}),
      job_id: current?.job_id ?? latestUploadSnapshot.history?.[0]?.job_id ?? latestUploadSnapshot.latest_result?.job_id ?? null,
      status: restoredBackendStatus,
      progress_label: current?.progress_label ?? latestUploadSnapshot.message ?? "Session restored from persisted state.",
      message: latestUploadSnapshot.message ?? current?.message ?? "Session restored from persisted state.",
      filename: current?.filename ?? latestUploadSnapshot.last_filename ?? null,
      rows_processed: Number.isFinite(latestUploadSnapshot.rows_processed) ? latestUploadSnapshot.rows_processed : (current?.rows_processed ?? 0),
      columns_detected: Number.isFinite(latestUploadSnapshot.columns_detected) ? latestUploadSnapshot.columns_detected : (current?.columns_detected ?? 0),
      replay_ready: snapshotReplayReady,
      replay_frame_count: snapshotReplayFrameCount,
      runner_used: latestUploadSnapshot.runner_used ?? current?.runner_used ?? false,
      runner_module: latestUploadSnapshot.runner_module ?? current?.runner_module ?? null,
      core_engine: latestUploadSnapshot.core_engine ?? current?.core_engine ?? null,
    }));
  }, [latestUploadSnapshot, uploadJob?.job_id, uploadState]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(DATA_CONNECTIONS_TAB_STORAGE_KEY, activeTab);
  }, [activeTab]);

function normalizeUploadStatusPath(statusUrl, jobId) {
  const statusValue = String(statusUrl ?? "").trim();
  if (statusValue.startsWith("/api/data/upload-status/")) return statusValue;
  if (statusValue.startsWith("/api/upload-status/")) return statusValue.replace("/api/upload-status/", "/api/data/upload-status/");
  if (statusValue.startsWith("/data/upload-status/")) return `/api${statusValue}`;
  if (statusValue.startsWith("/upload-status/")) return `/api/data${statusValue}`;
  const fallbackId = String(jobId ?? "").trim();
  return fallbackId ? `/api/data/upload-status/${fallbackId}` : null;
}

function extractJobIdFromStatusPath(value) {
  const text = String(value ?? "");
  const match = text.match(/\/api\/data\/upload-status\/([^/?#\s]+)/i) || text.match(/\/api\/upload-status\/([^/?#\s]+)/i) || text.match(/\/upload-status\/([^/?#\s]+)/i);
  return match?.[1] ? decodeURIComponent(match[1]) : "";
}

function toUploadStreamPath(statusPath, jobId) {
  const normalized = normalizeUploadStatusPath(statusPath, jobId);
  if (!normalized) return null;
  return normalized.replace("/upload-status/", "/upload-stream/");
}

function clearStoredUploadJobId() {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY);
  }
}

function stopUploadPolling(reason = "manual") {
  pollSessionRef.current += 1;
  if (pollTimerRef.current) {
    window.clearTimeout(pollTimerRef.current);
    pollTimerRef.current = null;
  }
  pollInFlightRef.current = null;
  pollOwnerJobIdRef.current = null;
  pollFailureCountRef.current = 0;
  missingStatusCooldownUntilRef.current = 0;
  statusEndpointCooldownUntilRef.current = 0;
  statusEndpointFailureCountRef.current = 0;
  console.info("upload_status_poll_stopped", { reason });
}

function markUploadFailed({ message, errorType = null, jobId = null, keepStoredJobId = false }) {
  const resolvedJobId = String(jobId ?? uploadJobIdRef.current ?? "").trim() || null;
  stopUploadPolling("terminal_error");
  uploadJobIdRef.current = resolvedJobId;
  uploadStatusPathRef.current = resolvedJobId
    ? normalizeUploadStatusPath(uploadStatusPathRef.current, resolvedJobId)
    : null;
  if (!resolvedJobId || !keepStoredJobId) {
    clearStoredUploadJobId();
  }
  if (typeof window !== "undefined") {
    window.__NERAIUM_UPLOAD_COMPLETE__ = false;
  }
  setUploadProcessingFlag(false);
  setUploadError(message);
  setUploadState("error");
  setUploadJob((current) => ({
    ...(current ?? {}),
    job_id: resolvedJobId,
    status: resolvedJobId ? "FAILED" : "none",
    processing_state: "failed",
    progress_label: message,
    message,
    error: message,
    error_type: errorType,
    result_available: false,
  }));
}

function clearUploadClientState() {
  setIsResetViewActive(true);
  setSelectedFiles([]);
  setUploadState("idle");
  setUploadError("");
  setUploadResult(null);
  setUploadJob(null);
  setUploadTransfer(null);
  setBatchResults([]);
  setFeedbackState({ status: "idle", category: null, message: "" });
  setCopyState("idle");
  setIsJsonSchemaOpen(false);
  uploadJobIdRef.current = null;
  uploadStatusPathRef.current = null;
  lastRecoveryProbeAtRef.current = 0;
  lastRecoveryPayloadRef.current = null;
  clearStoredUploadJobId();
  if (uploadInputRef.current) uploadInputRef.current.value = "";
  uploadInFlightRef.current = false;
  if (typeof window !== "undefined") {
    window.__NERAIUM_UPLOAD_COMPLETE__ = false;
  }
  stopUploadPolling("clear_state");
  setUploadProcessingFlag(false);
}

function shouldLogPollTick(attempt, failureCount) {
  return attempt <= 3 || failureCount > 0 || attempt % 5 === 0;
}

async function pollUploadStatus(jobId, statusUrl) {
    const requestedJobId = String(jobId || uploadJobIdRef.current || "").trim();
    if (!requestedJobId) {
      markUploadFailed({
        message: "Upload processing interrupted. No valid job ID was returned.",
        errorType: "upload_session_missing",
      });
      return null;
    }

    console.info("upload_status_poll_started", {
      requested_job_id: requestedJobId,
      status_url: statusUrl ?? null,
      current_ref_job_id: uploadJobIdRef.current ?? null,
      in_flight: Boolean(pollInFlightRef.current),
    });

    if (pollInFlightRef.current && pollOwnerJobIdRef.current === requestedJobId) {
      return pollInFlightRef.current;
    }

    const pollSessionId = pollSessionRef.current + 1;
    pollSessionRef.current = pollSessionId;

    const shouldContinuePolling = (activeJobId = requestedJobId) => (
      pollSessionRef.current === pollSessionId
      && Boolean(String(activeJobId || uploadJobIdRef.current || "").trim())
      && !TERMINAL_UPLOAD_STATES.has(normalizeUploadStatus(uploadStateRef.current))
    );

    const runPoll = async () => {
      const pollingJobId = requestedJobId;
      const defaultPollingPath = `/api/data/upload-status/${pollingJobId}`;
      const pollingPath = normalizeUploadStatusPath(statusUrl ?? uploadStatusPathRef.current, pollingJobId) ?? defaultPollingPath;
      const streamPath = toUploadStreamPath(statusUrl ?? uploadStatusPathRef.current, pollingJobId);
      if (!pollingJobId || !pollingPath) {
        markUploadFailed({
          message: "Upload processing interrupted. No status endpoint was returned.",
          errorType: "upload_session_missing",
          jobId: pollingJobId,
        });
        return null;
      }

      if (!shouldContinuePolling(pollingJobId)) {
        return null;
      }

      const streamPayload = await streamUploadStatusOnce({ streamPath, pollingJobId });
      if (!shouldContinuePolling(pollingJobId)) {
        return streamPayload;
      }
      if (streamPayload) {
        setUploadJob(streamPayload);
        const streamStatus = normalizeUploadStatus(streamPayload.status);
        if (streamStatus === "complete") {
          setUploadState("complete");
          if (typeof window !== "undefined") window.__NERAIUM_UPLOAD_COMPLETE__ = true;
          setUploadProcessingFlag(false);
        } else if (streamStatus === "failed") {
          markUploadFailed({
            message: normalizeErrorMessage(streamPayload?.error || streamPayload?.message || "Upload processing interrupted."),
            errorType: streamPayload?.error_type ?? null,
            jobId: pollingJobId,
            keepStoredJobId: true,
          });
        } else {
          setUploadState(streamStatus || "running_sii");
        }
        if (streamStatus === "complete" || streamStatus === "failed") {
          return streamPayload;
        }
      }

      let completeWithoutReplayCount = 0;
      let notFoundCount = 0;
      for (let attempts = 0; ; attempts += 1) {
        if (!shouldContinuePolling(pollingJobId)) {
          return null;
        }
        try {
          const now = Date.now();
          const activeCooldownUntil = Math.max(
            Number(missingStatusCooldownUntilRef.current || 0),
            Number(statusEndpointCooldownUntilRef.current || 0),
          );
          if (activeCooldownUntil > now) {
            await new Promise((resolve) => {
              pollTimerRef.current = window.setTimeout(resolve, Math.max(1000, activeCooldownUntil - now));
            });
            continue;
          }
          const requestPath = pollingPath === defaultPollingPath ? `/api/data/upload-status/${pollingJobId}` : pollingPath;
          if (shouldLogPollTick(attempts + 1, pollFailureCountRef.current)) {
            console.info("upload_status_poll_tick", {
              job_id: String(pollingJobId),
              attempt: attempts + 1,
              request_path: requestPath,
              stream_path: streamPath,
              failure_count: pollFailureCountRef.current,
            });
          }
          const response = await apiFetch(requestPath, { accessCode });
          const payload = await readJsonPayload(response);
          if (!response.ok) {
            if (response.status === 404 || response.status >= 500) {
              statusEndpointFailureCountRef.current += 1;
              const cooldownMs = Math.min(120000, 20000 + statusEndpointFailureCountRef.current * 10000);
              statusEndpointCooldownUntilRef.current = Date.now() + cooldownMs;
              if (Date.now() - lastRecoveryProbeAtRef.current >= 10000) {
                const latestPayload = await loadLatestUpload();
                lastRecoveryProbeAtRef.current = Date.now();
                lastRecoveryPayloadRef.current = latestPayload;
                const recoveredJobId = String(
                  latestPayload?.latest_result?.job_id
                  ?? latestPayload?.history?.[0]?.job_id
                  ?? "",
                ).trim();
                const recoveredStatus = normalizeUploadStatus(latestPayload?.status ?? latestPayload?.snapshot?.status ?? "");
                if (latestPayload?.latest_result && recoveredJobId === String(pollingJobId) && ["active", "complete", "running_sii"].includes(recoveredStatus)) {
                  const recoveredPayload = {
                    ...payload,
                    ...latestPayload,
                    job_id: recoveredJobId,
                    status: "COMPLETE",
                    replay_ready: true,
                    replay_frame_count:
                      Number(
                        latestPayload?.latest_result?.replay_timeline?.timeline?.length
                        ?? latestPayload?.latest_result?.sii_intelligence?.replay_timeline?.timeline?.length
                        ?? 0,
                      ) || 1,
                    progress_label: "Telemetry processing complete.",
                    message: "Telemetry processing complete.",
                  };
                  setUploadJob(recoveredPayload);
                  setUploadState("complete");
                  setUploadProcessingFlag(false);
                  return recoveredPayload;
                }
              }
              await new Promise((resolve) => {
                pollTimerRef.current = window.setTimeout(resolve, cooldownMs);
              });
              continue;
            }
            const missingStatus = response.status === 404
              && String(payload?.error_type ?? payload?.error ?? "").toLowerCase() === "upload_session_missing";
            if (missingStatus) {
              notFoundCount += 1;
              const nowMs = Date.now();
              const shouldProbeLatest = notFoundCount >= 3 && (nowMs - lastRecoveryProbeAtRef.current >= 15000);
              let latestPayload = lastRecoveryPayloadRef.current;
              if (shouldProbeLatest) {
                latestPayload = await loadLatestUpload();
                lastRecoveryProbeAtRef.current = nowMs;
                lastRecoveryPayloadRef.current = latestPayload;
              }
              const recoveredJobId = String(
                latestPayload?.latest_result?.job_id
                ?? latestPayload?.history?.[0]?.job_id
                ?? "",
              ).trim();
              const recoveredStatus = normalizeUploadStatus(latestPayload?.status ?? latestPayload?.snapshot?.status ?? "");
              const sameJobRecovered = recoveredJobId && recoveredJobId === String(pollingJobId);
              if (latestPayload?.latest_result && sameJobRecovered && ["active", "complete", "running_sii"].includes(recoveredStatus)) {
                const recoveredPayload = {
                  ...payload,
                  ...latestPayload,
                  job_id: recoveredJobId,
                  status: "COMPLETE",
                  replay_ready: true,
                  replay_frame_count:
                    Number(
                      latestPayload?.latest_result?.replay_timeline?.timeline?.length
                      ?? latestPayload?.latest_result?.sii_intelligence?.replay_timeline?.timeline?.length
                      ?? 0,
                    ) || 1,
                  progress_label: "Telemetry processing complete.",
                  message: "Telemetry processing complete.",
                };
                setUploadJob(recoveredPayload);
                setUploadState("complete");
                setUploadProcessingFlag(false);
                return recoveredPayload;
              }
              const missingDelayMs = Math.max(15000, nextUploadPollDelay({
                payload: null,
                failureCount: Math.max(pollFailureCountRef.current + 1, notFoundCount + 1),
                failedAttempt: true,
              }));
              if (notFoundCount >= 3) {
                missingStatusCooldownUntilRef.current = nowMs + missingDelayMs;
              }
              await new Promise((resolve) => {
                pollTimerRef.current = window.setTimeout(resolve, missingDelayMs);
              });
              continue;
            }
            throw buildUploadRequestError(response, payload, "poll");
          }

          const payloadStatusUpper = String(payload?.status ?? "").toUpperCase();
          statusEndpointFailureCountRef.current = 0;
          statusEndpointCooldownUntilRef.current = 0;
          const previouslyComplete = normalizeUploadStatus(uploadStateRef.current) === "complete" || (typeof window !== "undefined" && window.__NERAIUM_UPLOAD_COMPLETE__ === true);
          if (previouslyComplete && ["NOT_FOUND", "MISSING"].includes(payloadStatusUpper)) {
            notFoundCount += 1;
            if (notFoundCount <= 5) {
              const delayMs = nextUploadPollDelay({ payload: null, failureCount: notFoundCount, failedAttempt: true });
              await new Promise((resolve) => {
                pollTimerRef.current = window.setTimeout(resolve, delayMs);
              });
              continue;
            }
          }
          if (["NOT_FOUND", "MISSING"].includes(payloadStatusUpper)) {
            notFoundCount += 1;
            if (notFoundCount >= 3) {
              const latestPayload = await loadLatestUpload();
              const recoveredStatus = normalizeUploadStatus(latestPayload?.status ?? "");
              if (latestPayload?.latest_result && ["active", "complete"].includes(recoveredStatus)) {
                const recoveredPayload = {
                  ...payload,
                  status: "COMPLETE",
                  replay_ready: true,
                  replay_frame_count:
                    Number(
                      latestPayload?.latest_result?.replay_timeline?.timeline?.length
                      ?? latestPayload?.latest_result?.sii_intelligence?.replay_timeline?.timeline?.length
                      ?? 0,
                    ) || 1,
                  progress_label: "Telemetry processing complete.",
                  message: "Telemetry processing complete.",
                };
                setUploadJob(recoveredPayload);
                setUploadState("complete");
                return recoveredPayload;
              }
            }
          } else {
            notFoundCount = 0;
          }

          pollFailureCountRef.current = 0;
          uploadJobIdRef.current = payload.job_id ?? pollingJobId;
          uploadStatusPathRef.current = normalizeUploadStatusPath(payload?.status_url, uploadJobIdRef.current) ?? pollingPath;
          if (typeof window !== "undefined" && uploadJobIdRef.current) {
            window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, String(uploadJobIdRef.current));
          }
          setUploadJob(payload);
          const nextStatus = normalizeUploadStatus(payload.status);
          const backendPercent = Number(payload?.percent ?? payload?.progress ?? 0);
          const resultAvailable = Boolean(payload?.result_available);
          const firstUsableAvailable = Boolean(payload?.first_usable_available);
          const replayReady = Boolean(payload?.replay_ready) || Number(payload?.replay_frame_count ?? 0) > 0;

          if (nextStatus === "complete" || backendPercent >= 100 || resultAvailable || replayReady) {
            if (typeof window !== "undefined") window.__NERAIUM_UPLOAD_COMPLETE__ = true;
            setUploadProcessingFlag(false);
            const completedPayload = {
              ...payload,
              status: "COMPLETE",
              percent: 100,
              progress: 100,
              processing_state: "complete",
              progress_label: payload?.progress_label || "Telemetry processing complete.",
              message: payload?.message || "Telemetry processing complete.",
            };
            setUploadJob(completedPayload);
            setUploadState("complete");
            return completedPayload;
          }

          if (firstUsableAvailable && nextStatus === "cognition_ready") {
            setUploadState("cognition_ready");
          } else {
            setUploadState(nextStatus);
          }
          if (nextStatus === "complete" && !replayReady) {
            completeWithoutReplayCount += 1;
            if (completeWithoutReplayCount >= 5) {
              const completedPayload = {
                ...payload,
                replay_pending: true,
                progress_label: payload?.progress_label ?? "Telemetry processing complete. Replay is finalizing.",
                message: payload?.message ?? "Telemetry processing complete. Replay is finalizing.",
              };
              setUploadJob(completedPayload);
              setUploadState("complete");
              return completedPayload;
            }
            setUploadState("generating_replay");
          }
          if (nextStatus === "failed") throw buildUploadRequestError(response, payload, "poll");
          const delayMs = nextUploadPollDelay({ payload, failureCount: pollFailureCountRef.current });
          await new Promise((resolve) => {
            pollTimerRef.current = window.setTimeout(resolve, delayMs);
          });
        } catch (error) {
          const classified = classifyUploadError(error, "poll");
          if (classified.retryable && pollFailureCountRef.current < MAX_STATUS_POLL_FAILURES && shouldContinuePolling(pollingJobId)) {
            pollFailureCountRef.current += 1;
            setUploadState((current) => (isUploadProcessing(current) ? current : "running_sii"));
            setUploadError(classified.message);
            const delayMs = nextUploadPollDelay({ payload: null, failureCount: pollFailureCountRef.current, failedAttempt: true });
            await new Promise((resolve) => {
              pollTimerRef.current = window.setTimeout(resolve, delayMs);
            });
            continue;
          }
          markUploadFailed({
            message: classified.finalMessage ?? classified.message,
            errorType: classified.errorType ?? error?.errorType ?? error?.error_type ?? null,
            jobId: pollingJobId,
            keepStoredJobId: Boolean(pollingJobId),
          });
          throw error;
        }
      }
    };

    pollOwnerJobIdRef.current = requestedJobId;
    pollInFlightRef.current = runPoll();
    try {
      return await pollInFlightRef.current;
    } finally {
      if (pollSessionRef.current === pollSessionId) {
        pollInFlightRef.current = null;
        pollOwnerJobIdRef.current = null;
      }
    }
  }

  async function streamUploadStatusOnce({ streamPath, pollingJobId }) { 
    if (!streamPath || typeof window === "undefined" || typeof window.EventSource === "undefined") {
      return null;
    }
    const urls = buildApiCandidateUrls(streamPath);
    for (const url of urls) {
      console.info("upload_status_stream_request", {
        job_id: String(pollingJobId ?? ""),
        streamPath,
        status: null,
        propagation_stage: null,
        propagation_progress: null,
        worker_state: null,
      });
      const payload = await new Promise((resolve) => { 
        let resolved = false; 
        let lastPayload = null;
        let lastMessageAt = Date.now();
        const es = new EventSource(url, { withCredentials: true }); 
        const timer = window.setTimeout(() => { 
          if (resolved) return; 
          resolved = true; 
          try { es.close(); } catch {} 
          resolve(lastPayload); 
        }, 60000); 
        es.onmessage = (event) => { 
          if (resolved) return; 
          let parsed = null; 
          try {
            parsed = JSON.parse(event.data || "{}");
          } catch {
            parsed = null;
          }
          if (!parsed || String(parsed.job_id || "") !== String(pollingJobId || "")) { 
            return; 
          } 
          lastPayload = parsed;
          lastMessageAt = Date.now();
          const status = String(parsed?.status ?? "");
          console.info("upload_status_stream_tick", {
            job_id: String(parsed?.job_id ?? pollingJobId ?? ""),
            streamPath,
            status,
            propagation_stage: parsed?.propagation_stage ?? null,
            propagation_progress: parsed?.propagation_progress ?? null,
            worker_state: parsed?.worker_state ?? null,
          });
          setUploadJob(parsed);
          const s = normalizeUploadStatus(parsed.status); 
          if (s && !["complete", "failed"].includes(s)) {
            setUploadState(s);
          }
          if (["complete", "failed"].includes(s)) { 
            console.info("upload_status_stream_terminal", {
              job_id: String(parsed?.job_id ?? pollingJobId ?? ""),
              streamPath,
              status,
              propagation_stage: parsed?.propagation_stage ?? null,
              propagation_progress: parsed?.propagation_progress ?? null,
              worker_state: parsed?.worker_state ?? null,
            });
            resolved = true; 
            window.clearTimeout(timer); 
            try { es.close(); } catch {} 
            resolve(parsed); 
            return;
          }
          if (Date.now() - lastMessageAt > 30000) {
            resolved = true;
            window.clearTimeout(timer);
            try { es.close(); } catch {}
            resolve(lastPayload);
          } 
        }; 
        es.onerror = () => {
          if (resolved) return;
          console.error("upload_status_stream_error", {
            job_id: String(pollingJobId ?? ""),
            streamPath,
            status: String(lastPayload?.status ?? ""),
            propagation_stage: lastPayload?.propagation_stage ?? null,
            propagation_progress: lastPayload?.propagation_progress ?? null,
            worker_state: lastPayload?.worker_state ?? null,
          });
          resolved = true;
          window.clearTimeout(timer);
          try { es.close(); } catch {}
          resolve(null);
        };
      });
      if (payload) return payload; 
    } 
    return null; 
  } 

  async function handleUpload(event) {
    event.preventDefault();
    if (uploadInFlightRef.current) return;
    await processUploadBatch(selectedFiles);
  }

  async function handleReprocessCurrentBatch() {
    const failedFiles = batchResults.filter((item) => item.status === "failed").map((item) => item.file).filter(Boolean);
    if (failedFiles.length > 0) {
      await processUploadBatch(failedFiles);
      return;
    }
    if (selectedFiles.length > 0) {
      await processUploadBatch(selectedFiles);
      return;
    }
    const latestJobId = uploadJob?.job_id ?? latestUploadSnapshot?.history?.[0]?.job_id;
    if (!latestJobId) {
      setUploadError("No upload session is available to reprocess yet.");
      setUploadState("validation_error");
      return;
    }

    stopUploadPolling("reprocess_upload_request");
    setUploadError("");
    setUploadState("running_sii");
    setUploadJob({
      job_id: latestJobId,
      status: "running_sii",
      progress_label: "Reprocessing persisted telemetry session.",
      message: "Rebuilding the latest session from persisted artifacts.",
    });

    try {
      const response = await apiFetch(`/api/data/upload-reprocess/${latestJobId}`, {
        method: "POST",
        accessCode,
      });
      const payload = await readJsonPayload(response);
      if (!response.ok) throw buildUploadRequestError(response, payload, "upload");

      uploadJobIdRef.current = payload?.job_id ?? latestJobId;
      console.info("upload_accepted_job_id", {
        job_id: String(uploadJobIdRef.current),
        source: "reprocess_response",
        status_url: payload?.status_url ?? null,
      });
      setUploadJob(payload);
      setUploadState(normalizeUploadStatus(payload?.status ?? "pending"));
      console.info("upload_status_poll_started", {
        requested_job_id: String(uploadJobIdRef.current),
        source: "reprocess",
        status_url: payload?.status_url ?? null,
      });
      await pollUploadStatus(uploadJobIdRef.current);

      const latestPayload = await loadLatestUpload();
      const latestResult = latestPayload?.latest_result;
      const completedPayload = uploadStateView.hasFullUploadResult(latestResult)
        ? {
            ...latestResult,
            latest_result: latestResult,
            snapshot: latestPayload?.snapshot ?? latestPayload,
            status: "complete",
            last_processed_at:
              latestResult?.last_processed_at
              ?? latestResult?.completed_at
              ?? latestResult?.sii_intelligence?.last_updated
              ?? new Date().toISOString(),
          }
        : {
            ...(latestPayload ?? {}),
            filename: latestPayload?.filename ?? "Uploaded telemetry",
            row_count: latestPayload?.row_count ?? latestPayload?.rows_processed ?? 1,
            column_count: latestPayload?.column_count ?? latestPayload?.columns_detected ?? 1,
            operating_state: latestPayload?.operating_state ?? "Monitoring",
            drift_status: latestPayload?.drift_status ?? "info",
            status: "complete",
            last_processed_at: latestPayload?.last_processed_at ?? new Date().toISOString(),
            sii_intelligence: {
              facility_state: "Monitoring",
              urgency: "info",
              primary_room: "Uploaded telemetry",
              last_updated: latestPayload?.last_processed_at ?? new Date().toISOString(),
              ...(latestPayload?.sii_intelligence ?? {}),
            },
          };
      setUploadResult(completedPayload);
      setUploadJob((current) => ({
        ...(current ?? {}),
        status: "COMPLETE",
        processing_state: "complete",
        percent: 100,
        progress: 100,
        result_available: true,
        progress_label: "Telemetry processing complete.",
        message: "Telemetry processing complete.",
      }));
      setIsResetViewActive(false);
      if (typeof onUploadComplete === "function") {
        await onUploadComplete(completedPayload);
      }
      setUploadState("complete");
    } catch (error) {
      const classified = classifyUploadError(error, "upload");
      setUploadError(classified.message);
      setUploadState(classified.state);
    }
  }

  async function processUploadBatch(filesToProcess) {
    if (uploadInFlightRef.current) return;
    uploadInFlightRef.current = true;
    stopUploadPolling("new_upload_request");
    setUploadProcessingFlag(true);
    let keepProcessingLock = false;
    const validationError = filesToProcess.length === 0
      ? "Choose one or more CSV/JSON telemetry files to upload."
      : validateTelemetryFile(filesToProcess[0], pendingUploadKind);
    if (validationError) {
      setUploadError(validationError);
      setUploadState("validation_error");
      uploadInFlightRef.current = false;
      if (typeof window !== "undefined") {
        window.__NERAIUM_UPLOAD_IN_PROGRESS__ = false;
      }
      return;
    }
    setUploadState("uploading");
    setUploadError("");
    const totalBytes = filesToProcess.reduce((sum, file) => sum + (file.size || 0), 0);
    setUploadJob({ job_id: null, status: "uploading", progress_label: "Upload started.", message: "Uploading telemetry export.", file_size_bytes: totalBytes });
    setUploadTransfer({ loaded: 0, total: totalBytes, percent: 0, speedBytesPerSecond: 0, stage: "upload_started" });
    setBatchResults(filesToProcess.map((file) => ({
      id: `${file.name}-${file.size}-${file.lastModified ?? Date.now()}`,
      file,
      fileName: file.name,
      status: "pending",
      message: "Waiting",
      jobId: null,
    })));
    uploadJobIdRef.current = null;
    uploadStatusPathRef.current = null;
    clearStoredUploadJobId();
    pollFailureCountRef.current = 0;
    if (typeof window !== "undefined") {
      window.__NERAIUM_UPLOAD_COMPLETE__ = false;
    }
    try {
      let aggregateLoaded = 0;
      let successCount = 0;
      let failedCount = 0;
      let hasBackgroundProcessing = false;
      for (const [index, file] of filesToProcess.entries()) {
        const startingLoaded = aggregateLoaded;
        const fileId = `${file.name}-${file.size}-${file.lastModified ?? Date.now()}`;
        let returnedJobId = null;
        setBatchResults((current) => current.map((entry) => (entry.id === fileId ? { ...entry, status: "uploading", message: "Uploading" } : entry)));
        const { ok, status, payload } = await uploadTelemetryFileWithProgress({
          file,
          accessCode,
          timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS,
          onProgress: (progress) => {
            const loaded = startingLoaded + (progress.loaded ?? 0);
            const total = totalBytes;
            const percent = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0;
            setUploadTransfer({ ...progress, loaded, total, percent });
            setUploadJob((current) => ({
              ...(current ?? {}),
              status: progress.stage === "accepted" ? "pending" : "uploading",
              progress_label: `Uploading file ${index + 1}/${filesToProcess.length} - ${percent}% - ${formatTransferSpeed(progress.speedBytesPerSecond)}`,
              message: progress.message,
              file_size_bytes: total,
              bytes_processed: loaded,
            }));
          },
        });
        try {
          if (!ok) throw buildUploadRequestError({ status }, payload, "upload");
          returnedJobId = payload?.job_id ?? payload?.jobId ?? payload?.id;
          if (!returnedJobId) {
            const latestPayload = await loadLatestUpload();
            const recoveredJobId = String(
              latestPayload?.latest_result?.job_id
              ?? latestPayload?.history?.[0]?.job_id
              ?? "",
            ).trim();
            if (recoveredJobId) {
              returnedJobId = recoveredJobId;
            }
          }
          if (!returnedJobId) throw buildUploadRequestError({ status }, { ...payload, error_type: "upload_session_missing", message: "Upload state unavailable." }, "upload");
          console.info("upload_accepted_job_id", {
            job_id: String(returnedJobId),
            source: payload?.job_id ? "upload_response" : "latest_upload_recovery",
            status_url: payload?.status_url ?? null,
          });
          uploadJobIdRef.current = returnedJobId;
          if (typeof window !== "undefined" && uploadJobIdRef.current) {
            window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, String(uploadJobIdRef.current));
          }
          const normalizedPayload = { ...payload, job_id: returnedJobId };
          uploadStatusPathRef.current = normalizeUploadStatusPath(normalizedPayload?.status_url, returnedJobId);
          setUploadJob(normalizedPayload);
          setUploadState(normalizeUploadStatus(normalizedPayload.status));
          console.info("upload_status_poll_started", {
            requested_job_id: String(returnedJobId),
            source: "process_upload_batch",
            status_url: normalizedPayload?.status_url ?? null,
          });
          await pollUploadStatus(returnedJobId, normalizedPayload?.status_url);
          aggregateLoaded += file.size || 0;
          successCount += 1;
          setBatchResults((current) => current.map((entry) => (entry.id === fileId
            ? { ...entry, status: "success", message: "Processed", jobId: returnedJobId }
            : entry)));
        } catch (fileError) {
          const uploadRequestError = fileError?.name === "UploadRequestError" && fileError?.payload
            ? buildUploadRequestError({ status: fileError.status }, fileError.payload, "upload")
            : fileError;
          const transientStatus = Number(fileError?.status ?? fileError?.response?.status ?? 0);
          const transientUploadFailure = ["ApiNetworkError", "ApiTimeoutError", "UploadRequestError"].includes(String(fileError?.name))
            || [408, 425, 429, 500, 502, 503, 504].includes(transientStatus);
          if (transientUploadFailure) {
            const latestPayload = await loadLatestUpload();
            const inferredJobId = String(
              returnedJobId
              ?? uploadJobIdRef.current
              ?? extractJobIdFromStatusPath(fileError?.path)
              ?? "",
            ).trim();
            const recoveredJobId = String(
              latestPayload?.latest_result?.job_id
              ?? latestPayload?.history?.[0]?.job_id
              ?? inferredJobId
              ?? "",
            ).trim();
            const recoveredStatus = normalizeUploadStatus(latestPayload?.status ?? latestPayload?.snapshot?.status ?? "");
            const recoveredFilename = String(
              latestPayload?.last_filename
              ?? latestPayload?.snapshot?.last_filename
              ?? latestPayload?.latest_result?.filename
              ?? "",
            ).trim();
            const sameFileRecovered = recoveredFilename.length > 0 && recoveredFilename === file.name;
            if (recoveredJobId && (sameFileRecovered || ["active", "complete", "running_sii"].includes(recoveredStatus))) {
              uploadJobIdRef.current = recoveredJobId;
              if (typeof window !== "undefined") {
                window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, recoveredJobId);
              }
              uploadStatusPathRef.current = normalizeUploadStatusPath(latestPayload?.status_url, recoveredJobId);
              setUploadJob((current) => ({
                ...(current ?? {}),
                job_id: recoveredJobId,
                status: "PENDING",
                processing_state: "processing",
                progress_label: "Upload accepted. Recovering processing state after transient network error.",
                message: "Upload accepted. Recovering processing state after transient network error.",
              }));
              setUploadState("running_sii");
              await pollUploadStatus(recoveredJobId, latestPayload?.status_url);
              aggregateLoaded += file.size || 0;
              successCount += 1;
              setBatchResults((current) => current.map((entry) => (entry.id === fileId
                ? { ...entry, status: "success", message: "Recovered after transient upload failure", jobId: recoveredJobId }
                : entry)));
              continue;
            }
            if (inferredJobId) {
              uploadJobIdRef.current = inferredJobId;
              uploadStatusPathRef.current = normalizeUploadStatusPath(
                payload?.status_url ?? latestPayload?.status_url ?? fileError?.path,
                inferredJobId,
              );
              hasBackgroundProcessing = true;
              setUploadState("running_sii");
              setUploadJob((current) => ({
                ...(current ?? {}),
                job_id: inferredJobId,
                status: "PENDING",
                processing_state: "processing",
                progress_label: "Upload accepted. Status endpoint is temporarily unavailable; continuing in background.",
                message: "Upload accepted. Status endpoint is temporarily unavailable; continuing in background.",
              }));
              aggregateLoaded += file.size || 0;
              successCount += 1;
              setBatchResults((current) => current.map((entry) => (entry.id === fileId
                ? { ...entry, status: "success", message: "Accepted; status temporarily unavailable", jobId: inferredJobId }
                : entry)));
              continue;
            }
          }
          const classified = classifyUploadError(uploadRequestError, "upload");
          failedCount += 1;
          setUploadJob((current) => ({
            ...(current ?? {}),
            status: "FAILED",
            processing_state: "failed",
            progress_label: classified.message,
            message: classified.message,
            error: classified.message,
          }));
          setBatchResults((current) => current.map((entry) => (entry.id === fileId
            ? { ...entry, status: "failed", message: classified.message, jobId: payload?.job_id ?? null }
            : entry)));
        }
      }
      const latestPayload = await loadLatestUpload();
      const latestResult = latestPayload?.latest_result;
      const completedPayload = {
        ...(uploadStateView.hasFullUploadResult(latestResult) ? latestResult : {}),
        ...(latestPayload ?? {}),
      };
      setUploadTransfer({ loaded: totalBytes, total: totalBytes, percent: 100, speedBytesPerSecond: 0, stage: "accepted", message: "All files processed." });
      if (hasBackgroundProcessing && failedCount === 0) {
        keepProcessingLock = true;
        setUploadResult(completedPayload);
        setUploadState("running_sii");
        setUploadError("Upload accepted. Status endpoint is temporarily unavailable; processing continues in background.");
        return;
      }
      if (failedCount > 0) {
        stopUploadPolling("upload_batch_failed");
        setUploadJob((current) => ({
          ...(current ?? {}),
          status: "FAILED",
          processing_state: "failed",
          progress_label: `Processed ${successCount} file(s), ${failedCount} failed. Retry failed files.`,
          message: `Processed ${successCount} file(s), ${failedCount} failed. Retry failed files.`,
          error: `Processed ${successCount} file(s), ${failedCount} failed. Retry failed files.`,
          result_available: successCount > 0,
        }));
        if (successCount === 0) {
          setUploadResult(null);
          clearStoredUploadJobId();
          if (typeof window !== "undefined") {
            window.__NERAIUM_UPLOAD_COMPLETE__ = false;
          }
        } else {
          setUploadResult(completedPayload);
        }
        if (successCount > 0) {
          if (typeof onUploadComplete === "function") {
            await onUploadComplete(completedPayload);
          }
        }
        setUploadState("error");
        setUploadError(`Processed ${successCount} file(s), ${failedCount} failed. Retry failed files.`);
        return;
      }
      setUploadResult(completedPayload);
      if (typeof window !== "undefined") {
        window.__NERAIUM_UPLOAD_COMPLETE__ = true;
      }
      keepProcessingLock = false;
      setUploadProcessingFlag(false);
      setIsResetViewActive(false);
      if (typeof onUploadComplete === "function") {
        await onUploadComplete(completedPayload);
      }
      setUploadState("complete");
    } catch (error) {
      const uploadRequestError = error?.name === "UploadRequestError" && error?.payload
        ? buildUploadRequestError({ status: error.status }, error.payload, "upload")
        : error;
      const classified = classifyUploadError(uploadRequestError, "upload");
      markUploadFailed({
        message: classified.finalMessage ?? classified.message,
        errorType: classified.errorType ?? uploadRequestError?.errorType ?? uploadRequestError?.error_type ?? null,
        jobId: uploadJobIdRef.current,
        keepStoredJobId: Boolean(uploadJobIdRef.current),
      });
      keepProcessingLock = false;
    } finally {
      uploadInFlightRef.current = false;
      if (!keepProcessingLock) {
        setUploadProcessingFlag(false);
      }
    }
  }

  function openFilePicker(kind) {
    setPendingUploadKind(kind);
    if (uploadInputRef.current) {
      uploadInputRef.current.value = "";
      uploadInputRef.current.multiple = true;
      uploadInputRef.current.accept = kind === "json" ? ".json,application/json" : ".csv,text/csv";
      uploadInputRef.current.click();
    }
  }

  function handleFileSelection(event) {
    const nextFiles = Array.from(event.target.files ?? []);
    const firstInvalid = nextFiles.find((file) => Boolean(validateTelemetryFile(file, pendingUploadKind)));
    const validationError = firstInvalid ? validateTelemetryFile(firstInvalid, pendingUploadKind) : "";
    setSelectedFiles(validationError ? [] : nextFiles);
    setUploadError(validationError);
    setUploadState(validationError ? "validation_error" : nextFiles.length > 0 ? "validated" : "idle");
    setUploadTransfer(null);
    setBatchResults([]);
    if (nextFiles.length > 0 && !validationError) {
      const totalBytes = nextFiles.reduce((sum, file) => sum + (file.size || 0), 0);
      setUploadJob({
        job_id: null,
        status: "validated",
        progress_label: nextFiles.length > 1 ? `${nextFiles.length} telemetry files validated.` : (isLargeOperationalUpload(nextFiles[0]) ? "Large telemetry export detected." : "Telemetry export validated."),
        message: uploadReadinessMessage(nextFiles[0]),
        file_size_bytes: totalBytes,
      });
    } else {
      setUploadJob(null);
    }
  }

  async function handleResetDemoClick() { 
    setUploadError("");
    try {
      if (onResetDemo) await onResetDemo();
      clearUploadClientState();
    } catch (error) {
      setIsResetViewActive(false);
      markUploadFailed({
        message: normalizeErrorMessage(error?.message || error?.detail || "Reset Everything failed."),
        errorType: "reset_failed",
        jobId: uploadJobIdRef.current,
        keepStoredJobId: Boolean(uploadJobIdRef.current),
      });
    }
  } 

  const displayUploadError = uploadError; 
  const effectiveSnapshot = isResetViewActive
    ? uploadStateView.buildEmptyLatestUploadSnapshot()
    : latestUploadSnapshot;
  const latestMessage = normalizeErrorMessage(displayUploadError || uploadJob?.error || uploadJob?.propagation_label || uploadJob?.progress_label || uploadJob?.message || effectiveSnapshot?.message || uploadStateMessage(uploadState));
  const selectedFileSize = formatFileSize(selectedFiles.reduce((sum, file) => sum + (file.size || 0), 0));
  const uploadTransferPercent = Number.isFinite(uploadTransfer?.percent) ? Math.min(100, Math.max(0, uploadTransfer.percent)) : null;
  const backendPercent = Number.isFinite(uploadJob?.percent ?? uploadJob?.progress) ? Math.min(100, Math.max(0, uploadJob.percent ?? uploadJob.progress)) : null;
  const propagationPercent = Number.isFinite(uploadJob?.propagation_progress)
    ? Math.min(100, Math.max(0, Number(uploadJob?.propagation_progress)))
    : backendPercent;
  const propagationLabel = String(
    uploadJob?.propagation_label
    ?? uploadJob?.progress_label
    ?? uploadJob?.message
    ?? "",
  ).trim();
  const currentJobId = String(uploadJob?.job_id ?? uploadJobIdRef.current ?? "").trim();
  const latestResultJobId = String(latestUploadResult?.job_id ?? "").trim();
  const latestResultMatchesCurrentJob = Boolean(currentJobId) && currentJobId === latestResultJobId;
  const backendComplete = String(uploadJob?.processing_state ?? "").toLowerCase() === "complete"
    || Number(uploadJob?.percent ?? uploadJob?.progress ?? 0) >= 100
    || Boolean(uploadJob?.result_available)
    || latestResultMatchesCurrentJob;
  const effectiveUploadState = backendComplete ? "complete" : normalizeUploadStatus(uploadState);
  const statusFallbackPercent = fallbackPercentFromStatus(uploadJob?.status ?? effectiveUploadState);
  const preferredPercent = [uploadTransferPercent, propagationPercent, backendPercent, statusFallbackPercent]
    .filter((value) => Number.isFinite(value))
    .reduce((maxValue, value) => Math.max(maxValue, value), 0);
  const visibleProgressPercent = backendPercent >= 100 || effectiveUploadState === "complete"
    ? 100
    : isUploadProcessing(uploadState)
      ? Math.max(1, Math.min(99, preferredPercent))
      : null;
  const latestReplayFrames = Math.max(
    Number(uploadJob?.latest_replay_frames ?? 0) || 0,
    Number(uploadJob?.replay_frame_count ?? 0) || 0,
    Number(effectiveSnapshot?.latest_replay_frames ?? 0) || 0,
    Number(effectiveSnapshot?.replay_frame_count ?? 0) || 0,
    Number(latestUploadResult?.latest_replay_frames ?? 0) || 0,
    Number(latestUploadResult?.replay_frame_count ?? 0) || 0,
    Number(
      latestUploadResult?.replay_timeline?.timeline?.length
      ?? latestUploadResult?.sii_intelligence?.replay_timeline?.timeline?.length
      ?? 0,
    ) || 0,
  );
  const effectiveReplayReady = Boolean(uploadJob?.replay_ready) || Number(uploadJob?.replay_frame_count ?? 0) > 0 || latestReplayFrames > 0;
  const effectiveReplayFrameCount = Math.max(Number(uploadJob?.replay_frame_count ?? 0) || 0, latestReplayFrames);
  const estimatedStageProgress = effectiveUploadState === "complete"
    ? 100
    : (Number.isFinite(statusFallbackPercent) ? Number(statusFallbackPercent) : null);
  const hasExplicitPropagationProgress = uploadJob?.propagation_progress !== undefined
    && uploadJob?.propagation_progress !== null
    && uploadJob?.propagation_progress !== "";
  const explicitPropagationPercent = hasExplicitPropagationProgress && Number.isFinite(uploadJob?.propagation_progress)
    ? Math.max(0, Math.min(100, Number(uploadJob?.propagation_progress)))
    : null;
  const statusDebug = [
    ["Job ID", uploadJob?.job_id ?? effectiveSnapshot?.history?.[0]?.job_id ?? "none"],
    ["Upload State", effectiveUploadState],
    ["Job Status", String(uploadJob?.status ?? "none")],
    ["Processing State", String(uploadJob?.processing_state ?? "none")],
    ["Backend Percent", backendPercent !== null ? `${backendPercent}%` : "n/a"],
    ["Propagation Stage", String(uploadJob?.propagation_stage ?? "none")],
    ...(explicitPropagationPercent !== null ? [["Propagation Progress", `${explicitPropagationPercent}%`]] : []),
    ...(estimatedStageProgress !== null ? [["Estimated Stage Progress", `${estimatedStageProgress}% (derived from upload state)`]] : []),
    ["Replay Ready", String(effectiveReplayReady)],
    ["Replay Frame Count", String(effectiveReplayFrameCount)],
    ["Snapshot Status", String(effectiveSnapshot?.status ?? "none")],
    ["Snapshot SII Completed", String(Boolean(effectiveSnapshot?.sii_completed))],
    ["Latest Result Present", String(Boolean(latestUploadResult))],
    ["Latest Replay Frames", String(latestReplayFrames)],
    ["Replay Source", String(uploadJob?.replay_source ?? latestUploadResult?.replay_timeline?.meta?.replay_source ?? latestUploadResult?.sii_intelligence?.replay_timeline?.meta?.replay_source ?? "unknown")],
  ];
  const workerState = String(uploadJob?.worker_state || "").toLowerCase();
  const workerLastSeenAt = String(uploadJob?.worker_last_seen_at || "").trim();
  const nowMs = Date.now();
  const lastSeenMs = workerLastSeenAt ? Date.parse(workerLastSeenAt) : NaN;
  const lastSeenAgeSeconds = Number.isFinite(lastSeenMs) ? Math.max(0, Math.round((nowMs - lastSeenMs) / 1000)) : null;
  const isQueuedState = ["queued", "pending"].includes(String(uploadJob?.processing_state ?? effectiveUploadState).toLowerCase());
  const queuedWorkerDetail = !isQueuedState
    ? ""
    : workerState === "starting"
      ? "Worker starting..."
      : workerState === "running"
        ? (Number.isFinite(lastSeenAgeSeconds)
          ? `Worker active • last update ${lastSeenAgeSeconds}s ago`
          : "Worker active")
        : workerState === "stalled"
          ? "Possible stall • no worker update yet"
          : "Still queued • waiting for worker";

  const debugProgressValue = backendPercent !== null
    ? backendPercent
    : 0;
  return ( 
    <div className="workspace-grid workspace-grid--connections workspace-grid--connections-clean">
      <ConnectionsHeaderPanel
        tabs={tabs}
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        onResetEverything={handleResetDemoClick}
        disableReset={false}
      />
      <IntakeFlowPanel
        handleUpload={handleUpload}
        uploadInputRef={uploadInputRef}
        handleFileSelection={handleFileSelection}
        selectedFiles={selectedFiles}
        latestUploadSnapshot={effectiveSnapshot}
        pendingUploadKind={pendingUploadKind}
        selectedFileSize={selectedFileSize}
        uploadReadinessMessage={uploadReadinessMessage}
        isUploadProcessing={isUploadProcessing}
        uploadState={uploadState}
        openFilePicker={openFilePicker}
        uploadJob={uploadJob}
        latestMessage={latestMessage}
        visibleProgressPercent={visibleProgressPercent}
        propagationLabel={propagationLabel}
        queuedWorkerDetail={queuedWorkerDetail}
        uploadTransfer={uploadTransfer}
        formatFileSize={formatFileSize}
        formatTransferSpeed={formatTransferSpeed}
        uploadStateMessage={uploadStateMessage}
        setCopyState={setCopyState}
        copyState={copyState}
        isJsonSchemaOpen={isJsonSchemaOpen}
        setIsJsonSchemaOpen={setIsJsonSchemaOpen}
        batchResults={batchResults}
        onRetryFailedUploads={() => processUploadBatch(batchResults.filter((item) => item.status === "failed").map((item) => item.file))}
        onReprocessCurrentBatch={handleReprocessCurrentBatch}
      />
      <section className="panel span-12 upload-debug-panel" aria-label="Replay debug status">
        <header className="panel-header">
          <h3>Debug Status</h3>
        </header>
        <div className="panel-body">
          <ul className="system-body-timeline-list">
            {statusDebug.map(([label, value]) => (
              <li key={label}>
                <span>{label}: </span>
                <strong>{value}</strong>
              </li>
            ))}
          </ul>
          <div style={{ marginTop: "0.8rem" }}>
            <p className="metadata-text" style={{ marginBottom: "0.35rem" }}>
              Backend Percent: {backendPercent !== null ? `${backendPercent}%` : "n/a"}
            </p>
            <div
              className="upload-progress-meter"
              aria-label="Backend upload progress"
              aria-valuemin="0"
              aria-valuemax="100"
              aria-valuenow={debugProgressValue}
              role="progressbar"
            >
              <span style={{ width: `${debugProgressValue}%` }} />
            </div>
          </div>
          {explicitPropagationPercent !== null ? (
            <div style={{ marginTop: "0.8rem" }}>
              <p className="metadata-text" style={{ marginBottom: "0.35rem" }}>
                Propagation Progress: {explicitPropagationPercent}%
              </p>
              <div
                className="upload-progress-meter"
                aria-label="Backend propagation progress"
                aria-valuemin="0"
                aria-valuemax="100"
                aria-valuenow={explicitPropagationPercent}
                role="progressbar"
              >
                <span style={{ width: `${explicitPropagationPercent}%` }} />
              </div>
            </div>
          ) : null}
          {estimatedStageProgress !== null ? (
            <p className="metadata-text" style={{ marginTop: "0.8rem" }}>
              Estimated Stage Progress: {estimatedStageProgress}% (derived from upload state)
            </p>
          ) : null}
        </div>
      </section>
      
    </div>
  );
}

function nextUploadPollDelay({ payload, failureCount = 0, failedAttempt = false }) {
  const hintedRetry = Number(payload?.retry_after_ms);
  if (Number.isFinite(hintedRetry) && hintedRetry >= 1000) {
    return Math.min(Math.max(hintedRetry, 1200), 120000);
  }

  const percent = Number(payload?.percent);
  const progress = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : null;
  let baseDelay = 1200;

  if (failedAttempt) {
    baseDelay = Math.min(6000 + failureCount * 12000, 120000);
  } else if (progress != null) {
    if (progress < 20) baseDelay = 900;
    else if (progress < 70) baseDelay = 1300;
    else if (progress < 95) baseDelay = 1700;
    else baseDelay = 2200;
  } else {
    baseDelay = 1500;
  }

  const hiddenMultiplier = typeof document !== "undefined" && document.visibilityState === "hidden" ? 1.35 : 1;
  return Math.round(baseDelay * hiddenMultiplier);
}
