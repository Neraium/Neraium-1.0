import { useCallback, useEffect, useRef, useState } from "react";
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
import IntakeFlowPanel from "./setup/IntakeFlowPanel";

const MAX_UPLOAD_BYTES = 250 * 1024 * 1024;
const LARGE_OPERATIONAL_UPLOAD_BYTES = 100 * 1024 * 1024;
const UPLOAD_REQUEST_TIMEOUT_MS = 10 * 60 * 1000;
const LAST_UPLOAD_JOB_ID_STORAGE_KEY = "neraium.last_upload_job_id";
const MAX_STATUS_POLL_FAILURES = 8;

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
  if (!file) return "Choose a telemetry file to begin.";
  if (isLargeOperationalUpload(file)) {
    return "Large telemetry export detected. Processing continues in the background.";
  }
  return "Telemetry export validated.";
}

function validateTelemetryFile(file, kind) {
  if (!file) return "Choose a CSV file to upload.";
  if (file.size > MAX_UPLOAD_BYTES) return `High-volume export above ${formatFileSize(MAX_UPLOAD_BYTES)}. Use partitioned export or enterprise batch intake.`;
  const filename = String(file.name ?? "").toLowerCase();
  const mime = String(file.type ?? "").toLowerCase();
  const looksCsv = filename.endsWith(".csv") || mime.includes("csv") || mime === "text/plain" || mime === "";
  if (kind === "csv" && !looksCsv) return "Choose a CSV file.";
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

export default function DataConnectionsWorkspace({
  accessCode,
  apiFetch,
  latestUploadSnapshot,
  latestUploadResult,
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
  const [batchResults, setBatchResults] = useState([]);
  void uploadResult;
  const [isResetViewActive, setIsResetViewActive] = useState(false);
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

  useEffect(() => {
    if (typeof window === "undefined") return;
    let cancelled = false;
    const restoreUploadSession = async () => {
      const storedJobId = String(window.localStorage.getItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY) ?? "").trim();
      const latestPayload = await loadLatestUpload();
      if (cancelled) return;
      const latestJobId = uploadStateView.resolveCurrentUploadJobId(latestPayload);
      const restoreJobId = latestJobId || storedJobId;
      const latestStatus = normalizeUploadStatus(latestPayload?.status ?? latestPayload?.snapshot?.status ?? "");
      const latestResult = uploadStateView.resolveCurrentUploadResult(latestPayload);
      if (!restoreJobId && !latestResult) return;
      uploadJobIdRef.current = restoreJobId || null;
      uploadStatusPathRef.current = normalizeUploadStatusPath(latestPayload?.status_url, restoreJobId);
      if (restoreJobId) window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, restoreJobId);
      if (latestResult || ["complete", "active", "running_sii"].includes(latestStatus)) {
        const restoredPayload = {
          ...(latestPayload ?? {}),
          job_id: restoreJobId || latestJobId || null,
          status: latestResult || latestStatus === "complete" ? "COMPLETE" : "PENDING",
          processing_state: latestResult || latestStatus === "complete" ? "complete" : "processing",
          percent: latestResult || latestStatus === "complete" ? 100 : undefined,
          progress: latestResult || latestStatus === "complete" ? 100 : undefined,
          result_available: Boolean(latestResult),
          progress_label: latestResult ? "Telemetry processing complete." : "Restored upload session. Checking processing status.",
          message: latestResult ? "Telemetry processing complete." : "Restored upload session. Checking processing status.",
        };
        setUploadJob(restoredPayload);
        setUploadResult(latestResult ?? latestPayload ?? null);
        if (latestResult || latestStatus === "complete") {
          setUploadState("complete");
          setUploadProcessingFlag(false);
          if (typeof onUploadComplete === "function") {
            await onUploadComplete(latestResult ?? latestPayload, { navigateToGate: false });
          }
          return;
        }
        setUploadState("running_sii");
        pollUploadStatus(restoreJobId, latestPayload?.status_url).catch(() => {});
      }
    };
    restoreUploadSession();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadLatestUpload, onUploadComplete]);

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

  function clearUploadClientState() {
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
    setIsResetViewActive(true);
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
      markUploadFailed({ message: "Upload session was not created. Try uploading again.", errorType: "missing_job_id" });
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
      let completeWithoutReplayCount = 0;
      while (shouldContinuePolling(requestedJobId) && pollSessionRef.current === pollSessionId) {
        attempts += 1;
        try {
          const streamPath = normalizeUploadStreamPath(pollingPath, requestedJobId);
          if (streamPath && attempts === 1) {
            const streamed = await streamUploadStatusOnce({ streamPath, pollingJobId: requestedJobId });
            if (streamed) {
              const streamedStatus = normalizeUploadStatus(streamed.status);
              if (streamedStatus === "complete" || Boolean(streamed?.result_available) || Boolean(streamed?.replay_ready)) {
                const completedPayload = { ...streamed, status: "COMPLETE", percent: 100, progress: 100, processing_state: "complete", progress_label: streamed?.progress_label || "Telemetry processing complete.", message: streamed?.message || "Telemetry processing complete." };
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
                  "Upload status remained unavailable after repeated retries. Try uploading again.",
                );
              }
              const cooldownMs = Math.min(120000, 20000 + statusEndpointFailureCountRef.current * 10000);
              statusEndpointCooldownUntilRef.current = Date.now() + cooldownMs;
              await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, cooldownMs); });
              continue;
            }
            throw buildUploadRequestError(response, payload, payload?.message || "Upload status could not be checked.");
          }
          statusEndpointFailureCountRef.current = 0;
          const normalizedPayload = normalizeStatusPayload(payload, requestedJobId);
          pollingPath = normalizeUploadStatusPath(normalizedPayload?.status_url, requestedJobId) ?? pollingPath;
          uploadStatusPathRef.current = pollingPath;
          setUploadJob(normalizedPayload);
          const normalizedStatus = normalizeUploadStatus(normalizedPayload.status ?? normalizedPayload.processing_state ?? normalizedPayload.worker_state);
          const progressPercent = normalizedPayload.percent ?? normalizedPayload.progress ?? fallbackPercentFromStatus(normalizedStatus);
          const hasResult = Boolean(normalizedPayload.result_available || normalizedPayload.latest_result || normalizedPayload.engine_result || normalizedPayload.operator_report);
          const hasReplay = Boolean(normalizedPayload.replay_ready || normalizedPayload.replay_frame_count || normalizedPayload.latest_replay_frames);
          if (normalizedStatus === "complete" || hasResult || hasReplay) {
            completeWithoutReplayCount += hasReplay ? 2 : 1;
            if (completeWithoutReplayCount >= 2 || hasReplay) {
              const completePayload = { ...normalizedPayload, status: "COMPLETE", processing_state: "complete", percent: 100, progress: 100, progress_label: normalizedPayload.progress_label || "Telemetry processing complete.", message: normalizedPayload.message || "Telemetry processing complete." };
              setUploadJob(completePayload);
              setUploadState("complete");
              setUploadProcessingFlag(false);
              clearStoredUploadJobId();
              return completePayload;
            }
          } else {
            completeWithoutReplayCount = 0;
          }
          if (["failed", "error", "validation_error", "cancelled"].includes(normalizedStatus)) {
            throw buildUploadRequestError({ status: 500 }, normalizedPayload, normalizedPayload.message || normalizedPayload.error || "Telemetry processing failed.");
          }
          setUploadState("running_sii");
          if (typeof progressPercent === "number") {
            setUploadTransfer((current) => ({ ...(current ?? {}), percent: Math.max(current?.percent ?? 0, Math.min(progressPercent, 99)) }));
          }
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
        if (completedPayload && typeof onUploadComplete === "function") {
          return onUploadComplete(completedPayload, { navigateToGate: true }).then(() => completedPayload);
        }
        return completedPayload;
      })
      .catch((error) => {
        const classified = classifyUploadError(error);
        markUploadFailed({ message: classified.message || normalizeErrorMessage(error, "Telemetry upload failed."), errorType: classified.errorType, jobId: requestedJobId, keepStoredJobId: false });
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
          setUploadJob(normalizeStatusPayload(payload, pollingJobId));
          if (normalizeUploadStatus(payload?.status) === "complete" || payload?.result_available || payload?.replay_ready) {
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
      setUploadError("Choose a telemetry file before uploading.");
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
    setUploadTransfer({ percent: 0, loaded: 0, total: file.size, label: "Preparing upload." });
    try {
      const uploadResponse = await uploadTelemetryFileWithProgress({
        file,
        apiFetch,
        accessCode,
        timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS,
        onProgress: (progress) => {
          setUploadTransfer({ ...progress, label: `Uploading ${formatFileSize(progress.loaded)} of ${formatFileSize(progress.total)} at ${formatTransferSpeed(progress.bytesPerSecond)}` });
        },
      });
      const payload = uploadResponse.payload;
      const jobId = uploadStateView.resolveCurrentUploadJobId(payload) || payload?.job_id;
      console.info("[neraium] upload success response", {
        jobId: jobId ?? null,
        status: normalizeUploadStatus(payload?.status ?? payload?.processing_state ?? payload?.worker_state),
      });
      if (!jobId) {
        markUploadFailed({ message: "Upload was accepted but no processing job was returned. Try again.", errorType: "missing_job_id" });
        return;
      }
      setUploadJob(normalizeStatusPayload(payload, jobId));
      setUploadState("running_sii");
      await pollUploadStatus(jobId, payload?.status_url);
    } catch (error) {
      const classified = classifyUploadError(error);
      markUploadFailed({ message: classified.message || normalizeErrorMessage(error, "Telemetry upload failed."), errorType: classified.errorType });
    }
  }

  const readiness = uploadReadinessMessage(selectedFiles[0]);
  const uploadTransferPercent = uploadTransfer?.percent;
  const propagationPercent = uploadJob?.propagation_progress ?? uploadJob?.propagationProgress;
  const backendPercent = uploadJob?.percent ?? uploadJob?.progress;
  const statusFallbackPercent = fallbackPercentFromStatus(uploadState);
  const uploadPercent = [uploadTransferPercent, propagationPercent, backendPercent, statusFallbackPercent].find((value) => Number.isFinite(Number(value))) ?? 0;
  const propagationLabel = uploadJob?.propagation_label ?? uploadJob?.propagationLabel ?? uploadJob?.propagation_stage ?? "";
  const statusLabel = uploadJob?.progress_label ?? uploadJob?.message ?? uploadStateMessage(uploadState);
  const queuedWorkerDetail = queuedWorkerMessage(uploadJob);
  const visibleProgressPercent = Number.isFinite(Number(uploadPercent))
    ? Math.max(0, Math.min(100, Math.round(Number(uploadPercent))))
    : null;

  function handleFileSelection(event) {
    const files = Array.from(event?.target?.files ?? []);
    setSelectedFiles(files);
    setIsResetViewActive(false);
    setUploadError("");
    setUploadState(files.length ? "validated" : "idle");
  }

  function openFilePicker(kind = "csv") {
    setPendingUploadKind(kind);
    uploadInputRef.current?.click();
  }

  function retryCurrentBatch() {
    void handleUpload();
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
        uploadJob={uploadJob}
        latestMessage={uploadError || statusLabel || readiness}
        visibleProgressPercent={visibleProgressPercent}
        propagationLabel={propagationLabel}
        queuedWorkerDetail={queuedWorkerDetail}
        uploadTransfer={uploadTransfer}
        uploadStateMessage={uploadStateMessage}
        batchResults={batchResults}
        onRetryFailedUploads={retryCurrentBatch}
        onReprocessCurrentBatch={retryCurrentBatch}
        onResetWorkspace={clearUploadClientState}
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
  if (statusPath.includes("/upload-status-stream/")) return statusPath;
  return statusPath.replace("/upload-status/", "/upload-status-stream/");
}
