export function deriveCurrentSession({
  latestUploadResult,
  latestUploadSnapshot,
  hasActiveSession,
  hasCurrentUploadResult,
  hasResumedSession,
  hasRealSiiOutput,
}) {
  const snapshot = latestUploadSnapshot ?? null;
  const result = latestUploadResult ?? null;
  const currentUpload = snapshot?.current_upload ?? null;
  const interpretation = snapshot?.system_interpretation ?? result?.system_interpretation ?? null;
  const sessionJobId = currentUpload?.job_id ?? result?.job_id ?? snapshot?.job_id ?? null;
  const lineageJobId = interpretation?.lineage?.job_id ?? null;
  const hasAlignedInterpretation = Boolean(
    interpretation
    && interpretation?.lineage?.aligned
    && interpretation?.run_alignment_verified !== false,
  );
  const interpretationMatchesSession = !sessionJobId || !lineageJobId || String(lineageJobId) === String(sessionJobId);
  const hasReliableOperatorEvidence = Boolean(
    hasActiveSession
    && hasRealSiiOutput
    && result?.sii_reliable_enough_to_show === true
    && hasAlignedInterpretation
    && interpretationMatchesSession
  );
  const reviewReadiness = !hasActiveSession
    ? "no_session"
    : !hasRealSiiOutput
      ? "processing"
      : result?.sii_reliable_enough_to_show !== true
        ? "quality_gate"
        : !hasAlignedInterpretation || !interpretationMatchesSession
          ? "unaligned"
          : "ready";

  return {
    latestUploadResult: result,
    latestUploadSnapshot: snapshot,
    hasActiveSession: Boolean(hasActiveSession),
    hasCurrentUploadResult: Boolean(hasCurrentUploadResult),
    hasResumedSession: Boolean(hasResumedSession),
    hasRealSiiOutput: Boolean(hasRealSiiOutput),
    hasReliableOperatorEvidence,
    reviewReadiness,
  };
}

export function resolveSessionJobId(currentSession) {
  const snapshot = currentSession?.latestUploadSnapshot ?? null;
  const result = currentSession?.latestUploadResult ?? null;
  const currentUpload = snapshot?.current_upload ?? null;
  const traceability = currentUpload?.traceability ?? result?.traceability ?? snapshot?.traceability ?? null;
  return (
    currentUpload?.job_id
    ?? currentUpload?.run_id
    ?? currentUpload?.upload_id
    ?? result?.job_id
    ?? result?.run_id
    ?? result?.upload_id
    ?? traceability?.job_id
    ?? snapshot?.job_id
    ?? snapshot?.run_id
    ?? snapshot?.upload_id
    ?? null
  );
}
