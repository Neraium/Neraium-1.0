export const UPLOAD_STATUSES = Object.freeze({
  IDLE: "idle",
  VALIDATED: "validated",
  UPLOADING: "uploading",
  ACCEPTED: "accepted",
  QUEUED: "queued",
  PROCESSING: "processing",
  STRUCTURAL_SCORING: "structural_scoring",
  SAVING_RESULTS: "saving_results",
  SAVE_COMPLETE: "save_complete",
  NAVIGATION_PENDING: "navigation_pending",
  COMPLETE: "complete",
  FAILED: "failed",
  CANCELLED: "cancelled",
  TIMEOUT: "timeout",
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
  "building_fingerprint",
  "writing_state",
  "cognition_ready",
  "saving_result",
  "saving_results",
  "navigation_pending",
]);

export const UPLOAD_STAGE_PROGRESS = Object.freeze({
  idle: 0,
  validated: 5,
  uploading: 12,
  accepted: 20,
  queued: 20,
  pending: 20,
  validating_schema: 45,
  parsing: 20,
  baseline_modeling: 70,
  processing: 45,
  structural_scoring: 70,
  running_sii: 70,
  building_fingerprint: 90,
  writing_state: 90,
  cognition_ready: 90,
  saving_result: 90,
  saving_results: 99,
  save_complete: 100,
  navigation_pending: 100,
  complete: 100,
  cancelled: 100,
  timeout: 100,
  failed: 100,
  error: 100,
  validation_error: 100,
});

export const UPLOAD_STAGE_LABELS = Object.freeze({
  idle: "Awaiting file selection",
  validated: "Telemetry export validated",
  uploading: "Uploading telemetry batch",
  accepted: "Parsing telemetry...",
  queued: "Parsing telemetry...",
  validating_schema: "Validating signals...",
  parsing: "Parsing telemetry...",
  baseline_modeling: "Analyzing relationships...",
  processing: "Validating signals...",
  structural_scoring: "Analyzing relationships...",
  building_fingerprint: "Preparing results...",
  writing_state: "Preparing results...",
  cognition_ready: "Preparing results...",
  saving_result: "Preparing results...",
  saving_results: "Saving Behavior Baseline",
  save_complete: "Behavior Baseline Established",
  navigation_pending: "Loading Command Center",
  complete: "Analysis ready.",
  cancelled: "Analysis cancelled.",
  timeout: "Analysis timed out.",
  error: "Validation needs attention",
  failed: "Upload failed",
  validation_error: "Validation needs attention",
});

export const UPLOAD_STAGE_INDEX = Object.freeze({
  uploading: 0,
  accepted: 1,
  queued: 1,
  validating_schema: 1,
  parsing: 2,
  baseline_modeling: 3,
  structural_scoring: 4,
  building_fingerprint: 5,
  writing_state: 6,
  saving_result: 7,
  saving_results: 7,
  save_complete: 7,
  navigation_pending: 7,
  cognition_ready: 7,
  complete: 7,
  cancelled: 7,
  timeout: 7,
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
    building_fingerprint: "building_fingerprint",
    cognition_ready: "cognition_ready",
    generating_replay: "saving_result",
    saving_result: "saving_result",
    saving_results: "saving_results",
    save_complete: "save_complete",
    navigation_pending: "navigation_pending",
    generating_evidence: "writing_state",
    generating_findings_evidence: "writing_state",
    writing_result_replay: "saving_result",
    writing_state: "writing_state",
    complete: UPLOAD_STATUSES.COMPLETE,
    completed: UPLOAD_STATUSES.COMPLETE,
    success: UPLOAD_STATUSES.COMPLETE,
    failed: UPLOAD_STATUSES.FAILED,
    failure: UPLOAD_STATUSES.FAILED,
    cancelled: UPLOAD_STATUSES.CANCELLED,
    timeout: UPLOAD_STATUSES.TIMEOUT,
    error: UPLOAD_STATUSES.ERROR,
    validation_error: UPLOAD_STATUSES.VALIDATION_ERROR,
    not_found: UPLOAD_STATUSES.ERROR,
    missing: UPLOAD_STATUSES.ERROR,
    parsing_telemetry: "parsing",
    building_relationship_baselines: "baseline_modeling",
    scoring_relationship_drift: "structural_scoring",
    building_propagation_model: "writing_state",
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
