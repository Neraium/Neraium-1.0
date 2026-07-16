import { useEffect, useState } from "react";

function safeAdminError(value, fallback) {
  const message = String(value || "").trim();
  if (!message) return fallback;
  if (/(traceback|exception|stack trace|shared_upload|psycopg|sqlite3|errno|file:\/\/|[a-z]:\\)/i.test(message)) return fallback;
  return message;
}

function governanceDecision(value) {
  return String(value || "").toUpperCase() === "PASS" ? "Approved for operator review" : "Held for administrator review";
}

export default function GovernanceAdminWorkspace({
  apiFetch,
  accessCode,
  Panel,
  EmptyState,
  onBackToGate = null,
  currentUser = null,
}) {
  const [payload, setPayload] = useState(null);
  const [performance, setPerformance] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        setLoading(true);
        setError("");
        const [governanceResponse, performanceResponse] = await Promise.all([
          apiFetch("/api/observability/evp-governance?limit=200", { accessCode }),
          apiFetch("/api/observability/performance?window=200", { accessCode }),
        ]);
        const data = await governanceResponse.json().catch(() => ({}));
        if (!governanceResponse.ok) {
          throw new Error(safeAdminError(data?.detail, "Governance records could not be loaded. Refresh the page and retry."));
        }
        const perf = await performanceResponse.json().catch(() => ({}));
        if (!mounted) return;
        setPayload(data);
        setPerformance(perf);
      } catch (err) {
        if (!mounted) return;
        setError(safeAdminError(err?.message ?? err, "Administration data could not be loaded. Refresh the page and retry."));
      } finally {
        if (mounted) setLoading(false);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, [accessCode, apiFetch]);

  const backControl = (
    <button
      type="button"
      className="system-gate__settings-action"
      onClick={() => {
        if (typeof onBackToGate === "function") {
          onBackToGate();
        }
      }}
      style={{
        position: "sticky",
        top: "max(10px, env(safe-area-inset-top, 0px))",
        left: 0,
        zIndex: 40,
        width: "fit-content",
        marginBottom: "10px",
        paddingInline: "12px",
      }}
      aria-label="Back to Command Center"
    >
      Back to Command Center
    </button>
  );

  if (loading) {
    return (
      <section className="workspace-surface">
        {backControl}
        <Panel title="Intelligence Governance" subtitle="Loading SII evidence review records..." />
      </section>
    );
  }

  if (error) {
    return (
      <section className="workspace-surface">
        {backControl}
        <EmptyState title="Intelligence Governance Unavailable" body={error} />
      </section>
    );
  }

  const rows = (payload?.records ?? []).slice(0, 100);
  return (
    <section className="workspace-surface">
      {backControl}
      <Panel
        title="Intelligence Governance"
        subtitle="Administrator audit records for decisions about which SII evidence can appear in operator workspaces."
      >
        <div className="metric-grid">
          <article className="metric-card"><span className="metric-label">Decision records</span><strong className="metric-value">{payload?.total ?? 0}</strong></article>
          <article className="metric-card"><span className="metric-label">Approved for operator review</span><strong className="metric-value">{payload?.pass_count ?? 0}</strong></article>
          <article className="metric-card"><span className="metric-label">Held for administrator review</span><strong className="metric-value">{payload?.no_pass_count ?? 0}</strong></article>
        </div>
      </Panel>
      <Panel title="Analysis Service Performance" subtitle="Recent analysis timing and queue status">
        <div className="metric-grid">
          <article className="metric-card"><span className="metric-label">Queued analyses</span><strong className="metric-value">{performance?.queue_depth ?? 0}</strong></article>
          <article className="metric-card"><span className="metric-label">Median analysis time (s)</span><strong className="metric-value">{performance?.upload_duration_seconds?.p50 ?? "-"}</strong></article>
          <article className="metric-card"><span className="metric-label">95th percentile analysis time (s)</span><strong className="metric-value">{performance?.upload_duration_seconds?.p95 ?? "-"}</strong></article>
          <article className="metric-card"><span className="metric-label">Result reuse rate</span><strong className="metric-value">{performance?.cache?.hash_cache_hit_rate != null ? `${Math.round(performance.cache.hash_cache_hit_rate * 100)}%` : "-"}</strong></article>
        </div>
      </Panel>

      <AccessAdminPanel apiFetch={apiFetch} accessCode={accessCode} Panel={Panel} currentUser={currentUser} />

      <div className="workspace-grid workspace-grid--two">
        {rows.map((record) => (
          <Panel
            key={record.evp_id}
            title={`${governanceDecision(record.gate_outcome)}: ${record.affected_subsystem || "Evidence record"}`}
            subtitle={record.timestamp_utc}
          >
            <ul className="compact-list">
              <li><span className="metadata-text">Governance policy</span><strong>{record.doctrine_version}</strong></li>
              <li><span className="metadata-text">Decision reasons</span><strong>{(record.decision_reason_codes ?? []).join(", ") || "-"}</strong></li>
              <li><span className="metadata-text">Evidence record hash</span><strong>{record.evp_hash}</strong></li>
              <li><span className="metadata-text">Previous record hash</span><strong>{record.previous_evp_hash || "-"}</strong></li>
              <li><span className="metadata-text">Visible to operators</span><strong>{String(Boolean(record.operator_visible))}</strong></li>
            </ul>
          </Panel>
        ))}
      </div>
    </section>
  );
}


function AccessAdminPanel({ apiFetch, accessCode, Panel, currentUser }) {
  const [users, setUsers] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState({ email: "", name: "", password: "", role: "operator" });

  async function read(response) { try { return await response.json(); } catch { return {}; } }
  async function loadAccess() {
    setLoading(true); setError("");
    try {
      const [userResponse, sessionResponse] = await Promise.all([
        apiFetch("/api/auth/users?include_inactive=true", { accessCode, cache: "no-store" }),
        apiFetch("/api/auth/sessions?include_revoked=false", { accessCode, cache: "no-store" }),
      ]);
      const userPayload = await read(userResponse); const sessionPayload = await read(sessionResponse);
      if (!userResponse.ok || !sessionResponse.ok) throw new Error(safeAdminError(userPayload?.detail || sessionPayload?.detail, "User access records could not be loaded. Refresh and retry."));
      setUsers(userPayload.users || []); setSessions(sessionPayload.sessions || []);
    } catch (loadError) { setError(safeAdminError(loadError?.message || loadError, "User access records could not be loaded. Refresh and retry.")); }
    finally { setLoading(false); }
  }
  useEffect(() => { void loadAccess(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function mutate(key, path, options = {}) {
    if (busy) return false;
    setBusy(key); setError(""); setNotice("");
    try {
      const response = await apiFetch(path, { accessCode, method: "POST", ...options });
      const payload = await read(response);
      if (!response.ok) throw new Error(safeAdminError(payload?.detail, response.status === 403 ? "Administrator access is required." : "The action could not be completed. Review the account and retry."));
      setNotice(payload?.message || "Access settings updated.");
      await loadAccess();
      return true;
    } catch (actionError) { setError(safeAdminError(actionError?.message || actionError, "The action could not be completed. Review the account and retry.")); return false; }
    finally { setBusy(""); }
  }

  async function createAccount(event) {
    event.preventDefault();
    if (!form.email.trim() || form.password.length < 8) { setError("Enter a valid email and a password of at least 8 characters."); return; }
    const created = await mutate("create", "/api/auth/users", { headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
    if (created) setForm({ email: "", name: "", password: "", role: "operator" });
  }

  return <Panel title="User Access" subtitle={`Signed in as ${currentUser?.email || "administrator"}. Create accounts, activate or deactivate access, and revoke sessions.`}>
    {loading ? <p role="status">Loading user accounts and active sessions...</p> : null}
    <form className="admin-access-form" onSubmit={createAccount} aria-busy={Boolean(busy)}>
      <input aria-label="User email" type="email" placeholder="operator@facility.com" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} disabled={Boolean(busy)} />
      <input aria-label="User name" placeholder="Operator name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} disabled={Boolean(busy)} />
      <input aria-label="Temporary password" type="password" placeholder="Temporary password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} disabled={Boolean(busy)} />
      <select aria-label="User role" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })} disabled={Boolean(busy)}><option value="viewer">Viewer</option><option value="operator">Operator</option><option value="admin">Administrator</option></select>
      <button className="command-button" type="submit" disabled={Boolean(busy)}>{busy === "create" ? "Creating Account..." : "Create Account"}</button>
    </form>
    {notice ? <p className="connector-notice" role="status">{notice}</p> : null}{error ? <p className="auth-error" role="alert">{error}</p> : null}
    <div className="admin-access-list" aria-label="User accounts">{users.map((user) => <article key={user.email}><div><strong>{user.name || user.email}</strong><small>{user.email} &middot; {user.role} &middot; {user.is_active ? "active" : "inactive"}</small></div><div>{user.is_active ? <button type="button" className="operational-link-button operational-link-button--danger" disabled={Boolean(busy) || user.email === currentUser?.email} title={user.email === currentUser?.email ? "You cannot deactivate your current account." : "Deactivate this account and revoke its sessions."} onClick={() => void mutate(`deactivate-${user.email}`, `/api/auth/users/${encodeURIComponent(user.email)}/deactivate`)}>Deactivate Account</button> : <button type="button" className="secondary-command-button" disabled={Boolean(busy)} onClick={() => void mutate(`activate-${user.email}`, `/api/auth/users/${encodeURIComponent(user.email)}/activate`)}>Activate Account</button>}<button type="button" className="operational-link-button" disabled={Boolean(busy) || !sessions.some((session) => session.email === user.email)} title={sessions.some((session) => session.email === user.email) ? "Revoke all active sessions for this account." : "This account has no active sessions."} onClick={() => void mutate(`revoke-${user.email}`, "/api/auth/sessions/revoke", { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: user.email, revoke_all_for_user: true }) })}>Revoke Sessions</button></div></article>)}</div>
  </Panel>;
}
