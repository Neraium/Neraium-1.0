import { useEffect, useMemo, useState } from "react";

import DataConnectionsWorkspace from "./DataConnectionsWorkspace";
import GoldenNuggetAssessment from "./GoldenNuggetAssessment";
import SkipToMainContent from "./SkipToMainContent";
import { buildEngineeringReasoningModel } from "../viewModels/engineeringReasoning";
import {
  buildSystemRows,
  filterFindings,
  formatDateTime,
  mergeFindings,
  normalizeCurrentFindings,
  normalizePersistedFinding,
  persistenceLabel,
} from "../viewModels/monitoringProduct";
import "../styles/monitoring.css";

const ROUTE_PATHS = {
  status: "/status",
  findings: "/findings",
  systems: "/systems",
  data: "/data",
};

const PRIMARY_NAV = [
  { id: "status", label: "Status" },
  { id: "findings", label: "Findings" },
  { id: "systems", label: "Systems" },
  { id: "data", label: "Data" },
];

function routeFromLocation() {
  if (typeof window === "undefined") return "status";
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (/^\/findings\/[^/]+/.test(path) || path.startsWith("/evidence") || path.startsWith("/investigations")) return "evidence";
  if (path === "/findings" || path === "/workspace/insights") return "findings";
  if (path === "/systems" || path.startsWith("/systems/")) return "systems";
  if (path === "/data" || path === "/workspace/data-sources") return "data";
  return "status";
}

function findingIdFromLocation() {
  if (typeof window === "undefined") return "";
  const parts = window.location.pathname.split("/").filter(Boolean);
  if (parts[0] === "findings" && parts[1]) return decodeURIComponent(parts[1]);
  if (["evidence", "investigations"].includes(parts[0]) && parts[1]) return decodeURIComponent(parts[1]);
  return "";
}

function responseJson(response) {
  return response?.json?.().catch(() => ({})) ?? Promise.resolve({});
}

function statusTone(value) {
  return String(value ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function displayCoverage(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "Not available";
  return `${Math.round((numeric > 1 ? numeric / 100 : numeric) * 100)}%`;
}

function displayCount(value, singular, plural = `${singular}s`) {
  const count = Number(value) || 0;
  return `${count} ${count === 1 ? singular : plural}`;
}

function windowLabel(start, end) {
  if (!start && !end) return "Not available";
  if (start && end) return `${formatDateTime(start)} to ${formatDateTime(end)}`;
  return formatDateTime(start || end);
}

function lastAnalysisAt(result, snapshot) {
  return result?.completed_at
    ?? result?.processed_at
    ?? result?.last_processed_at
    ?? result?.processing_trace?.completed_at
    ?? snapshot?.last_processed_at
    ?? snapshot?.processed_at
    ?? null;
}

function isAnalysisRunning(gateProcessing, result, snapshot) {
  const state = [
    gateProcessing?.status,
    gateProcessing?.state,
    gateProcessing?.processing_state,
    result?.status,
    result?.processing_state,
    snapshot?.status,
    snapshot?.processing_state,
  ].filter(Boolean).join(" ").toLowerCase();
  return gateProcessing?.active === true || /queued|processing|analyzing|running|baseline_modeling|building/.test(state);
}

function isAnalysisFailed(result, snapshot) {
  const state = [result?.status, result?.processing_state, snapshot?.status, snapshot?.processing_state].filter(Boolean).join(" ").toLowerCase();
  return /failed|error|cancelled|timeout/.test(state);
}

function findingStorageKey(user) {
  const scope = String(user?.email ?? user?.id ?? "operator").toLowerCase().replace(/[^a-z0-9@._-]+/g, "-");
  return `neraium.findings.acknowledged.${scope}`;
}

function readAcknowledged(user) {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(findingStorageKey(user)) || "[]");
    return Array.isArray(value) ? value.map(String) : [];
  } catch {
    return [];
  }
}

function writeAcknowledged(user, values) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(findingStorageKey(user), JSON.stringify(values));
  } catch {
    // Acknowledgment is optional; monitoring remains available without browser storage.
  }
}

function Metric({ label, value, detail }) {
  return (
    <div className="monitoring-metric">
      <dt>{label}</dt>
      <dd>{value}</dd>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

function FindingCard({ finding, acknowledged, onAcknowledge, onEvidence, compact = false }) {
  const state = acknowledged && finding.state === "active" ? "acknowledged" : finding.state;
  return (
    <article className={`monitoring-finding-card monitoring-finding-card--${state}${compact ? " is-compact" : ""}`} data-testid="finding-card">
      <div className="monitoring-finding-card__heading">
        <div>
          <span className="monitoring-state-label"><i aria-hidden="true" />{state}</span>
          <h3>{finding.title}</h3>
        </div>
        <span className="monitoring-finding-card__system">{finding.system}</span>
      </div>
      <p className="monitoring-finding-card__description">{finding.description}</p>
      <dl className="monitoring-finding-facts">
        <div><dt>Persistent for</dt><dd>{persistenceLabel(finding)}</dd></div>
        <div><dt>Corroboration</dt><dd>{displayCount(finding.corroborationCount, "related signal")}</dd></div>
        <div><dt>First detected</dt><dd>{formatDateTime(finding.firstDetectedAt)}</dd></div>
      </dl>
      <div className="monitoring-finding-card__actions">
        <button type="button" className="monitoring-button monitoring-button--primary" onClick={() => onEvidence(finding)}>View evidence</button>
        {finding.state === "active" ? (
          <button
            type="button"
            className="monitoring-button monitoring-button--quiet"
            aria-pressed={acknowledged}
            onClick={() => onAcknowledge(finding)}
          >
            {acknowledged ? "Acknowledged" : "Acknowledge"}
          </button>
        ) : null}
      </div>
    </article>
  );
}

function StatusPage({
  activeFindings,
  acknowledgedIds,
  model,
  liveOps,
  result,
  snapshot,
  gateProcessing,
  onAcknowledge,
  onEvidence,
  onNavigate,
}) {
  const hasAnalysis = model.hasAnalysis;
  const learning = isAnalysisRunning(gateProcessing, result, snapshot);
  const failed = isAnalysisFailed(result, snapshot);
  const degraded = liveOps?.connectionTone === "degraded" || liveOps?.apiStatus?.state === "offline";
  const stale = liveOps?.dataFreshness?.tone === "stale";
  const latestAt = lastAnalysisAt(result, snapshot);
  const systemCount = Math.max(model.subsystems.length, liveOps?.systems?.length ?? 0);
  const relationshipCount = model.relationships.length;

  return (
    <div className="monitoring-page monitoring-status-page" data-testid="status-page">
      <header className="monitoring-page-header">
        <div><p>Status</p><h1>System monitoring</h1></div>
        {hasAnalysis ? <span className={`monitoring-health-chip monitoring-health-chip--${activeFindings.length ? "change" : "quiet"}`}>{activeFindings.length ? "Change detected" : "Monitoring"}</span> : null}
      </header>

      {failed ? <div className="monitoring-notice monitoring-notice--error" role="alert"><strong>Analysis failed</strong><span>The last analysis did not complete. Existing findings and evidence are unchanged.</span><button type="button" onClick={() => onNavigate("data")}>Open data</button></div> : null}
      {degraded ? <div className="monitoring-notice" role="status"><strong>Connection degraded</strong><span>Neraium cannot confirm the latest monitoring state.</span></div> : null}
      {stale && !degraded ? <div className="monitoring-notice" role="status"><strong>Data is stale</strong><span>The latest source update is outside the expected monitoring window.</span></div> : null}

      {!hasAnalysis && !learning ? (
        <section className="monitoring-onboarding" aria-labelledby="monitoring-onboarding-title">
          <div className="monitoring-onboarding__copy">
            <span className="monitoring-eyebrow">Set up monitoring</span>
            <h2 id="monitoring-onboarding-title">Connect or import telemetry</h2>
            <p>Neraium needs historical operating data to learn how signals normally behave together.</p>
            <button type="button" className="monitoring-button monitoring-button--primary" onClick={() => onNavigate("data")}>Open data setup</button>
          </div>
          <ol className="monitoring-steps">
            <li><span>1</span><div><strong>Connect or import data</strong><small>Use a live source or a historical dataset.</small></div></li>
            <li><span>2</span><div><strong>Learn normal behavior</strong><small>Relationships are learned from comparable operating periods.</small></div></li>
            <li><span>3</span><div><strong>Begin monitoring</strong><small>Neraium stays quiet until a supported, persistent change appears.</small></div></li>
          </ol>
        </section>
      ) : learning ? (
        <section className="monitoring-state-hero monitoring-state-hero--learning" role="status" aria-live="polite">
          <span className="monitoring-state-symbol" aria-hidden="true" />
          <div><p>Learning baseline</p><h2>Learning how signals normally behave together.</h2><span>Monitoring begins when baseline learning is complete.</span></div>
        </section>
      ) : activeFindings.length ? (
        <section className="monitoring-active-state" aria-labelledby="active-state-title">
          <div className="monitoring-active-state__intro">
            <span className="monitoring-eyebrow">Meaningful change detected</span>
            <h2 id="active-state-title">Something about this system’s behavior has changed.</h2>
            <p>Neraium found a persistent relationship change with supporting evidence.</p>
          </div>
          <FindingCard finding={activeFindings[0]} acknowledged={acknowledgedIds.includes(String(activeFindings[0].id))} onAcknowledge={onAcknowledge} onEvidence={onEvidence} />
          {activeFindings.length > 1 ? <button type="button" className="monitoring-text-link" onClick={() => onNavigate("findings")}>View all {activeFindings.length} active findings</button> : null}
        </section>
      ) : (
        <section className="monitoring-state-hero monitoring-state-hero--quiet" aria-labelledby="quiet-state-title">
          <span className="monitoring-state-symbol" aria-hidden="true" />
          <div>
            <p>Monitoring</p>
            <h2 id="quiet-state-title">No meaningful relationship changes detected.</h2>
            <span>Neraium will speak up when a persistent, supported change appears.</span>
          </div>
        </section>
      )}

      <dl className="monitoring-metrics" aria-label="Monitoring status details">
        <Metric label="Last successful analysis" value={latestAt ? formatDateTime(latestAt) : "Not available"} />
        <Metric label="Data freshness" value={liveOps?.dataFreshness?.label ?? "No data"} />
        <Metric label="Monitored systems" value={String(systemCount)} detail={systemCount ? "Systems with mapped telemetry" : "Available after signal mapping"} />
        <Metric label="Learned relationships" value={String(relationshipCount)} detail={relationshipCount ? "Relationships in the current baseline" : "Available after baseline learning"} />
      </dl>
    </div>
  );
}

function FindingsPage({ findings, acknowledgedIds, onAcknowledge, onEvidence }) {
  const [filters, setFilters] = useState({ state: "active", system: "all", date: "" });
  const systems = [...new Set(findings.map((finding) => finding.system))].sort();
  const visible = filterFindings(findings, filters);
  return (
    <div className="monitoring-page" data-testid="findings-page">
      <header className="monitoring-page-header">
        <div><p>Findings</p><h1>Relationship changes</h1><span>Active and historical changes that met the engine’s evidence requirements.</span></div>
        <span className="monitoring-count">{displayCount(findings.filter((finding) => finding.state === "active").length, "active finding")}</span>
      </header>
      <form className="monitoring-filters" aria-label="Filter findings" onSubmit={(event) => event.preventDefault()}>
        <label><span>State</span><select value={filters.state} onChange={(event) => setFilters((current) => ({ ...current, state: event.target.value }))}><option value="active">Active</option><option value="resolved">Resolved</option><option value="all">All</option></select></label>
        <label><span>System</span><select value={filters.system} onChange={(event) => setFilters((current) => ({ ...current, system: event.target.value }))}><option value="all">All systems</option>{systems.map((system) => <option key={system} value={system}>{system}</option>)}</select></label>
        <label><span>First detected</span><input type="date" value={filters.date} onChange={(event) => setFilters((current) => ({ ...current, date: event.target.value }))} /></label>
        {(filters.state !== "active" || filters.system !== "all" || filters.date) ? <button type="button" className="monitoring-button monitoring-button--quiet" onClick={() => setFilters({ state: "active", system: "all", date: "" })}>Clear filters</button> : null}
      </form>
      <div className="monitoring-findings-list">
        {visible.length ? visible.map((finding) => <FindingCard key={finding.id} finding={finding} acknowledged={acknowledgedIds.includes(String(finding.id))} onAcknowledge={onAcknowledge} onEvidence={onEvidence} compact />) : (
          <section className="monitoring-empty">
            <h2>No findings match these filters.</h2>
            <p>Neraium does not create queue items when no meaningful change is present.</p>
          </section>
        )}
      </div>
    </div>
  );
}

function RelationshipComparison({ relationship }) {
  const baseline = relationship?.baseline;
  const current = relationship?.current;
  const numeric = Number.isFinite(baseline) && Number.isFinite(current);
  const max = numeric ? Math.max(Math.abs(baseline), Math.abs(current), 0.01) : 1;
  const baselineWidth = numeric ? Math.max(4, (Math.abs(baseline) / max) * 100) : 100;
  const currentWidth = numeric ? Math.max(4, (Math.abs(current) / max) * 100) : 64;
  return (
    <figure className="relationship-comparison" aria-labelledby="relationship-comparison-title">
      <figcaption id="relationship-comparison-title">Baseline versus current relationship</figcaption>
      <div className="relationship-bar">
        <div><span>Before</span><i style={{ width: `${baselineWidth}%` }} /><strong>{numeric ? baseline.toFixed(2) : "Learned pattern"}</strong></div>
        <div><span>Now</span><i style={{ width: `${currentWidth}%` }} /><strong>{numeric ? current.toFixed(2) : "Changed pattern"}</strong></div>
      </div>
      {numeric ? <p>Coupling changed by {Math.abs(Number.isFinite(relationship.delta) ? relationship.delta : current - baseline).toFixed(2)}.</p> : <p>The current relationship is outside its learned pattern.</p>}
    </figure>
  );
}

function EvidencePage({ finding, onBack }) {
  if (!finding) {
    return (
      <div className="monitoring-page">
        <button type="button" className="monitoring-back" onClick={onBack}>Back to findings</button>
        <section className="monitoring-empty"><h1>Evidence not found</h1><p>This finding is not available in the current workspace.</p></section>
      </div>
    );
  }
  const relationship = finding.relationships[0] ?? null;
  const endpoints = relationship?.endpoints?.length ? relationship.endpoints : finding.variables.slice(0, 2);
  return (
    <div className="monitoring-page monitoring-evidence-page" data-testid="evidence-page">
      <button type="button" className="monitoring-back" onClick={onBack}>Back to findings</button>
      <header className="monitoring-evidence-header">
        <span className={`monitoring-state-label monitoring-state-label--${finding.state}`}><i aria-hidden="true" />{finding.state}</span>
        <p>{finding.system}</p>
        <h1>{finding.title}</h1>
        <span>{finding.description}</span>
      </header>

      <section className="monitoring-evidence-grid" aria-label="Finding evidence">
        <div className="monitoring-evidence-primary">
          <section className="evidence-block" aria-labelledby="relationship-title">
            <p className="monitoring-eyebrow">What relationship changed</p>
            <h2 id="relationship-title">{endpoints.length >= 2 ? `${endpoints[0]} and ${endpoints[1]}` : finding.title}</h2>
            <RelationshipComparison relationship={relationship} />
          </section>
          <section className="evidence-block" aria-labelledby="change-timeline-title">
            <p className="monitoring-eyebrow">When the change began</p>
            <h2 id="change-timeline-title">{formatDateTime(finding.firstDetectedAt)}</h2>
            <div className="evidence-timeline" aria-label="Relationship change timeline">
              <i aria-hidden="true" />
              <div><span>Learned baseline</span><small>{windowLabel(finding.window.baselineStart, finding.window.baselineEnd)}</small></div>
              <div><span>Change detected</span><small>{formatDateTime(finding.firstDetectedAt)}</small></div>
              <div><span>Latest analysis</span><small>{formatDateTime(finding.lastObservedAt)}</small></div>
            </div>
          </section>
        </div>
        <aside className="monitoring-evidence-facts">
          <dl>
            <Metric label="Persistence" value={persistenceLabel(finding)} />
            <Metric label="Supporting signals" value={String(finding.corroborationCount)} />
            <Metric label="Current period" value={windowLabel(finding.window.currentStart, finding.window.currentEnd)} />
            <Metric label="Comparable context" value={finding.window.comparableContext || "Matched operating context"} />
          </dl>
        </aside>
      </section>

      {finding.variables.length ? <section className="evidence-block"><p className="monitoring-eyebrow">Corroborating signals</p><div className="signal-chips">{finding.variables.map((variable) => <span key={variable}>{variable}</span>)}</div></section> : null}
      {finding.evidence.length ? <section className="evidence-block"><p className="monitoring-eyebrow">Supporting observations</p><ul className="evidence-observations">{finding.evidence.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
      {finding.limitations.length ? <section className="evidence-block evidence-block--limitations"><p className="monitoring-eyebrow">Data and context limitations</p><ul>{finding.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}

      <details className="monitoring-technical">
        <summary>Detailed measurements</summary>
        <div>
          <dl className="monitoring-technical-grid">
            <Metric label="Evidence record" value={finding.runId || "Current analysis"} />
            <Metric label="Source" value={finding.sourceName || "Mapped telemetry"} />
            <Metric label="Baseline coupling" value={Number.isFinite(relationship?.baseline) ? relationship.baseline.toFixed(4) : "Not available"} />
            <Metric label="Current coupling" value={Number.isFinite(relationship?.current) ? relationship.current.toFixed(4) : "Not available"} />
            <Metric label="Coupling change" value={Number.isFinite(relationship?.delta) ? relationship.delta.toFixed(4) : "Not available"} />
            <Metric label="Data quality" value={finding.dataQuality || (finding.limitations.length ? "Limited" : "No limitation recorded")} />
          </dl>
          {relationship?.raw ? <details className="monitoring-raw-values"><summary>Raw relationship values</summary><pre><code>{JSON.stringify(relationship.raw, null, 2)}</code></pre></details> : null}
        </div>
      </details>
    </div>
  );
}

function SystemsPage({ systems }) {
  return (
    <div className="monitoring-page" data-testid="systems-page">
      <header className="monitoring-page-header">
        <div><p>Systems</p><h1>Monitoring coverage</h1><span>Systems, mapped signals, learned relationships, and current relationship health.</span></div>
        <span className="monitoring-count">{displayCount(systems.length, "system")}</span>
      </header>
      {systems.length ? <div className="monitoring-systems-table" role="table" aria-label="Monitored systems">
        <div className="monitoring-systems-table__header" role="row">
          <span role="columnheader">System</span><span role="columnheader">Mapped signals</span><span role="columnheader">Relationships</span><span role="columnheader">Coverage</span><span role="columnheader">Freshness</span><span role="columnheader">Relationship health</span>
        </div>
        {systems.map((system) => (
          <article key={system.id} className="monitoring-system-row" role="row">
            <div role="cell"><strong>{system.name}</strong>{system.activeFindingCount ? <small>{displayCount(system.activeFindingCount, "active finding")}</small> : null}</div>
            <span role="cell" data-label="Mapped signals">{system.signalCount || "Not available"}</span>
            <span role="cell" data-label="Relationships">{system.relationshipCount || "Learning"}</span>
            <span role="cell" data-label="Coverage">{displayCoverage(system.coverage)}</span>
            <span role="cell" data-label="Freshness">{system.freshness?.label ?? "No data"}</span>
            <span role="cell" data-label="Relationship health" className={`system-health system-health--${statusTone(system.health)}`}><i aria-hidden="true" />{system.health}</span>
          </article>
        ))}
      </div> : <section className="monitoring-empty"><h2>No systems mapped yet.</h2><p>Systems appear after telemetry is connected or imported and signal mapping completes.</p></section>}
    </div>
  );
}

function sourceStatus(connection) {
  const status = String(connection?.status ?? "").toLowerCase();
  if (/ready|online|connected|active|healthy/.test(status)) return "Connected";
  if (/error|failed|offline|disconnected/.test(status)) return "Disconnected";
  return status ? status.replace(/_/g, " ") : "Not configured";
}

function DataPage({
  accessCode,
  apiFetch,
  currentUser,
  connections,
  setConnections,
  connectionsState,
  result,
  snapshot,
  model,
  liveOps,
  onUploadComplete,
  pendingUploadFiles,
  setPendingUploadFiles,
}) {
  const [connectionBusy, setConnectionBusy] = useState("");
  const [connectionNotice, setConnectionNotice] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [connectionForm, setConnectionForm] = useState({ name: "", url: "", facilityId: "", pollingSeconds: "300" });
  const qualityWarnings = [
    ...(Array.isArray(result?.data_quality?.warnings) ? result.data_quality.warnings : []),
    ...(Array.isArray(result?.warnings) ? result.warnings : []),
  ];

  async function runConnectionAction(connection, action) {
    if (connectionBusy) return;
    const id = String(connection?.connection_id ?? "");
    setConnectionBusy(`${id}:${action}`);
    setConnectionError("");
    setConnectionNotice("");
    try {
      const response = await apiFetch(`/api/data-connections/${encodeURIComponent(id)}/${action}`, { accessCode, method: "POST" });
      const payload = await responseJson(response);
      if (!response?.ok) throw new Error("The connection action did not complete.");
      if (payload.connection) setConnections((current) => current.map((item) => item.connection_id === id ? payload.connection : item));
      setConnectionNotice(action === "test" ? "Connection test complete." : action === "poll-once" ? "Source checked for new data." : action === "start" ? "Live monitoring started." : "Live monitoring stopped.");
    } catch (error) {
      setConnectionError(String(error?.message || "The connection action did not complete."));
    } finally {
      setConnectionBusy("");
    }
  }

  async function saveConnection(event) {
    event.preventDefault();
    if (connectionBusy || !connectionForm.name.trim() || !connectionForm.url.trim()) return;
    setConnectionBusy("create");
    setConnectionError("");
    setConnectionNotice("");
    try {
      const response = await apiFetch("/api/data-connections", {
        accessCode,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: connectionForm.name.trim(),
          url: connectionForm.url.trim(),
          source_type: "external_rest_api",
          facility_id: connectionForm.facilityId.trim() || null,
          polling_enabled: false,
          polling_interval_seconds: Math.max(1, Number(connectionForm.pollingSeconds) || 300),
        }),
      });
      const payload = await responseJson(response);
      if (!response?.ok || !payload.connection) throw new Error("The connection could not be saved. Check the fields and retry.");
      setConnections((current) => [payload.connection, ...current.filter((item) => item.connection_id !== payload.connection.connection_id)]);
      setConnectionForm({ name: "", url: "", facilityId: "", pollingSeconds: "300" });
      setConnectionNotice("Connection saved. Test it before starting live monitoring.");
    } catch (error) {
      setConnectionError(String(error?.message || "The connection could not be saved."));
    } finally {
      setConnectionBusy("");
    }
  }

  return (
    <div className="monitoring-page monitoring-data-page" data-testid="data-page">
      <header className="monitoring-page-header">
        <div><p>Data</p><h1>Historical assessment</h1><span>Prove the blinded baseline-to-event workflow on real tower telemetry.</span></div>
        <span className="monitoring-health-chip monitoring-health-chip--learning">Pilot workflow</span>
      </header>
      <GoldenNuggetAssessment apiFetch={apiFetch} accessCode={accessCode} />

      <details className="monitoring-technical golden-secondary-data">
        <summary>Live monitoring sources and legacy single-period import</summary>
        <div>
      <ol className="data-onboarding-steps" aria-label="Monitoring setup">
        <li className={model.hasAnalysis ? "is-complete" : "is-current"}><span>1</span><div><strong>Connect or import data</strong><small>Historical or live telemetry</small></div></li>
        <li className={model.hasAnalysis ? "is-complete" : ""}><span>2</span><div><strong>Learn normal behavior</strong><small>Comparable relationship baseline</small></div></li>
        <li className={model.hasAnalysis ? "is-current" : ""}><span>3</span><div><strong>Begin monitoring</strong><small>Quiet until meaningful change</small></div></li>
      </ol>

      <section className="data-summary-grid">
        <article><span>Live data</span><strong>{liveOps?.connectionTone === "degraded" ? "Disconnected" : connections.some((connection) => sourceStatus(connection) === "Connected") ? "Connected" : "Not configured"}</strong><small>{liveOps?.dataFreshness?.label ?? "No live update"}</small></article>
        <article><span>Historical dataset</span><strong>{result?.filename ?? snapshot?.last_filename ?? "Not imported"}</strong><small>{result?.row_count ?? snapshot?.rows_processed ?? 0} rows available</small></article>
        <article><span>Signal mapping</span><strong>{model.nodes.length ? `${model.nodes.length} signals mapped` : "Not ready"}</strong><small>{model.relationships.length} learned relationships</small></article>
        <article><span>Data quality</span><strong>{qualityWarnings.length ? "Limited" : model.hasAnalysis ? "Ready" : "Not assessed"}</strong><small>{qualityWarnings.length ? displayCount(qualityWarnings.length, "quality notice") : "No active data-quality notice"}</small></article>
      </section>

      {connectionsState === "error" ? <div className="monitoring-notice" role="alert"><strong>Connection status unavailable</strong><span>Existing data and findings remain available.</span></div> : null}
      <section className="data-connections-list" aria-labelledby="connections-title">
        <div className="data-section-heading"><div><p className="monitoring-eyebrow">Live sources</p><h2 id="connections-title">Connections</h2><span>Read-only historian, BAS, SCADA, database, and telemetry sources.</span></div></div>
        {connections.length ? connections.map((connection) => (
          <article key={connection.connection_id}>
            <div><strong>{connection.name}</strong><span>{connection.source_type?.replace(/_/g, " ")}</span></div>
            <span className={`source-status source-status--${statusTone(sourceStatus(connection))}`}><i aria-hidden="true" />{sourceStatus(connection)}</span>
            <dl><div><dt>Last success</dt><dd>{formatDateTime(connection.last_success_at)}</dd></div><div><dt>Latest data</dt><dd>{formatDateTime(connection.latest_telemetry_timestamp)}</dd></div><div><dt>Signals</dt><dd>{connection.sensors_detected ?? 0}</dd></div><div><dt>Baseline</dt><dd>{connection.baseline_status?.replace(/_/g, " ") || "Not started"}</dd></div></dl>
            {connection.error_message ? <p role="alert">{connection.error_message}</p> : null}
            <div className="data-connection-actions">
              <button type="button" className="monitoring-button monitoring-button--quiet" disabled={Boolean(connectionBusy)} onClick={() => runConnectionAction(connection, "test")}>{connectionBusy === `${connection.connection_id}:test` ? "Testing…" : "Test"}</button>
              <button type="button" className="monitoring-button monitoring-button--quiet" disabled={Boolean(connectionBusy)} onClick={() => runConnectionAction(connection, "poll-once")}>{connectionBusy === `${connection.connection_id}:poll-once` ? "Checking…" : "Check now"}</button>
              {currentUser?.role === "admin" ? <button type="button" className="monitoring-button monitoring-button--quiet" disabled={Boolean(connectionBusy)} onClick={() => runConnectionAction(connection, connection.polling_enabled ? "stop" : "start")}>{connection.polling_enabled ? "Stop live monitoring" : "Start live monitoring"}</button> : null}
            </div>
          </article>
        )) : <div className="monitoring-empty monitoring-empty--connection"><h3>No live source configured.</h3><p>Historical import remains available below.</p></div>}
        {currentUser?.role === "admin" ? <details className="monitoring-technical data-connection-setup"><summary>Add a live connection</summary><form onSubmit={saveConnection}><label><span>Name</span><input required value={connectionForm.name} onChange={(event) => setConnectionForm((current) => ({ ...current, name: event.target.value }))} /></label><label><span>Read-only endpoint</span><input required type="url" placeholder="https://telemetry.example/api/readings" value={connectionForm.url} onChange={(event) => setConnectionForm((current) => ({ ...current, url: event.target.value }))} /></label><label><span>Facility ID</span><input value={connectionForm.facilityId} onChange={(event) => setConnectionForm((current) => ({ ...current, facilityId: event.target.value }))} /></label><label><span>Polling interval (seconds)</span><input type="number" min="1" value={connectionForm.pollingSeconds} onChange={(event) => setConnectionForm((current) => ({ ...current, pollingSeconds: event.target.value }))} /></label><button type="submit" className="monitoring-button monitoring-button--primary" disabled={Boolean(connectionBusy)}>{connectionBusy === "create" ? "Saving…" : "Save connection"}</button></form></details> : null}
        {connectionNotice ? <p className="data-connection-notice" role="status">{connectionNotice}</p> : null}
        {connectionError ? <p className="data-connection-error" role="alert">{connectionError}</p> : null}
      </section>

      <section className="data-import-section" aria-labelledby="historical-import-title">
        <div className="data-section-heading"><div><p className="monitoring-eyebrow">Historical data</p><h2 id="historical-import-title">Import a dataset</h2><span>Use timestamped CSV telemetry to establish or refresh the learned baseline.</span></div></div>
        <DataConnectionsWorkspace
          accessCode={accessCode}
          apiFetch={apiFetch}
          onUploadComplete={onUploadComplete}
          initialSelectedFiles={pendingUploadFiles}
          onInitialSelectedFilesConsumed={() => setPendingUploadFiles([])}
          autoStartInitialFiles={pendingUploadFiles.length > 0}
        />
      </section>
        </div>
      </details>

      {currentUser?.role === "admin" ? <details className="monitoring-technical data-diagnostics"><summary>Connection diagnostics</summary><p>Connector configuration and service diagnostics remain available to administrators through the existing protected APIs.</p></details> : null}
    </div>
  );
}

export default function MonitoringWorkspace({
  activeWorkspace = "status",
  accessCode,
  apiFetch,
  liveOps = {},
  currentSession,
  canonicalFinding,
  gateProcessing,
  effectiveLatestUploadResult,
  effectiveLatestUploadSnapshot,
  domainDetection,
  onWorkspaceNavigate,
  onSignOut,
  signOutPending = false,
  currentUser,
  onUploadComplete,
  pendingUploadFiles = [],
  setPendingUploadFiles = () => {},
}) {
  const [route, setRoute] = useState(routeFromLocation);
  const [selectedFindingId, setSelectedFindingId] = useState(findingIdFromLocation);
  const [evidenceRuns, setEvidenceRuns] = useState([]);
  const [historyState, setHistoryState] = useState("loading");
  const [connections, setConnections] = useState([]);
  const [connectionsState, setConnectionsState] = useState("loading");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [acknowledgedIds, setAcknowledgedIds] = useState(() => readAcknowledged(currentUser));

  const result = effectiveLatestUploadResult ?? liveOps?.latestUploadResult ?? currentSession?.latestUploadResult ?? null;
  const snapshot = effectiveLatestUploadSnapshot ?? liveOps?.latestUploadSnapshot ?? null;
  const model = useMemo(() => buildEngineeringReasoningModel({
    liveOps,
    canonicalFinding,
    currentSession,
    result,
    snapshot,
    domainDetection,
  }), [canonicalFinding, currentSession, domainDetection, liveOps, result, snapshot]);
  const currentFindings = useMemo(() => normalizeCurrentFindings(model), [model]);
  const persistedFindings = useMemo(() => evidenceRuns.map(normalizePersistedFinding).filter(Boolean), [evidenceRuns]);
  const findings = useMemo(() => mergeFindings(currentFindings, persistedFindings), [currentFindings, persistedFindings]);
  const activeFindings = findings.filter((finding) => finding.state === "active");
  const selectedFinding = findings.find((finding) => String(finding.id) === String(selectedFindingId) || String(finding.runId) === String(selectedFindingId)) ?? null;
  const systems = useMemo(() => buildSystemRows({
    systems: liveOps?.systems ?? model.subsystems,
    findings,
    relationships: model.relationships,
    coverage: model.coverage,
    freshness: liveOps?.dataFreshness,
  }), [findings, liveOps?.dataFreshness, liveOps?.systems, model.coverage, model.relationships, model.subsystems]);

  useEffect(() => {
    const next = activeWorkspace === "system-body" ? "status" : activeWorkspace === "data-connections" ? "data" : routeFromLocation();
    setRoute(next === "evidence" ? "evidence" : next);
    setSelectedFindingId(findingIdFromLocation());
  }, [activeWorkspace]);

  useEffect(() => {
    const onPopState = () => {
      setRoute(routeFromLocation());
      setSelectedFindingId(findingIdFromLocation());
      setMobileNavOpen(false);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setHistoryState("loading");
    Promise.resolve(apiFetch?.("/api/evidence/runs?limit=100", { accessCode, cache: "no-store" }))
      .then(async (response) => {
        const payload = await responseJson(response);
        if (!response?.ok) throw new Error("Evidence history unavailable");
        if (!cancelled) {
          setEvidenceRuns(Array.isArray(payload.runs) ? payload.runs : []);
          setHistoryState("ready");
        }
      })
      .catch(() => { if (!cancelled) setHistoryState("error"); });
    return () => { cancelled = true; };
  }, [accessCode, apiFetch, result?.job_id, result?.run_id]);

  useEffect(() => {
    let cancelled = false;
    setConnectionsState("loading");
    Promise.resolve(apiFetch?.("/api/data-connections", { accessCode, cache: "no-store" }))
      .then(async (response) => {
        const payload = await responseJson(response);
        if (!response?.ok) throw new Error("Connection status unavailable");
        if (!cancelled) {
          setConnections(Array.isArray(payload.connections) ? payload.connections : []);
          setConnectionsState("ready");
        }
      })
      .catch(() => { if (!cancelled) setConnectionsState("error"); });
    return () => { cancelled = true; };
  }, [accessCode, apiFetch, result?.job_id, result?.run_id]);

  function navigate(target) {
    setMobileNavOpen(false);
    setSelectedFindingId("");
    setRoute(target);
    onWorkspaceNavigate?.(target);
    if (!onWorkspaceNavigate && typeof window !== "undefined") window.history.pushState({}, "", ROUTE_PATHS[target] ?? "/status");
  }

  function openEvidence(finding) {
    if (!finding) return;
    setSelectedFindingId(String(finding.id));
    setRoute("evidence");
    const path = `/findings/${encodeURIComponent(finding.id)}`;
    if (typeof window !== "undefined" && window.location.pathname !== path) window.history.pushState({}, "", path);
  }

  function acknowledge(finding) {
    const id = String(finding?.id ?? "");
    if (!id) return;
    const next = acknowledgedIds.includes(id) ? acknowledgedIds.filter((value) => value !== id) : [...acknowledgedIds, id];
    setAcknowledgedIds(next);
    writeAcknowledged(currentUser, next);
  }

  const navRoute = route === "evidence" ? "findings" : route;
  return (
    <div className="monitoring-shell" data-testid="monitoring-workspace">
      <SkipToMainContent targetId="monitoring-main" />
      <aside className={`monitoring-sidebar${mobileNavOpen ? " is-open" : ""}`} aria-label="Application navigation">
        <div className="monitoring-brand"><span aria-hidden="true">N</span><div><strong>Neraium</strong><small>Relationship monitoring</small></div></div>
        <nav aria-label="Primary navigation">
          {PRIMARY_NAV.map((item) => <button key={item.id} type="button" className={navRoute === item.id ? "is-active" : ""} aria-current={navRoute === item.id ? "page" : undefined} onClick={() => navigate(item.id)}><i aria-hidden="true" className={`monitoring-nav-icon monitoring-nav-icon--${item.id}`} />{item.label}{item.id === "findings" && activeFindings.length ? <span>{activeFindings.length}</span> : null}</button>)}
        </nav>
        <div className="monitoring-account">
          <strong>{currentUser?.name || currentUser?.email || "Signed in"}</strong>
          <span>{currentUser?.role || "operator"}</span>
          {onSignOut ? <button type="button" onClick={onSignOut} disabled={signOutPending}>{signOutPending ? "Signing out…" : "Sign out"}</button> : null}
        </div>
      </aside>
      <div className="monitoring-app">
        <header className="monitoring-topbar">
          <button type="button" className="monitoring-menu-button" aria-label={mobileNavOpen ? "Close menu" : "Open menu"} aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen((current) => !current)}><i aria-hidden="true" /></button>
          <div><span className={`monitoring-live-dot monitoring-live-dot--${activeFindings.length ? "change" : liveOps?.connectionTone === "degraded" ? "degraded" : "quiet"}`} aria-hidden="true" /><strong>{activeFindings.length ? displayCount(activeFindings.length, "active change") : "Monitoring"}</strong></div>
          <span>{model.site.name}</span>
        </header>
        <main id="monitoring-main" tabIndex={-1}>
          {historyState === "error" && route === "findings" ? <div className="monitoring-notice" role="status"><strong>Historical findings unavailable</strong><span>Current monitoring remains available.</span></div> : null}
          {route === "findings" ? <FindingsPage findings={findings} acknowledgedIds={acknowledgedIds} onAcknowledge={acknowledge} onEvidence={openEvidence} />
            : route === "evidence" ? <EvidencePage finding={selectedFinding} onBack={() => navigate("findings")} />
              : route === "systems" ? <SystemsPage systems={systems} />
                : route === "data" ? <DataPage accessCode={accessCode} apiFetch={apiFetch} currentUser={currentUser} connections={connections} setConnections={setConnections} connectionsState={connectionsState} result={result} snapshot={snapshot} model={model} liveOps={liveOps} onUploadComplete={onUploadComplete} pendingUploadFiles={pendingUploadFiles} setPendingUploadFiles={setPendingUploadFiles} />
                  : <StatusPage activeFindings={activeFindings} acknowledgedIds={acknowledgedIds} model={model} liveOps={liveOps} result={result} snapshot={snapshot} gateProcessing={gateProcessing} onAcknowledge={acknowledge} onEvidence={openEvidence} onNavigate={navigate} />}
        </main>
      </div>
    </div>
  );
}
