import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react"; 
import { apiFetch } from "./config"; 
import { ENABLE_ADMISSION_GATE } from "./config";
import SystemTopologyWorkspace from "./components/SystemTopologyWorkspace"; 
import DataConnectionsWorkspace from "./components/DataConnectionsWorkspace"; 
import { EmptyState, MetricGrid, Panel } from "./components/workspacePrimitives"; 
import useFacilityRuntime from "./hooks/useFacilityRuntime"; 
import * as uploadStateView from "./viewModels/uploadState"; 
import { classifyDataFreshness, deriveIntelligenceMode } from "./viewModels/systemState"; 
import { deriveCurrentSession } from "./viewModels/currentSession"; 
import { logoutUser } from "./services/api/authApi";
import { normalizeUploadStatus, uploadStateMessage } from "./viewModels/uploadFlow";

const StructuralReplayWorkspace = lazy(() => import("./components/StructuralReplayWorkspace"));
const GovernanceAdminWorkspace = lazy(() => import("./components/GovernanceAdminWorkspace"));

const SESSION_INTENT_STORAGE_KEY = "neraium.session_intent";
const ALLOW_PERSISTED_LATEST_STORAGE_KEY = "neraium.allow_persisted_latest";

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
  const [appReady, setAppReady] = useState(false);
  const [resetGuardActive, setResetGuardActive] = useState(false);
  const [completedUploadOverride, setCompletedUploadOverride] = useState(null);
  const [gateUploadCompleteSeen, setGateUploadCompleteSeen] = useState(false);
  const [gateStateOverride, setGateStateOverride] = useState("");

  const {
    apiStatus,
    systems,
    systemsState,
    intelligenceStatus,
    latestUploadResult,
    latestUploadSnapshot,
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
  });

  const guardedLatestUploadResult = resetGuardActive ? null : (completedUploadOverride ?? latestUploadResult);
  const guardedLatestUploadSnapshot = resetGuardActive ? uploadStateView.buildEmptyLatestUploadSnapshot() : latestUploadSnapshot;

  const hasRealSiiOutput = useMemo(
    () => uploadStateView.hasVerifiedSiiCompletion({
      latestResult: guardedLatestUploadResult,
      latestSnapshot: guardedLatestUploadSnapshot,
    }),
    [guardedLatestUploadResult, guardedLatestUploadSnapshot],
  );
  const hasObservableUploadSession = useMemo(
    () => gateUploadCompleteSeen || Boolean(completedUploadOverride) || uploadStateView.hasActiveTelemetrySnapshot(guardedLatestUploadSnapshot) || uploadStateView.hasFullUploadResult(guardedLatestUploadResult),
    [gateUploadCompleteSeen, completedUploadOverride, guardedLatestUploadResult, guardedLatestUploadSnapshot],
  );
  const effectiveSessionIntent = sessionIntent;
  useEffect(() => {
    if (
      resetGuardActive
      || !allowPersistedLatest
      || sessionIntent !== "neutral"
      || !hasObservableUploadSession
    ) {
      return;
    }
    setSessionIntent("resumed");
    setGateStateOverride("Monitoring");
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, "1");
    }
  }, [allowPersistedLatest, hasObservableUploadSession, resetGuardActive, sessionIntent]);
  const hasCurrentUploadResult =
    (effectiveSessionIntent === "current" || gateUploadCompleteSeen || Boolean(completedUploadOverride))
    && hasObservableUploadSession;
  const hasResumedSession = effectiveSessionIntent === "resumed" && hasObservableUploadSession;
  const hasActiveSession = hasCurrentUploadResult || hasResumedSession;
  const effectiveLatestUploadResult = hasActiveSession
    ? (completedUploadOverride ?? guardedLatestUploadResult ?? (gateUploadCompleteSeen ? buildGateFallbackUploadResult() : null))
    : null;
  const effectiveLatestUploadSnapshot = hasActiveSession
    ? guardedLatestUploadSnapshot
    : uploadStateView.buildEmptyLatestUploadSnapshot();
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
    const hasPass = ENABLE_ADMISSION_GATE && gateOutcome === "PASS" && ["WATCH", "ALERT"].includes(admittedState);
    const uploadTone = deriveUploadTone(effectiveLatestUploadResult);

    const heartbeatSource =
      hasObservableUploadSession
        ? (
          effectiveLatestUploadSnapshot?.last_processed_at
          ?? effectiveLatestUploadSnapshot?.last_upload_at
          ?? effectiveLatestUploadResult?.last_processed_at
          ?? effectiveLatestUploadResult?.completed_at
          ?? effectiveLatestUploadResult?.processing_trace?.completed_at
          ?? effectiveLatestUploadResult?.sii_intelligence?.last_updated
          ?? new Date().toISOString()
        )
        : null;
    const hasTelemetryHeartbeat = Boolean(heartbeatSource);
    const facilityTone = hasTelemetryHeartbeat
      ? (hasPass
        ? admittedState === "ALERT"
          ? "critical"
          : "watch"
        : uploadTone)
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
      latestUploadResult: completedUploadOverride ?? effectiveLatestUploadResult,
      latestUploadSnapshot: effectiveLatestUploadSnapshot,
      currentSession,
      systems,
      systemsState,
      intelligenceStatus,
      telemetryTick,
    };
  }, [apiStatus.state, completedUploadOverride, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, hasObservableUploadSession, hasRealSiiOutput, intelligenceStatus, roomContext.primary, systems, systemsState, telemetryTick]);
  const gateProcessing = useMemo(() => deriveGateProcessing(effectiveLatestUploadSnapshot), [effectiveLatestUploadSnapshot]);

  const handleReplayFrameChange = useCallback((frame, meta) => {
    setHistorianReplayState((current) => ({ ...current, frame, meta }));
  }, []);

  const handleReplayModeChange = useCallback((enabled) => {
    setHistorianReplayState((current) => ({ ...current, enabled }));
  }, []);

  const handleGateUploadComplete = useCallback(async (completedPayload = null) => {
    setResetGuardActive(false);
    setIsDemoMode(false);
    setAllowPersistedLatest(true);
    setGateUploadCompleteSeen(true);
    setGateStateOverride("Monitoring");
    if (completedPayload && typeof completedPayload === "object") {
      setCompletedUploadOverride(completedPayload);
    }
    await loadLatestUploadState({ includePersisted: true });
    setSessionIntent("current");
    await loadFacilitySystems();
  }, [loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest, setIsDemoMode]);

  const handleResumePreviousSession = useCallback(async () => {
    setResetGuardActive(false);
    setAllowPersistedLatest(true);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, "1");
    }
    const hasResult = await loadLatestUploadState({ includePersisted: true });
    setSessionIntent(hasResult ? "resumed" : "neutral");
    await loadFacilitySystems();
    setActiveWorkspace("system-body");
  }, [loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest]);

  const handleResetDemo = useCallback(async () => {
    setResetGuardActive(true);
    setSessionIntent("neutral");
    setIsDemoMode(false);
    setAllowPersistedLatest(false);
    clearUploadSessionState();
    setCompletedUploadOverride(null);
    setGateUploadCompleteSeen(false);
    setGateStateOverride("");
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("neraium.last_upload_job_id");
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, "0");
    }
    setHistorianReplayState({ enabled: false, frame: null, meta: null });
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
  }, [accessCode, clearUploadSessionState, loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest, setIsDemoMode]);


  const handleSignOut = useCallback(async () => {
    await logoutUser();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SESSION_INTENT_STORAGE_KEY, effectiveSessionIntent);
  }, [effectiveSessionIntent]);

  useEffect(() => {
    if (!allowPersistedLatest && effectiveSessionIntent !== "neutral") {
      setSessionIntent("neutral");
    }
  }, [allowPersistedLatest, effectiveSessionIntent]);

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

  function renderWithBackControl(content) {
    return (
      <div style={{ position: "relative", minHeight: "100svh" }}>
        <button
          type="button"
          className="system-gate__settings-action"
          onClick={async () => {
            setGateUploadCompleteSeen(true);
            setGateStateOverride("Monitoring");
            setSessionIntent("current");
            const hasResult = await loadLatestUploadState({ includePersisted: true });
            if (!hasResult) {
              setCompletedUploadOverride((current) => current ?? buildGateFallbackUploadResult());
            }
            await loadFacilitySystems();
            setActiveWorkspace("system-body");
          }}
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
      liveOps={{
        ...liveOps,
        replayOverlay: historianReplayState.frame ?? null,
      }}
      replayFrame={historianReplayState.frame}
      selectedTarget={null}
      onSelectTarget={() => {}}
      apiFetch={apiFetch}
      accessCode={accessCode}
      onWorkspaceNavigate={setActiveWorkspace}
      onSignOut={handleSignOut}
      onUploadComplete={handleGateUploadComplete}
      domainMode={domainMode}
      domainDetection={domainDetection}
      gateProcessing={gateProcessing}
      gateStateOverride={gateStateOverride}
    />
  </div>
  );
}


function buildGateFallbackUploadResult() {
  const now = new Date().toISOString();
  return {
    filename: "Uploaded telemetry",
    row_count: 1,
    column_count: 1,
    rows_processed: 1,
    columns_detected: 1,
    operating_state: "Monitoring",
    drift_status: "info",
    last_processed_at: now,
    completed_at: now,
    timestamp_profile: {
      first_timestamp: now,
      last_timestamp: now,
    },
    sii_intelligence: {
      facility_state: "Monitoring",
      urgency: "info",
      primary_room: "Uploaded telemetry",
      neraium_score: 0,
      last_updated: now,
      replay_timeline: {
        meta: { frame_count: 1 },
        timeline: [
          {
            total_frames: 1,
            affected_subsystem: "Uploaded telemetry",
            cognition_state: { facility_state: "Monitoring", canonical_phase: "stable_topology" },
            topology_state: { drift_index: 0 },
            propagation_state: {},
            evidence_state: {},
            row_start: 1,
            row_end: 1,
            timestamp_start: now,
            timestamp_end: now,
          },
        ],
      },
    },
    replay_timeline: {
      meta: { frame_count: 1 },
      timeline: [
        {
          total_frames: 1,
          affected_subsystem: "Uploaded telemetry",
          cognition_state: { facility_state: "Monitoring", canonical_phase: "stable_topology" },
          topology_state: { drift_index: 0 },
          propagation_state: {},
          evidence_state: {},
          row_start: 1,
          row_end: 1,
          timestamp_start: now,
          timestamp_end: now,
        },
      ],
    },
  };
}

function deriveGateProcessing(snapshot) {
  const rawStatus = String(snapshot?.status ?? snapshot?.processing_state ?? "");
  const status = normalizeUploadStatus(rawStatus);
  const processingStates = new Set([
    "uploading",
    "queued",
    "validating_schema",
    "parsing",
    "baseline_modeling",
    "structural_scoring",
    "cognition_ready",
    "generating_replay",
    "writing_state",
  ]);
  const percentByStage = {
    uploading: 12,
    queued: 20,
    validating_schema: 30,
    parsing: 45,
    baseline_modeling: 60,
    structural_scoring: 75,
    cognition_ready: 86,
    generating_replay: 93,
    writing_state: 97,
  };
  const percent = Number(snapshot?.percent ?? snapshot?.progress);
  return {
    active: processingStates.has(status),
    percent: Number.isFinite(percent) ? Math.max(1, Math.min(99, Math.round(percent))) : (percentByStage[status] ?? 0),
    label: String(snapshot?.progress_label ?? snapshot?.message ?? uploadStateMessage(status)),
  };
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
