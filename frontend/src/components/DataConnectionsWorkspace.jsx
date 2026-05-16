import { useCallback, useEffect, useRef, useState } from "react";
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
import { CompactList, DataTable, EmptyState, MetricGrid, Panel, WorkflowStages } from "./workspacePrimitives";

const JSON_UPLOAD_SCHEMA_EXAMPLE = `{
  "source_id": "pilot-json-001",
  "source_type": "uploaded_dataset",
  "facility_id": "pilot-facility-001",
  "room_id": "room-1",
  "scenario": "airflow_drift",
  "tick": 10,
  "timestamp": "2026-05-01T08:00:00Z",
  "readings": [
    {
      "timestamp": "2026-05-01T08:00:00Z",
      "sensor_id": "temp-001",
      "sensor_name": "temperature",
      "value": 75.2,
      "unit": "F",
      "quality": "good"
    }
  ]
}`;

const MAX_UPLOAD_BYTES = 250 * 1024 * 1024;
const LARGE_OPERATIONAL_UPLOAD_BYTES = 100 * 1024 * 1024;
const UPLOAD_REQUEST_TIMEOUT_MS = 10 * 60 * 1000;

function formatTransferSpeed(bytesPerSecond) {
  if (!Number.isFinite(bytesPerSecond) || bytesPerSecond <= 0) {
    return "measuring speed";
  }
  if (bytesPerSecond >= 1024 * 1024) {
    return `${(bytesPerSecond / (1024 * 1024)).toFixed(1)} MB/s`;
  }
  return `${Math.max(bytesPerSecond / 1024, 1).toFixed(1)} KB/s`;
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "Awaiting file";
  }
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${Math.max(bytes / 1024, 1).toFixed(1)} KB`;
}

function isLargeOperationalUpload(file) {
  return (file?.size ?? 0) >= LARGE_OPERATIONAL_UPLOAD_BYTES;
}

function uploadReadinessMessage(file) {
  if (!file) {
    return "Choose an operational telemetry export to begin intelligence construction.";
  }
  if (isLargeOperationalUpload(file)) {
    return "Large operational telemetry detected. The export will be transferred securely, queued for background intake, and processed through schema detection, baseline modeling, SII analysis, and evidence writing.";
  }
  return "Telemetry export ready for secure intake and background processing.";
}

function validateTelemetryFile(file, kind) {
  if (!file) {
    return "Choose a CSV or JSON telemetry file to upload.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `High-volume export identified above the configured ${formatFileSize(MAX_UPLOAD_BYTES)} operational intake target. Use a partitioned export or route through the enterprise batch intake path.`;
  }

  const filename = String(file.name ?? "").toLowerCase();
  const mime = String(file.type ?? "").toLowerCase();
  const looksJson = filename.endsWith(".json") || mime.includes("json");
  const looksCsv = filename.endsWith(".csv") || mime.includes("csv") || mime === "text/plain" || mime === "";

  if (kind === "json" && !looksJson) {
    return "Selected file does not look like JSON telemetry. Choose a .json export or switch to CSV.";
  }
  if (kind === "csv" && !looksCsv) {
    return "Selected file does not look like CSV telemetry. Choose a .csv export or switch to JSON.";
  }
  return "";
}

export default function DataConnectionsWorkspace({
  accessCode,
  apiFetch,
  apiStatus,
  latestUploadSnapshot,
  latestUploadResult,
  roomContext,
  onUploadComplete,
  formatClockTime,
}) {
  const TABS = ["overview", "upload", "diagnostics"];
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
      const response = await apiFetch("/api/data/latest-upload", { accessCode });
      const payload = await readJsonPayload(response);
      if (!response.ok) {
        return null;
      }
      return payload;
    } catch (error) {
      console.error("latest_upload_refresh_failed", { error: normalizeErrorMessage(error?.message ?? error) });
      return null;
    }
  }, [accessCode, apiFetch]);

  useEffect(() => () => {
    if (pollTimerRef.current) {
      window.clearTimeout(pollTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (copyState !== "copied") {
      return undefined;
    }
    const timerId = window.setTimeout(() => setCopyState("idle"), 1600);
    return () => window.clearTimeout(timerId);
  }, [copyState]);

  useEffect(() => {
    setUploadResult(latestUploadResult);
  }, [latestUploadResult]);

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
    setUploadJob({
      job_id: null,
      status: "uploading",
      progress_label: "Upload started.",
      message: "Uploading telemetry export.",
      file_size_bytes: selectedFile.size,
    });
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
              ? `Uploading telemetry export · ${progress.percent}% · ${formatTransferSpeed(progress.speedBytesPerSecond)}`
              : `Uploading telemetry export · ${formatTransferSpeed(progress.speedBytesPerSecond)}`,
            message: progress.message,
            file_size_bytes: progress.total || selectedFile.size,
            bytes_processed: progress.loaded,
          }));
        },
      });

      if (!ok) {
        throw buildUploadRequestError({ status }, payload, "upload");
      }

      if (!payload?.job_id) {
        throw buildUploadRequestError({ status }, { ...payload, error_type: "upload_session_missing", message: "Upload state unavailable." }, "upload");
      }

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
        progress_label: isLargeOperationalUpload(nextFile)
          ? "Large operational telemetry detected. Preparing telemetry intake."
          : "Telemetry export validated. Ready for intake.",
        message: uploadReadinessMessage(nextFile),
        file_size_bytes: nextFile.size,
      });
    } else {
      setUploadJob(null);
    }
  }

  function handleRetryUpload() {
    if (uploadJobIdRef.current && isUploadProcessing(uploadState)) {
      pollUploadStatus(uploadJobIdRef.current);
      return;
    }
    if (uploadInputRef.current && selectedFile) {
      setUploadError("");
      setUploadState("validated");
    } else {
      openFilePicker(pendingUploadKind);
    }
  }

  async function handleCopyJsonSchema() {
    try {
      await navigator.clipboard.writeText(JSON_UPLOAD_SCHEMA_EXAMPLE);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  }

  async function pollUploadStatus(jobId) {
    const pollingJobId = jobId || uploadJobIdRef.current;
    if (!pollingJobId) {
      setUploadError("Upload state unavailable.");
      setUploadState("error");
      return;
    }

    try {
      const response = await apiFetch(`/api/data/upload-status/${pollingJobId}`, { accessCode });
      const payload = await readJsonPayload(response);

      if (!response.ok) {
        throw buildUploadRequestError(response, payload, "poll");
      }

      pollFailureCountRef.current = 0;
      uploadJobIdRef.current = payload.job_id ?? pollingJobId;
      setUploadJob(payload);
      const nextStatus = normalizeUploadStatus(payload.status);
      setUploadState(nextStatus);
      if (isUploadProcessing(nextStatus)) {
        setUploadError("");
      }

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
        setUploadError(operatorUploadMessage({
          status: response.status,
          errorType: payload.error_type ?? "sii_processing_failure",
          detail: payload.error,
          phase: "poll",
        }));
        return;
      }

      pollTimerRef.current = window.setTimeout(() => pollUploadStatus(pollingJobId), 2000);
    } catch (error) {
      const classified = classifyUploadError(error, "poll");
      if (classified.retryable && pollFailureCountRef.current < 30) {
        pollFailureCountRef.current += 1;
        setUploadState((current) => isUploadProcessing(current) ? current : "running_sii");
        setUploadError(classified.message);
        pollTimerRef.current = window.setTimeout(
          () => pollUploadStatus(pollingJobId),
          Math.min(2000 + pollFailureCountRef.current * 1500, 12000),
        );
        return;
      }
      setUploadError(classified.finalMessage ?? classified.message);
      setUploadState(classified.retryable ? "error" : classified.state);
    }
  }

  const displayUploadError = uploadError;
  const intakeStages = uploadJob
    ? buildIntakeStages(uploadResult, uploadState, roomContext, uploadJob)
    : uploadResult
      ? buildIntakeStages(uploadResult, uploadState, roomContext, null)
      : uploadStateView.buildConnectionStateStages({ latestUploadSnapshot, uploadState, uploadError: displayUploadError, roomContext });
  const latestStatus = latestUploadSnapshot?.status ?? "empty";
  const uploadHistoryRows = uploadStateView.buildUploadHistoryRows(latestUploadSnapshot?.history ?? []);
  const uploadDiffSummary = uploadStateView.buildUploadDiffSummary(latestUploadSnapshot?.history ?? []);
  const latestMessage = normalizeErrorMessage(
    displayUploadError
      || uploadJob?.error
      || uploadJob?.message
      || uploadJob?.progress_label
      || latestUploadSnapshot?.message
      || uploadStateMessage(uploadState),
  );
  const selectedFileSize = formatFileSize(selectedFile?.size ?? 0);
  const selectedFileIsLarge = isLargeOperationalUpload(selectedFile);
  const uploadGuidance = uploadReadinessMessage(selectedFile);
  const intakeStateEstimate = selectedFileIsLarge
    ? "Estimated intake state: high-volume export will remain in background processing while the workspace polls for status."
    : selectedFile
      ? "Estimated intake state: standard telemetry export will queue for background processing after transfer."
      : "Estimated intake state appears after file selection.";
  const uploadTransferPercent = Number.isFinite(uploadTransfer?.percent) ? Math.min(100, Math.max(0, uploadTransfer.percent)) : null;
  const backendPercent = Number.isFinite(uploadJob?.percent ?? uploadJob?.progress) ? Math.min(100, Math.max(0, uploadJob.percent ?? uploadJob.progress)) : null;
  const visibleProgressPercent = normalizeUploadStatus(uploadState) === "uploading" ? uploadTransferPercent : backendPercent;
  const uploadProgressLabel = uploadJob?.progress_label || (isUploadProcessing(uploadState) ? "Preparing telemetry intake" : latestMessage);
  const uploadPhaseState = (phase) => {
    if (phase === "select") {
      return selectedFile || uploadResult ? "complete" : "active";
    }
    if (phase === "validate") {
      if (uploadError) return "error";
      return selectedFile || uploadResult ? "complete" : "pending";
    }
    if (phase === "process") {
      if (uploadError && !isUploadProcessing(uploadState)) return "error";
      if (isUploadProcessing(uploadState)) return "active";
      return uploadResult ? "complete" : "pending";
    }
    if (uploadError && !isUploadProcessing(uploadState)) return "error";
    return uploadResult ? "complete" : isUploadProcessing(uploadState) ? "active" : "pending";
  };
  const uploadFlowSteps = [
    { key: "select", label: "Acquire Telemetry", value: selectedFile ? selectedFile.name : latestUploadSnapshot?.last_filename || "Operational source" },
    { key: "validate", label: "Resolve Signal Schema", value: selectedFile ? selectedFileSize : "sensor matrix" },
    { key: "process", label: "Construct Intelligence Model", value: isUploadProcessing(uploadState) ? "baseline + replay generation" : uploadJob?.status || "Ready" },
    { key: "status", label: "Activate Cognition", value: uploadError ? "Operator attention" : uploadResult ? "Active" : "Standby" },
  ];
  const baselineStatus = latestUploadSnapshot?.baseline_status;
  const baselineMessage = baselineStatus === "building"
    ? "Building uploaded baseline"
    : baselineStatus === "active"
      ? "Uploaded baseline active"
      : baselineStatus === "failed"
        ? "Uploaded baseline failed"
        : "Awaiting uploaded telemetry";

  return (
    <div className="workspace-grid workspace-grid--connections">
      <Panel title="Data Connections" className="span-12 workspace-hero-panel">
        <div className="intake-flow__controls" role="tablist" aria-label="Data connections sections">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={activeTab === tab}
              className={activeTab === tab ? "command-button" : "secondary-command-button"}
              onClick={() => setActiveTab(tab)}
            >
              {tab === "overview" ? "Overview" : tab === "upload" ? "Upload" : "Diagnostics"}
            </button>
          ))}
        </div>
      </Panel>

      {activeTab === "upload" && (
      <Panel title="Upload Intake" className="span-7 workspace-hero-panel upload-ops-panel">
        <form className="intake-flow intake-flow--ops" onSubmit={handleUpload}>
          <div className="intake-flow__header">
            <div>
              <p className="section-token">Telemetry Intelligence Constructor</p>
              <h3>Acquire → Resolve → Model → Activate</h3>
            </div>
            <p>Neraium constructs a structural intelligence model from telemetry: schema resolution, relational baseline computation, replay generation, and active cognition handoff.</p>
          </div>

          <ol className="upload-flow-rail" aria-label="Upload progress">
            {uploadFlowSteps.map((step, index) => (
              <li className={`upload-flow-rail__step upload-flow-rail__step--${uploadPhaseState(step.key)}`} key={step.key}>
                <span className="upload-flow-rail__index">{index + 1}</span>
                <span className="upload-flow-rail__copy">
                  <strong>{step.label}</strong>
                  <span>{step.value}</span>
                </span>
              </li>
            ))}
          </ol>

          <input
            ref={uploadInputRef}
            accept=".csv,text/csv"
            id="csv-upload"
            type="file"
            className="intake-flow__input"
            onChange={handleFileSelection}
          />

          <div className="upload-file-card">
            <div className="upload-file-card__main">
              <span className="upload-file-card__label">Telemetry source</span>
              <strong>{selectedFile ? selectedFile.name : latestUploadSnapshot?.last_filename ?? "No file selected"}</strong>
              <p>{selectedFile ? `${pendingUploadKind.toUpperCase()} file · ${selectedFileSize}` : "Choose an operational telemetry export to begin intelligence construction."}</p>
              <p>{uploadGuidance}</p>
            </div>
            <div className="upload-file-card__actions">
              <button className="secondary-command-button" type="button" disabled={isUploadProcessing(uploadState)} onClick={() => openFilePicker("csv")}>
                Select CSV
              </button>
              <button className="secondary-command-button" type="button" disabled={isUploadProcessing(uploadState)} onClick={() => openFilePicker("json")}>
                Select JSON
              </button>
              <button className="command-button" type="submit" disabled={!selectedFile || isUploadProcessing(uploadState)}>
                {isUploadProcessing(uploadState) ? "Processing" : `Process ${pendingUploadKind.toUpperCase()}`}
              </button>
            </div>
          </div>

          <div className={`intake-flow__status intake-flow__status--${uploadError ? "error" : isUploadProcessing(uploadState) ? "active" : uploadResult ? "complete" : "idle"}`}>
            <span className="intake-flow__progress">
              {isUploadProcessing(uploadState) && <span className="upload-spinner" aria-hidden="true" />}
              {uploadProgressLabel}
            </span>
            <span>{uploadJob?.job_id ? `Job ${uploadJob.job_id}` : uploadStateMessage(uploadState)}</span>
            {visibleProgressPercent !== null && (
              <div className="upload-progress-meter" aria-label="Telemetry intake progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow={visibleProgressPercent} role="progressbar">
                <span style={{ width: `${visibleProgressPercent}%` }} />
              </div>
            )}
          </div>

          <div className="intake-flow__guidance" role="status" aria-live="polite">
            <strong>{selectedFileIsLarge ? "High-volume telemetry field identified" : "Intelligence construction guidance"}</strong>
            <span>{intakeStateEstimate}</span>
            <span>Progress tracks transfer, schema resolution, baseline modeling, structural scoring, replay frame generation, and active cognition handoff.</span>
            {uploadTransfer && <span>{`${formatFileSize(uploadTransfer.loaded)} of ${formatFileSize(uploadTransfer.total)} transferred at ${formatTransferSpeed(uploadTransfer.speedBytesPerSecond)}.`}</span>}
          </div>

          {uploadError && <span className="sr-only">{normalizeErrorMessage(uploadError)}</span>}
          {displayUploadError && (
            <div className="form-error form-error--professional" role="status" aria-live="polite">
              <strong>Upload requires attention</strong>
              <span>{normalizeErrorMessage(uploadError || displayUploadError)}</span>
              <button className="secondary-command-button" type="button" onClick={handleRetryUpload}>
                Retry intake
              </button>
            </div>
          )}
        </form>
        <div className="connector-json-hint">
          <div className="connector-json-hint__header">
            <p className="section-token">JSON upload schema</p>
            <div className="connector-json-hint__actions">
              <button className="secondary-command-button" type="button" onClick={handleCopyJsonSchema}>
                {copyState === "copied" ? "Copied" : copyState === "error" ? "Copy failed" : "Copy Example"}
              </button>
              <button className="secondary-command-button" type="button" onClick={() => setIsJsonSchemaOpen((current) => !current)}>
                {isJsonSchemaOpen ? "Hide Schema" : "Show Schema"}
              </button>
            </div>
          </div>
          {isJsonSchemaOpen && (
            <pre className="connector-json-hint__code">{JSON_UPLOAD_SCHEMA_EXAMPLE}</pre>
          )}
        </div>
      </Panel>
      )}

      {activeTab === "upload" && (
      <Panel title="Model Construction State" className="span-5 upload-cognition-state">
        <WorkflowStages items={intakeStages} />
      </Panel>
      )}

      {activeTab === "overview" && (
      <>
      <Panel title="Active Structural Intelligence" className="span-7 uploaded-intelligence-panel">
        <MetricGrid
          metrics={[
            { label: "Cognition State", value: uploadStateView.connectionStateLabel(latestStatus, uploadState, displayUploadError) },
            { label: "Control Plane", value: apiStatus.label },
            { label: "Model Updated", value: latestUploadSnapshot?.last_processed_at ? formatClockTime(latestUploadSnapshot.last_processed_at) : "Awaiting first intelligence model" },
            { label: "Signal Origin", value: latestUploadSnapshot?.result_source ? "Operational telemetry import" : "Awaiting uploaded telemetry" },
            { label: "Relational Baseline", value: baselineMessage },
            { label: "Primary Environment", value: roomContext.primary },
            { label: "Operating Scenario", value: latestUploadSnapshot?.scenario ?? "Awaiting uploaded telemetry" },
            { label: "Temporal Index", value: latestUploadSnapshot?.current_tick ?? "Tracking on activation" },
          ]}
        />
      </Panel>

      <Panel title="Structural Delta" className="span-5 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
        <MetricGrid
          metrics={[
            { label: "Active Model", value: latestUploadSnapshot?.history?.[0]?.filename ?? "Model pending" },
            { label: "Baseline Reference", value: latestUploadSnapshot?.history?.[1]?.filename ?? "First baseline forming" },
            { label: "Score Movement", value: latestUploadSnapshot?.history?.[0]?.diff?.neraium_score_delta ?? "Awaiting second frame" },
            { label: "Structural Read", value: latestUploadSnapshot?.history?.[0]?.operating_state ?? "Evidence will populate after processing" },
          ]}
          compact
        />
        <CompactList items={uploadDiffSummary.lines} emptyText="Waiting for a meaningful state change." />
      </Panel>
      </>
      )}

      {activeTab === "diagnostics" && (
      <Panel title="Advanced Diagnostics" className="span-12">
        <details className="technical-summary-panel">
          <summary>Show active result and upload history</summary>

          <MetricGrid
            metrics={[
              { label: "Score", value: latestUploadResult?.sii_intelligence?.neraium_score ?? "No active result" },
              { label: "State", value: latestUploadResult?.sii_intelligence?.facility_state ?? "No active result" },
              { label: "Drift", value: latestUploadResult?.sii_intelligence?.urgency ?? "No active result" },
              { label: "Timestamp", value: uploadStateView.deriveTimeCoverage(latestUploadResult).summary },
            ]}
            compact
          />

          <Panel title="Upload History" className="span-12">
            {uploadHistoryRows.length > 0 ? (
              <DataTable
                columns={["Result", "Status", "Score", "State", "Room", "Delta"]}
                rows={uploadHistoryRows.map((row) => [
                  row.filename,
                  row.status,
                  row.score,
                  row.state,
                  row.room,
                  row.scoreDelta ?? "Pending",
                ])}
              />
            ) : (
              <EmptyState title="No ingestion history" body="Completed uploads and meaningful uploaded telemetry changes will appear here." compact />
            )}
          </Panel>
        </details>
      </Panel>
      )}
    </div>
  );
}
