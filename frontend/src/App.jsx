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
import { deriveCanonicalFinding } from "./viewModels/operatorFinding";
import { logoutUser } from "./services/api/authApi";
import { normalizeUploadStatus, uploadStateMessage } from "./viewModels/uploadFlow";

const StructuralReplayWorkspace = lazy(() => import("./components/StructuralReplayWorkspace"));
const GovernanceAdminWorkspace = lazy(() => import("./components/GovernanceAdminWorkspace"));
const ObservationCenterWorkspace = lazy(() => import("./components/ObservationCenterWorkspace"));
const HelpChangelogWorkspace = lazy(() => import("./components/HelpChangelogWorkspace"));

const SESSION_INTENT_STORAGE_KEY = "neraium.session_intent";
const ALLOW_PERSISTED_LATEST_STORAGE_KEY = "neraium.allow_persisted_latest";

function readStoredSessionIntent() {
  if (typeof window === "undefined") return "neutral";
  const allowPersisted = window.localStorage.getItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY);
  if (allowPersisted === "0") return "neutral";
  const value = window.localStorage.getItem(SESSION_INTENT_STORAGE_KEY);
  return value === "current" || value === "resumed" ? value : "neutral";
}


function readStoredAllowPersistedLatest() {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY) !== "0";
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
  const initialAllowPersistedLatest = readStoredAllowPersistedLatest();

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
    initialAllowPersistedLatest,
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
  const telemetrySession = useMemo(
    () => uploadStateView.deriveTelemetrySessionState({
      latestUploadResult: guardedLatestUploadResult,
      latestUploadSnapshot: guardedLatestUploadSnapshot,
      latestReplayFrame: historianReplayState.frame,
    }),
    [guardedLatestUploadResult, guardedLatestUploadSnapshot, historianReplayState.frame],
  );
  const hasObservableUploadSession = telemetrySession.hasTelemetry || gateUploadCompleteSeen || Boolean(completedUploadOverride);
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
    ? (completedUploadOverride ?? guardedLatestUploadResult)
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
  const canonicalFinding = useMemo(
    () => deriveCanonicalFinding({ currentSession, latestReplayFrame: historianReplayState.frame }),
    [currentSession, historianReplayState.frame],
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
      latestUploadResult: completedUploadOverride ?? effectiveLatestUploadResult,
      latestUploadSnapshot: effectiveLatestUploadSnapshot,
      currentSession,
      telemetrySession,
      systems,
      systemsState,
      intelligenceStatus,
      telemetryTick,
    };
  }, [apiStatus.state, canonicalFinding, completedUploadOverride, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, hasRealSiiOutput, intelligenceStatus, roomContext.primary, systems, systemsState, telemetrySession, telemetryTick]);
  const gateProcessing = useMemo(() => deriveGateProcessing(effectiveLatestUploadSnapshot), [effectiveLatestUploadSnapshot]);

  const handleReplayFrameChange = useCallback((frame, meta) => {
    setHistorianReplayState((current) => ({ ...current, frame, meta }));
  }, []);

  const handleReplayModeChange = useCallback((enabled) => {
    setHistorianReplayState((current) => ({ ...current, enabled }));
  }, []);

  const handleGateUploadComplete = useCallback(async (completedPayload = null, options = {}) => {
    setResetGuardActive(false);
    setIsDemoMode(false);
    setAllowPersistedLatest(true);
    setGateUploadCompleteSeen(true);
    const completedResult = uploadStateView.resolveCurrentUploadResult(completedPayload)
      ?? (uploadStateView.hasFullUploadResult(completedPayload) ? completedPayload : null);
    if (completedResult) {
      setCompletedUploadOverride(completedResult);
    } else {
      setCompletedUploadOverride(null);
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, "1");
    }
    await loadLatestUploadState({ includePersisted: true });
    setSessionIntent("current");
    await loadFacilitySystems();
    if (options.navigateToGate !== false) {
      setActiveWorkspace("system-body");
    }
  }, [loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest, setIsDemoMode]);

  const handleResumePreviousSession = useCallback(async () => {
    setResetGuardActive(false);
    setAllowPersistedLatest(true);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, "1");
    }
    const hasResult = await loadLatestUploadState({ includePersisted: true });
    if (!hasResult) {
      setCompletedUploadOverride(null);
      setGateUploadCompleteSeen(false);
    }
    setSessionIntent(hasResult ? "resumed" : "neutral");
    await loadFacilitySystems();
    setActiveWorkspace("system-body");
  }, [loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest]);

  const handleResetDemo = useCallback(async () => {
    const [uploadResetResponse, connectionResetResponse] = await Promise.all([
      apiFetch("/api/data/reset", {
        method: "POST",
        accessCode,
      }),
      apiFetch("/api/data-connections/reset-all", {
        method: "POST",
        accessCode,
      }),
    ]);

    const [uploadResetPayload, connectionResetPayload] = await Promise.all([
      uploadResetResponse.json().catch(() => ({})),
      connectionResetResponse.json().catch(() => ({})),
    ]);

    if (!uploadResetResponse.ok || !connectionResetResponse.ok) {
      const detail = uploadResetPayload?.message
        || uploadResetPayload?.detail
        || connectionResetPayload?.message
        || connectionResetPayload?.detail
        || "Reset Everything failed.";
      throw new Error(String(detail));
    }

    setResetGuardActive(true);
    setSessionIntent("neutral");
    setIsDemoMode(false);
    setAllowPersistedLatest(false);
    clearUploadSessionState();
    setCompletedUploadOverride(null);
    setGateUploadCompleteSeen(false);
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("neraium.last_upload_job_id");
      window.localStorage.removeItem(SESSION_INTENT_STORAGE_KEY);
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, "0");
    }
    setHistorianReplayState({ enabled: false, frame: null, meta: null });
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
    if (typeof window === "undefined") return;
    window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, allowPersistedLatest ? "1" : "0");
  }, [allowPersistedLatest]);

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

  const handleBackToGate = useCallback(async () => {
    setGateUploadCompleteSeen(true);
    setSessionIntent("current");
    const hasResult = await loadLatestUploadState({ includePersisted: true });
    if (!hasResult) setCompletedUploadOverride(null);
    await loadFacilitySystems();
    setActiveWorkspace("system-body");
  }, [loadFacilitySystems, loadLatestUploadState]);

  function renderWithBackControl(content) {
    return (
      <div className="workspace-shell-with-back" style={{ minHeight: "100svh" }}>
        <div className="workspace-back-control" aria-label="Workspace navigation">
          <button
            type="button"
            className="system-gate__settings-action"
            onClick={handleBackToGate}
            aria-label="Back to Gate"
          >
            Back to Gate
          </button>
        </div>
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
          canonicalFinding={canonicalFinding}
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

  if (activeWorkspace === "observation-center") {
    return renderWithBackControl(
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
        <Suspense fallback={<div className="workspace-grid"><Panel title="Loading Findings" className="span-12"><p className="narrative-text">Preparing findings...</p></Panel></div>}>
          <ObservationCenterWorkspace
            apiFetch={apiFetch}
            accessCode={accessCode}
            canonicalFinding={canonicalFinding}
            currentSession={currentSession}
            onBackToGate={() => setActiveWorkspace("system-body")}
            onReviewEvidence={() => setActiveWorkspace("historical-replay")}
            onWorkspaceNavigate={setActiveWorkspace}
          />
        </Suspense>
      </div>
    );
  }

  if (activeWorkspace === "help-changelog") {
    return renderWithBackControl(
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
        <Suspense fallback={<div className="workspace-grid"><Panel title="Loading Help" className="span-12"><p className="narrative-text">Preparing help and changelog workspace...</p></Panel></div>}>
          <HelpChangelogWorkspace
            onBackToGate={() => setActiveWorkspace("system-body")}
            onWorkspaceNavigate={setActiveWorkspace}
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
        canonicalFinding,
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
    />
  </div>
  );
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