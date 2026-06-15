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
  const currentUpload = snapshot?.current_upload ?? null;
  const traceability = result?.traceability ?? snapshot?.traceability ?? currentUpload?.traceability ?? null;
  return (
    result?.job_id
    ?? result?.run_id
    ?? result?.upload_id
    ?? traceability?.job_id
    ?? currentUpload?.job_id
    ?? currentUpload?.run_id
    ?? currentUpload?.upload_id
    ?? snapshot?.job_id
    ?? snapshot?.run_id
    ?? snapshot?.upload_id
    ?? null
  );
}
