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
  const history = Array.isArray(snapshot?.history) ? snapshot.history : [];
  const persistedJobId = (typeof window !== "undefined")
    ? window.localStorage.getItem("neraium.last_upload_job_id")
    : null;
  return (
    result?.job_id
    ?? snapshot?.latest_result?.job_id
    ?? snapshot?.latest_upload?.job_id
    ?? history[0]?.job_id
    ?? persistedJobId
    ?? null
  );
}
