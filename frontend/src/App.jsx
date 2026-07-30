import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch, ENABLE_ADMISSION_GATE } from "./config";

import WorkspaceLoadingState from "./components/WorkspaceLoadingState";
import useFacilityRuntime from "./hooks/useFacilityRuntime";
import useWorkspaceSessionController, { readStoredAllowPersistedLatest } from "./hooks/useWorkspaceSessionController";
import { fetchCurrentUser, logoutUser } from "./services/api/authApi";
import {
  CURRENT_WORKSPACE_STORAGE_KEY,
  activateDatasetCacheScope,
  clearDatasetSessionCache,
  getCurrentWorkspaceId,
  setCurrentWorkspaceId,
} from "./services/datasetSessionCache";
import { resolveSessionStore } from "./viewModels/sessionState";
import { classifyDataFreshness, deriveIntelligenceMode } from "./viewModels/systemState";
import {
  analysisBelongsToBaseline,
  baselineAnalysisRoutePath,
  baselineRoutePath,
  parseBaselineAnalysisRoute,
  parseBaselineRoute,
} from "./viewModels/baselineSelection";

const AppWorkspaceRouter = lazy(() => import("./components/AppWorkspaceRouter"));
const AuthScreen = lazy(() => import("./components/AuthScreen"));

const HOME_PATH = "/";
const WORKSPACE_PATHS = {
  home: "/home",
  "system-body": "/sites/current",
  "data-connections": "/workspace/data-sources",
  "observation-center": "/workspace/insights",
  "system-story": "/workspace/advanced",
  "help-changelog": "/workspace/help",
  "governance-admin": "/workspace/admin",
};
const PATH_WORKSPACES = Object.fromEntries(Object.entries(WORKSPACE_PATHS).map(([workspace, path]) => [path, workspace]));

function readInitialWorkspaceRoute() {
  if (typeof window === "undefined") return "system-body";
  const pathname = window.location.pathname.replace(/\/+$/, "") || HOME_PATH;
  if (pathname === HOME_PATH || pathname === "/signin") return "system-body";
  if (parseBaselineRoute(pathname)) return "data-connections";
  if (parseBaselineAnalysisRoute(pathname)) return "system-body";
  if (["/portfolio", "/workspace"].includes(pathname) || pathname.startsWith("/sites/") || pathname.startsWith("/systems") || pathname.startsWith("/findings") || pathname.startsWith("/investigations") || pathname.startsWith("/evidence") || pathname.startsWith("/trace")) return "system-body";
  return PATH_WORKSPACES[pathname] ?? "system-body";
}

function App() {
  const accessCode = String(import.meta.env.VITE_NERAIUM_API_TOKEN ?? "").trim();
  const [activeWorkspace, setActiveWorkspaceState] = useState(() => readInitialWorkspaceRoute());
  const [selectedBaselineIdentity, setSelectedBaselineIdentity] = useState(() => parseBaselineRoute());
  const [selectedAnalysisIdentity, setSelectedAnalysisIdentity] = useState(() => parseBaselineAnalysisRoute());
  const [activeBaselineIdentity, setActiveBaselineIdentity] = useState(() => parseBaselineRoute() ?? parseBaselineAnalysisRoute());
  const [pendingUploadFiles, setPendingUploadFiles] = useState([]);
  const [resultsNavigationKey, setResultsNavigationKey] = useState(0);
  const [appReady, setAppReady] = useState(false);
  const [authState, setAuthState] = useState({ status: "checking", user: null, notice: "", errorKind: null });
  const [authCheckAttempt, setAuthCheckAttempt] = useState(0);
  const [signOutPending, setSignOutPending] = useState(false);
  const [datasetScopeKey, setDatasetScopeKey] = useState("signed-out");
  const initialAllowPersistedLatest = readStoredAllowPersistedLatest();
  const hasAccess = authState.status === "authenticated" && Boolean(authState.user);

  const setActiveWorkspace = useCallback((workspaceId) => {
    const nextWorkspace = workspaceId === "home" ? "home" : workspaceId;
    setActiveWorkspaceState(nextWorkspace);
    setSelectedBaselineIdentity(null);
    setSelectedAnalysisIdentity(null);

    if (typeof window === "undefined") return;
    const nextPath = WORKSPACE_PATHS[nextWorkspace] ?? WORKSPACE_PATHS["system-body"];
    if (window.location.pathname !== nextPath) window.history.pushState({}, "", nextPath);
  }, []);

  const handleBaselineSelected = useCallback((identity, { replace = false } = {}) => {
    const nextPath = baselineRoutePath(identity?.portfolioId, identity?.baselineId);
    if (!nextPath) return false;
    if (typeof window !== "undefined") {
      try {
        if (window.location.pathname !== nextPath) {
          window.history[replace ? "replaceState" : "pushState"]({}, "", nextPath);
        }
        if (window.location.pathname !== nextPath) return false;
      } catch {
        return false;
      }
    }
    setSelectedBaselineIdentity(identity);
    setSelectedAnalysisIdentity(null);
    setActiveBaselineIdentity(identity);
    setActiveWorkspaceState("data-connections");
    return true;
  }, []);

  const handleBaselineClosedForComparison = useCallback((identity) => {
    if (identity?.baselineId) setActiveBaselineIdentity(identity);
    setSelectedBaselineIdentity(null);
    setSelectedAnalysisIdentity(null);
    setActiveWorkspaceState("data-connections");
    if (typeof window !== "undefined" && window.location.pathname !== WORKSPACE_PATHS["data-connections"]) {
      window.history.pushState({}, "", WORKSPACE_PATHS["data-connections"]);
    }
  }, []);

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
    hasAccess,
    accessCode,
    formatClockTime,
    formatEndpoint,
    buildProtectedRequestMessage,
    initialAllowPersistedLatest,
    datasetScopeKey,
    activeAnalysisIdentity: selectedAnalysisIdentity,
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
    analysisHistory,
    handleReplayFrameChange,
    handleReplayModeChange,
    handleGateUploadComplete,
    handleResumePreviousSession,
    handleReopenHistoricalAnalysis,
    handleDeleteHistoricalAnalysis,
    handleResetDemo,
    handleBackToGate,
    handleRetryWorkspace,
  } = useWorkspaceSessionController({
    activeWorkspace,
    datasetScopeKey,
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
    activeBaselineIdentity,
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
        ? [{ detail: governance?.why_summary ?? canonicalFinding.summary ?? "Governed insight approved for operator review." }]
        : (canonicalFinding.exists ? [{ detail: canonicalFinding.summary }] : []),
      interventionItems: hasPass
        ? [{
          label: governance?.affected_subsystem ?? roomContext.primary,
          recommendation: governance?.operator_focus ?? "Review the affected operating pattern.",
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
      analysisHistory,
      session: resolvedSessionStore,
      systems,
      systemsState,
      intelligenceStatus,
      telemetryTick,
    };
  }, [analysisHistory, apiStatus.state, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, hasRealSiiOutput, intelligenceStatus, persistedLatestUpload, previousUploadHistory, resolvedSessionStore, roomContext.primary, systems, systemsState, telemetrySession, telemetryTick]);

  const logSessionDiagnostic = useCallback((event, error = null) => {
    if (!import.meta.env.DEV) return;
    console.warn(`[neraium] ${event}`, {
      kind: error?.kind ?? null,
      name: error?.name ?? null,
    });
  }, []);

  const resetSignedOutSession = useCallback(() => {
    setDatasetScopeKey("signed-out");
    setActiveBaselineIdentity(null);
    setSelectedAnalysisIdentity(null);
    try {
      clearDatasetSessionCache();
    } catch (error) {
      logSessionDiagnostic("dataset cache cleanup failed", error);
    }
    try {
      clearUploadSessionState();
    } catch (error) {
      logSessionDiagnostic("upload session cleanup failed", error);
    }
  }, [clearUploadSessionState, logSessionDiagnostic]);

  const handleSignOut = useCallback(async () => {
    if (signOutPending) return;
    setSignOutPending(true);
    try {
      await logoutUser();
      resetSignedOutSession();
      setAuthState({ status: "signed-out", user: null, notice: "You have been signed out.", errorKind: null });
    } catch (error) {
      setAuthState((current) => ({ ...current, notice: String(error?.message ?? "Sign out failed. Try again.") }));
    } finally {
      setSignOutPending(false);
    }
  }, [resetSignedOutSession, signOutPending]);

  const handleAuthenticated = useCallback((user) => {
    setAuthState({ status: "authenticated", user, notice: "", errorKind: null });
    try {
      const baselineRoute = parseBaselineRoute();
      const analysisRoute = parseBaselineAnalysisRoute();
      const routeIdentity = baselineRoute ?? analysisRoute;
      if (routeIdentity?.portfolioId) {
        setCurrentWorkspaceId(routeIdentity.portfolioId);
        setActiveBaselineIdentity(routeIdentity);
        setSelectedAnalysisIdentity(analysisRoute);
      }
      const scope = activateDatasetCacheScope(user, routeIdentity?.portfolioId ?? getCurrentWorkspaceId());
      setDatasetScopeKey(scope.scopeKey);
    } catch (error) {
      setDatasetScopeKey("authenticated");
      logSessionDiagnostic("dataset scope activation failed", error);
    }
    try {
      clearUploadSessionState();
      setAllowPersistedLatest(true);
    } catch (error) {
      logSessionDiagnostic("authenticated workspace initialization failed", error);
    }
  }, [clearUploadSessionState, logSessionDiagnostic, setAllowPersistedLatest]);

  const handleRetrySession = useCallback(() => {
    setAuthState({ status: "checking", user: null, notice: "", errorKind: null });
    setAuthCheckAttempt((current) => current + 1);
  }, []);

  const handleTelemetryAnalysisComplete = useCallback(async (completedPayload = null, options = {}) => {
    const outcome = await handleGateUploadComplete(completedPayload, options);
    setPendingUploadFiles([]);
    if (options.navigateToGate !== false) {
      const result = outcome?.latestResult ?? null;
      if (analysisBelongsToBaseline(result, activeBaselineIdentity)) {
        const identity = {
          ...activeBaselineIdentity,
          systemId: String(result.system_id),
          analysisRunId: String(result.analysis_run_id ?? result.run_id ?? result.job_id),
        };
        const path = baselineAnalysisRoutePath(identity.portfolioId, identity.baselineId, identity.analysisRunId);
        if (path && typeof window !== "undefined") window.history.replaceState({}, "", path);
        setSelectedAnalysisIdentity(identity);
        setActiveBaselineIdentity(identity);
      }
      setResultsNavigationKey((current) => current + 1);
    }
  }, [activeBaselineIdentity, handleGateUploadComplete]);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    fetchCurrentUser({ signal: controller.signal })
      .then((payload) => {
        if (cancelled) return;
        if (payload?.authenticated && payload?.user) {
          handleAuthenticated(payload.user);
          return;
        }
        resetSignedOutSession();
        setAuthState({ status: "signed-out", user: null, notice: "Sign in to continue.", errorKind: null });
      })
      .catch((error) => {
        if (cancelled || error?.name === "AbortError") return;
        const errorKind = ["backend-unavailable", "malformed-response", "timeout"].includes(error?.kind)
          ? error.kind
          : "backend-unavailable";
        logSessionDiagnostic("session initialization failed", { ...error, kind: errorKind, name: error?.name });
        setAuthState({
          status: "error",
          user: null,
          notice: String(error?.message ?? "Unable to verify your session. Retry session verification."),
          errorKind,
        });
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [authCheckAttempt, handleAuthenticated, logSessionDiagnostic, resetSignedOutSession]);

  useEffect(() => {
    const handleSessionExpired = () => {
      if (authState.status === "checking") {
        logSessionDiagnostic("ignored session-expired event during session initialization");
        return;
      }
      resetSignedOutSession();
      setAuthState({ status: "signed-out", user: null, notice: "Your session expired. Sign in again to continue.", errorKind: null });
    };
    window.addEventListener("neraium:session-expired", handleSessionExpired);
    return () => window.removeEventListener("neraium:session-expired", handleSessionExpired);
  }, [authState.status, logSessionDiagnostic, resetSignedOutSession]);

  useEffect(() => {
    if (typeof window === "undefined" || !authState.user) return undefined;
    const applyWorkspaceChange = () => {
      const scope = activateDatasetCacheScope(authState.user, getCurrentWorkspaceId());
      clearUploadSessionState();
      setAllowPersistedLatest(true);
      setDatasetScopeKey(scope.scopeKey);
      void loadLatestUploadState({ includePersisted: true, forceRefresh: true });
      void loadFacilitySystems({ forceRefresh: true });
    };
    const handleStorage = (event) => {
      if (event.key === CURRENT_WORKSPACE_STORAGE_KEY) applyWorkspaceChange();
    };
    window.addEventListener("neraium:workspace-changed", applyWorkspaceChange);
    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener("neraium:workspace-changed", applyWorkspaceChange);
      window.removeEventListener("storage", handleStorage);
    };
  }, [authState.user, clearUploadSessionState, loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest]);

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

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const handlePopState = () => {
      const baselineRoute = parseBaselineRoute();
      const analysisRoute = parseBaselineAnalysisRoute();
      setSelectedBaselineIdentity(baselineRoute);
      setSelectedAnalysisIdentity(analysisRoute);
      if (baselineRoute ?? analysisRoute) setActiveBaselineIdentity(baselineRoute ?? analysisRoute);
      setActiveWorkspaceState(readInitialWorkspaceRoute());
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  if (authState.status === "checking") {
    return <WorkspaceLoadingState label="Opening Neraium" detail="Checking your secure session." fullScreen />;
  }

  if (authState.status === "error") {
    const errorLabel = authState.errorKind === "timeout"
      ? "Session verification timed out"
      : authState.errorKind === "malformed-response"
        ? "Session response unavailable"
        : "Session service unavailable";
    return (
      <WorkspaceLoadingState
        label={errorLabel}
        detail={authState.notice}
        fullScreen
        variant="error"
        actionLabel="Retry"
        onAction={handleRetrySession}
      />
    );
  }

  if (!hasAccess) {
    return (
      <Suspense fallback={<WorkspaceLoadingState label="Opening secure access" detail="Loading sign-in." fullScreen />}>
        <AuthScreen notice={authState.notice} onAuthenticated={handleAuthenticated} />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<WorkspaceLoadingState label="Opening workspace" detail="Loading the latest site context." fullScreen />}>
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
        handleGateUploadComplete={handleTelemetryAnalysisComplete}
        handleResumePreviousSession={handleResumePreviousSession}
        handleReopenHistoricalAnalysis={handleReopenHistoricalAnalysis}
        handleDeleteHistoricalAnalysis={handleDeleteHistoricalAnalysis}
        handleResetDemo={handleResetDemo}
        handleReplayFrameChange={handleReplayFrameChange}
        handleReplayModeChange={handleReplayModeChange}
        handleSignOut={handleSignOut}
        signOutPending={signOutPending}
        currentUser={authState.user}
        setActiveWorkspace={setActiveWorkspace}
        selectedBaselineIdentity={selectedBaselineIdentity}
        activeBaselineIdentity={activeBaselineIdentity}
        datasetScopeKey={datasetScopeKey}
        onBaselineSelected={handleBaselineSelected}
        onBaselineClosedForComparison={handleBaselineClosedForComparison}
        pendingUploadFiles={pendingUploadFiles}
        setPendingUploadFiles={setPendingUploadFiles}
        resultsNavigationKey={resultsNavigationKey}
      />
    </Suspense>
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
  if (!value) return "Not available";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
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
