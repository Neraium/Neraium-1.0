import { useCallback, useEffect, useMemo, useState } from "react";
import * as uploadStateView from "../viewModels/uploadState";
import { deriveCurrentSession, deriveSessionActivity } from "../viewModels/currentSession";
import { deriveCanonicalFinding } from "../viewModels/operatorFinding";
import { normalizeUploadStatus, uploadStateMessage } from "../viewModels/uploadFlow";
import { isUploadProcessingStatus, uploadStageLabel, uploadStagePercent } from "../viewModels/uploadContract";
import { clearLatestUploadStateCache, resetDemoSession } from "../services/api/uploadApi";

const SESSION_INTENT_STORAGE_KEY = "neraium.session_intent";
const ALLOW_PERSISTED_LATEST_STORAGE_KEY = "neraium.allow_persisted_latest";

function readStoredSessionIntent() {
  if (typeof window === "undefined") return "neutral";
  const allowPersisted = window.localStorage.getItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY);
  if (allowPersisted !== "1") return "neutral";
  const value = window.localStorage.getItem(SESSION_INTENT_STORAGE_KEY);
  return value === "current" || value === "resumed" ? value : "neutral";
}

export function readStoredAllowPersistedLatest() {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY) === "1";
}

export default function useWorkspaceSessionController({
  activeWorkspace,
  setActiveWorkspace,
  apiFetch,
  accessCode,
  sessionStore,
  loadFacilitySystems,
  loadLatestUploadState,
  allowPersistedLatest,
  setAllowPersistedLatest,
  clearUploadSessionState,
  setIsDemoMode,
}) {
  const [sessionIntent, setSessionIntent] = useState(() => readStoredSessionIntent());
  const [historianReplayState, setHistorianReplayState] = useState({ enabled: false, frame: null, meta: null });
  const [resetGuardActive, setResetGuardActive] = useState(false);
  const [completedUploadOverride, setCompletedUploadOverride] = useState(null);
  const [postUploadPendingSnapshot, setPostUploadPendingSnapshot] = useState(null);
  const [postUploadExpectedJobId, setPostUploadExpectedJobId] = useState(null);
  const [gateUploadCompleteSeen, setGateUploadCompleteSeen] = useState(false);
  const [errorBoundaryResetKey, setErrorBoundaryResetKey] = useState(0);
  const [workspaceStatusMessage, setWorkspaceStatusMessage] = useState("");
  const [workspaceResetRevision, setWorkspaceResetRevision] = useState(0);

  const canonicalLatestUploadJobId = sessionStore?.jobId ?? null;
  const pendingUploadJobId = uploadStateView.resolveCurrentUploadJobId(postUploadPendingSnapshot);
  const guardedLatestUploadResult = resetGuardActive ? null : (completedUploadOverride ?? sessionStore?.latestUploadResult ?? null);
  const guardedLatestUploadSnapshot = resetGuardActive
    ? uploadStateView.buildEmptyLatestUploadSnapshot()
    : (postUploadPendingSnapshot ?? sessionStore?.latestUploadSnapshot ?? uploadStateView.buildEmptyLatestUploadSnapshot());

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
  const sessionActivity = useMemo(
    () => deriveSessionActivity({
      telemetrySession,
      sessionIntent,
      gateUploadCompleteSeen,
      hasCompletedUploadOverride: Boolean(completedUploadOverride),
      resetGuardActive,
    }),
    [completedUploadOverride, gateUploadCompleteSeen, resetGuardActive, sessionIntent, telemetrySession],
  );
  const effectiveSessionIntent = sessionActivity.effectiveIntent;

  useEffect(() => {
    if (!postUploadExpectedJobId) return;
    if (!canonicalLatestUploadJobId || String(canonicalLatestUploadJobId) !== String(postUploadExpectedJobId)) return;
    console.info("[neraium] current upload refetch result", {
      expectedJobId: postUploadExpectedJobId,
      canonicalJobId: canonicalLatestUploadJobId,
    });
    setPostUploadPendingSnapshot(null);
    setPostUploadExpectedJobId(null);
  }, [canonicalLatestUploadJobId, postUploadExpectedJobId]);

  useEffect(() => {
    if (!completedUploadOverride) return;
    const overrideJobId = String(completedUploadOverride?.job_id ?? "").trim();
    if (!overrideJobId) return;
    const sessionResult = sessionStore?.latestUploadResult ?? null;
    if (!sessionResult || !uploadStateView.hasFullUploadResult(sessionResult)) return;
    if (String(sessionResult?.job_id ?? "").trim() !== overrideJobId) return;
    setCompletedUploadOverride(null);
  }, [completedUploadOverride, sessionStore]);

  const hasCurrentUploadResult = sessionActivity.hasCurrentUploadResult;
  const hasResumedSession = sessionActivity.hasResumedSession;
  const hasActiveSession = sessionActivity.hasActiveSession;
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
    telemetrySession,
    sessionIntent: effectiveSessionIntent,
  }), [effectiveLatestUploadResult, effectiveLatestUploadSnapshot, effectiveSessionIntent, hasActiveSession, hasCurrentUploadResult, hasResumedSession, hasRealSiiOutput, telemetrySession]);
  const canonicalFinding = useMemo(
    () => deriveCanonicalFinding({ currentSession, latestReplayFrame: historianReplayState.frame }),
    [currentSession, historianReplayState.frame],
  );
  const gateProcessing = useMemo(() => deriveGateProcessing(effectiveLatestUploadSnapshot), [effectiveLatestUploadSnapshot]);

  const handleReplayFrameChange = useCallback((frame, meta) => {
    setHistorianReplayState((current) => ({ ...current, frame, meta }));
  }, []);

  const handleReplayModeChange = useCallback((enabled) => {
    setHistorianReplayState((current) => ({ ...current, enabled }));
  }, []);

  const handleGateUploadComplete = useCallback(async (completedPayload = null, options = {}) => {
    setWorkspaceStatusMessage("");
    setResetGuardActive(false);
    setIsDemoMode(false);
    setAllowPersistedLatest(true);
    setGateUploadCompleteSeen(true);
    const completedResult = uploadStateView.resolveCurrentUploadResult(completedPayload)
      ?? (uploadStateView.hasFullUploadResult(completedPayload) ? completedPayload : null);
    const expectedJobId = uploadStateView.resolveCurrentUploadJobId(completedPayload)
      ?? (String(completedResult?.job_id ?? "").trim() || null);
    if (completedResult) {
      setCompletedUploadOverride(completedResult);
    } else {
      setCompletedUploadOverride(null);
    }
    if (expectedJobId) {
      setPostUploadExpectedJobId(expectedJobId);
      setPostUploadPendingSnapshot(buildPendingUploadSnapshot({ completedPayload, completedResult, expectedJobId }));
    } else {
      setPostUploadExpectedJobId(null);
      setPostUploadPendingSnapshot(null);
    }
    console.info("[neraium] upload success response", {
      jobId: expectedJobId,
      status: normalizeUploadStatus(completedPayload?.status ?? completedPayload?.processing_state ?? completedPayload?.worker_state),
    });
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, "1");
    }
    await loadLatestUploadState({ includePersisted: true, forceRefresh: true });
    console.info("[neraium] current upload refetch requested", {
      expectedJobId,
      canonicalJobId: canonicalLatestUploadJobId,
      pendingJobId: pendingUploadJobId,
    });
    setSessionIntent("current");
    await loadFacilitySystems({ forceRefresh: true });
    if (options.navigateToGate !== false) {
      console.info("[neraium] route transition target", { target: "system-body", jobId: expectedJobId });
      setActiveWorkspace("system-body");
    }
  }, [canonicalLatestUploadJobId, loadFacilitySystems, loadLatestUploadState, pendingUploadJobId, setActiveWorkspace, setAllowPersistedLatest, setIsDemoMode]);

  const handleResumePreviousSession = useCallback(async () => {
    setWorkspaceStatusMessage("");
    setResetGuardActive(false);
    setAllowPersistedLatest(true);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, "1");
    }
    const hasResult = await loadLatestUploadState({ includePersisted: true, forceRefresh: true });
    if (!hasResult) {
      setCompletedUploadOverride(null);
      setPostUploadPendingSnapshot(null);
      setPostUploadExpectedJobId(null);
      setGateUploadCompleteSeen(false);
    }
    setSessionIntent(hasResult ? "resumed" : "neutral");
    await loadFacilitySystems();
    setActiveWorkspace("system-body");
  }, [loadFacilitySystems, loadLatestUploadState, setActiveWorkspace, setAllowPersistedLatest]);

  const handleResetWorkspace = useCallback(async () => {
    const hasActiveUploadOrProcessing = sessionStore?.isProcessing === true
      || (typeof window !== "undefined" && window.__NERAIUM_UPLOAD_IN_PROGRESS__ === true);
    if (hasActiveUploadOrProcessing && typeof window !== "undefined") {
      const confirmed = window.confirm("An upload or processing job is active. Reset the workspace anyway?");
      if (!confirmed) return false;
    }

    const [uploadResetPayload, connectionResetResponse] = await Promise.all([
      resetDemoSession({ apiFetch, accessCode }),
      apiFetch("/api/data-connections/reset-all", {
        method: "POST",
        accessCode,
      }),
    ]);

    const connectionResetPayload = await connectionResetResponse.json().catch(() => ({}));

    if (!connectionResetResponse.ok) {
      const detail = uploadResetPayload?.message
        || connectionResetPayload?.message
        || connectionResetPayload?.detail
        || "Workspace reset failed.";
      throw new Error(String(detail));
    }

    setResetGuardActive(true);
    setSessionIntent("neutral");
    setIsDemoMode(false);
    setAllowPersistedLatest(false);
    clearUploadSessionState();
    setCompletedUploadOverride(null);
    setPostUploadPendingSnapshot(null);
    setPostUploadExpectedJobId(null);
    setGateUploadCompleteSeen(false);
    setWorkspaceStatusMessage("Workspace reset.");
    setWorkspaceResetRevision((current) => current + 1);
    clearLatestUploadStateCache();
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("neraium.last_upload_job_id");
      window.localStorage.removeItem(SESSION_INTENT_STORAGE_KEY);
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, "0");
    }
    setHistorianReplayState({ enabled: false, frame: null, meta: null });
    await loadLatestUploadState({ includePersisted: false });
    await loadFacilitySystems();
    return true;
  }, [accessCode, apiFetch, clearUploadSessionState, loadFacilitySystems, loadLatestUploadState, sessionStore?.isProcessing, setAllowPersistedLatest, setIsDemoMode]);

  const handleBackToGate = useCallback(async () => {
    setWorkspaceStatusMessage("");
    setGateUploadCompleteSeen(true);
    setSessionIntent("current");
    const hasResult = await loadLatestUploadState({ includePersisted: true, forceRefresh: true });
    if (!hasResult) {
      setCompletedUploadOverride(null);
      setPostUploadPendingSnapshot(null);
      setPostUploadExpectedJobId(null);
    }
    await loadFacilitySystems();
    setActiveWorkspace("system-body");
  }, [loadFacilitySystems, loadLatestUploadState, setActiveWorkspace]);

  const handleRetryWorkspace = useCallback(() => {
    console.info("[neraium] route retry requested", { workspace: activeWorkspace });
    setWorkspaceStatusMessage("");
    setErrorBoundaryResetKey((current) => current + 1);
    if (activeWorkspace === "system-body") {
      void loadLatestUploadState({ includePersisted: false, forceRefresh: true });
      void loadFacilitySystems({ forceRefresh: true });
    }
  }, [activeWorkspace, loadFacilitySystems, loadLatestUploadState]);

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

  return {
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
    workspaceStatusMessage,
    workspaceResetRevision,
    handleReplayFrameChange,
    handleReplayModeChange,
    handleGateUploadComplete,
    handleResumePreviousSession,
    handleResetWorkspace,
    handleBackToGate,
    handleRetryWorkspace,
  };
}

function buildPendingUploadSnapshot({ completedPayload = null, completedResult = null, expectedJobId = null } = {}) {
  if (!expectedJobId) return null;
  return {
    ...uploadStateView.buildEmptyLatestUploadSnapshot(),
    ...(completedPayload ?? {}),
    status: normalizeUploadStatus(completedPayload?.status ?? completedPayload?.processing_state ?? completedPayload?.worker_state) || "structural_scoring",
    processing_state: "structural_scoring",
    progress_label: completedPayload?.progress_label ?? completedPayload?.message ?? "Telemetry active. Analysis pending.",
    message: completedPayload?.message ?? completedPayload?.progress_label ?? "Telemetry active. Analysis pending.",
    percent: Number(completedPayload?.percent ?? completedPayload?.progress) || 86,
    current_upload: {
      ...(completedPayload?.current_upload ?? {}),
      job_id: expectedJobId,
      result: completedResult ?? null,
    },
    latest_result: completedResult ?? null,
    state_available: true,
    last_filename: completedResult?.filename ?? completedPayload?.filename ?? null,
  };
}

function deriveGateProcessing(snapshot) {
  const rawStatus = String(snapshot?.contract_stage ?? snapshot?.status ?? snapshot?.processing_state ?? "");
  const status = normalizeUploadStatus(rawStatus);
  const percent = Number(snapshot?.contract_progress ?? snapshot?.percent ?? snapshot?.progress);
  return {
    active: isUploadProcessingStatus(status),
    percent: Number.isFinite(percent) ? Math.max(1, Math.min(99, Math.round(percent))) : (uploadStagePercent(status) ?? 0),
    label: String(snapshot?.contract_label ?? snapshot?.progress_label ?? snapshot?.message ?? uploadStageLabel(status) ?? uploadStateMessage(status)),
  };
}
