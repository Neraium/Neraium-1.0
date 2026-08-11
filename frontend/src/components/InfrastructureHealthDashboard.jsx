import { useEffect, useMemo, useState } from "react";

const SUBSYSTEM_LABELS = {
  api: "API",
  auth: "Authentication",
  runtime_db: "Runtime database",
  workers: "Background workers",
  uploads: "Upload processing",
  notifications: "Notifications",
  storage: "Runtime storage",
  secrets: "Secrets & credentials",
};

function safeText(value, fallback = "Not available") {
  const normalized = String(value ?? "").trim();
  return normalized || fallback;
}

function formatTime(value) {
  const parsed = Date.parse(value || "");
  if (Number.isNaN(parsed)) return "Not recorded";
  return new Date(parsed).toLocaleString();
}

function formatAge(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return "Not recorded";
  const value = Math.max(0, Number(seconds));
  if (value < 120) return `${Math.round(value)} seconds`;
  if (value < 7200) return `${Math.round(value / 60)} minutes`;
  if (value < 172800) return `${Math.round(value / 3600)} hours`;
  return `${Math.round(value / 86400)} days`;
}

function statusLabel(value) {
  const normalized = String(value || "healthy").toLowerCase();
  if (normalized === "critical") return "Critical";
  if (normalized === "degraded") return "Degraded";
  return "Healthy";
}

function StatusBadge({ status }) {
  const normalized = String(status || "healthy").toLowerCase();
  return <span className={`infra-status-badge infra-status-badge--${normalized}`}>{statusLabel(normalized)}</span>;
}

export default function InfrastructureHealthDashboard({ apiFetch, accessCode, Panel }) {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    let activeController = null;

    async function load() {
      activeController?.abort();
      activeController = new AbortController();
      try {
        const response = await apiFetch("/api/infrastructure/health?incident_limit=50", {
          accessCode,
          cache: "no-store",
          signal: activeController.signal,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error("Production infrastructure health could not be loaded.");
        if (mounted) {
          setHealth(payload);
          setError("");
        }
      } catch (loadError) {
        if (loadError?.name !== "AbortError" && mounted) {
          setError("Production infrastructure health could not be loaded. The external AWS alarm path remains active.");
        }
      } finally {
        if (mounted) setLoading(false);
      }
    }

    void load();
    const interval = window.setInterval(load, 30000);
    return () => {
      mounted = false;
      activeController?.abort();
      window.clearInterval(interval);
    };
  }, [accessCode, apiFetch]);

  const metrics = useMemo(() => {
    const subsystems = health?.subsystems || {};
    const secrets = subsystems.secrets?.checks || {};
    const auth = subsystems.auth?.checks || {};
    const runtime = subsystems.runtime_db?.checks || {};
    const workers = subsystems.workers?.checks || {};
    const api = subsystems.api?.checks || {};
    return {
      credentialRefresh: secrets.credential_refresh?.metadata?.last_refresh_success_at,
      secretAge: secrets.secrets_manager_access?.metadata?.age_seconds,
      worker: workers.worker_heartbeat,
      auth: auth.auth_connectivity,
      runtime: runtime.runtime_db_connectivity,
      apiLatency: api.api_latency,
    };
  }, [health]);

  if (loading) {
    return <Panel title="Production Infrastructure" subtitle="Checking persistent platform health and current incidents..."><p role="status">Loading infrastructure health...</p></Panel>;
  }

  if (error && !health) {
    return <Panel title="Production Infrastructure" subtitle="Independent AWS alarms continue monitoring API, ALB, and ECS availability."><p className="auth-error" role="alert">{error}</p></Panel>;
  }

  const currentAlerts = health?.current_alerts || [];
  const incidents = health?.incidents || [];
  const pending = health?.pending_validation || [];
  const isQuiet = health?.overall_status === "healthy" && currentAlerts.length === 0 && pending.length === 0;

  return (
    <section className="infrastructure-health-dashboard" aria-label="Production infrastructure health">
      <Panel
        title="Production Infrastructure"
        subtitle={`Last evaluated ${formatTime(health?.observed_at)} · confidence ${safeText(health?.confidence, "unknown")}`}
      >
        <div className="infra-overall-row">
          <div>
            <span className="metadata-text">Overall health</span>
            <h2>{safeText(health?.category, "Infrastructure status unavailable")}</h2>
          </div>
          <StatusBadge status={health?.overall_status} />
        </div>
        {isQuiet ? <p className="infra-quiet-state">All monitored production subsystems are within their persistence and latency limits.</p> : null}
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        {pending.length ? <p className="infra-validation-note">{pending.length} signal{pending.length === 1 ? " is" : "s are"} being validated for persistence. No alert has been sent yet.</p> : null}
        <div className="infra-subsystem-grid">
          {Object.entries(SUBSYSTEM_LABELS).map(([key, label]) => {
            const subsystem = health?.subsystems?.[key] || {};
            const evidence = subsystem.evidence || [];
            return (
              <article className="infra-subsystem-card" key={key}>
                <div><strong>{label}</strong><StatusBadge status={subsystem.status} /></div>
                <p>{safeText(evidence[0], "No current degradation evidence.")}</p>
              </article>
            );
          })}
        </div>
      </Panel>

      <div className="workspace-grid workspace-grid--two infra-metric-grid">
        <Panel title="Dependency checks" subtitle="Live connectivity and latency evidence">
          <dl className="infra-definition-list">
            <div><dt>Authentication</dt><dd>{statusLabel(metrics.auth?.status)}</dd></div>
            <div><dt>Auth latency</dt><dd>{metrics.auth?.latency_ms != null ? `${Math.round(metrics.auth.latency_ms)} ms` : "Not recorded"}</dd></div>
            <div><dt>Runtime database</dt><dd>{statusLabel(metrics.runtime?.status)}</dd></div>
            <div><dt>API p95 latency</dt><dd>{metrics.apiLatency?.latency_ms != null ? `${Math.round(metrics.apiLatency.latency_ms)} ms` : "No recent traffic"}</dd></div>
          </dl>
        </Panel>
        <Panel title="Worker & credential state" subtitle="Background availability and managed secret freshness">
          <dl className="infra-definition-list">
            <div><dt>Worker heartbeat</dt><dd>{statusLabel(metrics.worker?.status)}</dd></div>
            <div><dt>Heartbeat age</dt><dd>{formatAge(metrics.worker?.metadata?.age_seconds)}</dd></div>
            <div><dt>Last credential refresh</dt><dd>{formatTime(metrics.credentialRefresh)}</dd></div>
            <div><dt>Secrets age</dt><dd>{formatAge(metrics.secretAge)}</dd></div>
          </dl>
        </Panel>
      </div>

      {currentAlerts.length ? (
        <Panel title="Current alerts" subtitle="One notification per unresolved incident; recovery closes the incident.">
          <div className="infra-incident-list">
            {currentAlerts.map((incident) => (
              <article key={incident.incident_id}>
                <div><strong>{incident.category}</strong><StatusBadge status={incident.severity} /></div>
                <p>{safeText(incident.impact)}</p>
                <small>Started {formatTime(incident.started_at)} · {safeText(incident.subsystem)}</small>
                <p><strong>First check:</strong> {safeText(incident.recommended_first_check)}</p>
              </article>
            ))}
          </div>
        </Panel>
      ) : null}

      <Panel title="Incident history" subtitle="Persistent degradations and recovery transitions">
        {incidents.length === 0 ? <p className="infra-quiet-state">No persistent infrastructure incidents have been recorded.</p> : (
          <div className="infra-incident-list">
            {incidents.slice(0, 20).map((incident) => (
              <article key={incident.incident_id}>
                <div><strong>{safeText(incident.category)}</strong><span>{incident.status === "resolved" ? "Recovered" : "Active"}</span></div>
                <p>{safeText(incident.evidence?.[0], incident.impact)}</p>
                <small>Started {formatTime(incident.started_at)}{incident.resolved_at ? ` · recovered ${formatTime(incident.resolved_at)}` : ""}</small>
              </article>
            ))}
          </div>
        )}
      </Panel>
    </section>
  );
}
