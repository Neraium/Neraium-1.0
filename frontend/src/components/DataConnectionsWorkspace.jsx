import { startTransition, useDeferredValue, useEffect, useRef, useState } from "react";
import { API_BASE_URL, API_ROUTE_MODE, CONFIGURED_API_BASE_URL } from "../config";
import {
  normalizeUploadJob,
  uploadStagePercent,
} from "../viewModels/uploadContract";
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
import { retryUploadAnalysisJob, uploadTelemetryFileWithProgress } from "../services/api/uploadApi";
import IntakeFlowPanel from "./setup/IntakeFlowPanel";

const MAX_UPLOAD_BYTES = 250 * 1024 * 1024;
const LARGE_OPERATIONAL_UPLOAD_BYTES = 100 * 1024 * 1024;
const UPLOAD_REQUEST_TIMEOUT_MS = 4 * 60 * 60 * 1000;
const LAST_UPLOAD_JOB_ID_STORAGE_KEY = "neraium.last_upload_job_id";
const MAX_STATUS_POLL_FAILURES = 8;

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
  if (!Number.isFinite(bytes) || bytes <= 0) return "Awaiting file";
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(bytes / 1024, 1).toFixed(1)} KB`;
}

function isLargeOperationalUpload(file) {
  return (file?.size ?? 0) >= LARGE_OPERATIONAL_UPLOAD_BYTES;
}

function uploadReadinessMessage(file) {
  if (!file) return "Choose a telemetry file to begin.";
  if (isLargeOperationalUpload(file)) {
    return "Large telemetry export detected. Processing continues in the background.";
  }
  return "Telemetry export validated.";
}

function validateTelemetryFile(file, kind) {
  if (!file) return "Choose a telemetry file to analyze.";
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
  const baseDelay = 2000;
  const backoff = Math.min(30000, baseDelay * (1.5 ** failureCount));
  return Math.min(Math.max(backoff, 1000), 45000);
}

function queuedWorkerMessage(uploadJob) {
  const workerState = String(uploadJob?.worker_state ?? uploadJob?.workerState ?? "").toLowerCase();
  const lastUpdate = uploadJob?.worker_last_update_at ?? uploadJob?.worker_last_update ?? uploadJob?.updated_at ?? "";
  if (workerState === "starting") return "Worker starting...";
  if (workerState === "active" || workerState === "running") return `Worker active • last update ${lastUpdate || "just now"}`;
  if (workerState === "queued" || normalizeUploadStatus(uploadJob?.status) === "queued") return "Still queued • waiting for worker";
  if (workerState === "stalled") return "Possible stall • no worker update yet";
  return "";
}

function isActiveUploadProgressState(uploadState) {
  return ["uploading", "running_sii", "processing", "complete"].includes(String(uploadState || "").toLowerCase());
}

export default function DataConnectionsWorkspace({
  accessCode,
  apiFetch,
  latestUploadSnapshot,
  latestUploadResult,
  hasActiveSession = false,
  hasResumedSession = false,
  sessionStore,
  onUploadComplete,
  onResetDemo,
}) {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [pendingUploadKind, setPendingUploadKind] = useState("csv");
  const [uploadState, setUploadState] = useState("idle");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(latestUploadResult);
  const [uploadJob, setUploadJob] = useState(null);
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

  const setUploadProcessingFlag = (active) => {
    if (typeof window !== "undefined") {
      window.__NERAIUM_UPLOAD_IN_PROGRESS__ = Boolean(active);
    }
  };

  useEffect(() => {
    uploadStateRef.current = uploadState;
  }, [uploadState]);

  useEffect(() => {
    const active = ["running_sii", "processing", "uploading"].includes(String(uploadState || "").toLowerCase());
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
    if (typeof window === "undefined") return;
    const sessionJobId = String(sessionStore?.jobId ?? "").trim();
    if (!sessionJobId) return;
    if (!hasActiveSession && !hasResumedSession) return;
    const normalizedSessionJob = normalizeUploadJob({
      ...(sessionStore?.latestUploadSnapshot ?? {}),
      latest_result: sessionStore?.latestUploadResult ?? null,
      job_id: sessionJobId,
    });
    uploadJobIdRef.current = sessionJobId;
    uploadStatusPathRef.current = normalizeUploadStatusPath(normalizedSessionJob?.status_url, sessionJobId);
    window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, sessionJobId);
    setUploadJob(normalizedSessionJob);
    setUploadResult(sessionStore?.latestUploadResult ?? null);
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
    if (selectedFiles.length > 0 || hasResumedSession) return;
    setUploadTransfer(null);
    setUploadJob(null);
    if (uploadStateRef.current === "validated") {
      setUploadState("idle");
    }
  }, [hasResumedSession, selectedFiles.length]);

  useEffect(() => () => {
    pollSessionRef.current += 1;
    if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
    pollTimerRef.current = null;
    pollInFlightRef.current = null;
    pollOwnerJobIdRef.current = null;
  }, []);

  useEffect(() => { setUploadResult(latestUploadResult); }, [latestUploadResult]);

  function clearStoredUploadJobId() {
    if (typeof window !== "undefined") window.localStorage.removeItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY);
  }

  async function clearUploadClientState() {
    stopUploadPolling("reset_upload_client_state");
    uploadJobIdRef.current = null;
    uploadStatusPathRef.current = null;
    pollFailureCountRef.current = 0;
    setSelectedFiles([]);
    setUploadTransfer(null);
    setUploadJob(null);
    setUploadResult(null);
    setUploadError("");
    setUploadState("idle");
    setBatchResults([]);
    clearStoredUploadJobId();
    if (uploadInputRef.current) uploadInputRef.current.value = "";
    if (typeof window !== "undefined") {
      window.__NERAIUM_UPLOAD_COMPLETE__ = false;
      window.__NERAIUM_UPLOAD_IN_PROGRESS__ = false;
    }
    if (typeof onResetDemo === "function") {
      await onResetDemo();
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

  function markUploadFailed({ message, errorType = null, jobId = null, keepStoredJobId = false }) {
    stopUploadPolling("upload_failed");
    setUploadError(message);
    setUploadState("error");
    setUploadJob((current) => ({
      ...(current ?? {}),
      job_id: jobId ?? current?.job_id ?? null,
      status: "FAILED",
      processing_state: "failed",
      progress_label: message,
      message,
      error: message,
      error_type: errorType,
    }));
    if (!keepStoredJobId) clearStoredUploadJobId();
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
        try {
          const streamPath = normalizeUploadStreamPath(pollingPath, requestedJobId);
          if (streamPath && attempts === 1) {
            const streamed = await streamUploadStatusOnce({ streamPath, pollingJobId: requestedJobId });
            if (streamed) {
              const streamedStatus = normalizeUploadStatus(streamed.status);
              if (streamedStatus === "complete") {
                const completedPayload = { ...streamed, status: "COMPLETE", percent: 100, progress: 100, processing_state: "complete", progress_label: streamed?.progress_label || "Analysis ready.", message: streamed?.message || "Analysis ready." };
                setUploadJob(completedPayload);
                setUploadState("complete");
                setUploadProcessingFlag(false);
                return completedPayload;
              }
              pollingPath = normalizeUploadStatusPath(streamed?.status_url, requestedJobId) ?? pollingPath;
            }
          }
          const now = Date.now();
          const activeCooldownUntil = Math.max(Number(missingStatusCooldownUntilRef.current || 0), Number(statusEndpointCooldownUntilRef.current || 0));
          if (activeCooldownUntil > now) {
            await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, Math.max(1000, activeCooldownUntil - now)); });
            continue;
          }
          const requestPath = pollingPath;
          const response = await apiFetch(requestPath, { accessCode });
          const payload = await readJsonPayload(response);
          uploadJobIdRef.current = payload.job_id ?? requestedJobId;
          if (!response.ok) {
            if (response.status === 404 || response.status >= 500) {
              statusEndpointFailureCountRef.current += 1;
              if (statusEndpointFailureCountRef.current > MAX_STATUS_POLL_FAILURES) {
                pollFailureCountRef.current = MAX_STATUS_POLL_FAILURES;
                throw buildUploadRequestError(
                  response,
                  {
                    ...payload,
                    error_type: payload?.error_type || "upload_status_unavailable",
                    message: payload?.message || "Upload status remained unavailable after repeated retries.",
                  },
                  "poll",
                );
              }
              const cooldownMs = Math.min(120000, 20000 + statusEndpointFailureCountRef.current * 10000);
              statusEndpointCooldownUntilRef.current = Date.now() + cooldownMs;
              await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, cooldownMs); });
              continue;
            }
            throw buildUploadRequestError(response, payload, "poll");
          }
          statusEndpointFailureCountRef.current = 0;
          const normalizedPayload = normalizeStatusPayload(payload, requestedJobId);
          pollingPath = normalizeUploadStatusPath(normalizedPayload?.status_url, requestedJobId) ?? pollingPath;
          uploadStatusPathRef.current = pollingPath;
          startTransition(() => {
            setUploadJob(normalizedPayload);
          });
          const normalizedStatus = normalizeUploadStatus(normalizedPayload.status ?? normalizedPayload.processing_state ?? normalizedPayload.worker_state);
          const progressPercent = normalizedPayload.percent ?? normalizedPayload.progress ?? fallbackPercentFromStatus(normalizedStatus);
          const terminalSuccess = normalizedStatus === "complete" || Boolean(normalizedPayload.result_available || normalizedPayload.first_usable_available);
          if (terminalSuccess) {
            const completePayload = {
              ...normalizedPayload,
              status: "COMPLETE",
              processing_state: "complete",
              percent: 100,
              progress: 100,
              progress_label: normalizedPayload.progress_label || "Analysis ready.",
              message: normalizedPayload.message || "Analysis ready.",
            };
            setUploadJob(completePayload);
            setUploadState("complete");
            setUploadProcessingFlag(false);
            clearStoredUploadJobId();
            return completePayload;
          }
          if (["failed", "error", "validation_error", "cancelled", "timeout"].includes(normalizedStatus)) {
            throw buildUploadRequestError({ status: 500 }, normalizedPayload, "poll");
          }
          startTransition(() => {
            setUploadState("running_sii");
            if (typeof progressPercent === "number") {
              setUploadTransfer((current) => ({ ...(current ?? {}), percent: Math.max(current?.percent ?? 0, Math.min(progressPercent, 99)) }));
            }
          });
          await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, 1500); });
        } catch (error) {
          pollFailureCountRef.current += 1;
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
        if (completedPayload) {
          setUploadResult(uploadStateView.resolveCurrentUploadResult(completedPayload) ?? completedPayload);
        }
        if (completedPayload && typeof onUploadComplete === "function") {
          return onUploadComplete(completedPayload, { navigateToGate: false }).then(() => completedPayload);
        }
        return completedPayload;
      })
      .catch((error) => {
        const classified = classifyUploadError(error, "poll");
        markUploadFailed({ message: classified.message || normalizeErrorMessage(error, "Telemetry analysis failed."), errorType: classified.errorType, jobId: requestedJobId, keepStoredJobId: false });
        return null;
      })
      .finally(() => {
        pollInFlightRef.current = null;
        pollOwnerJobIdRef.current = null;
      });
    pollOwnerJobIdRef.current = requestedJobId;
    return pollInFlightRef.current;
  }

  async function streamUploadStatusOnce({ streamPath, pollingJobId }) {
    try {
      const response = await apiFetch(streamPath, { accessCode });
      if (!response.ok || !response.body) return null;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const startedAt = Date.now();
      while (Date.now() - startedAt < 6000 && shouldContinuePolling(pollingJobId)) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const eventText of events) {
          const dataLine = eventText.split("\n").find((line) => line.startsWith("data:"));
          if (!dataLine) continue;
          const payload = JSON.parse(dataLine.slice(5).trim());
          startTransition(() => {
            setUploadJob(normalizeStatusPayload(payload, pollingJobId));
          });
          if (normalizeUploadStatus(payload?.status) === "complete" || payload?.result_available || payload?.first_usable_available) {
            return payload;
          }
        }
      }
    } catch {
      return null;
    }
    return null;
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

  async function handleUpload() {
    if (!selectedFiles.length) {
      setUploadError("Choose a telemetry file before analysis.");
      return;
    }
    const file = selectedFiles[0];
    const validationError = validateTelemetryFile(file, pendingUploadKind);
    if (validationError) {
      setUploadError(validationError);
      return;
    }
    setUploadError("");
    console.info("[neraium] upload start", {
      filename: file.name,
      size: file.size,
    });
    setUploadState("uploading");
    setUploadProcessingFlag(true);
    setUploadTransfer({ percent: 0, loaded: 0, total: file.size, label: `Sending telemetry ${formatFileSize(0)} of ${formatFileSize(file.size)}` });
    try {
      const uploadResponse = await uploadTelemetryFileWithProgress({
        file,
        apiFetch,
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
      setUploadJob(normalizeStatusPayload(payload, jobId));
      setUploadState("running_sii");
      await pollUploadStatus(jobId, payload?.status_url);
    } catch (error) {
      const classified = classifyUploadError(error, "upload");
      markUploadFailed({ message: classified.message || normalizeErrorMessage(error, "Telemetry analysis failed."), errorType: classified.errorType });
    }
  }

  const readiness = uploadReadinessMessage(selectedFiles[0]);
  const hasActiveProgress = isActiveUploadProgressState(uploadState);
  const progressUploadJob = hasActiveProgress ? uploadJob : null;
  const progressUploadTransfer = hasActiveProgress ? uploadTransfer : null;
  const uploadTransferPercent = progressUploadTransfer?.percent;
  const propagationPercent = progressUploadJob?.propagation_progress ?? progressUploadJob?.propagationProgress;
  const backendPercent = progressUploadJob?.percent ?? progressUploadJob?.progress;
  const statusFallbackPercent = hasActiveProgress ? fallbackPercentFromStatus(uploadState) : null;
  const uploadPercent = [uploadTransferPercent, propagationPercent, backendPercent, statusFallbackPercent].find((value) => Number.isFinite(Number(value))) ?? null;
  const propagationLabel = progressUploadJob?.propagation_label ?? progressUploadJob?.propagationLabel ?? progressUploadJob?.propagation_stage ?? "";
  const statusLabel = progressUploadJob?.progress_label ?? progressUploadJob?.message ?? uploadStateMessage(uploadState);
  const isProcessingQuiet = ["running_sii", "processing"].includes(String(uploadState || "").toLowerCase())
    && normalizeUploadStatus(progressUploadJob?.status ?? progressUploadJob?.processing_state) !== "complete"
    && Date.now() - lastProgressAt > 6000
    && heartbeatTick >= 0;
  const visibleStatusLabel = isProcessingQuiet ? "Still processing..." : statusLabel;
  const queuedWorkerDetail = queuedWorkerMessage(progressUploadJob);
  const visibleProgressPercent = Number.isFinite(Number(uploadPercent))
    ? Math.max(0, Math.min(100, Math.round(Number(uploadPercent))))
    : null;
  const deferredProgressUploadJob = useDeferredValue(progressUploadJob);
  const deferredProgressUploadTransfer = useDeferredValue(progressUploadTransfer);
  const latestStatusMessage = uploadError || visibleStatusLabel || readiness;
  const deferredLatestStatusMessage = useDeferredValue(latestStatusMessage);
  const deferredVisibleProgressPercent = useDeferredValue(visibleProgressPercent);
  const deferredPropagationLabel = useDeferredValue(propagationLabel);
  const deferredQueuedWorkerDetail = useDeferredValue(queuedWorkerDetail);

  function handleFileSelection(event) {
    const files = Array.from(event?.target?.files ?? []);
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
    setUploadState(files.length ? "validated" : "idle");
  }

  function openFilePicker(kind = "csv") {
    setPendingUploadKind(kind);
    uploadInputRef.current?.click();
  }

  async function viewCompletedResults() {
    if (typeof onUploadComplete !== "function") return;
    const payload = uploadJob ?? uploadResult ?? latestUploadResult ?? latestUploadSnapshot ?? null;
    await onUploadComplete(payload, { navigateToGate: true });
  }

  async function retryCurrentBatch() {
    const currentJobId = String(uploadJob?.job_id ?? uploadJobIdRef.current ?? "").trim();
    if (!currentJobId) {
      await handleUpload();
      return;
    }
    setUploadError("");
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
      const classified = classifyUploadError(error, "upload");
      markUploadFailed({ message: classified.message || normalizeErrorMessage(error, "Telemetry analysis failed."), errorType: classified.errorType, jobId: currentJobId, keepStoredJobId: true });
    }
  }

  return (
    <div className="data-connections-workspace" data-testid="upload-workspace">
      <IntakeFlowPanel
        handleUpload={(event) => {
          event?.preventDefault?.();
          void handleUpload();
        }}
        uploadInputRef={uploadInputRef}
        handleFileSelection={handleFileSelection}
        selectedFiles={selectedFiles}
        latestUploadSnapshot={latestUploadSnapshot}
        pendingUploadKind={pendingUploadKind}
        selectedFileSize={formatFileSize(selectedFiles[0]?.size ?? 0)}
        isUploadProcessing={isUploadProcessing}
        uploadState={uploadState}
        openFilePicker={openFilePicker}
        uploadJob={deferredProgressUploadJob}
        latestMessage={deferredLatestStatusMessage}
        visibleProgressPercent={deferredVisibleProgressPercent}
        propagationLabel={deferredPropagationLabel}
        queuedWorkerDetail={deferredQueuedWorkerDetail}
        uploadTransfer={deferredProgressUploadTransfer}
        uploadDebug={uploadDebug}
        uploadStateMessage={uploadStateMessage}
        batchResults={batchResults}
        onRetryFailedUploads={() => { void retryCurrentBatch(); }}
        onReprocessCurrentBatch={() => { void retryCurrentBatch(); }}
        onResetWorkspace={() => { void clearUploadClientState(); }}
        onViewResults={() => { void viewCompletedResults(); }}
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

function normalizeUploadStreamPath(path, jobId) {
  const statusPath = normalizeUploadStatusPath(path, jobId);
  if (!statusPath) return null;
  if (statusPath.includes("/upload-stream/")) return statusPath;
  return statusPath.replace("/upload-status/", "/upload-stream/");
}
