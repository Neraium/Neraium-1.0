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

export const UPLOAD_STAGE_PROGRESS = Object.freeze({
  idle: 0,
  validated: 3,
  uploading: 12,
  accepted: 10,
  queued: 5,
  pending: 5,
  validating_schema: 35,
  parsing: 20,
  baseline_modeling: 65,
  processing: 55,
  structural_scoring: 75,
  running_sii: 75,
  cognition_ready: 95,
  generating_replay: 95,
  writing_state: 85,
  complete: 100,
  failed: 100,
  error: 100,
  validation_error: 100,
});

export const UPLOAD_STAGE_LABELS = Object.freeze({
  idle: "Awaiting file selection",
  validated: "Telemetry export validated",
  uploading: "Uploading telemetry batch",
  accepted: "Reading uploaded CSV...",
  queued: "Worker starting...",
  validating_schema: "Detecting schema and telemetry signals...",
  parsing: "Parsing telemetry...",
  baseline_modeling: "Building baseline...",
  processing: "Checking data quality...",
  structural_scoring: "Scoring operating changes...",
  cognition_ready: "Writing result and replay...",
  generating_replay: "Writing result and replay...",
  writing_state: "Preparing findings...",
  complete: "Analysis ready.",
  error: "Validation needs attention",
  failed: "Upload failed",
  validation_error: "Validation needs attention",
});

export const UPLOAD_STAGE_INDEX = Object.freeze({
  uploading: 0,
  accepted: 0,
  queued: 0,
  validating_schema: 1,
  parsing: 2,
  baseline_modeling: 3,
  structural_scoring: 4,
  generating_replay: 5,
  cognition_ready: 6,
  writing_state: 6,
  complete: 7,
  failed: 6,
});

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
    detecting_schema_signals: "validating_schema",
    parsing: "parsing",
    reading_csv: UPLOAD_STATUSES.ACCEPTED,
    baseline_modeling: "baseline_modeling",
    building_baseline: "baseline_modeling",
    cleaning_imputing_data: UPLOAD_STATUSES.PROCESSING,
    profiling_data_quality: UPLOAD_STATUSES.PROCESSING,
    processing: UPLOAD_STATUSES.PROCESSING,
    running: UPLOAD_STATUSES.PROCESSING,
    running_sii: UPLOAD_STATUSES.STRUCTURAL_SCORING,
    structural_scoring: UPLOAD_STATUSES.STRUCTURAL_SCORING,
    scoring_drift_relationships: UPLOAD_STATUSES.STRUCTURAL_SCORING,
    cognition_ready: "cognition_ready",
    generating_replay: "generating_replay",
    generating_evidence: "writing_state",
    generating_findings_evidence: "writing_state",
    writing_result_replay: "generating_replay",
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
    parsing_telemetry: "parsing",
    building_relationship_baselines: "baseline_modeling",
    scoring_relationship_drift: "structural_scoring",
    building_propagation_model: "generating_replay",
    generating_system_interpretation: "writing_state",
    partial_complete: "cognition_ready",
  };

  return map[raw] ?? raw ?? UPLOAD_STATUSES.IDLE;
}

export function uploadStagePercent(status) {
  const normalized = normalizeUploadStatus(status);
  return UPLOAD_STAGE_PROGRESS[normalized] ?? null;
}

export function uploadStageLabel(status) {
  const normalized = normalizeUploadStatus(status);
  return UPLOAD_STAGE_LABELS[normalized] ?? UPLOAD_STAGE_LABELS.idle;
}

export function uploadStageIndex(status) {
  return UPLOAD_STAGE_INDEX[normalizeUploadStatus(status)] ?? 0;
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

export function hasSupportedSiiClaims(payload = {}) {
  return payload.sii_reliable_enough_to_show === true
    && (payload.evidence_persisted === true || payload.evidence_persistence?.persisted === true);
}

export function normalizeUploadJob(payload = {}) {
  const jobId = payload.job_id ?? payload.jobId ?? payload.id ?? null;
  const status = normalizeUploadStatus(
    payload.contract_stage
      ?? payload.status
      ?? payload.processing_state
      ?? payload.stage
      ?? payload.propagation_stage
  );
  const percentRaw = payload.contract_progress ?? payload.percent ?? payload.progress ?? payload.propagation_progress ?? uploadStagePercent(status) ?? 0;
  const percent = Number.isFinite(Number(percentRaw))
    ? Math.min(100, Math.max(0, Number(percentRaw)))
    : 0;

  return {
    ...payload,
    job_id: jobId,
    jobId,
    status,
    processing_state: payload.processing_state ?? status,
    contract_stage: payload.contract_stage ?? status,
    contract_progress: Number.isFinite(Number(payload.contract_progress))
      ? Math.min(100, Math.max(0, Number(payload.contract_progress)))
      : percent,
    contract_label: payload.contract_label ?? payload.progress_label ?? payload.message ?? uploadStageLabel(status),
    percent,
    progress: percent,
    propagation_stage: payload.propagation_stage ?? null,
    propagation_progress: Number.isFinite(Number(payload.propagation_progress))
      ? Math.min(100, Math.max(0, Number(payload.propagation_progress)))
      : null,
    propagation_label: payload.propagation_label ?? null,
    filename: payload.filename ?? payload.file_name ?? null,
    message: payload.message ?? payload.progress_label ?? payload.contract_label ?? payload.propagation_label ?? payload.error ?? "",
    error: payload.error ?? payload.detail ?? null,
    result_available: Boolean(payload.result_available),
    replay_ready: Boolean(payload.replay_ready),
    replay_frame_count: Number(payload.replay_frame_count ?? 0) || 0,
    rows_received: Number(payload.rows_received ?? payload.ingestion_report?.rows_received ?? payload.row_count ?? 0) || 0,
    rows_used: Number(payload.rows_used ?? payload.ingestion_report?.rows_used ?? payload.rows_processed ?? 0) || 0,
    rows_dropped: Number(payload.rows_dropped ?? payload.ingestion_report?.rows_dropped ?? 0) || 0,
    drop_reasons: payload.drop_reasons ?? payload.ingestion_report?.drop_reasons ?? {},
    processing_time_seconds: Number(payload.processing_time_seconds ?? payload.processing_stats?.processing_time_seconds ?? 0) || 0,
    quality_warning: payload.quality_warning ?? payload.data_quality?.warnings?.[0] ?? null,
    sii_reliable_enough_to_show: payload.sii_reliable_enough_to_show === true,
    evidence_persisted: payload.evidence_persisted === true || payload.evidence_persistence?.persisted === true,
    supported_sii_claims: hasSupportedSiiClaims(payload),
  };
}

export function isUploadProcessingStatus(status) {
  return UPLOAD_PROCESSING_STATUSES.includes(normalizeUploadStatus(status));
}
