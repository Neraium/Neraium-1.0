import React, { useEffect, useState } from "react";

const ENDPOINTS = [
  { key: "memory", label: "Persistent cognition graph memory", path: "/api/distributed/memory" },
  { key: "federation", label: "Federated cognition exchange", path: "/api/distributed/federation" },
  { key: "cross_domain", label: "Cross-domain structural matches", path: "/api/distributed/cross-domain" },
  { key: "ontology", label: "Ontology extension candidates", path: "/api/distributed/ontology" },
  { key: "exchange", label: "SII graph exchange status", path: "/api/distributed/exchange" },
  { key: "governance", label: "Governance review state", path: "/api/distributed/governance" },
  { key: "search", label: "Structural evolution search", path: "/api/distributed/search" },
];

export default function DistributedCognitionWorkspace({ apiFetch, accessCode, Panel, EmptyState }) {
  const [payloads, setPayloads] = useState({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const entries = await Promise.all(
          ENDPOINTS.map(async (endpoint) => {
            const response = await apiFetch(endpoint.path, {
              headers: accessCode ? { "X-Api-Key": accessCode } : {},
            });
            return [endpoint.key, await response.json()];
          }),
        );
        if (!cancelled) {
          setPayloads(Object.fromEntries(entries));
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError?.message ?? "Distributed cognition context unavailable.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [accessCode, apiFetch]);

  if (error) {
    return <EmptyState title="Distributed cognition unavailable" body={error} />;
  }

  if (loading) {
    return (
      <Panel
        title="Distributed Structural Cognition Network"
        subtitle="Synchronizing cognition primitive exchange, graph memory, governance, and search."
      />
    );
  }

  return (
    <section className="workspace-surface">
      <Panel
        title="Distributed Structural Cognition Network"
        subtitle="Privacy-preserving cognition primitive exchange with replay-backed governance and cross-domain structural matching."
      >
        <div className="metric-grid metric-grid--three">
          <div className="metric-tile">
            <span className="metric-label">Read-only posture</span>
            <strong className="metric-value">enforced</strong>
          </div>
          <div className="metric-tile">
            <span className="metric-label">Privacy-preserving exchange</span>
            <strong className="metric-value">active</strong>
          </div>
          <div className="metric-tile">
            <span className="metric-label">Governance status</span>
            <strong className="metric-value">{payloads.governance?.validation_status ?? "reviewed"}</strong>
          </div>
        </div>
      </Panel>
      <div className="workspace-grid workspace-grid--two">
        {ENDPOINTS.map((endpoint) => (
          <Panel key={endpoint.key} title={endpoint.label} subtitle="Replay-backed pattern, evidence summary, and governance context.">
            <pre className="code-surface">{JSON.stringify(payloads[endpoint.key] ?? {}, null, 2)}</pre>
          </Panel>
        ))}
      </div>
    </section>
  );
}
