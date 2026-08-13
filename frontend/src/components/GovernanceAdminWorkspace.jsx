import { useEffect, useState } from "react";

import ConnectorSetupPanel from "./ConnectorSetupPanel";
import InfrastructureHealthDashboard from "./InfrastructureHealthDashboard";

function safeAdminError(value, fallback) {
  const message = String(value || "").trim();
  if (!message) return fallback;
  if (/(traceback|exception|stack trace|shared_upload|psycopg|sqlite3|errno|file:\/\/|[a-z]:\\)/i.test(message)) return fallback;
  return message;
}

function governanceDecision(value) {
  return String(value || "").toUpperCase() === "PASS" ? "Approved for operator review" : "Held for administrator review";
}

function AdministrationHeader({ currentUser }) {
  return (
    <header className="workspace-page-header">
      <div className="workspace-page-header__copy">
        <p className="section-token">Configure</p>
        <h1>Access & governance</h1>
        <p>Manage users, sessions, evidence records, and service health.</p>
      </div>
      <span className="workspace-page-header__meta">{currentUser?.email || "Administrator"} · Administrator</span>
    </header>
  );
}

export default function GovernanceAdminWorkspace({
  apiFetch,
  accessCode,
  Panel,
  EmptyState,
  currentUser = null,
  currentWorkspace = null,
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

  if (loading) {
    return (
      <section className="workspace-surface">
        <AdministrationHeader currentUser={currentUser} />
        <ConnectorSetupPanel apiFetch={apiFetch} accessCode={accessCode} currentUser={currentUser} />
        <InfrastructureHealthDashboard apiFetch={apiFetch} accessCode={accessCode} Panel={Panel} />
        <Panel title="Evidence governance" subtitle="Loading governance records…" />
      </section>
    );
  }

  if (error) {
    return (
      <section className="workspace-surface">
        <AdministrationHeader currentUser={currentUser} />
        <ConnectorSetupPanel apiFetch={apiFetch} accessCode={accessCode} currentUser={currentUser} />
        <InfrastructureHealthDashboard apiFetch={apiFetch} accessCode={accessCode} Panel={Panel} />
        <EmptyState title="Intelligence Governance Unavailable" body={error} />
      </section>
    );
  }

  const rows = (payload?.records ?? []).slice(0, 100);
  return (
    <section className="workspace-surface">
      <AdministrationHeader currentUser={currentUser} />
      <ConnectorSetupPanel apiFetch={apiFetch} accessCode={accessCode} currentUser={currentUser} />
      <InfrastructureHealthDashboard apiFetch={apiFetch} accessCode={accessCode} Panel={Panel} />
      <div className="workspace-grid workspace-grid--two admin-summary-grid">
      <Panel
        title="Evidence governance"
        subtitle="Evidence admission audit."
      >
        <div className="metric-grid">
          <article className="metric-card"><span className="metric-label">Decision records</span><strong className="metric-value">{payload?.total ?? 0}</strong></article>
          <article className="metric-card"><span className="metric-label">Approved for operator review</span><strong className="metric-value">{payload?.pass_count ?? 0}</strong></article>
          <article className="metric-card"><span className="metric-label">Held for administrator review</span><strong className="metric-value">{payload?.no_pass_count ?? 0}</strong></article>
        </div>
      </Panel>
      <Panel title="Analysis performance" subtitle="Queue and timing">
        <div className="metric-grid">
          <article className="metric-card"><span className="metric-label">Queued analyses</span><strong className="metric-value">{performance?.queue_depth ?? 0}</strong></article>
          <article className="metric-card"><span className="metric-label">Median analysis time (s)</span><strong className="metric-value">{performance?.upload_duration_seconds?.p50 ?? "-"}</strong></article>
          <article className="metric-card"><span className="metric-label">95th percentile analysis time (s)</span><strong className="metric-value">{performance?.upload_duration_seconds?.p95 ?? "-"}</strong></article>
          <article className="metric-card"><span className="metric-label">Result reuse rate</span><strong className="metric-value">{performance?.cache?.hash_cache_hit_rate != null ? `${Math.round(performance.cache.hash_cache_hit_rate * 100)}%` : "-"}</strong></article>
        </div>
      </Panel>
      </div>

      <AccessAdminPanel apiFetch={apiFetch} accessCode={accessCode} Panel={Panel} currentUser={currentUser} currentWorkspace={currentWorkspace} />

      <div className="workspace-grid workspace-grid--two admin-record-grid">
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


function AccessAdminPanel({ apiFetch, accessCode, Panel, currentUser, currentWorkspace }) {
  const [users, setUsers] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState({ email: "", name: "", password: "", role: "operator" });
  const [memberEmail, setMemberEmail] = useState("");
  const isFacilityWorkspace = currentWorkspace?.kind === "facility";

  async function read(response) { try { return await response.json(); } catch { return {}; } }
  async function loadAccess() {
    setLoading(true); setError("");
    try {
      const requests = [
        apiFetch("/api/auth/users?include_inactive=true", { accessCode, cache: "no-store" }),
        apiFetch("/api/auth/sessions?include_revoked=false", { accessCode, cache: "no-store" }),
      ];
      if (isFacilityWorkspace) requests.push(apiFetch("/api/workspaces/current/members", { accessCode, cache: "no-store" }));
      const [userResponse, sessionResponse, memberResponse] = await Promise.all(requests);
      const userPayload = await read(userResponse); const sessionPayload = await read(sessionResponse);
      const memberPayload = memberResponse ? await read(memberResponse) : { members: [] };
      if (!userResponse.ok || !sessionResponse.ok || (memberResponse && !memberResponse.ok)) throw new Error(safeAdminError(userPayload?.detail || sessionPayload?.detail || memberPayload?.detail, "User access records could not be loaded. Refresh and retry."));
      setUsers(userPayload.users || []); setSessions(sessionPayload.sessions || []);
      setMembers(memberPayload.members || []);
    } catch (loadError) { setError(safeAdminError(loadError?.message || loadError, "User access records could not be loaded. Refresh and retry.")); }
    finally { setLoading(false); }
  }
  useEffect(() => { setMemberEmail(""); void loadAccess(); }, [currentWorkspace?.workspace_id]); // eslint-disable-line react-hooks/exhaustive-deps

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

  async function addFacilityMember(event) {
    event.preventDefault();
    if (!isFacilityWorkspace || !memberEmail) return;
    const added = await mutate(`member-add-${memberEmail}`, `/api/workspaces/${encodeURIComponent(currentWorkspace.workspace_id)}/members`, {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: memberEmail }),
    });
    if (added) setMemberEmail("");
  }

  const activeMemberIds = new Set(members.filter((member) => member.is_active).map((member) => member.member_id));
  const availableAccounts = users.filter((user) => user.is_active && !activeMemberIds.has(user.email));

  return (
    <Panel
      title="User Access"
      subtitle={`Signed in as ${currentUser?.email || "administrator"}.`}
    >
      {loading ? <p role="status">Loading user accounts and active sessions...</p> : null}
      <section className="admin-membership-block" aria-labelledby="current-facility-membership-title">
        <div className="admin-membership-block__header">
          <div>
            <h3 id="current-facility-membership-title">Current facility membership</h3>
            <p>{isFacilityWorkspace
              ? `${currentWorkspace.display_name} access is separate from global account status.`
              : "Personal workspaces are private. Select a facility workspace to manage team access."}</p>
          </div>
          <span className="status-badge">{isFacilityWorkspace ? currentWorkspace.display_name : "Personal"}</span>
        </div>
        {isFacilityWorkspace ? (
          <>
            <form className="admin-membership-form" onSubmit={addFacilityMember}>
              <label>
                <span>Add active account</span>
                <select aria-label="Account to add to current facility" value={memberEmail} onChange={(event) => setMemberEmail(event.target.value)} disabled={Boolean(busy) || availableAccounts.length === 0}>
                  <option value="">{availableAccounts.length ? "Select an account" : "No eligible active accounts"}</option>
                  {availableAccounts.map((user) => <option key={user.email} value={user.email}>{user.name || user.email} · {user.role}</option>)}
                </select>
              </label>
              <button className="secondary-command-button" type="submit" disabled={Boolean(busy) || !memberEmail}>Add facility access</button>
            </form>
            <div className="admin-access-list" aria-label="Current facility members">
              {members.map((member) => (
                <article key={member.member_id}>
                  <div>
                    <strong>{member.display_name || member.member_id}</strong>
                    <small>{member.member_id} · workspace access active · account role {member.role}</small>
                  </div>
                  <div>
                    <button
                      type="button"
                      className="operational-link-button operational-link-button--danger"
                      disabled={Boolean(busy) || member.member_id === currentUser?.email}
                      title={member.member_id === currentUser?.email ? "You cannot disable your current workspace access." : "Remove future access without deactivating this account."}
                      onClick={() => void mutate(`member-disable-${member.member_id}`, `/api/workspaces/${encodeURIComponent(currentWorkspace.workspace_id)}/members/${encodeURIComponent(member.member_id)}/disable`)}
                    >
                      Disable facility access
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </>
        ) : null}
      </section>
      <form className="admin-access-form" onSubmit={createAccount} aria-busy={Boolean(busy)}>
        <label>
          <span>Email address</span>
          <input aria-label="User email" type="email" placeholder="operator@facility.com" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} disabled={Boolean(busy)} />
        </label>
        <label>
          <span>Display name</span>
          <input aria-label="User name" placeholder="Operator name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} disabled={Boolean(busy)} />
        </label>
        <label>
          <span>Temporary password</span>
          <input aria-label="Temporary password" type="password" placeholder="At least 8 characters" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} disabled={Boolean(busy)} />
        </label>
        <label>
          <span>Permission role</span>
          <select aria-label="User role" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })} disabled={Boolean(busy)}>
            <option value="viewer">Viewer</option>
            <option value="operator">Operator</option>
            <option value="admin">Administrator</option>
          </select>
        </label>
        <button className="command-button" type="submit" disabled={Boolean(busy)}>{busy === "create" ? "Creating Account..." : "Create Account"}</button>
      </form>
      {notice ? <p className="connector-notice" role="status">{notice}</p> : null}
      {error ? <p className="auth-error" role="alert">{error}</p> : null}
      <div className="admin-access-list" aria-label="User accounts">
        {users.map((user) => (
          <article key={user.email}>
            <div>
              <strong>{user.name || user.email}</strong>
              <small>{user.email} · {user.role} · account {user.is_active ? "active" : "inactive"}</small>
            </div>
            <div>
              {user.is_active ? (
                <button
                  type="button"
                  className="operational-link-button operational-link-button--danger"
                  disabled={Boolean(busy) || user.email === currentUser?.email}
                  title={user.email === currentUser?.email ? "You cannot deactivate your current account." : "Deactivate this account and revoke its sessions."}
                  onClick={() => void mutate(`deactivate-${user.email}`, `/api/auth/users/${encodeURIComponent(user.email)}/deactivate`)}
                >
                  Deactivate Account
                </button>
              ) : (
                <button type="button" className="secondary-command-button" disabled={Boolean(busy)} onClick={() => void mutate(`activate-${user.email}`, `/api/auth/users/${encodeURIComponent(user.email)}/activate`)}>
                  Activate Account
                </button>
              )}
              <button
                type="button"
                className="operational-link-button"
                disabled={Boolean(busy) || !sessions.some((session) => session.email === user.email)}
                title={sessions.some((session) => session.email === user.email) ? "Revoke all active sessions for this account." : "This account has no active sessions."}
                onClick={() => void mutate(`revoke-${user.email}`, "/api/auth/sessions/revoke", { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: user.email, revoke_all_for_user: true }) })}
              >
                Revoke Sessions
              </button>
            </div>
          </article>
        ))}
      </div>
    </Panel>
  );
}
