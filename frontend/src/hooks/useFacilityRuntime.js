import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL, API_CONFIG_WARNING, apiFetch } from "../config";
import useStableInterval from "./useStableInterval";
import { fetchApiHealth } from "../services/api/healthApi";
import {
  fetchDomainMode,
  fetchEngineIdentity,
  fetchFacilitySystems as fetchSystemFacility,
} from "../services/api/systemApi";
import { fetchLatestUploadState } from "../services/api/uploadApi";
import * as uploadStateView from "../viewModels/uploadState";
import { buildEmptySessionStore, buildSessionStore } from "../viewModels/sessionState";
import { normalizeErrorMessage } from "../viewModels/uploadFlow";

const OPERATIONAL_CADENCE_MS = 45000;
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
  initialAllowPersistedLatest = true,
}) {
  const isUploadInProgress = () => (typeof window !== "undefined" && window.__NERAIUM_UPLOAD_IN_PROGRESS__ === true);
  const isUploadJobLocked = () => false;
  const [telemetryTick, setTelemetryTick] = useState(0);
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
  const [domainDetection, setDomainDetection] = useState({ mode: null, source: "default", confidence: 0, evidence: [] });
  const healthCheckAttemptsRef = useRef(0);
  const latestStabilityRef = useRef({ hasData: false, dataStreak: 0, emptyStreak: 0 });
  const latestUploadResultRef = useRef(null);
  const lastKnownGoodTelemetryRef = useRef({ latestResult: null, snapshot: uploadStateView.buildEmptyLatestUploadSnapshot(), sessionStore: buildEmptySessionStore() });
  const apiStateRef = useRef("checking");
  const healthRequestInFlightRef = useRef(false);
  const systemsRequestInFlightRef = useRef(false);
  const latestUploadRequestInFlightRef = useRef(false);

  const clearUploadSessionState = useCallback(() => {
    setLatestUploadResult(null);
    setLatestUploadSnapshot(uploadStateView.buildEmptyLatestUploadSnapshot());
    setSessionStore(buildEmptySessionStore());
    latestUploadResultRef.current = null;
    lastKnownGoodTelemetryRef.current = { latestResult: null, snapshot: uploadStateView.buildEmptyLatestUploadSnapshot(), sessionStore: buildEmptySessionStore() };
    latestStabilityRef.current = { hasData: false, dataStreak: 0, emptyStreak: 0 };
  }, []);

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

  const loadFacilitySystems = useCallback(async ({ forceRefresh = false } = {}) => {
    if (!hasAccess) return false;
    if (systemsRequestInFlightRef.current) return false;
    systemsRequestInFlightRef.current = true;
    if (isUploadInProgress() || isUploadJobLocked()) {
      systemsRequestInFlightRef.current = false;
      return false;
    }

    try {
      const payload = await fetchSystemFacility({ apiFetch, accessCode, domainMode, forceRefresh });
      const rawDomainMode = payload.domain_mode ?? null;
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
      systemsRequestInFlightRef.current = false;
    }
  }, [accessCode, buildProtectedRequestMessage, domainMode, hasAccess]);

  // Contract sentinel: const loadLatestUploadState = useCallback(async ({ includePersisted } = {}) => {
  const loadLatestUploadState = useCallback(async ({ includePersisted, forceRefresh = false, returnPayload = false } = {}) => {
    const latestReturn = (hasRuntimeData, payload = null) => returnPayload
      ? {
        hasRuntimeData: Boolean(hasRuntimeData),
        snapshot: payload?.snapshot ?? latestUploadSnapshot,
        latestResult: payload?.latestResult ?? latestUploadResultRef.current,
      }
      : Boolean(hasRuntimeData);
    if (!hasAccess) return latestReturn(false);
    if (latestUploadRequestInFlightRef.current) return latestReturn(Boolean(latestUploadResultRef.current));
    latestUploadRequestInFlightRef.current = true;
    if (isUploadInProgress() || isUploadJobLocked()) {
      latestUploadRequestInFlightRef.current = false;
      return latestReturn(Boolean(latestUploadResultRef.current));
    }
    const shouldIncludePersisted = typeof includePersisted === "boolean" ? includePersisted : allowPersistedLatest;
    try {
      const payload = await fetchLatestUploadState({ apiFetch, accessCode, includePersisted: shouldIncludePersisted, forceRefresh });
      const boundaryMeta = payload.snapshot?._neraiumTelemetryBoundary ?? {};
      if (boundaryMeta.renderable === false && lastKnownGoodTelemetryRef.current?.snapshot) {
        console.warn("[neraium] latest telemetry rejected by workspace boundary", {
          referenceId: boundaryMeta.referenceId ?? null,
          workspaceId: boundaryMeta.workspaceId ?? "system-body",
          telemetryTimestamp: boundaryMeta.telemetryTimestamp ?? null,
          schemaVersion: boundaryMeta.schemaVersion ?? null,
          requestCorrelationId: boundaryMeta.requestCorrelationId ?? null,
          issues: boundaryMeta.issues ?? [],
        });
        return latestReturn(Boolean(lastKnownGoodTelemetryRef.current.sessionStore?.hasRuntimeData), {
          snapshot: lastKnownGoodTelemetryRef.current.snapshot,
          latestResult: lastKnownGoodTelemetryRef.current.latestResult,
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
        return latestReturn(Boolean(latestUploadResultRef.current));
      }
      if (applyAntiFlapGate && stability.hasData && !nextHasData && stability.emptyStreak < EMPTY_DEMOTION_STREAK_REQUIRED) {
        return latestReturn(Boolean(latestUploadResultRef.current));
      }

      stability.hasData = nextHasData;
      const nextSessionStore = buildSessionStore(payload, { loaded: true });
      setLatestUploadSnapshot(payload.snapshot);
      setLatestUploadResult(payload.latestResult);
      setSessionStore(nextSessionStore);
      latestUploadResultRef.current = payload.latestResult;
      if (nextHasData && payload.snapshot?._neraiumTelemetryBoundary?.renderable !== false) {
        lastKnownGoodTelemetryRef.current = { latestResult: payload.latestResult, snapshot: payload.snapshot, sessionStore: nextSessionStore };
      }
      return latestReturn(Boolean(nextSessionStore.hasRuntimeData), payload);
    } catch (error) {
      if (!shouldIncludePersisted) {
        clearUploadSessionState();
        return latestReturn(false);
      }
      const lastGood = lastKnownGoodTelemetryRef.current;
      console.warn("[neraium] latest telemetry refresh failed; retaining last available state", {
        message: error?.message ?? "Latest telemetry refresh failed",
        status: error?.status ?? null,
        referenceId: lastGood?.snapshot?._neraiumTelemetryBoundary?.referenceId ?? null,
        workspaceId: lastGood?.snapshot?._neraiumTelemetryBoundary?.workspaceId ?? "system-body",
        telemetryTimestamp: lastGood?.snapshot?._neraiumTelemetryBoundary?.telemetryTimestamp ?? null,
        schemaVersion: lastGood?.snapshot?._neraiumTelemetryBoundary?.schemaVersion ?? null,
        requestCorrelationId: lastGood?.snapshot?._neraiumTelemetryBoundary?.requestCorrelationId ?? null,
      });
      return latestReturn(Boolean(lastGood?.sessionStore?.hasRuntimeData ?? latestUploadResultRef.current), {
        snapshot: lastGood?.snapshot ?? latestUploadSnapshot,
        latestResult: lastGood?.latestResult ?? latestUploadResultRef.current,
      });
    } finally {
      latestUploadRequestInFlightRef.current = false;
    }
  }, [accessCode, allowPersistedLatest, clearUploadSessionState, hasAccess, latestUploadSnapshot]);

  useEffect(() => {
    latestUploadResultRef.current = latestUploadResult;
  }, [latestUploadResult]);

  const retryBackendConnection = useCallback(async () => {
    const isHealthy = await checkApiHealth("retry");
    if (isHealthy) {
      await loadLatestUploadState({ includePersisted: true });
      await loadFacilitySystems();
    }
  }, [checkApiHealth, loadFacilitySystems, loadLatestUploadState]);

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
    if (!hasAccess) return;
    fetchDomainMode({ apiFetch, accessCode })
      .then((payload) => {
        const rawDomainMode = payload.mode ?? null;
        setDomainDetection({
          mode: displayDomainMode(rawDomainMode),
          source: payload.source ?? "default",
          confidence: Number(payload.confidence ?? 0),
          evidence: Array.isArray(payload.evidence) ? payload.evidence : [],
        });
        setDomainModeState(payload.source === "upload_shape" ? rawDomainMode : null);
      })
      .catch(() => {});
  }, [accessCode, hasAccess]);

  useEffect(() => {
    if (!hasAccess) return;
    if (isUploadInProgress() || isUploadJobLocked()) return;
    loadLatestUploadState({ includePersisted: true });
    loadFacilitySystems();
  }, [domainMode, hasAccess, loadFacilitySystems, loadLatestUploadState]);

  useEffect(() => {
    if (!hasAccess) return;
    fetchEngineIdentity({ apiFetch, accessCode }).catch(() => {});
  }, [accessCode, hasAccess]);

  useStableInterval(() => {
    checkApiHealth("interval");
  }, 45000, hasAccess);

  useStableInterval(() => {
    setTelemetryTick((current) => current + 1);
  }, OPERATIONAL_CADENCE_MS, hasAccess);

  useStableInterval(() => {
    if (isUploadInProgress() || isUploadJobLocked()) return;
    loadLatestUploadState({ includePersisted: true });
    loadFacilitySystems();
  }, LIVE_REFRESH_INTERVAL_MS, hasAccess);

  return {
    telemetryTick,
    apiStatus,
    systems,
    systemsState,
    intelligenceStatus,
    backendError,
    latestUploadResult,
    latestUploadSnapshot,
    sessionStore,
    domainDetection,
    demoScenario,
    setDemoScenario,
    isDemoMode,
    setIsDemoMode,
    domainMode,
    loadFacilitySystems,
    loadLatestUploadState,
    allowPersistedLatest,
    setAllowPersistedLatest: updateAllowPersistedLatest,
    clearUploadSessionState,
    retryBackendConnection,
  };
}
