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
  fallbackErrorType = "invalid_response",
} = {}) {
  const numericStatus = Number(status || 0) || null;
  const html = isLikelyHtmlResponse(rawBody, contentType);
  const serviceUnavailable = html || isTransientUploadServiceStatus(numericStatus);
  const message = serviceUnavailable
    ? SERVICE_UNAVAILABLE_UPLOAD_MESSAGE
    : "Analysis service response was unavailable.";
  return {
    status: "FAILED",
    processing_state: "failed",
    error_type: serviceUnavailable ? "service_unavailable" : fallbackErrorType,
    message,
    error: message,
    response_status: numericStatus,
    failure_url: route || null,
    failure_phase: phase || null,
    raw_response_body: compactRawResponse(rawBody),
    response_content_type: contentType || null,
    non_json_response: true,
    html_response: html,
  };
}

function hasSpecificTransientPayload(errorType) {
  return [
    "upload_queue_saturated",
    "upload_rate_limited",
    "upload_status_rate_limited",
    "shared_upload_queue_not_configured",
  ].includes(String(errorType || ""));
}

function withResponseDiagnostics(payload, { status = null, rawBody = "", route = "", phase = "", contentType = "" } = {}) {
  const candidateErrorType = payload?.error_type ?? payload?.detail?.error_type ?? null;
  const rawMessage = payload?.message ?? payload?.detail?.message ?? payload?.detail ?? payload?.error ?? "";
  const html = isLikelyHtmlResponse(rawMessage, contentType) || isLikelyHtmlResponse(rawBody, contentType);
  const serviceUnavailable = html
    || (
      isTransientUploadServiceStatus(status)
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
  const responseRoute = route ?? response?.url ?? "";
  if (typeof response?.text === "function") {
    const rawText = await response.text();
    if (!rawText) {
      return withResponseDiagnostics({}, { status: response?.status, route: responseRoute, phase, contentType });
    }
    try {
      return withResponseDiagnostics(JSON.parse(rawText), {
        status: response?.status,
        rawBody: rawText,
        route: responseRoute,
        phase,
        contentType,
      });
    } catch {
      return buildUploadServiceUnavailablePayload({
        status: response?.status,
        rawBody: rawText,
        route: responseRoute,
        phase,
        contentType,
      });
    }
  }
  try {
    return withResponseDiagnostics(await response.json(), { status: response?.status, route: responseRoute, phase, contentType });
  } catch {
    return buildUploadServiceUnavailablePayload({ status: response?.status, route: responseRoute, phase, contentType });
  }
}

export function normalizeErrorMessage(error) {
  return sanitizeUploadUserMessage(normalizeUploadContractErrorMessage(error), "Unknown error");
}

export function buildUploadRequestError(response, payload, phase) {
  const payloadStatus = String(payload?.status ?? "").toUpperCase();
  const fallbackErrorType = ["NOT_FOUND", "MISSING"].includes(payloadStatus) ? "upload_session_missing" : null;
  const responseStatus = Number(response?.status ?? payload?.response_status ?? 0) || null;
  const rawErrorType = payload?.error_type ?? payload?.detail?.error_type ?? fallbackErrorType;
  const serviceUnavailable = payload?.html_response === true
    || rawErrorType === "service_unavailable"
    || (isTransientUploadServiceStatus(responseStatus) && !hasSpecificTransientPayload(rawErrorType));
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
      : normalizeErrorMessage(payload?.message ?? payload?.detail?.message ?? payload?.detail ?? payload?.error ?? ""),
    payload,
    rawResponseBody: payload?.raw_response_body ?? "",
    failureUrl: payload?.failure_url ?? response?.url ?? null,
    failurePhase: payload?.failure_phase ?? phase,
    retryable: responseStatus === 408 || responseStatus === 409 || responseStatus === 425 || responseStatus === 429 || responseStatus >= 500 || (phase === "poll" && (responseStatus === 401 || responseStatus === 403)) || isMissingStatusDuringPoll,
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
      failureUrl: error.failureUrl ?? error.uploadUrl ?? error.path ?? error.payload?.failure_url ?? null,
      failurePhase: error.failurePhase ?? error.phase ?? phase,
      rawResponseBody: error.rawResponseBody ?? error.responseText ?? error.payload?.raw_response_body ?? "",
      responseStatus: error.status ?? error.payload?.response_status ?? null,
      finalMessage: isMissingStatusDuringPoll
        ? "Analysis status is temporarily unavailable. Processing may still be active."
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
      failureUrl: error.uploadUrl ?? error.path ?? null,
      failurePhase: phase,
      rawResponseBody: error.responseText ?? "",
      responseStatus: error?.status ?? null,
      message: phase === "poll"
        ? "Dataset analysis is in progress. Large datasets may require additional processing time."
        : error?.name === "ApiTimeoutError"
          ? "Dataset import timed out. Retry the analysis."
          : normalizeErrorMessage(error?.message || "The dataset could not be imported because the analysis service could not be reached. Retry the analysis."),
    };
  }
  if (error instanceof TypeError) {
    return {
      state: phase === "poll" ? "running_sii" : "error",
      retryable: phase === "poll",
      status: null,
      errorType: "network",
      failureUrl: error.path ?? null,
      failurePhase: phase,
      rawResponseBody: "",
      responseStatus: null,
      message: phase === "poll"
        ? "Dataset analysis is in progress. Large datasets may require additional processing time."
        : normalizeErrorMessage(error?.message || "The dataset could not be imported because the analysis service could not be reached. Retry the analysis."),
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
      ? "Dataset analysis is in progress. Large datasets may require additional processing time."
      : "Your analysis session could not be verified. Sign in again, then retry the analysis.";
  }
  if (errorType === "upload_session_missing") {
    if (phase === "poll") {
      return "Dataset analysis is in progress. Waiting for analysis status to become available.";
    }
    return "Analysis status is unavailable. Refresh and retry.";
  }
  if (errorType === "shared_upload_queue_not_configured") {
    return "Analysis processing is unavailable right now.";
  }
  if (errorType === "upload_queue_saturated") {
    return "Analysis service is busy. Retry shortly.";
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
  if (errorType === "service_unavailable" || [502, 503, 504].includes(Number(status))) {
    return SERVICE_UNAVAILABLE_UPLOAD_MESSAGE;
  }
  if (errorType === "upload_too_large" || status === 413) {
    return typeof detail === "string" && detail.trim()
      ? normalizeErrorMessage(detail)
      : "File too large. Maximum supported size is 10 GB.";
  }
  if (errorType === "upload_response_timeout" || errorType === "timeout" || status === 408) {
    return phase === "poll"
      ? "Dataset analysis is in progress. Large datasets may require additional processing time."
      : "Dataset import timed out. Retry the analysis.";
  }
  if (errorType === "csv_parse_error" || errorType === "processing_error") {
    return detail ? `CSV could not be parsed: ${normalizeErrorMessage(detail)}` : "CSV could not be parsed.";
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
      ? "The Command Center is using the established behavior baseline."
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
    ["cognition_ready", "saving_result"].includes(jobStatus) ? job.progress_label : "The behavior baseline is being persisted for Command Center review.",
    "Completion will open the Command Center with the learned baseline.",
  ];
  return details[index] ?? stage;
}
