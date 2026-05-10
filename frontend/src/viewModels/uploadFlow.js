const INTAKE_STAGES = [
  "Batch receipt",
  "Header and schema detection",
  "Timestamp and room context review",
  "SII engine processing",
  "Evidence and state write",
  "Complete",
];

export function buildIntakeStages(result, uploadState, roomContext, job = null) {
  const activeIndex = uploadStageIndex(uploadState);
  return INTAKE_STAGES.map((stage, index) => {
    if (job || [...["failed"], ...["uploading", "queued", "parsing", "baseline_modeling", "running_sii", "writing_state"]].includes(normalizeUploadStatus(uploadState))) {
      const normalizedStatus = normalizeUploadStatus(uploadState);
      return {
        title: stage,
        detail: uploadStageDetail(stage, index, job, roomContext),
        state: normalizedStatus === "failed"
          ? index <= activeIndex ? "failed" : "queued"
          : index < activeIndex ? "complete" : index === activeIndex ? "active" : "queued",
        tone: normalizedStatus === "failed" && index <= activeIndex ? "unstable" : index <= activeIndex ? "info" : "review",
      };
    }

    if (!result) {
      return {
        title: stage,
        detail: index === 2
          ? `Room context will resolve to ${roomContext.primary} after a completed upload.`
          : "Upload telemetry to begin ingestion and activate the dashboard.",
        state: "standby",
        tone: index === 3 ? "review" : "info",
      };
    }

    const details = [
      `${result.filename ?? result.last_filename ?? "Telemetry batch"} received for processing.`,
      `${result.columns?.length ?? result.columns_detected ?? result.column_count ?? 0} headers detected across the uploaded batch.`,
      `Room context resolved as ${roomContext.primary}.`,
      "SII engine processing complete.",
      "Evidence and facility state were written.",
      "Facility Command refreshed from latest uploaded state.",
    ];

    return {
      title: stage,
      detail: details[index],
      state: "complete",
      tone: index === 3 && !result.engine_result ? "review" : "nominal",
    };
  });
}

export function normalizeUploadStatus(status) {
  const normalized = String(status ?? "").toLowerCase();
  const aliases = {
    pending: "queued",
    queued: "queued",
    parsing: "parsing",
    baseline_modeling: "baseline_modeling",
    running_sii: "running_sii",
    generating_evidence: "writing_state",
    writing_state: "writing_state",
    complete: "complete",
    failed: "failed",
    not_found: "error",
  };
  return aliases[normalized] ?? normalized;
}

export function isUploadProcessing(status) {
  return ["uploading", "queued", "parsing", "baseline_modeling", "running_sii", "writing_state"].includes(normalizeUploadStatus(status));
}

export async function readJsonPayload(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
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

export function buildUploadRequestError(response, payload, phase) {
  const errorType = payload?.error_type ?? payload?.detail?.error_type ?? null;
  const isMissingStatusDuringPoll = phase === "poll" && response.status === 404 && errorType === "upload_session_missing";
  return {
    name: "UploadRequestError",
    status: response.status,
    phase,
    errorType,
    detail: normalizeErrorMessage(payload?.message ?? payload?.detail?.message ?? payload?.detail ?? payload?.error ?? ""),
    retryable: response.status === 408 || response.status === 409 || response.status === 425 || response.status === 429 || response.status >= 500 || (phase === "poll" && (response.status === 401 || response.status === 403)) || isMissingStatusDuringPoll,
  };
}

export function classifyUploadError(error, phase) {
  if (error?.name === "UploadRequestError") {
    const isAuthDuringPolling = phase === "poll" && (error.status === 401 || error.status === 403);
    const isMissingStatusDuringPoll = phase === "poll" && error.status === 404 && error.errorType === "upload_session_missing";
    return {
      state: isAuthDuringPolling || isMissingStatusDuringPoll || (phase === "poll" && error.retryable) ? "running_sii" : "error",
      retryable: phase === "poll" && error.retryable,
      status: error.status,
      errorType: error.errorType,
      finalMessage: isMissingStatusDuringPoll
        ? "Upload status unavailable. The backend may have restarted or another ECS task may be serving polling."
        : null,
      message: operatorUploadMessage({
        status: error.status,
        errorType: error.errorType,
        detail: error.detail,
        phase,
      }),
    };
  }
  if (error instanceof TypeError) {
    return {
      state: phase === "poll" ? "running_sii" : "error",
      retryable: phase === "poll",
      status: null,
      errorType: "network",
      message: phase === "poll"
        ? "Telemetry batch processing in progress. Large telemetry uploads may require additional processing time."
        : "Secure telemetry ingestion unavailable.",
    };
  }
  return {
    state: "error",
    retryable: false,
    status: null,
    errorType: null,
    message: operatorUploadMessage({
      status: null,
      errorType: null,
      detail: error?.message,
      phase,
    }),
  };
}

export function operatorUploadMessage({ status, errorType, detail, phase }) {
  if (errorType === "auth" || errorType === "auth_session_expired" || status === 401 || status === 403) {
    return phase === "poll"
      ? "Telemetry batch processing in progress. Large telemetry uploads may require additional processing time."
      : "Telemetry processing session could not be validated.";
  }
  if (errorType === "upload_session_missing") {
    if (phase === "poll") {
      return "Telemetry batch processing in progress. Waiting for upload status to become available.";
    }
    return "Upload state unavailable.";
  }
  if (errorType === "job_not_found" || status === 404) {
    return "Upload processing interrupted.";
  }
  if (errorType === "sii_processing_failure") {
    return detail ? `SII processing failure: ${normalizeErrorMessage(detail)}` : "SII processing failure.";
  }
  if (status === 408 || status === 425 || status === 429 || status >= 500) {
    return "Telemetry batch processing in progress. Large telemetry uploads may require additional processing time.";
  }
  if (phase === "poll") {
    return "Telemetry batch processing in progress. Large telemetry uploads may require additional processing time.";
  }
  return typeof detail === "string" && detail.trim()
    ? detail
    : "Upload processing interrupted.";
}

export function uploadStateMessage(uploadState) {
  const normalized = normalizeUploadStatus(uploadState);
  if (normalized === "uploading") {
    return "Telemetry batch received";
  }
  if (normalized === "queued") {
    return "Processing queued";
  }
  if (normalized === "parsing") {
    return "Header and schema detection";
  }
  if (normalized === "baseline_modeling") {
    return "Baseline modeling";
  }
  if (normalized === "running_sii") {
    return "Telemetry batch processing in progress";
  }
  if (normalized === "writing_state") {
    return "Writing facility state";
  }
  if (normalized === "complete") {
    return "Batch processing complete";
  }
  if (normalized === "error") {
    return "Validation needs attention";
  }
  return "Awaiting file selection";
}

function uploadStageIndex(uploadState) {
  return {
    uploading: 0,
    queued: 0,
    parsing: 1,
    baseline_modeling: 2,
    running_sii: 3,
    writing_state: 4,
    complete: 5,
    failed: 4,
  }[uploadState] ?? 0;
}

function uploadStageDetail(stage, index, job, roomContext) {
  const jobStatus = normalizeUploadStatus(job?.status);
  if (jobStatus === "failed" && index === uploadStageIndex("failed")) {
    return job.error ?? "Telemetry processing failed.";
  }
  if (jobStatus === "complete") {
    return index === 5
      ? "Facility Command is using the latest uploaded runner state."
      : "Stage complete.";
  }
  const details = [
    job?.message ?? "Telemetry batch received.",
    jobStatus === "parsing" ? job.progress_label : "Waiting for header and schema detection.",
    jobStatus === "baseline_modeling" ? job.progress_label : `Room context will resolve against ${roomContext.primary}.`,
    jobStatus === "running_sii" ? job.progress_label : "Telemetry processing will continue after baseline modeling.",
    jobStatus === "writing_state" ? job.progress_label : "Facility state will be written after telemetry processing.",
    "Completion will refresh Facility Command.",
  ];
  return details[index] ?? stage;
}
