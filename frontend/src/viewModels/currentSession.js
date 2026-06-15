export function deriveCurrentSession({
  latestUploadResult,
  latestUploadSnapshot,
  hasActiveSession,
  hasCurrentUploadResult,
  hasResumedSession,
  hasRealSiiOutput,
}) {
  return {
    latestUploadResult: latestUploadResult ?? null,
    latestUploadSnapshot: latestUploadSnapshot ?? null,
    hasActiveSession: Boolean(hasActiveSession),
    hasCurrentUploadResult: Boolean(hasCurrentUploadResult),
    hasResumedSession: Boolean(hasResumedSession),
    hasRealSiiOutput: Boolean(hasRealSiiOutput),
  };
}

export function resolveSessionJobId(currentSession) {
  const snapshot = currentSession?.latestUploadSnapshot ?? null;
  const result = currentSession?.latestUploadResult ?? null;
  const traceability = result?.traceability ?? snapshot?.traceability ?? null;
  const history = Array.isArray(snapshot?.history) ? snapshot.history : [];
  return (
    result?.job_id
    ?? result?.run_id
    ?? result?.upload_id
    ?? traceability?.job_id
    ?? snapshot?.job_id
    ?? snapshot?.run_id
    ?? snapshot?.upload_id
    ?? history[0]?.job_id
    ?? null
  );
}
