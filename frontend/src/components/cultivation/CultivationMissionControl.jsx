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
  const evidenceSummary = buildCultivationEvidenceSummary(cognition);
  const continuationWindow = cognition.continuation_windows?.window ?? "Monitoring";
  const replayFrames = replay.timeline?.slice(0, 8) ?? [];

  const metrics = [
    { label: "Facility Cognition State", value: cognition.cognition_state },
    { label: "Structural Stability", value: cognition.structural_stability },
    { label: "Active Pathways", value: (cognition.propagation_pathways ?? []).length },
    { label: "Continuation Window", value: cognition.continuation_windows?.window ?? "Monitoring" },
    { label: "Replay Frames", value: replay.meta?.frame_count ?? 0 },
    { label: "Recovery State", value: cognition.recovery_convergence?.convergence_quality ?? "developing" },
  ];
  const reportExport = buildWeeklyPilotReport({
    cognition,
    replay,
    ontology,
    evidenceSummary,
  });

  return (
    <div className="workspace-grid workspace-grid--console cultivation-mission-grid">
      <Panel
        title="Cultivation Mission Control"
        className="span-12 workspace-hero-panel cultivation-hero-panel"
        subtitle="Environmental mission-control cognition for coupled temperature, humidity, airflow, and VPD structural evolution."
      >
        <MetricGrid metrics={metrics} />
        <p className="narrative-text">{cognition.operator_explanation}</p>
        <div className="cultivation-summary-callouts">
          <p><strong>Propagation pathway:</strong> {humanizePathway(cognition.propagation_pathways?.[0])}</p>
          <p><strong>Continuation window:</strong> {continuationWindow}</p>
          <p><strong>Recovery / convergence:</strong> {cognition.recovery_convergence?.convergence_quality ?? "developing"}</p>
        </div>
      </Panel>
      <Panel title="Propagation Pathways" className="span-6 cultivation-list-panel" subtitle="Where structural pressure is currently spreading in plain operator language.">
        <ul className="system-body-timeline-list">
          {(cognition.propagation_pathways ?? []).map((path) => (
            <li key={path}><span className="metadata-text">Pathway</span><strong>{humanizePathway(path)}</strong></li>
          ))}
        </ul>
      </Panel>
      <Panel title="Evidence Lineage Summary" className="span-6 cultivation-list-panel" subtitle="Why structural drift was flagged for operator review.">
        <ul className="system-body-timeline-list">
          {evidenceSummary.map((item) => (
            <li key={item}><span className="metadata-text">Evidence</span><strong>{item}</strong></li>
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
        <pre className="code-surface">{JSON.stringify(replayFrames, null, 2)}</pre>
      </Panel>
      <Panel title="Cultivation Structural Ontology" className="span-12 cultivation-code-panel" subtitle="Domain structural primitives and archetype definitions in active use.">
        <pre className="code-surface">{JSON.stringify(ontology ?? {}, null, 2)}</pre>
      </Panel>
      <Panel title="Weekly Pilot Report" className="span-12 cultivation-code-panel" subtitle="Exportable operator-ready summary from current structural cognition state.">
        <button type="button" className="secondary-command-button" onClick={() => exportPilotReport(reportExport)}>
          Export Weekly Pilot Report
        </button>
        <pre className="code-surface">{reportExport}</pre>
      </Panel>
    </div>
  );
}

function humanizePathway(path) {
  if (!path) return "No active propagation pathway";
  return String(path).replaceAll("_", " -> ").replace(/\s+/g, " ").trim();
}

function buildCultivationEvidenceSummary(cognition) {
  const lineage = cognition.evidence_lineage ?? {};
  const sources = lineage.evidence_sources ?? {};
  const evidence = [
    ...(sources.topology_evidence ?? []),
    ...(sources.persistence_evidence ?? []),
    ...(sources.propagation_evidence ?? []),
    ...(sources.historical_memory_references ?? []),
  ].filter(Boolean);
  if (evidence.length > 0) {
    return evidence.slice(0, 6);
  }
  return [
    "Environmental topology drift has persisted across recent replay intervals.",
    "Propagation pathway activity is corroborated across subsystem relationships.",
    "Compensation masking signals indicate hidden pressure accumulation before visible deterioration.",
  ];
}

function buildWeeklyPilotReport({ cognition, replay, ontology, evidenceSummary }) {
  const payload = {
    generated_at: new Date().toISOString(),
    pilot_summary: {
      cognition_state: cognition.cognition_state,
      structural_stability: cognition.structural_stability,
      continuation_window: cognition.continuation_windows?.window ?? "Monitoring",
      recovery_convergence: cognition.recovery_convergence?.convergence_quality ?? "developing",
      operator_explanation: cognition.operator_explanation,
    },
    propagation_pathways: (cognition.propagation_pathways ?? []).map((path) => humanizePathway(path)),
    active_archetypes: cognition.active_archetypes ?? [],
    evidence_summary: evidenceSummary,
    replay_evidence: {
      frame_count: replay.meta?.frame_count ?? 0,
      canonical_flow: replay.meta?.canonical_flow ?? [],
    },
    ontology_snapshot_available: Boolean(ontology && Object.keys(ontology).length > 0),
  };
  return JSON.stringify(payload, null, 2);
}

function exportPilotReport(reportBody) {
  const blob = new Blob([reportBody], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `neraium-weekly-pilot-report-${new Date().toISOString().slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}
