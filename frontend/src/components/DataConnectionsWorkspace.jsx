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
import IntakeFlowPanel from "./setup/IntakeFlowPanel";
import ConnectionsHeaderPanel from "./dataConnections/ConnectionsHeaderPanel";

const MAX_UPLOAD_BYTES = 250 * 1024 * 1024;
const LARGE_OPERATIONAL_UPLOAD_BYTES = 100 * 1024 * 1024;
const UPLOAD_REQUEST_TIMEOUT_MS = 10 * 60 * 1000;
const DATA_CONNECTIONS_TAB_STORAGE_KEY = "neraium.data_connections.active_tab";
const LAST_UPLOAD_JOB_ID_STORAGE_KEY = "neraium.last_upload_job_id";

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
  const uploadInputRef = useRef(null);

  const loadLatestUpload = useCallback(async () => {
    try {
      const response = await apiFetch("/api/data/latest-upload?include_persisted=1", { accessCode });
      const payload = await readJsonPayload(response);
      return response.ok ? payload : null;
    } catch {
      return null;
    }
  }, [accessCode, apiFetch]);

  useEffect(() => () => {
    if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current);
  }, []);

  useEffect(() => {
    setUploadResult(latestUploadResult);
  }, [latestUploadResult]);

  useEffect(() => {
    if (!latestUploadSnapshot) return;
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
  }, [latestUploadSnapshot]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(DATA_CONNECTIONS_TAB_STORAGE_KEY, activeTab);
  }, [activeTab]);

  async function pollUploadStatus(jobId) {
    const pollingJobId = jobId || uploadJobIdRef.current;
    if (!pollingJobId) throw new Error("Upload polling could not start.");
    let completeWithoutReplayCount = 0;
    let notFoundCount = 0;
    for (let attempts = 0; attempts < 240; attempts += 1) {
      try {
        const response = await apiFetch(`/api/data/upload-status/${pollingJobId}`, { accessCode });
        const payload = await readJsonPayload(response);
        if (!response.ok) throw buildUploadRequestError(response, payload, "poll");
        if (String(payload?.status ?? "").toUpperCase() === "NOT_FOUND") {
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
        if (typeof window !== "undefined" && uploadJobIdRef.current) {
          window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, String(uploadJobIdRef.current));
        }
        setUploadJob(payload);
        const nextStatus = normalizeUploadStatus(payload.status);
        setUploadState(nextStatus);
        const replayReady = Boolean(payload?.replay_ready) || Number(payload?.replay_frame_count ?? 0) > 0;
        if (nextStatus === "complete" && replayReady) return payload;
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
        if (classified.retryable && pollFailureCountRef.current < 30) {
          pollFailureCountRef.current += 1;
          setUploadState((current) => (isUploadProcessing(current) ? current : "running_sii"));
          setUploadError(classified.message);
          const delayMs = nextUploadPollDelay({ payload: null, failureCount: pollFailureCountRef.current, failedAttempt: true });
          await new Promise((resolve) => {
            pollTimerRef.current = window.setTimeout(resolve, delayMs);
          });
          continue;
        }
        setUploadError(classified.finalMessage ?? classified.message);
        setUploadState(classified.retryable ? "error" : classified.state);
        throw error;
      }
    }
    throw new Error("Upload polling timed out.");
  }

  async function handleUpload(event) {
    event.preventDefault();
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
      setUploadJob(payload);
      setUploadState(normalizeUploadStatus(payload?.status ?? "pending"));
      await pollUploadStatus(uploadJobIdRef.current);

      const latestPayload = await loadLatestUpload();
      const latestResult = latestPayload?.latest_result;
      const completedPayload = {
        ...(uploadStateView.hasFullUploadResult(latestResult) ? latestResult : {}),
        ...(latestPayload ?? {}),
      };
      setUploadResult(completedPayload);
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
    if (pollTimerRef.current) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    const validationError = filesToProcess.length === 0
      ? "Choose one or more CSV/JSON telemetry files to upload."
      : validateTelemetryFile(filesToProcess[0], pendingUploadKind);
    if (validationError) {
      setUploadError(validationError);
      setUploadState("validation_error");
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
    pollFailureCountRef.current = 0;
    try {
      let aggregateLoaded = 0;
      let successCount = 0;
      let failedCount = 0;
      for (const [index, file] of filesToProcess.entries()) {
        const startingLoaded = aggregateLoaded;
        const fileId = `${file.name}-${file.size}-${file.lastModified ?? Date.now()}`;
        setBatchResults((current) => current.map((entry) => (entry.id === fileId ? { ...entry, status: "uploading", message: "Uploading" } : entry)));
        const { ok, status, payload } = await uploadTelemetryFileWithProgress({
          file,
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
          if (!payload?.job_id) throw buildUploadRequestError({ status }, { ...payload, error_type: "upload_session_missing", message: "Upload state unavailable." }, "upload");
          uploadJobIdRef.current = payload.job_id;
          if (typeof window !== "undefined" && uploadJobIdRef.current) {
            window.localStorage.setItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY, String(uploadJobIdRef.current));
          }
          setUploadJob(payload);
          setUploadState(normalizeUploadStatus(payload.status));
          await pollUploadStatus(payload.job_id);
          aggregateLoaded += file.size || 0;
          successCount += 1;
          setBatchResults((current) => current.map((entry) => (entry.id === fileId
            ? { ...entry, status: "success", message: "Processed", jobId: payload.job_id }
            : entry)));
        } catch (fileError) {
          const uploadRequestError = fileError?.name === "UploadRequestError" && fileError?.payload
            ? buildUploadRequestError({ status: fileError.status }, fileError.payload, "upload")
            : fileError;
          const classified = classifyUploadError(uploadRequestError, "upload");
          failedCount += 1;
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
      if (failedCount > 0) {
        if (successCount === 0) {
          setUploadResult(null);
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
      setUploadError(classified.message);
      setUploadState(classified.state);
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
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(LAST_UPLOAD_JOB_ID_STORAGE_KEY);
    }
    pollFailureCountRef.current = 0;
    if (pollTimerRef.current) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    if (uploadInputRef.current) uploadInputRef.current.value = "";
    if (onResetDemo) await onResetDemo(); 
  } 

  const displayUploadError = uploadError; 
  const effectiveSnapshot = isResetViewActive
    ? uploadStateView.buildEmptyLatestUploadSnapshot()
    : latestUploadSnapshot;
  const latestMessage = normalizeErrorMessage(displayUploadError || uploadJob?.error || uploadJob?.message || uploadJob?.progress_label || effectiveSnapshot?.message || uploadStateMessage(uploadState));
  const selectedFileSize = formatFileSize(selectedFiles.reduce((sum, file) => sum + (file.size || 0), 0));
  const uploadTransferPercent = Number.isFinite(uploadTransfer?.percent) ? Math.min(100, Math.max(0, uploadTransfer.percent)) : null;
  const backendPercent = Number.isFinite(uploadJob?.percent ?? uploadJob?.progress) ? Math.min(100, Math.max(0, uploadJob.percent ?? uploadJob.progress)) : null;
  const statusFallbackPercent = fallbackPercentFromStatus(uploadJob?.status ?? uploadState);
  const preferredPercent = [uploadTransferPercent, backendPercent, statusFallbackPercent]
    .filter((value) => Number.isFinite(value))
    .reduce((maxValue, value) => Math.max(maxValue, value), 0);
  const visibleProgressPercent = isUploadProcessing(uploadState)
    ? Math.max(1, Math.min(99, preferredPercent))
    : (normalizeUploadStatus(uploadState) === "complete" ? 100 : null);
  const latestReplayFrames =
    Number(
      latestUploadResult?.replay_timeline?.timeline?.length
      ?? latestUploadResult?.sii_intelligence?.replay_timeline?.timeline?.length
      ?? 0,
    ) || 0;
  const effectiveReplayReady = Boolean(uploadJob?.replay_ready) || Number(uploadJob?.replay_frame_count ?? 0) > 0 || latestReplayFrames > 0;
  const effectiveReplayFrameCount = Math.max(Number(uploadJob?.replay_frame_count ?? 0) || 0, latestReplayFrames);
  const uploadStatePercent = Number.isFinite(statusFallbackPercent) ? Number(statusFallbackPercent) : 0;
  const jobStatusPercent = Number.isFinite(uploadJob?.percent ?? uploadJob?.progress)
    ? Math.max(0, Math.min(100, Number(uploadJob?.percent ?? uploadJob?.progress)))
    : uploadStatePercent;
  const statusDebug = [
    ["Job ID", uploadJob?.job_id ?? effectiveSnapshot?.history?.[0]?.job_id ?? "none"],
    ["Upload State", normalizeUploadStatus(uploadState)],
    ["Upload State %", `${uploadStatePercent}%`],
    ["Job Status", String(uploadJob?.status ?? "none")],
    ["Job Status %", `${jobStatusPercent}%`],
    ["Processing State", String(uploadJob?.processing_state ?? "none")],
    ["Percent", String(uploadJob?.percent ?? uploadJob?.progress ?? "n/a")],
    ["Replay Ready", String(effectiveReplayReady)],
    ["Replay Frame Count", String(effectiveReplayFrameCount)],
    ["Snapshot Status", String(effectiveSnapshot?.status ?? "none")],
    ["Snapshot SII Completed", String(Boolean(effectiveSnapshot?.sii_completed))],
    ["Latest Result Present", String(Boolean(latestUploadResult))],
    ["Latest Replay Frames", String(latestReplayFrames)],
    ["Replay Source", String(uploadJob?.replay_source ?? latestUploadResult?.replay_timeline?.meta?.replay_source ?? latestUploadResult?.sii_intelligence?.replay_timeline?.meta?.replay_source ?? "unknown")],
  ];
  const debugProgressValue = Number.isFinite(uploadJob?.percent ?? uploadJob?.progress)
    ? Math.max(0, Math.min(100, Number(uploadJob?.percent ?? uploadJob?.progress)))
    : Number.isFinite(visibleProgressPercent)
      ? Math.max(0, Math.min(100, Number(visibleProgressPercent)))
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
      <section className="panel span-12" aria-label="Replay debug status">
        <header className="panel-header">
          <h3>Debug Status</h3>
        </header>
        <div className="panel-body">
          <ul className="system-body-timeline-list">
            {statusDebug.map(([label, value]) => (
              <li key={label}><span>{label}</span><strong>{value}</strong></li>
            ))}
          </ul>
          <div style={{ marginTop: "0.6rem" }}>
            <div
              className="upload-progress-meter"
              aria-label="Debug upload progress"
              aria-valuemin="0"
              aria-valuemax="100"
              aria-valuenow={debugProgressValue}
              role="progressbar"
            >
              <span style={{ width: `${debugProgressValue}%` }} />
            </div>
          </div>
        </div>
      </section>
      
    </div>
  );
}

function nextUploadPollDelay({ payload, failureCount = 0, failedAttempt = false }) {
  const hintedRetry = Number(payload?.retry_after_ms);
  if (Number.isFinite(hintedRetry) && hintedRetry >= 1000) {
    return Math.min(Math.max(hintedRetry, 800), 12000);
  }

  const percent = Number(payload?.percent);
  const progress = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : null;
  let baseDelay = 1200;

  if (failedAttempt) {
    baseDelay = Math.min(1200 + failureCount * 900, 8000);
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
