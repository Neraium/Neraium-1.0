import React, { useState } from "react";
import SystemOrbPanel from "./SystemOrbPanel";
import PageContainer from "../../layout/PageContainer";
import { EMPTY_VALUE } from "../../../viewModels/emptyValue";

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
  latestUploadResult = null,
  latestReplayFrame = null,
}) {
  void isLoading;
  const [detailOpen, setDetailOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const hasAdmittedFinding = statusLight !== "gray";
  const uploadDetail = buildUploadDetail(latestUploadResult, latestReplayFrame);
  const canInspectDetails = !isEmptyStructuralState && (hasAdmittedFinding || Boolean(uploadDetail));
  const heartbeat = heartbeatStatus(connectionTone, connectionStatus, lastUpdate);
  function openWorkspace(workspaceId) {
    if (settingsBusy) return;
    if (typeof onWorkspaceNavigate === "function") {
      onWorkspaceNavigate(workspaceId);
    }
    setSettingsOpen(false);
    setAdvancedOpen(false);
    setDetailOpen(false);
  }

  return (
    <PageContainer className="system-body system-body--gate">
      <section className={`system-gate system-gate--${statusLight} ui-state-surface ui-state-surface--${uiState}`} aria-label="The Gate">
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
          <button
            type="button"
            className="system-gate__settings"
            aria-label="Open Gate settings"
            onClick={() => {
              setSettingsOpen((v) => !v);
              setDetailOpen(false);
            }}
          >
            MENU
          </button>
          <div className="system-gate__center" role="button" tabIndex={0} onClick={() => {
            if (!canInspectDetails) return;
            setSettingsOpen(false);
            setDetailOpen(true);
          }} onKeyDown={(event) => {
            if ((event.key === "Enter" || event.key === " ") && canInspectDetails) {
              event.preventDefault();
              setSettingsOpen(false);
              setDetailOpen(true);
            }
          }}>
            <SystemOrbPanel
              systemState={systemState}
              uiState={uiState}
              coherence={coherence}
              stateLabel={stateLabel}
              lastUpdate={lastUpdate}
              focusLabel={focusLabel}
              orbData={orbData}
              compactPreview
            />
            <p className="system-gate__state">{renderGateStateLabel(stateLabel, statusLight)}</p>
            <p className="system-gate__timestamp">{lastUpdate || connectionStatus || EMPTY_VALUE}</p>
            {canInspectDetails ? <p className="system-gate__inspect">{hasAdmittedFinding ? "Inspect Details" : "Inspect Analysis"}</p> : null}
          </div>
          {settingsOpen ? (
            <aside className="system-gate__settings-panel" aria-label="Gate settings panel">
              <ul>
                <li><button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("data-connections")} disabled={settingsBusy}>Data connections</button></li>
                <li><span className="system-gate__settings-message">Data profile: {domainModeLabel(domainMode, domainDetection)}</span></li>
                <li><button type="button" className="system-gate__settings-action" onClick={() => setAdvancedOpen((value) => !value)} disabled={settingsBusy}>{advancedOpen ? "Hide advanced" : "Advanced"}</button></li>
              </ul>
              {advancedOpen ? (
                <div className="system-gate__settings-advanced">
                  <button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("historical-replay")} disabled={settingsBusy}>
                    Open CSV replay
                  </button>
                  <button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("governance-admin")} disabled={settingsBusy}>
                    Governance/admin access
                  </button>
                </div>
              ) : null}
            </aside>
          ) : null}
          {detailOpen && (governedDetail || uploadDetail) ? (
            <aside className="system-gate__detail" aria-label="Governed admitted detail view">
              <header>
                <strong>{governedDetail ? "Gate State Detail" : (uploadDetail?.replayAvailable ? "CSV Replay Detail" : "CSV Analysis Detail")}</strong>
                <button type="button" className="btn btn--secondary" onClick={() => setDetailOpen(false)}>Close</button>
              </header>
              {governedDetail ? (
                <ul>
                  <li><span>Why</span><strong>{governedDetail.why || EMPTY_VALUE}</strong></li>
                  <li><span>Primary Evidence Family</span><strong>{governedDetail.primaryEvidenceFamily || EMPTY_VALUE}</strong></li>
                  <li><span>Corroborating Evidence Families</span><strong>{governedDetail.corroboratingEvidenceFamilies || EMPTY_VALUE}</strong></li>
                  <li><span>Doctrine Rules Satisfied</span><strong>{governedDetail.doctrineRulesSatisfied || EMPTY_VALUE}</strong></li>
                  <li><span>Where</span><strong>{governedDetail.affectedRelationshipPath || EMPTY_VALUE}</strong></li>
                  <li><span>Operational Mapping</span><strong>{governedDetail.operationalMapping || EMPTY_VALUE}</strong></li>
                  <li><span>How Long</span><strong>{governedDetail.elapsedOperationalDuration || EMPTY_VALUE}</strong></li>
                  <li><span>Persistence Count</span><strong>{governedDetail.persistenceCount || EMPTY_VALUE}</strong></li>
                  <li><span>First Admitted Window</span><strong>{governedDetail.firstAdmittedWindow || EMPTY_VALUE}</strong></li>
                  <li><span>Trajectory</span><strong>{governedDetail.trajectory || EMPTY_VALUE}</strong></li>
                  <li><span>Drift Velocity</span><strong>{governedDetail.driftVelocity || EMPTY_VALUE}</strong></li>
                  <li><span>Transition Pressure</span><strong>{governedDetail.transitionPressure || EMPTY_VALUE}</strong></li>
                  <li><span>Relational Stability Trend</span><strong>{governedDetail.relationalStabilityTrend || EMPTY_VALUE}</strong></li>
                  <li><span>Structural Drift Trend</span><strong>{governedDetail.structuralDriftTrend || EMPTY_VALUE}</strong></li>
                  <li><span>Recovery Window Status</span><strong>{governedDetail.recoveryWindowStatus || EMPTY_VALUE}</strong></li>
                  <li><span>Intervention Sensitivity</span><strong>{governedDetail.interventionSensitivity || EMPTY_VALUE}</strong></li>
                  <li><span>Subsystem Affected</span><strong>{governedDetail.affectedSubsystem || EMPTY_VALUE}</strong></li>
                  <li><span>Structural Relationship Evidence</span><strong>{governedDetail.structuralRelationshipEvidence || EMPTY_VALUE}</strong></li>
                  <li><span>Operator Focus</span><strong>{governedDetail.operatorFocus || EMPTY_VALUE}</strong></li>
                  <li><span>EVP Reference</span><strong>{governedDetail.evpPreview || EMPTY_VALUE}</strong></li>
                </ul>
              ) : (
                <>
                  <ul>
                    <li><span>File</span><strong>{uploadDetail.filename || EMPTY_VALUE}</strong></li>
                    <li><span>Source Type</span><strong>{uploadDetail.sourceType || EMPTY_VALUE}</strong></li>
                    <li><span>Assessment</span><strong>{uploadDetail.assessment || EMPTY_VALUE}</strong></li>
                    <li><span>Urgency</span><strong>{uploadDetail.urgency || EMPTY_VALUE}</strong></li>
                    <li><span>State</span><strong>{uploadDetail.state || EMPTY_VALUE}</strong></li>
                    <li><span>Primary Room</span><strong>{uploadDetail.primaryRoom || EMPTY_VALUE}</strong></li>
                    <li><span>Score</span><strong>{uploadDetail.score || EMPTY_VALUE}</strong></li>
                    <li><span>Rows Processed</span><strong>{uploadDetail.rowsProcessed || EMPTY_VALUE}</strong></li>
                    <li><span>Columns Detected</span><strong>{uploadDetail.columnsDetected || EMPTY_VALUE}</strong></li>
                    <li><span>Replay</span><strong>{uploadDetail.replay || EMPTY_VALUE}</strong></li>
                    <li><span>Replay Frames</span><strong>{uploadDetail.replayFrames || EMPTY_VALUE}</strong></li>
                    <li><span>Preview Range</span><strong>{uploadDetail.previewRange || EMPTY_VALUE}</strong></li>
                    <li><span>Replay State</span><strong>{uploadDetail.replayState || EMPTY_VALUE}</strong></li>
                    <li><span>Replay Phase</span><strong>{uploadDetail.replayPhase || EMPTY_VALUE}</strong></li>
                    <li><span>Replay Drift</span><strong>{uploadDetail.replayDrift || EMPTY_VALUE}</strong></li>
                    <li><span>Replay Velocity</span><strong>{uploadDetail.replayVelocity || EMPTY_VALUE}</strong></li>
                    <li><span>Propagation</span><strong>{uploadDetail.replayPropagation || EMPTY_VALUE}</strong></li>
                    <li><span>Replay Confidence</span><strong>{uploadDetail.replayConfidence || EMPTY_VALUE}</strong></li>
                    <li><span>Operational Profile</span><strong>{uploadDetail.operationalProfile || EMPTY_VALUE}</strong></li>
                    <li><span>Operational Confidence</span><strong>{uploadDetail.operationalConfidence || EMPTY_VALUE}</strong></li>
                    <li><span>Operational Modality</span><strong>{uploadDetail.operationalModality || EMPTY_VALUE}</strong></li>
                    <li><span>Operational Signals</span><strong>{uploadDetail.operationalSignals || EMPTY_VALUE}</strong></li>
                  </ul>
                  <div className="system-gate__settings-advanced" style={{ marginTop: "12px" }}>
                    <button
                      type="button"
                      className="system-gate__settings-action"
                      onClick={() => openWorkspace("historical-replay")}
                      disabled={settingsBusy}
                    >
                      Open CSV replay
                    </button>
                  </div>
                </>
              )}
            </aside>
          ) : null}
      </section>
    </PageContainer>
  );
}

function statusLightLabel(light) {
  if (light === "yellow") return "Watch";
  if (light === "red") return "Admission";
  return "Stable";
}

function buildUploadDetail(result, replayFrame) {
  if (!result) return null;

  const intelligence = result?.sii_intelligence ?? {};
  const replayTimeline = intelligence?.replay_timeline?.timeline;
  const fallbackReplayFrame = Array.isArray(replayTimeline) && replayTimeline.length > 0 ? replayTimeline[replayTimeline.length - 1] : null;
  const effectiveReplayFrame = replayFrame && typeof replayFrame === "object" ? replayFrame : fallbackReplayFrame;
  const replayState = effectiveReplayFrame?.cognition_state ?? {};
  const replayTopology = effectiveReplayFrame?.topology_state ?? {};
  const replayPropagation = effectiveReplayFrame?.propagation_state ?? {};
  const replayEvidence = effectiveReplayFrame?.evidence_state ?? {};
  const replayCount = Number(effectiveReplayFrame?.total_frames ?? 0);
  const hasReplayFrame = Boolean(effectiveReplayFrame && typeof effectiveReplayFrame === "object");
  const sourceMetadata = intelligence?.source_metadata ?? {};
  return {
    filename: result?.filename ?? "",
    sourceType: detectSourceType(result, effectiveReplayFrame),
    assessment: String(replayState.facility_state ?? result?.operating_state ?? intelligence?.facility_state ?? "").trim() || "Monitoring",
    urgency: String(result?.drift_status ?? intelligence?.urgency ?? replayState.confidence_tier ?? "").trim() || "info",
    state: String(replayState.facility_state ?? result?.sii_intelligence?.facility_state ?? result?.operating_state ?? "").trim() || "Unknown",
    primaryRoom: String(effectiveReplayFrame?.affected_subsystem ?? effectiveReplayFrame?.affected_area ?? result?.primary_room ?? intelligence?.primary_room ?? "").trim() || "Unknown",
    score: effectiveReplayFrame?.evidence_confidence ?? replayTopology?.drift_index ?? result?.neraium_score ?? intelligence?.neraium_score ?? EMPTY_VALUE,
    rowsProcessed: hasReplayFrame && Number.isFinite(Number(effectiveReplayFrame?.row_start)) && Number.isFinite(Number(effectiveReplayFrame?.row_end))
      ? `${effectiveReplayFrame.row_start} to ${effectiveReplayFrame.row_end}`
      : (result?.rows_processed ?? result?.row_count ?? EMPTY_VALUE),
    columnsDetected: result?.columns_detected ?? result?.column_count ?? EMPTY_VALUE,
    replay: hasReplayFrame || (Array.isArray(replayTimeline) && replayTimeline.length > 0) ? "Available" : "Unavailable",
    replayAvailable: hasReplayFrame || (Array.isArray(replayTimeline) && replayTimeline.length > 0),
    replayFrames: Number.isFinite(replayCount) && replayCount > 0 ? replayCount : (Array.isArray(replayTimeline) ? replayTimeline.length : EMPTY_VALUE),
    previewRange: hasReplayFrame && effectiveReplayFrame?.timestamp_start && effectiveReplayFrame?.timestamp_end
      ? `${effectiveReplayFrame.timestamp_start} to ${effectiveReplayFrame.timestamp_end}`
      : (result?.timestamp_profile?.first_timestamp && result?.timestamp_profile?.last_timestamp
        ? `${result.timestamp_profile.first_timestamp} to ${result.timestamp_profile.last_timestamp}`
        : EMPTY_VALUE),
    replayState: hasReplayFrame ? String(replayState.facility_state ?? EMPTY_VALUE) : EMPTY_VALUE,
    replayPhase: hasReplayFrame ? String(replayState.canonical_phase ?? EMPTY_VALUE).replaceAll("_", " ") : EMPTY_VALUE,
    replayDrift: hasReplayFrame ? (replayTopology.drift_index ?? EMPTY_VALUE) : EMPTY_VALUE,
    replayVelocity: hasReplayFrame ? (effectiveReplayFrame?.drift_velocity ?? EMPTY_VALUE) : EMPTY_VALUE,
    replayPropagation: hasReplayFrame
      ? (
        replayPropagation.dominant_paths?.length
          ? replayPropagation.dominant_paths.join(", ")
          : (Array.isArray(effectiveReplayFrame?.relationship_changes) && effectiveReplayFrame.relationship_changes.length
            ? effectiveReplayFrame.relationship_changes.join(", ")
            : EMPTY_VALUE)
      )
      : EMPTY_VALUE,
    replayConfidence: hasReplayFrame ? String(replayEvidence.corroboration_strength ?? EMPTY_VALUE) : EMPTY_VALUE,
    operationalProfile: normalizeOperationalLabel(
      result?.sii_intelligence?.operational_signal_profile
      ?? result?.sii_intelligence?.system_identity?.operational_profile
      ?? result?.operational_signal_profile
      ?? sourceMetadata?.operational_signal_profile
    ),
    operationalConfidence: normalizeOperationalLabel(
      result?.sii_intelligence?.operational_signal_profile_confidence
      ?? result?.sii_intelligence?.system_identity?.operational_confidence
      ?? result?.operational_signal_profile_confidence
      ?? sourceMetadata?.operational_signal_profile_confidence
    ),
    operationalModality: normalizeOperationalLabel(
      result?.sii_intelligence?.operational_signal_modality
      ?? result?.sii_intelligence?.system_identity?.operational_modality
      ?? result?.operational_signal_modality
      ?? sourceMetadata?.operational_signal_modality
    ),
    operationalSignals: formatOperationalSignals(
      result?.sii_intelligence?.operational_signal_profile_signals
      ?? result?.sii_intelligence?.system_identity?.operational_signals
      ?? result?.operational_signal_profile_signals
      ?? sourceMetadata?.operational_signal_profile_signals
    ),
  };
}

function normalizeOperationalLabel(value) {
  const text = String(value ?? "").trim();
  if (!text) return EMPTY_VALUE;
  return text.replaceAll("_", " ");
}

function formatOperationalSignals(value) {
  if (!Array.isArray(value) || value.length === 0) return EMPTY_VALUE;
  return value.slice(0, 5).join(", ");
}

function detectSourceType(result, replayFrame) {
  const source = String(result?.source ?? result?.sii_intelligence?.source ?? "").toLowerCase();
  const sourceType = String(result?.source_type ?? result?.ingestion_metadata?.source_type ?? result?.sii_intelligence?.source_metadata?.source_type ?? "").toLowerCase();
  const filename = String(result?.filename ?? "").toLowerCase();
  if (source === "rest_poll" || sourceType.includes("rest")) return "Live stream";
  if (filename.endsWith(".json") || sourceType.includes("json")) return "JSON upload";
  if (filename.endsWith(".csv") || source === "uploaded") return "CSV upload";
  if (replayFrame?.timestamp_start || replayFrame?.timestamp_end) return "Replay-derived";
  return "Telemetry input";
}

function renderGateStateLabel(stateLabel, statusLight) {
  const normalized = String(stateLabel || "").trim();
  if (normalized) return normalized;
  return statusLightLabel(statusLight).toUpperCase();
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
