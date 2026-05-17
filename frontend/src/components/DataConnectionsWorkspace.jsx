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
const TAG_MAP_ROWS = [
  ["hvac_runtime", "HVAC Runtime", "Cultivation Rooms", "HVAC Unit 1", "minutes", "1 min", "Good"],
  ["temp_air", "Air Temperature", "Cultivation Rooms", "Room Sensor", "°F", "1 min", "Good"],
  ["rh_percent", "Relative Humidity", "Cultivation Rooms", "Room Sensor", "%RH", "1 min", "Good"],
  ["dehu_runtime", "Dehumidifier Runtime", "Cultivation Rooms", "Dehu Unit 1", "minutes", "1 min", "Good"],
];

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
  if (file.size > MAX_UPLOAD_BYTES) {
    return `High-volume export above ${formatFileSize(MAX_UPLOAD_BYTES)}. Use partitioned export or enterprise batch intake.`;
  }
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
  roomContext,
  onUploadComplete,
  onResetDemo,
  onResumePreviousSession,
  formatClockTime,
}) {
  const isMobile = typeof window !== "undefined" && window.innerWidth < 760;
  const tabs = useMemo(
    () => [
      { id: "overview", label: "Overview" },
      { id: "historian-setup", label: isMobile ? "Setup" : "Historian Setup" },
      { id: "upload", label: "Upload Data" },
      { id: "diagnostics", label: "Diagnostics" },
    ],
    [isMobile],
  );

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
              ? `Uploading telemetry export · ${progress.percent}% · ${formatTransferSpeed(progress.speedBytesPerSecond)}`
              : `Uploading telemetry export · ${formatTransferSpeed(progress.speedBytesPerSecond)}`,
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
  const latestStatus = latestUploadSnapshot?.status ?? "empty";
  const uploadHistoryRows = uploadStateView.buildUploadHistoryRows(latestUploadSnapshot?.history ?? []);
  const uploadDiffSummary = uploadStateView.buildUploadDiffSummary(latestUploadSnapshot?.history ?? []);
  const latestMessage = normalizeErrorMessage(
    displayUploadError || uploadJob?.error || uploadJob?.message || uploadJob?.progress_label || latestUploadSnapshot?.message || uploadStateMessage(uploadState),
  );
  const selectedFileSize = formatFileSize(selectedFile?.size ?? 0);
  const uploadTransferPercent = Number.isFinite(uploadTransfer?.percent) ? Math.min(100, Math.max(0, uploadTransfer.percent)) : null;
  const backendPercent = Number.isFinite(uploadJob?.percent ?? uploadJob?.progress) ? Math.min(100, Math.max(0, uploadJob.percent ?? uploadJob.progress)) : null;
  const visibleProgressPercent = normalizeUploadStatus(uploadState) === "uploading" ? uploadTransferPercent : backendPercent;
  const baselineStatus = latestUploadSnapshot?.baseline_status;
  const baselineMessage = baselineStatus === "building"
    ? "Baseline Pending"
    : baselineStatus === "active"
      ? "Baseline Active"
      : "Baseline Pending";

  return (
    <div className="workspace-grid workspace-grid--connections">
      <Panel title="Historian Intake" className="span-12 workspace-hero-panel">
        <div className="intake-flow__controls" role="tablist" aria-label="Historian intake sections">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={activeTab === tab.id ? "command-button" : "secondary-command-button"}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
          <button type="button" className="secondary-command-button" onClick={handleResetDemoClick} disabled={isUploadProcessing(uploadState)}>
            Reset Demo State
          </button>
          <button type="button" className="secondary-command-button" onClick={onResumePreviousSession} disabled={isUploadProcessing(uploadState)}>
            Resume Previous Session
          </button>
        </div>
      </Panel>

      {activeTab === "overview" && (
        <>
          <Panel title="Intake Status" className="span-7 uploaded-intelligence-panel">
            <MetricGrid
              metrics={[
                { label: "Active Session", value: uploadStateView.connectionStateLabel(latestStatus, uploadState, displayUploadError) },
                { label: "Control Plane", value: apiStatus.label },
                { label: "Analysis Active", value: latestUploadSnapshot?.last_processed_at ? formatClockTime(latestUploadSnapshot.last_processed_at) : "No Active Session" },
                { label: "Signal Origin", value: latestUploadSnapshot?.result_source ? "Telemetry import" : "Awaiting uploaded telemetry" },
                { label: "Baseline", value: baselineMessage },
                { label: "Primary Environment", value: roomContext.primary },
                { label: "Operational Mode", value: latestUploadSnapshot?.scenario ?? "Awaiting uploaded telemetry" },
                { label: "Session Tick", value: latestUploadSnapshot?.current_tick ?? "Pending activation" },
              ]}
            />
          </Panel>
          <Panel title="Recent Structural Analysis" className="span-5 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
            <MetricGrid
              metrics={[
                { label: "Active Model", value: latestUploadSnapshot?.history?.[0]?.filename ?? "Awaiting uploaded telemetry" },
                { label: "Baseline Reference", value: latestUploadSnapshot?.history?.[1]?.filename ?? "Awaiting uploaded telemetry" },
                { label: "Score Movement", value: latestUploadSnapshot?.history?.[0]?.diff?.neraium_score_delta ?? "No Active Session" },
                { label: "Structural Read", value: latestUploadSnapshot?.history?.[0]?.operating_state ?? "No Active Session" },
              ]}
              compact
            />
            <CompactList items={uploadDiffSummary.lines} emptyText="Awaiting meaningful structural change." />
          </Panel>
        </>
      )}

      {activeTab === "historian-setup" && (
        <>
          <Panel title="Historian Intake Architecture" className="span-12 workspace-hero-panel">
            <DataTable
              columns={["Pipeline Stage"]}
              rows={[
                ["Historian / BMS / SCADA"],
                ["read-only ingestion"],
                ["Neraium Intake Connector"],
                ["Tag Mapper + Normalizer"],
                ["Baseline Builder"],
                ["Live Structural Analysis"],
                ["Operator UI / Reports"],
              ]}
            />
          </Panel>
          <Panel title="Connection Mode" className="span-6">
            <MetricGrid
              metrics={[
                { label: "CSV Export Pilot", value: "Pilot Ready · Read-only ingest only" },
                { label: "Read-only Historian API", value: "Available · No control path" },
                { label: "Scheduled Pull", value: "Available · Pull-only ingestion window" },
                { label: "Live Stream / MQTT", value: "Future · Read-only subscription model" },
              ]}
            />
          </Panel>
          <Panel title="Historian Source" className="span-6">
            <MetricGrid
              metrics={[
                { label: "Source Type", value: "AVEVA / OSIsoft PI, Ignition, Niagara/BACnet, SQL historian, InfluxDB/TimescaleDB, CSV/S3/Blob" },
                { label: "Host / Endpoint", value: "Configured per pilot environment" },
                { label: "Authentication", value: "Token / basic / service account (read-only scope)" },
                { label: "Polling Interval", value: "1 to 15 minutes" },
                { label: "Timezone", value: "Facility local timezone" },
                { label: "Retention Window", value: "30 to 90 day baseline capture" },
              ]}
            />
          </Panel>
          <Panel title="Tag Mapping" className="span-12">
            <DataTable
              columns={["Raw Tag", "Normalized Name", "Subsystem", "Equipment", "Unit", "Sample Rate", "Quality"]}
              rows={TAG_MAP_ROWS}
            />
          </Panel>
          <Panel title="Baseline Window" className="span-8">
            <MetricGrid
              metrics={[
                { label: "Historical Baseline", value: "30 to 90 days recommended" },
                { label: "Recent Comparison", value: "15 minutes to 24 hours" },
                { label: "Context: Alarms", value: "Optional input channel" },
                { label: "Context: Maintenance Logs", value: "Optional input channel" },
                { label: "Context: Setpoint Changes", value: "Optional input channel" },
                { label: "Context: Weather + Load", value: "Optional input channel" },
              ]}
            />
          </Panel>
          <Panel title="Read-only Safety Statement" className="span-4">
            <p>
              Neraium connects read-only. It does not write to the historian, change setpoints, issue commands, or control equipment.
            </p>
          </Panel>
        </>
      )}

      {activeTab === "upload" && (
        <>
          <Panel title="Upload Data" className="span-7 workspace-hero-panel upload-ops-panel">
            <form className="intake-flow intake-flow--ops" onSubmit={handleUpload}>
              <div className="intake-flow__header">
                <div>
                  <p className="section-token">Historian Pilot Intake</p>
                  <h3>Acquire → Normalize → Baseline → Analyze</h3>
                </div>
                <p>Upload a historian export for read-only pilot intake and structural analysis.</p>
              </div>

              <input ref={uploadInputRef} accept=".csv,text/csv" id="csv-upload" type="file" className="intake-flow__input" onChange={handleFileSelection} />

              <div className="upload-file-card">
                <div className="upload-file-card__main">
                  <span className="upload-file-card__label">Telemetry source</span>
                  <strong>{selectedFile ? selectedFile.name : latestUploadSnapshot?.last_filename ?? "No file selected"}</strong>
                  <p>{selectedFile ? `${pendingUploadKind.toUpperCase()} file · ${selectedFileSize}` : "Choose CSV or JSON telemetry export."}</p>
                  <p>{uploadReadinessMessage(selectedFile)}</p>
                </div>
                <div className="upload-file-card__actions">
                  <button className="secondary-command-button" type="button" disabled={isUploadProcessing(uploadState)} onClick={() => openFilePicker("csv")}>Select CSV</button>
                  <button className="secondary-command-button" type="button" disabled={isUploadProcessing(uploadState)} onClick={() => openFilePicker("json")}>Select JSON</button>
                  <button className="command-button" type="submit" disabled={!selectedFile || isUploadProcessing(uploadState)}>
                    {isUploadProcessing(uploadState) ? "Processing" : `Process ${pendingUploadKind.toUpperCase()}`}
                  </button>
                </div>
              </div>

              <div className={`intake-flow__status intake-flow__status--${uploadError ? "error" : isUploadProcessing(uploadState) ? "active" : uploadResult ? "complete" : "idle"}`}>
                <span className="intake-flow__progress">{isUploadProcessing(uploadState) && <span className="upload-spinner" aria-hidden="true" />}{uploadJob?.progress_label || latestMessage}</span>
                <span>{uploadJob?.job_id ? `Job ${uploadJob.job_id}` : uploadStateMessage(uploadState)}</span>
                {visibleProgressPercent !== null && (
                  <div className="upload-progress-meter" aria-label="Telemetry intake progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow={visibleProgressPercent} role="progressbar">
                    <span style={{ width: `${visibleProgressPercent}%` }} />
                  </div>
                )}
                {uploadTransfer && <span>{`${formatFileSize(uploadTransfer.loaded)} of ${formatFileSize(uploadTransfer.total)} at ${formatTransferSpeed(uploadTransfer.speedBytesPerSecond)}.`}</span>}
              </div>
            </form>
            <div className="connector-json-hint">
              <div className="connector-json-hint__header">
                <p className="section-token">JSON upload schema</p>
                <div className="connector-json-hint__actions">
                  <button className="secondary-command-button" type="button" onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(JSON_UPLOAD_SCHEMA_EXAMPLE);
                      setCopyState("copied");
                    } catch {
                      setCopyState("error");
                    }
                  }}>
                    {copyState === "copied" ? "Copied" : copyState === "error" ? "Copy failed" : "Copy Example"}
                  </button>
                  <button className="secondary-command-button" type="button" onClick={() => setIsJsonSchemaOpen((current) => !current)}>
                    {isJsonSchemaOpen ? "Hide Schema" : "Show Schema"}
                  </button>
                </div>
              </div>
              {isJsonSchemaOpen && <pre className="connector-json-hint__code">{JSON_UPLOAD_SCHEMA_EXAMPLE}</pre>}
            </div>
          </Panel>
          <Panel title="Model Construction State" className="span-5 upload-cognition-state">
            <WorkflowStages items={intakeStages} />
          </Panel>
        </>
      )}

      {activeTab === "diagnostics" && (
        <Panel title="Diagnostics" className="span-12">
          <details className="technical-summary-panel">
            <summary>Show active result and upload history</summary>
            <MetricGrid
              metrics={[
                { label: "Score", value: latestUploadResult?.sii_intelligence?.neraium_score ?? "No Active Session" },
                { label: "State", value: latestUploadResult?.sii_intelligence?.facility_state ?? "No Active Session" },
                { label: "Drift", value: latestUploadResult?.sii_intelligence?.urgency ?? "No Active Session" },
                { label: "Timestamp", value: uploadStateView.deriveTimeCoverage(latestUploadResult).summary },
              ]}
              compact
            />
            <Panel title="Upload History" className="span-12">
              {uploadHistoryRows.length > 0 ? (
                <DataTable
                  columns={["Result", "Status", "Score", "State", "Room", "Delta"]}
                  rows={uploadHistoryRows.map((row) => [row.filename, row.status, row.score, row.state, row.room, row.scoreDelta ?? "Pending"])}
                />
              ) : (
                <EmptyState title="No ingestion history" body="Completed uploads and structural analysis sessions will appear here." compact />
              )}
            </Panel>
          </details>
        </Panel>
      )}
    </div>
  );
}
