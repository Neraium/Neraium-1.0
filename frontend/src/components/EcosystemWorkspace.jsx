import { useEffect, useState } from "react";

const ENDPOINTS = [
  { key: "runtime", label: "Runtime state", path: "/api/ecosystem/runtime/state" },
  { key: "graph", label: "Structural graph snapshot", path: "/api/ecosystem/graph/snapshot" },
  { key: "evidence", label: "Evidence lineage export", path: "/api/ecosystem/evidence/export" },
  { key: "replay", label: "Replay frame export", path: "/api/ecosystem/replay/export" },
  { key: "integrations", label: "Integration readiness", path: "/api/ecosystem/integrations/readiness" },
  { key: "simulations", label: "Operational reasoning scenarios", path: "/api/ecosystem/simulation/scenarios" },
];

function summarize(payload, key) {
  if (!payload || typeof payload !== "object") {
    return "No data available.";
  }
  if (key === "runtime") {
    return `Execution mode: ${payload.execution_mode ?? "unknown"} | Read-only: ${payload.read_only_status ?? "enforced"}`;
  }
  if (key === "graph") {
    const nodeCount = payload?.snapshot?.nodes?.length ?? 0;
    const edgeCount = payload?.snapshot?.edges?.length ?? 0;
    return `Graph snapshot contains ${nodeCount} nodes and ${edgeCount} relationships.`;
  }
  if (key === "evidence") {
    const sources = payload?.lineage?.evidence_sources?.length ?? 0;
    return `Evidence lineage export currently contains ${sources} evidence sources.`;
  }
  if (key === "replay") {
    const frames = payload?.frames?.length ?? 0;
    return `Replay frame export includes ${frames} structural timeline frames.`;
  }
  if (key === "integrations") {
    const ready = (payload?.integrations ?? []).filter((item) => item.read_only === true).length;
    const total = payload?.integrations?.length ?? 0;
    return `${ready}/${total} adapters report explicit read-only integration readiness.`;
  }
  if (key === "simulations") {
    const scenarios = payload?.scenarios?.length ?? 0;
    return `Operational reasoning produced ${scenarios} replayable structural scenarios.`;
  }
  return "SII ecosystem payload available.";
}

export default function EcosystemWorkspace({
  apiFetch,
  accessCode,
  Panel,
  EmptyState,
  formatClockTime,
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [fetchedAt, setFetchedAt] = useState(null);
  const [payloads, setPayloads] = useState({});

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const entries = await Promise.all(
          ENDPOINTS.map(async (endpoint) => {
            const result = await apiFetch(endpoint.path, {
              headers: accessCode ? { "X-Api-Key": accessCode } : {},
            });
            return [endpoint.key, await result.json()];
          }),
        );
        if (!cancelled) {
          setPayloads(Object.fromEntries(entries));
          setFetchedAt(new Date().toISOString());
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError?.message ?? "Failed to load ecosystem context.");
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

  return (
    <section className="workspace-surface">
      <Panel
        title="Infrastructure Cognition Ecosystem"
        subtitle="Read-only integration posture with cognition state export, evidence lineage export, replay frame export, and structural graph snapshots."
      >
        <div className="metric-grid metric-grid--three">
          <div className="metric-tile">
            <span className="metric-label">Read-only integration</span>
            <strong className="metric-value">{payloads.integrations?.read_only_integration_status ?? "enforced"}</strong>
          </div>
          <div className="metric-tile">
            <span className="metric-label">Runtime execution</span>
            <strong className="metric-value">{payloads.runtime?.execution_mode ?? "cloud"}</strong>
          </div>
          <div className="metric-tile">
            <span className="metric-label">Last refresh (CT)</span>
            <strong className="metric-value">{fetchedAt ? formatClockTime(new Date(fetchedAt)) : "Pending"}</strong>
          </div>
        </div>
      </Panel>

      {error ? (
        <EmptyState
          title="Ecosystem context unavailable"
          description={error}
        />
      ) : null}

      {loading ? (
        <Panel title="Loading ecosystem context" subtitle="Synchronizing SII runtime, structural cognition graph, replay, evidence, and integration status." />
      ) : (
        <div className="workspace-grid workspace-grid--two">
          {ENDPOINTS.map((endpoint) => (
            <Panel key={endpoint.key} title={endpoint.label} subtitle={summarize(payloads[endpoint.key], endpoint.key)}>
              <pre className="code-surface">{JSON.stringify(payloads[endpoint.key] ?? {}, null, 2)}</pre>
            </Panel>
          ))}
        </div>
      )}
    </section>
  );
}
