import React, { useEffect, useState } from "react";
import { fetchCanonicalCognitionState } from "../../services/api/cognitionApi";
import { fetchReplayTimeline } from "../../services/api/replayApi";

export default function CultivationMissionControl({
  apiFetch,
  accessCode,
  isDemoMode,
  Panel,
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
        const [stateResult, timelineResult, ontologyResult] = await Promise.allSettled([
          fetchCanonicalCognitionState({ apiFetch, accessCode, mode }),
          fetchReplayTimeline({ apiFetch, accessCode, intervals: 24, mode }),
          loadOntology({ apiFetch, accessCode }),
        ]);
        const state = stateResult.status === "fulfilled" ? stateResult.value : buildFallbackCognitionState();
        const timeline = timelineResult.status === "fulfilled" ? timelineResult.value : buildFallbackReplayTimeline();
        const onto = ontologyResult.status === "fulfilled" ? ontologyResult.value : {};
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
  const replayFrames = replay.timeline?.slice(0, 6) ?? [];

  const topSummaryCards = [
    {
      label: "What's changing",
      value: summarizeChange(cognition),
    },
    {
      label: "Where it's spreading",
      value: summarizeSpread(cognition),
    },
    {
      label: "Why trust this",
      value: summarizeTrust(cognition, evidenceSummary),
    },
  ];
  const reportExport = buildWeeklyPilotReport({
    cognition,
    replay,
    ontology,
    evidenceSummary,
  });

  return (
    <div className="workspace-grid workspace-grid--console cultivation-mission-grid cultivation-mission-grid--clean">
      <Panel
        title="Cultivation Mission Control"
        className="span-12 workspace-hero-panel cultivation-hero-panel"
        subtitle="Environmental structural cognition for controlled cultivation."
      >
        <div className="cultivation-top-summary-grid">
          {topSummaryCards.map((card) => (
            <article key={card.label} className="cultivation-top-summary-card">
              <span>{card.label}</span>
              <strong>{card.value}</strong>
            </article>
          ))}
        </div>
      </Panel>

      <Panel title="Structural Replay" className="span-7 cultivation-replay-panel" subtitle="Replay evidence of environmental topology progression.">
        <ul className="system-body-timeline-list cultivation-compact-list">
          {replayFrames.length === 0 && (
            <li><span className="metadata-text">Replay</span><strong>No replay frames available.</strong></li>
          )}
          {replayFrames.map((frame, index) => (
            <li key={`${frame.timestamp ?? "frame"}-${index}`}>
              <span className="metadata-text">{frame.timestamp ? new Date(frame.timestamp).toLocaleString() : `Frame ${index + 1}`}</span>
              <strong>{summarizeFrame(frame)}</strong>
            </li>
          ))}
        </ul>
      </Panel>

      <Panel title="Evidence Lineage" className="span-5 cultivation-list-panel" subtitle="Why structural drift is supported for operator review.">
        <ul className="system-body-timeline-list cultivation-compact-list">
          {evidenceSummary.map((item) => (
            <li key={item}><span className="metadata-text">Evidence</span><strong>{item}</strong></li>
          ))}
        </ul>
      </Panel>

      <Panel title="Propagation Pathways" className="span-7 cultivation-list-panel" subtitle="Where structural pressure is moving in plain operator language.">
        <ul className="system-body-timeline-list cultivation-compact-list">
          {(cognition.propagation_pathways ?? []).map((path) => (
            <li key={path}><span className="metadata-text">Pathway</span><strong>{humanizePathway(path)}</strong></li>
          ))}
          {(cognition.propagation_pathways ?? []).length === 0 && (
            <li><span className="metadata-text">Pathway</span><strong>No active propagation pathway.</strong></li>
          )}
        </ul>
      </Panel>

      <div className="span-5 cultivation-right-stack">
        <Panel title="Active Cultivation Archetypes" className="cultivation-list-panel cultivation-stack-panel" subtitle="Structural behaviors active in the current state.">
          <ul className="system-body-timeline-list cultivation-compact-list">
            {(cognition.active_archetypes ?? []).map((item) => (
              <li key={item}><span className="metadata-text">Archetype</span><strong>{item}</strong></li>
            ))}
            {(cognition.active_archetypes ?? []).length === 0 && (
              <li><span className="metadata-text">Archetype</span><strong>No active archetypes.</strong></li>
            )}
          </ul>
        </Panel>

        <Panel title="Continuation Window" className="cultivation-list-panel cultivation-stack-panel" subtitle="Current continuation and convergence/recovery context.">
          <div className="cultivation-summary-callouts">
            <p><strong>Continuation window:</strong> {continuationWindow}</p>
            <p><strong>Recovery / convergence:</strong> {cognition.recovery_convergence?.convergence_quality ?? "developing"}</p>
            <p><strong>Topology context:</strong> {cognition.cognition_state ?? "Monitoring"}</p>
          </div>
        </Panel>
      </div>

      <Panel title="Weekly Pilot Report" className="span-12 cultivation-code-panel cultivation-report-panel" subtitle="Exportable operator-ready summary from current structural cognition state.">
        <button type="button" className="secondary-command-button" onClick={() => exportPilotReport(reportExport)}>
          Export Weekly Pilot Report
        </button>
        <p className="metadata-text cultivation-ontology-note">
          Ontology snapshot: {Boolean(ontology && Object.keys(ontology).length > 0) ? "available" : "unavailable"}
        </p>
        <pre className="code-surface cultivation-report-surface">{reportExport}</pre>
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

async function loadOntology({ apiFetch, accessCode }) {
  const response = await apiFetch("/api/distributed/cultivation/ontology", {
    headers: accessCode ? { "X-Api-Key": accessCode } : {},
  });
  if (!response.ok) {
    return {};
  }
  return response.json();
}

function buildFallbackCognitionState() {
  return {
    cognition_state: "Monitoring",
    structural_stability: "WATCH",
    active_archetypes: [],
    propagation_pathways: [],
    evidence_lineage: {},
    continuation_windows: { window: "Monitoring" },
    replay_summary: { frame_count: 0, canonical_flow: [] },
    recovery_convergence: {},
    operator_explanation: "Cognition payload is temporarily unavailable. Structural monitoring context remains active.",
  };
}

function buildFallbackReplayTimeline() {
  return {
    timeline: [],
    meta: {
      frame_count: 0,
      canonical_flow: [],
    },
  };
}

function summarizeChange(cognition) {
  return cognition.cognition_state
    ? `${cognition.cognition_state}.`
    : "No active structural change detected.";
}

function summarizeSpread(cognition) {
  const firstPath = cognition.propagation_pathways?.[0];
  return firstPath ? humanizePathway(firstPath) : "No active propagation pathway.";
}

function summarizeTrust(cognition, evidenceSummary) {
  return evidenceSummary[0]
    ?? cognition.operator_explanation
    ?? "Evidence lineage is building from current telemetry context.";
}

function summarizeFrame(frame) {
  const archetypes = frame?.active_archetypes ?? [];
  if (archetypes.length > 0) {
    return `Active archetypes: ${archetypes.slice(0, 2).join(", ")}${archetypes.length > 2 ? "..." : ""}`;
  }
  const pathway = frame?.propagation_state?.dominant_pathway ?? frame?.propagation_state?.pathway;
  if (pathway) {
    return `Propagation: ${humanizePathway(pathway)}`;
  }
  return "Structural state captured for operator review.";
}
