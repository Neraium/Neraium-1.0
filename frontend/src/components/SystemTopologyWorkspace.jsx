import { useMemo } from "react";
import SystemBodyWorkspace from "./workspaces/SystemBody/SystemBodyWorkspace";
import { normalizeOperationalState } from "../viewModels/operationalUiState";

const STATE = {
  nominal: {
    label: "Stable structure",
    description: "Core system relationships are holding steady across the facility.",
  },
  review: {
    label: "Relationship drift",
    description: "The structure is still intact, but system relationships are starting to pull out of alignment.",
  },
  elevated: {
    label: "Structural separation",
    description: "Facility systems are fragmenting and need attention before signal thresholds fail harder.",
  },
  unstable: {
    label: "Structural separation",
    description: "Facility systems are fragmenting and need attention before signal thresholds fail harder.",
  },
  info: {
    label: "Awaiting baseline",
    description: "Connect telemetry or upload a baseline source to activate live structural health.",
  },
};

const FALLBACK_STATE = {
  label: "Awaiting baseline",
  description: "Telemetry baseline pending. The orb remains in standby until live infrastructure evidence arrives.",
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
  const sourceLabel = liveOps.dataSourceLabel ?? "Awaiting data";
  const awaitingLabel = liveOps.intelligenceMode === "processing" ? "SII analysis running" : "Awaiting SII analysis";
  const issueType = awaitingSii ? awaitingLabel : (primaryItem?.title ?? findings[0]?.title ?? liveOps.facilityStateLabel ?? state.label);
  const suspectedLocation = awaitingSii ? awaitingLabel : (primaryItem?.label ?? liveOps.primaryWindow?.label ?? "Location not isolated");
  const runway = awaitingSii
    ? awaitingLabel
    : liveOps.facilityTone === "nominal"
      ? "Stable - no immediate constraint"
      : (primaryItem?.projectedTimeToFailure ?? primaryItem?.window ?? liveOps.primaryWindow?.window ?? "Runway unavailable");
  const urgency = awaitingSii ? awaitingLabel : (primaryItem?.status ?? liveOps.primaryWindow?.status ?? state.label);
  const confidence = awaitingSii
    ? awaitingLabel
    : (Number.isFinite(primaryItem?.confidence) ? `${primaryItem.confidence}% evidence quality` : (liveOps.readinessLabel ?? "Evidence building"));
  const primaryEvidence = awaitingSii
    ? awaitingLabel
    : (primaryItem?.supportingEvidence?.[0] ?? findings[0]?.detail ?? "Baseline relationships are being monitored for early divergence.");
  const relationshipEvidence = awaitingSii
    ? awaitingLabel
    : (primaryItem?.relationshipEvidence?.[0] ?? liveOps.relationshipRows?.[0]?.detail ?? "Infrastructure relationships are currently holding within the observed envelope.");
  const activeArchetype = awaitingSii
    ? awaitingLabel
    : (primaryItem?.activeArchetypes?.[0]?.name?.replaceAll?.("_", " ") ?? "Stable operating pattern");
  const propagationPath = awaitingSii
    ? awaitingLabel
    : (primaryItem?.propagationPathways?.[0]?.replaceAll?.("_", " ") ?? "No escalation pathway currently active.");
  const memoryMatch = awaitingSii
    ? awaitingLabel
    : (primaryItem?.structuralMemoryMatches?.[0]?.label ?? "Current pattern remains within recent operating memory.");
  const continuationWindow = awaitingSii
    ? awaitingLabel
    : (primaryItem?.continuationWindow ?? "Monitoring");
  const facilityCognitionState = awaitingSii
    ? awaitingLabel
    : (primaryItem?.facilityCognitionState ?? liveOps.heroSubline);
  const lastUpdate = liveOps.connectionSummary ?? "Awaiting confirmed update";
  const whyWeThinkThat = awaitingSii || uiState === "neutral"
    ? "The workspace is waiting for a usable telemetry baseline or backend evidence stream."
    : (facilityCognitionState || secondaryMessage || relationshipEvidence);
  const humanRead = awaitingSii || uiState === "neutral"
    ? "The structural view is in standby while Neraium waits for a confirmed telemetry baseline."
    : (liveOps.connectionActionHint || `Monitor ${propagationPath} and schedule operator review if structural pressure persists.`);
  const where = suspectedLocation;
  void selectedTarget;
  void onSelectTarget;

  const metrics = compactOperationalItems([
    { label: "Time to consequence", value: runway, priority: true, state: uiState },
    { label: "Operational focus", value: liveOps.primaryWindow?.label ?? where, state: uiState === "stable" ? "stable" : "watch" },
  ]);
  const evidenceItems = compactOperationalItems([
    { label: "Why Neraium flagged this", value: primaryEvidence, state: uiState },
    { label: "Infrastructure relationships", value: relationshipEvidence, state: uiState === "stable" ? "stable" : uiState },
    { label: "Structural drivers", value: activeArchetype, state: uiState === "neutral" ? "neutral" : "watch" },
  ]);
  const narrativeItems = compactOperationalItems([
    { label: "Escalation direction", value: issueType, state: uiState },
    { label: "Primary driver", value: whyWeThinkThat, state: uiState === "stable" ? "stable" : uiState },
    { label: "Operator focus", value: humanRead, state: uiState === "critical" ? "warning" : "stable" },
  ]);
  const timelineItems = compactOperationalItems([
    { label: "Instability began", value: lastUpdate, state: "neutral" },
    { label: "Persistence", value: confidence, state: uiState === "neutral" ? "neutral" : "stable" },
    { label: "Escalation window", value: continuationWindow, state: uiState },
    { label: "Relationship spread", value: propagationPath || memoryMatch, state: uiState === "neutral" ? "neutral" : uiState },
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


