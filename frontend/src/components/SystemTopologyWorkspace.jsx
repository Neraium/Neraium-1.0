import React, { useMemo } from "react";
import SystemBodyWorkspace from "./workspaces/SystemBody/SystemBodyWorkspace";
import { ENABLE_ADMISSION_GATE } from "../config";
import { normalizeOperationalState } from "../viewModels/operationalUiState"; 
import { 
  ESCALATION_LAYERS, 
} from "../viewModels/operationalVocabulary"; 
import { EMPTY_VALUE } from "../viewModels/emptyValue";

const FALLBACK_STATE = {
  label: "Monitoring",
  description: "Telemetry baseline is still forming. Evidence remains insufficient for structural classification.",
};

export default function SystemTopologyWorkspace({ 
  liveOps,
  selectedTarget,
  onSelectTarget,
  apiFetch,
  accessCode,
  onWorkspaceNavigate, 
  onUploadComplete, 
  domainMode = "aquatic",
  onDomainModeChange = null,
}) { 
  const rawUiState = normalizeOperationalState(liveOps.facilityTone);
  const awaitingSii = liveOps.intelligenceMode === "empty" || liveOps.intelligenceMode === "processing";
  const uiState = awaitingSii || rawUiState === "neutral" ? "neutral" : rawUiState;
  const layer = deriveEscalationLayer({ awaitingSii, uiState, liveOps });
  const governed = deriveGovernedOutput(liveOps, {
    awaitingSii,
    uiState,
    layer,
  });

  const stateLabel = awaitingSii
    ? "No Data"
    : (governed.currentGovernedSystemState || ESCALATION_LAYERS[layer - 1] || FALLBACK_STATE.label);
  const stateDescription = buildStateDescription(layer);
  const primaryItem = liveOps.interventionItems?.[0] ?? null;
  const coherence = useMemo(() => {
    const total = (liveOps.relationshipRows ?? []).reduce(
      (sum, row) => sum + Math.abs(Number(row.pair_weight ?? row.change ?? 0)),
      0,
    );
    return Math.max(0, Math.min(1, 1 - total));
  }, [liveOps.relationshipRows]);

  const systemState = orbStateFromStatusLight(governed.statusLight);
  const primaryMessage = awaitingSii
    ? "Upload or connect telemetry to begin monitoring."
    : governed.hasPass
      ? concise(governed.passedFindingSummary, 120)
      : "Stable";

  const focusArea = governed.affectedSubsystem;
  const summaryTitle = governed.hasPass
    ? "Governed PASS Finding"
    : "Governed Output Pending";
  const lastUpdate = liveOps.connectionSummary ?? EMPTY_VALUE;

  const metrics = [];

  const evidenceItems = [];

  const narrativeItems = compactOperationalItems([
    { label: "Current Governed System State", value: governed.currentGovernedSystemState, state: uiState },
    ...(governed.hasPass ? [{ label: "Affected Subsystem", value: concise(governed.affectedSubsystem, 80), state: uiState }] : []),
    { label: "Timestamp", value: governed.timestamp, state: "stable" },
  ]);

  const timelineItems = [];
  const lifecycleRail = [];
  const orbData = buildOrbData(liveOps, primaryItem, coherence, layer);

  void selectedTarget;
  void onSelectTarget;

  return (
    <SystemBodyWorkspace
      systemState={systemState}
      uiState={uiState}
      coherence={coherence}
      stateLabel={stateLabel}
      subtitle={stateDescription}
      connectionStatus={liveOps.connectionStatusLine}
      connectionTone={liveOps.connectionTone}
      dataFreshness={liveOps.dataFreshness}
      siiVerification={liveOps.siiVerification}
      primaryMessage={primaryMessage}
      summaryTitle={summaryTitle}
      narrativeItems={narrativeItems}
      metrics={metrics}
      evidenceItems={evidenceItems}
      timelineItems={timelineItems}
      lastUpdate={lastUpdate}
      focusLabel={focusArea}
      lifecycleRail={lifecycleRail}
      orbData={orbData}
      isLoading={awaitingSii}
      isEmptyStructuralState={awaitingSii || uiState === "neutral"}
      statusLight={governed.statusLight}
      governedOnly
      governedDetail={governed.detail}
      apiFetch={apiFetch}
      accessCode={accessCode}
      onWorkspaceNavigate={onWorkspaceNavigate}
      onUploadComplete={onUploadComplete} 
      domainMode={domainMode}
      onDomainModeChange={onDomainModeChange}
    /> 
  ); 
} 

function deriveGovernedOutput(liveOps, { awaitingSii, uiState, layer }) {
  const intelligence = liveOps?.sourceIntelligence ?? null;
  const governance =
    intelligence?.aletheia_gate
    ?? intelligence?.distributed_cognition_governance
    ?? liveOps?.distributed_cognition_governance
    ?? null;

  const outcome = gateOutcome(governance);
  const admittedState = String(governance?.admitted_state ?? "").toUpperCase();
  const hasPass = ENABLE_ADMISSION_GATE && outcome === "PASS" && ["WATCH", "ALERT"].includes(admittedState);
  const statusLight = statusLightFromAdmitted(admittedState, hasPass);

  if (!hasPass) {
    return {
      hasPass: false,
      statusLight,
      currentGovernedSystemState: awaitingSii ? "No Data" : "Stable",
      passedFindingSummary: "",
      affectedSubsystem: "",
      evidenceBackedOperatorFocus: "",
      persistenceWindowConfirmation: "",
      evpPreview: "",
      timestamp: liveOps.connectionSummary ?? "Not available",
      detail: null,
    };
  }

  const evpRaw =
    governance?.evp_reference?.evp_id
    ?? governance?.evp_reference?.evp_hash
    ?? governance?.evp_id
    ?? governance?.evp_hash
    ?? governance?.record_id
    ?? governance?.decision_id
    ?? null;
  const intervention = liveOps?.interventionItems?.[0] ?? {};
  const primaryWindow = liveOps?.primaryWindow ?? {};
  const finding = liveOps?.findings?.[0] ?? {};
  const relationshipEvidence = governance?.affected_relationship_path
    ?? intervention?.relationshipEvidence?.[0]
    ?? liveOps?.relationshipRows?.[0]?.detail
    ?? "";
  const affectedSubsystem = governance?.affected_subsystem
    ?? intervention?.label
    ?? primaryWindow?.label
    ?? "Facility relationship scope";
  const evidenceSummary = governance?.why_summary
    ?? finding?.detail
    ?? "Doctrine-admitted structural relationship evidence satisfied persistence and corroboration requirements.";
  const persistenceCount = valueOrEmpty(governance?.persistence_count);
  const trajectoryDirection = normalizeTrajectory(governance?.trajectory_direction);
  const recoveryWindowStatus = governance?.recovery_window_status ?? "RECOVERY_WINDOW_UNCLEAR";
  const evpPreview = evpRaw ? previewHash(evpRaw) : "EVP pending server custody";

  return {
    hasPass: true,
    statusLight,
    currentGovernedSystemState: governedStateFromAdmitted(admittedState),
    passedFindingSummary: evidenceSummary,
    affectedSubsystem,
    evidenceBackedOperatorFocus:
      governance?.operator_focus
      ?? intervention?.recommendation
      ?? "Inspect admitted structural relationship path and recovery window status.",
    persistenceWindowConfirmation:
      governance?.elapsed_operational_duration
      ?? intervention?.window
      ?? primaryWindow?.window
      ?? `Layer ${layer} persistence confirmed`,
    evpPreview,
    timestamp: liveOps.connectionSummary ?? "Unavailable",
    detail: {
      admittedState: governedStateFromAdmitted(admittedState),
      why: evidenceSummary,
      primaryEvidenceFamily: governance?.primary_evidence_family ?? "Structural relationship evidence",
      corroboratingEvidenceFamilies: formatList(governance?.corroborating_evidence_families),
      doctrineRulesSatisfied: formatList(governance?.doctrine_rules_satisfied),
      doctrineVersion: governance?.doctrine_version ?? "Unknown doctrine",
      affectedSubsystem,
      affectedRelationshipPath: relationshipEvidence || "Primary subsystem relationship path",
      operationalMapping: governance?.operational_mapping ?? "Operational loop under admitted finding",
      persistenceCount: persistenceCount || "Confirmed",
      firstAdmittedWindow: governance?.first_admitted_window ?? primaryWindow?.window ?? "First Gate-admitted window",
      elapsedOperationalDuration:
        governance?.elapsed_operational_duration
        ?? intervention?.window
        ?? primaryWindow?.window
        ?? "Confirmed operational window",
      trajectory: trajectoryDirection,
      driftVelocity: governance?.drift_velocity ?? `${trajectoryDirection} structural drift`,
      transitionPressure: governance?.transition_pressure ?? (admittedState === "ALERT" ? "High" : "Elevated"),
      relationalStabilityTrend: governance?.relational_stability_trend ?? (admittedState === "ALERT" ? "Degrading" : "Under admitted watch"),
      structuralDriftTrend: governance?.structural_drift_trend ?? trajectoryDirection,
      recoveryWindowStatus,
      interventionSensitivity: governance?.intervention_sensitivity ?? recoveryLanguage(recoveryWindowStatus),
      structuralRelationshipEvidence: relationshipEvidence || "Primary subsystem relationship path",
      operatorFocus:
        governance?.operator_focus
        ?? intervention?.recommendation
        ?? "Inspect admitted structural relationship path and recovery window status.",
      telemetryWindowReferences:
        governance?.first_admitted_window
        ?? intervention?.window
        ?? primaryWindow?.window
        ?? "Gate-admitted telemetry window",
      evpPreview,
    },
  };
}

function gateOutcome(governance) {
  // Aletheia's Gate operator admissibility is strictly binary.
  const normalized = String(
    governance?.gate_outcome
    ?? governance?.validation_status
    ?? governance?.status
    ?? governance?.decision?.status
    ?? "",
  ).toUpperCase();
  if (["PASS", "VALIDATED", "APPROVED"].includes(normalized)) return "PASS";
  // REVIEW and all non-PASS outcomes are non-admitted in operator view.
  return "NO_PASS";
}

function governedStateFromAdmitted(admittedState) {
  if (admittedState === "WATCH") return "Watch";
  if (admittedState === "ALERT") return "Alert";
  return "Stable";
}

function statusLightFromAdmitted(admittedState, hasPass) {
  if (!hasPass) return "gray";
  if (admittedState === "WATCH") return "yellow";
  if (admittedState === "ALERT") return "red";
  return "gray";
}

function orbStateFromStatusLight(statusLight) {
  if (statusLight === "yellow") return "watching";
  if (statusLight === "red") return "propagation_active";
  return "unknown";
}

function valueOrEmpty(value) {
  if (value === null || value === undefined || value === "") return "";
  return String(value);
}

function normalizeTrajectory(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "Stable";
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
}

function formatList(value) {
  if (Array.isArray(value)) return value.filter(Boolean).join("; ");
  return String(value ?? "").trim() || "Doctrine requirements satisfied";
}

function recoveryLanguage(status) {
  if (status === "RECOVERY_WINDOW_CRITICAL") return "Urgent intervention sensitivity";
  if (status === "RECOVERY_WINDOW_NARROWING") return "Elevated intervention sensitivity";
  if (status === "RECOVERY_WINDOW_OPEN") return "Recovery remains responsive to intervention";
  return "Recovery sensitivity unclear";
}

function previewHash(value) {
  const v = String(value ?? "").trim();
  if (!v) return "Unavailable";
  if (v.length <= 12) return v;
  return `${v.slice(0, 6)}...${v.slice(-4)}`;
}

function buildStateDescription(layer) {
  if (layer <= 2) return "Structural relationships remain inside baseline containment with active observation.";
  if (layer === 3) return "Divergence Observed with emerging persistence across recent windows.";
  if (layer === 4) return "Persistent Drift is corroborated across multiple evidence windows.";
  if (layer === 5) return "Structural Instability is exceeding baseline containment assumptions.";
  if (layer === 6) return "Propagation and recovery degradation indicate Escalation Candidate status.";
  return "Critical Escalation conditions indicate fragmented structural relationships and high propagation pressure.";
}

function deriveEscalationLayer({ awaitingSii, uiState, liveOps }) {
  if (awaitingSii || uiState === "neutral") return 2;
  const propagationSignal = String(liveOps.relationshipRows?.[0]?.detail ?? "").toLowerCase();
  const hasPropagation = propagationSignal.includes("propagation") || propagationSignal.includes("spread") || propagationSignal.includes("fragment");
  if (uiState === "stable") return 1;
  if (uiState === "watch") return 3;
  if (uiState === "warning") return hasPropagation ? 5 : 4;
  if (uiState === "critical") return hasPropagation ? 7 : 6;
  return 2;
}

function buildOrbData(liveOps, primaryItem, coherence, layer) {
  const instabilityDensity = Math.round((1 - Math.max(0, Math.min(1, coherence))) * 100);
  const evidenceConfidence = Number(primaryItem?.confidence ?? liveOps.primaryWindow?.confidence ?? 0);
  const propagation = String(primaryItem?.propagationPathways?.[0] ?? liveOps.relationshipRows?.[0]?.detail ?? "");
  const fragmentation = layer >= 5 ? "Relational Fragmentation" : "Contained Relationships";
  const containment = layer >= 5 ? "Containment Boundary Stressed" : "Containment Stable";

  return {
    topologyHealth: ESCALATION_LAYERS[layer - 1],
    propagationDirection: propagation || "Propagation direction under evaluation",
    instabilityDensity: `${instabilityDensity}%`,
    fragmentation,
    containment,
    evidenceConfidence: evidenceConfidence > 0 ? `${evidenceConfidence}%` : "Evidence Insufficient",
  };
}

function compactOperationalItems(items) {
  return items.filter((item) => {
    const value = String(item?.value ?? "").trim().toLowerCase();
    return value && value !== "none" && value !== "n/a" && value !== "na" && value !== "awaiting facility cognition";
  });
}

function concise(value, max = 80) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 1)).trimEnd()}...`;
}

