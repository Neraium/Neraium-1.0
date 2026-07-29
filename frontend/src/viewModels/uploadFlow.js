import {
  isUploadProcessingStatus,
  normalizeErrorMessage as normalizeUploadContractErrorMessage,
  normalizeUploadStatus as normalizeUploadContractStatus,
  uploadStageIndex as uploadContractStageIndex,
  uploadStageLabel as uploadContractStageLabel,
} from "./uploadContract";

const INTAKE_STAGES = [
  "Import Dataset",
  "Check Dataset",
  "Prepare Dataset",
  "Learn Relationships",
  "Organize Systems",
  "Behavior Baseline",
  "Insights and Evidence",
  "Completion",
];

export const SERVICE_UNAVAILABLE_UPLOAD_MESSAGE = "Analysis service is temporarily unavailable. Retry the analysis.";
export const SERVICE_UNAVAILABLE_RETRY_MESSAGE = "Analysis service is temporarily unavailable. Retrying the analysis...";

const TRANSIENT_UPLOAD_SERVICE_STATUSES = new Set([408, 429, 502, 503, 504]);
const SERVICE_UNAVAILABLE_HTTP_STATUSES = new Set([502, 503]);

export function isTransientUploadServiceStatus(status) {
  return TRANSIENT_UPLOAD_SERVICE_STATUSES.has(Number(status));
}

export function isLikelyHtmlResponse(value = "", contentType = "") {
  const type = String(contentType || "").toLowerCase();
  const text = String(value || "").trim().toLowerCase();
  return type.includes("text/html")
    || text.startsWith("<!doctype html")
    || text.startsWith("<html")
    || text.includes("<head>")
    || text.includes("<body")
    || text.includes("<title>503 service temporarily unavailable</title>")
    || text.includes("<title>502 bad gateway</title>")
    || text.includes("<title>504 gateway time-out</title>");
}

function compactRawResponse(value = "") {
  const text = String(value || "");
  return text.length > 4000 ? `${text.slice(0, 4000)}...` : text;
}

function responseHeader(response, key) {
  try {
    return response?.headers?.get?.(key) || "";
  } catch {
    return "";
  }
}

export function buildUploadServiceUnavailablePayload({
  status = null,
  rawBody = "",
  route = "",
  phase = "",
  contentType = "",
  requestId = "",
  fallbackErrorType = "invalid_response",
} = {}) {
  const numericStatus = Number(status || 0) || null;
  const html = isLikelyHtmlResponse(rawBody, contentType);
  const serviceUnavailable = SERVICE_UNAVAILABLE_HTTP_STATUSES.has(numericStatus) || (html && numericStatus === null);
  const statusErrorType = ({
    401: "auth_session_expired",
    403: "auth_session_expired",
    404: "not_found",
    408: "server_timeout",
    413: "file_too_large",
    422: "validation_failed",
    429: "rate_limited",
    500: "internal_processing_failure",
    502: "service_unavailable",
    503: "service_unavailable",
    504: "server_timeout",
  })[numericStatus] ?? fallbackErrorType;
  const errorType = serviceUnavailable ? "service_unavailable" : statusErrorType;
  const message = operatorUploadMessage({
    status: numericStatus,
    errorType,
    detail: "",
    phase,
  });
  return {
    status: "FAILED",
    processing_state: "failed",
    error_type: errorType,
    message,
    error: message,
    response_status: numericStatus,
    failure_url: route || null,
    failure_phase: phase || null,
    raw_response_body: compactRawResponse(rawBody),
    response_content_type: contentType || null,
    non_json_response: true,
    html_response: html,
    request_id: requestId || null,
    diagnostic_timestamp: new Date().toISOString(),
  };
}

function hasSpecificTransientPayload(errorType) {
  return [
    "dataset_record_creation_failed",
    "file_storage_failed",
    "server_timeout",
    "server_unavailable",
    "unexpected_server_error",
    "upload_queue_saturated",
    "upload_rate_limited",
    "upload_status_rate_limited",
    "shared_upload_queue_not_configured",
    "large_upload_storage_unavailable",
  ].includes(String(errorType || ""));
}

function withResponseDiagnostics(payload, { status = null, rawBody = "", route = "", phase = "", contentType = "", requestId = "" } = {}) {
  const candidateErrorType = payload?.error_type ?? payload?.detail?.error_type ?? null;
  const rawMessage = payload?.message ?? payload?.detail?.message ?? payload?.detail ?? payload?.error ?? "";
  const html = isLikelyHtmlResponse(rawMessage, contentType) || isLikelyHtmlResponse(rawBody, contentType);
  const serviceUnavailable = html
    || (
      SERVICE_UNAVAILABLE_HTTP_STATUSES.has(Number(status))
      && !hasSpecificTransientPayload(candidateErrorType)
      && !String(rawMessage || "").trim()
    );
  const message = serviceUnavailable
    ? SERVICE_UNAVAILABLE_UPLOAD_MESSAGE
    : sanitizeUploadUserMessage(rawMessage, payload?.message ?? "");

  return {
    ...(payload ?? {}),
    ...(serviceUnavailable ? {
      status: payload?.status ?? "FAILED",
      processing_state: payload?.processing_state ?? "failed",
      error_type: "service_unavailable",
      message,
      error: message,
    } : {}),
    response_status: Number(status || 0) || payload?.response_status || null,
    failure_url: payload?.failure_url ?? route ?? null,
    failure_phase: payload?.failure_phase ?? phase ?? null,
    raw_response_body: payload?.raw_response_body ?? compactRawResponse(rawBody),
    response_content_type: payload?.response_content_type ?? contentType ?? null,
    html_response: payload?.html_response ?? html,
    request_id: payload?.request_id ?? requestId ?? null,
    diagnostic_timestamp: payload?.diagnostic_timestamp ?? new Date().toISOString(),
  };
}

export function sanitizeUploadUserMessage(value, fallback = "Analysis was interrupted. Retry the analysis.") {
  const text = typeof value === "string"
    ? value.trim()
    : normalizeUploadContractErrorMessage(value);
  if (!text || text === "Unknown error") return fallback;
  if (isLikelyHtmlResponse(text)) return SERVICE_UNAVAILABLE_UPLOAD_MESSAGE;
  if (/traceback|stack|exception|localhost|\/api\/|\b(?:sql|python|uvicorn|undefined|null pointer)\b/i.test(text)) {
    return "Analysis could not complete or save a usable result. Retry the analysis. If it happens again, contact an administrator.";
  }
  return text;
}

export function buildIntakeStages(result, uploadState, roomContext, job = null) {
  const activeIndex = uploadStageIndex(uploadState);
  const operatorReviewReady = result?.sii_reliable_enough_to_show === true;
  const finalStageIndex = INTAKE_STAGES.length - 1;
  return INTAKE_STAGES.map((stage, index) => {
    if (job || [...["failed", "cancelled", "timeout"], ...["uploading", "accepted", "queued", "validating_schema", "parsing", "baseline_modeling", "processing", "structural_scoring", "building_fingerprint", "writing_state", "cognition_ready", "saving_result", "saving_results", "navigation_pending"]].includes(normalizeUploadStatus(uploadState))) {
      const normalizedStatus = normalizeUploadStatus(uploadState);
      const terminalFailure = ["failed", "cancelled", "timeout"].includes(normalizedStatus);
      const failedStage = String(job?.failed_stage ?? job?.failedStage ?? "").trim().toLowerCase();
      const failedIndex = {
        upload_transfer: 0,
        authentication: 0,
        dataset_creation: 0,
        file_storage: 0,
        baseline_job_creation: 0,
        csv_parsing: 1,
        validation: 1,
        baseline_processing: 3,
        server: Math.max(0, activeIndex),
        unexpected: Math.max(0, activeIndex),
      }[failedStage] ?? Math.max(0, activeIndex);
      return {
        title: stage,
        detail: uploadStageDetail(stage, index, job, roomContext),
        state: terminalFailure
          ? index < failedIndex ? "complete" : index === failedIndex ? "failed" : "queued"
          : index < activeIndex ? "complete" : index === activeIndex ? "active" : "queued",
        tone: terminalFailure && index === failedIndex ? "unstable" : index <= activeIndex ? "info" : "review",
      };
    }

    if (!result) {
      return {
        title: stage,
        detail: index === 2
          ? "Dataset preparation begins after the import is accepted."
          : "Import a historical telemetry dataset to establish a behavior baseline.",
        state: "standby",
        tone: index === 3 ? "review" : "info",
      };
    }

    const details = [
      `${result.filename ?? result.last_filename ?? "Telemetry dataset"} imported for analysis.`,
      `${result.columns?.length ?? result.columns_detected ?? result.column_count ?? 0} telemetry fields validated from the uploaded batch.`,
      `${result.row_count ?? result.rows_processed ?? 0} telemetry rows prepared for comparison.`,
      "SII learned meaningful operational relationships from the telemetry.",
      "Related telemetry was organized into visible system behavior.",
      "Behavior baseline established from the prepared telemetry.",
      "Insights and supporting evidence generated from observed behavior.",
      operatorReviewReady
        ? "Behavior baseline saved and ready for review."
        : "Behavior baseline saved. Insights and evidence are still being prepared.",
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

export async function readJsonPayload(response, { route = null, phase = "" } = {}) {
  const contentType = responseHeader(response, "content-type");
  const requestId = responseHeader(response, "x-request-id");
  const responseRoute = route ?? response?.url ?? "";
  if (typeof response?.text === "function") {
    const rawText = await response.text();
    if (!rawText) {
      return withResponseDiagnostics({}, { status: response?.status, route: responseRoute, phase, contentType, requestId });
    }
    try {
      return withResponseDiagnostics(JSON.parse(rawText), {
        status: response?.status,
        rawBody: rawText,
        route: responseRoute,
        phase,
        contentType,
        requestId,
      });
    } catch {
      return buildUploadServiceUnavailablePayload({
        status: response?.status,
        rawBody: rawText,
        route: responseRoute,
        phase,
        contentType,
        requestId,
      });
    }
  }
  try {
    return withResponseDiagnostics(await response.json(), { status: response?.status, route: responseRoute, phase, contentType, requestId });
  } catch {
    return buildUploadServiceUnavailablePayload({ status: response?.status, route: responseRoute, phase, contentType, requestId });
  }
}

export function normalizeErrorMessage(error) {
  return sanitizeUploadUserMessage(normalizeUploadContractErrorMessage(error), "Unknown error");
}

export function buildUploadRequestError(response, payload, phase) {
  const payloadStatus = String(payload?.status ?? "").toUpperCase();
  const fallbackErrorType = ["NOT_FOUND", "MISSING"].includes(payloadStatus) ? "upload_session_missing" : null;
  const responseStatus = Number(response?.status ?? payload?.response_status ?? 0) || null;
  const errorDetails = payload?.error_details && typeof payload.error_details === "object"
    ? payload.error_details
    : {};
  const rawErrorType = payload?.error_code
    ?? errorDetails.code
    ?? payload?.error_type
    ?? payload?.detail?.error_code
    ?? payload?.detail?.error_type
    ?? fallbackErrorType;
  const serviceUnavailable = payload?.html_response === true
    || rawErrorType === "service_unavailable"
    || (SERVICE_UNAVAILABLE_HTTP_STATUSES.has(responseStatus) && !hasSpecificTransientPayload(rawErrorType));
  const errorType = serviceUnavailable ? "service_unavailable" : rawErrorType;
  const isMissingStatusDuringPoll =
    phase === "poll"
    && (
      (responseStatus === 404 && errorType === "upload_session_missing")
      || ["NOT_FOUND", "MISSING"].includes(payloadStatus)
    );
  return {
    name: "UploadRequestError",
    status: responseStatus,
    phase,
    errorType,
    detail: serviceUnavailable
      ? SERVICE_UNAVAILABLE_UPLOAD_MESSAGE
      : normalizeErrorMessage(payload?.message ?? errorDetails.message ?? payload?.detail?.message ?? payload?.detail ?? payload?.error ?? ""),
    payload,
    rawResponseBody: payload?.raw_response_body ?? "",
    failureUrl: payload?.failure_url ?? response?.url ?? null,
    failurePhase: payload?.failure_phase ?? phase,
    jobId: payload?.job_id ?? payload?.dataset_id ?? null,
    uploadSessionId: payload?.upload_session_id ?? null,
    failedStage: payload?.failed_stage ?? errorDetails.failed_stage ?? phase,
    transferSucceeded: payload?.transfer_succeeded === true,
    fileStored: payload?.file_stored === true,
    retryUrl: payload?.retry_url ?? null,
    requestId: payload?.request_id ?? responseHeader(response, "x-request-id") ?? null,
    diagnosticTimestamp: payload?.diagnostic_timestamp ?? new Date().toISOString(),
    retryable: typeof payload?.retryable === "boolean"
      ? payload.retryable
      : responseStatus === 408 || responseStatus === 409 || responseStatus === 425 || responseStatus === 429 || responseStatus >= 500 || (phase === "poll" && (responseStatus === 401 || responseStatus === 403)) || isMissingStatusDuringPoll,
  };
}

export function classifyUploadError(error, phase) {
  if (error?.name === "UploadRequestError") {
    const payloadErrorType = error?.payload?.error_code
      ?? error?.payload?.error_details?.code
      ?? error?.payload?.error_type
      ?? error?.payload?.detail?.error_code
      ?? error?.payload?.detail?.error_type
      ?? null;
    const payloadDetail = error?.payload?.message ?? error?.payload?.detail?.message ?? error?.payload?.detail ?? error?.payload?.error ?? null;
    const requestErrorType = error.errorType ?? payloadErrorType;
    const requestDetail = error.detail ?? payloadDetail ?? error.message;
    const isAuthDuringPolling = phase === "poll" && (error.status === 401 || error.status === 403);
    const isMissingStatusDuringPoll = phase === "poll" && error.status === 404 && requestErrorType === "upload_session_missing";
    return {
      state: isAuthDuringPolling || isMissingStatusDuringPoll || (phase === "poll" && error.retryable) ? "running_sii" : "error",
      retryable: Boolean(error.retryable),
      status: error.status,
      errorType: requestErrorType,
      failureUrl: error.failureUrl ?? error.uploadUrl ?? error.path ?? error.payload?.failure_url ?? null,
      failurePhase: error.failurePhase ?? error.phase ?? phase,
      rawResponseBody: error.rawResponseBody ?? error.responseText ?? error.payload?.raw_response_body ?? "",
      responseStatus: error.status ?? error.payload?.response_status ?? null,
      jobId: error.jobId ?? error.payload?.job_id ?? error.payload?.dataset_id ?? null,
      uploadSessionId: error.uploadSessionId ?? error.payload?.upload_session_id ?? null,
      failedStage: error.failedStage ?? error.payload?.failed_stage ?? error.failurePhase ?? phase,
      transferSucceeded: error.transferSucceeded === true || error.payload?.transfer_succeeded === true,
      fileStored: error.fileStored === true || error.payload?.file_stored === true,
      retryUrl: error.retryUrl ?? error.payload?.retry_url ?? null,
      requestId: error.requestId ?? error.payload?.request_id ?? null,
      diagnosticTimestamp: error.diagnosticTimestamp ?? error.payload?.diagnostic_timestamp ?? new Date().toISOString(),
      finalMessage: isMissingStatusDuringPoll
        ? "Analysis status is temporarily unavailable. Processing may still be active."
        : null,
      message: operatorUploadMessage({
        status: error.status,
        errorType: requestErrorType,
        detail: requestDetail,
        phase,
        transferSucceeded: error.transferSucceeded === true || error.payload?.transfer_succeeded === true,
      }),
    };
  }
  if (error?.name === "ApiTimeoutError" || error?.name === "ApiNetworkError") {
    const transferSucceeded = error?.transferSucceeded === true;
    return {
      state: phase === "poll" ? "running_sii" : "error",
      retryable: true,
      status: error?.name === "ApiTimeoutError" ? Number(error?.status ?? 408) || 408 : null,
      errorType: error?.name === "ApiTimeoutError" ? "timeout" : "network",
      failureUrl: error.uploadUrl ?? error.path ?? null,
      failurePhase: phase,
      rawResponseBody: error.responseText ?? "",
      responseStatus: error?.status ?? null,
      jobId: error?.jobId ?? null,
      uploadSessionId: error?.uploadSessionId ?? null,
      failedStage: error?.failedStage ?? phase,
      transferSucceeded,
      fileStored: error?.fileStored === true,
      retryUrl: error?.retryUrl ?? null,
      message: phase === "poll"
        ? "Dataset analysis is in progress. Large datasets may require additional processing time."
        : error?.name === "ApiTimeoutError"
          ? transferSucceeded
            ? "The file was transferred successfully, but the server timed out before processing could begin."
            : "The file transfer timed out. Check the connection and try again."
          : phase === "job_creation"
            ? "The file was transferred successfully, but Neraium could not begin processing it."
            : transferSucceeded
              ? "The file was transferred, but the server response was interrupted before processing could begin."
              : "The file transfer failed. Check the connection and try again.",
    };
  }
  if (error instanceof TypeError) {
    return {
      state: phase === "poll" ? "running_sii" : "error",
      retryable: true,
      status: null,
      errorType: "network",
      failureUrl: error.path ?? null,
      failurePhase: phase,
      rawResponseBody: "",
      responseStatus: null,
      jobId: error?.jobId ?? null,
      uploadSessionId: error?.uploadSessionId ?? null,
      failedStage: error?.failedStage ?? phase,
      transferSucceeded: error?.transferSucceeded === true,
      fileStored: error?.fileStored === true,
      retryUrl: error?.retryUrl ?? null,
      message: phase === "poll"
        ? "Dataset analysis is in progress. Large datasets may require additional processing time."
          : phase === "job_creation"
            ? "Upload completed, but analysis could not be started."
            : "The file transfer failed. Check the connection and try again.",
    };
  }
  return {
    state: "error",
    retryable: false,
    status: null,
    errorType: null,
    failureUrl: error?.path ?? null,
    failurePhase: phase,
    rawResponseBody: error?.responseText ?? "",
    responseStatus: null,
    jobId: error?.jobId ?? null,
    uploadSessionId: error?.uploadSessionId ?? null,
    failedStage: error?.failedStage ?? phase,
    transferSucceeded: error?.transferSucceeded === true,
    fileStored: error?.fileStored === true,
    retryUrl: error?.retryUrl ?? null,
    message: operatorUploadMessage({
      status: null,
      errorType: null,
      detail: error?.message,
      phase,
      transferSucceeded: error?.transferSucceeded === true,
    }),
  };
}

export function operatorUploadMessage({ status, errorType, detail, phase, transferSucceeded = false }) {
  if (errorType === "auth" || errorType === "auth_session_expired" || status === 401 || status === 403) {
    return phase === "poll"
      ? "Dataset analysis is in progress. Large datasets may require additional processing time."
      : "Your session has expired. Sign in again, then retry the import.";
  }
  if (errorType === "not_found" || status === 404) {
    return "The requested endpoint, dataset, or uploaded object was not found.";
  }
  if (errorType === "file_too_large" || errorType === "upload_too_large" || status === 413) {
    return typeof detail === "string" && detail.trim()
      ? normalizeErrorMessage(detail)
      : "File is larger than the supported upload limit.";
  }
  if (errorType === "rate_limited" || status === 429) {
    return "Analysis service is busy or rate limited. Retry shortly.";
  }
  if (errorType === "internal_processing_failure" || status === 500) {
    return "The server could not complete dataset processing.";
  }
  if (errorType === "dataset_record_creation_failed") {
    return transferSucceeded
      ? "The file was transferred successfully, but Neraium could not begin processing it."
      : normalizeErrorMessage(detail || "The dataset record could not be created. Retry the import.");
  }
  if (errorType === "file_storage_failed") {
    return transferSucceeded
      ? "The transfer completed, but the file could not be saved to secure storage."
      : normalizeErrorMessage(detail || "The file could not be saved to secure storage.");
  }
  if (errorType === "upload_transfer_failed") {
    return "The file transfer failed. Check the connection and try again.";
  }
  if (errorType === "csv_parsing_failed") {
    return "The CSV could not be parsed. Check its format and try again.";
  }
  if (errorType === "validation_failed") {
    return "The dataset did not pass validation. Check the file and try again.";
  }
  if (errorType === "baseline_processing_failed") {
    return "The dataset was imported, but baseline processing could not complete.";
  }
  if (errorType === "server_timeout") {
    return "The server timed out while processing the dataset. Retry the import.";
  }
  if (errorType === "server_unavailable") {
    return "The import service is temporarily unavailable. Retry shortly.";
  }
  if (errorType === "unexpected_server_error") {
    return "The server could not complete the import. Retry the import.";
  }
  if (errorType === "upload_session_missing") {
    if (phase === "poll") {
      return "Dataset analysis is in progress. Waiting for analysis status to become available.";
    }
    if (phase === "job_creation") return "Upload completed, but analysis could not be started.";
    if (phase === "upload_session") return "The upload session could not be created. Retry the import.";
    return "Analysis status is unavailable. Refresh and retry.";
  }
  if (errorType === "shared_upload_queue_not_configured") {
    return "Analysis processing is unavailable right now.";
  }
  if (errorType === "upload_queue_saturated") {
    return "Analysis service is busy. Retry shortly.";
  }
  if (errorType === "large_upload_storage_unavailable") {
    return "Secure file storage is temporarily unavailable. Retry shortly.";
  }
  if (["object_storage_upload_failed", "upload_not_complete", "upload_size_mismatch", "upload_etag_mismatch"].includes(errorType)) {
    return typeof detail === "string" && detail.trim()
      ? normalizeErrorMessage(detail)
      : "The file transfer failed. Check the connection and try again.";
  }
  if (errorType === "missing_job_id") {
    return "Upload completed, but analysis could not be started.";
  }
  if (errorType === "upload_enqueue_failed") {
    return typeof detail === "string" && detail.trim()
      ? normalizeErrorMessage(detail)
      : "Analysis processing is unavailable right now.";
  }
  if (errorType === "upload_status_unavailable") {
    return typeof detail === "string" && detail.trim()
      ? normalizeErrorMessage(detail)
      : "Analysis status remained unavailable after repeated retries.";
  }
  if (errorType === "service_unavailable" || [502, 503].includes(Number(status))) {
    return SERVICE_UNAVAILABLE_UPLOAD_MESSAGE;
  }
  if (errorType === "upload_too_large" || status === 413) {
    return typeof detail === "string" && detail.trim()
      ? normalizeErrorMessage(detail)
      : "File is larger than the supported upload limit.";
  }
  if (errorType === "upload_response_timeout" || errorType === "timeout" || status === 408 || status === 504) {
    return phase === "poll"
      ? "Dataset analysis is in progress. Large datasets may require additional processing time."
      : "Dataset import timed out. Retry the analysis.";
  }
  if (errorType === "csv_parse_error") {
    return detail ? `CSV could not be parsed: ${normalizeErrorMessage(detail)}` : "CSV could not be parsed.";
  }
  if (errorType === "processing_error") {
    return "The dataset was imported, but baseline processing could not complete.";
  }
  if (status === 404 || status === 405) {
    return phase === "upload" ? "Telemetry intake unavailable." : "Analysis status unavailable.";
  }
  if (errorType === "job_not_found") {
    return "Analysis status unavailable.";
  }
  if (errorType === "sii_processing_failure") {
    return detail ? `Analysis processing failure: ${normalizeErrorMessage(detail)}` : "Analysis processing failure.";
  }
  if (status === 425 || status === 429 || status >= 500) {
    return phase === "poll"
      ? "Dataset analysis is in progress. Large datasets may require additional processing time."
      : (typeof detail === "string" && detail.trim()
        ? normalizeErrorMessage(detail)
        : "Analysis processing is unavailable right now.");
  }
  if (phase === "poll") {
    return "Dataset analysis is in progress. Large datasets may require additional processing time.";
  }
  return typeof detail === "string" && detail.trim()
    ? detail
    : "Telemetry analysis interrupted.";
}

const UPLOAD_ERROR_TITLES = Object.freeze({
  upload_transfer_failed: "Upload transfer failed",
  network: "Upload transfer failed",
  aborted: "Upload transfer failed",
  auth: "Authentication expired",
  auth_session_expired: "Authentication expired",
  dataset_record_creation_failed: "Dataset record creation failed",
  missing_job_id: "Dataset record creation failed",
  upload_enqueue_failed: "Dataset record creation failed",
  file_storage_failed: "File storage failed",
  large_upload_storage_unavailable: "File storage failed",
  object_storage_upload_failed: "File storage failed",
  csv_parsing_failed: "CSV parsing failed",
  csv_parse_error: "CSV parsing failed",
  validation_failed: "Validation failed",
  validation_error: "Validation failed",
  baseline_processing_failed: "Baseline processing failed",
  processing_error: "Baseline processing failed",
  not_found: "Not found",
  file_too_large: "File too large",
  rate_limited: "Service busy",
  internal_processing_failure: "Processing failed",
  server_timeout: "Server timeout",
  timeout: "Server timeout",
  upload_response_timeout: "Server timeout",
  server_unavailable: "Server unavailable",
  service_unavailable: "Server unavailable",
  unexpected_server_error: "Unexpected server error",
});

export function uploadErrorPresentation(value = {}) {
  const errorCode = String(value?.error_code ?? value?.errorCode ?? value?.error_type ?? value?.errorType ?? "").trim();
  const failedStage = String(value?.failed_stage ?? value?.failedStage ?? "").trim();
  const transferSucceeded = value?.transfer_succeeded === true || value?.transferSucceeded === true;
  const title = UPLOAD_ERROR_TITLES[errorCode] ?? (
    failedStage === "upload_transfer" ? "Upload transfer failed" : "Unexpected server error"
  );
  const message = transferSucceeded && ["dataset_creation", "baseline_job_creation"].includes(failedStage)
    ? "The file was transferred successfully, but Neraium could not begin processing it."
    : operatorUploadMessage({
      status: value?.response_status ?? value?.responseStatus ?? value?.status ?? null,
      errorType: errorCode,
      detail: value?.message ?? value?.error,
      phase: value?.failure_phase ?? value?.failurePhase ?? failedStage,
      transferSucceeded,
    });
  return {
    errorCode: errorCode || "unexpected_server_error",
    failedStage: failedStage || "unexpected",
    title,
    heading: title === "Dataset record creation failed" ? "Dataset import failed" : title,
    message,
    retryable: value?.retryable !== false,
    transferSucceeded,
    fileStored: value?.file_stored === true || value?.fileStored === true,
  };
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
      ? "The workspace is using the established behavior baseline."
      : "Step complete.";
  }
  const details = [
    job?.message ?? "Telemetry upload starts after operator confirmation.",
    ["accepted", "queued", "validating_schema"].includes(jobStatus) ? job.progress_label : "Telemetry structure and key fields are being validated.",
    ["parsing", "processing"].includes(jobStatus) ? job.progress_label : "Telemetry is being normalized for relationship inference.",
    jobStatus === "baseline_modeling" ? job.progress_label : "Operational relationships are being inferred from the evidence.",
    jobStatus === "structural_scoring" ? job.progress_label : "Relationship changes are being organized into subsystem behavior.",
    jobStatus === "building_fingerprint" ? job.progress_label : "The behavior baseline is being established from normalized telemetry.",
    jobStatus === "writing_state" ? job.progress_label : "Insights and supporting evidence are being prepared from observed behavior.",
    ["cognition_ready", "saving_result"].includes(jobStatus) ? job.progress_label : "The behavior baseline is being persisted for workspace review.",
    "Completion will make the learned baseline available in the workspace.",
  ];
  return details[index] ?? stage;
}
