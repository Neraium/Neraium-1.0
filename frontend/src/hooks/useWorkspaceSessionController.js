import { useCallback, useEffect, useMemo, useState } from "react";
import * as uploadStateView from "../viewModels/uploadState";
import { analysisBelongsToBaseline } from "../viewModels/baselineSelection";
import { deriveCurrentSession, deriveSessionActivity } from "../viewModels/currentSession";
import { deriveCanonicalFinding } from "../viewModels/operatorFinding";
import { normalizeUploadStatus, uploadStateMessage } from "../viewModels/uploadFlow";
import { isUploadProcessingStatus, uploadStageLabel } from "../viewModels/uploadContract";
import { createUploadAttempt, uploadAttemptOwnsPayload } from "../viewModels/uploadAttempt";
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

function logStorageWarning(operation, error) {
  if (!import.meta.env.DEV) return;
  console.warn("[neraium] workspace storage unavailable", {
    operation,
    name: error?.name ?? "StorageError",
  });
}

function readStoredSessionIntent() {
  if (typeof window === "undefined") return "neutral";
  try {
    const allowPersisted = window.localStorage.getItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY);
    if (allowPersisted === "0") return "neutral";
    const value = window.sessionStorage.getItem(SESSION_INTENT_STORAGE_KEY);
    return value === "current" || value === "resumed" ? value : "neutral";
  } catch (error) {
    logStorageWarning("read-session-intent", error);
    return "neutral";
  }
}

export function readStoredAllowPersistedLatest() {
  if (typeof window === "undefined") return false;
  try {
    const explicitlyAllowed = window.localStorage.getItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY) === "1";
    const continuationIntent = window.sessionStorage.getItem(SESSION_INTENT_STORAGE_KEY);
    return explicitlyAllowed && (continuationIntent === "current" || continuationIntent === "resumed");
  } catch (error) {
    logStorageWarning("read-persisted-latest", error);
    return false;
  }
}

export default function useWorkspaceSessionController({
  activeWorkspace,
  datasetScopeKey,
  setActiveWorkspace,
  apiFetch,
  accessCode,
  sessionStore,
  loadFacilitySystems,
  loadLatestUploadState,
  allowPersistedLatest,
  setAllowPersistedLatest,
  commitCompletedUploadState,
  clearUploadSessionState,
  setIsDemoMode,
  activeBaselineIdentity = null,
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
  const [activeUploadAttempt, setActiveUploadAttempt] = useState(null);

  useEffect(() => {
    setSessionIntent(readStoredSessionIntent());
    setHistorianReplayState({ enabled: false, frame: null, meta: null });
    setResetGuardActive(false);
    setCompletedUploadOverride(null);
    setPostUploadPendingSnapshot(null);
    setPostUploadExpectedJobId(null);
    setGateUploadCompleteSeen(false);
    setRestoredAnalysisOverride(null);
    setActiveUploadAttempt(null);
    setAnalysisHistory(readAnalysisHistory());
  }, [datasetScopeKey]);

  useEffect(() => {
    if (!activeBaselineIdentity?.analysisRunId) return;
    setAllowPersistedLatest(true);
    setSessionIntent("resumed");
  }, [activeBaselineIdentity?.analysisRunId, setAllowPersistedLatest]);

  const canonicalLatestUploadJobId = sessionStore?.jobId ?? null;
  const canonicalLatestUploadSnapshot = sessionStore?.latestUploadSnapshot ?? null;
  const pendingUploadJobId = uploadStateView.resolveCurrentUploadJobId(postUploadPendingSnapshot);
  const restoredAnalysisResult = restoredAnalysisOverride?.result ?? null;
  const restoredAnalysisSnapshot = restoredAnalysisOverride?.snapshot ?? null;
  // A selected baseline establishes an ownership boundary. Broad "latest"
  // records and browser-restored history are ignored unless they are a completed
  // comparison run linked to this exact portfolio and baseline.
  const candidateLatestUploadResult = completedUploadOverride ?? restoredAnalysisResult ?? sessionStore?.latestUploadResult ?? null;
  const selectedBaselineRejectsCandidate = Boolean(activeBaselineIdentity?.baselineId)
    && (!activeUploadAttempt || activeUploadAttempt.workflow === "analyze_new_data")
    && !analysisBelongsToBaseline(candidateLatestUploadResult, activeBaselineIdentity);
  const uploadAttemptRejectsCandidate = Boolean(activeUploadAttempt)
    && !uploadAttemptOwnsPayload(activeUploadAttempt, candidateLatestUploadResult);
  const candidateLatestUploadSnapshot = postUploadPendingSnapshot
    ?? restoredAnalysisSnapshot
    ?? sessionStore?.latestUploadSnapshot
    ?? uploadStateView.buildEmptyLatestUploadSnapshot();
  const uploadAttemptRejectsSnapshot = Boolean(activeUploadAttempt)
    && !uploadAttemptOwnsPayload(activeUploadAttempt, candidateLatestUploadSnapshot);
  const guardedLatestUploadResult = resetGuardActive || selectedBaselineRejectsCandidate || uploadAttemptRejectsCandidate
    ? null
    : candidateLatestUploadResult;
  const guardedLatestUploadSnapshot = resetGuardActive
    ? uploadStateView.buildEmptyLatestUploadSnapshot()
    : activeUploadAttempt && (uploadAttemptRejectsSnapshot || selectedBaselineRejectsCandidate)
      ? buildActiveUploadAttemptSnapshot(activeUploadAttempt)
      : selectedBaselineRejectsCandidate
        ? uploadStateView.buildEmptyLatestUploadSnapshot()
        : scopeSnapshotToUploadAttempt(candidateLatestUploadSnapshot, activeUploadAttempt);

  const observableTelemetrySession = useMemo(
    () => uploadStateView.deriveTelemetrySessionState({
      latestUploadResult: guardedLatestUploadResult,
      latestUploadSnapshot: guardedLatestUploadSnapshot,
      latestReplayFrame: historianReplayState.frame,
    }),
    [guardedLatestUploadResult, guardedLatestUploadSnapshot, historianReplayState.frame],
  );
  const sessionActivity = useMemo(
    () => deriveSessionActivity({
      telemetrySession: observableTelemetrySession,
      sessionIntent,
      gateUploadCompleteSeen,
      hasCompletedUploadOverride: Boolean(completedUploadOverride),
      resetGuardActive,
    }),
    [completedUploadOverride, gateUploadCompleteSeen, resetGuardActive, sessionIntent, observableTelemetrySession],
  );
  const effectiveSessionIntent = sessionActivity.effectiveIntent;

  useEffect(() => {
    if (!postUploadExpectedJobId) return;
    if (!canonicalLatestUploadJobId || String(canonicalLatestUploadJobId) !== String(postUploadExpectedJobId)) return;
    if (!uploadStateView.isCompletedUploadState(canonicalLatestUploadSnapshot)) return;
    console.info("[neraium] current upload refetch result", {
      expectedJobId: postUploadExpectedJobId,
      canonicalJobId: canonicalLatestUploadJobId,
    });
    setPostUploadPendingSnapshot(null);
    setPostUploadExpectedJobId(null);
  }, [canonicalLatestUploadJobId, canonicalLatestUploadSnapshot, postUploadExpectedJobId]);

  useEffect(() => {
    if (!completedUploadOverride) return;
    const overrideJobId = String(completedUploadOverride?.job_id ?? "").trim();
    if (!overrideJobId) return;
    const sessionResult = sessionStore?.latestUploadResult ?? null;
    if (!sessionResult || !uploadStateView.hasFullUploadResult(sessionResult)) return;
    if (String(sessionResult?.job_id ?? "").trim() !== overrideJobId) return;
    if (!uploadStateView.isCompletedUploadState(sessionStore?.latestUploadSnapshot)) return;
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

  const handleUploadAttemptStarted = useCallback(({ files = [], workflow = "create_baseline" } = {}) => {
    if (!files[0]) return null;
    const attempt = createUploadAttempt({ files, workflow });
    clearUploadSessionState();
    setActiveUploadAttempt(attempt);
    setCompletedUploadOverride(null);
    setPostUploadPendingSnapshot(null);
    setPostUploadExpectedJobId(null);
    setRestoredAnalysisOverride(null);
    setGateUploadCompleteSeen(false);
    setSessionIntent("current");
    return attempt;
  }, [clearUploadSessionState]);

  const handleUploadAttemptIdentified = useCallback(({ attemptId = null, jobId = null, datasetId = null, workflow = null } = {}) => {
    setActiveUploadAttempt((current) => {
      if (!current || (attemptId && current.attemptId !== attemptId)) return current;
      return {
        ...current,
        ...(jobId ? { jobId: String(jobId) } : {}),
        ...(datasetId ? { datasetId: String(datasetId) } : {}),
        ...(workflow ? { workflow: String(workflow) } : {}),
        phase: jobId ? "processing" : current.phase,
      };
    });
  }, []);

  const handleUploadAttemptCleared = useCallback(() => {
    setActiveUploadAttempt(null);
  }, []);

  const handleGateUploadComplete = useCallback(async (completedPayload = null, options = {}) => {
    const completedResult = uploadStateView.resolveCurrentUploadResult(completedPayload)
      ?? (uploadStateView.hasFullUploadResult(completedPayload) ? completedPayload : null);
    const expectedJobId = uploadStateView.resolveCurrentUploadJobId(completedPayload)
      ?? (String(completedResult?.job_id ?? "").trim() || null);
    const completedDatasetId = completedResult?.dataset_id
      ?? completedResult?.datasetId
      ?? completedPayload?.dataset_id
      ?? completedPayload?.datasetId
      ?? null;
    const completionAttemptId = String(options.attemptId ?? "").trim() || null;
    const completionMatchesActiveAttempt = !activeUploadAttempt
      || (completionAttemptId && completionAttemptId === activeUploadAttempt.attemptId)
      || (activeUploadAttempt.jobId && expectedJobId && String(activeUploadAttempt.jobId) === String(expectedJobId));
    if (!completionMatchesActiveAttempt) {
      console.info("[neraium] stale upload completion ignored", {
        activeAttemptId: activeUploadAttempt.attemptId,
        completionAttemptId,
        activeJobId: activeUploadAttempt.jobId ?? null,
        completionJobId: expectedJobId,
      });
      return { ignored: true, jobId: expectedJobId };
    }
    setResetGuardActive(false);
    setIsDemoMode(false);
    setAllowPersistedLatest(true);
    setGateUploadCompleteSeen(true);
    setRestoredAnalysisOverride(null);
    const completionAttempt = expectedJobId
      ? { ...(activeUploadAttempt ?? {}), jobId: expectedJobId, datasetId: completedDatasetId ?? activeUploadAttempt?.datasetId ?? null }
      : activeUploadAttempt;
    const pendingSnapshot = expectedJobId
      ? buildPendingUploadSnapshot({ completedPayload, completedResult, expectedJobId })
      : null;
    const completionStatus = normalizeUploadStatus(completedPayload?.status ?? completedPayload?.processing_state ?? completedPayload?.worker_state);
    const terminalCompletion = completionStatus === "complete"
      || completionStatus === "save_complete"
      || completedPayload?.result_available === true
      || completedPayload?.sii_completed === true
      || completedPayload?.sii_reliable_enough_to_show === true;
    if (completedResult) {
      setCompletedUploadOverride(completedResult);
    } else {
      setCompletedUploadOverride(null);
    }
    if (expectedJobId) {
      setActiveUploadAttempt((current) => current ? {
        ...current,
        jobId: expectedJobId,
        ...(completedDatasetId ? { datasetId: String(completedDatasetId) } : {}),
        phase: terminalCompletion ? "complete" : "processing",
      } : current);
      setPostUploadExpectedJobId(expectedJobId);
      setPostUploadPendingSnapshot(pendingSnapshot);
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
    if (terminalCompletion && isCompletedAnalysisPayload({ result: completedResult, snapshot: pendingSnapshot })) {
      commitCompletedUploadState?.({
        latestResult: completedResult,
        latestSnapshot: pendingSnapshot,
      });
    }
    console.info("[neraium] state hydration started", { jobId: expectedJobId });
    const latestRefresh = await loadLatestUploadState({ includePersisted: true, forceRefresh: true, returnPayload: true });
    console.info("[neraium] current upload refetch requested", {
      expectedJobId,
      canonicalJobId: canonicalLatestUploadJobId,
      pendingJobId: pendingUploadJobId,
    });
    const refreshedResult = uploadAttemptOwnsPayload(completionAttempt, latestRefresh?.latestResult)
      ? latestRefresh.latestResult
      : completedResult;
    const refreshedSnapshot = uploadAttemptOwnsPayload(completionAttempt, latestRefresh?.snapshot)
      ? latestRefresh.snapshot
      : pendingSnapshot;
    const payloadValid = isCompletedAnalysisPayload({ result: refreshedResult, snapshot: refreshedSnapshot });
    console.info("[neraium] payload validation result", { jobId: expectedJobId, valid: payloadValid, terminal: terminalCompletion });
    if (terminalCompletion && !payloadValid) {
      throw new Error("The saved analysis result could not be opened. Refresh and retry.");
    }
    if (refreshedResult) {
      setCompletedUploadOverride(refreshedResult);
    }
    setSessionIntent("current");
    const facilityRefreshed = await loadFacilitySystems({ includePersisted: true, forceRefresh: true });
    console.info("[neraium] state hydration completed", { jobId: expectedJobId, facilityRefreshed });
    if (!facilityRefreshed) {
      throw new Error("Facility state refresh failed after results were saved.");
    }
    if (options.navigateToGate !== false) {
      console.info("[neraium] navigation started", { target: "system-body", jobId: expectedJobId });
      setActiveWorkspace("system-body");
    }
    return {
      jobId: expectedJobId,
      latestResult: refreshedResult,
      latestSnapshot: refreshedSnapshot,
      payloadValid,
      facilityRefreshed,
    };
  }, [activeUploadAttempt, canonicalLatestUploadJobId, commitCompletedUploadState, loadFacilitySystems, loadLatestUploadState, pendingUploadJobId, setActiveWorkspace, setAllowPersistedLatest, setIsDemoMode]);

  const handleResumePreviousSession = useCallback(async () => {
    setActiveUploadAttempt(null);
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
    await loadFacilitySystems({ includePersisted: true });
    setActiveWorkspace("system-body");
  }, [loadFacilitySystems, loadLatestUploadState, setActiveWorkspace, setAllowPersistedLatest]);

  const handleReopenHistoricalAnalysis = useCallback((recordId) => {
    const record = analysisHistory.find((item) => item.id === recordId);
    if (!record) return;
    setResetGuardActive(false);
    setActiveUploadAttempt(null);
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
    setActiveUploadAttempt(null);
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
    await loadFacilitySystems({ includePersisted: false });
  }, [accessCode, apiFetch, clearUploadSessionState, loadFacilitySystems, loadLatestUploadState, setAllowPersistedLatest, setIsDemoMode]);

  const handleBackToGate = useCallback(async () => {
    if (hasActiveSession) {
      setGateUploadCompleteSeen(hasCurrentUploadResult);
      setSessionIntent(hasResumedSession ? "resumed" : "current");
    } else {
      setGateUploadCompleteSeen(false);
      setSessionIntent("neutral");
    }
    const hasResult = await loadLatestUploadState({ includePersisted: hasActiveSession, forceRefresh: true });
    if (!hasResult) {
      setCompletedUploadOverride(null);
      setPostUploadPendingSnapshot(null);
      setPostUploadExpectedJobId(null);
    }
    await loadFacilitySystems({ includePersisted: hasActiveSession });
    setActiveWorkspace("system-body");
  }, [hasActiveSession, hasCurrentUploadResult, hasResumedSession, loadFacilitySystems, loadLatestUploadState, setActiveWorkspace]);

  const handleRetryWorkspace = useCallback(() => {
    console.info("[neraium] route retry requested", { workspace: activeWorkspace });
    setErrorBoundaryResetKey((current) => current + 1);
    if (activeWorkspace === "system-body") {
      void loadLatestUploadState({ includePersisted: hasActiveSession, forceRefresh: true });
      void loadFacilitySystems({ includePersisted: hasActiveSession, forceRefresh: true });
    }
  }, [activeWorkspace, hasActiveSession, loadFacilitySystems, loadLatestUploadState]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      if (effectiveSessionIntent === "neutral") {
        window.sessionStorage.removeItem(SESSION_INTENT_STORAGE_KEY);
      } else {
        window.sessionStorage.setItem(SESSION_INTENT_STORAGE_KEY, effectiveSessionIntent);
      }
    } catch (error) {
      logStorageWarning("write-session-intent", error);
    }
  }, [effectiveSessionIntent]);

  useEffect(() => {
    if (!allowPersistedLatest && effectiveSessionIntent !== "neutral") {
      setSessionIntent("neutral");
    }
  }, [allowPersistedLatest, effectiveSessionIntent]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(ALLOW_PERSISTED_LATEST_STORAGE_KEY, allowPersistedLatest ? "1" : "0");
    } catch (error) {
      logStorageWarning("write-persisted-latest", error);
    }
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

function buildActiveUploadAttemptSnapshot(attempt) {
  if (!attempt) return uploadStateView.buildEmptyLatestUploadSnapshot();
  return {
    ...uploadStateView.buildEmptyLatestUploadSnapshot(),
    status: "uploading",
    processing_state: "uploading",
    session_state: "processing",
    state_available: true,
    client_attempt_id: attempt.attemptId,
    job_id: attempt.jobId ?? null,
    dataset_id: attempt.datasetId ?? null,
    last_filename: attempt.filename ?? null,
    progress_label: "Preparing the selected dataset for upload.",
    message: "Preparing the selected dataset for upload.",
    current_upload: {
      client_attempt_id: attempt.attemptId,
      job_id: attempt.jobId ?? null,
      dataset_id: attempt.datasetId ?? null,
      filename: attempt.filename ?? null,
      result: null,
    },
  };
}

function scopeSnapshotToUploadAttempt(snapshot, attempt) {
  if (!attempt || !snapshot) return snapshot;
  const nestedResult = uploadStateView.resolveCurrentUploadResult(snapshot);
  if (!nestedResult || uploadAttemptOwnsPayload(attempt, nestedResult)) return snapshot;
  return {
    ...snapshot,
    latest_result: null,
    current_upload: snapshot.current_upload
      ? { ...snapshot.current_upload, result: null }
      : snapshot.current_upload,
  };
}

function buildPendingUploadSnapshot({ completedPayload = null, completedResult = null, expectedJobId = null } = {}) {
  if (!expectedJobId) return null;
  const terminalCompletion = uploadStateView.isCompletedUploadState(completedPayload)
    || completedPayload?.result_available === true
    || completedPayload?.sii_completed === true;
  const status = terminalCompletion
    ? "COMPLETE"
    : normalizeUploadStatus(completedPayload?.status ?? completedPayload?.processing_state ?? completedPayload?.worker_state) || "structural_scoring";
  return {
    ...uploadStateView.buildEmptyLatestUploadSnapshot(),
    ...(completedPayload ?? {}),
    status,
    processing_state: terminalCompletion ? "complete" : status,
    ...(terminalCompletion ? { job_state: "completed", terminal: true, result_available: true } : {}),
    session_state: terminalCompletion ? "verified" : (completedPayload?.session_state ?? "processing"),
    progress_label: completedPayload?.progress_label ?? completedPayload?.message ?? (terminalCompletion ? "Analysis ready." : "Telemetry is available. Analysis has not started."),
    message: completedPayload?.message ?? completedPayload?.progress_label ?? (terminalCompletion ? "Analysis ready." : "Telemetry is available. Analysis has not started."),
    percent: terminalCompletion
      ? 100
      : completedPayload?.job_progress?.overall_percent_complete ?? completedPayload?.percent ?? completedPayload?.progress ?? null,
    progress: terminalCompletion
      ? 100
      : completedPayload?.job_progress?.overall_percent_complete ?? completedPayload?.progress ?? completedPayload?.percent ?? null,
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
  const rawPercent = snapshot?.job_progress?.overall_percent_complete
    ?? snapshot?.contract_progress
    ?? snapshot?.percent
    ?? snapshot?.progress
    ?? null;
  const percent = rawPercent === null ? null : Number(rawPercent);
  return {
    active: isUploadProcessingStatus(status),
    percent: Number.isFinite(percent) ? Math.max(0, Math.min(100, Math.round(percent))) : null,
    label: String(snapshot?.contract_label ?? snapshot?.progress_label ?? snapshot?.message ?? uploadStageLabel(status) ?? uploadStateMessage(status)),
  };
}
