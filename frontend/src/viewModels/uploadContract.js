export const UPLOAD_STATUSES = Object.freeze({
  IDLE: "idle",
  VALIDATED: "validated",
  UPLOADING: "uploading",
  ACCEPTED: "accepted",
  QUEUED: "queued",
  PROCESSING: "processing",
  STRUCTURAL_SCORING: "structural_scoring",
  COMPLETE: "complete",
  FAILED: "failed",
  ERROR: "error",
  VALIDATION_ERROR: "validation_error",
});

export const UPLOAD_PROCESSING_STATUSES = Object.freeze([
  "uploading",
  "accepted",
  "queued",
  "validating_schema",
  "parsing",
  "baseline_modeling",
  "processing",
  "structural_scoring",
  "cognition_ready",
  "generating_replay",
  "writing_state",
]);

export function normalizeUploadStatus(status) {
  const raw = String(status ?? "").trim().toLowerCase();

  const map = {
    idle: UPLOAD_STATUSES.IDLE,
    validated: UPLOAD_STATUSES.VALIDATED,
    queued: UPLOAD_STATUSES.QUEUED,
    queue: UPLOAD_STATUSES.QUEUED,
    pending: UPLOAD_STATUSES.QUEUED,
    accepted: UPLOAD_STATUSES.ACCEPTED,
    uploading: UPLOAD_STATUSES.UPLOADING,
    upload_started: UPLOAD_STATUSES.UPLOADING,
    validating_schema: "validating_schema",
    parsing: "parsing",
    baseline_modeling: "baseline_modeling",
    processing: UPLOAD_STATUSES.PROCESSING,
    running: UPLOAD_STATUSES.PROCESSING,
    running_sii: UPLOAD_STATUSES.STRUCTURAL_SCORING,
    structural_scoring: UPLOAD_STATUSES.STRUCTURAL_SCORING,
    cognition_ready: "cognition_ready",
    generating_replay: "generating_replay",
    generating_evidence: "writing_state",
    writing_state: "writing_state",
    complete: UPLOAD_STATUSES.COMPLETE,
    completed: UPLOAD_STATUSES.COMPLETE,
    success: UPLOAD_STATUSES.COMPLETE,
    failed: UPLOAD_STATUSES.FAILED,
    failure: UPLOAD_STATUSES.FAILED,
    error: UPLOAD_STATUSES.ERROR,
    validation_error: UPLOAD_STATUSES.VALIDATION_ERROR,
    not_found: UPLOAD_STATUSES.ERROR,
    missing: UPLOAD_STATUSES.ERROR,
  };

  return map[raw] ?? raw ?? UPLOAD_STATUSES.IDLE;
}

export function normalizeErrorMessage(error) {
  if (!error) {
    return "Unknown error";
  }
  if (typeof error === "string") {
    return error;
  }
  if (error.message) {
    return normalizeErrorMessage(error.message);
  }
  if (error.detail) {
    return normalizeErrorMessage(error.detail);
  }
  if (typeof error === "object") {
    return JSON.stringify(error);
  }
  return "Unexpected processing error";
}

export function normalizeUploadJob(payload = {}) {
  const jobId = payload.job_id ?? payload.jobId ?? payload.id ?? null;
  const status = normalizeUploadStatus(payload.status ?? payload.processing_state ?? payload.stage ?? payload.propagation_stage);
  const percentRaw = payload.percent ?? payload.progress ?? payload.propagation_progress ?? 0;
  const percent = Number.isFinite(Number(percentRaw))
    ? Math.min(100, Math.max(0, Number(percentRaw)))
    : 0;

  return {
    ...payload,
    job_id: jobId,
    jobId,
    status,
    processing_state: payload.processing_state ?? status,
    percent,
    progress: percent,
    propagation_stage: payload.propagation_stage ?? null,
    propagation_progress: Number.isFinite(Number(payload.propagation_progress))
      ? Math.min(100, Math.max(0, Number(payload.propagation_progress)))
      : null,
    propagation_label: payload.propagation_label ?? null,
    filename: payload.filename ?? payload.file_name ?? null,
    message: payload.message ?? payload.progress_label ?? payload.propagation_label ?? payload.error ?? "",
    error: payload.error ?? payload.detail ?? null,
    result_available: Boolean(payload.result_available),
    replay_ready: Boolean(payload.replay_ready),
    replay_frame_count: Number(payload.replay_frame_count ?? 0) || 0,
  };
}

export function isUploadProcessingStatus(status) {
  return UPLOAD_PROCESSING_STATUSES.includes(normalizeUploadStatus(status));
}
