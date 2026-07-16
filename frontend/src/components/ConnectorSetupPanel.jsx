import { useCallback, useEffect, useMemo, useState } from "react";

import { connectorHealthLabel } from "../content/productLanguage";

const SAFE_CONFIG_KEY = "neraium.connector.safe_config";
const DEFAULT_SAMPLE = JSON.stringify({ records: [{ timestamp: "2026-01-01T00:00:00Z", sensor_id: "supply_temp", value: 42.5, unit: "f" }] }, null, 2);

function readSafeConfig() {
  if (typeof window === "undefined") return {};
  try { return JSON.parse(window.sessionStorage.getItem(SAFE_CONFIG_KEY) || "{}"); } catch { return {}; }
}

async function responsePayload(response) {
  try { return await response.json(); } catch { return {}; }
}

function safeConnectorDetail(value) {
  const detail = String(value || "").trim();
  if (!detail) return "The connector settings were not accepted.";
  if (/(traceback|exception|stack trace|shared_upload|psycopg|sqlite3|errno|file:\/\/|[a-z]:\\)/i.test(detail)) {
    return "The connector could not complete the request. Check the settings and retry.";
  }
  return detail;
}

function connectorError(response, payload) {
  if (response?.status === 401) return "Your session expired. Sign in again and retry.";
  if (response?.status === 403) return "Administrator access is required to configure telemetry connectors.";
  if (response?.status === 400) return `${safeConnectorDetail(payload?.detail)} Review the fields and retry.`;
  return "The connector service is unavailable. Check service health and retry.";
}

export default function ConnectorSetupPanel({ apiFetch, accessCode, currentUser }) {
  const saved = useMemo(readSafeConfig, []);
  const [connectorType, setConnectorType] = useState(saved.connectorType || "rest");
  const [sourceId, setSourceId] = useState(saved.sourceId || "facility-source");
  const [systemId, setSystemId] = useState(saved.systemId || "facility-system");
  const [endpoint, setEndpoint] = useState(saved.endpoint || "");
  const [samplePayload, setSamplePayload] = useState(saved.samplePayload || DEFAULT_SAMPLE);
  const [databaseUrl, setDatabaseUrl] = useState("");
  const [query, setQuery] = useState(saved.query || "SELECT timestamp, sensor_id, value, unit FROM telemetry ORDER BY timestamp DESC LIMIT 500");
  const [types, setTypes] = useState([]);
  const [health, setHealth] = useState([]);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const isAdmin = currentUser?.role === "admin";

  const refresh = useCallback(async ({ announce = true } = {}) => {
    if (!isAdmin) return;
    setBusy((current) => current || "refresh");
    setError("");
    try {
      const [typesResponse, healthResponse] = await Promise.all([
        apiFetch("/api/connectors/types", { accessCode, cache: "no-store" }),
        apiFetch("/api/connectors/health", { accessCode, cache: "no-store" }),
      ]);
      const typesPayload = await responsePayload(typesResponse);
      const healthPayload = await responsePayload(healthResponse);
      if (!typesResponse.ok) throw new Error(connectorError(typesResponse, typesPayload));
      if (!healthResponse.ok) throw new Error(connectorError(healthResponse, healthPayload));
      setTypes(typesPayload.types || []);
      setHealth(healthPayload.connectors || []);
      if (announce) setNotice("Connector health refreshed.");
    } catch (refreshError) {
      setError(String(refreshError?.message || refreshError));
    } finally {
      setBusy("");
    }
  }, [accessCode, apiFetch, isAdmin]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    window.sessionStorage.setItem(SAFE_CONFIG_KEY, JSON.stringify({ connectorType, sourceId, systemId, endpoint, samplePayload, query }));
  }, [connectorType, endpoint, query, samplePayload, sourceId, systemId]);

  async function run(action) {
    if (busy) return;
    setBusy(action);
    setError("");
    setNotice("");
    try {
      let path;
      let payload;
      if (connectorType === "rest") {
        let parsedSample;
        try { parsedSample = JSON.parse(samplePayload); } catch { throw new Error("Sample JSON is invalid. Correct it before testing the connector."); }
        path = `/api/connectors/rest/${action === "test" ? "test" : "ingest"}`;
        payload = { source_id: sourceId, system_id: systemId, endpoint: endpoint || "https://example.invalid/telemetry", method: "GET", sample_payload: parsedSample };
      } else {
        if (!databaseUrl.trim()) throw new Error("Enter a read-only SQLite or PostgreSQL database URL.");
        if (!query.trim()) throw new Error("Enter a bounded read-only SELECT query.");
        path = `/api/connectors/database/${action === "test" ? "test" : "ingest"}`;
        payload = { source_id: sourceId, system_id: systemId, database_url: databaseUrl, query, max_rows: 5000, query_timeout_seconds: 30, sslmode: "require" };
      }
      const response = await apiFetch(path, { accessCode, method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const body = await responsePayload(response);
      if (!response.ok) throw new Error(connectorError(response, body));
      setNotice(action === "test" ? `${body.message} No records were saved.` : `${body.message} ${body.records_ingested || 0} records were validated for analysis.`);
      await refresh({ announce: false });
    } catch (actionError) {
      setError(String(actionError?.message || actionError));
    } finally {
      setBusy("");
    }
  }

  if (!isAdmin) {
    return <section className="connector-setup" aria-label="Telemetry connector permissions"><h2>Telemetry connectors</h2><p>Only administrators can configure connectors or review connector health. Import a CSV dataset for analysis, or ask an administrator to configure a supported read-only connector.</p></section>;
  }

  const functionalTypes = types.filter((item) => item.functional && ["rest", "database"].includes(item.connector_type));
  return (
    <section className="connector-setup" aria-labelledby="connector-title">
      <div className="connector-setup__header"><div><p className="section-token">Administrator</p><h2 id="connector-title">Telemetry Connector Setup</h2><p>Test read-only access before preparing a bounded telemetry sample. Credentials are used only for the request and are masked in connector health responses.</p></div><button type="button" className="secondary-command-button" onClick={() => void refresh()} disabled={Boolean(busy)}>{busy === "refresh" ? "Refreshing..." : "Refresh health"}</button></div>
      <div className="connector-setup__grid">
        <label>Connector type<select value={connectorType} onChange={(event) => setConnectorType(event.target.value)} disabled={Boolean(busy)}>{functionalTypes.map((item) => <option key={item.connector_type} value={item.connector_type}>{item.display_name}</option>)}</select></label>
        <label>Source identifier<input value={sourceId} onChange={(event) => setSourceId(event.target.value)} disabled={Boolean(busy)} /></label>
        <label>System identifier<input value={systemId} onChange={(event) => setSystemId(event.target.value)} disabled={Boolean(busy)} /></label>
        {connectorType === "rest" ? <><label className="connector-setup__wide">Endpoint<input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="https://telemetry.example/api/readings" disabled={Boolean(busy)} /></label><label className="connector-setup__wide">Sample response JSON<textarea value={samplePayload} onChange={(event) => setSamplePayload(event.target.value)} rows={7} disabled={Boolean(busy)} /></label></> : <><label className="connector-setup__wide">Database URL<input type="password" value={databaseUrl} onChange={(event) => setDatabaseUrl(event.target.value)} placeholder="postgresql://readonly@host/database" autoComplete="off" disabled={Boolean(busy)} /></label><label className="connector-setup__wide">Read-only query<textarea value={query} onChange={(event) => setQuery(event.target.value)} rows={5} disabled={Boolean(busy)} /></label></>}
      </div>
      <div className="operational-actions"><button type="button" className="secondary-command-button" onClick={() => void run("test")} disabled={Boolean(busy)}>{busy === "test" ? "Testing..." : "Test connection"}</button><button type="button" className="command-button" onClick={() => void run("ingest")} disabled={Boolean(busy)} title="Validates and prepares a bounded sample. This does not run an analysis.">{busy === "ingest" ? "Preparing sample..." : "Prepare sample"}</button></div>
      {notice ? <p className="connector-notice" role="status">{notice}</p> : null}{error ? <p className="auth-error" role="alert">{error}</p> : null}
      <div className="connector-health" aria-label="Connector health">{health.map((item) => <article key={item.connector_type}><strong>{item.display_name}</strong><span className={`connector-health__status connector-health__status--${item.connection_status}`}>{connectorHealthLabel(item.connection_status)}</span><small>{item.records_ingested || 0} records · {item.sensors_detected || 0} sensors</small>{item.errors?.length ? <small>{safeConnectorDetail(item.errors[0])}</small> : null}</article>)}</div>
    </section>
  );
}
