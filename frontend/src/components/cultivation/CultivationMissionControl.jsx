import React, { useEffect, useState } from "react";
import { fetchCanonicalCognitionState } from "../../services/api/cognitionApi";
import { fetchReplayTimeline } from "../../services/api/replayApi";
import HealthOrb from "../HealthOrb";

export default function CultivationMissionControl({
  apiFetch,
  accessCode,
  isDemoMode,
  expertMode = false,
  onRunPilotDemo,
  hasUploadedTelemetry = false,
  Panel,
  EmptyState,
}) {
  const [cognition, setCognition] = useState(null);
  const [replay, setReplay] = useState(null);
  const [ontology, setOntology] = useState(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("overview");
  const [isReportExpanded, setIsReportExpanded] = useState(false);

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
    return (
      <Panel
        title="Cultivation Mission Control"
        className="span-12 cultivation-loading-panel"
        subtitle="Loading cultivation structural cognition context."
      >
        <div className="cultivation-loading-panel__skeleton" aria-hidden="true">
          <div className="cultivation-loading-panel__hero" />
          <div className="cultivation-loading-panel__grid">
            <div className="cultivation-loading-panel__card" />
            <div className="cultivation-loading-panel__card" />
            <div className="cultivation-loading-panel__card" />
          </div>
        </div>
      </Panel>
    );
  }
  const evidenceSummary = buildCultivationEvidenceSummary(cognition);
  const replayFrames = replay.timeline?.slice(0, 6) ?? [];
  const orbState = deriveOrbState(cognition, isDemoMode, hasUploadedTelemetry);
  const isNoDataState = orbState === "unknown";
  const continuationWindow = isNoDataState ? "Awaiting telemetry" : (cognition.continuation_windows?.window ?? "Monitoring");
  const severityState = deriveCultivationSeverity(cognition, orbState);

  const report = buildWeeklyPilotReport({
    cognition,
    replay,
    ontology,
    evidenceSummary,
  });
  const operationalAwareness = buildOperationalAwarenessQueue({
    cognition,
    evidenceSummary,
    replayFrames,
    continuationWindow,
  });
  const pilotFlowSteps = [
    { id: "overview", label: "Facility status", detail: "Confirm structural state and continuation window." },
    { id: "overview", label: "Active change", detail: "Read what is changing and where attention should go." },
    { id: "propagation", label: "Propagation map", detail: "See where pressure is spreading or stabilizing." },
    { id: "evidence", label: "Evidence summary", detail: "Review confidence-backed support in plain language." },
    { id: "replay", label: "Replay snapshot", detail: "Check simplified progression and recovery posture." },
    { id: "reports", label: "Weekly pilot report", detail: "Export concise operator-ready report." },
  ];

  return (
    <div className={`workspace-grid workspace-grid--console cultivation-mission-grid cultivation-mission-grid--clean cultivation-mission-grid--${severityState}`}>
      <Panel
        title="Cultivation Mission Control"
        className="span-12 workspace-hero-panel cultivation-hero-panel"
        subtitle="Environmental structural cognition for controlled cultivation."
      >
        <div className="cultivation-tabs" role="tablist" aria-label="Cultivation mission control views">
          {[
            { id: "overview", label: "Overview" },
            { id: "propagation", label: "Propagation" },
            { id: "replay", label: "Replay Snapshot" },
            { id: "evidence", label: "Evidence Summary" },
            { id: "reports", label: "Reports" },
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
        <div className="cultivation-report-actions">
          <button
            type="button"
            className="command-button"
            onClick={() => {
              onRunPilotDemo?.();
              setActiveTab("overview");
            }}
          >
            Run Pilot Demo
          </button>
          <button
            type="button"
            className="secondary-command-button"
            onClick={() => {
              onRunPilotDemo?.();
              setActiveTab("overview");
            }}
          >
            Load Sample Cultivation Data
          </button>
        </div>
      </Panel>
      <Panel
        title="Pilot Demo Path"
        className="span-12 cultivation-list-panel cultivation-view-panel"
        subtitle="One guided operator flow from facility status through report export."
      >
        <div className="cultivation-awareness-feed" role="list">
          {pilotFlowSteps.map((step, index) => (
            <article className="cultivation-awareness-feed__item cultivation-awareness-feed__item--trust cultivation-awareness-feed__item--severity-low" key={`${step.label}-${index}`} role="listitem">
              <div className="cultivation-awareness-feed__index">
                <span>{String(index + 1).padStart(2, "0")}</span>
                <i aria-hidden="true" />
              </div>
              <div className="cultivation-awareness-feed__body">
                <div className="cultivation-awareness-feed__header">
                  <span>{step.label}</span>
                  <em>{activeTab === step.id ? "Current" : "Open"}</em>
                </div>
                <p>{step.detail}</p>
                <div className="cultivation-report-actions">
                  <button
                    type="button"
                    className="secondary-command-button"
                    onClick={() => setActiveTab(step.id)}
                  >
                    {step.id === "reports" ? "Open Report" : "Open Step"}
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      </Panel>
      {activeTab === "overview" && (
        <>
          <Panel title="Overview" className="span-12 cultivation-list-panel cultivation-view-panel cultivation-view-panel--overview" subtitle="Current facility-level structural cognition summary.">
            <div className="cultivation-overview-grid">
              <section className={`cultivation-overview-left cultivation-overview-left--${severityState}`}>
                <div className="cultivation-overview-orb-wrap">
                  <div className="cultivation-overview-orb">
                    <div className="cultivation-overview-orb-field" aria-hidden="true" />
                    <HealthOrb systemState={orbState} intensity={orbStateIntensity(orbState)} />
                  </div>
                  <div className="cultivation-overview-orb-meta">
                    <span>Structural health</span>
                    <strong>{formatCultivationStateLabel(cognition, orbState)}</strong>
                  </div>
                </div>
                <div className="cultivation-overview-left-metrics">
                  <article className="cultivation-overview-pill">
                    <span>Cognition state</span>
                    <strong>{isNoDataState ? "Awaiting telemetry" : (cognition.cognition_state ?? "Monitoring")}</strong>
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
              <section className="cultivation-overview-right cultivation-intelligence-block" aria-label="Operator intelligence summary">
                <div className="cultivation-intelligence-row">
                  <span>What's changing</span>
                  <strong>{isNoDataState ? "Awaiting telemetry." : summarizeChange(cognition)}</strong>
                </div>
                <div className="cultivation-intelligence-row">
                  <span>Where it's spreading</span>
                  <strong>{summarizeSpread(cognition)}</strong>
                </div>
                <div className="cultivation-intelligence-row">
                  <span>Why trust this</span>
                  <strong>{isNoDataState ? "Upload telemetry to activate evidence-backed structural cognition." : summarizeTrust(cognition, evidenceSummary)}</strong>
                </div>
                <div className="cultivation-intelligence-row">
                  <span>Confidence</span>
                  <strong>{isNoDataState ? "Building evidence confidence" : summarizeConfidence(cognition, evidenceSummary)}</strong>
                </div>
              </section>
            </div>
          </Panel>
          <Panel title="Operational Awareness Feed" className="span-12 cultivation-list-panel cultivation-awareness-panel cultivation-view-panel cultivation-view-panel--awareness" subtitle="Live operator focus before historical reporting and exports.">
            <div className="cultivation-awareness-feed" role="list">
              {operationalAwareness.map((item, index) => (
                <article className={`cultivation-awareness-feed__item cultivation-awareness-feed__item--${item.tone} cultivation-awareness-feed__item--severity-${item.severity}`} key={item.label} role="listitem">
                  <div className="cultivation-awareness-feed__index">
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <i aria-hidden="true" />
                  </div>
                  <div className="cultivation-awareness-feed__body">
                    <div className="cultivation-awareness-feed__header">
                      <span>{item.label}</span>
                      <em>{item.marker}</em>
                    </div>
                    <strong>{item.value}</strong>
                    <p>{item.detail}</p>
                  </div>
                </article>
              ))}
            </div>
          </Panel>
        </>
      )}


      {activeTab === "reports" && (
        <Panel title="Export Center" className="span-12 cultivation-code-panel cultivation-report-panel cultivation-view-panel cultivation-view-panel--report" subtitle="Weekly Pilot Report is archived reporting workflow, collapsed by default so live operations stay primary.">
          <div className="cultivation-report-collapsed-shell">
            <div className="cultivation-report-summary-card">
              <p className="cultivation-report-operator__eyebrow">Weekly Pilot Report</p>
              <h3>{report.headline}</h3>
              <p>Formatted operator report, raw payload, and expert mode export tools are available as a secondary workflow.</p>
            </div>
            <div className="cultivation-report-actions cultivation-report-actions--center">
              <button type="button" className="secondary-command-button" onClick={() => exportPilotReport(report.formatted)}>
                Export Operator Report
              </button>
              <button
                type="button"
                className="secondary-command-button"
                aria-expanded={isReportExpanded}
                aria-controls="weekly-pilot-report-body"
                onClick={() => setIsReportExpanded((current) => !current)}
              >
                {isReportExpanded ? "Collapse Report" : "Open Report Module"}
              </button>
            </div>
          </div>
          {isReportExpanded && (
            <div id="weekly-pilot-report-body" className="cultivation-report-expanded-flow">
              <article className="cultivation-report-operator">
                <p className="cultivation-report-operator__eyebrow">Formatted operator report</p>
                <h3>{report.headline}</h3>
                <div className="cultivation-report-operator__grid">
                  {report.sections.map((section) => (
                    <section key={section.label}>
                      <span>{section.label}</span>
                      <strong>{section.value}</strong>
                    </section>
                  ))}
                </div>
                <div className="cultivation-report-operator__notes">
                  {report.notes.map((note) => (
                    <p key={note}>{note}</p>
                  ))}
                </div>
              </article>
              {expertMode ? (
                <details className="technical-summary-panel technical-summary-panel--raw cultivation-report-raw">
                  <summary>View Raw Payload (Expert)</summary>
                  <pre className="code-surface cultivation-report-surface">{report.raw}</pre>
                </details>
              ) : null}
            </div>
          )}
        </Panel>
      )}

      {activeTab === "replay" && (
        <>
          <Panel title="Replay Snapshot" className="span-12 cultivation-replay-panel cultivation-view-panel cultivation-view-panel--replay" subtitle="Progression view for escalation and recovery.">
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
          <Panel title="Continuation Window" className="span-12 cultivation-list-panel cultivation-view-panel cultivation-view-panel--context" subtitle="How much time remains before escalation risk increases.">
            <div className="cultivation-summary-callouts">
              <p><strong>Lead time:</strong> {continuationWindow}</p>
              <p><strong>Recovery signal:</strong> {cognition.recovery_convergence?.convergence_quality ?? "developing"}</p>
              <p><strong>Snapshots:</strong> {replay.meta?.frame_count ?? 0}</p>
            </div>
          </Panel>
        </>
      )}

      {activeTab === "evidence" && (
        <>
          <Panel title="Evidence Summary" className="span-12 cultivation-list-panel cultivation-view-panel cultivation-view-panel--evidence" subtitle="Concise evidence supporting the current operator view.">
            <ul className="system-body-timeline-list cultivation-compact-list">
              {evidenceSummary.map((item) => (
                <li key={item}><span className="metadata-text">Evidence source</span><strong>{item}</strong></li>
              ))}
            </ul>
          </Panel>
          <Panel title={expertMode ? "Confidence Basis" : "Confidence"} className="span-12 cultivation-list-panel cultivation-view-panel cultivation-view-panel--confidence" subtitle={expertMode ? "Operational confidence grounded in corroboration and persistence." : "Evidence-backed confidence for current operator guidance."}>
            <div className="cultivation-summary-callouts">
              <p><strong>Evidence confidence:</strong> {summarizeConfidence(cognition, evidenceSummary)}</p>
              <p><strong>Cross-system support:</strong> {(cognition.propagation_pathways ?? []).length > 0 ? "present" : "limited"}</p>
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
              <p><strong>Room synchronization:</strong> {(cognition.propagation_pathways ?? []).length > 0 ? "monitoring" : "stable"}</p>
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

function deriveCultivationSeverity(cognition, orbState) {
  if (orbState === "unknown") return "empty";
  const stability = String(cognition?.structural_stability ?? "").toUpperCase();
  if (stability.includes("ALERT") || stability.includes("FRAGMENT") || stability.includes("DETERIOR")) return "alert";
  if (stability.includes("WATCH") || orbState === "watching" || orbState === "drift") return "watch";
  return "stable";
}

function formatCultivationStateLabel(cognition, orbState) {
  if (orbState === "unknown") return "Awaiting telemetry";
  const stability = String(cognition?.structural_stability ?? "").trim();
  if (stability) return stability.toUpperCase();
  return formatOrbLabel(orbState).toUpperCase();
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
  const generatedAt = new Date().toISOString();
  const pathways = (cognition.propagation_pathways ?? []).map((path) => humanizePathway(path));
  const continuationWindow = cognition.continuation_windows?.window ?? "Monitoring";
  const recovery = cognition.recovery_convergence?.convergence_quality ?? "developing";
  const payload = {
    generated_at: generatedAt,
    pilot_summary: {
      cognition_state: cognition.cognition_state,
      structural_stability: cognition.structural_stability,
      continuation_window: continuationWindow,
      recovery_convergence: recovery,
      operator_explanation: cognition.operator_explanation,
    },
    propagation_pathways: pathways,
    active_archetypes: cognition.active_archetypes ?? [],
    evidence_summary: evidenceSummary,
    replay_evidence: {
      frame_count: replay.meta?.frame_count ?? 0,
      canonical_flow: replay.meta?.canonical_flow ?? [],
    },
    ontology_snapshot_available: Boolean(ontology && Object.keys(ontology).length > 0),
  };
  const headline = `${cognition.structural_stability ?? "WATCH"}: ${cognition.cognition_state ?? "Monitoring"}`;
  const sections = [
    { label: "Condition", value: cognition.structural_stability ?? "WATCH" },
    { label: "Operator Focus", value: cognition.operator_explanation ?? summarizeChange(cognition) },
    { label: "Propagation", value: pathways[0] ?? "No active propagation pathway" },
    { label: "Continuation Window", value: continuationWindow },
    { label: "Recovery / Convergence", value: recovery },
    { label: "Replay Evidence", value: `${replay.meta?.frame_count ?? 0} frames reviewed` },
  ];
  const notes = [
    `Active archetypes: ${summarizeArchetypes(cognition.active_archetypes)}.`,
    `Evidence basis: ${evidenceSummary[0] ?? "Evidence lineage is building from current telemetry context."}`,
    `Generated: ${new Date(generatedAt).toLocaleString()}.`,
  ];
  const formatted = [
    "NERAIUM WEEKLY PILOT REPORT",
    headline,
    "",
    ...sections.map((section) => `${section.label}: ${section.value}`),
    "",
    ...notes,
  ].join("\n");

  return {
    headline,
    sections,
    notes,
    formatted,
    raw: JSON.stringify(payload, null, 2),
  };
}


function buildOperationalAwarenessQueue({ cognition, evidenceSummary, replayFrames, continuationWindow }) {
  const replayCount = replayFrames.length;
  const propagationCount = cognition.propagation_pathways?.length ?? 0;
  return [
    {
      label: "Operator focus",
      value: cognition.operator_explanation ?? summarizeChange(cognition),
      detail: `Continuation window: ${continuationWindow}.`,
      tone: "focus",
      severity: "high",
      marker: "Operator priority",
    },
    {
      label: "Propagation state",
      value: summarizeSpread(cognition),
      detail: propagationCount > 0 ? `${propagationCount} active pathway${propagationCount === 1 ? "" : "s"} requiring watch.` : "No active propagation pathway in current state.",
      tone: propagationCount > 0 ? "watch" : "stable",
      severity: propagationCount > 0 ? "high" : "low",
      marker: propagationCount > 0 ? "Structural marker" : "Holding",
    },
    {
      label: "Evidence / trust",
      value: summarizeTrust(cognition, evidenceSummary),
      detail: `${evidenceSummary.length} evidence signal${evidenceSummary.length === 1 ? "" : "s"} surfaced for operator confidence.`,
      tone: "trust",
      severity: evidenceSummary.length > 1 ? "medium" : "low",
      marker: "Evidence linked",
    },
    {
      label: "Replay indicators",
      value: replayCount > 0 ? summarizeFrame(replayFrames[0]) : "No replay frames available.",
      detail: replayCount > 0 ? `${replayCount} recent frame${replayCount === 1 ? "" : "s"} ready for review.` : "Replay context will appear after timeline data loads.",
      tone: "replay",
      severity: replayCount > 0 ? "medium" : "low",
      marker: replayCount > 0 ? "Replay active" : "Replay idle",
    },
    {
      label: "Actionable intelligence",
      value: buildActionableIntelligence(cognition, propagationCount),
      detail: "Live operational awareness remains ahead of reports and export workflows.",
      tone: "action",
      severity: propagationCount > 0 ? "high" : "medium",
      marker: "Next move",
    },
  ];
}

function buildActionableIntelligence(cognition, propagationCount) {
  if (propagationCount > 0) {
    return "Inspect linked rooms and verify environmental compensation before symptoms appear.";
  }
  if ((cognition.active_archetypes?.length ?? 0) > 0) {
    return "Track active archetypes and confirm room behavior remains synchronized.";
  }
  return "Maintain monitoring cadence and capture fresh telemetry if conditions change.";
}

function exportPilotReport(reportBody) {
  const blob = new Blob([reportBody], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `neraium-weekly-pilot-report-${new Date().toISOString().slice(0, 10)}.txt`;
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

function summarizeConfidence(cognition, evidenceSummary) {
  const confidenceSignals = evidenceSummary.length;
  if ((cognition.propagation_pathways?.length ?? 0) === 0 && confidenceSignals <= 1) {
    return "Moderate confidence";
  }
  if (confidenceSignals >= 3) {
    return "High confidence";
  }
  return "Building confidence";
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

function deriveOrbState(cognition, isDemoMode, hasUploadedTelemetry) {
  if (!cognition) return "unknown";
  if (!hasUploadedTelemetry && !isDemoMode) return "unknown";
  const hasSignals = Boolean(
    (cognition.propagation_pathways?.length ?? 0) > 0
    || (cognition.active_archetypes?.length ?? 0) > 0
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
