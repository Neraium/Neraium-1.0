import {
  buildEmptyLatestUploadSnapshot,
  deriveTelemetrySessionState,
  hasActiveTelemetrySnapshot,
  hasFullUploadResult,
  isCompletedUploadState,
  resolveCurrentUploadJobId,
  resolveCurrentUploadResult,
} from "./uploadState";
import { isCompletedAnalysisPayload } from "./analysisHistory";

export const FRONTEND_SESSION_STATES = Object.freeze({
  IDLE: "idle",
  EMPTY: "empty",
  QUEUED: "queued",
  PROCESSING: "processing",
  VERIFIED: "verified",
  RESTORED: "restored",
  STALE: "stale",
  ERROR: "error",
});

const BACKEND_TO_FRONTEND_STATE = Object.freeze({
  empty: FRONTEND_SESSION_STATES.EMPTY,
  queued: FRONTEND_SESSION_STATES.QUEUED,
  processing: FRONTEND_SESSION_STATES.PROCESSING,
  complete: FRONTEND_SESSION_STATES.VERIFIED,
  completed: FRONTEND_SESSION_STATES.VERIFIED,
  save_complete: FRONTEND_SESSION_STATES.VERIFIED,
  navigation_pending: FRONTEND_SESSION_STATES.VERIFIED,
  success: FRONTEND_SESSION_STATES.VERIFIED,
  verified: FRONTEND_SESSION_STATES.VERIFIED,
  exact_analysis: FRONTEND_SESSION_STATES.VERIFIED,
  restored: FRONTEND_SESSION_STATES.RESTORED,
  stale: FRONTEND_SESSION_STATES.STALE,
  error: FRONTEND_SESSION_STATES.ERROR,
});

const STATE_LABELS = Object.freeze({
  idle: "Waiting for session state",
  empty: "No upload session",
  queued: "Upload queued",
  processing: "Processing telemetry",
  verified: "Verified telemetry session",
  restored: "Restored telemetry session",
  stale: "Stale telemetry session",
  error: "Upload session error",
});

export function buildEmptySessionStore() {
  const snapshot = buildEmptyLatestUploadSnapshot();
  return {
    loaded: false,
    uiState: FRONTEND_SESSION_STATES.IDLE,
    backendState: "empty",
    label: STATE_LABELS.idle,
    jobId: null,
    runId: null,
    uploadId: null,
    datasetId: null,
    workflow: null,
    latestUploadSnapshot: snapshot,
    latestUploadResult: null,
    telemetrySession: deriveTelemetrySessionState({
      latestUploadResult: null,
      latestUploadSnapshot: snapshot,
    }),
    hasActiveSession: false,
    hasResult: false,
    hasRuntimeData: false,
    isProcessing: false,
    isRestored: false,
    isEmpty: true,
    isStale: false,
    isError: false,
    message: snapshot.message,
    payload: { snapshot, latestResult: null },
  };
}

export function buildSessionStore(payload, { loaded = true } = {}) {
  if (!loaded && !payload) {
    return buildEmptySessionStore();
  }
  const sourcePayload = payload ?? {};
  const snapshot = sourcePayload.snapshot ?? sourcePayload ?? buildEmptyLatestUploadSnapshot();
  const latestUploadResult = resolveCurrentUploadResult(sourcePayload);
  const jobId = resolveCurrentUploadJobId(sourcePayload);
  const identityPayload = latestUploadResult ?? snapshot?.current_upload ?? snapshot;
  const runId = String(identityPayload?.run_id ?? snapshot?.run_id ?? jobId ?? "").trim() || null;
  const uploadId = String(identityPayload?.upload_id ?? snapshot?.upload_id ?? jobId ?? "").trim() || null;
  const datasetId = String(identityPayload?.dataset_id ?? identityPayload?.datasetId ?? snapshot?.dataset_id ?? snapshot?.datasetId ?? "").trim() || null;
  const workflow = String(identityPayload?.workflow ?? snapshot?.workflow ?? "").trim() || null;
  const backendState = String(sourcePayload.session_state ?? snapshot.session_state ?? snapshot.status ?? "empty").toLowerCase();
  const uiState = loaded
    ? (BACKEND_TO_FRONTEND_STATE[backendState] ?? FRONTEND_SESSION_STATES.EMPTY)
    : FRONTEND_SESSION_STATES.IDLE;
  const telemetrySession = deriveTelemetrySessionState({
    latestUploadResult,
    latestUploadSnapshot: snapshot,
  });
  const hasResult = hasFullUploadResult(latestUploadResult);
  const hasRuntimeData = hasResult || hasActiveTelemetrySnapshot(snapshot);
  return {
    loaded,
    uiState,
    backendState,
    label: STATE_LABELS[uiState] ?? STATE_LABELS.empty,
    jobId,
    runId,
    uploadId,
    datasetId,
    workflow,
    latestUploadSnapshot: snapshot,
    latestUploadResult,
    telemetrySession,
    hasActiveSession: ![FRONTEND_SESSION_STATES.IDLE, FRONTEND_SESSION_STATES.EMPTY, FRONTEND_SESSION_STATES.STALE, FRONTEND_SESSION_STATES.ERROR].includes(uiState),
    hasResult,
    hasRuntimeData,
    isProcessing: [FRONTEND_SESSION_STATES.QUEUED, FRONTEND_SESSION_STATES.PROCESSING].includes(uiState),
    isRestored: uiState === FRONTEND_SESSION_STATES.RESTORED,
    isEmpty: uiState === FRONTEND_SESSION_STATES.EMPTY,
    isStale: uiState === FRONTEND_SESSION_STATES.STALE,
    isError: uiState === FRONTEND_SESSION_STATES.ERROR,
    message: String(snapshot.message ?? snapshot.progress_label ?? snapshot.contract_label ?? ""),
    payload: sourcePayload,
  };
}

export function resolveSessionStore({
  sessionStore = null,
  latestUploadSnapshot = null,
  latestUploadResult = null,
} = {}) {
  if (sessionStore) {
    return sessionStore;
  }
  return buildSessionStore(
    {
      snapshot: latestUploadSnapshot,
      latest_result: latestUploadResult,
      session_state: latestUploadSnapshot?.session_state
        ?? (latestUploadResult ? FRONTEND_SESSION_STATES.VERIFIED : (latestUploadSnapshot?.status ?? FRONTEND_SESSION_STATES.EMPTY)),
    },
    { loaded: true },
  );
}

export function buildLatestUploadSessionState(payload, { loaded = true } = {}) {
  const sessionStore = buildSessionStore(payload, { loaded });
  return {
    snapshot: sessionStore.latestUploadSnapshot,
    latestResult: sessionStore.latestUploadResult,
    sessionStore,
  };
}

export function isValidTerminalUploadSessionState(state) {
  const jobId = state?.sessionStore?.jobId ?? resolveCurrentUploadJobId({
    snapshot: state?.snapshot,
    latest_result: state?.latestResult,
  });
  return Boolean(
    jobId
    && (isCompletedUploadState(state?.snapshot) || state?.snapshot?.sii_completed === true)
    && isCompletedAnalysisPayload({
      result: state?.latestResult,
      snapshot: state?.snapshot,
    }),
  );
}

/**
 * Reconcile a latest-upload response at the canonical session boundary.
 *
 * A valid terminal result is sticky only for its own job attempt. Empty or
 * non-terminal responses for that job are stale by definition after completion;
 * an explicit different job id establishes a new attempt and may progress
 * normally.
 */
export function reconcileLatestUploadSessionState({ incomingPayload, terminalState = null } = {}) {
  const incomingState = buildLatestUploadSessionState(incomingPayload, { loaded: true });
  const retainedTerminal = isValidTerminalUploadSessionState(terminalState) ? terminalState : null;
  const incomingIsTerminal = isValidTerminalUploadSessionState(incomingState);
  const incomingJobId = incomingState.sessionStore.jobId;
  const terminalJobId = retainedTerminal?.sessionStore?.jobId ?? null;
  const belongsToTerminalAttempt = Boolean(
    retainedTerminal
    && (!incomingJobId || String(incomingJobId) === String(terminalJobId)),
  );

  if (belongsToTerminalAttempt && !incomingIsTerminal) {
    return {
      ...retainedTerminal,
      terminalState: retainedTerminal,
      incomingIsTerminal: false,
      retainedTerminal: true,
    };
  }

  return {
    ...incomingState,
    terminalState: incomingIsTerminal
      ? incomingState
      : (incomingJobId && terminalJobId && String(incomingJobId) !== String(terminalJobId) ? null : retainedTerminal),
    incomingIsTerminal,
    retainedTerminal: false,
  };
}
