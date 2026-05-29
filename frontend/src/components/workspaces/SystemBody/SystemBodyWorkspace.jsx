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
  void latestReplayFrame;
  const backendSystemInterpretation = latestUploadSnapshot?.system_interpretation
    ?? latestUploadResult?.system_interpretation
    ?? liveSnapshot?.latestUploadSnapshot?.system_interpretation
    ?? null;
  const mappedBackendInterpretation = mapBackendSystemInterpretation(backendSystemInterpretation);
  if (mappedBackendInterpretation) {
    return mappedBackendInterpretation;
  }

  const uploadStatus = String(
    latestUploadSnapshot?.status
    ?? latestUploadSnapshot?.processing_state
    ?? latestUploadResult?.processing_state
    ?? "",
  ).toLowerCase();
  const processingLike = ["processing", "queued", "pending", "running_sii", "parsing", "baseline_modeling", "structural_scoring", "generating_replay", "cognition_ready", "writing_state"];
  const hasUploadInFlight = processingLike.some((token) => uploadStatus.includes(token));

  const fallbackState = hasUploadInFlight
    ? "Processing Upload"
    : (fallback?.isEmptyStructuralState ? "No Active Session" : "Awaiting Interpretation");

  return {
    facility_state: fallbackState,
    confidence: "Interpretation Unavailable",
    instability_index: "Interpretation Unavailable",
    escalation_window: "Interpretation Unavailable",
    primary_driver: "Interpretation Unavailable",
    relationship_events: [
      { stage: "onset", summary: fallbackState },
      { stage: "progression", summary: "Awaiting backend system interpretation." },
      { stage: "escalation", summary: "Interpretation Unavailable" },
    ],
    evidence: {
      packet_id: EMPTY_VALUE,
      filename: EMPTY_VALUE,
      rows_columns: EMPTY_VALUE,
      timestamp_coverage: EMPTY_VALUE,
      replay_frames: EMPTY_VALUE,
      processing_trace: EMPTY_VALUE,
      relationship_snapshot_archived: "unknown",
      operator_actions_preserved: "unknown",
      confidence_trace_stored: "unknown",
    },
    forecasts: {
      escalation_window: "Interpretation Unavailable",
      projected_state: fallbackState,
    },
    supporting_signals: [],
    relationship_summary: {
      text: hasUploadInFlight ? "Awaiting backend system interpretation." : "Interpretation Unavailable",
      divergence_severity: "Interpretation Unavailable",
      confidence: "Interpretation Unavailable",
      affected_systems: [],
    },
    investigation: {
      relationship_drift: "Interpretation Unavailable",
      coupling_degradation: "Interpretation Unavailable",
      instability_propagation: "Interpretation Unavailable",
      evidence_reasoning: "Interpretation Unavailable",
    },
    forensic: {
      correlation_matrices: EMPTY_VALUE,
      temporal_relationship_geometry: EMPTY_VALUE,
      evidence_trace: EMPTY_VALUE,
      confidence_lineage: EMPTY_VALUE,
      historical_similarity: EMPTY_VALUE,
    },
    debug: {
      source_used: "minimal_fallback",
      raw_facility_inputs: EMPTY_VALUE,
      raw_confidence_inputs: EMPTY_VALUE,
      raw_instability_inputs: EMPTY_VALUE,
      missing_expected_fields: "system_interpretation",
      fallback_values_used: "minimal_neutral_fallback",
    },
  };
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
