import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  buildIntakeStages,
  buildUploadRequestError,
  classifyUploadError,
  isUploadProcessing,
  normalizeErrorMessage,
  normalizeUploadStatus,
  operatorUploadMessage,
  readJsonPayload,
  uploadStateMessage,
} from "../viewModels/uploadFlow";
import * as uploadStateView from "../viewModels/uploadState";
import { uploadTelemetryFileWithProgress } from "../services/api/uploadApi";
import { Panel } from "./workspacePrimitives";
import HistorianSetupWorkspace from "./setup/HistorianSetupWorkspace";
import IntakeStatusPanel from "./setup/IntakeStatusPanel";
import IntakeFlowPanel from "./setup/IntakeFlowPanel";
import DiagnosticsPanel from "./setup/DiagnosticsPanel";
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
}) {
  const tabs = useMemo(() => [
    { id: "overview", label: "Overview" },
    { id: "historian-setup", label: "Setup" },
    { id: "upload", label: "Upload" },
    { id: "diagnostics", label: "Diagnostics" },
  ], []);

  const [selectedFile, setSelectedFile] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [pendingUploadKind, setPendingUploadKind] = useState("csv");
  const [uploadState, setUploadState] = useState("idle");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(latestUploadResult);
  const [uploadJob, setUploadJob] = useState(null);
  const [uploadTransfer, setUploadTransfer] = useState(null);
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

  async function pollUploadStatus(jobId) {
    const pollingJobId = jobId || uploadJobIdRef.current;
    if (!pollingJobId) return;
    try {
      const response = await apiFetch(`/api/data/upload-status/${pollingJobId}`, { accessCode });
      const payload = await readJsonPayload(response);
      if (!response.ok) throw buildUploadRequestError(response, payload, "poll");
      pollFailureCountRef.current = 0;
      uploadJobIdRef.current = payload.job_id ?? pollingJobId;
      setUploadJob(payload);
      const nextStatus = normalizeUploadStatus(payload.status);
      setUploadState(nextStatus);
      if (nextStatus === "complete") {
        const latestPayload = await loadLatestUpload();
        const latestResult = latestPayload?.latest_result;
        const completedPayload = {
          ...(uploadStateView.hasFullUploadResult(latestResult) ? latestResult : {}),
          ...(latestPayload ?? {}),
          filename: latestPayload?.last_filename ?? payload.filename,
          row_count: latestPayload?.rows_processed ?? payload.rows_processed,
          column_count: latestPayload?.columns_detected ?? payload.columns_detected,
          job_status: payload,
        };
        setUploadResult(completedPayload);
        await onUploadComplete(completedPayload);
        return;
      }
      if (nextStatus === "failed") {
        setUploadError(operatorUploadMessage({ status: response.status, errorType: payload.error_type ?? "sii_processing_failure", detail: payload.error, phase: "poll" }));
        return;
      }
      pollTimerRef.current = window.setTimeout(() => pollUploadStatus(pollingJobId), 2000);
    } catch (error) {
      const classified = classifyUploadError(error, "poll");
      if (classified.retryable && pollFailureCountRef.current < 30) {
        pollFailureCountRef.current += 1;
        setUploadState((current) => (isUploadProcessing(current) ? current : "running_sii"));
        setUploadError(classified.message);
        pollTimerRef.current = window.setTimeout(() => pollUploadStatus(pollingJobId), Math.min(2000 + pollFailureCountRef.current * 1500, 12000));
        return;
      }
      setUploadError(classified.finalMessage ?? classified.message);
      setUploadState(classified.retryable ? "error" : classified.state);
    }
  }

  async function handleUpload(event) {
    event.preventDefault();
    const validationError = validateTelemetryFile(selectedFile, pendingUploadKind);
    if (validationError) {
      setUploadError(validationError);
      setUploadState("validation_error");
      return;
    }
    setUploadState("uploading");
    setUploadError("");
    setUploadJob({ job_id: null, status: "uploading", progress_label: "Upload started.", message: "Uploading telemetry export.", file_size_bytes: selectedFile.size });
    setUploadTransfer({ loaded: 0, total: selectedFile.size, percent: 0, speedBytesPerSecond: 0, stage: "upload_started" });
    uploadJobIdRef.current = null;
    pollFailureCountRef.current = 0;
    try {
      const { ok, status, payload } = await uploadTelemetryFileWithProgress({
        file: selectedFile,
        timeoutMs: UPLOAD_REQUEST_TIMEOUT_MS,
        onProgress: (progress) => {
          setUploadTransfer(progress);
          setUploadJob((current) => ({
            ...(current ?? {}),
            status: progress.stage === "accepted" ? "pending" : "uploading",
            progress_label: progress.percent != null
              ? `Uploading telemetry export - ${progress.percent}% - ${formatTransferSpeed(progress.speedBytesPerSecond)}`
              : `Uploading telemetry export - ${formatTransferSpeed(progress.speedBytesPerSecond)}`,
            message: progress.message,
            file_size_bytes: progress.total || selectedFile.size,
            bytes_processed: progress.loaded,
          }));
        },
      });
      if (!ok) throw buildUploadRequestError({ status }, payload, "upload");
      if (!payload?.job_id) throw buildUploadRequestError({ status }, { ...payload, error_type: "upload_session_missing", message: "Upload state unavailable." }, "upload");
      uploadJobIdRef.current = payload.job_id;
      setUploadJob(payload);
      setUploadState(normalizeUploadStatus(payload.status));
      pollUploadStatus(payload.job_id);
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
      uploadInputRef.current.accept = kind === "json" ? ".json,application/json" : ".csv,text/csv";
      uploadInputRef.current.click();
    }
  }

  function handleFileSelection(event) {
    const nextFile = event.target.files?.[0] ?? null;
    const validationError = validateTelemetryFile(nextFile, pendingUploadKind);
    setSelectedFile(nextFile);
    setUploadError(validationError);
    setUploadState(validationError ? "validation_error" : nextFile ? "validated" : "idle");
    setUploadTransfer(null);
    if (nextFile && !validationError) {
      setUploadJob({
        job_id: null,
        status: "validated",
        progress_label: isLargeOperationalUpload(nextFile) ? "Large telemetry export detected." : "Telemetry export validated.",
        message: uploadReadinessMessage(nextFile),
        file_size_bytes: nextFile.size,
      });
    } else {
      setUploadJob(null);
    }
  }

  async function handleResetDemoClick() {
    setSelectedFile(null);
    setUploadState("idle");
    setUploadError("");
    setUploadResult(null);
    setUploadJob(null);
    setUploadTransfer(null);
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
  const uploadHistoryRows = uploadStateView.buildUploadHistoryRows(latestUploadSnapshot?.history ?? []);
  const uploadDiffSummary = uploadStateView.buildUploadDiffSummary(latestUploadSnapshot?.history ?? []);
  const latestMessage = normalizeErrorMessage(displayUploadError || uploadJob?.error || uploadJob?.message || uploadJob?.progress_label || latestUploadSnapshot?.message || uploadStateMessage(uploadState));
  const selectedFileSize = formatFileSize(selectedFile?.size ?? 0);
  const uploadTransferPercent = Number.isFinite(uploadTransfer?.percent) ? Math.min(100, Math.max(0, uploadTransfer.percent)) : null;
  const backendPercent = Number.isFinite(uploadJob?.percent ?? uploadJob?.progress) ? Math.min(100, Math.max(0, uploadJob.percent ?? uploadJob.progress)) : null;
  const visibleProgressPercent = normalizeUploadStatus(uploadState) === "uploading" ? uploadTransferPercent : backendPercent;
  const baselineStatus = latestUploadSnapshot?.baseline_status;
  const baselineMessage = baselineStatus === "building" ? "Baseline Pending" : baselineStatus === "active" ? "Baseline Active" : "Baseline Pending";
  const diagnosticsResult = uploadStateView.hasFullUploadResult(uploadResult) ? uploadResult : latestUploadResult;
  const hasDiagnosticsSession = hasActiveSession && hasRealSiiOutput && (hasCurrentUploadResult || hasResumedSession);

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

      {activeTab === "overview" && (
        <>
          <Panel title="Session Controls" className="span-12">
            <p className="narrative-text">
              Startup remains neutral until a new upload completes or a previous session is explicitly resumed.
            </p>
            <div className="intake-flow__controls">
              <button type="button" className="secondary-command-button" onClick={handleResetDemoClick} disabled={isUploadProcessing(uploadState)}>
                Reset Demo State
              </button>
              <button type="button" className="secondary-command-button" onClick={onResumePreviousSession} disabled={isUploadProcessing(uploadState)}>
                Resume Previous Session
              </button>
              <button type="button" className="command-button" onClick={() => setActiveTab("upload")}>
                Upload Data
              </button>
            </div>
          </Panel>
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

      {activeTab === "historian-setup" && (
        <>
          <Panel title="Session Controls" className="span-12">
            <div className="intake-flow__controls">
              <button type="button" className="secondary-command-button" onClick={handleResetDemoClick} disabled={isUploadProcessing(uploadState)}>
                Reset Demo State
              </button>
              <button type="button" className="secondary-command-button" onClick={onResumePreviousSession} disabled={isUploadProcessing(uploadState)}>
                Resume Previous Session
              </button>
            </div>
          </Panel>
          <HistorianSetupWorkspace tagMapRows={TAG_MAP_ROWS} />
        </>
      )}

      {activeTab === "upload" && (
        <IntakeFlowPanel
          handleUpload={handleUpload}
          uploadInputRef={uploadInputRef}
          handleFileSelection={handleFileSelection}
          selectedFile={selectedFile}
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
        />
      )}

      {activeTab === "diagnostics" && (
        <DiagnosticsPanel
          latestUploadResult={diagnosticsResult}
          latestUploadSnapshot={latestUploadSnapshot}
          hasActiveSession={hasDiagnosticsSession}
          hasCurrentUploadResult={hasCurrentUploadResult}
          hasResumedSession={hasResumedSession}
          hasRealSiiOutput={hasRealSiiOutput}
          apiFetch={apiFetch}
          accessCode={accessCode}
          uploadStateView={uploadStateView}
          uploadHistoryRows={uploadHistoryRows}
        />
      )}
    </div>
  );
}
