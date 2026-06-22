import { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch, ENABLE_ADMISSION_GATE } from "./config";
import AppWorkspaceRouter from "./components/AppWorkspaceRouter";
import useFacilityRuntime from "./hooks/useFacilityRuntime";
import useWorkspaceSessionController, { readStoredAllowPersistedLatest } from "./hooks/useWorkspaceSessionController";
import { logoutUser } from "./services/api/authApi";
import { resolveSessionStore } from "./viewModels/sessionState";
import { classifyDataFreshness, deriveIntelligenceMode } from "./viewModels/systemState";

function App() {
  const accessCode = "";
  const [activeWorkspace, setActiveWorkspace] = useState("system-body");
  const [appReady, setAppReady] = useState(false);
  const initialAllowPersistedLatest = readStoredAllowPersistedLatest();

  const {
    apiStatus,
    systems,
    systemsState,
    intelligenceStatus,
    latestUploadResult,
    latestUploadSnapshot,
    sessionStore,
    domainDetection,
    setIsDemoMode,
    loadFacilitySystems,
    loadLatestUploadState,
    allowPersistedLatest,
    setAllowPersistedLatest,
    clearUploadSessionState,
    telemetryTick,
    domainMode,
  } = useFacilityRuntime({
    hasAccess: true,
    accessCode,
    formatClockTime,
    formatEndpoint,
    buildProtectedRequestMessage,
    initialAllowPersistedLatest,
  });

  const resolvedSessionStore = useMemo(() => resolveSessionStore({
    sessionStore,
    latestUploadSnapshot,
    latestUploadResult,
  }), [latestUploadResult, latestUploadSnapshot, sessionStore]);

  const {
    historianReplayState,
    errorBoundaryResetKey,
    effectiveLatestUploadResult,
    effectiveLatestUploadSnapshot,
    hasCurrentUploadResult,
    hasResumedSession,
    hasActiveSession,
    hasRealSiiOutput,
    roomContext,
    currentSession,
    canonicalFinding,
    telemetrySession,
    gateProcessing,
    persistedLatestUpload,
    previousUploadHistory,
    handleReplayFrameChange,
    handleReplayModeChange,
    handleGateUploadComplete,
    handleResumePreviousSession,
    handleResetDemo,
    handleBackToGate,
    handleRetryWorkspace,
  } = useWorkspaceSessionController({
    activeWorkspace,
    setActiveWorkspace,
    apiFetch,
    accessCode,
    sessionStore: resolvedSessionStore,
    loadFacilitySystems,
    loadLatestUploadState,
    allowPersistedLatest,
    setAllowPersistedLatest,
    clearUploadSessionState,
    setIsDemoMode,
  });

  const liveOps = useMemo(() => {
    const intelligence = effectiveLatestUploadResult?.sii_intelligence ?? null;
    const governance =
      intelligence?.aletheia_gate
      ?? intelligence?.distributed_cognition_governance
      ?? effectiveLatestUploadResult?.distributed_cognition_governance
      ?? null;
    const admittedState = String(governance?.admitted_state ?? "").toUpperCase();
    const gateOutcome = String(governance?.gate_outcome ?? "").toUpperCase();
    const hasPass = ENABLE_ADMISSION_GATE && gateOutcome === "PASS" && ["WATCH", "ALERT"].includes(admittedState);
    const uploadTone = deriveUploadTone(effectiveLatestUploadResult);

    const heartbeatSource = telemetrySession.heartbeatAt;
    const hasTelemetryHeartbeat = Boolean(heartbeatSource);
    const facilityTone = hasTelemetryHeartbeat
      ? (hasPass
        ? admittedState === "ALERT"
          ? "critical"
          : "watch"
        : uploadTone)
      : telemetrySession.sessionMode === "persisted"
        ? "watch"
        : "empty";

    const intelligenceMode = hasTelemetryHeartbeat
      ? deriveIntelligenceMode({
        hasRealSiiOutput,
        latestUploadSnapshot: effectiveLatestUploadSnapshot,
      })
      : "empty";
    const connectionSummary = heartbeatSource
      ? `Updated ${formatClockTime(heartbeatSource)} CT`
      : null;
    const connectionStatusLine = apiStatus.state === "online"
      ? telemetrySession.statusLabel
      : "Connection degraded";
    const dataFreshness = classifyDataFreshness({
      heartbeatAt: heartbeatSource,
      online: apiStatus.state === "online",
    });
    const siiVerification = {
      verified: Boolean(hasRealSiiOutput || effectiveLatestUploadSnapshot?.sii_completed === true),
      artifacts: effectiveLatestUploadSnapshot?.sii_completion_artifacts || {},
    };

    return {
      facilityTone,
      intelligenceMode,
      connectionTone: apiStatus.state === "online" ? "online" : "degraded",
      connectionSummary,
      connectionStatusLine,
      lastDataHeartbeat: heartbeatSource,
      dataFreshness,
      siiVerification,
      primaryWindow: {
        label: governance?.affected_subsystem ?? roomContext.primary,
        window: governance?.elapsed_operational_duration ?? "Governed window active",
      },
      findings: hasPass
        ? [{ detail: governance?.why_summary ?? canonicalFinding.summary ?? "Admitted governed finding active." }]
        : (canonicalFinding.exists ? [{ detail: canonicalFinding.summary }] : []),
      interventionItems: hasPass
        ? [{
          label: governance?.affected_subsystem ?? roomContext.primary,
          recommendation: governance?.operator_focus ?? "Review admitted structural relationship path.",
          window: governance?.elapsed_operational_duration ?? "Governed window active",
          confidence: 90,
          relationshipEvidence: [governance?.affected_relationship_path ?? "Admitted relationship path"],
        }]
        : (canonicalFinding.exists ? [{
          label: roomContext.primary,
          recommendation: canonicalFinding.reviewNext,
          window: canonicalFinding.technicalDetails?.find((item) => item.label === "Behavior duration")?.value ?? "Current observation",
          confidence: canonicalFinding.confidence === "High" ? 90 : canonicalFinding.confidence === "Moderate" ? 70 : 50,
          relationshipEvidence: canonicalFinding.supportingEvidence ?? [],
        }] : []),
      relationshipRows: effectiveLatestUploadResult?.baseline_analysis?.relationship_drift ?? [],
      distributed_cognition_governance: governance,
      sourceIntelligence: intelligence,
      latestUploadResult: effectiveLatestUploadResult,
      latestUploadSnapshot: effectiveLatestUploadSnapshot,
      currentSession,
      telemetrySession,
      persistedLatestUpload,
      previousUploadHistory,
      session: resolvedSessionStore,
      systems,
      systemsState,
      intelligenceStatus,
      telemetryTick,
    };
  }, [apiStatus.state, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, hasRealSiiOutput, intelligenceStatus, persistedLatestUpload, previousUploadHistory, resolvedSessionStore, roomContext.primary, systems, systemsState, telemetrySession, telemetryTick]);

  const handleSignOut = useCallback(async () => {
    await logoutUser();
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    if (domainMode) {
      document.documentElement.setAttribute("data-domain-mode", domainMode);
    } else {
      document.documentElement.removeAttribute("data-domain-mode");
    }
  }, [domainMode]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setAppReady(true);
    window.__NERAIUM_APP_READY__ = true;
  }, []);

  return (
    <AppWorkspaceRouter
      activeWorkspace={activeWorkspace}
      appReady={appReady}
      errorBoundaryResetKey={errorBoundaryResetKey}
      apiFetch={apiFetch}
      accessCode={accessCode}
      apiStatus={apiStatus}
      liveOps={liveOps}
      historianReplayState={historianReplayState}
      currentSession={currentSession}
      canonicalFinding={canonicalFinding}
      gateProcessing={gateProcessing}
      effectiveLatestUploadResult={effectiveLatestUploadResult}
      effectiveLatestUploadSnapshot={effectiveLatestUploadSnapshot}
      hasActiveSession={hasActiveSession}
      hasCurrentUploadResult={hasCurrentUploadResult}
      hasResumedSession={hasResumedSession}
      hasRealSiiOutput={hasRealSiiOutput}
      roomContext={roomContext}
      domainMode={domainMode}
      domainDetection={domainDetection}
      formatClockTime={formatClockTime}
      handleBackToGate={handleBackToGate}
      handleRetryWorkspace={handleRetryWorkspace}
      handleGateUploadComplete={handleGateUploadComplete}
      handleResumePreviousSession={handleResumePreviousSession}
      handleResetDemo={handleResetDemo}
      handleReplayFrameChange={handleReplayFrameChange}
      handleReplayModeChange={handleReplayModeChange}
      handleSignOut={handleSignOut}
      setActiveWorkspace={setActiveWorkspace}
    />
  );
}

function deriveUploadTone(result) {
  if (!result) return "stable";
  const operatingState = String(result?.operating_state ?? result?.sii_intelligence?.facility_state ?? "").toLowerCase();
  const urgency = String(result?.drift_status ?? result?.sii_intelligence?.urgency ?? "").toLowerCase();

  if (!operatingState && !urgency) return "stable";
  if (operatingState.includes("needs action") || urgency === "unstable" || operatingState.includes("unstable")) return "critical";
  if (operatingState.includes("drift") || urgency === "elevated" || operatingState.includes("degrad")) return "warning";
  if (operatingState.includes("needs review") || urgency === "review" || operatingState.includes("review")) return "review";
  if (operatingState.includes("stable") || operatingState.includes("monitor")) return "stable";
  return "stable";
}

function formatClockTime(value) {
  if (!value) return "Unavailable";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function formatEndpoint(url) {
  try {
    return new URL(url).host;
  } catch {
    return String(url ?? "");
  }
}

async function buildProtectedRequestMessage(response) {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
  } catch {
    // Ignore parse failures and use fallback.
  }
  return "Session expired. Refresh workspace.";
}

export default App;
