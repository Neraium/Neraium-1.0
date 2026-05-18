import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  buildIntakeStages,
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
import { Panel } from "./workspacePrimitives";
import HistorianSetupWorkspace from "./setup/HistorianSetupWorkspace";
import IntakeStatusPanel from "./setup/IntakeStatusPanel";
import IntakeFlowPanel from "./setup/IntakeFlowPanel";
import { TAG_MAP_ROWS } from "./setup/setupConstants";

const MAX_UPLOAD_BYTES = 250 * 1024 * 1024;
const LARGE_OPERATIONAL_UPLOAD_BYTES = 100 * 1024 * 1024;
const UPLOAD_REQUEST_TIMEOUT_MS = 10 * 60 * 1000;

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
  hasRealSiiOutput,
  roomContext,
  onUploadComplete,
  onResetDemo,
  onResumePreviousSession,
  formatClockTime,
  demoTabId,
}) {
  const tabs = useMemo(() => [
    { id: "connect-live", label: "Live Link" },
    { id: "upload", label: "Upload Data" },
  ], []);

  const [selectedFiles, setSelectedFiles] = useState([]);
  const [activeTab, setActiveTab] = useState("connect-live");
  const [pendingUploadKind, setPendingUploadKind] = useState("csv");
  const [uploadState, setUploadState] = useState("idle");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(latestUploadResult);
  const [uploadJob, setUploadJob] = useState(null);
  const [uploadTransfer, setUploadTransfer] = useState(null);
  const [batchResults, setBatchResults] = useState([]);
  const [isJsonSchemaOpen, setIsJsonSchemaOpen] = useState(false);
  const [copyState, setCopyState] = useState("idle");
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
    if (!demoTabId) return;
    if (demoTabId === "upload") {
      setActiveTab("upload");
      return;
    }
    setActiveTab("connect-live");
  }, [demoTabId]);

  async function pollUploadStatus(jobId) {
    const pollingJobId = jobId || uploadJobIdRef.current;
    if (!pollingJobId) throw new Error("Upload polling could not start.");
    for (let attempts = 0; attempts < 240; attempts += 1) {
      try {
        const response = await apiFetch(`/api/data/upload-status/${pollingJobId}`, { accessCode });
        const payload = await readJsonPayload(response);
        if (!response.ok) throw buildUploadRequestError(response, payload, "poll");
        pollFailureCountRef.current = 0;
        uploadJobIdRef.current = payload.job_id ?? pollingJobId;
        setUploadJob(payload);
        const nextStatus = normalizeUploadStatus(payload.status);
        setUploadState(nextStatus);
        if (nextStatus === "complete") return payload;
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
    setUploadError("No local files available to reprocess. Re-select the source telemetry file(s) and retry.");
    setUploadState("validation_error");
  }

  async function processUploadBatch(filesToProcess) {
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
          setUploadJob(payload);
          setUploadState(normalizeUploadStatus(payload.status));
          await pollUploadStatus(payload.job_id);
          aggregateLoaded += file.size || 0;
          setBatchResults((current) => current.map((entry) => (entry.id === fileId
            ? { ...entry, status: "success", message: "Processed", jobId: payload.job_id }
            : entry)));
        } catch (fileError) {
          const uploadRequestError = fileError?.name === "UploadRequestError" && fileError?.payload
            ? buildUploadRequestError({ status: fileError.status }, fileError.payload, "upload")
            : fileError;
          const classified = classifyUploadError(uploadRequestError, "upload");
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
      setUploadResult(completedPayload);
      await onUploadComplete(completedPayload);
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
    setSelectedFiles([]);
    setUploadState("idle");
    setUploadError("");
    setUploadResult(null);
    setUploadJob(null);
    setUploadTransfer(null);
    setBatchResults([]);
    uploadJobIdRef.current = null;
    pollFailureCountRef.current = 0;
    if (pollTimerRef.current) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    if (uploadInputRef.current) uploadInputRef.current.value = "";
    if (onResetDemo) await onResetDemo();
  }

  const displayUploadError = uploadError;
  const intakeStages = uploadJob
    ? buildIntakeStages(uploadResult, uploadState, roomContext, uploadJob)
    : uploadResult
      ? buildIntakeStages(uploadResult, uploadState, roomContext, null)
      : uploadStateView.buildConnectionStateStages({ latestUploadSnapshot, uploadState, uploadError: displayUploadError, roomContext });
  const latestStatus = hasActiveSession ? (latestUploadSnapshot?.status ?? "empty") : "empty";
  const uploadDiffSummary = uploadStateView.buildUploadDiffSummary(latestUploadSnapshot?.history ?? []);
  const latestMessage = normalizeErrorMessage(displayUploadError || uploadJob?.error || uploadJob?.message || uploadJob?.progress_label || latestUploadSnapshot?.message || uploadStateMessage(uploadState));
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
  const baselineStatus = latestUploadSnapshot?.baseline_status;
  const baselineMessage = baselineStatus === "building" ? "Baseline Pending" : baselineStatus === "active" ? "Baseline Active" : "Baseline Pending";
  return (
    <div className="workspace-grid workspace-grid--connections">
      <Panel title="Historian Intake" className="span-12 workspace-hero-panel">
        <div className="intake-flow__controls" role="tablist" aria-label="Historian intake sections">
          {tabs.map((tab) => (
            <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} className={activeTab === tab.id ? "command-button" : "secondary-command-button"} onClick={() => setActiveTab(tab.id)}>
              {tab.label}
            </button>
          ))}
        </div>
      </Panel>

      {activeTab === "connect-live" && (
        <>
          <Panel title="Session Controls" className="span-12">
            <p className="narrative-text">
              Link a live source or resume the latest validated session.
            </p>
            <div className="intake-flow__controls">
              <button type="button" className="secondary-command-button" onClick={handleResetDemoClick} disabled={isUploadProcessing(uploadState)}>
                Reset Demo State
              </button>
              <button type="button" className="secondary-command-button" onClick={onResumePreviousSession} disabled={isUploadProcessing(uploadState)}>
                Resume Previous Session
              </button>
              <button type="button" className="command-button" onClick={() => setActiveTab("upload")}>
                Open Upload
              </button>
            </div>
          </Panel>
          <HistorianSetupWorkspace tagMapRows={TAG_MAP_ROWS} />
          <IntakeStatusPanel
            uploadStateView={uploadStateView}
            latestStatus={latestStatus}
            uploadState={uploadState}
            displayUploadError={displayUploadError}
            apiStatus={apiStatus}
            latestUploadSnapshot={latestUploadSnapshot}
            formatClockTime={formatClockTime}
            baselineMessage={baselineMessage}
            roomContext={roomContext}
            uploadDiffSummary={uploadDiffSummary}
            hasActiveSession={hasActiveSession}
            hasResumedSession={hasResumedSession}
            hasCurrentUploadResult={hasCurrentUploadResult}
            hasRealSiiOutput={hasRealSiiOutput}
            onResumePreviousSession={onResumePreviousSession}
            onOpenUpload={() => setActiveTab("upload")}
          />
        </>
      )}

      {activeTab === "upload" && (
        <>
          <IntakeFlowPanel
            handleUpload={handleUpload}
            uploadInputRef={uploadInputRef}
            handleFileSelection={handleFileSelection}
            selectedFiles={selectedFiles}
            latestUploadSnapshot={latestUploadSnapshot}
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
            intakeStages={intakeStages}
            batchResults={batchResults}
            onRetryFailedUploads={() => processUploadBatch(batchResults.filter((item) => item.status === "failed").map((item) => item.file))}
            onReprocessCurrentBatch={handleReprocessCurrentBatch}
          />
          <IntakeStatusPanel
            uploadStateView={uploadStateView}
            latestStatus={latestStatus}
            uploadState={uploadState}
            displayUploadError={displayUploadError}
            apiStatus={apiStatus}
            latestUploadSnapshot={latestUploadSnapshot}
            formatClockTime={formatClockTime}
            baselineMessage={baselineMessage}
            roomContext={roomContext}
            uploadDiffSummary={uploadDiffSummary}
            hasActiveSession={hasActiveSession}
            hasResumedSession={hasResumedSession}
            hasCurrentUploadResult={hasCurrentUploadResult}
            hasRealSiiOutput={hasRealSiiOutput}
            onResumePreviousSession={onResumePreviousSession}
            onOpenUpload={() => setActiveTab("upload")}
          />
        </>
      )}
    </div>
  );
}

function nextUploadPollDelay({ payload, failureCount = 0, failedAttempt = false }) {
  const hintedRetry = Number(payload?.retry_after_ms);
  if (Number.isFinite(hintedRetry) && hintedRetry >= 1000) {
    return Math.min(Math.max(hintedRetry, 1000), 30000);
  }

  const percent = Number(payload?.percent);
  const progress = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : null;
  let baseDelay = 2000;

  if (failedAttempt) {
    baseDelay = Math.min(2000 + failureCount * 1500, 15000);
  } else if (progress != null) {
    if (progress < 20) baseDelay = 1400;
    else if (progress < 70) baseDelay = 2200;
    else if (progress < 95) baseDelay = 3200;
    else baseDelay = 4200;
  } else {
    baseDelay = 2600;
  }

  const hiddenMultiplier = typeof document !== "undefined" && document.visibilityState === "hidden" ? 1.75 : 1;
  return Math.round(baseDelay * hiddenMultiplier);
}
