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
import { buildApiCandidateUrls } from "../config";
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
    return "Large file selected. Processing continues in the background.";
  }
  return "File ready to upload.";
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
          pollFailureCountRef.current = 0;
          uploadJobIdRef.current = payload.job_id ?? requestedJobId;
          uploadStatusPathRef.current = normalizeUploadStatusPath(payload?.status_url, uploadJobIdRef.current) ?? pollingPath;
          setUploadJob(payload);
          const nextStatus = normalizeUploadStatus(payload.status);
          const backendPercent = Number(payload?.percent ?? payload?.progress ?? 0);
          const resultAvailable = Boolean(payload?.result_available);
          const replayReady = Boolean(payload?.replay_ready) || Number(payload?.replay_frame_count ?? 0) > 0;
          if (nextStatus === "complete" || backendPercent >= 100 || resultAvailable || replayReady) {
            if (typeof window !== "undefined") window.__NERAIUM_UPLOAD_COMPLETE__ = true;
            setUploadProcessingFlag(false);
            const completedPayload = { ...payload, status: "COMPLETE", percent: 100, progress: 100, processing_state: "complete", progress_label: payload?.progress_label || "Telemetry processing complete.", message: payload?.message || "Telemetry processing complete." };
            setUploadJob(completedPayload);
            setUploadState("complete");
            return completedPayload;
          }
          setUploadState(nextStatus);
          if (nextStatus === "complete" && !replayReady) {
            completeWithoutReplayCount += 1;
            if (completeWithoutReplayCount >= 5) return payload;
            setUploadState("generating_replay");
          }
          if (nextStatus === "failed") throw buildUploadRequestError(response, payload, "poll");
          const delayMs = nextUploadPollDelay({ payload, failureCount: pollFailureCountRef.current });
          await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, delayMs); });
        } catch (error) {
          const classified = classifyUploadError(error, "poll");
          if (classified.retryable && pollFailureCountRef.current < MAX_STATUS_POLL_FAILURES && shouldContinuePolling(requestedJobId)) {
            pollFailureCountRef.current += 1;
            setUploadState((current) => (isUploadProcessing(current) ? current : "running_sii"));
            setUploadError(classified.message);
            const delayMs = nextUploadPollDelay({ payload: null, failureCount: pollFailureCountRef.current, failedAttempt: true });
            await new Promise((resolve) => { pollTimerRef.current = window.setTimeout(resolve, delayMs); });
            continue;
          }
          markUploadFailed({ message: classified.finalMessage ?? classified.message, errorType: classified.errorType ?? error?.errorType ?? error?.error_type ?? null, jobId: requestedJobId, keepStoredJobId: Boolean(requestedJobId) });
          throw error;
        }
      }
    };
    pollOwnerJobIdRef.current = requestedJobId;
    pollInFlightRef.current = runPoll();
    try { return await pollInFlightRef.current; }
    finally {
      if (pollSessionRef.current === pollSessionId) {
        pollInFlightRef.current = null;
        pollOwnerJobIdRef.current = null;
      }
    }
  }

  async function streamUploadStatusOnce({ streamPath, pollingJobId }) {
    if (!streamPath || typeof window === "undefined" || typeof window.EventSource === "undefined") return null;
    const urls = buildApiCandidateUrls(streamPath);
    for (const url of urls) {
      const payload = await new Promise((resolve) => {
        let resolved = false;
        let lastPayload = null;
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
          try { parsed = JSON.parse(event.data || "{}"); } catch { parsed = null; }
          if (!parsed || String(parsed.job_id || "") !== String(pollingJobId || "")) return;
          lastPayload = parsed;
          setUploadJob(parsed);
          const s = normalizeUploadStatus(parsed.status);
          if (s && !["complete", "failed"].includes(s)) setUploadState(s);
          if (["complete", "failed"].includes(s)) {
            resolved = true;
            window.clearTimeout(timer);
            try { es.close(); } catch {}
            resolve(parsed);
          }
        };
        es.onerror = () => {
          if (resolved) return;
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

  async function processUploadBatch(filesToProcess) {
    if (uploadInFlightRef.current) return;
    uploadInFlightRef.current = true;
    stopUploadPolling("new_upload_request");
    setUploadProcessingFlag(true);
    let keepProcessingLock = false;
    const validationError = filesToProcess.length === 0 ? "Choose a CSV file to upload." : validateTelemetryFile(filesToProcess[0], pendingUploadKind);
    if (validationError) {
      setUploadError(validationError);
      setUploadState("validation_error");
      uploadInFlightRef.current = false;
      setUploadProcessingFlag(false);
      return;
    }
    setUploadState("uploading");
    setUploadError("");
    const totalBytes = filesToProcess.reduce((sum, file) => sum + (file.size || 0), 0);
    setUploadJob({ job_id: null, status: "uploading", progress_label: "Upload started.", message: "Uploading telemetry export.", file_size_bytes: totalBytes });
    setUploadTransfer({ loaded: 0, total: totalBytes, percent: 0, speedBytesPerSecond: 0, stage: "upload_started" });
    setBatchResults(filesToProcess.map((file) => ({ id: `${file.name}-${file.size}-${file.lastModified ?? Date.now()}`, file, fileName: file.name, status: "pending", message: "Waiting", jobId: null })));
    uploadJobIdRef.current = null;
    uploadStatusPathRef.current = null;
    clearStoredUploadJobId();
    pollFailureCountRef.current = 0;
    try {
      let successCount = 0;
      let failedCount = 0;
      let hasBackgroundProcessing = false;
      for (const [index, file] of filesToProcess.entries()) {
        const fileId = `${file.name}-${file.size}-${file.lastModified ?? Date.now()}`;
        setBatchResults((current) => current.map((entry) => (entry.id === fileId ? { ...entry, status: "uploading", message: "Uploading" } : entry)));
        const { ok, status, payload } = await uploadTelemetryFileWithProgress({
          file,
          accessCode,
          timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS,
          onProgress: (progress) => {
            const percent = totalBytes > 0 ? Math.min(100, Math.round(((progress.loaded ?? 0) / totalBytes) * 100)) : 0;
            setUploadTransfer({ ...progress, loaded: progress.loaded ?? 0, total: totalBytes, percent });
            setUploadJob((current) => ({ ...(current ?? {}), status: progress.stage === "accepted" ? "pending" : "uploading", progress_label: `Uploading file ${index + 1}/${filesToProcess.length} - ${percent}% - ${formatTransferSpeed(progress.speedBytesPerSecond)}`, message: progress.message, file_size_bytes: totalBytes, bytes_processed: progress.loaded ?? 0 }));
          },
        });
        try {
          if (!ok) throw buildUploadRequestError({ status }, payload, "upload");
          const returnedJobId = payload?.job_id ?? payload?.jobId ?? payload?.id;
          if (!returnedJobId) throw buildUploadRequestError({ status }, { ...payload, error_type: "upload_session_missing", message: "Upload state unavailable." }, "upload");
          uploadJobIdRef.current = returnedJobId;
          if (typeof window !== "undefined") window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, String(returnedJobId));
          const normalizedPayload = { ...payload, job_id: returnedJobId };
          uploadStatusPathRef.current = normalizeUploadStatusPath(normalizedPayload?.status_url, returnedJobId);
          setUploadJob(normalizedPayload);
          setUploadState(normalizeUploadStatus(normalizedPayload.status));
          await pollUploadStatus(returnedJobId, normalizedPayload?.status_url);
          successCount += 1;
          setBatchResults((current) => current.map((entry) => (entry.id === fileId ? { ...entry, status: "success", message: "Processed", jobId: returnedJobId } : entry)));
        } catch (fileError) {
          const classified = classifyUploadError(fileError, "upload");
          failedCount += 1;
          setBatchResults((current) => current.map((entry) => (entry.id === fileId ? { ...entry, status: "failed", message: classified.message, jobId: payload?.job_id ?? null } : entry)));
        }
      }
      const latestPayload = await loadLatestUpload();
      const latestResult = uploadStateView.resolveCurrentUploadResult(latestPayload);
      const completedPayload = { ...(uploadStateView.hasFullUploadResult(latestResult) ? latestResult : {}), ...(latestPayload ?? {}) };
      setUploadTransfer({ loaded: totalBytes, total: totalBytes, percent: 100, speedBytesPerSecond: 0, stage: "accepted", message: "All files processed." });
      if (hasBackgroundProcessing && failedCount === 0) {
        keepProcessingLock = true;
        setUploadResult(completedPayload);
        setUploadState("running_sii");
        setUploadError("Upload accepted. Processing continues in background.");
        return;
      }
      if (failedCount > 0) {
        stopUploadPolling("upload_batch_failed");
        setUploadState("error");
        setUploadError(`Processed ${successCount} file(s), ${failedCount} failed. Retry failed files.`);
        return;
      }
      setUploadResult(completedPayload);
      if (typeof window !== "undefined") window.__NERAIUM_UPLOAD_COMPLETE__ = true;
      keepProcessingLock = false;
      setUploadProcessingFlag(false);
      setIsResetViewActive(false);
      if (typeof onUploadComplete === "function") await onUploadComplete(completedPayload);
      setUploadState("complete");
    } catch (error) {
      const classified = classifyUploadError(error, "upload");
      markUploadFailed({ message: classified.finalMessage ?? classified.message, errorType: classified.errorType ?? error?.errorType ?? error?.error_type ?? null, jobId: uploadJobIdRef.current, keepStoredJobId: Boolean(uploadJobIdRef.current) });
      keepProcessingLock = false;
    } finally {
      uploadInFlightRef.current = false;
      if (!keepProcessingLock) setUploadProcessingFlag(false);
    }
  }

  function openFilePicker(kind) {
    setPendingUploadKind("csv");
    if (uploadInputRef.current) {
      uploadInputRef.current.value = "";
      uploadInputRef.current.multiple = true;
      uploadInputRef.current.accept = ".csv,text/csv";
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
      setUploadJob({ job_id: null, status: "validated", progress_label: nextFiles.length > 1 ? `${nextFiles.length} telemetry files validated.` : (isLargeOperationalUpload(nextFiles[0]) ? "Large telemetry export detected." : "Telemetry export validated."), message: uploadReadinessMessage(nextFiles[0]), file_size_bytes: totalBytes });
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
      markUploadFailed({ message: normalizeErrorMessage(error?.message || error?.detail || "Reset Everything failed."), errorType: "reset_failed", jobId: uploadJobIdRef.current, keepStoredJobId: Boolean(uploadJobIdRef.current) });
    }
  }

  const displayUploadError = uploadError;
  const effectiveSnapshot = isResetViewActive ? uploadStateView.buildEmptyLatestUploadSnapshot() : latestUploadSnapshot;
  const latestMessage = normalizeErrorMessage(displayUploadError || uploadJob?.error || uploadJob?.propagation_label || uploadJob?.progress_label || uploadJob?.message || effectiveSnapshot?.message || uploadStateMessage(uploadState));
  const selectedFileSize = formatFileSize(selectedFiles.reduce((sum, file) => sum + (file.size || 0), 0));
  const uploadTransferPercent = Number.isFinite(uploadTransfer?.percent) ? Math.min(100, Math.max(0, uploadTransfer.percent)) : null;
  const backendPercent = Number.isFinite(uploadJob?.percent ?? uploadJob?.progress) ? Math.min(100, Math.max(0, uploadJob.percent ?? uploadJob.progress)) : null;
  const propagationPercent = Number.isFinite(uploadJob?.propagation_progress) ? Math.min(100, Math.max(0, Number(uploadJob?.propagation_progress))) : backendPercent;
  const currentJobId = String(uploadJob?.job_id ?? uploadJobIdRef.current ?? "").trim();
  const latestResultJobId = String(latestUploadSnapshot?.current_upload?.job_id ?? latestUploadResult?.job_id ?? "").trim();
  const latestResultMatchesCurrentJob = Boolean(currentJobId) && currentJobId === latestResultJobId;
  const backendComplete = String(uploadJob?.processing_state ?? "").toLowerCase() === "complete" || Number(uploadJob?.percent ?? uploadJob?.progress ?? 0) >= 100 || Boolean(uploadJob?.result_available) || latestResultMatchesCurrentJob;
  const effectiveUploadState = backendComplete ? "complete" : normalizeUploadStatus(uploadState);
  const statusFallbackPercent = fallbackPercentFromStatus(uploadJob?.status ?? effectiveUploadState);
  const preferredPercent = [uploadTransferPercent, propagationPercent, backendPercent, statusFallbackPercent].filter((value) => Number.isFinite(value)).reduce((maxValue, value) => Math.max(maxValue, value), 0);
  const visibleProgressPercent = backendPercent >= 100 || effectiveUploadState === "complete" ? 100 : isUploadProcessing(uploadState) ? Math.max(1, Math.min(99, preferredPercent)) : null;
  const workerState = String(uploadJob?.worker_state || "").toLowerCase();
  const workerLastSeenAt = String(uploadJob?.worker_last_seen_at || "").trim();
  const nowMs = Date.now();
  const lastSeenMs = workerLastSeenAt ? Date.parse(workerLastSeenAt) : NaN;
  const lastSeenAgeSeconds = Number.isFinite(lastSeenMs) ? Math.max(0, Math.round((nowMs - lastSeenMs) / 1000)) : null;
  const isQueuedState = ["queued", "pending"].includes(String(uploadJob?.processing_state ?? effectiveUploadState).toLowerCase());
  const queuedWorkerDetail = !isQueuedState ? "" : workerState === "starting" ? "Worker starting..." : workerState === "running" ? (Number.isFinite(lastSeenAgeSeconds) ? `Worker active • last update ${lastSeenAgeSeconds}s ago` : "Worker active") : workerState === "stalled" ? "Possible stall • no worker update yet" : "Still queued • waiting for worker";

  return (
    <div className="workspace-grid workspace-grid--connections workspace-grid--connections-clean">
      <IntakeFlowPanel
        handleUpload={handleUpload}
        uploadInputRef={uploadInputRef}
        handleFileSelection={handleFileSelection}
        selectedFiles={selectedFiles}
        latestUploadSnapshot={effectiveSnapshot}
        pendingUploadKind={pendingUploadKind}
        selectedFileSize={selectedFileSize}
        isUploadProcessing={isUploadProcessing}
        uploadState={uploadState}
        openFilePicker={openFilePicker}
        uploadJob={uploadJob}
        latestMessage={latestMessage}
        visibleProgressPercent={visibleProgressPercent}
        propagationLabel={String(uploadJob?.propagation_label ?? uploadJob?.progress_label ?? uploadJob?.message ?? "").trim()}
        queuedWorkerDetail={queuedWorkerDetail}
        uploadTransfer={uploadTransfer}
        formatFileSize={formatFileSize}
        formatTransferSpeed={formatTransferSpeed}
        uploadStateMessage={uploadStateMessage}
        batchResults={batchResults}
        onRetryFailedUploads={() => processUploadBatch(batchResults.filter((item) => item.status === "failed").map((item) => item.file))}
        onReprocessCurrentBatch={() => processUploadBatch(selectedFiles)}
        onResetWorkspace={handleResetDemoClick}
      />
    </div>
  );
}

function nextUploadPollDelay({ payload, failureCount = 0, failedAttempt = false }) {
  const hintedRetry = Number(payload?.retry_after_ms);
  if (Number.isFinite(hintedRetry) && hintedRetry >= 1000) return Math.min(Math.max(hintedRetry, 1200), 120000);
  const percent = Number(payload?.percent);
  const progress = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : null;
  let baseDelay = 1200;
  if (progress !== null) {
    if (progress < 25) baseDelay = 1200;
    else if (progress < 70) baseDelay = 2000;
    else if (progress < 95) baseDelay = 3500;
    else baseDelay = 5000;
  }
  if (failedAttempt) baseDelay = Math.max(baseDelay, 4000);
  const backoff = failureCount > 0 ? Math.min(30000, baseDelay * (1.5 ** failureCount)) : baseDelay;
  return Math.round(Math.min(Math.max(backoff, 1000), 45000));
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
