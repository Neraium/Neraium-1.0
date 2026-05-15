import React, { useEffect, useState } from "react";
import { fetchCanonicalCognitionState } from "../../services/api/cognitionApi";
import { fetchReplayTimeline } from "../../services/api/replayApi";
import HealthOrb from "../HealthOrb";

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
  const [activeTab, setActiveTab] = useState("overview");

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
  const orbState = deriveOrbState(cognition, isDemoMode);

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
        <div className="cultivation-tabs" role="tablist" aria-label="Cultivation mission control views">
          {[
            { id: "overview", label: "Overview" },
            { id: "replay", label: "Replay" },
            { id: "evidence", label: "Evidence" },
            { id: "propagation", label: "Propagation" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`cultivation-tab ${activeTab === tab.id ? "is-active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </Panel>
      {activeTab === "overview" && (
        <>
          <Panel title="Overview" className="span-12 cultivation-list-panel cultivation-view-panel cultivation-view-panel--overview" subtitle="Current facility-level structural cognition summary.">
            <div className="cultivation-overview-grid">
              <section className="cultivation-overview-left">
                <div className="cultivation-overview-orb-wrap">
                  <div className="cultivation-overview-orb">
                    <div className="cultivation-overview-orb-field" aria-hidden="true" />
                    <HealthOrb systemState={orbState} intensity={orbStateIntensity(orbState)} />
                  </div>
                  <div className="cultivation-overview-orb-meta">
                    <span>Structural condition</span>
                    <strong>{formatOrbLabel(orbState)}</strong>
                  </div>
                </div>
                <div className="cultivation-overview-left-metrics">
                  <article className="cultivation-overview-pill">
                    <span>Cognition state</span>
                    <strong>{cognition.cognition_state ?? "Monitoring"}</strong>
                  </article>
                  <article className="cultivation-overview-pill">
                    <span>Continuation window</span>
                    <strong>{continuationWindow}</strong>
                  </article>
                  <article className="cultivation-overview-pill">
                    <span>Recovery / convergence</span>
                    <strong>{cognition.recovery_convergence?.convergence_quality ?? "developing"}</strong>
                  </article>
                </div>
              </section>
              <section className="cultivation-overview-right">
                <article className="cultivation-top-summary-card">
                  <span>What's changing</span>
                  <strong>{summarizeChange(cognition)}</strong>
                </article>
                <article className="cultivation-top-summary-card">
                  <span>Where it's spreading</span>
                  <strong>{summarizeSpread(cognition)}</strong>
                </article>
                <article className="cultivation-top-summary-card">
                  <span>Why trust this</span>
                  <strong>{summarizeTrust(cognition, evidenceSummary)}</strong>
                </article>
                <article className="cultivation-top-summary-card">
                  <span>Active archetypes</span>
                  <strong>{summarizeArchetypes(cognition.active_archetypes)}</strong>
                </article>
              </section>
            </div>
          </Panel>
          <Panel title="Weekly Pilot Report" className="span-12 cultivation-code-panel cultivation-report-panel cultivation-view-panel cultivation-view-panel--report" subtitle="Exportable operator-ready summary from current structural cognition state.">
            <button type="button" className="secondary-command-button" onClick={() => exportPilotReport(reportExport)}>
              Export Weekly Pilot Report
            </button>
            <pre className="code-surface cultivation-report-surface">{reportExport}</pre>
          </Panel>
        </>
      )}

      {activeTab === "replay" && (
        <>
          <Panel title="Structural Replay" className="span-12 cultivation-replay-panel cultivation-view-panel cultivation-view-panel--replay" subtitle="Replay timeline and environmental topology progression context.">
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
          <Panel title="Continuation Window Context" className="span-12 cultivation-list-panel cultivation-view-panel cultivation-view-panel--context" subtitle="Continuation window framing during replay review.">
            <div className="cultivation-summary-callouts">
              <p><strong>Continuation window:</strong> {continuationWindow}</p>
              <p><strong>Recovery / convergence:</strong> {cognition.recovery_convergence?.convergence_quality ?? "developing"}</p>
              <p><strong>Replay frames:</strong> {replay.meta?.frame_count ?? 0}</p>
            </div>
          </Panel>
        </>
      )}

      {activeTab === "evidence" && (
        <>
          <Panel title="Evidence Lineage" className="span-12 cultivation-list-panel cultivation-view-panel cultivation-view-panel--evidence" subtitle="Evidence sources, confidence basis, and relationship corroboration.">
            <ul className="system-body-timeline-list cultivation-compact-list">
              {evidenceSummary.map((item) => (
                <li key={item}><span className="metadata-text">Evidence source</span><strong>{item}</strong></li>
              ))}
            </ul>
          </Panel>
          <Panel title="Confidence Basis" className="span-12 cultivation-list-panel cultivation-view-panel cultivation-view-panel--confidence" subtitle="Operational confidence grounded in corroboration and persistence.">
            <div className="cultivation-summary-callouts">
              <p><strong>Confidence basis:</strong> Evidence density + subsystem corroboration + persistence consistency.</p>
              <p><strong>Subsystem corroboration:</strong> {(cognition.propagation_pathways ?? []).length > 0 ? "present" : "limited"}</p>
              <p><strong>Relationship evidence:</strong> {summarizeTrust(cognition, evidenceSummary)}</p>
            </div>
          </Panel>
        </>
      )}

      {activeTab === "propagation" && (
        <>
          <Panel title="Propagation Pathways" className="span-7 cultivation-list-panel cultivation-view-panel cultivation-view-panel--propagation" subtitle="Environmental pressure movement and room-to-room pathway context.">
            <div className="cultivation-propagation-map-wrap">
              <PropagationPulseMap state={orbState} pathways={cognition.propagation_pathways ?? []} />
            </div>
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
            <Panel title="Recovery / Convergence" className="cultivation-list-panel cultivation-stack-panel" subtitle="Room synchronization and convergence state.">
              <div className="cultivation-summary-callouts">
                <p><strong>Room synchronization:</strong> {(cognition.propagation_pathways ?? []).length > 0 ? "drifting" : "stable"}</p>
                <p><strong>Environmental pressure:</strong> {summarizeSpread(cognition)}</p>
                <p><strong>Recovery / convergence:</strong> {cognition.recovery_convergence?.convergence_quality ?? "developing"}</p>
              </div>
            </Panel>
          </div>
        </>
      )}
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

function deriveOrbState(cognition, isDemoMode) {
  if (!cognition) return "unknown";
  const hasSignals = Boolean(
    (cognition.propagation_pathways?.length ?? 0) > 0
    || (cognition.active_archetypes?.length ?? 0) > 0
    || cognition.operator_explanation
  );
  if (!hasSignals && !isDemoMode) return "unknown";

  const recovery = String(cognition.recovery_convergence?.convergence_quality ?? "").toLowerCase();
  if (recovery.includes("recover") || recovery.includes("converg")) return "recovery";

  const pathways = cognition.propagation_pathways?.length ?? 0;
  if (pathways > 1) return "propagation_active";
  if (pathways === 1) return "drift";

  const stability = String(cognition.structural_stability ?? "").toUpperCase();
  if (stability.includes("FRAGMENTING")) return "propagation_active";
  if (stability.includes("DETERIORATING") || stability.includes("WATCH")) return "watching";
  return "stable";
}

function orbStateIntensity(state) {
  if (state === "propagation_active") return 0.95;
  if (state === "drift") return 0.74;
  if (state === "watching") return 0.56;
  if (state === "recovery") return 0.42;
  if (state === "unknown") return 0.2;
  return 0.3;
}

function formatOrbLabel(state) {
  if (state === "propagation_active") return "Propagation active";
  if (state === "drift") return "Structural drift";
  if (state === "watching") return "Watching";
  if (state === "recovery") return "Recovery / convergence";
  if (state === "unknown") return "No upload / unknown";
  return "Stable";
}

function summarizeArchetypes(archetypes = []) {
  if (!archetypes.length) return "No active archetypes.";
  if (archetypes.length === 1) return archetypes[0];
  return `${archetypes[0]}, ${archetypes[1]}${archetypes.length > 2 ? "..." : ""}`;
}

function PropagationPulseMap({ state, pathways }) {
  const active = pathways.length > 0;
  const pathText = active ? pathways[0].replaceAll("_", " -> ") : "No active pathway";
  return (
    <div className={`propagation-map ${active ? "is-active" : "is-idle"} state-${state}`}>
      <svg viewBox="0 0 760 250" role="img" aria-label="Propagation pathway map">
        <defs>
          <linearGradient id="prop-line" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="rgba(110,160,174,0.2)" />
            <stop offset="50%" stopColor="rgba(142,226,205,0.74)" />
            <stop offset="100%" stopColor="rgba(110,160,174,0.2)" />
          </linearGradient>
          <radialGradient id="prop-node" cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="rgba(237,252,246,0.95)" />
            <stop offset="50%" stopColor="rgba(130,220,196,0.74)" />
            <stop offset="100%" stopColor="rgba(130,220,196,0)" />
          </radialGradient>
        </defs>
        <g className="propagation-map__field">
          <ellipse cx="112" cy="126" rx="88" ry="44" className="propagation-map__zone" />
          <ellipse cx="292" cy="92" rx="90" ry="42" className="propagation-map__zone" />
          <ellipse cx="468" cy="158" rx="95" ry="48" className="propagation-map__zone" />
          <ellipse cx="648" cy="112" rx="82" ry="38" className="propagation-map__zone" />
        </g>
        <g className="propagation-map__paths">
          <path d="M116 126 C170 126, 216 104, 292 94" className="propagation-map__path" />
          <path d="M292 94 C348 94, 390 126, 468 154" className="propagation-map__path" />
          <path d="M468 154 C540 154, 574 128, 648 112" className="propagation-map__path" />
        </g>
        <g className="propagation-map__nodes">
          <circle cx="112" cy="126" r="14" className="propagation-map__node" />
          <circle cx="292" cy="94" r="14" className="propagation-map__node" />
          <circle cx="468" cy="154" r="14" className="propagation-map__node" />
          <circle cx="648" cy="112" r="14" className="propagation-map__node" />
        </g>
        <g className="propagation-map__pulse">
          <circle cx="112" cy="126" r="9" className="propagation-map__pulse-node" />
          <circle cx="292" cy="94" r="9" className="propagation-map__pulse-node" />
          <circle cx="468" cy="154" r="9" className="propagation-map__pulse-node" />
          <circle cx="648" cy="112" r="9" className="propagation-map__pulse-node" />
        </g>
      </svg>
      <p className="propagation-map__caption">{pathText}</p>
    </div>
  );
}
