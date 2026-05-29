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

  const [menuOpen, setMenuOpen] = useState(false);


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

  function navigateWorkspace(workspaceId) {
    if (typeof onWorkspaceNavigate === "function") {
      onWorkspaceNavigate(workspaceId);
    }
    setMenuOpen(false);
  }

  function openInvestigationWorkspace() {
    navigateWorkspace("historical-replay");
  }

  return (
    <PageContainer className="system-body system-body--gate">
      <section className={`system-gate system-gate--${statusLight} ui-state-surface ui-state-surface--${uiState}`} aria-label="System interpretation view">
        <div className={`system-gate__heartbeat system-gate__heartbeat--${heartbeat.tone}`} aria-label={`Neraium platform status: ${heartbeat.label}`}>
          <span className="system-gate__heartbeat-dot" />
          <strong>{heartbeat.label}</strong>
        </div>

        <button
          type="button"
          className="system-gate__settings"
          aria-label="Open data menu"
          aria-expanded={menuOpen}
          aria-controls="system-body-menu"
          onClick={() => setMenuOpen((v) => !v)}
        >
          Menu
        </button>

        {menuOpen ? (
          <aside id="system-body-menu" className="system-gate__settings-panel" aria-label="System body navigation menu">
            <ul>
              <li>
                <button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("data-connections")}>
                  Upload CSV / Connect Data
                </button>
              </li>
              <li>
                <button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("data-connections")}>
                  Connect API
                </button>
              </li>
              <li>
                <button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("historical-replay")}>
                  Replay / Investigate
                </button>
              </li>
            </ul>
          </aside>
        ) : null}

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
        </div>

        <section className="panel" aria-label="System body home summary">
          <div className="panel-body">
            <ul className="onboarding-summary">
              <li><span>Current State</span><strong>{interpretation.facility_state}</strong></li>
              <li><span>Main Concern</span><strong>{interpretation.relationship_summary.text}</strong></li>
              <li><span>Confidence</span><strong>{interpretation.confidence}</strong></li>
            </ul>
          </div>
        </section>

        <div style={{ marginTop: "0.8rem" }}>
          <button
            type="button"
            className="command-button"
            onClick={openInvestigationWorkspace}
          >
            Investigate
          </button>
        </div>

      </section>
    </PageContainer>
  );
}

function mapBackendSystemInterpretation(contract) {
  const value = contract && typeof contract === "object" ? contract : null;
  if (!value) return null;

  const divergence = value.relationship_divergence || {};
  const evidencePacket = value.evidence_packet || {};
  const forensic = value.forensic || {};

  const rowCount = Number(evidencePacket.row_count ?? 0);
  const columnCount = Number(evidencePacket.column_count ?? 0);
  const replayFrames = Number(evidencePacket.replay_frame_count ?? 0);
  const timestampCoverage = [evidencePacket.timestamp_start, evidencePacket.timestamp_end].filter(Boolean).join(" to ") || EMPTY_VALUE;

  return {
    facility_state: String(value.facility_state_label || "No Active Session"),
    confidence: String(value.confidence || EMPTY_VALUE),
    instability_index: Number.isFinite(Number(value.instability_index)) ? String(Math.round(Number(value.instability_index))) + "%" : "0%",
    escalation_window: String(value.escalation_window || EMPTY_VALUE),
    primary_driver: String(value.primary_driver || "None"),
    relationship_events: Array.isArray(value.relationship_events) && value.relationship_events.length
      ? value.relationship_events
      : [
          { stage: "onset", summary: "No active telemetry session." },
          { stage: "progression", summary: "Upload or connect a source to begin interpretation." },
          { stage: "escalation", summary: "Escalation tracking starts after first valid session." },
        ],
    evidence: {
      packet_id: String(evidencePacket.packet_id || EMPTY_VALUE),
      filename: String(evidencePacket.filename || EMPTY_VALUE),
      rows_columns: String(rowCount) + " rows / " + String(columnCount) + " columns",
      timestamp_coverage: timestampCoverage,
      replay_frames: String(replayFrames),
      processing_trace: String(evidencePacket.processing_trace_summary || EMPTY_VALUE),
      relationship_snapshot_archived: evidencePacket.relationship_snapshot_archived ? "yes" : "no",
      operator_actions_preserved: evidencePacket.archived ? "yes" : "no",
      confidence_trace_stored: evidencePacket.confidence_trace_stored ? "yes" : "no",
    },
    forecasts: {
      escalation_window: String(value.escalation_window || EMPTY_VALUE),
      projected_state: String(value.facility_state_label || "No Active Session"),
    },
    supporting_signals: Array.isArray(divergence.affected_systems) ? divergence.affected_systems : [],
    relationship_summary: {
      text: relationshipSummaryText(divergence, value),
      divergence_severity: String(divergence.severity || "contained"),
      confidence: String(divergence.confidence || value.confidence || EMPTY_VALUE),
      affected_systems: Array.isArray(divergence.affected_systems) ? divergence.affected_systems : [],
    },
    investigation: {
      relationship_drift: Array.isArray(divergence.top_relationship_changes) ? divergence.top_relationship_changes.join(" | ") : "No active drift relationships in current frame.",
      coupling_degradation: String(value.propagation_scope || "none"),
      instability_propagation: String(value.state_derivation_reason || "Escalation path not established."),
      evidence_reasoning: String(value.state_derivation_reason || "Evidence reasoning derived from backend interpretation."),
    },
    forensic: {
      correlation_matrices: stringifyForensic(forensic.correlation_matrix_summary),
      temporal_relationship_geometry: stringifyForensic(forensic.temporal_geometry_summary),
      evidence_trace: stringifyForensic(evidencePacket.packet_id),
      confidence_lineage: stringifyForensic(forensic.confidence_lineage),
      historical_similarity: stringifyForensic(forensic.historical_similarity_matches),
    },
    debug: {
      source_used: "backend_system_interpretation",
      raw_facility_inputs: String(value.facility_state_enum || EMPTY_VALUE),
      raw_confidence_inputs: String(value.confidence || EMPTY_VALUE),
      raw_instability_inputs: String(value.instability_index ?? EMPTY_VALUE),
      missing_expected_fields: Array.isArray(value.missing_fields) && value.missing_fields.length ? value.missing_fields.join(", ") : "none",
      fallback_values_used: [
        Array.isArray(value.fallback_flags) && value.fallback_flags.length ? `flags: ${value.fallback_flags.join(", ")}` : null,
        Array.isArray(value.fallback_fields) && value.fallback_fields.length ? `fields: ${value.fallback_fields.join(", ")}` : null,
        Array.isArray(value.engine_native_fields) && value.engine_native_fields.length ? `engine: ${value.engine_native_fields.join(", ")}` : null,
        value.interpretation_quality && typeof value.interpretation_quality === "object"
          ? `quality: ${String(value.interpretation_quality.level || "unknown")} (${String(value.interpretation_quality.engine_native_count ?? 0)} native / ${String(value.interpretation_quality.fallback_count ?? 0)} fallback) ${String(value.interpretation_quality.summary || "")}`
          : null,
      ].filter(Boolean).join(" | ") || "none",
    },
  };
}

export function buildSystemInterpretation({ latestUploadSnapshot, latestUploadResult, liveSnapshot, latestReplayFrame = null, fallback = {} }) {
  const backendSystemInterpretation = latestUploadSnapshot?.system_interpretation
    ?? latestUploadResult?.system_interpretation
    ?? liveSnapshot?.latestUploadSnapshot?.system_interpretation
    ?? null;
  const mappedBackendInterpretation = mapBackendSystemInterpretation(backendSystemInterpretation);
  if (mappedBackendInterpretation) {
    return mappedBackendInterpretation;
  }

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

function relationshipSummaryText(divergence, value) {
  const changes = Array.isArray(divergence?.top_relationship_changes) ? divergence.top_relationship_changes : [];
  if (changes.length > 0) {
    const first = changes[0];
    if (first && typeof first === "object") {
      return String(first.summary || first.relationship || value?.state_derivation_reason || "Relationship drift detected.");
    }
    return String(first);
  }
  return String(value?.state_derivation_reason || "System relationships remain coherent with no active divergence.");
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

void EXECUTIVE_STATES;
