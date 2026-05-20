import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react"; 
import { apiFetch } from "./config"; 
import SystemTopologyWorkspace from "./components/SystemTopologyWorkspace"; 
import DataConnectionsWorkspace from "./components/DataConnectionsWorkspace"; 
import { DEMO_STEPS, STEP_DURATION_MS } from "./components/setup/DemoModePanel"; 
import { EmptyState, MetricGrid, Panel } from "./components/workspacePrimitives"; 
import useFacilityRuntime from "./hooks/useFacilityRuntime"; 
import * as uploadStateView from "./viewModels/uploadState"; 
import { classifyDataFreshness, deriveIntelligenceMode } from "./viewModels/systemState"; 
import { deriveCurrentSession } from "./viewModels/currentSession"; 

const StructuralReplayWorkspace = lazy(() => import("./components/StructuralReplayWorkspace"));
const GovernanceAdminWorkspace = lazy(() => import("./components/GovernanceAdminWorkspace"));

const SESSION_INTENT_STORAGE_KEY = "neraium.session_intent";

function readStoredSessionIntent() {
  if (typeof window === "undefined") return "neutral";
  const value = window.localStorage.getItem(SESSION_INTENT_STORAGE_KEY);
  return value === "current" || value === "resumed" ? value : "neutral";
}

function App() {
  const accessCode = "";
  const [activeWorkspace, setActiveWorkspace] = useState("system-body");
  const [sessionIntent, setSessionIntent] = useState(() => readStoredSessionIntent());
  const [historianReplayState, setHistorianReplayState] = useState({ enabled: false, frame: null, meta: null });
  const [guidedDemo, setGuidedDemo] = useState({ active: false, isPlaying: false, stepIndex: 0, elapsedMs: 0 });
  const [demoDataConnectionsTab, setDemoDataConnectionsTab] = useState(null);
  const [appReady, setAppReady] = useState(false);

  const {
    apiStatus,
    systems,
    systemsState,
    intelligenceStatus,
    latestUploadResult,
    latestUploadSnapshot,
    setIsDemoMode,
    loadFacilitySystems,
    loadLatestUploadState,
    setAllowPersistedLatest,
    telemetryTick,
    domainMode,
    setDomainMode,
  } = useFacilityRuntime({
    hasAccess: true,
    accessCode,
    formatClockTime,
    formatEndpoint,
    buildProtectedRequestMessage,
  });

  const hasRealSiiOutput = useMemo(
    () => uploadStateView.hasVerifiedSiiCompletion({
      latestResult: latestUploadResult,
      latestSnapshot: latestUploadSnapshot,
    }),
    [latestUploadResult, latestUploadSnapshot],
  );
  const hasObservableUploadSession = useMemo(
    () => uploadStateView.hasActiveTelemetrySnapshot(latestUploadSnapshot) || uploadStateView.hasFullUploadResult(latestUploadResult),
    [latestUploadResult, latestUploadSnapshot],
  );
  const effectiveSessionIntent = hasObservableUploadSession && sessionIntent === "neutral" ? "resumed" : sessionIntent;
  const hasCurrentUploadResult = effectiveSessionIntent === "current" && hasObservableUploadSession;
  const hasResumedSession = effectiveSessionIntent === "resumed" && hasObservableUploadSession;
  const hasActiveSession = hasCurrentUploadResult || hasResumedSession || hasObservableUploadSession;
  const effectiveLatestUploadResult = hasActiveSession ? latestUploadResult : null;
  const effectiveLatestUploadSnapshot = latestUploadSnapshot;
  const roomContext = useMemo(
    () => uploadStateView.deriveRoomContext(effectiveLatestUploadResult),
    [effectiveLatestUploadResult],
  );
  const currentSession = useMemo(() => deriveCurrentSession({
    latestUploadResult: effectiveLatestUploadResult,
    latestUploadSnapshot: effectiveLatestUploadSnapshot,
    hasActiveSession,
    hasCurrentUploadResult,
    hasResumedSession,
    hasRealSiiOutput,
  }), [effectiveLatestUploadResult, effectiveLatestUploadSnapshot, hasActiveSession, hasCurrentUploadResult, hasResumedSession, hasRealSiiOutput]);

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

    const heartbeatSource =
      effectiveLatestUploadSnapshot?.last_processed_at
      ?? effectiveLatestUploadSnapshot?.last_upload_at
      ?? intelligenceStatus?.last_processed_at
      ?? null;
    const hasTelemetryHeartbeat = Boolean(heartbeatSource);
    const facilityTone = hasTelemetryHeartbeat
      ? (hasPass
        ? admittedState === "ALERT"
          ? "critical"
          : "watch"
        : "stable")
      : "empty";

    const intelligenceMode = hasTelemetryHeartbeat
      ? deriveIntelligenceMode({
        hasRealSiiOutput,
        latestUploadSnapshot: effectiveLatestUploadSnapshot,
      })
      : "empty";
    const connectionSummary = heartbeatSource
      ? `Updated ${formatClockTime(heartbeatSource)} CT`
      : "Awaiting telemetry heartbeat";
    const connectionStatusLine = apiStatus.state === "online"
      ? (heartbeatSource ? "Data stream active" : "Awaiting telemetry data")
      : "Connection degraded";
    const dataFreshness = classifyDataFreshness({
      heartbeatAt: heartbeatSource,
      online: apiStatus.state === "online",
    });
    const siiVerification = {
      verified: effectiveLatestUploadSnapshot?.sii_completed === true,
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
  }, [apiStatus.state, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, hasRealSiiOutput, intelligenceStatus, roomContext.primary, systems, systemsState, telemetryTick]);

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
    setGuidedDemo({ active: false, isPlaying: false, stepIndex: 0, elapsedMs: 0 });
    setDemoDataConnectionsTab(null);
    await Promise.allSettled([
      apiFetch("/api/data/reset", {
        method: "POST",
        accessCode,
      }),
      apiFetch("/api/data-connections/reset-all", {
        method: "POST",
        accessCode,
      }),
    ]);
    await loadLatestUploadState({ includePersisted: false });
    await loadFacilitySystems();
  }, [accessCode, loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest, setIsDemoMode]);

  const applyDemoStep = useCallback((index) => {
    const step = DEMO_STEPS[index] ?? DEMO_STEPS[0];
    setActiveWorkspace(step.workspace);
    setDemoDataConnectionsTab(step.workspace === "data-connections" && step.tab ? step.tab : null);
  }, []);

  const startGuidedDemo = useCallback(() => {
    setGuidedDemo({ active: true, isPlaying: true, stepIndex: 0, elapsedMs: 0 });
    applyDemoStep(0);
  }, [applyDemoStep]);

  const toggleGuidedDemoPlayback = useCallback(() => {
    setGuidedDemo((current) => ({ ...current, active: true, isPlaying: !current.isPlaying }));
  }, []);

  const gotoGuidedDemoStep = useCallback((nextIndex) => {
    const normalized = ((nextIndex % DEMO_STEPS.length) + DEMO_STEPS.length) % DEMO_STEPS.length;
    setGuidedDemo((current) => ({ ...current, active: true, isPlaying: false, stepIndex: normalized, elapsedMs: 0 }));
    applyDemoStep(normalized);
  }, [applyDemoStep]);

  const restartGuidedDemo = useCallback(() => {
    setGuidedDemo({ active: true, isPlaying: true, stepIndex: 0, elapsedMs: 0 });
    applyDemoStep(0);
  }, [applyDemoStep]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SESSION_INTENT_STORAGE_KEY, effectiveSessionIntent);
  }, [effectiveSessionIntent]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.setAttribute("data-domain-mode", domainMode || "aquatic");
  }, [domainMode]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setAppReady(true);
    window.__NERAIUM_APP_READY__ = true;
  }, []);

  useEffect(() => {
    if (!guidedDemo.active || !guidedDemo.isPlaying) return;
    const timer = window.setInterval(() => {
      setGuidedDemo((current) => {
        if (!current.active || !current.isPlaying) return current;
        const nextElapsed = current.elapsedMs + 100;
        if (nextElapsed < STEP_DURATION_MS) {
          return { ...current, elapsedMs: nextElapsed };
        }
        const nextStep = (current.stepIndex + 1) % DEMO_STEPS.length;
        applyDemoStep(nextStep);
        return { ...current, stepIndex: nextStep, elapsedMs: 0 };
      });
    }, 100);
    return () => window.clearInterval(timer);
  }, [applyDemoStep, guidedDemo.active, guidedDemo.isPlaying]);

  function renderWithBackControl(content) {
    return (
      <div style={{ position: "relative", minHeight: "100svh" }}>
        <button
          type="button"
          className="system-gate__settings-action"
          onClick={() => setActiveWorkspace("system-body")}
          aria-label="Back to Gate"
          style={{
            position: "fixed",
            top: "max(12px, env(safe-area-inset-top, 0px))",
            left: "max(12px, env(safe-area-inset-left, 0px))",
            zIndex: 1000,
            width: "fit-content",
            paddingInline: "12px",
            backdropFilter: "blur(10px)",
          }}
        >
          Back to Gate
        </button>
        {content}
      </div>
    );
  }

  if (activeWorkspace === "data-connections") {
    return renderWithBackControl(
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
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
        demoState={guidedDemo}
        demoTabId={demoDataConnectionsTab}
        onActivateDemo={startGuidedDemo}
        onToggleDemoPlayback={toggleGuidedDemoPlayback}
        onPreviousDemoStep={() => gotoGuidedDemoStep(guidedDemo.stepIndex - 1)}
        onNextDemoStep={() => gotoGuidedDemoStep(guidedDemo.stepIndex + 1)}
        onRestartDemo={restartGuidedDemo}
      />
      </div>
    );
  }

  if (activeWorkspace === "historical-replay") { 
    return renderWithBackControl( 
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}> 
      <Suspense fallback={<div className="workspace-grid"><Panel title="Loading Replay" className="span-12"><p className="narrative-text">Preparing replay workspace...</p></Panel></div>}>
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
          currentSession={currentSession} 
          domainMode={domainMode} 
          onReplayFrameChange={handleReplayFrameChange} 
          onReplayModeChange={handleReplayModeChange} 
        />
      </Suspense>
      </div> 
    ); 
  } 

  if (activeWorkspace === "governance-admin") { 
    return renderWithBackControl( 
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}> 
      <Suspense fallback={<div className="workspace-grid"><Panel title="Loading Governance" className="span-12"><p className="narrative-text">Preparing governance workspace...</p></Panel></div>}>
        <GovernanceAdminWorkspace 
          apiFetch={apiFetch} 
          accessCode={accessCode} 
          Panel={Panel} 
          EmptyState={EmptyState}
        onBackToGate={() => setActiveWorkspace("system-body")}
        /> 
      </Suspense>
      </div> 
    ); 
  } 

  return (
    <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
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
      domainMode={domainMode}
      onDomainModeChange={setDomainMode}
    />
    </div>
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
