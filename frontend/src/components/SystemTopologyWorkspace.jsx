import { useMemo } from "react";
import SystemBodyWorkspace from "./workspaces/SystemBody/SystemBodyWorkspace";
import { normalizeOperationalState } from "../viewModels/operationalUiState";

const STATE = {
  nominal: {
    label: "Stable",
    description: "Infrastructure relationships are stable across the facility envelope.",
  },
  review: {
    label: "Emerging Structural Drift",
    description: "Escalation pressure is increasing as relationships begin to move out of alignment.",
  },
  elevated: {
    label: "Escalating Instability",
    description: "Relationship divergence is visible and now requires focused operator review.",
  },
  unstable: {
    label: "Critical Divergence",
    description: "Cross-system coupling stress is rising and consequence windows are narrowing.",
  },
  info: {
    label: "Baseline Pending",
    description: "Telemetry baseline required before structural deviation assessment is available.",
  },
};

const FALLBACK_STATE = {
  label: "Baseline Pending",
  description: "Telemetry baseline pending. Structural deviation assessment is not yet available.",
  mode: "no-data",
};

export default function SystemTopologyWorkspace({ liveOps, selectedTarget, onSelectTarget }) {
  const rawUiState = normalizeOperationalState(liveOps.facilityTone);
  const awaitingSii = liveOps.intelligenceMode === "empty" || liveOps.intelligenceMode === "processing";
  const uiState = awaitingSii || rawUiState === "neutral" ? "neutral" : rawUiState;
  const state = awaitingSii || uiState === "neutral" ? FALLBACK_STATE : (STATE[liveOps.facilityTone] ?? STATE.info);
  const primaryItem = liveOps.interventionItems?.[0] ?? null;
  const coherence = useMemo(() => {
    const total = (liveOps.relationshipRows ?? []).reduce((sum, row) => sum + Math.abs(Number(row.pair_weight ?? row.change ?? 0)), 0);
    return Math.max(0, Math.min(1, 1 - total));
  }, [liveOps.relationshipRows]);
  const systemState = deriveOrbOperationalState({
    awaitingSii,
    uiState,
    liveOps,
    primaryItem,
  });
  const findings = liveOps.findings?.slice(0, 2) ?? [];
  const primaryMessage = findings[0]?.detail ?? state.description;
  const secondaryMessage = findings[1]?.detail ?? liveOps.heroSubline;
  const awaitingLabel = liveOps.intelligenceMode === "processing"
    ? "Telemetry processing in progress"
    : "Awaiting baseline telemetry";
  const issueType = awaitingSii
    ? awaitingLabel
    : (primaryItem?.title ?? findings[0]?.title ?? liveOps.facilityStateLabel ?? state.label);
  const suspectedLocation = awaitingSii
    ? awaitingLabel
    : (primaryItem?.label ?? liveOps.primaryWindow?.label ?? "Facility scope");
  const runway = awaitingSii
    ? awaitingLabel
    : liveOps.facilityTone === "nominal"
      ? "No elevated progression observed"
      : (primaryItem?.window ?? liveOps.primaryWindow?.window ?? "Progression rate under review");
  const confidence = awaitingSii
    ? awaitingLabel
    : (primaryItem?.supportingEvidence?.length || liveOps.relationshipRows?.length)
      ? "Multi-signal corroboration observed"
      : "Corroboration still developing";
  const primaryEvidence = awaitingSii
    ? awaitingLabel
    : (primaryItem?.supportingEvidence?.[0] ?? findings[0]?.detail ?? "Environmental control relationships diverging from baseline.");
  const relationshipEvidence = awaitingSii
    ? awaitingLabel
    : (primaryItem?.relationshipEvidence?.[0] ?? liveOps.relationshipRows?.[0]?.detail ?? "Subsystem telemetry relationships shifting relative to baseline.");
  const activeArchetype = awaitingSii
    ? awaitingLabel
    : (primaryItem?.activeArchetypes?.[0]?.name?.replaceAll?.("_", " ") ?? "Primary contributing signal under review");
  const propagationPath = awaitingSii
    ? awaitingLabel
    : (primaryItem?.propagationPathways?.[0]?.replaceAll?.("_", " ") ?? "No cross-subsystem spread confirmed.");
  const memoryMatch = awaitingSii
    ? awaitingLabel
    : (primaryItem?.structuralMemoryMatches?.[0]?.label ?? "Historical reference match not yet established.");
  const continuationWindow = awaitingSii
    ? awaitingLabel
    : (primaryItem?.continuationWindow ?? "Progression window under monitoring");
  const facilitySummary = awaitingSii
    ? awaitingLabel
    // TODO(engine-binding): replace heroSubline fallback with an explicit engine output field for baseline divergence/persistence.
    : (primaryItem?.facilityCognitionState ?? liveOps.heroSubline);
  const lastUpdate = liveOps.connectionSummary ?? "Awaiting confirmed update";
  const whyWeThinkThat = awaitingSii || uiState === "neutral"
    ? "Telemetry baseline not available; structural deviation assessment is deferred."
    : (facilitySummary || secondaryMessage || relationshipEvidence);
  const humanRead = awaitingSii || uiState === "neutral"
    ? "Collect additional telemetry windows to establish baseline and persistence context."
    // TODO(engine-binding): liveOps.connectionActionHint is currently a mixed-source hint; replace with deterministic operator action outputs from engine.
    : (liveOps.connectionActionHint || `Review ${propagationPath}; confirm persistence across successive windows.`);
  const where = suspectedLocation;
  void selectedTarget;
  void onSelectTarget;

  const metrics = compactOperationalItems([
    { label: "Progression window", value: runway, priority: true, state: uiState },
    { label: "Current structural state", value: issueType, state: uiState },
    { label: "Operational focus", value: liveOps.primaryWindow?.label ?? where, state: uiState === "stable" ? "stable" : "watch" },
    { label: "Corroboration", value: confidence, state: uiState === "neutral" ? "neutral" : "stable" },
  ]);
  const evidenceItems = compactOperationalItems([
    { label: "Observed structural deviations", value: primaryEvidence, state: uiState },
    { label: "Subsystem relationship changes", value: relationshipEvidence, state: uiState === "stable" ? "stable" : uiState },
    { label: "Primary contributing signals", value: activeArchetype, state: uiState === "neutral" ? "neutral" : "watch" },
  ]);
  const narrativeItems = compactOperationalItems([
    { label: "Primary changes", value: concise(whyWeThinkThat, 92), state: uiState === "stable" ? "stable" : uiState },
    { label: "Infrastructure areas", value: concise(where, 68), state: uiState === "critical" ? "warning" : uiState },
    { label: "Operational focus", value: concise(humanRead, 96), state: uiState === "critical" ? "warning" : "stable" },
  ]);
  const timelineItems = compactOperationalItems([
    { label: "Initial deviation detected", value: concise(lastUpdate, 54), state: "neutral" },
    { label: "Persistence signal", value: concise(confidence, 58), state: uiState === "neutral" ? "neutral" : "stable" },
    { label: "Divergence increasing", value: concise(continuationWindow, 58), state: uiState },
    { label: "Cross-subsystem spread", value: concise(propagationPath || memoryMatch, 66), state: uiState === "neutral" ? "neutral" : uiState },
  ]);

  return (
    <SystemBodyWorkspace
      systemState={systemState}
      uiState={uiState}
      coherence={coherence}
      stateLabel={state.label}
      subtitle={state.description}
      connectionStatus={liveOps.connectionStatusLine}
      connectionTone={liveOps.connectionTone}
      primaryMessage={primaryMessage}
      summaryTitle={state.description}
      narrativeItems={narrativeItems}
      metrics={metrics}
      evidenceItems={evidenceItems}
      timelineItems={timelineItems}
      lastUpdate={lastUpdate}
      focusLabel={where}
      isLoading={awaitingSii}
    />
  );
}
function compactOperationalItems(items) {
  return items.filter((item) => {
    const value = String(item?.value ?? "").trim().toLowerCase();
    return value && value !== "none" && value !== "n/a" && value !== "na";
  });
}

function concise(value, max = 80) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 1)).trimEnd()}...`;
}

function deriveOrbOperationalState({ awaitingSii, uiState, liveOps, primaryItem }) {
  if (awaitingSii || uiState === "neutral") {
    return "unknown";
  }

  const convergenceSignal = String(
    primaryItem?.recoveryConvergence
    ?? liveOps.primaryWindow?.recoveryConvergence
    ?? liveOps.heroSubline
    ?? "",
  ).toLowerCase();
  if (
    convergenceSignal.includes("recover")
    || convergenceSignal.includes("convergen")
    || convergenceSignal.includes("stabiliz")
  ) {
    return "recovery";
  }

  const propagationSignal = String(
    primaryItem?.propagationPathways?.[0]
    ?? liveOps.relationshipRows?.[0]?.detail
    ?? "",
  ).toLowerCase();
  const hasPropagation = propagationSignal.includes("propagation")
    || propagationSignal.includes("spread")
    || propagationSignal.includes("pathway");

  if ((uiState === "critical" || uiState === "warning") && hasPropagation) {
    return "propagation_active";
  }

  if (uiState === "critical" || uiState === "warning") {
    return "drift";
  }

  if (uiState === "watch") {
    return "watching";
  }

  return "stable";
}


