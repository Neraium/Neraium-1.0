import { resolveCurrentUploadJobId, resolveCurrentUploadResult } from "./uploadState";

let uploadAttemptSequence = 0;

function text(value) {
  return String(value ?? "").trim() || null;
}

function firstText(...values) {
  for (const value of values) {
    const normalized = text(value);
    if (normalized) return normalized;
  }
  return null;
}

export function resolveUploadIdentity(payload = null) {
  const result = resolveCurrentUploadResult(payload) ?? payload?.result ?? payload;
  return {
    jobId: firstText(
      resolveCurrentUploadJobId(payload),
      result?.job_id,
      result?.jobId,
      result?.run_id,
      result?.upload_id,
      payload?.job_id,
      payload?.jobId,
    ),
    datasetId: firstText(
      result?.dataset_id,
      result?.datasetId,
      payload?.dataset_id,
      payload?.datasetId,
      payload?.current_upload?.dataset_id,
      payload?.snapshot?.current_upload?.dataset_id,
    ),
  };
}

export function createUploadAttempt({ files = [], workflow = "create_baseline" } = {}) {
  const file = Array.isArray(files) ? files[0] : null;
  uploadAttemptSequence += 1;
  const randomId = typeof crypto !== "undefined" ? crypto.randomUUID?.() : null;
  return {
    attemptId: randomId ?? `upload-attempt-${Date.now()}-${uploadAttemptSequence}`,
    jobId: null,
    datasetId: null,
    filename: text(file?.name),
    fileSize: Number(file?.size ?? 0) || 0,
    fileLastModified: Number(file?.lastModified ?? 0) || 0,
    workflow: text(workflow) ?? "create_baseline",
    phase: "selected",
  };
}

export function uploadAttemptOwnsPayload(attempt, payload) {
  if (!attempt) return true;
  if (!payload) return false;
  const attemptJobId = text(attempt.jobId);
  const attemptDatasetId = text(attempt.datasetId);
  if (!attemptJobId && !attemptDatasetId) return false;

  const identity = resolveUploadIdentity(payload);
  let matched = false;
  if (attemptJobId && identity.jobId) {
    if (attemptJobId !== identity.jobId) return false;
    matched = true;
  }
  if (attemptDatasetId && identity.datasetId) {
    if (attemptDatasetId !== identity.datasetId) return false;
    matched = true;
  }
  return matched;
}

export function assessmentBelongsToUploadAttempt({ attempt = null, result = null, job = null, profile = null } = {}) {
  if (!attempt) return true;
  const resultIdentity = resolveUploadIdentity(result);
  const jobIdentity = resolveUploadIdentity(job);
  const profileIdentity = resolveUploadIdentity(profile);
  if ((profileIdentity.jobId || profileIdentity.datasetId) && !uploadAttemptOwnsPayload(attempt, profile)) {
    return false;
  }
  const sourceIdentity = {
    jobId: firstText(resultIdentity.jobId, jobIdentity.jobId, profileIdentity.jobId),
    datasetId: firstText(resultIdentity.datasetId, jobIdentity.datasetId, profileIdentity.datasetId),
  };
  return uploadAttemptOwnsPayload(attempt, sourceIdentity);
}
