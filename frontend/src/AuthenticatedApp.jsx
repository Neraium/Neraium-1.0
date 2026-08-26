import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch, ENABLE_ADMISSION_GATE } from "./config";

import WorkspaceLoadingState from "./components/WorkspaceLoadingState";
import useFacilityRuntime from "./hooks/useFacilityRuntime";
import useWorkspaceSessionController, { readStoredAllowPersistedLatest } from "./hooks/useWorkspaceSessionController";
import { logoutUser } from "./services/api/authApi";
import {
  CURRENT_WORKSPACE_STORAGE_KEY,
  activateDatasetCacheScope,
  clearDatasetSessionCache,
  getCurrentWorkspaceId,
  resolveAuthorizedWorkspaceSelection,
  setCurrentWorkspaceId,
} from "./services/datasetSessionCache";
import { resolveSessionStore } from "./viewModels/sessionState";
import { classifyDataFreshness, deriveIntelligenceMode } from "./viewModels/systemState";
import {
  analysisBelongsToBaseline,
  baselineAnalysisRoutePath,
  baselineComparisonRoutePath,
  baselineRoutePath,
  parseBaselineAnalysisRoute,
  parseBaselineComparisonRoute,
  parseBaselineRoute,
} from "./viewModels/baselineSelection";

const AppWorkspaceRouter = lazy(() => import("./components/AppWorkspaceRouter"));
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
  if (pathname === "/workspace/live-monitoring") {
    window.history.replaceState({}, "", WORKSPACE_PATHS["system-body"]);
    return "system-body";
  }
  if (parseBaselineRoute(pathname) || parseBaselineComparisonRoute(pathname)) return "data-connections";
  if (parseBaselineAnalysisRoute(pathname)) return "system-body";
  if (["/portfolio", "/workspace", "/work"].includes(pathname) || pathname.startsWith("/sites/") || pathname.startsWith("/systems") || pathname.startsWith("/work/") || pathname.startsWith("/findings") || pathname.startsWith("/investigations") || pathname.startsWith("/evidence") || pathname.startsWith("/trace")) return "system-body";
  return PATH_WORKSPACES[pathname] ?? "system-body";
}

function initializeAuthenticatedRoute(currentUser, workspaceSession) {
  const baselineRoute = parseBaselineRoute();
  const comparisonRoute = parseBaselineComparisonRoute();
  const analysisRoute = parseBaselineAnalysisRoute();
  const routeIdentity = baselineRoute ?? comparisonRoute ?? analysisRoute;
  let datasetScopeKey = "authenticated";
  try {
    const workspaceId = resolveAuthorizedWorkspaceSelection(workspaceSession).workspaceId;
    datasetScopeKey = activateDatasetCacheScope(currentUser, workspaceId).scopeKey;
  } catch {
    // Browser storage is an optional cache; authenticated routing remains available without it.
  }
  return {
    activeWorkspace: readInitialWorkspaceRoute(),
    baselineRoute,
    comparisonRoute,
    analysisRoute,
    routeIdentity,
    datasetScopeKey,
  };
}

function AuthenticatedApp({ currentUser, workspaceSession, onSignedOut }) {
  const accessCode = String(import.meta.env.VITE_NERAIUM_API_TOKEN ?? "").trim();
  const [initialRoute] = useState(() => initializeAuthenticatedRoute(currentUser, workspaceSession));
  const [activeWorkspace, setActiveWorkspaceState] = useState(initialRoute.activeWorkspace);
  const [selectedBaselineIdentity, setSelectedBaselineIdentity] = useState(initialRoute.baselineRoute);
  const [comparisonBaselineIdentity, setComparisonBaselineIdentity] = useState(initialRoute.comparisonRoute);
  const [selectedAnalysisIdentity, setSelectedAnalysisIdentity] = useState(initialRoute.analysisRoute);
  const [activeBaselineIdentity, setActiveBaselineIdentity] = useState(initialRoute.routeIdentity);
  const [pendingUploadFiles, setPendingUploadFiles] = useState([]);
  const [resultsNavigationKey, setResultsNavigationKey] = useState(0);
  const [appReady, setAppReady] = useState(false);
  const [signOutPending, setSignOutPending] = useState(false);
  const [datasetScopeKey, setDatasetScopeKey] = useState(initialRoute.datasetScopeKey);
  const [currentWorkspaceId, setCurrentWorkspaceIdState] = useState(() => resolveAuthorizedWorkspaceSelection(workspaceSession).workspaceId);
  const initialAllowPersistedLatest = readStoredAllowPersistedLatest();
  const hasAccess = true;
  const authorizedWorkspaces = useMemo(
    () => resolveAuthorizedWorkspaceSelection(workspaceSession, currentWorkspaceId).workspaces,
    [currentWorkspaceId, workspaceSession],
  );
  const currentWorkspace = useMemo(
    () => authorizedWorkspaces.find((workspace) => workspace.workspace_id === currentWorkspaceId) ?? authorizedWorkspaces[0],
    [authorizedWorkspaces, currentWorkspaceId],
  );

  const handleWorkspaceChange = useCallback((workspaceId) => {
    const selection = resolveAuthorizedWorkspaceSelection(workspaceSession, workspaceId);
    setCurrentWorkspaceId(selection.workspaceId);
  }, [workspaceSession]);

  const setActiveWorkspace = useCallback((workspaceId) => {
    const nextWorkspace = workspaceId === "home" ? "home" : workspaceId;
    setActiveWorkspaceState(nextWorkspace);
    setSelectedBaselineIdentity(null);
    setComparisonBaselineIdentity(null);
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
    setComparisonBaselineIdentity(null);
    setSelectedAnalysisIdentity(null);
    setActiveBaselineIdentity(identity);
    setActiveWorkspaceState("data-connections");
    return true;
  }, []);

  const handleBaselineClosedForComparison = useCallback((identity) => {
    const nextPath = baselineComparisonRoutePath(identity?.portfolioId, identity?.baselineId);
    if (!nextPath) return false;
    if (identity?.baselineId) setActiveBaselineIdentity(identity);
    setSelectedBaselineIdentity(null);
    setComparisonBaselineIdentity(identity);
    setSelectedAnalysisIdentity(null);
    setActiveWorkspaceState("data-connections");
    if (typeof window !== "undefined" && window.location.pathname !== nextPath) {
      window.history.pushState({}, "", nextPath);
    }
    return true;
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
    commitCompletedUploadState,
    clearUploadSessionState,
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
    activeUploadAttempt,
    handleReplayFrameChange,
    handleReplayModeChange,
    handleUploadAttemptStarted,
    handleUploadAttemptIdentified,
    handleUploadAttemptCleared,
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
    commitCompletedUploadState,
    clearUploadSessionState,
    setIsDemoMode,
    activeBaselineIdentity,
  });

  const handleHistoricalBaselineSelected = useCallback((identity, options) => {
    handleUploadAttemptCleared();
    return handleBaselineSelected(identity, options);
  }, [handleBaselineSelected, handleUploadAttemptCleared]);

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
    };
  }, [analysisHistory, apiStatus.state, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, hasRealSiiOutput, intelligenceStatus, persistedLatestUpload, previousUploadHistory, resolvedSessionStore, roomContext.primary, systems, systemsState, telemetrySession]);

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
    setComparisonBaselineIdentity(null);
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
      onSignedOut?.("You have been signed out.");
    } catch (error) {
      logSessionDiagnostic("sign out failed", error);
    } finally {
      setSignOutPending(false);
    }
  }, [logSessionDiagnostic, onSignedOut, resetSignedOutSession, signOutPending]);

  const handleTelemetryAnalysisComplete = useCallback(async (completedPayload = null, options = {}) => {
    const outcome = await handleGateUploadComplete(completedPayload, options);
    if (outcome?.ignored) return outcome;
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
    return outcome;
  }, [activeBaselineIdentity, handleGateUploadComplete]);

  useEffect(() => {
    const handleSessionExpired = () => {
      resetSignedOutSession();
      onSignedOut?.("Your session expired. Sign in again to continue.");
    };
    window.addEventListener("neraium:session-expired", handleSessionExpired);
    return () => window.removeEventListener("neraium:session-expired", handleSessionExpired);
  }, [onSignedOut, resetSignedOutSession]);

  useEffect(() => {
    if (typeof window === "undefined" || !currentUser) return undefined;
    const applyWorkspaceChange = () => {
      const selection = resolveAuthorizedWorkspaceSelection(workspaceSession, getCurrentWorkspaceId());
      if (selection.stale) setCurrentWorkspaceId(selection.workspaceId);
      const scope = activateDatasetCacheScope(currentUser, selection.workspaceId);
      setCurrentWorkspaceIdState(selection.workspaceId);
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
  }, [clearUploadSessionState, currentUser, loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest, workspaceSession]);

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
      const comparisonRoute = parseBaselineComparisonRoute();
      const analysisRoute = parseBaselineAnalysisRoute();
      setSelectedBaselineIdentity(baselineRoute);
      setComparisonBaselineIdentity(comparisonRoute);
      setSelectedAnalysisIdentity(analysisRoute);
      setActiveBaselineIdentity(baselineRoute ?? comparisonRoute ?? analysisRoute ?? null);
      setActiveWorkspaceState(readInitialWorkspaceRoute());
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

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
        activeUploadAttempt={activeUploadAttempt}
        handleUploadAttemptStarted={handleUploadAttemptStarted}
        handleUploadAttemptIdentified={handleUploadAttemptIdentified}
        handleResumePreviousSession={handleResumePreviousSession}
        handleReopenHistoricalAnalysis={handleReopenHistoricalAnalysis}
        handleDeleteHistoricalAnalysis={handleDeleteHistoricalAnalysis}
        handleResetDemo={handleResetDemo}
        handleReplayFrameChange={handleReplayFrameChange}
        handleReplayModeChange={handleReplayModeChange}
        handleSignOut={handleSignOut}
        signOutPending={signOutPending}
        currentUser={currentUser}
        workspaceSession={{ ...workspaceSession, workspaces: authorizedWorkspaces }}
        currentWorkspace={currentWorkspace}
        onWorkspaceChange={handleWorkspaceChange}
        setActiveWorkspace={setActiveWorkspace}
        selectedBaselineIdentity={selectedBaselineIdentity}
        comparisonBaselineIdentity={comparisonBaselineIdentity}
        selectedAnalysisIdentity={selectedAnalysisIdentity}
        activeBaselineIdentity={activeBaselineIdentity}
        datasetScopeKey={datasetScopeKey}
        onBaselineSelected={handleHistoricalBaselineSelected}
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

const CLOCK_FORMATTER = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

function formatClockTime(value) {
  if (!value) return "Not available";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return CLOCK_FORMATTER.format(date);
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

export default AuthenticatedApp;
