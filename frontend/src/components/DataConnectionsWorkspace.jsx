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
    return "Polling";
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
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadState, setUploadState] = useState("idle");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(latestUploadResult);
  const [uploadJob, setUploadJob] = useState(null);
  const [connectionError, setConnectionError] = useState("");
  const [connections, setConnections] = useState([]);
  const [connectionBusy, setConnectionBusy] = useState("");
  const [connectionForm, setConnectionForm] = useState({
    connection_id: DEFAULT_CONNECTION_ID,
    name: "Node-RED Cultivation Telemetry",
    url: "http://18.216.253.180:1880/telemetry/latest",
    facility_id: "cultivation-facility-001",
    room_id: "flower-room-1",
    polling_interval_seconds: 5,
  });
  const uploadJobIdRef = useRef(null);
  const pollTimerRef = useRef(null);
  const pollFailureCountRef = useRef(0);

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
      setConnectionError(normalizeErrorMessage(error?.message ?? error));
    }
  }, [accessCode, apiFetch]);

  useEffect(() => () => {
    if (pollTimerRef.current) {
      window.clearTimeout(pollTimerRef.current);
    }
  }, []);

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
      setUploadError("Choose a CSV telemetry file to upload.");
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

  async function handleConnectionAction(connectionId, action) {
    setConnectionBusy(`${connectionId}:${action}`);
    setConnectionError("");
    try {
      const response = await apiFetch(`/api/data-connections/${connectionId}/${action}`, {
        accessCode,
        method: "POST",
      });
      const payload = await readJsonPayload(response);
      if (!response.ok) {
        throw new Error(payload?.detail ?? payload?.message ?? `Unexpected response: ${response.status}`);
      }
      await loadConnections();
      if (action === "poll-once" || action === "reset-baseline" || payload?.latest_result) {
        await onUploadComplete(payload?.latest_result ?? null);
      }
    } catch (error) {
      setConnectionError(normalizeErrorMessage(error?.message ?? error));
    } finally {
      setConnectionBusy("");
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
  const intakeStages = uploadJob
    ? buildIntakeStages(uploadResult, uploadState, roomContext, uploadJob)
    : uploadResult
      ? buildIntakeStages(uploadResult, uploadState, roomContext, null)
      : uploadStateView.buildConnectionStateStages({ latestUploadSnapshot, uploadState, uploadError, roomContext });
  const latestStatus = latestUploadSnapshot?.status ?? "empty";
  const uploadHistoryRows = uploadStateView.buildUploadHistoryRows(latestUploadSnapshot?.history ?? []);
  const uploadDiffSummary = uploadStateView.buildUploadDiffSummary(latestUploadSnapshot?.history ?? []);
  const latestMessage = normalizeErrorMessage(
    uploadError
      || uploadJob?.error
      || uploadJob?.message
      || uploadJob?.progress_label
      || latestUploadSnapshot?.message
      || uploadStateMessage(uploadState),
  );

  const baselineStatusLabel = formatBaselineStatus(activeConnection?.baseline_status ?? latestUploadSnapshot?.baseline_status);
  const baselineSamplesCollected = activeConnection?.baseline_samples_collected ?? latestUploadSnapshot?.baseline_samples_collected ?? 0;
  const baselineSamplesRequired = activeConnection?.baseline_samples_required ?? latestUploadSnapshot?.baseline_samples_required ?? 0;
  const baselineSource = activeConnection?.baseline_source ?? latestUploadSnapshot?.baseline_source;
  const baselineMessage = latestUploadSnapshot?.baseline_status === "building"
    ? "Building live baseline"
    : latestUploadSnapshot?.baseline_status === "active"
      ? "Live baseline active"
      : latestUploadSnapshot?.baseline_status === "failed"
        ? "Live baseline failed"
        : "No data connected yet";

  return (
    <div className="workspace-grid workspace-grid--connections">
      <Panel title="Data Connections" className="span-7">
        <form className="intake-flow" onSubmit={handleUpload}>
          <div className="intake-flow__header">
            <h3>Upload Telemetry File</h3>
            <p>Upload a production CSV or JSON telemetry export if you want a file-based baseline. Live REST telemetry can build its own baseline automatically.</p>
          </div>

          <div className="intake-flow__controls">
            <input
              accept=".csv,.json,text/csv,application/json"
              id="csv-upload"
              type="file"
              onChange={(event) => {
                setSelectedFile(event.target.files?.[0] ?? null);
                setUploadError("");
              }}
            />
            <button className="command-button" type="submit" disabled={isUploadProcessing(uploadState)}>
              {isUploadProcessing(uploadState) ? "Processing" : "Upload Telemetry File"}
            </button>
          </div>

          <div className="intake-flow__status">
            <span>{selectedFile ? selectedFile.name : (latestUploadSnapshot?.last_filename ?? "No data connected yet")}</span>
            <span className="intake-flow__progress">
              {isUploadProcessing(uploadState) && <span className="upload-spinner" aria-hidden="true" />}
              {latestMessage}
            </span>
          </div>

          {uploadError && <p className="form-error">{normalizeErrorMessage(uploadError)}</p>}
        </form>
        <div className="connector-json-hint">
          <p className="section-token">JSON upload schema</p>
          <pre className="connector-json-hint__code">{JSON_UPLOAD_SCHEMA_EXAMPLE}</pre>
        </div>
      </Panel>

      <Panel title="Ingestion State" className="span-5">
        <WorkflowStages items={intakeStages} />
      </Panel>

      <Panel title="Latest Sync" className="span-7">
        <MetricGrid
          metrics={[
            { label: "State", value: uploadStateView.connectionStateLabel(latestStatus, uploadState, uploadError) },
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

      <Panel title="Node-RED Cultivation Telemetry" className="span-12">
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
              <label>
                <span>Polling Interval</span>
                <input
                  type="number"
                  min="1"
                  value={connectionForm.polling_interval_seconds}
                  onChange={(event) => setConnectionForm((current) => ({ ...current, polling_interval_seconds: event.target.value }))}
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
                { label: "Polling", value: activeConnection.polling_enabled ? "Enabled" : "Disabled" },
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
            <div className="connector-form__actions">
              <button
                className="secondary-command-button"
                type="button"
                disabled={connectionBusy === `${activeConnection.connection_id}:test`}
                onClick={() => handleConnectionAction(activeConnection.connection_id, "test")}
              >
                {connectionBusy === `${activeConnection.connection_id}:test` ? "Testing" : "Test Connection"}
              </button>
              <button
                className="secondary-command-button"
                type="button"
                disabled={connectionBusy === `${activeConnection.connection_id}:poll-once`}
                onClick={() => handleConnectionAction(activeConnection.connection_id, "poll-once")}
              >
                {connectionBusy === `${activeConnection.connection_id}:poll-once` ? "Polling" : "Poll Once"}
              </button>
              <button
                className="command-button"
                type="button"
                disabled={activeConnection.polling_enabled || connectionBusy === `${activeConnection.connection_id}:start`}
                onClick={() => handleConnectionAction(activeConnection.connection_id, "start")}
              >
                {connectionBusy === `${activeConnection.connection_id}:start` ? "Starting" : "Start Polling"}
              </button>
              <button
                className="secondary-command-button"
                type="button"
                disabled={!activeConnection.polling_enabled || connectionBusy === `${activeConnection.connection_id}:stop`}
                onClick={() => handleConnectionAction(activeConnection.connection_id, "stop")}
              >
                {connectionBusy === `${activeConnection.connection_id}:stop` ? "Stopping" : "Stop Polling"}
              </button>
              <button
                className="secondary-command-button"
                type="button"
                disabled={connectionBusy === `${activeConnection.connection_id}:reset-baseline`}
                onClick={() => handleConnectionAction(activeConnection.connection_id, "reset-baseline")}
              >
                {connectionBusy === `${activeConnection.connection_id}:reset-baseline` ? "Resetting" : "Rebuild Baseline"}
              </button>
            </div>
            <CompactList
              items={[
                `Room: ${activeConnection.room_id ?? "Unknown room"}`,
                `Facility: ${activeConnection.facility_id ?? "Unknown facility"}`,
                `Telemetry timestamp: ${activeConnection.latest_telemetry_timestamp ?? "Awaiting telemetry"}`,
                `Last ingestion source: ${activeConnection.last_ingestion_source ?? "Not yet ingested"}`,
                `Baseline status: ${baselineStatusLabel}`,
                baselineSamplesRequired > 0 ? `Baseline samples: ${baselineSamplesCollected}/${baselineSamplesRequired}` : `Baseline samples: ${baselineSamplesCollected}`,
                activeConnection.last_baseline_update ? `Last baseline update: ${activeConnection.last_baseline_update}` : "Last baseline update: Not yet",
                activeConnection.baseline_error_message ? `Baseline error: ${activeConnection.baseline_error_message}` : null,
                activeConnection.error_message ? `Error: ${activeConnection.error_message}` : `Connection is ${formatConnectionStatus(activeConnection.status).toLowerCase()}.`,
              ].filter(Boolean)}
              emptyText="No live connection metadata yet."
            />
          </>
        ) : (
          <EmptyState title="No data connection registered" body="Register a REST telemetry source to start live polling." compact />
        )}
      </Panel>

      <Panel title="Connection Overview" className="span-12">
        <MetricGrid
          metrics={[
            { label: "Connections", value: connections.length || "Pending" },
            { label: "Online", value: healthyCount },
            { label: "Sensors", value: totalSensors || "Pending" },
            { label: "Readings", value: totalReadings || "Pending" },
          ]}
        />
      </Panel>

      <Panel title="Connections" className="span-7">
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
              <div className="connector-detail-list">
                <div className="connector-detail-row">
                  <span>URL</span>
                  <strong>{connection.url}</strong>
                </div>
                <div className="connector-detail-row">
                  <span>Room</span>
                  <strong>{connection.room_id ?? "Unknown room"}</strong>
                </div>
                <div className="connector-detail-row">
                  <span>Scenario</span>
                  <strong>{connection.current_scenario ?? "Awaiting telemetry"}</strong>
                </div>
                <div className="connector-detail-row">
                  <span>Baseline Samples</span>
                  <strong>{`${connection.baseline_samples_collected ?? 0}/${connection.baseline_samples_required ?? 0}`}</strong>
                </div>
              </div>
              {(connection.error_message || connection.status === "error") && (
                <div className="connector-issues">
                  <p>{connection.error_message || "Connection error. Last valid facility state has been preserved."}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Active Result" className="span-5">
        <MetricGrid
          metrics={[
            { label: "Score", value: latestUploadResult?.sii_intelligence?.neraium_score ?? "No active result" },
            { label: "State", value: latestUploadResult?.sii_intelligence?.facility_state ?? "No active result" },
            { label: "Drift", value: latestUploadResult?.sii_intelligence?.urgency ?? "No active result" },
            { label: "Timestamp", value: activeConnection?.latest_telemetry_timestamp ? formatClockTime(activeConnection.latest_telemetry_timestamp) : uploadStateView.deriveTimeCoverage(latestUploadResult).summary },
          ]}
          compact
        />
        <CompactList
          items={latestUploadResult?.sii_intelligence?.supporting_evidence ?? [latestUploadSnapshot?.message ?? "No data connected yet."]}
          emptyText="No data connected yet."
        />
      </Panel>

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
          <EmptyState title="No ingestion history" body="Completed uploads and meaningful live polling changes will appear here." compact />
        )}
      </Panel>

      {connectionError && (
        <Panel title="Connection Response" className="span-12">
          <p className="form-error">{connectionError}</p>
        </Panel>
      )}
    </div>
  );
}
