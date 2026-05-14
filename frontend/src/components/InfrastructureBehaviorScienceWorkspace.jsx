import React, { useEffect, useState } from "react";

const ENDPOINTS = [
  { key: "memory", label: "Long-horizon structural memory", path: "/api/distributed/science/memory" },
  { key: "taxonomy", label: "Infrastructure behavioral taxonomy", path: "/api/distributed/science/taxonomy" },
  { key: "evolution", label: "Structural evolution theory", path: "/api/distributed/science/evolution-theory" },
  { key: "research", label: "Behavior research studies", path: "/api/distributed/science/research" },
  { key: "explainability", label: "Explainability assessments", path: "/api/distributed/science/explainability" },
  { key: "lab", label: "Behavioral infrastructure laboratory", path: "/api/distributed/science/laboratory" },
  { key: "federation", label: "Infrastructure cognition federation", path: "/api/distributed/science/federation" },
];

export default function InfrastructureBehaviorScienceWorkspace({ apiFetch, accessCode, Panel, EmptyState }) {
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
          setError(loadError?.message ?? "Behavior science context unavailable.");
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
    return <EmptyState title="Behavior science unavailable" body={error} />;
  }

  if (loading) {
    return (
      <Panel
        title="Infrastructure Behavior Science"
        subtitle="Synchronizing long-horizon memory, taxonomy, evolution rules, research tools, explainability, and federation science."
      />
    );
  }

  return (
    <section className="workspace-surface">
      <Panel
        title="Infrastructure Behavior Science"
        subtitle="Evidence-backed structural behavior studies with replay support, taxonomy framing, and non-deterministic evolution theory."
      >
        <div className="metric-grid metric-grid--three">
          <div className="metric-tile">
            <span className="metric-label">Evidence sufficiency</span>
            <strong className="metric-value">{payloads.explainability?.assessment?.explainability_completeness ?? "MODERATE"}</strong>
          </div>
          <div className="metric-tile">
            <span className="metric-label">Replay support</span>
            <strong className="metric-value">{payloads.explainability?.assessment?.replay_support_level ?? "DEVELOPING"}</strong>
          </div>
          <div className="metric-tile">
            <span className="metric-label">Behavior classification</span>
            <strong className="metric-value">{payloads.taxonomy?.classification_result?.primary_class ?? "PENDING"}</strong>
          </div>
        </div>
      </Panel>
      <div className="workspace-grid workspace-grid--two">
        {ENDPOINTS.map((endpoint) => (
          <Panel key={endpoint.key} title={endpoint.label} subtitle="Structural behavior, topology evolution, convergence study, and replay-backed evidence context.">
            <pre className="code-surface">{JSON.stringify(payloads[endpoint.key] ?? {}, null, 2)}</pre>
          </Panel>
        ))}
      </div>
    </section>
  );
}

