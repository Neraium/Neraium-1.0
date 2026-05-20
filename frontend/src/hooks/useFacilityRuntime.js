import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL, API_CONFIG_WARNING, apiFetch } from "../config";
import useStableInterval from "./useStableInterval";
import { fetchApiHealth } from "../services/api/healthApi";
import {
  fetchDomainMode,
  fetchEngineIdentity,
  fetchFacilitySystems as fetchSystemFacility,
  updateDomainMode as saveDomainMode,
} from "../services/api/systemApi";
import { fetchLatestUploadState } from "../services/api/uploadApi";
import * as uploadStateView from "../viewModels/uploadState";
import { normalizeErrorMessage } from "../viewModels/uploadFlow";
import { FALLBACK_SYSTEMS } from "../config/workspaces";

const OPERATIONAL_CADENCE_MS = 30000;
const LIVE_REFRESH_INTERVAL_MS = 5000;

export default function useFacilityRuntime({
  hasAccess,
  accessCode,
  formatClockTime,
  formatEndpoint,
  buildProtectedRequestMessage,
}) {
  const [telemetryTick, setTelemetryTick] = useState(0);
  const [apiStatus, setApiStatus] = useState({
    state: "checking",
    label: "Sync pending",
    detail: "Establishing facility sync.",
    checkedAt: null,
    attemptCount: 0,
    endpoint: formatEndpoint(API_BASE_URL),
    message: "",
  });
  const [systems, setSystems] = useState(FALLBACK_SYSTEMS);
  const [systemsState, setSystemsState] = useState("loading");
  const [intelligenceStatus, setIntelligenceStatus] = useState(uploadStateView.buildEmptyIntelligenceStatus());
  const [backendError, setBackendError] = useState(API_CONFIG_WARNING);
  const [latestUploadResult, setLatestUploadResult] = useState(null);
  const [latestUploadSnapshot, setLatestUploadSnapshot] = useState(uploadStateView.buildEmptyLatestUploadSnapshot());
  const [allowPersistedLatest, setAllowPersistedLatest] = useState(true);
  const [demoScenario, setDemoScenario] = useState("drift");
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [domainMode, setDomainModeState] = useState("aquatic");
  const healthCheckAttemptsRef = useRef(0);

  const checkApiHealth = useCallback(async (trigger = "scheduled") => {
    if (!hasAccess) {
      return false;
    }

    const checkTime = new Date();
    const attemptCount = healthCheckAttemptsRef.current + 1;
    healthCheckAttemptsRef.current = attemptCount;

    try {
      await fetchApiHealth({ apiFetch, accessCode });
      setApiStatus({
        state: "online",
        label: "API Connected",
        detail: `Last sync ${formatClockTime(checkTime)} CT.`,
        checkedAt: checkTime.toISOString(),
        attemptCount,
        endpoint: formatEndpoint(API_BASE_URL),
        message: trigger === "scheduled" ? "Backend sync current." : "Facility sync refreshed.",
      });
      return true;
    } catch {
      setApiStatus({
        state: "offline",
        label: "API Offline",
        detail: "Backend connection unavailable. System data could not be loaded.",
        checkedAt: checkTime.toISOString(),
        attemptCount,
        endpoint: formatEndpoint(API_BASE_URL),
        message: "Backend connection unavailable. System data could not be loaded.",
      });
      setBackendError("Backend connection unavailable. System data could not be loaded.");
      return false;
    }
  }, [accessCode, formatClockTime, formatEndpoint, hasAccess]);

  const loadFacilitySystems = useCallback(async () => {
    if (!hasAccess) {
      return false;
    }

    try {
      const payload = await fetchSystemFacility({ apiFetch, accessCode, domainMode });
      setSystems(payload.systems);
      setDomainModeState(payload.domain_mode ?? domainMode);
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
      setSystems(FALLBACK_SYSTEMS);
      setIntelligenceStatus(uploadStateView.buildEmptyIntelligenceStatus());
      setSystemsState("fallback");
      setBackendError((current) => {
        if (normalizedMessage === "Session expired. Refresh workspace.") {
          return normalizedMessage;
        }
        if (apiStatus.state === "offline") {
          return "Backend connection unavailable. System data could not be loaded.";
        }
        return current || API_CONFIG_WARNING;
      });
      return false;
    }
  }, [accessCode, apiStatus.state, buildProtectedRequestMessage, domainMode, hasAccess]);

  const loadLatestUploadState = useCallback(async ({ includePersisted } = {}) => {
    if (!hasAccess) {
      return false;
    }
    const shouldIncludePersisted = typeof includePersisted === "boolean" ? includePersisted : allowPersistedLatest;
    try {
      const payload = await fetchLatestUploadState({ apiFetch, accessCode, includePersisted: shouldIncludePersisted });
      setLatestUploadSnapshot(payload.snapshot);
      setLatestUploadResult(payload.latestResult);
      return Boolean(payload.latestResult);
    } catch {
      // Preserve the most recent known upload session on transient failures so refreshes do not clear state.
      return Boolean(latestUploadResult);
    }
  }, [accessCode, allowPersistedLatest, hasAccess, latestUploadResult]);

  const retryBackendConnection = useCallback(async () => {
    const isHealthy = await checkApiHealth("retry");
    if (isHealthy) {
      await loadFacilitySystems();
    }
  }, [checkApiHealth, loadFacilitySystems]);

  useEffect(() => {
    if (!hasAccess) return;
    checkApiHealth("startup");
  }, [checkApiHealth, hasAccess]);

  useEffect(() => {
    if (!hasAccess) return;
    fetchDomainMode({ apiFetch, accessCode })
      .then((payload) => setDomainModeState(payload.mode || "aquatic"))
      .catch(() => {});
  }, [accessCode, hasAccess]);

  useEffect(() => {
    if (!hasAccess) return;
    loadFacilitySystems();
    loadLatestUploadState();
  }, [domainMode, hasAccess, loadFacilitySystems, loadLatestUploadState]);

  useEffect(() => {
    if (!hasAccess) return;
    fetchEngineIdentity({ apiFetch, accessCode }).catch(() => {});
  }, [accessCode, hasAccess]);

  useStableInterval(() => {
    checkApiHealth("interval");
  }, 20000, hasAccess);

  useStableInterval(() => {
    setTelemetryTick((current) => current + 1);
  }, OPERATIONAL_CADENCE_MS, hasAccess);

  useStableInterval(() => {
    loadLatestUploadState();
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
    demoScenario,
    setDemoScenario,
    isDemoMode,
    setIsDemoMode,
    domainMode,
    setDomainMode: async (mode) => {
      const payload = await saveDomainMode({ apiFetch, accessCode, mode });
      setDomainModeState(payload.mode || "aquatic");
      await loadFacilitySystems();
      return payload.mode || "aquatic";
    },
    loadFacilitySystems,
    loadLatestUploadState,
    allowPersistedLatest,
    setAllowPersistedLatest,
    retryBackendConnection,
  };
}
