import React, { useMemo, useState } from "react";
import SystemOrbPanel from "./SystemOrbPanel";
import PageContainer from "../../layout/PageContainer";
import { EMPTY_VALUE } from "../../../viewModels/emptyValue";

const EXECUTIVE_STATES = [
  "Stable",
  "Transitional",
  "Relationship Drift",
  "Structural Degradation",
  "Cascade Risk",
  "Recovery State",
];

export default function SystemBodyWorkspace({
  systemState,
  uiState,
  coherence,
  stateLabel,
  subtitle,
  connectionStatus,
  connectionTone,
  dataFreshness = null,
  siiVerification = null,
  primaryMessage,
  summaryTitle,
  narrativeItems,
  metrics,
  evidenceItems,
  timelineItems,
  lastUpdate,
  focusLabel,
  lifecycleRail = [],
  orbData = null,
  statusLight = "gray",
  governedOnly = false,
  governedDetail = null,
  apiFetch = null,
  accessCode = "",
  onWorkspaceNavigate = null,
  onUploadComplete = null,
  isLoading = false,
  isEmptyStructuralState = false,
  domainMode = "aquatic",
  domainDetection = null,
  latestUploadSnapshot = null,
  latestUploadResult = null,
  liveSnapshot = null,
  latestReplayFrame = null,
  gateProcessing = null,
}) {
  void summaryTitle;
  void narrativeItems;
  void metrics;
  void evidenceItems;
  void timelineItems;
  void lifecycleRail;
  void governedOnly;
  void apiFetch;
  void accessCode;
  void onUploadComplete;

  const [investigationOpen, setInvestigationOpen] = useState(false);
  const [forensicOpen, setForensicOpen] = useState(false);
  const [debugOpen, setDebugOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const heartbeat = heartbeatStatus(connectionTone, connectionStatus, lastUpdate);
  const interpretation = useMemo(
    () => buildSystemInterpretation({
      latestUploadSnapshot,
      latestUploadResult,
      liveSnapshot,
      latestReplayFrame,
      fallback: {
        stateLabel,
        primaryMessage,
        focusLabel,
        statusLight,
        subtitle,
        lastUpdate,
        isLoading,
        isEmptyStructuralState,
        governedDetail,
      },
    }),
    [
      latestUploadSnapshot,
      latestUploadResult,
      liveSnapshot,
      latestReplayFrame,
      stateLabel,
      primaryMessage,
      focusLabel,
      statusLight,
      subtitle,
      lastUpdate,
      isLoading,
      isEmptyStructuralState,
      governedDetail,
    ],
  );

  function openWorkspace(workspaceId) {
    if (typeof onWorkspaceNavigate === "function") {
      onWorkspaceNavigate(workspaceId);
    }
    setSettingsOpen(false);
  }

  return (
    <PageContainer className="system-body system-body--gate">
      <section className={`system-gate system-gate--${statusLight} ui-state-surface ui-state-surface--${uiState}`} aria-label="System interpretation view">
        <div className={`system-gate__heartbeat system-gate__heartbeat--${heartbeat.tone}`} aria-label={`Neraium platform status: ${heartbeat.label}`}>
          <span className="system-gate__heartbeat-dot" />
          <strong>{heartbeat.label}</strong>
          {dataFreshness ? (
            <span className={`system-gate__freshness system-gate__freshness--${dataFreshness.tone}`}>{dataFreshness.label}</span>
          ) : null}
          {siiVerification ? (
            <span className={`system-gate__freshness ${siiVerification.verified ? "system-gate__freshness--live" : "system-gate__freshness--aging"}`}>
              {siiVerification.verified ? "SII Verified" : "SII Pending"}
            </span>
          ) : null}
        </div>

        {gateProcessing?.active ? (
          <div className="system-gate__upload-progress-wrap" aria-label="Processing status">
            <div className="system-gate__upload-progress">
              <span style={{ width: `${Math.max(1, Math.min(99, Number(gateProcessing.percent) || 1))}%` }} />
            </div>
            <span className="system-gate__upload-progress-label">{String(gateProcessing.label || "Processing").slice(0, 64)}</span>
          </div>
        ) : null}

        <button
          type="button"
          className="system-gate__settings"
          aria-label="Open view settings"
          onClick={() => setSettingsOpen((v) => !v)}
        >
          MENU
        </button>

        <div className="system-gate__center" style={{ cursor: "default" }}>
          <SystemOrbPanel
            systemState={systemState}
            uiState={uiState}
            coherence={coherence}
            stateLabel={interpretation.facility_state}
            lastUpdate={lastUpdate}
            focusLabel={interpretation.primary_driver}
            orbData={orbData}
            compactPreview
          />
          <p className="system-gate__state">{interpretation.facility_state}</p>
          <p className="system-gate__timestamp">{lastUpdate || connectionStatus || EMPTY_VALUE}</p>
        </div>

        {settingsOpen ? (
          <aside className="system-gate__settings-panel" aria-label="View settings panel">
            <ul>
              <li>
                <button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("data-connections")}>
                  Data connections
                </button>
              </li>
              <li><span className="system-gate__settings-message">Data profile: {domainModeLabel(domainMode, domainDetection)}</span></li>
              <li>
                <button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("historical-replay")}>
                  Open replay workspace
                </button>
              </li>
            </ul>
          </aside>
        ) : null}

        <section className="panel" aria-label="System state header">
          <header className="panel-header"><h3>System State</h3></header>
          <div className="panel-body">
            <ul className="onboarding-summary">
              <li><span>Facility State</span><strong>{interpretation.facility_state}</strong></li>
              <li><span>Confidence</span><strong>{interpretation.confidence}</strong></li>
              <li><span>Instability Index</span><strong>{interpretation.instability_index}</strong></li>
              <li><span>Escalation Window</span><strong>{interpretation.escalation_window}</strong></li>
              <li><span>Primary Driver</span><strong>{interpretation.primary_driver}</strong></li>
            </ul>
          </div>
        </section>

        <section className="panel" aria-label="Relationship summary">
          <header className="panel-header"><h3>Relationship Summary</h3></header>
          <div className="panel-body">
            <p>{interpretation.relationship_summary.text}</p>
            <ul className="onboarding-summary">
              <li><span>Divergence Severity</span><strong>{interpretation.relationship_summary.divergence_severity}</strong></li>
              <li><span>Confidence</span><strong>{interpretation.relationship_summary.confidence}</strong></li>
              <li><span>Affected Systems</span><strong>{interpretation.relationship_summary.affected_systems.join(", ") || EMPTY_VALUE}</strong></li>
            </ul>
          </div>
        </section>

        <section className="panel" aria-label="Progressive timeline">
          <header className="panel-header"><h3>Timeline</h3></header>
          <div className="panel-body">
            <ul className="system-body-timeline-list">
              {interpretation.relationship_events.map((event) => (
                <li key={`${event.stage}-${event.summary}`}>
                  <span>{event.stage}:</span> <strong>{event.summary}</strong>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <div style={{ marginTop: "0.8rem" }}>
          <button
            type="button"
            className="command-button"
            onClick={() => setInvestigationOpen((v) => !v)}
            aria-expanded={investigationOpen}
            aria-controls="investigation-view"
          >
            {investigationOpen ? "Hide Investigation" : "Investigate"}
          </button>
        </div>

        {investigationOpen ? (
          <section id="investigation-view" className="panel" aria-label="Investigation view">
            <header className="panel-header"><h3>Investigation</h3></header>
            <div className="panel-body">
              <ul className="onboarding-summary">
                <li><span>Subsystem Relationship Drift</span><strong>{interpretation.investigation.relationship_drift}</strong></li>
                <li><span>Coupling Degradation</span><strong>{interpretation.investigation.coupling_degradation}</strong></li>
                <li><span>Instability Propagation</span><strong>{interpretation.investigation.instability_propagation}</strong></li>
                <li><span>Supporting Signals</span><strong>{interpretation.supporting_signals.join(", ") || EMPTY_VALUE}</strong></li>
                <li><span>Evidence Reasoning</span><strong>{interpretation.investigation.evidence_reasoning}</strong></li>
              </ul>

              <div style={{ marginTop: "0.8rem" }}>
                <button
                  type="button"
                  className="secondary-command-button"
                  onClick={() => setForensicOpen((v) => !v)}
                  aria-expanded={forensicOpen}
                  aria-controls="forensic-view"
                >
                  {forensicOpen ? "Hide Forensic Mode" : "Forensic Mode"}
                </button>
              </div>

              {forensicOpen ? (
                <section id="forensic-view" style={{ marginTop: "0.8rem" }}>
                  <ul className="onboarding-summary">
                    <li><span>Correlation Matrices</span><strong>{interpretation.forensic.correlation_matrices}</strong></li>
                    <li><span>Temporal Relationship Geometry</span><strong>{interpretation.forensic.temporal_relationship_geometry}</strong></li>
                    <li><span>Evidence Trace</span><strong>{interpretation.forensic.evidence_trace}</strong></li>
                    <li><span>Confidence Lineage</span><strong>{interpretation.forensic.confidence_lineage}</strong></li>
                    <li><span>Historical Similarity</span><strong>{interpretation.forensic.historical_similarity}</strong></li>
                  </ul>

                  <div style={{ marginTop: "0.8rem" }}>
                    <button
                      type="button"
                      className="secondary-command-button"
                      onClick={() => setDebugOpen((v) => !v)}
                      aria-expanded={debugOpen}
                      aria-controls="forensic-debug-view"
                    >
                      {debugOpen ? "Hide Developer Debug" : "Developer Debug"}
                    </button>
                  </div>

                  {debugOpen ? (
                    <section id="forensic-debug-view" style={{ marginTop: "0.8rem" }} aria-label="Forensic debug fields">
                      <ul className="onboarding-summary">
                        <li><span>Source Used</span><strong>{interpretation.debug.source_used}</strong></li>
                        <li><span>Raw Facility Inputs</span><strong>{interpretation.debug.raw_facility_inputs}</strong></li>
                        <li><span>Raw Confidence Inputs</span><strong>{interpretation.debug.raw_confidence_inputs}</strong></li>
                        <li><span>Raw Instability Inputs</span><strong>{interpretation.debug.raw_instability_inputs}</strong></li>
                        <li><span>Missing Expected Fields</span><strong>{interpretation.debug.missing_expected_fields}</strong></li>
                        <li><span>Fallback Values Used</span><strong>{interpretation.debug.fallback_values_used}</strong></li>
                      </ul>
                    </section>
                  ) : null}
                </section>
              ) : null}
            </div>
          </section>
        ) : null}

        <section className="panel" aria-label="Evidence panel">
          <header className="panel-header"><h3>Evidence</h3></header>
          <div className="panel-body">
            <ul className="onboarding-summary">
              <li><span>Evidence Packet ID</span><strong>{interpretation.evidence.packet_id}</strong></li>
              <li><span>Filename</span><strong>{interpretation.evidence.filename}</strong></li>
              <li><span>Rows / Columns</span><strong>{interpretation.evidence.rows_columns}</strong></li>
              <li><span>Timestamp Coverage</span><strong>{interpretation.evidence.timestamp_coverage}</strong></li>
              <li><span>Replay Frames</span><strong>{interpretation.evidence.replay_frames}</strong></li>
              <li><span>Processing Trace</span><strong>{interpretation.evidence.processing_trace}</strong></li>
              <li><span>Relationship Snapshot Archived</span><strong>{interpretation.evidence.relationship_snapshot_archived}</strong></li>
              <li><span>Operator Actions Preserved</span><strong>{interpretation.evidence.operator_actions_preserved}</strong></li>
              <li><span>Confidence Trace Stored</span><strong>{interpretation.evidence.confidence_trace_stored}</strong></li>
            </ul>
          </div>
        </section>
      </section>
    </PageContainer>
  );
}

export function buildSystemInterpretation({ latestUploadSnapshot, latestUploadResult, liveSnapshot, latestReplayFrame = null, fallback = {} }) {
  const resolvedResult = (latestUploadResult?.latest_result && typeof latestUploadResult.latest_result === "object")
    ? latestUploadResult.latest_result
    : ((latestUploadResult?.latestResult && typeof latestUploadResult.latestResult === "object")
      ? latestUploadResult.latestResult
      : latestUploadResult);

  const intelligence = resolvedResult?.sii_intelligence ?? {};
  const replayTimeline = intelligence?.replay_timeline?.timeline ?? resolvedResult?.replay_timeline?.timeline ?? [];
  const frame = latestReplayFrame && typeof latestReplayFrame === "object"
    ? latestReplayFrame
    : (Array.isArray(replayTimeline) && replayTimeline.length ? replayTimeline[replayTimeline.length - 1] : null);

  const replayState = frame?.cognition_state ?? {};
  const topology = frame?.topology_state ?? {};
  const propagation = frame?.propagation_state ?? {};
  const evidenceState = frame?.evidence_state ?? {};
  const relationshipChanges = Array.isArray(frame?.relationship_changes) ? frame.relationship_changes.filter(Boolean) : [];
  const dominantPaths = Array.isArray(propagation?.dominant_paths) ? propagation.dominant_paths.filter(Boolean) : [];

  const source_used = resolvedResult ? "upload" : (liveSnapshot ? "live" : "none");
  const rawFacilityInputs = [
    replayState?.facility_state,
    intelligence?.facility_state,
    resolvedResult?.operating_state,
    fallback?.stateLabel,
  ].filter((value) => value !== null && value !== undefined && String(value).trim() !== "");
  const rawConfidenceInputs = [
    evidenceState?.corroboration_strength,
    frame?.confidence_tier,
    replayState?.confidence_tier,
    intelligence?.telemetry_profile_confidence,
  ].filter((value) => value !== null && value !== undefined && String(value).trim() !== "");
  const rawInstabilityInputs = [
    frame?.instability_score,
    topology?.instability_score,
    intelligence?.instability_index,
    resolvedResult?.emerging_instability?.instability_score,
  ].filter((value) => value !== null && value !== undefined && String(value).trim() !== "");

  const hasData = Boolean(
    resolvedResult
    || latestUploadSnapshot?.last_filename
    || latestUploadSnapshot?.latest_result
    || liveSnapshot?.latestUploadResult
    || liveSnapshot?.relationshipRows?.length,
  );

  if (!hasData || fallback?.isEmptyStructuralState) {
    return {
      facility_state: "No Active Session",
      confidence: "Calm",
      instability_index: "0%",
      escalation_window: "Awaiting telemetry session",
      primary_driver: "None",
      relationship_events: [
        { stage: "onset", summary: "No active telemetry session." },
        { stage: "progression", summary: "Upload or connect a source to begin interpretation." },
        { stage: "escalation", summary: "Escalation tracking starts after first valid session." },
      ],
      evidence: {
        packet_id: EMPTY_VALUE,
        filename: EMPTY_VALUE,
        rows_columns: EMPTY_VALUE,
        timestamp_coverage: EMPTY_VALUE,
        replay_frames: EMPTY_VALUE,
        processing_trace: EMPTY_VALUE,
        relationship_snapshot_archived: "no",
        operator_actions_preserved: "no",
        confidence_trace_stored: "no",
      },
      forecasts: { escalation_window: "Awaiting telemetry session", projected_state: "No Active Session" },
      supporting_signals: [],
      relationship_summary: {
        text: "No active telemetry session is loaded.",
        divergence_severity: "contained",
        confidence: "Calm",
        affected_systems: ["None"],
      },
      investigation: {
        relationship_drift: "No active drift path.",
        coupling_degradation: "No active coupling degradation.",
        instability_propagation: "No propagation state available.",
        evidence_reasoning: "Evidence reasoning will appear after first processed session.",
      },
      forensic: {
        correlation_matrices: EMPTY_VALUE,
        temporal_relationship_geometry: EMPTY_VALUE,
        evidence_trace: EMPTY_VALUE,
        confidence_lineage: EMPTY_VALUE,
        historical_similarity: EMPTY_VALUE,
      },
      debug: {
        source_used: "none",
        raw_facility_inputs: EMPTY_VALUE,
        raw_confidence_inputs: EMPTY_VALUE,
        raw_instability_inputs: EMPTY_VALUE,
        missing_expected_fields: "latestUploadSnapshot, latestUploadResult, liveSnapshot",
        fallback_values_used: "No Active Session defaults",
      },
    };
  }

  const instabilityRaw = firstPresent(
    frame?.instability_score,
    topology?.instability_score,
    intelligence?.instability_index,
    resolvedResult?.emerging_instability?.instability_score,
    0,
  );
  const instability_index = formatIndex(instabilityRaw);
  const instabilityNumeric = Number(String(instability_index).replace("%", ""));

  const compoundSignals = countTruthy([
    dominantPaths.length > 1,
    relationshipChanges.length > 2,
    Number(frame?.drift_velocity ?? 0) > 0.35,
    String(replayState?.canonical_phase ?? "").toLowerCase().includes("degrad"),
  ]);

  let facility_state = "Stable";
  const normalizedRawState = String(
    replayState?.facility_state
    ?? intelligence?.facility_state
    ?? resolvedResult?.operating_state
    ?? fallback?.stateLabel
    ?? "",
  ).toLowerCase();

  if (normalizedRawState.includes("recovery")) {
    facility_state = "Recovery State";
  } else if (compoundSignals >= 3 || instabilityNumeric >= 75) {
    facility_state = "Cascade Risk";
  } else if (compoundSignals >= 2 || instabilityNumeric >= 55) {
    facility_state = "Structural Degradation";
  } else if (relationshipChanges.length > 0 || dominantPaths.length > 0 || instabilityNumeric >= 25) {
    facility_state = "Relationship Drift";
  } else if (String(latestUploadSnapshot?.status ?? "").toLowerCase().includes("process") || fallback?.isLoading) {
    facility_state = "Transitional";
  }

  const confidence = String(
    evidenceState?.corroboration_strength
    ?? frame?.confidence_tier
    ?? replayState?.confidence_tier
    ?? intelligence?.telemetry_profile_confidence
    ?? EMPTY_VALUE,
  ).replaceAll("_", " ");

  const escalation_window = String(
    intelligence?.projected_time_to_failure
    ?? intelligence?.projected_time_to_failure_hours
    ?? resolvedResult?.projected_time_to_failure
    ?? latestUploadSnapshot?.last_processed_at
    ?? fallback?.lastUpdate
    ?? EMPTY_VALUE,
  );

  const primary_driver = cleanText(
    frame?.affected_subsystem
    ?? frame?.affected_area
    ?? fallback?.focusLabel
    ?? intelligence?.primary_room
    ?? resolvedResult?.primary_room
  ) || "Facility relationship scope";

  const relationship_summary_text = relationshipChanges.length
    ? relationshipChanges[0]
    : dominantPaths.length
      ? `Relationship divergence is propagating through ${dominantPaths.slice(0, 2).join(" and ")}.`
      : (cleanText(fallback?.primaryMessage) || "System relationships remain coherent with no active divergence.");

  const relationship_events = buildTimelineEvents({ replayTimeline, frame, relationshipChanges, dominantPaths, latestUploadSnapshot, resolvedResult });

  const rowCount = firstPresent(resolvedResult?.row_count, resolvedResult?.rows_processed, latestUploadSnapshot?.rows_processed, 0);
  const columnCount = firstPresent(resolvedResult?.column_count, resolvedResult?.columns_detected, latestUploadSnapshot?.columns_detected, 0);
  const timestampCoverage = buildTimestampCoverage(resolvedResult, frame);
  const replayFrames = firstPresent(
    frame?.total_frames,
    latestUploadSnapshot?.replay_frame_count,
    Array.isArray(replayTimeline) ? replayTimeline.length : 0,
    0,
  );
  const processingTrace = buildProcessingTrace(resolvedResult, latestUploadSnapshot);

  const packetId = String(
    resolvedResult?.evidence_packet?.packet_id
    ?? resolvedResult?.decision_integrity?.run_id
    ?? resolvedResult?.job_id
    ?? latestUploadSnapshot?.history?.[0]?.job_id
    ?? EMPTY_VALUE,
  );

  const supporting_signals = [
    ...(Array.isArray(intelligence?.operational_signal_profile_signals) ? intelligence.operational_signal_profile_signals : []),
    ...(Array.isArray(intelligence?.telemetry_profile_signals) ? intelligence.telemetry_profile_signals : []),
  ].filter(Boolean).slice(0, 8);

  const missingExpectedFields = [
    !resolvedResult?.filename && !latestUploadSnapshot?.last_filename ? "filename" : null,
    !resolvedResult?.row_count && !resolvedResult?.rows_processed && !latestUploadSnapshot?.rows_processed ? "row_count" : null,
    !resolvedResult?.column_count && !resolvedResult?.columns_detected && !latestUploadSnapshot?.columns_detected ? "column_count" : null,
    !frame && !(Array.isArray(replayTimeline) && replayTimeline.length) ? "replay_timeline" : null,
    !rawConfidenceInputs.length ? "confidence_inputs" : null,
    !rawInstabilityInputs.length ? "instability_inputs" : null,
  ].filter(Boolean);

  const fallbackValuesUsed = [
    facility_state === "Stable" && !rawFacilityInputs.length ? "facility_state_default_stable" : null,
    confidence === EMPTY_VALUE ? "confidence_empty_value" : null,
    instability_index === "0%" && !rawInstabilityInputs.length ? "instability_default_zero" : null,
    relationship_events[2]?.summary?.includes("Current escalation trajectory") ? "timeline_metadata_fallback" : null,
  ].filter(Boolean);

  return {
    facility_state,
    confidence: confidence || EMPTY_VALUE,
    instability_index,
    escalation_window,
    primary_driver,
    relationship_events,
    evidence: {
      packet_id: packetId,
      filename: String(resolvedResult?.filename ?? latestUploadSnapshot?.last_filename ?? EMPTY_VALUE),
      rows_columns: `${rowCount} rows / ${columnCount} columns`,
      timestamp_coverage: timestampCoverage,
      replay_frames: String(replayFrames),
      processing_trace: processingTrace,
      relationship_snapshot_archived: replayFrames > 0 ? "yes" : "partial",
      operator_actions_preserved: resolvedResult?.decision_integrity ? "yes" : "unknown",
      confidence_trace_stored: confidence && confidence !== EMPTY_VALUE ? "yes" : "partial",
    },
    forecasts: {
      escalation_window,
      projected_state: facility_state,
    },
    supporting_signals,
    relationship_summary: {
      text: relationship_summary_text,
      divergence_severity: normalizeSeverity(instability_index),
      confidence: confidence || EMPTY_VALUE,
      affected_systems: [primary_driver],
    },
    investigation: {
      relationship_drift: relationshipChanges.slice(0, 3).join(" | ") || "No active drift relationships in current frame.",
      coupling_degradation: dominantPaths.join(" | ") || "No active multi-path degradation detected.",
      instability_propagation: relationship_events[2]?.summary || "Escalation path not established.",
      evidence_reasoning: cleanText(fallback?.primaryMessage) || "Evidence reasoning derived from replay topology and corroboration state.",
    },
    forensic: {
      correlation_matrices: stringifyForensic(
        frame?.correlation_matrix
        ?? topology?.correlation_matrix
        ?? resolvedResult?.processing_trace?.correlation_matrix,
      ),
      temporal_relationship_geometry: stringifyForensic(
        frame?.temporal_geometry
        ?? topology?.temporal_geometry
        ?? propagation?.geometry,
      ),
      evidence_trace: stringifyForensic(
        resolvedResult?.processing_trace
        ?? resolvedResult?.decision_integrity
        ?? resolvedResult?.evidence_packet,
      ),
      confidence_lineage: stringifyForensic(
        evidenceState?.lineage_events
        ?? evidenceState?.confidence_lineage
        ?? resolvedResult?.processing_trace?.confidence_lineage,
      ),
      historical_similarity: stringifyForensic(
        intelligence?.structural_memory?.memory_matches
        ?? intelligence?.structural_memory?.retrieval_status
        ?? resolvedResult?.processing_trace?.historical_similarity,
      ),
    },
    debug: {
      source_used,
      raw_facility_inputs: rawFacilityInputs.length ? rawFacilityInputs.join(" | ") : EMPTY_VALUE,
      raw_confidence_inputs: rawConfidenceInputs.length ? rawConfidenceInputs.join(" | ") : EMPTY_VALUE,
      raw_instability_inputs: rawInstabilityInputs.length ? rawInstabilityInputs.join(" | ") : EMPTY_VALUE,
      missing_expected_fields: missingExpectedFields.length ? missingExpectedFields.join(", ") : "none",
      fallback_values_used: fallbackValuesUsed.length ? fallbackValuesUsed.join(", ") : "none",
    },
  };
}

function buildTimelineEvents({ replayTimeline, frame, relationshipChanges, dominantPaths, latestUploadSnapshot, resolvedResult }) {
  if (Array.isArray(replayTimeline) && replayTimeline.length > 0) {
    const first = replayTimeline[0] ?? {};
    const mid = replayTimeline[Math.floor(replayTimeline.length / 2)] ?? {};
    const last = replayTimeline[replayTimeline.length - 1] ?? {};
    return [
      { stage: "onset", summary: summarizeReplayFrame(first) },
      { stage: "progression", summary: summarizeReplayFrame(mid) },
      { stage: "escalation", summary: summarizeReplayFrame(last) },
    ];
  }

  return [
    {
      stage: "onset",
      summary: String(resolvedResult?.timestamp_profile?.first_timestamp ?? latestUploadSnapshot?.created_at ?? "Initial telemetry window captured."),
    },
    {
      stage: "progression",
      summary: relationshipChanges[0] || dominantPaths[0] || "Structural relationships remained under review across processing windows.",
    },
    {
      stage: "escalation",
      summary: String(latestUploadSnapshot?.status ?? resolvedResult?.operating_state ?? frame?.cognition_state?.facility_state ?? "Current escalation trajectory under active evaluation."),
    },
  ];
}

function summarizeReplayFrame(frame) {
  const state = String(frame?.cognition_state?.facility_state ?? frame?.facility_state ?? "").trim();
  const change = Array.isArray(frame?.relationship_changes) && frame.relationship_changes.length ? frame.relationship_changes[0] : "";
  const velocity = Number(frame?.drift_velocity);
  if (change) return `${state || "State"}: ${change}`;
  if (Number.isFinite(velocity)) return `${state || "State"}: drift velocity ${Math.round(velocity * 100) / 100}`;
  return state || "Replay frame available.";
}

function buildTimestampCoverage(resolvedResult, frame) {
  if (frame?.timestamp_start && frame?.timestamp_end) {
    return `${frame.timestamp_start} to ${frame.timestamp_end}`;
  }
  const first = resolvedResult?.timestamp_profile?.first_timestamp;
  const last = resolvedResult?.timestamp_profile?.last_timestamp;
  if (first && last) return `${first} to ${last}`;
  return EMPTY_VALUE;
}

function buildProcessingTrace(resolvedResult, latestUploadSnapshot) {
  const trace = resolvedResult?.processing_trace;
  if (trace && typeof trace === "object") {
    return [
      trace.sii_pipeline_ran ? "SII pipeline ran" : null,
      trace.sii_completed ? "SII completed" : null,
      Number.isFinite(Number(trace.rows_processed)) ? `${trace.rows_processed} rows processed` : null,
      Number.isFinite(Number(trace.columns_analyzed)) ? `${trace.columns_analyzed} columns analyzed` : null,
    ].filter(Boolean).join(" | ") || "Processing trace recorded";
  }
  const status = String(latestUploadSnapshot?.status ?? "").trim();
  return status || EMPTY_VALUE;
}

function stringifyForensic(value) {
  if (value === null || value === undefined || value === "") return EMPTY_VALUE;
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.slice(0, 3).map((item) => stringifyForensic(item)).join(" | ");
  if (typeof value === "object") {
    const entries = Object.entries(value).slice(0, 4).map(([key, val]) => `${key}: ${stringifyForensic(val)}`);
    return entries.join(" | ") || EMPTY_VALUE;
  }
  return String(value);
}

function normalizeSeverity(instabilityIndex) {
  const numeric = Number(String(instabilityIndex).replace("%", ""));
  if (!Number.isFinite(numeric)) return EMPTY_VALUE;
  if (numeric >= 75) return "high";
  if (numeric >= 45) return "elevated";
  return "contained";
}

function formatIndex(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "0%";
  const normalized = Math.max(0, Math.min(100, number <= 1 ? number * 100 : number));
  return `${Math.round(normalized)}%`;
}

function cleanText(value) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text && text !== EMPTY_VALUE ? text : "";
}

function firstPresent(...values) {
  return values.find((value) => value !== null && value !== undefined && value !== "") ?? EMPTY_VALUE;
}

function countTruthy(values) {
  return values.reduce((sum, value) => sum + (value ? 1 : 0), 0);
}

function heartbeatStatus(connectionTone, connectionStatus, lastUpdate) {
  const text = `${connectionTone ?? ""} ${connectionStatus ?? ""} ${lastUpdate ?? ""}`.toLowerCase();
  if (text.includes("offline") || text.includes("disconnected")) {
    return { label: "Offline", tone: "offline" };
  }
  if (text.includes("awaiting") || text.includes("pending")) {
    return { label: "Awaiting telemetry", tone: "syncing" };
  }
  if (text.includes("replay")) {
    return { label: "Replay running", tone: "syncing" };
  }
  if (text.includes("sync")) {
    return { label: "Data stream active", tone: "syncing" };
  }
  if (text.includes("degraded") || text.includes("limited") || text.includes("elevated")) {
    return { label: "Connection degraded", tone: "degraded" };
  }
  return { label: "Neraium online", tone: "online" };
}

function domainModeLabel(domainMode, domainDetection) {
  const source = String(domainDetection?.source ?? "").toLowerCase();
  const confidence = Number(domainDetection?.confidence ?? 0);
  if (source === "unclassified" || source === "default") return "Unclassified";
  if (source !== "upload_shape") return "Auto-detected";
  if (confidence > 0 && confidence < 0.65) return "Uncertain";
  const normalized = String(domainMode ?? "").trim().toLowerCase();
  if (normalized === "cultivation") return "Cultivation";
  if (normalized === "aquatic") return "Aquatic";
  return "Uncertain";
}

void EXECUTIVE_STATES;
