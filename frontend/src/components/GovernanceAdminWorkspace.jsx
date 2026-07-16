import { useEffect, useState } from "react";

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
          throw new Error(String(data?.detail ?? `Unexpected response: ${governanceResponse.status}`)); 
        } 
        const perf = await performanceResponse.json().catch(() => ({}));
        if (!mounted) return; 
        setPayload(data); 
        setPerformance(perf);
      } catch (err) {
        if (!mounted) return;
        setError(String(err?.message ?? err));
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
      aria-label="Back to Gate"
    >
      Back to Gate
    </button>
  );

  if (loading) {
    return (
      <section className="workspace-surface">
        {backControl}
        <Panel title="Governance Admin" subtitle="Loading Aletheia Gate custody records..." />
      </section>
    );
  }

  if (error) {
    return (
      <section className="workspace-surface">
        {backControl}
        <EmptyState title="Governance Admin Unavailable" body={error} />
      </section>
    );
  }

  const rows = (payload?.records ?? []).slice(0, 100);
  return (
    <section className="workspace-surface">
      {backControl}
      <Panel 
        title="Governance Admin" 
        subtitle="Internal custody view for Aletheia Gate PASS/NO_PASS EVP receipts. Operator UI remains PASS-only." 
      > 
        <div className="metric-grid"> 
          <article className="metric-card"><span className="metric-label">Total Records</span><strong className="metric-value">{payload?.total ?? 0}</strong></article>
          <article className="metric-card"><span className="metric-label">PASS</span><strong className="metric-value">{payload?.pass_count ?? 0}</strong></article>
          <article className="metric-card"><span className="metric-label">NO_PASS</span><strong className="metric-value">{payload?.no_pass_count ?? 0}</strong></article> 
        </div> 
      </Panel> 
      <Panel title="Performance" subtitle="Runtime analysis throughput window">
        <div className="metric-grid">
          <article className="metric-card"><span className="metric-label">Pending Analyses</span><strong className="metric-value">{performance?.queue_depth ?? 0}</strong></article>
          <article className="metric-card"><span className="metric-label">Upload p50 (s)</span><strong className="metric-value">{performance?.upload_duration_seconds?.p50 ?? "-"}</strong></article>
          <article className="metric-card"><span className="metric-label">Upload p95 (s)</span><strong className="metric-value">{performance?.upload_duration_seconds?.p95 ?? "-"}</strong></article>
          <article className="metric-card"><span className="metric-label">Processing Reuse Rate</span><strong className="metric-value">{performance?.cache?.hash_cache_hit_rate != null ? `${Math.round(performance.cache.hash_cache_hit_rate * 100)}%` : "-"}</strong></article>
        </div>
      </Panel>

      <AccessAdminPanel apiFetch={apiFetch} accessCode={accessCode} Panel={Panel} currentUser={currentUser} />

      <div className="workspace-grid workspace-grid--two"> 
        {rows.map((record) => (
          <Panel
            key={record.evp_id}
            title={`${record.gate_outcome} - ${record.admitted_state}`}
            subtitle={`${record.evp_id} - ${record.timestamp_utc}`}
          >
            <ul className="compact-list">
              <li><span className="metadata-text">Doctrine</span><strong>{record.doctrine_version}</strong></li>
              <li><span className="metadata-text">Reason Codes</span><strong>{(record.decision_reason_codes ?? []).join(", ") || "-"}</strong></li>
              <li><span className="metadata-text">EVP Hash</span><strong>{record.evp_hash}</strong></li>
              <li><span className="metadata-text">Prev Hash</span><strong>{record.previous_evp_hash || "-"}</strong></li>
              <li><span className="metadata-text">Operator Visible</span><strong>{String(Boolean(record.operator_visible))}</strong></li>
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
      if (!userResponse.ok || !sessionResponse.ok) throw new Error(userPayload?.detail || sessionPayload?.detail || "Access records could not be loaded.");
      setUsers(userPayload.users || []); setSessions(sessionPayload.sessions || []);
    } catch (loadError) { setError(String(loadError?.message || loadError)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void loadAccess(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function mutate(key, path, options = {}) {
    if (busy) return false;
    setBusy(key); setError(""); setNotice("");
    try {
      const response = await apiFetch(path, { accessCode, method: "POST", ...options });
      const payload = await read(response);
      if (!response.ok) throw new Error(payload?.detail || (response.status === 403 ? "Administrator access is required." : "The action failed. Review the account and retry."));
      setNotice(payload?.message || "Access settings updated.");
      await loadAccess();
      return true;
    } catch (actionError) { setError(String(actionError?.message || actionError)); return false; }
    finally { setBusy(""); }
  }

  async function createAccount(event) {
    event.preventDefault();
    if (!form.email.trim() || form.password.length < 8) { setError("Enter a valid email and a password of at least 8 characters."); return; }
    const created = await mutate("create", "/api/auth/users", { headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
    if (created) setForm({ email: "", name: "", password: "", role: "operator" });
  }

  return <Panel title="Access Administration" subtitle={`Signed in as ${currentUser?.email || "administrator"}. Create accounts, activate access, or revoke sessions.`}>
    {loading ? <p role="status">Loading access records...</p> : null}
    <form className="admin-access-form" onSubmit={createAccount} aria-busy={Boolean(busy)}>
      <input aria-label="User email" type="email" placeholder="operator@facility.com" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} disabled={Boolean(busy)} />
      <input aria-label="User name" placeholder="Operator name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} disabled={Boolean(busy)} />
      <input aria-label="Temporary password" type="password" placeholder="Temporary password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} disabled={Boolean(busy)} />
      <select aria-label="User role" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })} disabled={Boolean(busy)}><option value="viewer">Viewer</option><option value="operator">Operator</option><option value="admin">Administrator</option></select>
      <button className="command-button" type="submit" disabled={Boolean(busy)}>{busy === "create" ? "Creating..." : "Create account"}</button>
    </form>
    {notice ? <p className="connector-notice" role="status">{notice}</p> : null}{error ? <p className="auth-error" role="alert">{error}</p> : null}
    <div className="admin-access-list" aria-label="User accounts">{users.map((user) => <article key={user.email}><div><strong>{user.name || user.email}</strong><small>{user.email} &middot; {user.role} &middot; {user.is_active ? "active" : "inactive"}</small></div><div>{user.is_active ? <button type="button" className="operational-link-button operational-link-button--danger" disabled={Boolean(busy) || user.email === currentUser?.email} title={user.email === currentUser?.email ? "You cannot deactivate your current account." : "Deactivate this account and revoke its sessions."} onClick={() => void mutate(`deactivate-${user.email}`, `/api/auth/users/${encodeURIComponent(user.email)}/deactivate`)}>Deactivate</button> : <button type="button" className="secondary-command-button" disabled={Boolean(busy)} onClick={() => void mutate(`activate-${user.email}`, `/api/auth/users/${encodeURIComponent(user.email)}/activate`)}>Activate</button>}<button type="button" className="operational-link-button" disabled={Boolean(busy) || !sessions.some((session) => session.email === user.email)} title={sessions.some((session) => session.email === user.email) ? "Revoke all active sessions for this account." : "This account has no active sessions."} onClick={() => void mutate(`revoke-${user.email}`, "/api/auth/sessions/revoke", { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: user.email, revoke_all_for_user: true }) })}>Revoke sessions</button></div></article>)}</div>
  </Panel>;
}
