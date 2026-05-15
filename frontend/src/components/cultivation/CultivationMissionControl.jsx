import React, { useEffect, useState } from "react";
import { fetchCanonicalCognitionState } from "../../services/api/cognitionApi";
import { fetchReplayTimeline } from "../../services/api/replayApi";

export default function CultivationMissionControl({
  apiFetch,
  accessCode,
  isDemoMode,
  Panel,
  MetricGrid,
  EmptyState,
}) {
  const [cognition, setCognition] = useState(null);
  const [replay, setReplay] = useState(null);
  const [ontology, setOntology] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const mode = isDemoMode ? "demo" : "live";
        const [state, timeline, onto] = await Promise.all([
          fetchCanonicalCognitionState({ apiFetch, accessCode, mode }),
          fetchReplayTimeline({ apiFetch, accessCode, intervals: 24, mode }),
          apiFetch("/api/distributed/cultivation/ontology", { headers: accessCode ? { "X-Api-Key": accessCode } : {} }).then((r) => r.json()),
        ]);
        if (!cancelled) {
          setCognition(state);
          setReplay(timeline);
          setOntology(onto);
          setError("");
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError?.message ?? "Unable to load cultivation mission control.");
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [accessCode, apiFetch, isDemoMode]);

  if (error) {
    return <EmptyState title="Cultivation mission control unavailable" body={error} />;
  }
  if (!cognition || !replay) {
    return <Panel title="Cultivation Mission Control" subtitle="Loading cultivation structural cognition context." />;
  }

  const metrics = [
    { label: "Facility Cognition State", value: cognition.cognition_state },
    { label: "Structural Stability", value: cognition.structural_stability },
    { label: "Active Pathways", value: (cognition.propagation_pathways ?? []).length },
    { label: "Continuation Window", value: cognition.continuation_windows?.window ?? "Monitoring" },
    { label: "Replay Frames", value: replay.meta?.frame_count ?? 0 },
    { label: "Recovery State", value: cognition.recovery_convergence?.convergence_quality ?? "developing" },
  ];

  return (
    <div className="workspace-grid workspace-grid--console cultivation-mission-grid">
      <Panel
        title="Cultivation Mission Control"
        className="span-12 workspace-hero-panel cultivation-hero-panel"
        subtitle="Environmental mission-control cognition for coupled temperature, humidity, airflow, and VPD structural evolution."
      >
        <MetricGrid metrics={metrics} />
        <p className="narrative-text">{cognition.operator_explanation}</p>
      </Panel>
      <Panel title="Propagation Pathways" className="span-6 cultivation-list-panel" subtitle="Where structural pressure is currently spreading.">
        <ul className="system-body-timeline-list">
          {(cognition.propagation_pathways ?? []).map((path) => (
            <li key={path}><span className="metadata-text">Pathway</span><strong>{path}</strong></li>
          ))}
        </ul>
      </Panel>
      <Panel title="Active Cultivation Archetypes" className="span-6 cultivation-list-panel" subtitle="Structural behaviors active in the current facility state.">
        <ul className="system-body-timeline-list">
          {(cognition.active_archetypes ?? []).map((item) => (
            <li key={item}><span className="metadata-text">Archetype</span><strong>{item}</strong></li>
          ))}
        </ul>
      </Panel>
      <Panel title="Structural Replay" className="span-12 cultivation-code-panel" subtitle="Recent replay frames for operator review and timeline inspection.">
        <pre className="code-surface">{JSON.stringify(replay.timeline?.slice(0, 8) ?? [], null, 2)}</pre>
      </Panel>
      <Panel title="Cultivation Structural Ontology" className="span-12 cultivation-code-panel" subtitle="Domain structural primitives and archetype definitions in active use.">
        <pre className="code-surface">{JSON.stringify(ontology ?? {}, null, 2)}</pre>
      </Panel>
    </div>
  );
}
