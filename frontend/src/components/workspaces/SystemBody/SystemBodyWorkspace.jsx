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
  const resolvedStatusLight = statusLight === "red" || statusLight === "amber" ? "yellow" : statusLight;

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
        statusLight: resolvedStatusLight,
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
      resolvedStatusLight,
      subtitle,
      lastUpdate,
      isLoading,
      isEmptyStructuralState,
      governedDetail,
    ],
  );
  const stabilitySnapshot = useMemo(
    () => buildStabilitySnapshot({ latestUploadResult, latestReplayFrame }),
    [latestReplayFrame, latestUploadResult],
  );
  const dataConditions = useMemo(
    () => collectDataConditions(latestUploadResult),
    [latestUploadResult],
  );

  function navigateWorkspace(workspaceId) {
    if (typeof onWorkspaceNavigate === "function") {
      onWorkspaceNavigate(workspaceId);
    }
    setMenuOpen(false);
  }

  return (
    <PageContainer className="system-body system-body--gate">
      <section className={`system-gate system-gate--${resolvedStatusLight} ui-state-surface ui-state-surface--${uiState}`} aria-label="System interpretation view">
        <div className={`system-gate__heartbeat system-gate__heartbeat--${heartbeat.tone}`} aria-label={`Neraium platform status: ${heartbeat.label}`}>
          <span className="system-gate__heartbeat-dot" />
          <strong>{heartbeat.label}</strong>
        </div>

        <button
          type="button"
          className="system-gate__settings"
          aria-label="Open workspace menu"
          aria-expanded={menuOpen}
          aria-controls="system-body-menu"
          onClick={() => setMenuOpen((v) => !v)}
        >
          Views
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
                  Structural Replay
                </button>
              </li>
              <li>
                <button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("observation-center")}>
                  Observation Review
                </button>
              </li>
              <li>
                <button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("help-changelog")}>
                  Help / Changelog
                </button>
              </li>
            </ul>
          </aside>
        ) : null}

        <div className="system-gate__layout">
          <div className="system-gate__column system-gate__column--left">
            <section className="panel system-gate__plate system-gate__plate--summary" aria-label="System body home summary">
              <div className="panel-body">
                <ul className="onboarding-summary">
                  <li><span>Current State</span><strong>{interpretation.structuralState}</strong></li>
                  <li><span>Current Reading</span><strong>{interpretation.relationshipSummary.text}</strong></li>
                  <li><span>Evidence Confidence</span><strong>{interpretation.confidence}</strong></li>
                </ul>
              </div>
            </section>
          </div>

          <div className="system-gate__center" style={{ cursor: "default" }}>
            <SystemOrbPanel
              systemState={systemState}
              uiState={uiState}
              coherence={coherence}
              stateLabel={interpretation.structuralState}
              lastUpdate={lastUpdate}
              focusLabel={interpretation.primaryDriver}
              orbData={orbData}
              compactPreview
            />
            <p className="system-gate__state">{interpretation.structuralState}</p>
          </div>

          <div className="system-gate__column system-gate__column--right">
            <section className="panel system-gate__plate system-gate__plate--snapshot" aria-label="Structural stability snapshot">
              <div className="panel-body">
                <ul className="onboarding-summary">
                  <li><span>Current Regime</span><strong>{stabilitySnapshot.regime}</strong></li>
                  <li><span>Drift Magnitude</span><strong>{stabilitySnapshot.driftMagnitude}</strong></li>
                  <li><span>Active Observations</span><strong>{stabilitySnapshot.activeObservations}</strong></li>
                  <li><span>Deformation Age</span><strong>{stabilitySnapshot.deformationAge}</strong></li>
                </ul>
                {dataConditions.length > 0 ? (
                  <div style={{ marginTop: "0.8rem" }}>
                    <p className="section-token">Data Conditions</p>
                    <ul className="compact-list">
                      {dataConditions.slice(0, 3).map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </div>
                ) : null}
              </div>
            </section>

            <section className="panel system-gate__plate system-gate__plate--trust" aria-label="Instrument trust boundaries">
              <div className="panel-body">
                <ul className="onboarding-summary">
                  <li><span>Control Boundary</span><strong>Read-only. No actuation possible.</strong></li>
                  <li><span>Observation Method</span><strong>Structural change only. No severity or instructions.</strong></li>
                  <li><span>Latest Update</span><strong>Observation grammar refined on 2026-06-04.</strong></li>
                </ul>
              </div>
            </section>

            <div className="system-gate__actions">
              <button
                type="button"
                className="command-button"
                onClick={() => navigateWorkspace("observation-center")}
              >
                Review Observations
              </button>
            </div>
          </div>
        </div>

      </section>
    </PageContainer>
  );
}

function buildStabilitySnapshot({ latestUploadResult, latestReplayFrame }) {
  const sii = latestUploadResult?.sii_intelligence ?? {};
  const replay = latestUploadResult?.replay_timeline?.timeline ?? sii?.replay_timeline?.timeline ?? [];
  const frame = latestReplayFrame ?? replay?.[replay.length - 1] ?? null;
  const driftMagnitude = frame?.baseline_distance
    ?? frame?.topology_state?.drift_index
    ?? sii?.instability_index
    ?? "-";
  const startedAt = frame?.timestamp_start
    ?? latestUploadResult?.timestamp_profile?.first_timestamp
    ?? null;
  return {
    regime: sii?.baseline_regime ?? sii?.regime_label ?? "State Group A",
    driftMagnitude: Number.isFinite(Number(driftMagnitude)) ? Number(driftMagnitude).toFixed(2) : String(driftMagnitude ?? "-"),
    activeObservations: String(latestUploadResult?.drift_status ?? "").toLowerCase() === "info" ? 0 : 1,
    deformationAge: ageLabel(startedAt),
  };
}

function collectDataConditions(latestUploadResult) {
  const result = latestUploadResult ?? {};
  const dataQualityWarnings = Array.isArray(result?.data_quality?.warnings) ? result.data_quality.warnings : [];
  const timestampWarnings = Array.isArray(result?.timestamp_profile?.warnings) ? result.timestamp_profile.warnings : [];
  return [...new Set([...dataQualityWarnings, ...timestampWarnings].filter(Boolean).map(String))];
}

function ageLabel(value) {
  if (!value) return "-";
  const ms = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "-";
  const hours = Math.round(ms / 3600000);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

function mapBackendSystemInterpretation(contract) {
  const value = contract && typeof contract === "object" ? contract : null;
  if (!value) return null;

  const divergence = value.relationship_divergence || {};
  const backendSummary = value.relationship_summary || {};
  const fallbackSummary = divergence.summary || value.state_derivation_reason || EMPTY_VALUE;

  return {
    facility_state: String(value.facility_state_label || "No Active Session"),
    structuralState: String(value.facility_state_label || "No Active Session"),
    confidence: String(value.confidence || EMPTY_VALUE),
    primary_driver: String(value.primary_driver || "None"),
    primaryDriver: String(value.primary_driver || "None"),
    relationshipSummary: {
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
    structuralState: fallbackState,
    confidence: "Interpretation Unavailable",
    primaryDriver: "Interpretation Unavailable",
    relationshipSummary: {
      text: hasUploadInFlight ? "Awaiting backend structural interpretation." : "Interpretation Unavailable",
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
