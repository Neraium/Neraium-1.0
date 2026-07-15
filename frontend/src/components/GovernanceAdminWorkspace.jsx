import { useEffect, useState } from "react";

export default function GovernanceAdminWorkspace({
  apiFetch,
  accessCode,
  Panel,
  EmptyState,
  onBackToGate = null,
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
