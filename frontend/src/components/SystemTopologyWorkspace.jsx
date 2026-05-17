import React, { useMemo } from "react";
import SystemBodyWorkspace from "./workspaces/SystemBody/SystemBodyWorkspace";
import { normalizeOperationalState } from "../viewModels/operationalUiState";
import {
  ESCALATION_LAYERS,
  LIFECYCLE_RAIL_ACTIVE_BASE,
  LIFECYCLE_RAIL_NEUTRAL,
} from "../viewModels/operationalVocabulary";
import { EMPTY_VALUE } from "../viewModels/emptyValue";

const FALLBACK_STATE = {
  label: "Monitoring",
  description: "Telemetry baseline is still forming. Evidence remains insufficient for structural classification.",
};

const STRUCTURAL_PHASES = [
  { label: "Phase 1 - Initial Deviation", description: "Relationship variance detected outside baseline behavior." },
  { label: "Phase 2 - Persistence Confirmation", description: "Repeated multi-window corroboration observed." },
  { label: "Phase 3 - Drift Expansion", description: "Relationship instability propagating across adjacent telemetry groups." },
  { label: "Phase 4 - Structural Instability", description: "Persistent relational divergence exceeding baseline containment." },
  { label: "Phase 5 - Escalation Candidate", description: "Subsystem-level propagation and recovery degradation observed." },
];
export default function SystemTopologyWorkspace({
  liveOps,
  selectedTarget,
  onSelectTarget,
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

  const stateLabel = governed.currentGovernedSystemState || ESCALATION_LAYERS[layer - 1] || FALLBACK_STATE.label;
  const stateDescription = buildStateDescription(layer);
  const primaryItem = liveOps.interventionItems?.[0] ?? null;
  const findings = liveOps.findings?.slice(0, 2) ?? [];

  const coherence = useMemo(() => {
    const total = (liveOps.relationshipRows ?? []).reduce(
      (sum, row) => sum + Math.abs(Number(row.pair_weight ?? row.change ?? 0)),
      0,
    );
    return Math.max(0, Math.min(1, 1 - total));
  }, [liveOps.relationshipRows]);

  const systemState = deriveOrbOperationalState({ awaitingSii, layer, liveOps, primaryItem });
  const primaryMessage = governed.hasPass
    ? concise(governed.passedFindingSummary, 120)
    : "No admitted finding is available for operator display.";

  const focusArea = governed.affectedSubsystem;
  const summaryTitle = governed.hasPass
    ? "Governed PASS Finding"
    : "Governed Output Pending";
  const lastUpdate = liveOps.connectionSummary ?? EMPTY_VALUE;

  const metrics = [];

  const evidenceItems = [];

  const narrativeItems = compactOperationalItems([
    { label: "Current Governed System State", value: governed.currentGovernedSystemState, state: uiState },
    { label: "Affected Subsystem", value: concise(governed.affectedSubsystem, 80), state: uiState },
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
  const hasPass = outcome === "PASS";
  const admittedState = String(governance?.admitted_state ?? "").toUpperCase();
  const statusLight = statusLightFromAdmitted(admittedState, hasPass, uiState);

  if (!hasPass) {
    return {
      hasPass: false,
      statusLight,
      currentGovernedSystemState: "No governed finding",
      passedFindingSummary: "No admitted PASS finding available from Aletheia's Gate.",
      affectedSubsystem: "Not available",
      evidenceBackedOperatorFocus: "Not available",
      persistenceWindowConfirmation: "Not available",
      evpPreview: "Not available",
      timestamp: liveOps.connectionSummary ?? "Not available",
      detail: {
        admittedState: "NONE",
        evidenceSummary: "Not available",
        persistenceConfirmation: "Not available",
        doctrineVersion: "Not available",
        affectedSubsystem: "Not available",
        structuralRelationshipEvidence: "Not available",
        operatorFocus: "Not available",
        telemetryWindowReferences: "Not available",
        evpPreview: "Not available",
      },
    };
  }

  const evpRaw =
    governance?.evp_id
    ?? governance?.evp_hash
    ?? governance?.record_id
    ?? governance?.decision_id
    ?? null;

  return {
    hasPass: true,
    statusLight,
    currentGovernedSystemState: governedStateFromAdmitted(admittedState, uiState),
    passedFindingSummary:
      liveOps?.findings?.[0]?.detail
      ?? "Governed PASS finding is active.",
    affectedSubsystem:
      liveOps?.interventionItems?.[0]?.label
      ?? liveOps?.primaryWindow?.label
      ?? "Facility scope",
    evidenceBackedOperatorFocus:
      liveOps?.interventionItems?.[0]?.recommendation
      ?? "Confirm governed persistence with current operating controls.",
    persistenceWindowConfirmation:
      liveOps?.interventionItems?.[0]?.window
      ?? liveOps?.primaryWindow?.window
      ?? `Layer ${layer} persistence confirmed`,
    evpPreview: showEvpForAdmitted(admittedState) && evpRaw ? previewHash(evpRaw) : "Not displayed for STABLE PASS",
    timestamp: liveOps.connectionSummary ?? "Unavailable",
    detail: {
      admittedState: governedStateFromAdmitted(admittedState, uiState),
      evidenceSummary: liveOps?.findings?.[0]?.detail ?? "Admitted PASS evidence available.",
      persistenceConfirmation: liveOps?.interventionItems?.[0]?.window ?? `Layer ${layer} persistence confirmed`,
      doctrineVersion: governance?.doctrine_version ?? "Unknown doctrine",
      affectedSubsystem:
        liveOps?.interventionItems?.[0]?.label
        ?? liveOps?.primaryWindow?.label
        ?? "Facility scope",
      structuralRelationshipEvidence:
        liveOps?.interventionItems?.[0]?.relationshipEvidence?.[0]
        ?? liveOps?.relationshipRows?.[0]?.detail
        ?? "Not available",
      operatorFocus:
        liveOps?.interventionItems?.[0]?.recommendation
        ?? "Confirm admitted persistence against telemetry controls.",
      telemetryWindowReferences:
        liveOps?.interventionItems?.[0]?.window
        ?? liveOps?.primaryWindow?.window
        ?? "Not available",
      evpPreview: showEvpForAdmitted(admittedState) && evpRaw ? previewHash(evpRaw) : "Not displayed for STABLE PASS",
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

function governedStateFromAdmitted(admittedState, uiState) {
  if (admittedState === "STABLE") return "Admitted stable condition";
  if (admittedState === "WATCH") return "Admitted watch condition";
  if (admittedState === "ALERT") return "Admitted alert condition";
  if (uiState === "stable") return "Governed stable condition";
  if (uiState === "watch") return "Governed watch condition";
  if (uiState === "warning" || uiState === "critical") return "Governed alert condition";
  return "No governed finding";
}

function statusLightFromAdmitted(admittedState, hasPass, uiState) {
  if (!hasPass) return "gray";
  if (admittedState === "STABLE") return "green";
  if (admittedState === "WATCH") return "yellow";
  if (admittedState === "ALERT") return "red";
  return uiState === "stable" ? "green" : uiState === "watch" ? "yellow" : "red";
}

function showEvpForAdmitted(admittedState) {
  return admittedState === "WATCH" || admittedState === "ALERT";
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

function buildLifecycleRail({ awaitingSii, layer }) {
  if (awaitingSii) return LIFECYCLE_RAIL_NEUTRAL;
  return LIFECYCLE_RAIL_ACTIVE_BASE.map((item) => ({
    label: item.label,
    status: item.level < layer ? "Confirmed" : item.level === layer ? "Active" : "Standby",
  }));
}

function buildStructuralProgressionItems(layer) {
  const count = Math.min(Math.max(layer, 4), 5);
  return STRUCTURAL_PHASES.slice(0, count).map((phase, index) => ({
    label: phase.label,
    value: phase.description,
    state: index + 1 <= layer ? "warning" : "neutral",
  }));
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

function deriveOrbOperationalState({ awaitingSii, layer, liveOps, primaryItem }) {
  if (awaitingSii) return "unknown";
  const convergenceSignal = String(primaryItem?.recoveryConvergence ?? liveOps.primaryWindow?.recoveryConvergence ?? liveOps.heroSubline ?? "").toLowerCase();
  if (convergenceSignal.includes("recover") || convergenceSignal.includes("convergen") || convergenceSignal.includes("stabiliz")) {
    return "recovery";
  }
  if (layer >= 7) return "propagation_active";
  if (layer >= 5) return "drift";
  if (layer >= 3) return "watching";
  return "stable";
}
