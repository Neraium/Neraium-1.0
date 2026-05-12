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
import { CompactList, DataTable, EmptyState, MetricGrid, Panel, WorkflowStages } from "./workspacePrimitives";

const LIVE_CONNECTION_REFRESH_MS = 5000;
const DEFAULT_CONNECTION_ID = "node-red-cultivation-telemetry";
const DEFAULT_CONNECTION_URL = "http://127.0.0.1:1880/telemetry/latest";
const JSON_UPLOAD_SCHEMA_EXAMPLE = `{
  "source_id": "pilot-json-001",
  "source_type": "external_rest_api",
  "facility_id": "cultivation-facility-001",
  "room_id": "flower-room-1",
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

function connectionTone(status) {
  const normalized = String(status ?? "").toLowerCase();
  if (normalized === "online") {
    return "nominal";
  }
  if (normalized === "polling") {
    return "review";
  }
  if (normalized === "error") {
    return "elevated";
  }
  return "info";
}

function formatConnectionStatus(status) {
  const normalized = String(status ?? "").toLowerCase();
  if (normalized === "online") {
    return "Online";
  }
  if (normalized === "polling") {
    return "Connected";
  }
  if (normalized === "error") {
    return "Error";
  }
  if (normalized === "offline") {
    return "Offline";
  }
  return "Not configured";
}

function formatBaselineStatus(status) {
  const normalized = String(status ?? "").toLowerCase();
  if (normalized === "building") {
    return "Building";
  }
  if (normalized === "active") {
    return "Active";
  }
  if (normalized === "failed") {
    return "Failed";
  }
  return "None";
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
  const TABS = ["overview", "upload", "connections", "diagnostics"];
  const [selectedFile, setSelectedFile] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [pendingUploadKind, setPendingUploadKind] = useState("csv");
  const [uploadState, setUploadState] = useState("idle");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(latestUploadResult);
  const [uploadJob, setUploadJob] = useState(null);
  const [connectionError, setConnectionError] = useState("");
  const [connections, setConnections] = useState([]);
  const [connectionBusy, setConnectionBusy] = useState("");
  const [isJsonSchemaOpen, setIsJsonSchemaOpen] = useState(false);
  const [copyState, setCopyState] = useState("idle");
  const [connectionForm, setConnectionForm] = useState({
    connection_id: DEFAULT_CONNECTION_ID,
    name: "Node-RED Cultivation Telemetry",
    url: DEFAULT_CONNECTION_URL,
    facility_id: "cultivation-facility-001",
    room_id: "flower-room-1",
    polling_interval_seconds: 5,
  });
  const uploadJobIdRef = useRef(null);
  const pollTimerRef = useRef(null);
  const pollFailureCountRef = useRef(0);
  const uploadInputRef = useRef(null);

  const loadConnections = useCallback(async () => {
    try {
      const response = await apiFetch("/api/data-connections", { accessCode });
      const payload = await readJsonPayload(response);
      if (!response.ok) {
        throw new Error(payload?.detail ?? `Unexpected response: ${response.status}`);
      }
      setConnections(payload?.connections ?? []);
      setConnectionError("");
    } catch (error) {
      console.error("data_connections_load_failed", { error: normalizeErrorMessage(error?.message ?? error) });
      setConnectionError(normalizeErrorMessage(error?.message ?? error));
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

  useEffect(() => {
    const activeConnection = connections.find((item) => item.connection_id === DEFAULT_CONNECTION_ID) ?? connections[0];
    if (!activeConnection) {
      return;
    }
    setConnectionForm({
      connection_id: activeConnection.connection_id,
      name: activeConnection.name,
      url: activeConnection.url,
      facility_id: activeConnection.facility_id ?? "",
      room_id: activeConnection.room_id ?? "",
      polling_interval_seconds: activeConnection.polling_interval_seconds ?? 5,
    });
  }, [connections]);

  useEffect(() => {
    loadConnections();
    const intervalId = window.setInterval(loadConnections, LIVE_CONNECTION_REFRESH_MS);
    return () => window.clearInterval(intervalId);
  }, [loadConnections]);

  async function handleUpload(event) {
    event.preventDefault();
    if (!selectedFile) {
      setUploadError("Choose a CSV or JSON telemetry file to upload.");
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);

    setUploadState("uploading");
    setUploadError("");
    setUploadJob(null);
    uploadJobIdRef.current = null;
    pollFailureCountRef.current = 0;

    try {
      const response = await apiFetch("/api/data/upload", {
        accessCode,
        method: "POST",
        body: formData,
      });
      const payload = await readJsonPayload(response);

      if (!response.ok) {
        throw buildUploadRequestError(response, payload, "upload");
      }

      if (!payload?.job_id) {
        throw buildUploadRequestError(response, { ...payload, error_type: "upload_session_missing", message: "Upload state unavailable." }, "upload");
      }

      uploadJobIdRef.current = payload.job_id;
      setUploadJob(payload);
      setUploadState(normalizeUploadStatus(payload.status));
      pollUploadStatus(payload.job_id);
    } catch (error) {
      const classified = classifyUploadError(error, "upload");
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
        const latestResponse = await apiFetch("/api/data/latest-upload", { accessCode });
        const latestPayload = latestResponse.ok ? await readJsonPayload(latestResponse) : payload.result_summary;
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
        await loadConnections();
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

  async function handleSaveConnection() {
    setConnectionBusy(`${connectionForm.connection_id}:save`);
    setConnectionError("");
    try {
      const response = await apiFetch("/api/data-connections", {
        accessCode,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...connectionForm,
          source_type: "external_rest_api",
          polling_enabled: Boolean(activeConnection?.polling_enabled),
          polling_interval_seconds: Number(connectionForm.polling_interval_seconds || 5),
        }),
      });
      const payload = await readJsonPayload(response);
      if (!response.ok) {
        throw new Error(payload?.detail ?? payload?.message ?? `Unexpected response: ${response.status}`);
      }
      await loadConnections();
    } catch (error) {
      setConnectionError(normalizeErrorMessage(error?.message ?? error));
    } finally {
      setConnectionBusy("");
    }
  }

  const activeConnection = connections.find((item) => item.connection_id === DEFAULT_CONNECTION_ID) ?? connections[0] ?? null;
  const healthyCount = connections.filter((item) => ["online", "polling"].includes(String(item.status).toLowerCase())).length;
  const totalSensors = connections.reduce((sum, item) => sum + (item.sensors_detected ?? 0), 0);
  const totalReadings = connections.reduce((sum, item) => sum + (item.readings_received ?? 0), 0);
  const hasSuccessfulLiveTelemetry = Boolean(
    activeConnection?.last_success_at
      && (activeConnection?.readings_accepted ?? 0) > 0
      && !activeConnection?.error_message,
  );
  const displayUploadError = hasSuccessfulLiveTelemetry && !isUploadProcessing(uploadState) ? "" : uploadError;
  const intakeStages = uploadJob
    ? buildIntakeStages(uploadResult, uploadState, roomContext, uploadJob)
    : uploadResult
      ? buildIntakeStages(uploadResult, uploadState, roomContext, null)
      : uploadStateView.buildConnectionStateStages({ latestUploadSnapshot, uploadState, uploadError: displayUploadError, roomContext });
  const latestStatus = latestUploadSnapshot?.status ?? "empty";
  const uploadHistoryRows = uploadStateView.buildUploadHistoryRows(latestUploadSnapshot?.history ?? []);
  const uploadDiffSummary = uploadStateView.buildUploadDiffSummary(latestUploadSnapshot?.history ?? []);
  const liveTelemetryMessage = activeConnection?.baseline_status === "active"
    ? "Live telemetry baseline ready"
    : activeConnection?.baseline_status === "building"
      ? `Building live baseline (${activeConnection?.baseline_samples_collected ?? 0}/${activeConnection?.baseline_samples_required ?? 0})`
      : "Live telemetry received";
  const latestMessage = normalizeErrorMessage(
    displayUploadError
      || uploadJob?.error
      || uploadJob?.message
      || uploadJob?.progress_label
      || (hasSuccessfulLiveTelemetry ? liveTelemetryMessage : "")
      || latestUploadSnapshot?.message
      || uploadStateMessage(uploadState),
  );

  const baselineStatusLabel = formatBaselineStatus(activeConnection?.baseline_status ?? latestUploadSnapshot?.baseline_status);
  const baselineSamplesCollected = activeConnection?.baseline_samples_collected ?? latestUploadSnapshot?.baseline_samples_collected ?? 0;
  const baselineSamplesRequired = activeConnection?.baseline_samples_required ?? latestUploadSnapshot?.baseline_samples_required ?? 0;
  const baselineSource = activeConnection?.baseline_source ?? latestUploadSnapshot?.baseline_source;
  const currentBaselineStatus = activeConnection?.baseline_status ?? latestUploadSnapshot?.baseline_status;
  const baselineMessage = currentBaselineStatus === "building"
    ? "Building live baseline"
    : currentBaselineStatus === "active"
      ? "Live baseline active"
      : currentBaselineStatus === "failed"
        ? "Live baseline failed"
        : "No data connected yet";

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
              {tab === "overview" ? "Overview" : tab === "upload" ? "Upload" : tab === "connections" ? "Connections" : "Diagnostics"}
            </button>
          ))}
        </div>
      </Panel>

      {activeTab === "upload" && (
      <Panel title="Upload Intake" className="span-7 workspace-hero-panel">
        <form className="intake-flow" onSubmit={handleUpload}>
          <div className="intake-flow__header">
            <h3>Upload Telemetry File</h3>
            <p>Upload a production CSV or JSON telemetry export if you want a file-based baseline. You can also keep a live REST endpoint connected here for reference.</p>
          </div>

          <div className="intake-flow__controls">
            <input
              ref={uploadInputRef}
              accept=".csv,text/csv"
              id="csv-upload"
              type="file"
              className="intake-flow__input"
              onChange={(event) => {
                setSelectedFile(event.target.files?.[0] ?? null);
                setUploadError("");
              }}
            />
            <button className="command-button" type="button" disabled={isUploadProcessing(uploadState)} onClick={() => openFilePicker("csv")}>
              Upload CSV Telemetry
            </button>
            <button className="secondary-command-button" type="button" disabled={isUploadProcessing(uploadState)} onClick={() => openFilePicker("json")}>
              Upload JSON Telemetry
            </button>
            <button className="secondary-command-button" type="submit" disabled={!selectedFile || isUploadProcessing(uploadState)}>
              {isUploadProcessing(uploadState) ? "Processing" : `Process ${pendingUploadKind.toUpperCase()} File`}
            </button>
          </div>

          <div className="intake-flow__status">
            <span>{selectedFile ? `${selectedFile.name} (${pendingUploadKind.toUpperCase()})` : (latestUploadSnapshot?.last_filename ?? "No data connected yet")}</span>
            <span className="intake-flow__progress">
              {isUploadProcessing(uploadState) && <span className="upload-spinner" aria-hidden="true" />}
              {latestMessage}
            </span>
          </div>

          {uploadError && <span className="sr-only">{normalizeErrorMessage(uploadError)}</span>}
          {displayUploadError && <p className="form-error">{normalizeErrorMessage(uploadError || displayUploadError)}</p>}
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
      <Panel title="Ingestion State" className="span-5">
        <WorkflowStages items={intakeStages} />
      </Panel>
      )}

      {activeTab === "overview" && (
      <>
      <Panel title="Latest Sync" className="span-7">
        <MetricGrid
          metrics={[
            { label: "State", value: uploadStateView.connectionStateLabel(latestStatus, uploadState, displayUploadError) },
            { label: "Backend", value: apiStatus.label },
            { label: "Latest Sync", value: latestUploadSnapshot?.last_processed_at ? formatClockTime(latestUploadSnapshot.last_processed_at) : "No data connected yet" },
            { label: "Source", value: latestUploadSnapshot?.result_source === "rest_poll" ? "REST Poll" : latestUploadSnapshot?.result_source ? "File Upload" : "Awaiting Data" },
            { label: "Baseline", value: baselineMessage },
            { label: "Connection", value: activeConnection?.name ?? "Awaiting source" },
            { label: "Primary Room", value: roomContext.primary },
            { label: "Scenario", value: activeConnection?.current_scenario ?? "Awaiting telemetry" },
            { label: "Tick", value: activeConnection?.current_tick ?? "n/a" },
          ]}
        />
      </Panel>

      <Panel title="Change Summary" className="span-5">
        <MetricGrid
          metrics={[
            { label: "Current Result", value: latestUploadSnapshot?.history?.[0]?.filename ?? activeConnection?.name ?? "No active result" },
            { label: "Previous Result", value: latestUploadSnapshot?.history?.[1]?.filename ?? "None" },
            { label: "Score Delta", value: latestUploadSnapshot?.history?.[0]?.diff?.neraium_score_delta ?? "n/a" },
            { label: "Result", value: latestUploadSnapshot?.history?.[0]?.operating_state ?? "Awaiting data" },
          ]}
          compact
        />
        <CompactList items={uploadDiffSummary.lines} emptyText="Waiting for a meaningful state change." />
      </Panel>
      </>
      )}

      {activeTab === "connections" && (
      <Panel title="Telemetry Stream" className="span-12">
        {activeConnection ? (
          <>
            <form className="connector-rest-grid" onSubmit={(event) => event.preventDefault()}>
              <label>
                <span>Name</span>
                <input
                  type="text"
                  value={connectionForm.name}
                  onChange={(event) => setConnectionForm((current) => ({ ...current, name: event.target.value }))}
                />
              </label>
              <label>
                <span>URL</span>
                <input
                  type="url"
                  value={connectionForm.url}
                  onChange={(event) => setConnectionForm((current) => ({ ...current, url: event.target.value }))}
                />
              </label>
              <label>
                <span>Facility ID</span>
                <input
                  type="text"
                  value={connectionForm.facility_id}
                  onChange={(event) => setConnectionForm((current) => ({ ...current, facility_id: event.target.value }))}
                />
              </label>
              <label>
                <span>Room ID</span>
                <input
                  type="text"
                  value={connectionForm.room_id}
                  onChange={(event) => setConnectionForm((current) => ({ ...current, room_id: event.target.value }))}
                />
              </label>
              <div className="connector-form__actions">
                <button
                  className="secondary-command-button"
                  type="button"
                  disabled={connectionBusy === `${connectionForm.connection_id}:save`}
                  onClick={handleSaveConnection}
                >
                  {connectionBusy === `${connectionForm.connection_id}:save` ? "Saving" : "Save Connection"}
                </button>
              </div>
            </form>
            <MetricGrid
              metrics={[
                { label: "URL", value: activeConnection.url },
                { label: "Status", value: formatConnectionStatus(activeConnection.status) },
                { label: "Endpoint Mode", value: "Configured" },
                { label: "Baseline Source", value: baselineSource === "live_rest" ? "Live REST" : baselineSource === "uploaded_file" ? "Uploaded File" : "None" },
                { label: "Baseline Status", value: baselineStatusLabel },
                { label: "Samples", value: baselineSamplesRequired > 0 ? `${baselineSamplesCollected}/${baselineSamplesRequired}` : baselineSamplesCollected },
                { label: "Last Poll", value: activeConnection.last_poll_at ? formatClockTime(activeConnection.last_poll_at) : "Not yet" },
                { label: "Last Success", value: activeConnection.last_success_at ? formatClockTime(activeConnection.last_success_at) : "Not yet" },
                { label: "Readings", value: activeConnection.readings_received ?? 0 },
                { label: "Sensors", value: activeConnection.sensors_detected ?? 0 },
                { label: "Scenario", value: activeConnection.current_scenario ?? "Awaiting telemetry" },
                { label: "Baseline Updated", value: activeConnection.last_baseline_update ? formatClockTime(activeConnection.last_baseline_update) : "Not yet" },
              ]}
            />
            <CompactList
              items={[
                `Room: ${activeConnection.room_id ?? "Unknown room"}`,
                `Facility: ${activeConnection.facility_id ?? "Unknown facility"}`,
                `Telemetry timestamp: ${activeConnection.latest_telemetry_timestamp ?? "Awaiting telemetry"}`,
                `Last ingestion source: ${activeConnection.last_ingestion_source ?? "Not yet ingested"}`,
                `Baseline status: ${baselineStatusLabel}`,
                baselineSamplesRequired > 0 ? `Baseline samples: ${baselineSamplesCollected}/${baselineSamplesRequired}` : `Baseline samples: ${baselineSamplesCollected}`,
                activeConnection.last_baseline_update ? `Last baseline update: ${activeConnection.last_baseline_update}` : "Last baseline update: Not yet",
                activeConnection.baseline_status === "failed" && activeConnection.baseline_error_message
                  ? `Baseline error: ${activeConnection.baseline_error_message}`
                  : null,
                String(activeConnection.status ?? "").toLowerCase() === "error" && activeConnection.error_message
                  ? `Error: ${activeConnection.error_message}`
                  : `Connection is ${formatConnectionStatus(activeConnection.status).toLowerCase()}.`,
              ].filter(Boolean)}
              emptyText="No live connection metadata yet."
            />
          </>
        ) : (
          <EmptyState title="No data connection registered" body="Register a REST telemetry source to keep the intake workspace ready for live data." compact />
        )}
      </Panel>
      )}

      {activeTab === "diagnostics" && (
      <Panel title="Advanced Diagnostics" className="span-12">
        <details className="technical-summary-panel">
          <summary>Show connection fleet, active result, and upload history</summary>

          <MetricGrid
            metrics={[
              { label: "Connections", value: connections.length || "Pending" },
              { label: "Online", value: healthyCount },
              { label: "Sensors", value: totalSensors || "Pending" },
              { label: "Readings", value: totalReadings || "Pending" },
            ]}
          />

          <div className="connector-status-list">
            {connections.map((connection) => (
              <div className="connector-status-card" key={connection.connection_id}>
                <div className="connector-status-card__header">
                  <div>
                    <p className="section-token">{connection.source_type}</p>
                    <h3>{connection.name}</h3>
                  </div>
                  <span className={`connector-status-pill connector-status-pill--${connectionTone(connection.status)}`}>
                    {formatConnectionStatus(connection.status)}
                  </span>
                </div>
                <MetricGrid
                  metrics={[
                    { label: "Last Poll", value: connection.last_poll_at ? formatClockTime(connection.last_poll_at) : "Not yet" },
                    { label: "Last Success", value: connection.last_success_at ? formatClockTime(connection.last_success_at) : "Not yet" },
                    { label: "Baseline", value: formatBaselineStatus(connection.baseline_status) },
                    { label: "Sensors", value: connection.sensors_detected ?? 0 },
                    { label: "Readings", value: connection.readings_received ?? 0 },
                  ]}
                  compact
                />
              </div>
            ))}
          </div>

          <MetricGrid
            metrics={[
              { label: "Score", value: latestUploadResult?.sii_intelligence?.neraium_score ?? "No active result" },
              { label: "State", value: latestUploadResult?.sii_intelligence?.facility_state ?? "No active result" },
              { label: "Drift", value: latestUploadResult?.sii_intelligence?.urgency ?? "No active result" },
              { label: "Timestamp", value: activeConnection?.latest_telemetry_timestamp ? formatClockTime(activeConnection.latest_telemetry_timestamp) : uploadStateView.deriveTimeCoverage(latestUploadResult).summary },
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
                  row.scoreDelta ?? "n/a",
                ])}
              />
            ) : (
              <EmptyState title="No ingestion history" body="Completed uploads and meaningful live telemetry changes will appear here." compact />
            )}
          </Panel>
        </details>
      </Panel>
      )}

      {connectionError && activeTab !== "overview" && (
        <Panel title="Connection Response" className="span-12">
          <p className="form-error">{connectionError}</p>
        </Panel>
      )}
    </div>
  );
}
