import { useEffect, useState } from "react";

export default function GovernanceAdminWorkspace({ apiFetch, accessCode, Panel, EmptyState }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        setLoading(true);
        setError("");
        const data = await apiFetch(`/api/observability/evp-governance?limit=200`, { accessCode });
        if (!mounted) return;
        setPayload(data);
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

  if (loading) {
    return <Panel title="Governance Admin" subtitle="Loading Aletheia Gate custody records..." />;
  }

  if (error) {
    return <EmptyState title="Governance Admin Unavailable" body={error} />;
  }

  const rows = (payload?.records ?? []).slice(0, 100);
  return (
    <section className="workspace-surface">
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

      <div className="workspace-grid workspace-grid--two">
        {rows.map((record) => (
          <Panel
            key={record.evp_id}
            title={`${record.gate_outcome} · ${record.admitted_state}`}
            subtitle={`${record.evp_id} · ${record.timestamp_utc}`}
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
