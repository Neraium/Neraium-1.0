import { useMemo } from "react";
import SystemBodyWorkspace from "./workspaces/SystemBody/SystemBodyWorkspace";
import { normalizeOperationalState, orbStateFromOperationalState } from "../viewModels/operationalUiState";

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
  description: "No telemetry baseline is available yet. The orb remains visible so operators can confirm structural health mode and wait for live evidence.",
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
  const systemState = orbStateFromOperationalState(uiState);
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
    : (primaryItem?.supportingEvidence?.[0] ?? findings[0]?.detail ?? "No active SII evidence yet");
  const relationshipEvidence = awaitingSii
    ? awaitingLabel
    : (primaryItem?.relationshipEvidence?.[0] ?? liveOps.relationshipRows?.[0]?.detail ?? "Relationship evidence not isolated yet");
  const lastUpdate = liveOps.connectionSummary ?? "No confirmed update";
  const whyWeThinkThat = awaitingSii || uiState === "neutral"
    ? "The workspace is waiting for a usable telemetry baseline or backend evidence stream."
    : (secondaryMessage || relationshipEvidence);
  const humanRead = awaitingSii || uiState === "neutral"
    ? "No upload is required for the orb to render. It stays visible as the neutral structural placeholder until live evidence arrives."
    : (liveOps.connectionActionHint || "Monitor relationship coherence and schedule operator review if drift persists.");
  const where = suspectedLocation;
  void selectedTarget;
  void onSelectTarget;

  const metrics = [
    { label: "Severity", value: liveOps.facilityStateLabel, priority: true, state: uiState },
    { label: "Primary room", value: where, state: uiState === "neutral" ? "neutral" : "stable" },
    { label: "Next inspect", value: liveOps.primaryWindow?.label ?? "Facility overview", state: uiState === "stable" ? "stable" : "watch" },
    { label: "What changed", value: issueType, state: uiState },
  ];
  const evidenceItems = [
    { label: "Primary evidence", value: primaryEvidence, state: uiState },
    { label: "Relationship evidence", value: relationshipEvidence, state: uiState === "stable" ? "watch" : uiState },
    { label: "Source of truth", value: `${sourceLabel}. Operational conclusions remain backend/SII sourced.`, state: "neutral" },
  ];
  const narrativeItems = [
    { label: "What's wrong", value: primaryMessage, state: uiState },
    { label: "Why we think that", value: whyWeThinkThat, state: uiState === "stable" ? "watch" : uiState },
    { label: "Human read", value: humanRead, state: uiState === "critical" ? "warning" : "stable" },
    { label: "Where", value: where, state: "neutral" },
  ];
  const timelineItems = [
    { label: "Latest update", value: lastUpdate, state: "neutral" },
    { label: "Operational runway", value: runway, state: uiState },
    { label: "Urgency", value: urgency, state: uiState },
    { label: "Evidence quality", value: confidence, state: uiState === "neutral" ? "neutral" : "stable" },
  ];

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
      isLoading={awaitingSii}
    />
  );
}


