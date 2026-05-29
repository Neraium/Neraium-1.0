import React, { useMemo, useState } from "react";
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
  lastUpdate,
  focusLabel,
  orbData = null,
  statusLight = "gray",
  governedDetail = null,
  onWorkspaceNavigate = null,
  isLoading = false,
  isEmptyStructuralState = false,
  latestUploadSnapshot = null,
  latestUploadResult = null,
  liveSnapshot = null,
  latestReplayFrame = null,
}) {
  void dataFreshness;
  void siiVerification;

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
  const backendSummary = value.relationship_summary || {};
  const fallbackSummary = divergence.summary || value.state_derivation_reason || EMPTY_VALUE;

  return {
    facility_state: String(value.facility_state_label || "No Active Session"),
    confidence: String(value.confidence || EMPTY_VALUE),
    primary_driver: String(value.primary_driver || "None"),
    relationship_summary: {
      text: String(backendSummary.text || fallbackSummary || EMPTY_VALUE),
      divergence_severity: String(divergence.severity || backendSummary.divergence_severity || EMPTY_VALUE),
      confidence: String(divergence.confidence || backendSummary.confidence || value.confidence || EMPTY_VALUE),
      affected_systems: Array.isArray(divergence.affected_systems)
        ? divergence.affected_systems
        : (Array.isArray(backendSummary.affected_systems) ? backendSummary.affected_systems : []),
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
    primary_driver: "Interpretation Unavailable",
    relationship_summary: {
      text: hasUploadInFlight ? "Awaiting backend system interpretation." : "Interpretation Unavailable",
      divergence_severity: EMPTY_VALUE,
      confidence: "Interpretation Unavailable",
      affected_systems: [],
    },
  };
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
