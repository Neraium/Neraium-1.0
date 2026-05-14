import React, { useEffect, useState } from "react";

export default function OperatorTrainingWorkspace({ apiFetch, accessCode, Panel, EmptyState }) {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setError("");
        const response = await apiFetch("/api/distributed/training", {
          headers: accessCode ? { "X-Api-Key": accessCode } : {},
        });
        const data = await response.json();
        if (!cancelled) {
          setPayload(data);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError?.message ?? "Failed to load operator cognition training.");
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [accessCode, apiFetch]);

  if (error) {
    return <EmptyState title="Training unavailable" body={error} />;
  }

  if (!payload) {
    return <Panel title="Operator Cognition Training" subtitle="Loading replay-backed cognition training scenarios." />;
  }

  return (
    <div className="workspace-grid workspace-grid--two">
      <Panel title="Training Scenarios" subtitle="Replay and simulation modules for structural cognition interpretation.">
        <ul className="system-body-timeline-list">
          {(payload.scenarios ?? []).map((scenario) => (
            <li key={scenario.scenario_id}>
              <span className="metadata-text">{scenario.replay?.focus?.replaceAll("_", " ")}</span>
              <strong>{scenario.title}</strong>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="Training Progress" subtitle="Operator interpretation progress for evidence, propagation, and convergence analysis.">
        <ul className="system-body-timeline-list">
          <li>
            <span className="metadata-text">Completed scenarios</span>
            <strong>{payload.training_progress?.completed_scenarios ?? 0}</strong>
          </li>
          <li>
            <span className="metadata-text">Active focus</span>
            <strong>{payload.training_progress?.active_focus ?? "N/A"}</strong>
          </li>
          <li>
            <span className="metadata-text">Evidence interpretation</span>
            <strong>{payload.latest_assessment?.evidence_interpretation_score ?? "N/A"}</strong>
          </li>
        </ul>
      </Panel>
    </div>
  );
}
