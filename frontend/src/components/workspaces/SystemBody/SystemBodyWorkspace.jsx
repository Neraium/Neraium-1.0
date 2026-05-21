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
  onSignOut = null,
  onUploadComplete = null,
  isLoading = false,
  isEmptyStructuralState = false,
  domainMode = "aquatic",
  domainDetection = null,
  latestUploadResult = null,
}) {
  void isLoading;
  const [detailOpen, setDetailOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const hasAdmittedFinding = statusLight !== "gray";
  const uploadDetail = buildUploadDetail(latestUploadResult);
  const canInspectDetails = hasAdmittedFinding || Boolean(uploadDetail);
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
                <li><button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("data-connections")} disabled={settingsBusy}>Setup & data connections</button></li>
                <li><span className="system-gate__settings-message">Detected data type: {domainModeLabel(domainMode, domainDetection)}</span></li>
                {typeof onSignOut === "function" ? (
                  <li><button type="button" className="system-gate__settings-action" onClick={onSignOut} disabled={settingsBusy}>Sign out</button></li>
                ) : null}
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
                <strong>{governedDetail ? "Gate State Detail" : "CSV Analysis Detail"}</strong>
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

function buildUploadDetail(result) {
  if (!result) return null;

  const intelligence = result?.sii_intelligence ?? {};
  const replayTimeline = intelligence?.replay_timeline?.timeline;
  return {
    filename: result?.filename ?? "",
    assessment: String(result?.operating_state ?? intelligence?.facility_state ?? "").trim() || "Monitoring",
    urgency: String(result?.drift_status ?? intelligence?.urgency ?? "").trim() || "info",
    state: String(result?.sii_intelligence?.facility_state ?? result?.operating_state ?? "").trim() || "Unknown",
    primaryRoom: String(result?.primary_room ?? intelligence?.primary_room ?? "").trim() || "Unknown",
    score: result?.neraium_score ?? intelligence?.neraium_score ?? EMPTY_VALUE,
    rowsProcessed: result?.rows_processed ?? result?.row_count ?? EMPTY_VALUE,
    columnsDetected: result?.columns_detected ?? result?.column_count ?? EMPTY_VALUE,
    replay: Array.isArray(replayTimeline) && replayTimeline.length > 0 ? "Available" : "Unavailable",
    replayAvailable: Array.isArray(replayTimeline) && replayTimeline.length > 0,
    replayFrames: Array.isArray(replayTimeline) ? replayTimeline.length : EMPTY_VALUE,
    previewRange: result?.timestamp_profile?.first_timestamp && result?.timestamp_profile?.last_timestamp
      ? `${result.timestamp_profile.first_timestamp} to ${result.timestamp_profile.last_timestamp}`
      : EMPTY_VALUE,
  };
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
  if (domainDetection && String(domainDetection.source ?? "").toLowerCase() !== "upload_shape") return "Auto-detected";
  const normalized = String(domainMode ?? "").trim().toLowerCase();
  if (normalized === "cultivation") return "Cultivation";
  if (normalized === "aquatic") return "Aquatic";
  return "Auto-detected";
}
