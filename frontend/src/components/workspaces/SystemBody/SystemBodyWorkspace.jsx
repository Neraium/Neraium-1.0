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
          Menu
        </button>

        {menuOpen ? (
          <aside id="system-body-menu" className="system-gate__settings-panel" aria-label="System body navigation menu">
            <ul>
              <li>
                <button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("data-connections")}>
                  Upload Data
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
                  Help
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
    ?? latestUploadResult?.first_timestamp
    ?? null;
  const age = startedAt ? daysBetween(startedAt, Date.now()) : null;
  return {
    regime: labelOrFallback(
      frame?.regime_label
        ?? frame?.state_label
        ?? sii?.regime_label
        ?? latestUploadResult?.operating_state,
      "Pending telemetry",
    ),
    driftMagnitude: formatNumber(driftMagnitude),
    activeObservations: labelOrFallback(
      sii?.active_observations
        ?? frame?.active_observations
        ?? latestUploadResult?.active_observations,
      "0",
    ),
    deformationAge: age !== null ? `${age}d` : "-",
  };
}

function buildSystemInterpretation({
  latestUploadSnapshot,
  latestUploadResult,
  liveSnapshot,
  latestReplayFrame,
  fallback,
}) {
  const sii = latestUploadResult?.sii_intelligence ?? {};
  const latestFrame = latestReplayFrame ?? null;
  const structuralState = labelOrFallback(
    latestFrame?.state_label
      ?? latestFrame?.cognition_state?.facility_state
      ?? latestFrame?.cognition_state?.canonical_phase
      ?? sii?.facility_state
      ?? sii?.state_label
      ?? latestUploadResult?.operating_state
      ?? latestUploadSnapshot?.status
      ?? fallback.stateLabel,
    fallback.isEmptyStructuralState ? "No Active Session" : "Monitoring",
  );
  const driver = labelOrFallback(
    latestFrame?.primary_driver
      ?? latestFrame?.topology_state?.primary_driver
      ?? sii?.primary_driver
      ?? sii?.dominant_driver
      ?? latestUploadResult?.primary_driver
      ?? fallback.focusLabel,
    fallback.isEmptyStructuralState ? "Awaiting telemetry" : "Structural relationship",
  );
  const relationship = buildRelationshipSummary({ latestUploadResult, latestReplayFrame, sii, fallback });
  const confidence = formatConfidence(
    latestFrame?.confidence
      ?? latestFrame?.evidence_state?.confidence
      ?? sii?.confidence
      ?? latestUploadResult?.confidence
      ?? null,
  );

  return {
    structuralState,
    primaryDriver: driver,
    relationshipSummary: relationship,
    confidence,
  };
}

function buildRelationshipSummary({ latestUploadResult, latestReplayFrame, sii, fallback }) {
  const candidates = [
    latestReplayFrame?.why_summary,
    latestReplayFrame?.relationship_summary,
    latestReplayFrame?.topology_state?.relationship_summary,
    latestReplayFrame?.evidence_state?.summary,
    sii?.why_summary,
    sii?.relationship_summary,
    latestUploadResult?.relationship_summary,
    fallback.primaryMessage,
    fallback.subtitle,
  ];
  const selected = candidates.find((item) => typeof item === "string" && item.trim());
  return {
    text: selected ? selected.trim() : "Interpretation Unavailable",
  };
}

function heartbeatStatus(connectionTone, connectionStatus, lastUpdate) {
  const text = `${connectionTone ?? ""} ${connectionStatus ?? ""}`.toLowerCase();
  if (text.includes("degrad") || text.includes("offline") || text.includes("error")) {
    return { tone: "offline", label: "Connection degraded" };
  }
  if (lastUpdate) return { tone: "online", label: "Telemetry active" };
  return { tone: "pending", label: "Awaiting telemetry" };
}

function labelOrFallback(value, fallback = EMPTY_VALUE) {
  if (value === null || value === undefined) return fallback;
  const text = String(value).trim();
  return text ? text : fallback;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return labelOrFallback(value, "-");
  if (Math.abs(number) >= 100) return number.toFixed(0);
  if (Math.abs(number) >= 10) return number.toFixed(1);
  return number.toFixed(2);
}

function formatConfidence(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Interpretation Unavailable";
  if (number <= 1) return `${Math.round(number * 100)}%`;
  return `${Math.round(number)}%`;
}

function daysBetween(start, endMs) {
  const startMs = new Date(start).getTime();
  if (!Number.isFinite(startMs)) return null;
  const diff = Math.max(0, endMs - startMs);
  return Math.max(0, Math.round(diff / 86_400_000));
}

function collectDataConditions(latestUploadResult) {
  const candidates = latestUploadResult?.data_conditions
    ?? latestUploadResult?.quality_flags
    ?? latestUploadResult?.sii_intelligence?.data_conditions
    ?? [];
  if (!Array.isArray(candidates)) return [];
  return candidates.map((item) => String(item ?? "").trim()).filter(Boolean);
}
