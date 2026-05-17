import React, { useMemo } from "react";
import SystemBodyWorkspace from "./workspaces/SystemBody/SystemBodyWorkspace";
import { normalizeOperationalState } from "../viewModels/operationalUiState";
import {
  LIFECYCLE_RAIL_NEUTRAL,
  LIFECYCLE_RAIL_ACTIVE,
} from "../viewModels/operationalVocabulary";
import { EMPTY_VALUE } from "../viewModels/emptyValue";

const STATE = {
  nominal: {
    label: "Stable",
    description: "Infrastructure relationships are stable across the monitored system.",
  },
  review: {
    label: "Early Structural Drift",
    description: "System behavior is beginning to move away from baseline.",
  },
  elevated: {
    label: "Escalating Drift",
    description: "Persistent deviation is visible and requires focused operator review.",
  },
  unstable: {
    label: "Structural Instability",
    description: "System behavior is moving away from baseline and requires focused review.",
  },
  info: {
    label: "Baseline Pending",
    description: "Telemetry baseline required before structural assessment is available.",
  },
};

const FALLBACK_STATE = {
  label: EMPTY_VALUE,
  description: "No telemetry session is currently active.",
  mode: "no-data",
};

export default function SystemTopologyWorkspace({
  liveOps,
  selectedTarget,
  onSelectTarget,
}) {
  const rawUiState = normalizeOperationalState(liveOps.facilityTone);

  const awaitingSii =
    liveOps.intelligenceMode === "empty"
    || liveOps.intelligenceMode === "processing";

  const uiState =
    awaitingSii || rawUiState === "neutral"
      ? "neutral"
      : rawUiState;

  const state =
    awaitingSii || uiState === "neutral"
      ? FALLBACK_STATE
      : (STATE[liveOps.facilityTone] ?? STATE.info);

  const primaryItem = liveOps.interventionItems?.[0] ?? null;

  const coherence = useMemo(() => {
    const total = (liveOps.relationshipRows ?? []).reduce(
      (sum, row) => sum + Math.abs(Number(row.pair_weight ?? row.change ?? 0)),
      0,
    );

    return Math.max(0, Math.min(1, 1 - total));
  }, [liveOps.relationshipRows]);

  const systemState = deriveOrbOperationalState({
    awaitingSii,
    uiState,
    liveOps,
    primaryItem,
  });

  const findings = liveOps.findings?.slice(0, 2) ?? [];

  const primaryMessage = concise(
    findings[0]?.detail ?? state.description,
    96,
  );

  const secondaryMessage =
    findings[1]?.detail ?? liveOps.heroSubline;

  const neutralCopy = {
    issue: EMPTY_VALUE,
    location: EMPTY_VALUE,
    runway: EMPTY_VALUE,
    confidence: EMPTY_VALUE,
    primaryEvidence: EMPTY_VALUE,
    relationshipEvidence: EMPTY_VALUE,
    signal: EMPTY_VALUE,
    propagation: EMPTY_VALUE,
    memory: EMPTY_VALUE,
    continuation: EMPTY_VALUE,
    summary: EMPTY_VALUE,
  };

  const issueType = awaitingSii
    ? neutralCopy.issue
    : (
        primaryItem?.title
        ?? findings[0]?.title
        ?? liveOps.facilityStateLabel
        ?? state.label
      );

  const suspectedLocation = awaitingSii
    ? neutralCopy.location
    : (
        primaryItem?.label
        ?? liveOps.primaryWindow?.label
        ?? "Facility scope"
      );

  const runway = awaitingSii
    ? neutralCopy.runway
    : liveOps.facilityTone === "nominal"
      ? "No elevated progression observed"
      : (
          primaryItem?.window
          ?? liveOps.primaryWindow?.window
          ?? "Progression rate under review"
        );

  const confidence = awaitingSii
    ? neutralCopy.confidence
    : (
        primaryItem?.supportingEvidence?.length
        || liveOps.relationshipRows?.length
      )
      ? "Multi-signal corroboration observed"
      : "Corroboration still developing";

  const primaryEvidence = awaitingSii
    ? neutralCopy.primaryEvidence
    : (
        primaryItem?.supportingEvidence?.[0]
        ?? findings[0]?.detail
        ?? "Relationships are moving away from baseline."
      );

  const relationshipEvidence = awaitingSii
    ? neutralCopy.relationshipEvidence
    : (
        primaryItem?.relationshipEvidence?.[0]
        ?? liveOps.relationshipRows?.[0]?.detail
        ?? "Subsystem relationships are shifting relative to baseline."
      );

  const activeArchetype = awaitingSii
    ? neutralCopy.signal
    : (
        primaryItem?.activeArchetypes?.[0]?.name?.replaceAll?.("_", " ")
        ?? EMPTY_VALUE
      );

  const propagationPath = awaitingSii
    ? neutralCopy.propagation
    : (
        primaryItem?.propagationPathways?.[0]?.replaceAll?.("_", " ")
        ?? EMPTY_VALUE
      );

  const memoryMatch = awaitingSii
    ? neutralCopy.memory
    : (
        primaryItem?.structuralMemoryMatches?.[0]?.label
        ?? EMPTY_VALUE
      );

  const continuationWindow = awaitingSii
    ? neutralCopy.continuation
    : (
        primaryItem?.continuationWindow
        ?? EMPTY_VALUE
      );

  const facilitySummary = awaitingSii
    ? neutralCopy.summary
    : (
        primaryItem?.facilityCognitionState
        ?? liveOps.heroSubline
        ?? EMPTY_VALUE
      );

  const lastUpdate = liveOps.connectionSummary ?? EMPTY_VALUE;

  const whyWeThinkThat =
    awaitingSii || uiState === "neutral"
      ? EMPTY_VALUE
      : (
          dedupeText(facilitySummary, state.description)
          || secondaryMessage
          || relationshipEvidence
        );

  const humanRead =
    awaitingSii || uiState === "neutral"
      ? EMPTY_VALUE
      : (
          liveOps.connectionActionHint
          || "Confirm persistence across recent telemetry windows."
        );

  const where = suspectedLocation;

  const summaryTitle = dedupeText(state.description, primaryMessage) || EMPTY_VALUE;

  void selectedTarget;
  void onSelectTarget;

  const metrics = compactOperationalItems([
    {
      label: "Progression window",
      value: runway,
      priority: true,
      state: uiState,
    },
    {
      label: "Current structural state",
      value: issueType,
      state: uiState,
    },
    {
      label: "Operational focus",
      value: liveOps.primaryWindow?.label ?? where,
      state: uiState === "stable" ? "stable" : "watch",
    },
    {
      label: "Corroboration",
      value: confidence,
      state: uiState === "neutral" ? "neutral" : "stable",
    },
  ]);

  const evidenceItems = compactOperationalItems([
    {
      label: "Observed structural deviation",
      value: concise(primaryEvidence, 88),
      state: uiState,
    },
    {
      label: "Relationship change",
      value: concise(relationshipEvidence, 88),
      state: uiState === "stable" ? "stable" : uiState,
    },
    {
      label: "Contributing signal",
      value: concise(activeArchetype, 72),
      state: uiState === "neutral" ? "neutral" : "watch",
    },
  ]);

  const narrativeItems = compactOperationalItems([
    {
      label: "Primary change",
      value: concise(whyWeThinkThat, 70),
      state: uiState === "stable" ? "stable" : uiState,
    },
    {
      label: "Infrastructure area",
      value: concise(where, 54),
      state: uiState === "critical" ? "warning" : uiState,
    },
    {
      label: "Operator focus",
      value: concise(humanRead, 72),
      state: uiState === "critical" ? "warning" : "stable",
    },
  ]);

  const timelineItems = compactOperationalItems([
    {
      label: "Initial deviation",
      value: concise(lastUpdate, 48),
      state: "neutral",
    },
    {
      label: "Persistence checkpoint",
      value: concise(confidence, 54),
      state: uiState === "neutral" ? "neutral" : "stable",
    },
    {
      label: "Drift trend",
      value: concise(continuationWindow, 54),
      state: uiState,
    },
    {
      label: "Subsystem spread",
      value: concise(propagationPath || memoryMatch, 58),
      state: uiState === "neutral" ? "neutral" : uiState,
    },
  ]);

  const lifecycleRail = buildLifecycleRail({ liveOps, awaitingSii, uiState });

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
      summaryTitle={summaryTitle}
      narrativeItems={narrativeItems}
      metrics={metrics}
      evidenceItems={evidenceItems}
      timelineItems={timelineItems}
      lastUpdate={lastUpdate}
      focusLabel={where}
      lifecycleRail={lifecycleRail}
      isLoading={awaitingSii}
    />
  );
}

function buildLifecycleRail({ awaitingSii, uiState }) {
  if (awaitingSii || uiState === "neutral") {
    return LIFECYCLE_RAIL_NEUTRAL;
  }
  return LIFECYCLE_RAIL_ACTIVE;
}

function compactOperationalItems(items) {
  return items.filter((item) => {
    const value = String(item?.value ?? "").trim().toLowerCase();

    return (
      value
      && value !== "none"
      && value !== "n/a"
      && value !== "na"
      && value !== "awaiting facility cognition"
    );
  });
}

function concise(value, max = 80) {
  const text = String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();

  if (text.length <= max) {
    return text;
  }

  return `${text.slice(0, Math.max(0, max - 1)).trimEnd()}...`;
}

function dedupeText(value, duplicateCandidate) {
  const text = String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();

  const duplicate = String(duplicateCandidate ?? "")
    .replace(/\s+/g, " ")
    .trim();

  if (!text) {
    return "";
  }

  if (!duplicate) {
    return text;
  }

  return text.toLowerCase() === duplicate.toLowerCase()
    ? ""
    : text;
}

function deriveOrbOperationalState({
  awaitingSii,
  uiState,
  liveOps,
  primaryItem,
}) {
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

  const hasPropagation =
    propagationSignal.includes("propagation")
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
