import {
  isUploadProcessingStatus,
  normalizeErrorMessage as normalizeUploadContractErrorMessage,
  normalizeUploadStatus as normalizeUploadContractStatus,
} from "./uploadContract";

const INTAKE_STAGES = [
  "Uploading telemetry batch",
  "Detecting variables",
  "Parsing state matrix",
  "Building baseline regime",
  "Computing structural drift",
  "Generating replay frames",
  "Preparing observations",
  "Ready",
];

export function buildIntakeStages(result, uploadState, roomContext, job = null) {
  const activeIndex = uploadStageIndex(uploadState);
  return INTAKE_STAGES.map((stage, index) => {
    if (job || [...["failed"], ...["uploading", "queued", "validating_schema", "parsing", "baseline_modeling", "structural_scoring", "cognition_ready", "generating_replay", "writing_state"]].includes(normalizeUploadStatus(uploadState))) {
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
          ? "Baseline profiling begins after the telemetry batch is accepted."
          : "Upload telemetry to begin structural analysis.",
        state: "standby",
        tone: index === 3 ? "review" : "info",
      };
    }

    const details = [
      `${result.filename ?? result.last_filename ?? "Telemetry batch"} received for processing.`,
      `${result.columns?.length ?? result.columns_detected ?? result.column_count ?? 0} headers detected across the uploaded batch.`,
      `${result.row_count ?? result.rows_processed ?? 0} rows parsed from the state matrix.`,
      "Baseline regime profiled from the uploaded telemetry.",
      "Structural drift scoring complete.",
      "Replay/evidence generation complete or available in the evidence workspace.",
      "Observation layer prepared from the latest uploaded state.",
      "Structural state refreshed from the latest uploaded telemetry.",
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
  return normalizeUploadContractStatus(status);
}

export function isUploadProcessing(status) {
  return isUploadProcessingStatus(status);
}

export async function readJsonPayload(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

export function normalizeErrorMessage(error) {
  return normalizeUploadContractErrorMessage(error);
}

export function buildUploadRequestError(response, payload, phase) {
  const payloadStatus = String(payload?.status ?? "").toUpperCase();
  const fallbackErrorType = ["NOT_FOUND", "MISSING"].includes(payloadStatus) ? "upload_session_missing" : null;
  const errorType = payload?.error_type ?? payload?.detail?.error_type ?? fallbackErrorType;
  const isMissingStatusDuringPoll =
    phase === "poll"
    && (
      (response.status === 404 && errorType === "upload_session_missing")
      || ["NOT_FOUND", "MISSING"].includes(payloadStatus)
    );
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
  if (error?.name === "ApiTimeoutError" || error?.name === "ApiNetworkError") {
    return {
      state: phase === "poll" ? "running_sii" : "error",
      retryable: phase === "poll",
      status: error?.name === "ApiTimeoutError" ? Number(error?.status ?? 408) || 408 : null,
      errorType: error?.name === "ApiTimeoutError" ? "timeout" : "network",
      message: phase === "poll"
        ? "Telemetry batch processing in progress. Large telemetry uploads may require additional processing time."
        : "Secure telemetry ingestion unavailable.",
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
  if (normalized === "validating_schema") {
    return "Validating schema";
  }
  if (normalized === "parsing") {
    return "Parsing signal matrix";
  }
  if (normalized === "baseline_modeling") {
    return "Building baseline regime";
  }
  if (normalized === "structural_scoring") {
    return "Computing structural drift";
  }
  if (normalized === "cognition_ready") {
    return "Cognition ready";
  }
  if (normalized === "generating_replay") {
    return "Generating replay frames";
  }
  if (normalized === "writing_state") {
    return "Writing structural state";
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
    validating_schema: 1,
    parsing: 2,
    baseline_modeling: 3,
    structural_scoring: 4,
    generating_replay: 5,
    cognition_ready: 6,
    writing_state: 6,
    complete: 7,
    failed: 6,
  }[normalizeUploadStatus(uploadState)] ?? 0;
}

function uploadStageDetail(stage, index, job, roomContext) {
  const jobStatus = normalizeUploadStatus(job?.status);
  if (jobStatus === "failed" && index === uploadStageIndex("failed")) {
    return job.error ?? "Telemetry processing failed.";
  }
  if (jobStatus === "complete") {
    return index === 7
      ? "The app is using the latest uploaded structural state."
      : "Stage complete.";
  }
  const details = [
    job?.message ?? "Telemetry batch upload starts after operator confirmation.",
    jobStatus === "validating_schema" ? job.progress_label : "Waiting for variable and schema detection.",
    jobStatus === "parsing" ? job.progress_label : "Parser will stream the state matrix without loading the full export into memory.",
    jobStatus === "baseline_modeling" ? job.progress_label : "The instrument is profiling a baseline regime from the uploaded telemetry.",
    jobStatus === "structural_scoring" ? job.progress_label : "Structural drift scoring starts after baseline modeling.",
    jobStatus === "generating_replay" ? job.progress_label : "Replay frames are deferred until first cognition state is ready.",
    ["cognition_ready", "writing_state"].includes(jobStatus) ? job.progress_label : "Observations become usable before all downstream artifacts finish.",
    "Completion will refresh the structural state view.",
  ];
  return details[index] ?? stage;
}
