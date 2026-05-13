import { useMemo } from "react";
import SystemBodyWorkspace from "./workspaces/SystemBody/SystemBodyWorkspace";

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

export default function SystemTopologyWorkspace({ liveOps, selectedTarget, onSelectTarget }) {
  const state = STATE[liveOps.facilityTone] ?? STATE.info;
  const primaryItem = liveOps.interventionItems?.[0] ?? null;
  const coherence = useMemo(() => {
    const total = (liveOps.relationshipRows ?? []).reduce((sum, row) => sum + Math.abs(Number(row.pair_weight ?? row.change ?? 0)), 0);
    return Math.max(0, Math.min(1, 1 - total));
  }, [liveOps.relationshipRows]);
  const systemState = liveOps.facilityTone === "nominal"
    ? "stable"
    : liveOps.facilityTone === "review"
      ? "drift"
      : liveOps.facilityTone === "info"
        ? "neutral"
      : "separation";
  const findings = liveOps.findings?.slice(0, 2) ?? [];
  const primaryMessage = findings[0]?.detail ?? state.description;
  const secondaryMessage = findings[1]?.detail ?? liveOps.heroSubline;
  const sourceLabel = liveOps.dataSourceLabel ?? "Awaiting data";
  const awaitingSii = liveOps.intelligenceMode === "empty" || liveOps.intelligenceMode === "processing";
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
  void selectedTarget;
  void onSelectTarget;

  const metrics = [
    { label: "Operational runway", value: runway, priority: true },
    { label: "Issue type", value: issueType },
    { label: "Suspected location", value: suspectedLocation },
    { label: "Urgency", value: urgency },
    { label: "Evidence quality", value: confidence },
    { label: "Latest update", value: lastUpdate },
  ];
  const evidenceItems = [
    { label: "Primary evidence", value: primaryEvidence },
    { label: "Relationship evidence", value: relationshipEvidence },
    { label: "Source of truth", value: `${sourceLabel}. Operational conclusions remain backend/SII sourced.` },
  ];

  return (
    <SystemBodyWorkspace
      systemState={systemState}
      coherence={coherence}
      stateLabel={state.label}
      primaryMessage={primaryMessage}
      summaryTitle={state.description}
      summaryText={secondaryMessage}
      metrics={metrics}
      evidenceItems={evidenceItems}
    />
  );
}
