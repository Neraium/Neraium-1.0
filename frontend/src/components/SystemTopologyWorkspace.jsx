import React, { useMemo } from "react";
import SystemBodyWorkspace from "./workspaces/SystemBody/SystemBodyWorkspace";
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
  replayFrame = null,
  selectedTarget,
  onSelectTarget,
  apiFetch,
  accessCode,
  onWorkspaceNavigate, 
  onUploadComplete,
  onResumePreviousSession,
  domainMode = "aquatic",
  domainDetection = null,
  gateProcessing = null,
  gateStateOverride = "",
}) { 
  const processingActive = Boolean(gateProcessing?.active);
  const sessionUiState = String(liveOps.session?.uiState ?? "empty");
  const rawUiState = normalizeOperationalState(liveOps.facilityTone);
  const hasUploadResult = sessionUiState === "verified" || sessionUiState === "restored";
  const awaitingSii = ["idle", "empty", "queued", "processing"].includes(sessionUiState);
  const uiState = processingActive || awaitingSii || rawUiState === "neutral" ? "neutral" : rawUiState;
  const layer = deriveEscalationLayer({ awaitingSii, uiState, liveOps });
  const governed = deriveCurrentOutput(liveOps, {
    awaitingSii,
    uiState,
    layer,
  });
  const reviewReady = liveOps.currentSession?.hasReliableOperatorEvidence === true;
  const uploadSignal = deriveUploadSignal(liveOps.latestUploadResult, { reviewReady });
  const pendingVerification = sessionUiState === "verified" && !reviewReady;

  const stateLabel = processingActive
    ? "Processing"
    : String(gateStateOverride || "").trim()
      ? String(gateStateOverride).trim()
      : pendingVerification
        ? "Telemetry still processing"
        : hasUploadResult
          ? (uploadSignal.label || "Monitoring")
          : awaitingSii
            ? "No runtime data"
            : (uploadSignal.label || governed.currentGovernedSystemState || ESCALATION_LAYERS[layer - 1] || FALLBACK_STATE.label);
  const stateDescription = pendingVerification
    ? "Telemetry is present, but the behavior evidence is still being verified for engineer review."
    : buildStateDescription(layer);
  const primaryItem = liveOps.interventionItems?.[0] ?? null;
  const coherence = useMemo(() => {
    const total = (liveOps.relationshipRows ?? []).reduce(
      (sum, row) => sum + Math.abs(Number(row.pair_weight ?? row.change ?? 0)),
      0,
    );
    return Math.max(0, Math.min(1, 1 - total));
  }, [liveOps.relationshipRows]);

  const systemState = processingActive || pendingVerification
    ? "unknown"
    : hasUploadResult
      ? (uploadSignal.systemState || "stable")
      : (awaitingSii ? "unknown" : (uploadSignal.systemState || orbStateFromStatusLight(governed.statusLight)));
  const primaryMessage = derivePrimaryMessage({
    awaitingSii,
    pendingVerification,
    governed,
    canonicalFinding: liveOps.canonicalFinding,
    uploadSignal,
  });

  const focusArea = governed.affectedSubsystem;
  const summaryTitle = pendingVerification
    ? "behavior evidence Verification Pending"
    : governed.hasFinding
      ? "System Review Active"
      : "System Review Pending";
  const lastUpdate = liveOps.connectionSummary ?? EMPTY_VALUE;

  const metrics = [];

  const evidenceItems = [];

  const narrativeItems = compactOperationalItems([
    { label: "Current System State", value: governed.currentGovernedSystemState, state: uiState },
    ...(governed.hasFinding ? [{ label: "Affected Equipment", value: concise(governed.affectedSubsystem, 80), state: uiState }] : []),
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
      statusLight={processingActive || pendingVerification ? "gray" : (uploadSignal.statusLight || governed.statusLight)}
      governedOnly
      governedDetail={governed.detail}
      apiFetch={apiFetch}
      accessCode={accessCode}
      onWorkspaceNavigate={onWorkspaceNavigate}
      onUploadComplete={onUploadComplete}
      onResumePreviousUpload={onResumePreviousSession}
      persistedLatestUpload={liveOps.persistedLatestUpload ?? null}
      previousUploadHistory={liveOps.previousUploadHistory ?? []}
      domainMode={domainMode}
      domainDetection={domainDetection}
      latestUploadSnapshot={liveOps.latestUploadSnapshot ?? null}
      latestUploadResult={liveOps.latestUploadResult}
      liveSnapshot={liveOps}
      latestReplayFrame={replayFrame}
      canonicalFinding={liveOps.canonicalFinding ?? null}
      telemetrySessionMode={liveOps.telemetrySession?.sessionMode ?? "empty"}
      gateProcessing={gateProcessing}
    /> 
  ); 
} 

export function derivePrimaryMessage({ awaitingSii, pendingVerification, canonicalFinding, uploadSignal }) {
  if (awaitingSii) return "Analyze or connect telemetry to begin monitoring.";
  if (pendingVerification) {
    return "Telemetry processing finished, but the behavior evidence is still being verified for engineer review.";
  }
  if (canonicalFinding?.exists && canonicalFinding?.summary) {
    return concise(canonicalFinding.summary, 120);
  }
  if (uploadSignal.label && uploadSignal.label !== "Stable") {
    return uploadSignal.label;
  }
  return "Stable";
}

export function deriveUploadSignal(latestUploadResult, { reviewReady = true } = {}) {
  if (!latestUploadResult) {
    return { systemState: null, label: "" };
  }

  const operatingState = String(latestUploadResult?.operating_state ?? latestUploadResult?.sii_intelligence?.facility_state ?? "").toLowerCase();
  const urgency = String(latestUploadResult?.drift_status ?? latestUploadResult?.sii_intelligence?.urgency ?? "").toLowerCase();

  if (!reviewReady) {
    return { systemState: "unknown", label: "Telemetry still processing", statusLight: "gray" };
  }
  if (!operatingState && !urgency) {
    return { systemState: null, label: "", statusLight: null };
  }
  if (operatingState.includes("needs action") || urgency === "unstable" || operatingState.includes("unstable")) {
    return { systemState: "alert", label: "System behavior changed", statusLight: "amber" };
  }
  if (operatingState.includes("drift") || urgency === "elevated" || operatingState.includes("degrad")) {
    return { systemState: "watching", label: "Needs review", statusLight: "gray" };
  }
  if (operatingState.includes("needs review") || urgency === "review" || operatingState.includes("review")) {
    return { systemState: "watching", label: "Needs review", statusLight: "gray" };
  }
  if (operatingState.includes("stable") || operatingState.includes("monitor")) {
    return { systemState: "stable", label: "Stable", statusLight: "gray" };
  }
  return { systemState: null, label: "", statusLight: null };
}

export function deriveCurrentOutput(liveOps, { awaitingSii }) {
  const finding = liveOps.canonicalFinding;
  return {
    hasFinding: Boolean(finding?.exists),
    statusLight: "gray",
    currentGovernedSystemState: awaitingSii ? "No Data" : "Monitoring",
    affectedSubsystem: finding?.exists ? (liveOps.primaryWindow?.label ?? "") : "",
    timestamp: liveOps.connectionSummary ?? "Not available",
    detail: null,
  };
}

function orbStateFromStatusLight(statusLight) {
  if (statusLight === "yellow") return "watching";
  if (statusLight === "amber" || statusLight === "red") return "propagation_active";
  return "unknown";
}

function buildStateDescription(layer) {
  if (layer <= 2) return "System behaviors remain inside baseline containment with active observation.";
  if (layer === 3) return "Behavior change observed across recent windows.";
  if (layer === 4) return "Persistent change is visible across multiple telemetry windows.";
  if (layer === 5) return "System behavior is outside the expected operating pattern.";
  if (layer === 6) return "Propagation and recovery degradation indicate a sustained system behavior changed.";
  return "Multiple equipment signals are changing together.";
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
    evidenceConfidence: evidenceConfidence > 0 ? `${evidenceConfidence}%` : "More telemetry needed",
  };
}

function compactOperationalItems(items) {
  return items.filter((item) => {
    const value = String(item?.value ?? "").trim().toLowerCase();
    return value && value !== "none" && value !== "n/a" && value !== "na" && value !== "awaiting structural interpretation";
  });
}

function concise(value, max = 80) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 1)).trimEnd()}...`;
}
