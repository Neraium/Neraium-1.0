import React, { useEffect, useState } from "react";

export default function OperatorCognitionTrainingWorkspace({ apiFetch, accessCode, Panel, EmptyState }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await apiFetch("/api/distributed/framework/training-curriculum", {
          headers: accessCode ? { "X-Api-Key": accessCode } : {},
        });
        const data = await response.json();
        if (!cancelled) {
          setPayload(data);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError?.message ?? "Unable to load operator cognition curriculum.");
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [accessCode, apiFetch]);

  if (error) {
    return <EmptyState title="Curriculum unavailable" body={error} />;
  }
  if (!payload) {
    return <Panel title="Operator Cognition Curriculum" subtitle="Loading replay-based interpretation curriculum." />;
  }

  return (
    <section className="workspace-surface">
      <Panel
        title="Operator Cognition Training System"
        subtitle="Replay-based exercises for topology drift, propagation recognition, compensation masking, and convergence interpretation."
      >
        <div className="metric-grid metric-grid--three">
          <div className="metric-tile">
            <span className="metric-label">Modules</span>
            <strong className="metric-value">{payload.modules?.length ?? 0}</strong>
          </div>
          <div className="metric-tile">
            <span className="metric-label">Completed</span>
            <strong className="metric-value">{payload.progress?.completed_modules ?? 0}</strong>
          </div>
          <div className="metric-tile">
            <span className="metric-label">Current focus</span>
            <strong className="metric-value">{payload.progress?.current_focus ?? "N/A"}</strong>
          </div>
        </div>
      </Panel>
      <div className="workspace-grid workspace-grid--two">
        {(payload.modules ?? []).map((module) => (
          <Panel key={module.module_id} title={module.title} subtitle={module.scenario?.focus?.replaceAll("_", " ")}>
            <pre className="code-surface">{JSON.stringify(module, null, 2)}</pre>
          </Panel>
        ))}
      </div>
    </section>
  );
}

