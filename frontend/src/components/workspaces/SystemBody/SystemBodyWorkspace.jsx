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
  onDomainModeChange = null,
}) {
  void isLoading;
  const [detailOpen, setDetailOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const hasAdmittedFinding = statusLight !== "gray";
  const heartbeat = heartbeatStatus(connectionTone, connectionStatus, lastUpdate);

  const operatorFocus =
    narrativeItems?.find((item) => item.label?.toLowerCase().includes("operator"))?.value
    || EMPTY_VALUE;

    function openWorkspace(workspaceId) {
      if (settingsBusy) return;
      if (typeof onWorkspaceNavigate === "function") {
        onWorkspaceNavigate(workspaceId);
      }
      setSettingsOpen(false);
      setAdvancedOpen(false);
    }

  async function switchDomainMode(nextMode) {
    if (settingsBusy || typeof onDomainModeChange !== "function" || !nextMode || nextMode === domainMode) return;
    setSettingsBusy(true);
    try {
      await onDomainModeChange(nextMode);
    } finally {
      setSettingsBusy(false);
    }
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
          <button type="button" className="system-gate__settings" aria-label="Open Gate settings" onClick={() => setSettingsOpen((v) => !v)}>
            SET
          </button>
          <div className="system-gate__center" role="button" tabIndex={0} onClick={() => hasAdmittedFinding && setDetailOpen(true)} onKeyDown={(event) => {
            if ((event.key === "Enter" || event.key === " ") && hasAdmittedFinding) {
              event.preventDefault();
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
              orbData={null}
              compactPreview
            />
            <p className="system-gate__state">{renderGateStateLabel(stateLabel, statusLight)}</p>
            <p className="system-gate__timestamp">{lastUpdate || connectionStatus || EMPTY_VALUE}</p>
            {hasAdmittedFinding ? <p className="system-gate__inspect">Tap to Inspect</p> : null}
          </div>
          {settingsOpen ? (
            <aside className="system-gate__settings-panel" aria-label="Gate settings panel">
              <ul>
                <li><button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("data-connections")} disabled={settingsBusy}>Setup & data connections</button></li>
                <li><button type="button" className="system-gate__settings-action" onClick={() => switchDomainMode(domainMode === "aquatic" ? "cultivation" : "aquatic")} disabled={settingsBusy}>{domainMode === "aquatic" ? "Switch to cultivation mode" : "Switch to aquatic mode"}</button></li>
                <li><button type="button" className="system-gate__settings-action" onClick={() => setAdvancedOpen((value) => !value)} disabled={settingsBusy}>{advancedOpen ? "Hide advanced" : "Advanced"}</button></li>
              </ul>
              {advancedOpen ? (
                <div className="system-gate__settings-advanced">
                  <button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("historical-replay")} disabled={settingsBusy}>
                    Replay controls
                  </button>
                  <button type="button" className="system-gate__settings-action" onClick={() => openWorkspace("governance-admin")} disabled={settingsBusy}>
                    Governance/admin access
                  </button>
                </div>
              ) : null}
            </aside>
          ) : null}
          {detailOpen && hasAdmittedFinding && governedDetail ? (
            <aside className="system-gate__detail" aria-label="Governed admitted detail view">
              <header>
                <strong>Gate State Detail</strong>
                <button type="button" className="btn btn--secondary" onClick={() => setDetailOpen(false)}>Close</button>
              </header>
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
