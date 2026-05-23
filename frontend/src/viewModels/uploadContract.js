export const UPLOAD_STATUSES = Object.freeze({
  IDLE: "idle",
  VALIDATED: "validated",
  UPLOADING: "uploading",
  ACCEPTED: "accepted",
  PENDING: "pending",
  PROCESSING: "processing",
  RUNNING_SII: "running_sii",
  COMPLETE: "complete",
  FAILED: "failed",
  ERROR: "error",
  VALIDATION_ERROR: "validation_error",
});

export function normalizeUploadStatus(status) {
  const raw = String(status ?? "").trim().toLowerCase();

  const map = {
    queued: UPLOAD_STATUSES.PENDING,
    queue: UPLOAD_STATUSES.PENDING,
    pending: UPLOAD_STATUSES.PENDING,
    accepted: UPLOAD_STATUSES.ACCEPTED,
    uploading: UPLOAD_STATUSES.UPLOADING,
    upload_started: UPLOAD_STATUSES.UPLOADING,
    processing: UPLOAD_STATUSES.PROCESSING,
    running: UPLOAD_STATUSES.PROCESSING,
    running_sii: UPLOAD_STATUSES.RUNNING_SII,
    structural_scoring: UPLOAD_STATUSES.RUNNING_SII,
    parsing: UPLOAD_STATUSES.PROCESSING,
    baseline_modeling: UPLOAD_STATUSES.PROCESSING,
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

export function normalizeUploadJob(payload = {}) {
  const jobId = payload.job_id ?? payload.jobId ?? payload.id ?? null;
  const status = normalizeUploadStatus(payload.status ?? payload.processing_state ?? payload.stage);
  const percentRaw = payload.percent ?? payload.progress ?? 0;
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
    filename: payload.filename ?? payload.file_name ?? null,
    message: payload.message ?? payload.progress_label ?? payload.error ?? "",
    error: payload.error ?? payload.detail ?? null,
    result_available: Boolean(payload.result_available),
    replay_ready: Boolean(payload.replay_ready),
    replay_frame_count: Number(payload.replay_frame_count ?? 0) || 0,
  };
}
