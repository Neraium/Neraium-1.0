import { useCallback, useMemo, useState } from "react";
import { apiFetch } from "./config";
import SystemTopologyWorkspace from "./components/SystemTopologyWorkspace";
import DataConnectionsWorkspace from "./components/DataConnectionsWorkspace";
import StructuralReplayWorkspace from "./components/StructuralReplayWorkspace";
import GovernanceAdminWorkspace from "./components/GovernanceAdminWorkspace";
import { EmptyState, MetricGrid, Panel } from "./components/workspacePrimitives";
import useFacilityRuntime from "./hooks/useFacilityRuntime";
import * as uploadStateView from "./viewModels/uploadState";

function App() {
  const accessCode = "";
  const [activeWorkspace, setActiveWorkspace] = useState("system-body");
  const [sessionIntent, setSessionIntent] = useState("neutral");
  const [historianReplayState, setHistorianReplayState] = useState({ enabled: false, frame: null, meta: null });

  const {
    apiStatus,
    systems,
    systemsState,
    intelligenceStatus,
    latestUploadResult,
    latestUploadSnapshot,
    demoScenario,
    setDemoScenario,
    isDemoMode,
    setIsDemoMode,
    loadFacilitySystems,
    loadLatestUploadState,
    setAllowPersistedLatest,
    telemetryTick,
  } = useFacilityRuntime({
    hasAccess: true,
    accessCode,
    formatClockTime,
    formatEndpoint,
    buildProtectedRequestMessage,
  });

  const hasRealSiiOutput = useMemo(
    () => uploadStateView.hasFullUploadResult(latestUploadResult),
    [latestUploadResult],
  );
  const hasCurrentUploadResult = sessionIntent === "current" && hasRealSiiOutput;
  const hasResumedSession = sessionIntent === "resumed" && hasRealSiiOutput;
  const hasActiveSession = hasCurrentUploadResult || hasResumedSession;
  const effectiveLatestUploadResult = hasActiveSession ? latestUploadResult : null;
  const effectiveLatestUploadSnapshot = hasActiveSession
    ? latestUploadSnapshot
    : uploadStateView.buildEmptyLatestUploadSnapshot();
  const roomContext = useMemo(
    () => uploadStateView.deriveRoomContext(effectiveLatestUploadResult),
    [effectiveLatestUploadResult],
  );

  const liveOps = useMemo(() => {
    const intelligence = effectiveLatestUploadResult?.sii_intelligence ?? null;
    const governance =
      intelligence?.aletheia_gate
      ?? intelligence?.distributed_cognition_governance
      ?? effectiveLatestUploadResult?.distributed_cognition_governance
      ?? null;
    const admittedState = String(governance?.admitted_state ?? "").toUpperCase();
    const gateOutcome = String(governance?.gate_outcome ?? "").toUpperCase();
    const hasPass = gateOutcome === "PASS" && ["WATCH", "ALERT"].includes(admittedState);

    const facilityTone = hasPass
      ? admittedState === "ALERT"
        ? "critical"
        : "watch"
      : "stable";

    const connectionSummary = latestUploadSnapshot?.last_upload_at
      ? `Updated ${formatClockTime(latestUploadSnapshot.last_upload_at)} CT`
      : formatClockTime(new Date());

    return {
      facilityTone,
      intelligenceMode: effectiveLatestUploadResult ? "live" : "empty",
      connectionTone: apiStatus.state === "online" ? "online" : "degraded",
      connectionSummary,
      connectionStatusLine: apiStatus.state === "online" ? "Data stream active" : "Connection degraded",
      primaryWindow: {
        label: governance?.affected_subsystem ?? roomContext.primary,
        window: governance?.elapsed_operational_duration ?? "Governed window active",
      },
      findings: hasPass
        ? [{ detail: governance?.why_summary ?? "Admitted governed finding active." }]
        : [],
      interventionItems: hasPass
        ? [{
          label: governance?.affected_subsystem ?? roomContext.primary,
          recommendation: governance?.operator_focus ?? "Inspect admitted structural relationship path.",
          window: governance?.elapsed_operational_duration ?? "Governed window active",
          confidence: 90,
          relationshipEvidence: [governance?.affected_relationship_path ?? "Admitted relationship path"],
        }]
        : [],
      relationshipRows: effectiveLatestUploadResult?.baseline_analysis?.relationship_drift ?? [],
      distributed_cognition_governance: governance,
      sourceIntelligence: intelligence,
      systems,
      systemsState,
      intelligenceStatus,
      telemetryTick,
    };
  }, [apiStatus.state, effectiveLatestUploadResult, intelligenceStatus, latestUploadSnapshot?.last_upload_at, roomContext.primary, systems, systemsState, telemetryTick]);

  const handleReplayFrameChange = useCallback((frame, meta) => {
    setHistorianReplayState((current) => ({ ...current, frame, meta }));
  }, []);

  const handleReplayModeChange = useCallback((enabled) => {
    setHistorianReplayState((current) => ({ ...current, enabled }));
  }, []);

  const handleGateUploadComplete = useCallback(async () => {
    setIsDemoMode(false);
    setAllowPersistedLatest(true);
    const hasResult = await loadLatestUploadState({ includePersisted: true });
    setSessionIntent(hasResult ? "current" : "neutral");
    await loadFacilitySystems();
  }, [loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest, setIsDemoMode]);

  const handleResumePreviousSession = useCallback(async () => {
    setAllowPersistedLatest(true);
    const hasResult = await loadLatestUploadState({ includePersisted: true });
    setSessionIntent(hasResult ? "resumed" : "neutral");
    await loadFacilitySystems();
    setActiveWorkspace("system-body");
  }, [loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest]);

  const handleResetDemo = useCallback(async () => {
    setSessionIntent("neutral");
    setIsDemoMode(false);
    setAllowPersistedLatest(false);
    await loadLatestUploadState({ includePersisted: false });
    await loadFacilitySystems();
  }, [loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest, setIsDemoMode]);

  if (activeWorkspace === "data-connections") {
    return (
      <DataConnectionsWorkspace
        accessCode={accessCode}
        apiFetch={apiFetch}
        apiStatus={apiStatus}
        latestUploadSnapshot={effectiveLatestUploadSnapshot}
        latestUploadResult={effectiveLatestUploadResult}
        hasActiveSession={hasActiveSession}
        hasResumedSession={hasResumedSession}
        hasCurrentUploadResult={hasCurrentUploadResult}
        hasRealSiiOutput={hasRealSiiOutput}
        roomContext={roomContext}
        onUploadComplete={handleGateUploadComplete}
        onResetDemo={handleResetDemo}
        onResumePreviousSession={handleResumePreviousSession}
        formatClockTime={formatClockTime}
        demoState={{ active: false, isPlaying: false, stepIndex: 0, elapsedMs: 0 }}
        demoTabId={null}
        onActivateDemo={() => {}}
        onToggleDemoPlayback={() => {}}
        onPreviousDemoStep={() => {}}
        onNextDemoStep={() => {}}
        onRestartDemo={() => {}}
      />
    );
  }

  if (activeWorkspace === "historical-replay") {
    return (
      <StructuralReplayWorkspace
        apiFetch={apiFetch}
        accessCode={accessCode}
        expertMode={false}
        normalizeErrorMessage={(value) => String(value ?? "")}
        formatClockTime={formatClockTime}
        Panel={Panel}
        MetricGrid={MetricGrid}
        EmptyState={EmptyState}
        hasActiveSession={hasActiveSession}
        hasCurrentUploadResult={hasCurrentUploadResult}
        hasResumedSession={hasResumedSession}
        hasRealSiiOutput={hasRealSiiOutput}
        onReplayFrameChange={handleReplayFrameChange}
        onReplayModeChange={handleReplayModeChange}
      />
    );
  }

  if (activeWorkspace === "governance-admin") {
    return (
      <GovernanceAdminWorkspace
        apiFetch={apiFetch}
        accessCode={accessCode}
        Panel={Panel}
        EmptyState={EmptyState}
      />
    );
  }

  return (
    <SystemTopologyWorkspace
      liveOps={historianReplayState.enabled && historianReplayState.frame
        ? { ...liveOps, ...historianReplayState.frame }
        : liveOps}
      selectedTarget={null}
      onSelectTarget={() => {}}
      apiFetch={apiFetch}
      accessCode={accessCode}
      onWorkspaceNavigate={setActiveWorkspace}
      onUploadComplete={handleGateUploadComplete}
    />
  );
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
