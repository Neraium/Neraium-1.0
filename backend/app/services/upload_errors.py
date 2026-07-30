from __future__ import annotations

from typing import Any


UPLOAD_ERROR_DEFAULTS: dict[str, tuple[str, str, bool]] = {
    "upload_transfer_failed": (
        "The file could not be transferred. Check the connection and try again.",
        "upload_transfer",
        True,
    ),
    "auth_session_expired": (
        "Your session has expired. Sign in again, then retry the import.",
        "authentication",
        False,
    ),
    "dataset_record_creation_failed": (
        "The file was transferred, but the dataset record could not be created.",
        "dataset_creation",
        True,
    ),
    "file_storage_failed": (
        "The file could not be saved to secure storage.",
        "file_storage",
        True,
    ),
    "csv_parsing_failed": (
        "The CSV could not be parsed. Check its format and try again.",
        "csv_parsing",
        False,
    ),
    "validation_failed": (
        "The dataset did not pass validation. Check the file and try again.",
        "validation",
        False,
    ),
    "baseline_processing_failed": (
        "The dataset was imported, but baseline processing could not complete.",
        "baseline_processing",
        True,
    ),
    "relationship_learning_failed": (
        "The file was uploaded, but expected signal relationships could not be learned.",
        "relationship_learning",
        True,
    ),
    "result_persistence_failed": (
        "Processing finished, but the baseline result could not be made available.",
        "baseline_creation",
        True,
    ),
    "server_timeout": (
        "The server timed out while processing the dataset. Retry the import.",
        "server",
        True,
    ),
    "not_found": (
        "The requested endpoint, dataset, or uploaded object was not found.",
        "lookup",
        False,
    ),
    "file_too_large": (
        "File is larger than the supported upload limit.",
        "upload_transfer",
        False,
    ),
    "rate_limited": (
        "The import service is busy or rate limited. Retry shortly.",
        "server",
        True,
    ),
    "internal_processing_failure": (
        "The server could not complete dataset processing.",
        "baseline_processing",
        True,
    ),
    "server_unavailable": (
        "The import service is temporarily unavailable. Retry shortly.",
        "server",
        True,
    ),
    "unexpected_server_error": (
        "The server could not complete the import. Retry the import.",
        "unexpected",
        True,
    ),
}


LEGACY_UPLOAD_ERROR_CODES = {
    "auth": "auth_session_expired",
    "upload_session_missing": "not_found",
    "missing_job_id": "dataset_record_creation_failed",
    "upload_enqueue_failed": "dataset_record_creation_failed",
    "upload_queue_saturated": "rate_limited",
    "shared_upload_queue_not_configured": "server_unavailable",
    "large_upload_storage_unavailable": "file_storage_failed",
    "shared_upload_source_client_unavailable": "file_storage_failed",
    "object_storage_upload_failed": "upload_transfer_failed",
    "upload_not_complete": "upload_transfer_failed",
    "upload_size_mismatch": "upload_transfer_failed",
    "upload_etag_mismatch": "upload_transfer_failed",
    "missing_upload_file": "file_storage_failed",
    "upload_source_missing": "file_storage_failed",
    "csv_parse_error": "csv_parsing_failed",
    "unsupported_file_type": "validation_failed",
    "invalid_filename": "validation_failed",
    "invalid_workflow": "validation_failed",
    "active_behavioral_baseline_required": "validation_failed",
    "upload_too_large": "file_too_large",
    "validation_error": "validation_failed",
    "processing_timeout": "server_timeout",
    "upload_response_timeout": "server_timeout",
    "timeout": "server_timeout",
    "upload_rate_limited": "rate_limited",
    "upload_status_rate_limited": "rate_limited",
    "service_unavailable": "server_unavailable",
    "worker_start_failed": "server_unavailable",
    "processing_error": "baseline_processing_failed",
    "sii_processing_failure": "baseline_processing_failed",
    "upload_request_error": "unexpected_server_error",
}


PROCESSING_FAILURE_STAGES = {"import", "validation", "relationship_learning", "baseline_creation"}


def canonical_processing_failure_stage(stage: Any) -> str:
    normalized = str(stage or "").strip().lower()
    if normalized in PROCESSING_FAILURE_STAGES:
        return normalized
    if normalized in {
        "validation", "csv_parsing", "validating_schema", "baseline_validating",
        "baseline_quality_assessment", "parsing", "parsing_telemetry",
    }:
        return "validation"
    if normalized in {"relationship_learning", "baseline_relationship_learning"}:
        return "relationship_learning"
    if normalized in {
        "baseline_creation", "baseline_processing", "baseline_mode_identification",
        "baseline_model_fitting", "baseline_candidate_persistence", "processing_timeout",
        "saving_result", "persistence", "server",
    }:
        return "baseline_creation"
    return "import"


def canonical_upload_error_code(error_code: Any) -> str:
    normalized = str(error_code or "").strip().lower()
    if normalized in UPLOAD_ERROR_DEFAULTS:
        return normalized
    return LEGACY_UPLOAD_ERROR_CODES.get(normalized, "unexpected_server_error")


def build_upload_error_payload(
    error_code: Any,
    *,
    message: str | None = None,
    failed_stage: str | None = None,
    retryable: bool | None = None,
    legacy_error_type: str | None = None,
    job_id: str | None = None,
    dataset_id: str | None = None,
    request_id: str | None = None,
    technical_message: str | None = None,
    exception_type: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    code = canonical_upload_error_code(error_code)
    default_message, default_stage, default_retryable = UPLOAD_ERROR_DEFAULTS[code]
    safe_message = str(message or default_message).strip() or default_message
    legacy_stage = str(failed_stage or default_stage).strip() or default_stage
    stage = canonical_processing_failure_stage(legacy_stage)
    can_retry = default_retryable if retryable is None else bool(retryable)
    error_type = str(legacy_error_type or error_code or code).strip() or code
    technical = str(technical_message or error_type).strip() or error_type
    normalized_job_id = str(job_id or "").strip() or None
    normalized_dataset_id = str(dataset_id or "").strip() or None
    normalized_request_id = str(request_id or "").strip() or None
    details = {
        "code": code,
        "message": safe_message,
        "failed_stage": legacy_stage,
        "stage": stage,
        "retryable": can_retry,
    }
    return {
        "job_id": normalized_job_id,
        "jobId": normalized_job_id,
        "dataset_id": normalized_dataset_id,
        "datasetId": normalized_dataset_id,
        "request_id": normalized_request_id,
        "requestId": normalized_request_id,
        "status": "FAILED",
        "job_state": "failed",
        "processing_state": "failed",
        "message": safe_message,
        "error": safe_message,
        "error_type": error_type,
        "error_code": code,
        "errorCode": code,
        "failed_stage": legacy_stage,
        "stage": stage,
        "userMessage": safe_message,
        "technicalMessage": technical,
        "exception_type": exception_type,
        "retryable": can_retry,
        "error_details": details,
        **extra,
    }
