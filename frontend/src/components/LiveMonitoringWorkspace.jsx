import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import useStableInterval from "../hooks/useStableInterval";
import { fetchLiveMonitoringSnapshot } from "../services/api/liveMonitoringApi";
import "../styles/engineering-reasoning.css";
import "../styles/live-monitoring.css";
import EvidenceDrawer from "./engineering/EvidenceDrawer";
import ReadOnlyIndicator from "./engineering/ReadOnlyIndicator";
import WorkspaceLoadingState from "./WorkspaceLoadingState";

export const LIVE_MONITORING_POLL_INTERVAL_MS = 30_000;

const DATE_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const ERROR_LABELS = {
  configurations: "System configurations",
  ingestionHealth: "Telemetry health",
  analysisHealth: "Analysis health",
  runs: "Analysis runs",
  findings: "Live findings",
};

function hasOwn(object, key) {
  return Object.prototype.hasOwnProperty.call(object ?? {}, key);
}

function formatTimestamp(value, fallback = "Unavailable") {
  if (!value) return fallback;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? fallback : DATE_FORMATTER.format(parsed);
}

function sentenceCase(value, fallback = "Unavailable") {
  const text = String(value ?? "").trim();
  if (!text) return fallback;
  return text.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusClass(value) {
  return String(value || "unavailable").toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function StatusBadge({ value, label = null }) {
  return <span className={`live-status live-status--${statusClass(value)}`}>{label ?? sentenceCase(value)}</span>;
}

function formatCoverage(health) {
  if (!health || !Number.isFinite(Number(health.current_window_coverage))) return "Unavailable";
  if (["never_run", "missing_baseline", "disabled"].includes(health.current_status) && Number(health.current_window_coverage) === 0) {
    return "Unavailable";
  }
  return `${Number(health.current_window_coverage).toFixed(1)}%`;
}

function formatRunCoverage(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)}%` : "Unavailable";
}

function formatScore(value) {
  if (!Number.isFinite(Number(value))) return null;
  return Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function persistenceText(state) {
  if (!state || typeof state !== "object") return "Unavailable";
  const parts = [];
  if (typeof state.persistent === "boolean") parts.push(`Persistent: ${state.persistent ? "Yes" : "No"}`);
  if (Number.isFinite(Number(state.support_fraction))) {
    parts.push(`Support: ${(Number(state.support_fraction) * 100).toFixed(0)}%`);
  }
  if (state.status) parts.push(sentenceCase(state.status));
  return parts.length ? parts.join(" · ") : "Unavailable";
}

function findingTitle(finding) {
  return String(
    finding?.finding_classification?.label
      ?? finding?.finding_classification?.type
      ?? finding?.relationship_identity
      ?? "",
  ).trim() || "Classification unavailable";
}

function telemetrySummary(configurations, health, unavailable) {
  if (unavailable) return { value: "Unavailable", detail: "Health endpoint unavailable" };
  if (!configurations.length && !health.length) return { value: "Unavailable", detail: "No systems configured" };
  if (!health.length) return { value: "Waiting", detail: "Waiting for telemetry" };
  const counts = health.reduce((result, item) => ({
    ...result,
    [item.status]: (result[item.status] ?? 0) + 1,
  }), {});
  if (counts.error) return { value: `${counts.error} error`, detail: `${health.length} source${health.length === 1 ? "" : "s"}` };
  if (counts.delayed) return { value: `${counts.delayed} delayed`, detail: `${health.length} source${health.length === 1 ? "" : "s"}` };
  if (counts.never_received) return { value: "Waiting", detail: "Waiting for telemetry" };
  return { value: "Healthy", detail: `${health.length} source${health.length === 1 ? "" : "s"}` };
}

function analysisSummary(configurations, health, unavailable) {
  if (unavailable) return { value: "Unavailable", detail: "Health endpoint unavailable" };
  if (!configurations.length) return { value: "Unavailable", detail: "No systems configured" };
  if (!health.length) return { value: "Never run", detail: "No analysis health recorded" };
  const unhealthy = health.filter((item) => item.current_status !== "healthy");
  if (!unhealthy.length) return { value: "Healthy", detail: `${health.length} system${health.length === 1 ? "" : "s"}` };
  if (unhealthy.length === 1) return { value: sentenceCase(unhealthy[0].current_status), detail: unhealthy[0].system_id };
  return { value: `${unhealthy.length} need review`, detail: `${health.length} systems` };
}

function SummaryCard({ label, value, detail, tone = "neutral" }) {
  return (
    <article className={`live-summary-card live-summary-card--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function EmptyState({ title, body }) {
  return <div className="live-empty" role="status"><span aria-hidden="true" /><strong>{title}</strong><p>{body}</p></div>;
}

function Panel({ title, subtitle, className = "", children }) {
  return (
    <section className={`live-panel ${className}`.trim()}>
      <header><div><h2>{title}</h2>{subtitle ? <p>{subtitle}</p> : null}</div></header>
      <div className="live-panel__body">{children}</div>
    </section>
  );
}

function latestIssue(health, configuration) {
  return health?.latest_error
    ?? health?.latest_skipped_reason
    ?? configuration?.latest_error
    ?? null;
}

function SystemStatusList({ configurations, ingestionHealth, analysisHealth, configurationUnavailable, ingestionUnavailable, analysisUnavailable }) {
  const telemetryBySystem = useMemo(() => {
    const grouped = new Map();
    ingestionHealth.forEach((item) => grouped.set(item.system_id, [...(grouped.get(item.system_id) ?? []), item]));
    return grouped;
  }, [ingestionHealth]);
  const analysisBySystem = useMemo(() => new Map(analysisHealth.map((item) => [item.system_id, item])), [analysisHealth]);

  if (configurationUnavailable) {
    return <EmptyState title="System configurations unavailable" body="Other available monitoring data remains visible below." />;
  }
  if (!configurations.length) {
    return <EmptyState title="No systems configured" body="Live Monitoring will remain empty until a backend configuration is added." />;
  }

  return (
    <div className="live-system-list">
      {configurations.map((configuration) => {
        const telemetry = telemetryBySystem.get(configuration.system_id) ?? [];
        const analysis = analysisBySystem.get(configuration.system_id) ?? null;
        const issue = latestIssue(analysis, configuration);
        return (
          <article className="live-system-card" key={configuration.system_id}>
            <div className="live-system-card__heading">
              <div><h3>{configuration.system_id}</h3><span>{configuration.enabled ? "Monitoring enabled" : "Monitoring disabled"}</span></div>
              <StatusBadge value={configuration.enabled ? "enabled" : "disabled"} />
            </div>
            <dl className="live-definition-grid">
              <div><dt>Telemetry</dt><dd>{ingestionUnavailable ? "Unavailable" : telemetry.length ? <span className="live-badge-list">{telemetry.map((item) => <StatusBadge key={`${item.system_id}-${item.source}`} value={item.status} label={`${item.source}: ${sentenceCase(item.status)}`} />)}</span> : "Waiting for telemetry"}</dd></div>
              <div><dt>Analysis</dt><dd>{analysisUnavailable ? "Unavailable" : analysis ? <StatusBadge value={analysis.current_status} /> : "Never run"}</dd></div>
              <div><dt>Last successful analysis</dt><dd>{analysisUnavailable ? "Unavailable" : formatTimestamp(analysis?.last_successful_run_at, "Never run")}</dd></div>
              <div><dt>Next scheduled analysis</dt><dd>{formatTimestamp(analysis?.next_scheduled_run ?? configuration.next_analysis_at)}</dd></div>
              <div><dt>Window coverage</dt><dd>{analysisUnavailable ? "Unavailable" : formatCoverage(analysis)}</dd></div>
              <div><dt>Approved baseline</dt><dd>{configuration.approved_baseline_id || "Unavailable"}</dd></div>
            </dl>
            {issue ? <p className="live-system-card__issue"><strong>Latest status detail:</strong> {sentenceCase(issue)}</p> : null}
          </article>
        );
      })}
    </div>
  );
}

function FindingCard({ finding, onEvidence }) {
  const score = formatScore(finding.severity_score);
  const hasEvidence = finding.latest_evidence && typeof finding.latest_evidence === "object" && Object.keys(finding.latest_evidence).length > 0;
  return (
    <article className="live-finding-card">
      <div className="live-finding-card__heading">
        <div><h3>{findingTitle(finding)}</h3><span>{finding.system_id || "System unavailable"}</span></div>
        <StatusBadge value={finding.current_state} label={finding.current_state === "open" ? "Active" : sentenceCase(finding.current_state)} />
      </div>
      <dl className="live-definition-grid live-definition-grid--finding">
        <div><dt>First detected</dt><dd>{formatTimestamp(finding.first_detected_at)}</dd></div>
        <div><dt>Last observed</dt><dd>{formatTimestamp(finding.last_observed_at)}</dd></div>
        <div><dt>Persistence</dt><dd>{persistenceText(finding.persistence_state)}</dd></div>
        {score !== null ? <div><dt>Severity score</dt><dd>{score}</dd></div> : null}
      </dl>
      {hasEvidence ? <button type="button" className="live-evidence-button" onClick={() => onEvidence(finding)}>View evidence</button> : <span className="live-evidence-unavailable">Evidence unavailable</span>}
    </article>
  );
}

function FindingPanel({ title, subtitle, findings, emptyTitle, emptyBody, unavailable, onEvidence }) {
  return (
    <Panel title={title} subtitle={subtitle}>
      {unavailable ? <EmptyState title="Findings unavailable" body="Finding data could not be loaded in this refresh." />
        : findings.length ? <div className="live-finding-list">{findings.map((finding) => <FindingCard key={finding.finding_id} finding={finding} onEvidence={onEvidence} />)}</div>
          : <EmptyState title={emptyTitle} body={emptyBody} />}
    </Panel>
  );
}

function TelemetryHealthList({ health, unavailable, hasSystems }) {
  if (unavailable) return <EmptyState title="Telemetry health unavailable" body="Physical findings remain separate and are not inferred from this state." />;
  if (!health.length) return <EmptyState title={hasSystems ? "Waiting for telemetry" : "Unavailable"} body={hasSystems ? "No telemetry source has reported ingestion health yet." : "No configured system or telemetry health is available."} />;
  return <div className="live-health-list">{health.map((item) => <article key={`${item.system_id}-${item.source}`}><div><strong>{item.system_id}</strong><StatusBadge value={item.status} /></div><span>{item.source}</span><dl><div><dt>Last telemetry</dt><dd>{formatTimestamp(item.last_telemetry_timestamp)}</dd></div><div><dt>Last ingestion</dt><dd>{formatTimestamp(item.last_successful_ingestion_at, "Never received")}</dd></div><div><dt>Accepted / rejected</dt><dd>{item.accepted_count} / {item.rejected_count}</dd></div>{item.latest_error_or_warning ? <div><dt>Latest status detail</dt><dd>{sentenceCase(item.latest_error_or_warning)}</dd></div> : null}</dl></article>)}</div>;
}

function AnalysisHealthList({ health, unavailable, hasSystems }) {
  if (unavailable) return <EmptyState title="Analysis health unavailable" body="No equipment state is inferred from this service condition." />;
  if (!health.length) return <EmptyState title={hasSystems ? "Never run" : "Unavailable"} body={hasSystems ? "No live-analysis health record is available yet." : "No configured system or analysis health is available."} />;
  return <div className="live-health-list">{health.map((item) => {
    const issue = item.latest_error ?? item.latest_skipped_reason;
    return <article key={item.system_id}><div><strong>{item.system_id}</strong><StatusBadge value={item.current_status} /></div><dl><div><dt>Last successful</dt><dd>{formatTimestamp(item.last_successful_run_at, "Never run")}</dd></div><div><dt>Next scheduled</dt><dd>{formatTimestamp(item.next_scheduled_run)}</dd></div><div><dt>Window coverage</dt><dd>{formatCoverage(item)}</dd></div><div><dt>Consecutive failures</dt><dd>{item.consecutive_failures}</dd></div>{issue ? <div><dt>Latest status detail</dt><dd>{sentenceCase(issue)}</dd></div> : null}</dl></article>;
  })}</div>;
}

function RunList({ runs, unavailable }) {
  if (unavailable) return <EmptyState title="Analysis runs unavailable" body="Run history could not be loaded in this refresh." />;
  if (!runs.length) return <EmptyState title="Never run" body="No rolling live-analysis run has been recorded." />;
  return (
    <div className="live-run-list">
      {runs.slice(0, 12).map((run) => {
        const issue = run.error_summary ?? run.skipped_reason;
        return (
          <article key={run.run_id}>
            <div className="live-run-list__heading"><div><strong>{run.system_id}</strong><span>{formatTimestamp(run.completed_at ?? run.started_at ?? run.created_at)}</span></div><StatusBadge value={run.status} /></div>
            <dl>
              <div><dt>Analysis window</dt><dd>{formatTimestamp(run.window_start)} – {formatTimestamp(run.window_end)}</dd></div>
              <div><dt>Coverage</dt><dd>{formatRunCoverage(run.coverage)}</dd></div>
              <div><dt>Rows / signals</dt><dd>{run.rows_analyzed} / {run.signals_analyzed}</dd></div>
              <div><dt>Finding changes</dt><dd>{run.created_findings_count} created · {run.updated_findings_count} updated · {run.resolved_findings_count} resolved</dd></div>
              {issue ? <div><dt>{run.status === "failed" ? "Error" : "Skipped reason"}</dt><dd>{sentenceCase(issue)}</dd></div> : null}
            </dl>
          </article>
        );
      })}
    </div>
  );
}

function exactTextList(values) {
  return Array.isArray(values) ? values.map((value) => String(value ?? "").trim()).filter(Boolean) : [];
}

function evidenceDrawerFinding(finding) {
  const evidence = finding.latest_evidence ?? {};
  const classification = finding.finding_classification ?? {};
  const tier = ["Confirmed", "Qualified", "Narrowed", "Deferred", "Withheld"].includes(classification.confidence_tier)
    ? classification.confidence_tier
    : null;
  return {
    id: finding.finding_id,
    title: findingTitle(finding),
    tier,
    supporting: exactTextList(evidence.evidence_summary ?? evidence.condition?.supporting_evidence),
    contradictions: [],
    limitations: [...exactTextList(evidence.data_conditions), ...exactTextList(evidence.warnings)],
    observedChange: exactTextList(evidence.evidence_summary)[0] ?? "",
    whyItMatters: String(evidence.potential_impact ?? classification.certainty_limit ?? "").trim(),
  };
}

function evidenceDrawerRelationship(finding) {
  return {
    label: finding.relationship_identity || "Relationship unavailable",
    delta: Number.isFinite(Number(finding.latest_evidence?.drift_metrics?.coupling_delta))
      ? Number(finding.latest_evidence.drift_metrics.coupling_delta)
      : null,
    state: finding.finding_classification?.type ?? null,
    baseline: null,
    current: null,
  };
}

export default function LiveMonitoringWorkspace({ apiFetch, accessCode = "", datasetScopeKey = "anonymous" }) {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState("");
  const [selectedFinding, setSelectedFinding] = useState(null);
  const [pageVisible, setPageVisible] = useState(() => typeof document === "undefined" || document.visibilityState !== "hidden");
  const mountedRef = useRef(false);
  const requestRef = useRef(null);
  const snapshotRef = useRef(null);
  const scopeRef = useRef(datasetScopeKey);
  scopeRef.current = datasetScopeKey;

  const load = useCallback(async ({ manual = false } = {}) => {
    const requestScope = datasetScopeKey;
    if (requestRef.current?.scope === requestScope) return requestRef.current.request;
    if (manual) setRefreshing(true);
    const request = fetchLiveMonitoringSnapshot({ apiFetch, accessCode });
    requestRef.current = { scope: requestScope, request };
    try {
      const next = await request;
      if (!mountedRef.current || scopeRef.current !== requestScope) return next;
      if (next.status === "error" && snapshotRef.current) {
        setRefreshNotice("Refresh failed. Previously loaded data remains visible.");
      } else {
        snapshotRef.current = next;
        setSnapshot(next);
        setRefreshNotice("");
      }
      return next;
    } catch {
      if (mountedRef.current && scopeRef.current === requestScope) setRefreshNotice("Refresh failed. Retry when the service is available.");
      return null;
    } finally {
      if (requestRef.current?.request === request) requestRef.current = null;
      if (mountedRef.current && scopeRef.current === requestScope) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [accessCode, apiFetch, datasetScopeKey]);

  useEffect(() => {
    mountedRef.current = true;
    void load();
    return () => { mountedRef.current = false; };
  }, [load]);

  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const handleVisibility = () => {
      const visible = document.visibilityState !== "hidden";
      setPageVisible(visible);
      if (visible) void load();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [load]);

  useStableInterval(() => { void load(); }, LIVE_MONITORING_POLL_INTERVAL_MS, pageVisible);

  const configurations = snapshot?.configurations ?? [];
  const ingestionHealth = snapshot?.ingestionHealth ?? [];
  const analysisHealth = snapshot?.analysisHealth ?? [];
  const findings = snapshot?.findings ?? [];
  const runs = snapshot?.runs ?? [];
  const activeFindings = findings.filter((finding) => finding.current_state === "open");
  const observingFindings = findings.filter((finding) => finding.current_state === "observing");
  const resolvedFindings = findings.filter((finding) => finding.current_state === "resolved");
  const configurationUnavailable = hasOwn(snapshot?.errors, "configurations");
  const findingsUnavailable = hasOwn(snapshot?.errors, "findings");
  const telemetryUnavailable = hasOwn(snapshot?.errors, "ingestionHealth");
  const analysisUnavailable = hasOwn(snapshot?.errors, "analysisHealth");
  const runsUnavailable = hasOwn(snapshot?.errors, "runs");
  const telemetryState = telemetrySummary(configurations, ingestionHealth, telemetryUnavailable);
  const analysisState = analysisSummary(configurations, analysisHealth, analysisUnavailable);

  if (loading && !snapshot) {
    return <WorkspaceLoadingState label="Opening Live Monitoring" detail="Loading telemetry, rolling analysis, and finding state." />;
  }

  if (snapshot?.status === "unauthorized") {
    return <div className="live-monitoring live-monitoring--centered"><EmptyState title="Live Monitoring access unavailable" body="Your session is not authorized to read this workspace. Sign in again or contact an administrator." /></div>;
  }

  if (snapshot?.status === "error") {
    return <div className="live-monitoring live-monitoring--centered"><EmptyState title="Live Monitoring unavailable" body="The monitoring services could not be reached. Check the network and retry." /><button type="button" className="live-refresh-button" onClick={() => void load({ manual: true })} disabled={refreshing}>{refreshing ? "Refreshing…" : "Retry"}</button></div>;
  }

  const partialErrors = Object.keys(snapshot?.errors ?? {});
  const enabledCount = configurations.filter((item) => item.enabled).length;
  const drawerFinding = selectedFinding ? evidenceDrawerFinding(selectedFinding) : null;
  const drawerRelationship = selectedFinding ? evidenceDrawerRelationship(selectedFinding) : null;

  return (
    <div className="live-monitoring" data-testid="live-monitoring-workspace">
      <header className="live-monitoring__header">
        <div><span className="forensic-kicker">Live operations</span><h1>Live Monitoring</h1><p>Backend-reported telemetry, rolling analysis, and finding state.</p></div>
        <div className="live-monitoring__actions"><ReadOnlyIndicator compact /><button type="button" className="live-refresh-button" onClick={() => void load({ manual: true })} disabled={refreshing}>{refreshing ? "Refreshing…" : "Refresh"}</button><span role="status" aria-live="polite">{refreshNotice || `Updated ${formatTimestamp(snapshot?.refreshedAt)}`}</span></div>
      </header>

      {partialErrors.length ? <div className="live-partial-banner" role="status"><strong>Partial data</strong><span>Unavailable: {partialErrors.map((key) => ERROR_LABELS[key] ?? key).join(", ")}.</span></div> : null}

      <section className="live-summary" aria-label="Live Monitoring summary">
        <SummaryCard label="Systems monitored" value={configurationUnavailable ? "Unavailable" : enabledCount} detail={configurationUnavailable ? "Configuration endpoint unavailable" : `${configurations.length} configured`} tone="blue" />
        <SummaryCard label="Active findings" value={findingsUnavailable ? "Unavailable" : activeFindings.length} detail="Backend state: open" tone={activeFindings.length ? "amber" : "neutral"} />
        <SummaryCard label="Observing" value={findingsUnavailable ? "Unavailable" : observingFindings.length} detail="Persistence under observation" tone={observingFindings.length ? "blue" : "neutral"} />
        <SummaryCard label="Recently resolved" value={findingsUnavailable ? "Unavailable" : resolvedFindings.length} detail="Returned finding history" tone="green" />
        <SummaryCard label="Telemetry health" value={telemetryState.value} detail={telemetryState.detail} tone={telemetryState.value === "Healthy" ? "green" : "neutral"} />
        <SummaryCard label="Analysis health" value={analysisState.value} detail={analysisState.detail} tone={analysisState.value === "Healthy" ? "green" : "neutral"} />
      </section>

      <Panel title="System status" subtitle="Configured live-analysis systems and their backend-reported readiness.">
        <SystemStatusList configurations={configurations} ingestionHealth={ingestionHealth} analysisHealth={analysisHealth} configurationUnavailable={configurationUnavailable} ingestionUnavailable={telemetryUnavailable} analysisUnavailable={analysisUnavailable} />
      </Panel>

      <section className="live-two-column" aria-label="Current live findings">
        <FindingPanel title="Active findings" subtitle="Persistent findings in the open state." findings={activeFindings} emptyTitle="No active findings" emptyBody="No live finding is currently open." unavailable={findingsUnavailable} onEvidence={setSelectedFinding} />
        <FindingPanel title="Observing" subtitle="Findings whose backend persistence state remains observing." findings={observingFindings} emptyTitle="No observing findings" emptyBody="No live finding is currently under observation." unavailable={findingsUnavailable} onEvidence={setSelectedFinding} />
      </section>

      <FindingPanel title="Recently resolved findings" subtitle="Resolved findings returned by the live finding API." findings={resolvedFindings.slice(0, 8)} emptyTitle="No recently resolved findings" emptyBody="No resolved live finding is available." unavailable={findingsUnavailable} onEvidence={setSelectedFinding} />

      <section className="live-health-boundary" aria-labelledby="monitoring-health-title">
        <header><div><span className="forensic-kicker">Service health</span><h2 id="monitoring-health-title">Telemetry and analysis health</h2></div><p>Transport and analysis status only. These states are not equipment findings.</p></header>
        <div className="live-two-column">
          <Panel title="Telemetry ingestion" subtitle="Source delivery, recency, and acceptance state."><TelemetryHealthList health={ingestionHealth} unavailable={telemetryUnavailable} hasSystems={configurations.length > 0} /></Panel>
          <Panel title="Rolling analysis" subtitle="Window readiness, scheduling, skips, and failures."><AnalysisHealthList health={analysisHealth} unavailable={analysisUnavailable} hasSystems={configurations.length > 0} /></Panel>
        </div>
      </section>

      <Panel title="Recent analysis runs" subtitle="Latest backend-recorded rolling windows and outcomes."><RunList runs={runs} unavailable={runsUnavailable} /></Panel>

      {selectedFinding ? <div className="live-evidence-layer"><button type="button" className="live-evidence-scrim" aria-label="Dismiss evidence overlay" onClick={() => setSelectedFinding(null)} /><div className="live-evidence-layer__drawer"><EvidenceDrawer open finding={drawerFinding} relationship={drawerRelationship} result={selectedFinding.latest_evidence} record={selectedFinding.latest_evidence} strictMissingValues onClose={() => setSelectedFinding(null)} /></div></div> : null}
    </div>
  );
}
