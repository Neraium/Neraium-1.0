import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL, API_CONFIG_WARNING, apiFetch } from "../config";
import useStableInterval from "./useStableInterval";
import { fetchApiHealth } from "../services/api/healthApi";
import {
  fetchDomainMode,
  fetchEngineIdentity,
  fetchFacilitySystems as fetchSystemFacility,
} from "../services/api/systemApi";
import { clearLatestUploadStateCache, fetchLatestUploadState } from "../services/api/uploadApi";
import { getCurrentWorkspaceId } from "../services/datasetSessionCache";
import * as uploadStateView from "../viewModels/uploadState";
import {
  buildEmptySessionStore,
  buildLatestUploadSessionState,
  reconcileLatestUploadSessionState,
} from "../viewModels/sessionState";
import { normalizeErrorMessage } from "../viewModels/uploadFlow";

const LIVE_REFRESH_INTERVAL_MS = 45000;
const DATA_PROMOTION_STREAK_REQUIRED = 2;
const EMPTY_DEMOTION_STREAK_REQUIRED = 3;

function displayDomainMode(mode) {
  return mode === "aquatic" ? "water_infrastructure" : mode;
}

export default function useFacilityRuntime({
  hasAccess,
  accessCode,
  formatClockTime,
  formatEndpoint,
  buildProtectedRequestMessage,
  initialAllowPersistedLatest = false,
  datasetScopeKey = "anonymous",
  activeAnalysisIdentity = null,
}) {
  const isUploadInProgress = () => (typeof window !== "undefined" && window.__NERAIUM_UPLOAD_IN_PROGRESS__ === true);
  const isUploadJobLocked = () => false;
  const [apiStatus, setApiStatus] = useState({
    state: "checking",
    label: "Sync pending",
    detail: "Establishing facility sync.",
    checkedAt: null,
    attemptCount: 0,
    endpoint: formatEndpoint(API_BASE_URL),
    message: "",
    queue: null,
    diagnostics: null,
  });
  const [systems, setSystems] = useState([]);
  const [systemsState, setSystemsState] = useState("loading");
  const [intelligenceStatus, setIntelligenceStatus] = useState(uploadStateView.buildEmptyIntelligenceStatus());
  const [backendError, setBackendError] = useState(API_CONFIG_WARNING);
  const [latestUploadResult, setLatestUploadResult] = useState(null);
  const [latestUploadSnapshot, setLatestUploadSnapshot] = useState(uploadStateView.buildEmptyLatestUploadSnapshot());
  const [allowPersistedLatest, setAllowPersistedLatest] = useState(Boolean(initialAllowPersistedLatest));
  const [sessionStore, setSessionStore] = useState(buildEmptySessionStore());
  const [demoScenario, setDemoScenario] = useState("drift");
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [domainMode, setDomainModeState] = useState(null);
  const [domainModeResolved, setDomainModeResolved] = useState(false);
  const [domainDetection, setDomainDetection] = useState({ mode: null, source: "default", confidence: 0, evidence: [] });
  const workspaceIdentityKey = `${datasetScopeKey}|portfolio:${String(getCurrentWorkspaceId() || "")}`;
  const uploadIdentityKey = `${workspaceIdentityKey}|analysis:${String(activeAnalysisIdentity?.analysisRunId || "latest")}`;
  const [systemsOwnerKey, setSystemsOwnerKey] = useState(workspaceIdentityKey);
  const [latestUploadOwnerKey, setLatestUploadOwnerKey] = useState(uploadIdentityKey);
  const [domainOwnerKey, setDomainOwnerKey] = useState(workspaceIdentityKey);
  const healthCheckAttemptsRef = useRef(0);
  const latestStabilityRef = useRef({ hasData: false, dataStreak: 0, emptyStreak: 0 });
  const latestUploadResultRef = useRef(null);
  const latestUploadStateRef = useRef(buildLatestUploadSessionState({
    snapshot: uploadStateView.buildEmptyLatestUploadSnapshot(),
    latest_result: null,
  }, { loaded: false }));
  const terminalUploadStateRef = useRef(null);
  const lastKnownGoodTelemetryRef = useRef({ latestResult: null, snapshot: uploadStateView.buildEmptyLatestUploadSnapshot(), sessionStore: buildEmptySessionStore(), ownerKey: uploadIdentityKey });
  const apiStateRef = useRef("checking");
  const healthRequestInFlightRef = useRef(false);
  const systemsRequestInFlightRef = useRef(null);
  const systemsRequestVersionRef = useRef(0);
  const latestUploadRequestInFlightRef = useRef(null);
  const latestUploadRequestVersionRef = useRef(0);
  const workspaceIdentityRef = useRef(workspaceIdentityKey);
  const uploadIdentityRef = useRef(uploadIdentityKey);
  workspaceIdentityRef.current = workspaceIdentityKey;
  uploadIdentityRef.current = uploadIdentityKey;

  const applyLatestUploadSessionState = useCallback((nextState, ownerKey = uploadIdentityRef.current) => {
    latestUploadStateRef.current = nextState;
    latestUploadResultRef.current = nextState.latestResult;
    setLatestUploadOwnerKey(ownerKey);
    setLatestUploadSnapshot(nextState.snapshot);
    setLatestUploadResult(nextState.latestResult);
    setSessionStore(nextState.sessionStore);
  }, []);

  const clearUploadSessionState = useCallback(() => {
    latestUploadRequestVersionRef.current += 1;
    latestUploadRequestInFlightRef.current = null;
    clearLatestUploadStateCache();
    const emptyState = {
      snapshot: uploadStateView.buildEmptyLatestUploadSnapshot(),
      latestResult: null,
      sessionStore: buildEmptySessionStore(),
    };
    terminalUploadStateRef.current = null;
    applyLatestUploadSessionState(emptyState, uploadIdentityRef.current);
    lastKnownGoodTelemetryRef.current = { ...emptyState, ownerKey: uploadIdentityRef.current };
    latestStabilityRef.current = { hasData: false, dataStreak: 0, emptyStreak: 0 };
  }, [applyLatestUploadSessionState]);

  const commitCompletedUploadState = useCallback(({ latestResult = null, latestSnapshot = null } = {}) => {
    const reconciliation = reconcileLatestUploadSessionState({
      incomingPayload: {
        snapshot: latestSnapshot,
        latest_result: latestResult,
        session_state: latestSnapshot?.session_state ?? "verified",
      },
      terminalState: terminalUploadStateRef.current,
    });
    if (!reconciliation.incomingIsTerminal) return false;
    const nextState = {
      snapshot: reconciliation.snapshot,
      latestResult: reconciliation.latestResult,
      sessionStore: reconciliation.sessionStore,
    };
    terminalUploadStateRef.current = reconciliation.terminalState;
    applyLatestUploadSessionState(nextState);
    lastKnownGoodTelemetryRef.current = { ...nextState, ownerKey: uploadIdentityRef.current };
    latestStabilityRef.current = { hasData: true, dataStreak: DATA_PROMOTION_STREAK_REQUIRED, emptyStreak: 0 };
    return true;
  }, [applyLatestUploadSessionState]);

  const checkApiHealth = useCallback(async (trigger = "scheduled") => {
    if (!hasAccess) return false;
    if (healthRequestInFlightRef.current) return apiStateRef.current === "online";
    healthRequestInFlightRef.current = true;

    const checkTime = new Date();
    const attemptCount = healthCheckAttemptsRef.current + 1;
    healthCheckAttemptsRef.current = attemptCount;

    try {
      const healthPayload = await fetchApiHealth({ apiFetch, accessCode });
      const queueMetrics = healthPayload?.ready?.queue_operational_metrics
        ?? healthPayload?.ready?.details?.queue_operational_metrics
        ?? null;
      const diagnostics = healthPayload?.ready?.diagnostics ?? healthPayload?.diagnostics ?? null;
      apiStateRef.current = "online";
      setApiStatus({
        state: "online",
        label: "Analysis Service Online",
        detail: `Last sync ${formatClockTime(checkTime)} CT.`,
        checkedAt: checkTime.toISOString(),
        attemptCount,
        endpoint: formatEndpoint(API_BASE_URL),
        message: trigger === "scheduled" ? "Analysis service sync current." : "Facility sync refreshed.",
        queue: queueMetrics,
        diagnostics,
      });
      return true;
    } catch {
      apiStateRef.current = "offline";
      setApiStatus({
        state: "offline",
        label: "Analysis Service Offline",
        detail: "Analysis service unavailable. System data could not be loaded.",
        checkedAt: checkTime.toISOString(),
        attemptCount,
        endpoint: formatEndpoint(API_BASE_URL),
        message: "Analysis service unavailable. System data could not be loaded.",
        queue: null,
        diagnostics: null,
      });
      setBackendError("Analysis service unavailable. System data could not be loaded.");
      return false;
    } finally {
      healthRequestInFlightRef.current = false;
    }
  }, [accessCode, formatClockTime, formatEndpoint, hasAccess]);

  const loadFacilitySystems = useCallback(async ({ forceRefresh = false, includePersisted = allowPersistedLatest } = {}) => {
    if (!hasAccess) return false;
    const requestIdentityKey = workspaceIdentityKey;
    if (systemsRequestInFlightRef.current === requestIdentityKey) return false;
    const requestVersion = systemsRequestVersionRef.current + 1;
    systemsRequestVersionRef.current = requestVersion;
    systemsRequestInFlightRef.current = requestIdentityKey;
    if (isUploadInProgress() || isUploadJobLocked()) {
      if (systemsRequestVersionRef.current === requestVersion) systemsRequestInFlightRef.current = null;
      return false;
    }

    try {
      const payload = await fetchSystemFacility({ apiFetch, accessCode, scopeKey: datasetScopeKey, portfolioId: getCurrentWorkspaceId(), domainMode, includePersisted, forceRefresh });
      if (systemsRequestVersionRef.current !== requestVersion || workspaceIdentityRef.current !== requestIdentityKey) return false;
      const rawDomainMode = payload.domain_mode ?? null;
      setSystemsOwnerKey(requestIdentityKey);
      setDomainOwnerKey(requestIdentityKey);
      setSystems(payload.systems);
      setDomainDetection({
        mode: displayDomainMode(rawDomainMode),
        source: payload.domain_source ?? "default",
        confidence: Number(payload.domain_confidence ?? 0),
        evidence: Array.isArray(payload.domain_evidence) ? payload.domain_evidence : [],
      });
      setDomainModeState(rawDomainMode);
      setIntelligenceStatus(payload.intelligence_status ?? uploadStateView.buildEmptyIntelligenceStatus());
      setSystemsState("ready");
      setBackendError(API_CONFIG_WARNING);
      return true;
    } catch (error) {
      if (systemsRequestVersionRef.current !== requestVersion || workspaceIdentityRef.current !== requestIdentityKey) return false;
      if (error instanceof Response && (error.status === 401 || error.status === 403)) {
        const authMessage = await buildProtectedRequestMessage(error);
        setBackendError(authMessage);
        return false;
      }
      const normalizedMessage = normalizeErrorMessage(error?.message ?? error);
      setSystems([]);
      setIntelligenceStatus(uploadStateView.buildEmptyIntelligenceStatus());
      setSystemsState("fallback");
      setBackendError((current) => {
        if (normalizedMessage === "Session expired. Refresh workspace.") return normalizedMessage;
        if (apiStateRef.current === "offline") return "Analysis service unavailable. System data could not be loaded.";
        return current || API_CONFIG_WARNING;
      });
      return false;
    } finally {
      if (systemsRequestVersionRef.current === requestVersion) systemsRequestInFlightRef.current = null;
    }
  }, [accessCode, allowPersistedLatest, buildProtectedRequestMessage, datasetScopeKey, domainMode, hasAccess, workspaceIdentityKey]);

  // Contract sentinel: const loadLatestUploadState = useCallback(async ({ includePersisted } = {}) => {
  const loadLatestUploadState = useCallback(async ({ includePersisted, forceRefresh = false, returnPayload = false } = {}) => {
    const requestIdentityKey = uploadIdentityKey;
    const currentIdentityOwnsState = latestUploadOwnerKey === requestIdentityKey;
    const ownedSnapshot = currentIdentityOwnsState
      ? latestUploadStateRef.current.snapshot
      : uploadStateView.buildEmptyLatestUploadSnapshot();
    const ownedResult = currentIdentityOwnsState ? latestUploadStateRef.current.latestResult : null;
    const latestReturn = (hasRuntimeData, payload = null) => returnPayload
      ? {
        hasRuntimeData: Boolean(hasRuntimeData),
        snapshot: payload?.snapshot ?? ownedSnapshot,
        latestResult: payload?.latestResult ?? ownedResult,
      }
      : Boolean(hasRuntimeData);
    if (!hasAccess) return latestReturn(false);
    if (latestUploadRequestInFlightRef.current === requestIdentityKey) {
      return latestReturn(currentIdentityOwnsState && Boolean(latestUploadResultRef.current));
    }
    const requestVersion = latestUploadRequestVersionRef.current + 1;
    latestUploadRequestVersionRef.current = requestVersion;
    latestUploadRequestInFlightRef.current = requestIdentityKey;
    const requestedPortfolioId = getCurrentWorkspaceId();
    if (isUploadInProgress() || isUploadJobLocked()) {
      if (latestUploadRequestVersionRef.current === requestVersion) latestUploadRequestInFlightRef.current = null;
      return latestReturn(currentIdentityOwnsState && Boolean(latestUploadResultRef.current));
    }
    const shouldIncludePersisted = typeof includePersisted === "boolean" ? includePersisted : allowPersistedLatest;
    try {
      const payload = await fetchLatestUploadState({
        apiFetch,
        accessCode,
        scopeKey: datasetScopeKey,
        includePersisted: shouldIncludePersisted,
        forceRefresh,
        exactAnalysisIdentity: activeAnalysisIdentity,
      });
      if (latestUploadRequestVersionRef.current !== requestVersion || uploadIdentityRef.current !== requestIdentityKey || getCurrentWorkspaceId() !== requestedPortfolioId) {
        return latestReturn(false, {
          snapshot: uploadStateView.buildEmptyLatestUploadSnapshot(),
          latestResult: null,
        });
      }
      const boundaryMeta = payload.snapshot?._neraiumTelemetryBoundary ?? {};
      const ownedLastGood = lastKnownGoodTelemetryRef.current?.ownerKey === requestIdentityKey
        ? lastKnownGoodTelemetryRef.current
        : null;
      if (boundaryMeta.renderable === false && ownedLastGood?.snapshot) {
        console.warn("[neraium] latest telemetry rejected by workspace boundary", {
          referenceId: boundaryMeta.referenceId ?? null,
          workspaceId: boundaryMeta.workspaceId ?? "system-body",
          telemetryTimestamp: boundaryMeta.telemetryTimestamp ?? null,
          schemaVersion: boundaryMeta.schemaVersion ?? null,
          requestCorrelationId: boundaryMeta.requestCorrelationId ?? null,
          issues: boundaryMeta.issues ?? [],
        });
        return latestReturn(Boolean(ownedLastGood.sessionStore?.hasRuntimeData), {
          snapshot: ownedLastGood.snapshot,
          latestResult: ownedLastGood.latestResult,
        });
      }
      const nextHasData = Boolean(
        uploadStateView.hasFullUploadResult(payload.latestResult)
        || uploadStateView.hasActiveTelemetrySnapshot(payload.snapshot),
      );
      const stability = latestStabilityRef.current;
      if (nextHasData) {
        stability.dataStreak += 1;
        stability.emptyStreak = 0;
      } else {
        stability.emptyStreak += 1;
        stability.dataStreak = 0;
      }

      const applyAntiFlapGate = !shouldIncludePersisted;
      if (applyAntiFlapGate && !stability.hasData && nextHasData && stability.dataStreak < DATA_PROMOTION_STREAK_REQUIRED) {
        return latestReturn(currentIdentityOwnsState && Boolean(latestUploadResultRef.current));
      }
      if (applyAntiFlapGate && stability.hasData && !nextHasData && stability.emptyStreak < EMPTY_DEMOTION_STREAK_REQUIRED) {
        return latestReturn(currentIdentityOwnsState && Boolean(latestUploadResultRef.current));
      }

      stability.hasData = nextHasData;
      const reconciliation = reconcileLatestUploadSessionState({
        incomingPayload: payload,
        terminalState: terminalUploadStateRef.current,
      });
      const nextState = {
        snapshot: reconciliation.snapshot,
        latestResult: reconciliation.latestResult,
        sessionStore: reconciliation.sessionStore,
      };
      terminalUploadStateRef.current = reconciliation.terminalState;
      applyLatestUploadSessionState(nextState, requestIdentityKey);
      if (reconciliation.retainedTerminal) {
        console.info("[neraium] stale latest-upload snapshot ignored after terminal completion", {
          jobId: nextState.sessionStore.jobId,
          incomingStatus: payload?.snapshot?.status ?? payload?.snapshot?.processing_state ?? null,
        });
      }
      if (nextState.sessionStore.hasRuntimeData && nextState.snapshot?._neraiumTelemetryBoundary?.renderable !== false) {
        lastKnownGoodTelemetryRef.current = { ...nextState, ownerKey: requestIdentityKey };
      }
      return latestReturn(Boolean(nextState.sessionStore.hasRuntimeData), nextState);
    } catch (error) {
      if (latestUploadRequestVersionRef.current !== requestVersion || uploadIdentityRef.current !== requestIdentityKey) {
        return latestReturn(false, {
          snapshot: uploadStateView.buildEmptyLatestUploadSnapshot(),
          latestResult: null,
        });
      }
      if (!shouldIncludePersisted) {
        clearUploadSessionState();
        return latestReturn(false);
      }
      const lastGood = lastKnownGoodTelemetryRef.current?.ownerKey === requestIdentityKey
        ? lastKnownGoodTelemetryRef.current
        : null;
      if (!lastGood) {
        return latestReturn(false, {
          snapshot: uploadStateView.buildEmptyLatestUploadSnapshot(),
          latestResult: null,
        });
      }
      console.warn("[neraium] latest telemetry refresh failed; retaining last available state", {
        message: error?.message ?? "Latest telemetry refresh failed",
        status: error?.status ?? null,
        referenceId: lastGood?.snapshot?._neraiumTelemetryBoundary?.referenceId ?? null,
        workspaceId: lastGood?.snapshot?._neraiumTelemetryBoundary?.workspaceId ?? "system-body",
        telemetryTimestamp: lastGood?.snapshot?._neraiumTelemetryBoundary?.telemetryTimestamp ?? null,
        schemaVersion: lastGood?.snapshot?._neraiumTelemetryBoundary?.schemaVersion ?? null,
        requestCorrelationId: lastGood?.snapshot?._neraiumTelemetryBoundary?.requestCorrelationId ?? null,
      });
      return latestReturn(Boolean(lastGood.sessionStore?.hasRuntimeData), {
        snapshot: lastGood.snapshot,
        latestResult: lastGood.latestResult,
      });
    } finally {
      if (latestUploadRequestVersionRef.current === requestVersion) latestUploadRequestInFlightRef.current = null;
    }
  }, [accessCode, activeAnalysisIdentity, allowPersistedLatest, applyLatestUploadSessionState, clearUploadSessionState, datasetScopeKey, hasAccess, latestUploadOwnerKey, uploadIdentityKey]);

  useEffect(() => {
    if (!activeAnalysisIdentity?.analysisRunId) return;
    const currentResult = latestUploadStateRef.current.latestResult;
    const currentAnalysisId = String(
      currentResult?.analysis_run_id
      ?? currentResult?.run_id
      ?? currentResult?.job_id
      ?? "",
    ).trim();
    if (currentAnalysisId && currentAnalysisId === String(activeAnalysisIdentity.analysisRunId)) {
      setLatestUploadOwnerKey(uploadIdentityKey);
      return;
    }
    clearUploadSessionState();
  }, [activeAnalysisIdentity?.analysisRunId, clearUploadSessionState, uploadIdentityKey]);

  useEffect(() => {
    latestUploadResultRef.current = latestUploadResult;
  }, [latestUploadResult]);

  useEffect(() => {
    systemsRequestVersionRef.current += 1;
    systemsRequestInFlightRef.current = null;
    setSystemsOwnerKey(workspaceIdentityKey);
    setSystems([]);
    setSystemsState("loading");
    setIntelligenceStatus(uploadStateView.buildEmptyIntelligenceStatus());
    setDomainOwnerKey(workspaceIdentityKey);
    setDomainDetection({ mode: null, source: "default", confidence: 0, evidence: [] });
    setDomainModeState(null);
    setDomainModeResolved(false);
    clearUploadSessionState();
  }, [clearUploadSessionState, workspaceIdentityKey]);

  const retryBackendConnection = useCallback(async () => {
    const isHealthy = await checkApiHealth("retry");
    if (isHealthy) {
      await loadLatestUploadState({ includePersisted: allowPersistedLatest });
      await loadFacilitySystems({ includePersisted: allowPersistedLatest });
    }
  }, [allowPersistedLatest, checkApiHealth, loadFacilitySystems, loadLatestUploadState]);

  const updateAllowPersistedLatest = useCallback((value) => {
    setAllowPersistedLatest((current) => {
      const next = typeof value === "function" ? value(current) : value;
      return Boolean(next);
    });
  }, []);

  useEffect(() => {
    if (!hasAccess) return;
    checkApiHealth("startup");
  }, [checkApiHealth, hasAccess]);

  useEffect(() => {
    if (!hasAccess) {
      setDomainModeResolved(false);
      return undefined;
    }
    let cancelled = false;
    const requestIdentityKey = workspaceIdentityKey;
    fetchDomainMode({ apiFetch, accessCode })
      .then((payload) => {
        if (cancelled || workspaceIdentityRef.current !== requestIdentityKey) return;
        const rawDomainMode = payload.mode ?? null;
        setDomainOwnerKey(requestIdentityKey);
        setDomainDetection({
          mode: displayDomainMode(rawDomainMode),
          source: payload.source ?? "default",
          confidence: Number(payload.confidence ?? 0),
          evidence: Array.isArray(payload.evidence) ? payload.evidence : [],
        });
        setDomainModeState(payload.source === "upload_shape" ? rawDomainMode : null);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled && workspaceIdentityRef.current === requestIdentityKey) setDomainModeResolved(true);
      });
    return () => {
      cancelled = true;
    };
  }, [accessCode, hasAccess, workspaceIdentityKey]);

  useEffect(() => {
    if (!hasAccess || !domainModeResolved) return;
    if (isUploadInProgress() || isUploadJobLocked()) return;
    loadLatestUploadState({ includePersisted: allowPersistedLatest });
    loadFacilitySystems({ includePersisted: allowPersistedLatest });
  }, [allowPersistedLatest, domainMode, domainModeResolved, hasAccess, loadFacilitySystems, loadLatestUploadState]);

  useEffect(() => {
    if (!hasAccess) return;
    fetchEngineIdentity({ apiFetch, accessCode }).catch(() => {});
  }, [accessCode, hasAccess]);

  useStableInterval(() => {
    void checkApiHealth("interval");
    if (isUploadInProgress() || isUploadJobLocked()) return;
    void Promise.all([
      loadLatestUploadState({ includePersisted: allowPersistedLatest }),
      loadFacilitySystems({ includePersisted: allowPersistedLatest }),
    ]);
  }, LIVE_REFRESH_INTERVAL_MS, hasAccess);

  return {
    apiStatus,
    systems: systemsOwnerKey === workspaceIdentityKey ? systems : [],
    systemsState: systemsOwnerKey === workspaceIdentityKey ? systemsState : "loading",
    intelligenceStatus: systemsOwnerKey === workspaceIdentityKey ? intelligenceStatus : uploadStateView.buildEmptyIntelligenceStatus(),
    backendError,
    latestUploadResult: latestUploadOwnerKey === uploadIdentityKey ? latestUploadResult : null,
    latestUploadSnapshot: latestUploadOwnerKey === uploadIdentityKey ? latestUploadSnapshot : uploadStateView.buildEmptyLatestUploadSnapshot(),
    sessionStore: latestUploadOwnerKey === uploadIdentityKey ? sessionStore : buildEmptySessionStore(),
    domainDetection: domainOwnerKey === workspaceIdentityKey ? domainDetection : { mode: null, source: "default", confidence: 0, evidence: [] },
    demoScenario,
    setDemoScenario,
    isDemoMode,
    setIsDemoMode,
    domainMode,
    loadFacilitySystems,
    loadLatestUploadState,
    allowPersistedLatest,
    setAllowPersistedLatest: updateAllowPersistedLatest,
    commitCompletedUploadState,
    clearUploadSessionState,
    retryBackendConnection,
  };
}
