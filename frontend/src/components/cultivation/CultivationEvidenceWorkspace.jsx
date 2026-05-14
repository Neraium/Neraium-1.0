import React, { useEffect, useState } from "react";

const ENDPOINTS = [
  { key: "vpd", title: "VPD Relationship State", path: "/api/distributed/cultivation/vpd" },
  { key: "masking", title: "Compensation Masking Evidence", path: "/api/distributed/cultivation/compensation-masking" },
  { key: "multi_room", title: "Room Synchronization Drift", path: "/api/distributed/cultivation/multi-room" },
  { key: "pre_visibility", title: "Pre-Visibility Structural State", path: "/api/distributed/cultivation/pre-visibility" },
];

export default function CultivationEvidenceWorkspace({ apiFetch, accessCode, Panel, EmptyState }) {
  const [payloads, setPayloads] = useState({});
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const entries = await Promise.all(
          ENDPOINTS.map(async (endpoint) => {
            const response = await apiFetch(endpoint.path, { headers: accessCode ? { "X-Api-Key": accessCode } : {} });
            return [endpoint.key, await response.json()];
          }),
        );
        if (!cancelled) {
          setPayloads(Object.fromEntries(entries));
          setError("");
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError?.message ?? "Unable to load cultivation evidence flows.");
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [accessCode, apiFetch]);

  if (error) {
    return <EmptyState title="Cultivation evidence unavailable" body={error} />;
  }

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel title="Cultivation Evidence Flows" className="span-12 workspace-hero-panel" subtitle="Evidence-first structural cognition for environmental relationship weakening, propagation, and convergence behavior." />
      {ENDPOINTS.map((endpoint) => (
        <Panel key={endpoint.key} title={endpoint.title} className="span-6" subtitle="Operational, explainable, and replay-linked structural evidence context.">
          <pre className="code-surface">{JSON.stringify(payloads[endpoint.key] ?? {}, null, 2)}</pre>
        </Panel>
      ))}
    </div>
  );
}

