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
        connectionTone,
        connectionStatus,
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
      connectionTone,
      connectionStatus,
    ],
  );
  const heartbeat = heartbeatStatus(connectionTone, connectionStatus, lastUpdate, interpretation.hasTelemetry);

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
              <li><button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("data-connections")}>Upload Data</button></li>
              <li><button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("historical-replay")}>Evidence Replay</button></li>
              <li><button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("observation-center")}>Findings</button></li>
              <li><button type="button" className="system-gate__settings-action" onClick={() => navigateWorkspace("help-changelog")}>Help</button></li>
            </ul>
          </aside>
        ) : null}

        <div className="system-gate__center" style={{ cursor: "default" }}>
          <SystemOrbPanel
            systemState={systemState}
            uiState={uiState}
            coherence={coherence}
            stateLabel={interpretation.structuralState}
            lastUpdate={interpretation.hasTelemetry ? lastUpdate : null}
            focusLabel={interpretation.primaryDriver}
            orbData={orbData}
            compactPreview
          />
          <p className="system-gate__state">{interpretation.structuralState}</p>
        </div>

        <section className="panel system-gate__plate system-gate__plate--summary system-gate__plate--operator" aria-label="System status summary">
          <div className="panel-body">
            <ul className="onboarding-summary">
              <li><span>What changed</span><strong>{interpretation.structuralState}</strong></li>
              <li><span>Why it matters</span><strong>{interpretation.relationshipSummary.text}</strong></li>
              <li><span>Review next</span><strong>{interpretation.nextStep}</strong></li>
              <li><span>Confidence</span><strong>{interpretation.confidence}</strong></li>
            </ul>
            <p className="system-gate__boundary-note">Read-only monitoring. No controls.</p>
          </div>
        </section>

        <div className="system-gate__primary-action">
          <button
            type="button"
            className="command-button"
            onClick={() => navigateWorkspace(interpretation.hasTelemetry ? "observation-center" : "data-connections")}
          >
            {interpretation.hasTelemetry ? "Review Evidence" : "Upload Data"}
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
    structuralState: normalizeStructuralLabel(value.facility_state_label, "No data yet"),
    confidence: String(value.confidence || EMPTY_VALUE),
    primaryDriver: String(value.primary_driver || "None"),
    relationshipSummary: {
      text: simplifyOperatorSummary(backendSummary.text || fallbackSummary || EMPTY_VALUE),
      divergence_severity: String(divergence.severity || backendSummary.divergence_severity || EMPTY_VALUE),
      confidence: String(divergence.confidence || backendSummary.confidence || value.confidence || EMPTY_VALUE),
      affected_systems: Array.isArray(divergence.affected_systems)
        ? divergence.affected_systems
        : (Array.isArray(backendSummary.affected_systems) ? backendSummary.affected_systems : []),
    },
    hasTelemetry: true,
    nextStep: "Review findings.",
  };
}

export function buildSystemInterpretation({ latestUploadSnapshot, latestUploadResult, liveSnapshot, latestReplayFrame = null, fallback = {} }) {
  const latestFrame = latestReplayFrame ?? null;
  const hasTelemetry = hasUsableTelemetry({ latestUploadResult, latestUploadSnapshot, latestReplayFrame: latestFrame });
  const connectionDegraded = isConnectionDegraded(fallback.connectionTone, fallback.connectionStatus);
  const backendSystemInterpretation = latestUploadSnapshot?.system_interpretation
    ?? latestUploadResult?.system_interpretation
    ?? liveSnapshot?.latestUploadSnapshot?.system_interpretation
    ?? null;
  const mappedBackendInterpretation = mapBackendSystemInterpretation(backendSystemInterpretation);
  if (mappedBackendInterpretation) {
    return mappedBackendInterpretation;
  }

  if (!hasTelemetry) {
    return {
      structuralState: "No data yet",
      primaryDriver: "No data yet",
      relationshipSummary: { text: "Upload data to begin." },
      confidence: "Pending",
      nextStep: "Upload data.",
      hasTelemetry: false,
    };
  }

  if (connectionDegraded) {
    return {
      structuralState: "Telemetry interrupted",
      primaryDriver: "Connection degraded",
      relationshipSummary: { text: "Connection is degraded. Latest interpretation may be stale." },
      confidence: "Pending",
      nextStep: "Check connection, then refresh telemetry.",
      hasTelemetry: true,
    };
  }

  const uploadStatus = String(
    latestUploadSnapshot?.status
    ?? latestUploadSnapshot?.processing_state
    ?? latestUploadResult?.processing_state
    ?? "",
  ).toLowerCase();
  const processingLike = ["processing", "queued", "pending", "running_sii", "parsing", "baseline_modeling", "structural_scoring", "generating_replay", "cognition_ready", "writing_state"];
  const hasUploadInFlight = processingLike.some((token) => uploadStatus.includes(token));

  if (hasUploadInFlight) {
    return {
      structuralState: "Processing data",
      confidence: "Interpretation Unavailable",
      primaryDriver: "Interpretation Unavailable",
      relationshipSummary: {
        text: "Review will appear when processing completes.",
        divergence_severity: EMPTY_VALUE,
        confidence: "Interpretation Unavailable",
        affected_systems: [],
      },
      nextStep: "Wait for processing to finish.",
      hasTelemetry: true,
    };
  }

  const sii = latestUploadResult?.sii_intelligence ?? {};
  const rawStructuralState = labelOrFallback(
    latestFrame?.state_label
      ?? latestFrame?.cognition_state?.facility_state
      ?? latestFrame?.cognition_state?.canonical_phase
      ?? sii?.facility_state
      ?? sii?.state_label
      ?? latestUploadResult?.operating_state
      ?? latestUploadSnapshot?.status
      ?? fallback.stateLabel,
    "Monitoring",
  );
  const structuralState = normalizeStructuralLabel(rawStructuralState, "Monitoring");
  const driver = labelOrFallback(
    latestFrame?.primary_driver
      ?? latestFrame?.topology_state?.primary_driver
      ?? sii?.primary_driver
      ?? sii?.dominant_driver
      ?? latestUploadResult?.primary_driver
      ?? fallback.focusLabel,
    "Structural relationship",
  );
  const hasDriftState = describesDrift(structuralState) || describesDrift(driver);
  const relationship = buildRelationshipSummary({ latestUploadResult, latestReplayFrame, sii, fallback, hasDriftState });
  const confidence = formatConfidence(
    latestFrame?.confidence
      ?? latestFrame?.evidence_state?.confidence
      ?? sii?.confidence
      ?? latestUploadResult?.confidence
      ?? null,
    { hasDriftState },
  );

  return {
    structuralState,
    primaryDriver: driver,
    relationshipSummary: relationship,
    confidence,
    nextStep: hasDriftState ? "Review findings." : "Continue monitoring.",
    hasTelemetry: true,
  };
}

function buildRelationshipSummary({ latestUploadResult, latestReplayFrame, sii, fallback, hasDriftState = false }) {
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
  const text = selected ? simplifyOperatorSummary(selected.trim()) : "Interpretation unavailable";
  if (hasDriftState && describesStable(text)) return { text: "Change detected." };
  return { text };
}

function heartbeatStatus(connectionTone, connectionStatus, lastUpdate, hasTelemetry) {
  if (!hasTelemetry) return { tone: "pending", label: "Awaiting telemetry" };
  if (isConnectionDegraded(connectionTone, connectionStatus)) return { tone: "offline", label: "Connection degraded" };
  const text = `${connectionTone ?? ""} ${connectionStatus ?? ""} ${lastUpdate ?? ""}`.toLowerCase();
  if (text.includes("replay")) return { label: "Replay running", tone: "syncing" };
  if (text.includes("sync")) return { label: "Data stream active", tone: "syncing" };
  if (lastUpdate) return { tone: "online", label: "Telemetry active" };
  return { tone: "pending", label: "Awaiting telemetry" };
}

function hasUsableTelemetry({ latestUploadResult, latestUploadSnapshot, latestReplayFrame }) {
  if (latestReplayFrame && Object.keys(latestReplayFrame).length > 0) return true;
  if (latestUploadResult && Object.keys(latestUploadResult).length > 0) return true;
  const status = String(latestUploadSnapshot?.status ?? latestUploadSnapshot?.processing_state ?? "").trim().toLowerCase();
  if (!status || ["empty", "idle", "none", "reset", "no_active_session"].includes(status)) return false;
  return Boolean(latestUploadSnapshot?.last_filename || latestUploadSnapshot?.job_id || latestUploadSnapshot?.latest_result || latestUploadSnapshot?.sii_completed);
}

function normalizeStructuralLabel(value, fallback = EMPTY_VALUE) {
  const text = String(value ?? "").trim();
  const normalized = text.toLowerCase().replaceAll("_", " ");
  if (!text || ["empty", "idle", "none", "null", "undefined"].includes(normalized)) return fallback;
  if (normalized === "no active session" || normalized.includes("baseline pending")) return "No data yet";
  if (normalized.includes("stable") || normalized.includes("nominal")) return "Monitoring";
  if (normalized.includes("drift") || normalized.includes("degrad") || normalized.includes("topology") || normalized.includes("fragment")) return "Change Detected";
  if (normalized.includes("recover")) return "Recovery tracking";
  return simplifyOperatorSummary(text);
}

function simplifyOperatorSummary(value) {
  const replacements = [
    ["structural drift", "system behavior change"],
    ["topology", "relationship pattern"],
    ["regime", "operating pattern"],
    ["baseline separation", "change from the usual pattern"],
    ["deformation", "change"],
    ["drift velocity", "change direction"],
    ["drift acceleration", "change momentum"],
  ];
  return replacements.reduce(
    (text, [term, replacement]) => text.replaceAll(new RegExp(term, "gi"), replacement),
    String(value ?? ""),
  );
}

function isConnectionDegraded(connectionTone, connectionStatus) {
  const text = `${connectionTone ?? ""} ${connectionStatus ?? ""}`.toLowerCase();
  return text.includes("degrad") || text.includes("offline") || text.includes("error") || text.includes("fail") || text.includes("disconnected");
}

function labelOrFallback(value, fallback = EMPTY_VALUE) {
  if (value === null || value === undefined) return fallback;
  const text = String(value).trim();
  return text ? text : fallback;
}

function formatConfidence(value, { hasDriftState = false } = {}) {
  const number = Number(value);
  if (!Number.isFinite(number) || (hasDriftState && number <= 0)) return "Pending";
  if (number <= 0) return "Pending";
  if (number <= 1) return `${Math.round(number * 100)}%`;
  return `${Math.round(number)}%`;
}

function describesDrift(value) {
  const text = String(value ?? "").toLowerCase();
  return text.includes("drift") || text.includes("degrad") || text.includes("unstable") || text.includes("watch") || text.includes("alert");
}

function describesStable(value) {
  const text = String(value ?? "").trim().toLowerCase();
  return text === "stable" || text === "normal" || text === "monitoring" || text === "within range";
}
