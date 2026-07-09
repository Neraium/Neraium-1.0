import { useCallback, useEffect, useMemo, useState } from "react";
import * as uploadStateView from "../viewModels/uploadState";
import { deriveCurrentSession, deriveSessionActivity } from "../viewModels/currentSession";
import { deriveCanonicalFinding } from "../viewModels/operatorFinding";
import { normalizeUploadStatus, uploadStateMessage } from "../viewModels/uploadFlow";
import { isUploadProcessingStatus, uploadStageLabel, uploadStagePercent } from "../viewModels/uploadContract";
import {
  createAnalysisRecord,
  deleteAnalysisRecord,
  isCompletedAnalysisPayload,
  readAnalysisHistory,
  upsertCompletedAnalysis,
  writeAnalysisHistory,
} from "../viewModels/analysisHistory";

const SESSION_INTENT_STORAGE_KEY = "neraium.session_intent";
const ALLOW_PERSISTED_LATEST_STORAGE_KEY = "neraium.allow_persisted_latest";

function readStoredSessionIntent() {
  if (typeof window === "undefined") return "neutral";
  const allowPersisted = window.localStorage.getItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY);
  if (allowPersisted === "0") return "neutral";
  const value = window.sessionStorage.getItem(SESSION_INTENT_STORAGE_KEY);
  return value === "current" || value === "resumed" ? value : "neutral";
}

export function readStoredAllowPersistedLatest() {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY) !== "0";
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
  const [analysisHistory, setAnalysisHistory] = useState(() => readAnalysisHistory());
  const [restoredAnalysisOverride, setRestoredAnalysisOverride] = useState(null);

  const canonicalLatestUploadJobId = sessionStore?.jobId ?? null;
  const pendingUploadJobId = uploadStateView.resolveCurrentUploadJobId(postUploadPendingSnapshot);
  const localLatestCompletedAnalysis = allowPersistedLatest ? (analysisHistory[0] ?? null) : null;
  const restoredAnalysisResult = restoredAnalysisOverride?.result ?? null;
  const restoredAnalysisSnapshot = restoredAnalysisOverride?.snapshot ?? null;
  const localLatestResult = localLatestCompletedAnalysis?.result ?? null;
  const localLatestSnapshot = localLatestCompletedAnalysis?.snapshot ?? null;
  const guardedLatestUploadResult = resetGuardActive
    ? null
    : (completedUploadOverride ?? restoredAnalysisResult ?? sessionStore?.latestUploadResult ?? localLatestResult ?? null);
  const guardedLatestUploadSnapshot = resetGuardActive
    ? uploadStateView.buildEmptyLatestUploadSnapshot()
    : (postUploadPendingSnapshot ?? restoredAnalysisSnapshot ?? sessionStore?.latestUploadSnapshot ?? localLatestSnapshot ?? uploadStateView.buildEmptyLatestUploadSnapshot());

  const observableTelemetrySession = useMemo(
    () => uploadStateView.deriveTelemetrySessionState({
      latestUploadResult: guardedLatestUploadResult,
      latestUploadSnapshot: guardedLatestUploadSnapshot,
      latestReplayFrame: historianReplayState.frame,
    }),
    [guardedLatestUploadResult, guardedLatestUploadSnapshot, historianReplayState.frame],
  );
  const hasCompletedAnalysisAvailable = isCompletedAnalysisPayload({
    result: guardedLatestUploadResult,
    snapshot: guardedLatestUploadSnapshot,
  });
  const sessionActivity = useMemo(
    () => deriveSessionActivity({
      telemetrySession: observableTelemetrySession,
      sessionIntent,
      gateUploadCompleteSeen,
      hasCompletedUploadOverride: Boolean(completedUploadOverride),
      resetGuardActive,
      autoResumeCompleted: hasCompletedAnalysisAvailable,
    }),
    [completedUploadOverride, gateUploadCompleteSeen, hasCompletedAnalysisAvailable, resetGuardActive, sessionIntent, observableTelemetrySession],
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
  const activeHasRealSiiOutput = useMemo(
    () => uploadStateView.hasVerifiedSiiCompletion({
      latestResult: effectiveLatestUploadResult,
      latestSnapshot: effectiveLatestUploadSnapshot,
    }),
    [effectiveLatestUploadResult, effectiveLatestUploadSnapshot],
  );
  const activeTelemetrySession = useMemo(
    () => uploadStateView.deriveTelemetrySessionState({
      latestUploadResult: effectiveLatestUploadResult,
      latestUploadSnapshot: effectiveLatestUploadSnapshot,
      latestReplayFrame: hasActiveSession ? historianReplayState.frame : null,
    }),
    [effectiveLatestUploadResult, effectiveLatestUploadSnapshot, hasActiveSession, historianReplayState.frame],
  );
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
    hasRealSiiOutput: activeHasRealSiiOutput,
    telemetrySession: activeTelemetrySession,
    sessionIntent: effectiveSessionIntent,
  }), [effectiveLatestUploadResult, effectiveLatestUploadSnapshot, effectiveSessionIntent, hasActiveSession, hasCurrentUploadResult, hasResumedSession, activeHasRealSiiOutput, activeTelemetrySession]);
  const canonicalFinding = useMemo(
    () => deriveCanonicalFinding({ currentSession, latestReplayFrame: historianReplayState.frame }),
    [currentSession, historianReplayState.frame],
  );
  const gateProcessing = useMemo(() => deriveGateProcessing(effectiveLatestUploadSnapshot), [effectiveLatestUploadSnapshot]);
  const persistedLatestUpload = useMemo(
    () => buildPersistedLatestUpload({
      latestUploadResult: guardedLatestUploadResult,
      latestUploadSnapshot: guardedLatestUploadSnapshot,
      hasActiveSession,
    }),
    [guardedLatestUploadResult, guardedLatestUploadSnapshot, hasActiveSession],
  );
  const previousUploadHistory = useMemo(
    () => Array.isArray(guardedLatestUploadSnapshot?.history) ? guardedLatestUploadSnapshot.history : [],
    [guardedLatestUploadSnapshot],
  );

  useEffect(() => {
    if (resetGuardActive) return;
    const record = createAnalysisRecord({ result: guardedLatestUploadResult, snapshot: guardedLatestUploadSnapshot });
    if (!record) return;
    setAnalysisHistory((current) => upsertCompletedAnalysis(current, record));
  }, [guardedLatestUploadResult, guardedLatestUploadSnapshot, resetGuardActive]);

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
    setRestoredAnalysisOverride(null);
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
    setResetGuardActive(false);
    setRestoredAnalysisOverride(null);
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

  const handleReopenHistoricalAnalysis = useCallback((recordId) => {
    const record = analysisHistory.find((item) => item.id === recordId);
    if (!record) return;
    setResetGuardActive(false);
    setRestoredAnalysisOverride(record);
    setCompletedUploadOverride(null);
    setPostUploadPendingSnapshot(null);
    setPostUploadExpectedJobId(null);
    setGateUploadCompleteSeen(false);
    setAllowPersistedLatest(true);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, "1");
    }
    setSessionIntent("current");
    setActiveWorkspace("system-body");
  }, [analysisHistory, setActiveWorkspace, setAllowPersistedLatest]);

  const handleDeleteHistoricalAnalysis = useCallback((recordId) => {
    setAnalysisHistory((current) => deleteAnalysisRecord(current, recordId));
    setRestoredAnalysisOverride((current) => current?.id === recordId ? null : current);
  }, []);

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
    setRestoredAnalysisOverride(null);
    setAnalysisHistory(writeAnalysisHistory([]));
    setPostUploadPendingSnapshot(null);
    setPostUploadExpectedJobId(null);
    setGateUploadCompleteSeen(false);
    if (typeof window !== "undefined") {
      window.localStorage.removeItem("neraium.last_upload_job_id");
      window.sessionStorage.removeItem(SESSION_INTENT_STORAGE_KEY);
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, "0");
    }
    setHistorianReplayState({ enabled: false, frame: null, meta: null });
    await loadLatestUploadState({ includePersisted: false });
    await loadFacilitySystems();
  }, [accessCode, apiFetch, clearUploadSessionState, loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest, setIsDemoMode]);

  const handleBackToGate = useCallback(async () => {
    if (hasActiveSession) {
      setGateUploadCompleteSeen(hasCurrentUploadResult);
      setSessionIntent(hasResumedSession ? "resumed" : "current");
    } else {
      setGateUploadCompleteSeen(false);
      setSessionIntent("neutral");
    }
    const hasResult = await loadLatestUploadState({ includePersisted: true, forceRefresh: true });
    if (!hasResult) {
      setCompletedUploadOverride(null);
      setPostUploadPendingSnapshot(null);
      setPostUploadExpectedJobId(null);
    }
    await loadFacilitySystems();
    setActiveWorkspace("system-body");
  }, [hasActiveSession, hasCurrentUploadResult, hasResumedSession, loadFacilitySystems, loadLatestUploadState, setActiveWorkspace]);

  const handleRetryWorkspace = useCallback(() => {
    console.info("[neraium] route retry requested", { workspace: activeWorkspace });
    setErrorBoundaryResetKey((current) => current + 1);
    if (activeWorkspace === "system-body") {
      void loadLatestUploadState({ includePersisted: true, forceRefresh: true });
      void loadFacilitySystems({ forceRefresh: true });
    }
  }, [activeWorkspace, loadFacilitySystems, loadLatestUploadState]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (effectiveSessionIntent === "neutral") {
      window.sessionStorage.removeItem(SESSION_INTENT_STORAGE_KEY);
    } else {
      window.sessionStorage.setItem(SESSION_INTENT_STORAGE_KEY, effectiveSessionIntent);
    }
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
    hasRealSiiOutput: activeHasRealSiiOutput,
    roomContext,
    currentSession,
    canonicalFinding,
    telemetrySession: activeTelemetrySession,
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
  };
}

function buildPersistedLatestUpload({ latestUploadResult = null, latestUploadSnapshot = null, hasActiveSession = false } = {}) {
  if (hasActiveSession || !latestUploadSnapshot) return null;
  const result = latestUploadResult ?? uploadStateView.resolveCurrentUploadResult({
    current_upload: latestUploadSnapshot?.current_upload ?? null,
    latest_result: latestUploadSnapshot?.latest_result ?? null,
    snapshot: latestUploadSnapshot,
  });
  const hasPersistedResult = uploadStateView.hasFullUploadResult(result) || uploadStateView.hasActiveTelemetrySnapshot(latestUploadSnapshot);
  if (!hasPersistedResult) return null;
  return {
    jobId: uploadStateView.resolveCurrentUploadJobId({
      current_upload: latestUploadSnapshot?.current_upload ?? null,
      latest_result: result,
      snapshot: latestUploadSnapshot,
    }),
    filename: result?.filename ?? latestUploadSnapshot?.last_filename ?? null,
    processedAt: result?.completed_at ?? latestUploadSnapshot?.last_processed_at ?? latestUploadSnapshot?.last_upload_at ?? null,
    result,
    snapshot: latestUploadSnapshot,
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
