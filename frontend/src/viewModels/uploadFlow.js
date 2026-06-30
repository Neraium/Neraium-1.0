import {
  isUploadProcessingStatus,
  normalizeErrorMessage as normalizeUploadContractErrorMessage,
  normalizeUploadStatus as normalizeUploadContractStatus,
  uploadStageIndex as uploadContractStageIndex,
  uploadStageLabel as uploadContractStageLabel,
} from "./uploadContract";

const INTAKE_STAGES = [
  "Uploading telemetry batch",
  "Validating CSV",
  "Normalizing telemetry",
  "Identifying systems",
  "Mapping relationships",
  "Building fingerprint",
  "Generating insights",
  "Saving result",
];

export function buildIntakeStages(result, uploadState, roomContext, job = null) {
  const activeIndex = uploadStageIndex(uploadState);
  const operatorReviewReady = result?.sii_reliable_enough_to_show === true;
  const finalStageIndex = INTAKE_STAGES.length - 1;
  return INTAKE_STAGES.map((stage, index) => {
    if (job || [...["failed", "cancelled", "timeout"], ...["uploading", "accepted", "queued", "validating_schema", "parsing", "baseline_modeling", "processing", "structural_scoring", "building_fingerprint", "writing_state", "cognition_ready", "saving_result"]].includes(normalizeUploadStatus(uploadState))) {
      const normalizedStatus = normalizeUploadStatus(uploadState);
      const terminalFailure = ["failed", "cancelled", "timeout"].includes(normalizedStatus);
      return {
        title: stage,
        detail: uploadStageDetail(stage, index, job, roomContext),
        state: terminalFailure
          ? index <= activeIndex ? "failed" : "queued"
          : index < activeIndex ? "complete" : index === activeIndex ? "active" : "queued",
        tone: terminalFailure && index <= activeIndex ? "unstable" : index <= activeIndex ? "info" : "review",
      };
    }

    if (!result) {
      return {
        title: stage,
        detail: index === 2
          ? "Reference learning begins after the telemetry batch is accepted."
          : "Upload telemetry to begin structural analysis.",
        state: "standby",
        tone: index === 3 ? "review" : "info",
      };
    }

    const details = [
      `${result.filename ?? result.last_filename ?? "Telemetry batch"} received for processing.`,
      `${result.columns?.length ?? result.columns_detected ?? result.column_count ?? 0} headers validated from the uploaded batch.`,
      `${result.row_count ?? result.rows_processed ?? 0} telemetry rows normalized for analysis.`,
      "System groups and primary operating patterns were identified.",
      "Cross-signal relationships were mapped against baseline behavior.",
      "Structural fingerprint built from the normalized telemetry.",
      "Insights generated from the latest telemetry evidence.",
      operatorReviewReady
        ? "Core result saved and ready for review."
        : "Core result saved; final report details may still be finalizing.",
    ];

    return {
      title: stage,
      detail: details[index],
      state: index === finalStageIndex && !operatorReviewReady ? "active" : "complete",
      tone: index === finalStageIndex && !operatorReviewReady
        ? "review"
        : index === 3 && !result.engine_result
          ? "review"
          : "nominal",
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
    const payloadErrorType = error?.payload?.error_type ?? error?.payload?.detail?.error_type ?? null;
    const payloadDetail = error?.payload?.message ?? error?.payload?.detail?.message ?? error?.payload?.detail ?? error?.payload?.error ?? null;
    const requestErrorType = error.errorType ?? payloadErrorType;
    const requestDetail = error.detail ?? payloadDetail ?? error.message;
    const isAuthDuringPolling = phase === "poll" && (error.status === 401 || error.status === 403);
    const isMissingStatusDuringPoll = phase === "poll" && error.status === 404 && requestErrorType === "upload_session_missing";
    return {
      state: isAuthDuringPolling || isMissingStatusDuringPoll || (phase === "poll" && error.retryable) ? "running_sii" : "error",
      retryable: phase === "poll" && error.retryable,
      status: error.status,
      errorType: requestErrorType,
      finalMessage: isMissingStatusDuringPoll
        ? "Upload status unavailable. The backend may have restarted or another ECS task may be serving polling."
        : null,
      message: operatorUploadMessage({
        status: error.status,
        errorType: requestErrorType,
        detail: requestDetail,
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
        : error?.name === "ApiTimeoutError"
          ? "Upload timed out."
          : normalizeErrorMessage(error?.message || "Upload network error before server accepted the file."),
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
        : normalizeErrorMessage(error?.message || "Upload network error before server accepted the file."),
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
  if (errorType === "shared_upload_queue_not_configured") {
    return "Upload processing is unavailable because the shared upload queue is not configured.";
  }
  if (errorType === "upload_queue_saturated") {
    return "Upload queue is saturated. Retry shortly.";
  }
  if (errorType === "upload_enqueue_failed") {
    return typeof detail === "string" && detail.trim()
      ? normalizeErrorMessage(detail)
      : "Upload processing is unavailable right now.";
  }
  if (errorType === "upload_status_unavailable") {
    return typeof detail === "string" && detail.trim()
      ? normalizeErrorMessage(detail)
      : "Upload status remained unavailable after repeated retries.";
  }
  if (errorType === "upload_too_large" || status === 413) {
    return typeof detail === "string" && detail.trim()
      ? normalizeErrorMessage(detail)
      : "File too large. Maximum supported size is 10 GB.";
  }
  if (errorType === "upload_response_timeout" || errorType === "timeout" || status === 408) {
    return phase === "poll"
      ? "Telemetry batch processing in progress. Large telemetry uploads may require additional processing time."
      : "Upload timed out.";
  }
  if (errorType === "csv_parse_error" || errorType === "processing_error") {
    return detail ? `CSV could not be parsed: ${normalizeErrorMessage(detail)}` : "CSV could not be parsed.";
  }
  if (status === 404 || status === 405) {
    return phase === "upload" ? "Upload endpoint unavailable." : "Upload status unavailable.";
  }
  if (errorType === "job_not_found") {
    return "Upload status unavailable.";
  }
  if (errorType === "sii_processing_failure") {
    return detail ? `Analysis processing failure: ${normalizeErrorMessage(detail)}` : "Analysis processing failure.";
  }
  if (status === 425 || status === 429 || status >= 500) {
    return phase === "poll"
      ? "Telemetry batch processing in progress. Large telemetry uploads may require additional processing time."
      : (typeof detail === "string" && detail.trim()
        ? normalizeErrorMessage(detail)
        : "Upload processing is unavailable right now.");
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
  return uploadContractStageLabel(normalized);
}

function uploadStageIndex(uploadState) {
  return uploadContractStageIndex(uploadState);
}

function uploadStageDetail(stage, index, job, roomContext) {
  const jobStatus = normalizeUploadStatus(job?.status);
  if (["failed", "cancelled", "timeout"].includes(jobStatus) && index === uploadStageIndex("failed")) {
    return job.error ?? "Telemetry processing failed.";
  }
  if (jobStatus === "complete") {
    return index === 7
      ? "The app is using the latest uploaded structural state."
      : "Stage complete.";
  }
  const details = [
    job?.message ?? "Telemetry batch upload starts after operator confirmation.",
    ["accepted", "queued", "validating_schema"].includes(jobStatus) ? job.progress_label : "CSV structure and key telemetry fields are being validated.",
    ["parsing", "processing"].includes(jobStatus) ? job.progress_label : "Telemetry is being normalized without loading the full export into memory.",
    jobStatus === "baseline_modeling" ? job.progress_label : "System groupings and baseline patterns are being identified.",
    jobStatus === "structural_scoring" ? job.progress_label : "Cross-signal relationships are being mapped against baseline behavior.",
    jobStatus === "building_fingerprint" ? job.progress_label : "A structural fingerprint is being assembled from the normalized telemetry.",
    jobStatus === "writing_state" ? job.progress_label : "Insights are being generated from the mapped system behavior.",
    ["cognition_ready", "saving_result"].includes(jobStatus) ? job.progress_label : "The core result can complete before optional report finalization finishes.",
    "Completion will refresh the structural state view.",
  ];
  return details[index] ?? stage;
}
