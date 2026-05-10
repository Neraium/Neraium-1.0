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
import { connectorStatusTone, formatConnectorStatus } from "../viewModels/operationalHelpers";
import * as uploadStateView from "../viewModels/uploadState";
import { CompactList, DataTable, EmptyState, MetricGrid, Panel, WorkflowStages } from "./workspacePrimitives";

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
  const uploadJobIdRef = useRef(null);
  const pollTimerRef = useRef(null);
  const pollFailureCountRef = useRef(0);
  const [connectorTypes, setConnectorTypes] = useState([]);
  const [connectorHealth, setConnectorHealth] = useState([]);
  const [connectorError, setConnectorError] = useState("");
  const [restForm, setRestForm] = useState({
    source_id: "customer-rest",
    system_id: "facility-rest",
    endpoint: "",
    method: "GET",
    token: "",
    records_path: "",
  });
  const [restResult, setRestResult] = useState(null);
  const [restBusy, setRestBusy] = useState("");

  const loadConnectorData = useCallback(async () => {
    try {
      const [typesResponse, healthResponse] = await Promise.all([
        apiFetch("/api/connectors/types", { accessCode }),
        apiFetch("/api/connectors/health", { accessCode }),
      ]);
      const [typesPayload, healthPayload] = await Promise.all([
        readJsonPayload(typesResponse),
        readJsonPayload(healthResponse),
      ]);
      if (!typesResponse.ok) {
        throw new Error(typesPayload?.detail ?? `Unexpected response: ${typesResponse.status}`);
      }
      if (!healthResponse.ok) {
        throw new Error(healthPayload?.detail ?? `Unexpected response: ${healthResponse.status}`);
      }
      setConnectorTypes(typesPayload?.types ?? []);
      setConnectorHealth(healthPayload?.connectors ?? []);
      setConnectorError("");
    } catch (error) {
      setConnectorError(normalizeErrorMessage(error?.message ?? error));
    }
  }, [accessCode, apiFetch, normalizeErrorMessage, readJsonPayload]);

  useEffect(() => () => {
    if (pollTimerRef.current) {
      window.clearTimeout(pollTimerRef.current);
    }
  }, []);

  useEffect(() => {
    setUploadResult(latestUploadResult);
  }, [latestUploadResult]);

  useEffect(() => {
    loadConnectorData();
  }, [loadConnectorData]);

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
      console.warn(
        "telemetry_upload_failure",
        `message=${classified.message}`,
        `status=${classified.status ?? "n/a"}`,
        `error_type=${classified.errorType ?? "n/a"}`,
      );
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
        await loadConnectorData();
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
      console.warn("telemetry_polling_failure", { ...classified, jobId: pollingJobId, attempts: pollFailureCountRef.current + 1 });
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

  async function handleRestAction(mode) {
    setRestBusy(mode);
    setConnectorError("");
    const payload = {
      ...restForm,
      records_path: restForm.records_path.trim() || null,
      token: restForm.token.trim() || null,
    };
    try {
      const response = await apiFetch(mode === "test" ? "/api/connectors/rest/test" : "/api/connectors/rest/ingest", {
        accessCode,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await readJsonPayload(response);
      if (!response.ok) {
        throw new Error(result?.detail ?? result?.message ?? `Unexpected response: ${response.status}`);
      }
      setRestResult(result);
      await loadConnectorData();
    } catch (error) {
      setConnectorError(normalizeErrorMessage(error?.message ?? error));
    } finally {
      setRestBusy("");
    }
  }

  const healthyCount = connectorHealth.filter((item) => item.connection_status === "ready").length;
  const totalSensors = connectorHealth.reduce((sum, item) => sum + (item.sensors_detected ?? 0), 0);
  const totalRecords = connectorHealth.reduce((sum, item) => sum + (item.records_ingested ?? 0), 0);
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

  return (
    <div className="workspace-grid workspace-grid--connections">
      <Panel title="Data Connections" className="span-7">
        <form className="intake-flow" onSubmit={handleUpload}>
          <div className="intake-flow__header">
            <h3>Upload Telemetry File</h3>
            <p>Upload a production CSV to refresh the active facility result.</p>
          </div>

          <div className="intake-flow__controls">
            <input
              accept=".csv,text/csv"
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
            { label: "Source", value: latestUploadSnapshot?.result_source ? "File Upload" : "Awaiting Upload" },
            { label: "File", value: latestUploadSnapshot?.last_filename ?? uploadJob?.filename ?? "Awaiting upload" },
            { label: "Rows", value: latestUploadSnapshot?.rows_processed ?? uploadJob?.rows_processed ?? "Pending" },
            { label: "Columns", value: latestUploadSnapshot?.columns_detected ?? uploadJob?.columns_detected ?? "Pending" },
            { label: "Primary Room", value: roomContext.primary },
          ]}
        />
      </Panel>

      <Panel title="Change Summary" className="span-5">
        <MetricGrid
          metrics={[
            { label: "Current File", value: latestUploadSnapshot?.history?.[0]?.filename ?? "No active result" },
            { label: "Previous File", value: latestUploadSnapshot?.history?.[1]?.filename ?? "None" },
            { label: "Score Delta", value: latestUploadSnapshot?.history?.[0]?.diff?.neraium_score_delta ?? "n/a" },
            { label: "Result", value: latestUploadSnapshot?.history?.[0]?.operating_state ?? "Awaiting upload" },
          ]}
          compact
        />
        <CompactList items={uploadDiffSummary.lines} emptyText="Upload two files to compare changes." />
      </Panel>

      <Panel title="Upload History" className="span-12">
        {uploadHistoryRows.length > 0 ? (
          <DataTable
            columns={["File", "Status", "Score", "State", "Room", "Delta"]}
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
          <EmptyState title="No upload history" body="Completed uploads will appear here." compact />
        )}
      </Panel>

      <Panel title="Connection Overview" className="span-12">
        <MetricGrid
          metrics={[
            { label: "Types", value: connectorTypes.length || "Pending" },
            { label: "Ready", value: healthyCount },
            { label: "Sensors", value: totalSensors || "Pending" },
            { label: "Records", value: totalRecords || "Pending" },
          ]}
        />
      </Panel>

      <Panel title="Connections" className="span-7">
        <div className="connector-status-list">
          {connectorHealth.map((connector) => (
            <div className="connector-status-card" key={connector.connector_type}>
              <div className="connector-status-card__header">
                <div>
                  <p className="section-token">{connector.connector_type}</p>
                  <h3>{connector.display_name}</h3>
                </div>
                <span className={`connector-status-pill connector-status-pill--${connectorStatusTone(connector.connection_status)}`}>
                  {formatConnectorStatus(connector.connection_status)}
                </span>
              </div>
              <MetricGrid
                metrics={[
                  { label: "Last Sync", value: connector.last_sync_time ? formatClockTime(connector.last_sync_time) : "Awaiting sync" },
                  { label: "Sensors", value: connector.sensors_detected ?? 0 },
                  { label: "Records", value: connector.records_ingested ?? 0 },
                  { label: "Mode", value: connector.functional ? "Functional" : "Scaffolded" },
                ]}
                compact
              />
              {connector.masked_configuration && Object.keys(connector.masked_configuration).length > 0 && (
                <div className="connector-detail-list">
                  {Object.entries(connector.masked_configuration).map(([key, value]) => (
                    <div className="connector-detail-row" key={key}>
                      <span>{key}</span>
                      <strong>{typeof value === "object" ? JSON.stringify(value) : String(value)}</strong>
                    </div>
                  ))}
                </div>
              )}
              {(connector.warnings?.length > 0 || connector.errors?.length > 0) && (
                <div className="connector-issues">
                  {[...(connector.warnings ?? []), ...(connector.errors ?? [])].slice(0, 4).map((item) => (
                    <p key={item}>{item}</p>
                  ))}
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
            { label: "Timestamps", value: uploadStateView.deriveTimeCoverage(latestUploadResult).summary },
          ]}
          compact
        />
        <CompactList
          items={latestUploadResult?.sii_intelligence?.supporting_evidence ?? [latestUploadSnapshot?.message ?? "No data connected yet."]}
          emptyText="No data connected yet."
        />
      </Panel>

      <Panel title="REST Connection" className="span-12">
        <form className="connector-rest-grid" onSubmit={(event) => event.preventDefault()}>
          <label>
            <span>Endpoint</span>
            <input
              type="url"
              value={restForm.endpoint}
              onChange={(event) => setRestForm((current) => ({ ...current, endpoint: event.target.value }))}
              placeholder="https://customer.example.com/telemetry"
            />
          </label>
          <label>
            <span>HTTP method</span>
            <select
              value={restForm.method}
              onChange={(event) => setRestForm((current) => ({ ...current, method: event.target.value }))}
            >
              <option value="GET">GET</option>
              <option value="POST">POST</option>
            </select>
          </label>
          <label>
            <span>Source ID</span>
            <input
              type="text"
              value={restForm.source_id}
              onChange={(event) => setRestForm((current) => ({ ...current, source_id: event.target.value }))}
            />
          </label>
          <label>
            <span>System ID</span>
            <input
              type="text"
              value={restForm.system_id}
              onChange={(event) => setRestForm((current) => ({ ...current, system_id: event.target.value }))}
            />
          </label>
          <label>
            <span>Token</span>
            <input
              type="password"
              value={restForm.token}
              onChange={(event) => setRestForm((current) => ({ ...current, token: event.target.value }))}
              placeholder="Bearer token"
            />
          </label>
          <label>
            <span>Records path</span>
            <input
              type="text"
              value={restForm.records_path}
              onChange={(event) => setRestForm((current) => ({ ...current, records_path: event.target.value }))}
              placeholder="data.records"
            />
          </label>
          <div className="connector-form__actions">
            <button className="secondary-command-button" type="button" disabled={restBusy === "test"} onClick={() => handleRestAction("test")}>
              {restBusy === "test" ? "Testing" : "Test connection"}
            </button>
            <button className="command-button" type="button" disabled={restBusy === "ingest"} onClick={() => handleRestAction("ingest")}>
              {restBusy === "ingest" ? "Ingesting" : "Ingest connector data"}
            </button>
          </div>
        </form>

        <div className="connector-rest-output">
          <MetricGrid
            metrics={[
              { label: "State", value: restResult?.connection_status ? formatConnectorStatus(restResult.connection_status) : "Awaiting validation" },
              { label: "Sensors", value: restResult?.sensors_detected ?? "Pending" },
              { label: "Records", value: restResult?.records_ingested ?? "Pending" },
              { label: "Last Sync", value: restResult?.last_sync_time ? formatClockTime(restResult.last_sync_time) : "Awaiting validation" },
            ]}
            compact
          />
          {restResult?.masked_configuration && (
            <div className="connector-detail-list">
              {Object.entries(restResult.masked_configuration).map(([key, value]) => (
                <div className="connector-detail-row" key={key}>
                  <span>{key}</span>
                  <strong>{typeof value === "object" ? JSON.stringify(value) : String(value)}</strong>
                </div>
              ))}
            </div>
          )}
          {restResult?.warnings?.length > 0 && (
            <div className="connector-issues">
              {restResult.warnings.slice(0, 4).map((warning) => <p key={warning}>{warning}</p>)}
            </div>
          )}
        </div>
      </Panel>

      {connectorError && (
        <Panel title="Connector response" subtitle="Operator-friendly validation feedback." className="span-12">
          <p className="form-error">{connectorError}</p>
        </Panel>
      )}
    </div>
  );
}
