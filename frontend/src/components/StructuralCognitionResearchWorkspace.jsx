import React, { useEffect, useState } from "react";

const ENDPOINTS = [
  { key: "primitives", label: "Universal structural primitives", path: "/api/distributed/framework/primitives" },
  { key: "math", label: "Structural evolution metrics", path: "/api/distributed/framework/mathematics" },
  { key: "governance", label: "Ontology governance queue", path: "/api/distributed/framework/ontology-governance" },
  { key: "archive", label: "Infrastructure behavior archive", path: "/api/distributed/framework/archive" },
  { key: "research", label: "SII research ecosystem export", path: "/api/distributed/framework/research-ecosystem" },
  { key: "reasoning", label: "Foundational reasoning substrate", path: "/api/distributed/framework/reasoning-substrate" },
  { key: "extreme", label: "Extreme environment cognition", path: "/api/distributed/framework/extreme-environment" },
];

export default function StructuralCognitionResearchWorkspace({ apiFetch, accessCode, Panel, EmptyState }) {
  const [payloads, setPayloads] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
          setError(loadError?.message ?? "Research framework endpoints unavailable.");
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
    return <EmptyState title="Structural cognition research unavailable" body={error} />;
  }
  if (loading) {
    return <Panel title="Structural Cognition Research Workspace" subtitle="Synchronizing universal primitives, mathematics, archives, and reasoning traces." />;
  }

  return (
    <section className="workspace-surface">
      <Panel
        title="Structural Cognition Research Workspace"
        subtitle="Research-grade structural cognition surface for universal primitives, evolution descriptors, governance, archives, and replay-grounded reasoning traces."
      >
        <div className="metric-grid metric-grid--three">
          <div className="metric-tile">
            <span className="metric-label">Primitive count</span>
            <strong className="metric-value">{payloads.primitives?.primitive_count ?? 0}</strong>
          </div>
          <div className="metric-tile">
            <span className="metric-label">Topology transition distance</span>
            <strong className="metric-value">{payloads.math?.topology_transition?.transition_distance ?? 0}</strong>
          </div>
          <div className="metric-tile">
            <span className="metric-label">Governance queue size</span>
            <strong className="metric-value">{payloads.governance?.promotion_queue?.items?.length ?? 0}</strong>
          </div>
        </div>
      </Panel>
      <div className="workspace-grid workspace-grid--two">
        {ENDPOINTS.map((endpoint) => (
          <Panel key={endpoint.key} title={endpoint.label} subtitle="Evidence-backed, replay-grounded structural cognition artifact.">
            <pre className="code-surface">{JSON.stringify(payloads[endpoint.key] ?? {}, null, 2)}</pre>
          </Panel>
        ))}
      </div>
    </section>
  );
}

