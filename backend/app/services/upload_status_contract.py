from __future__ import annotations

from app.services.upload_lifecycle import (
    LEGACY_STAGE_DEFAULTS,
    canonical_stage_payload,
    infer_legacy_stage,
)



REQUIRED_COMPLETION_ARTIFACTS = (
    "evidence_persisted",
    "relationships_persisted",
    "behavioral_structure_persisted",
    "baseline_persisted",
    "final_result_persisted",
    "terminal_backend_state_published",
)


def _truthy(value):
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _canonical_job_state(status: str, payload: dict) -> str:
    normalized = str(status or payload.get("status") or "").strip().upper()
    processing_state = str(payload.get("processing_state") or payload.get("contract_stage") or "").strip().lower()
    if normalized in {"COMPLETE", "COMPLETED", "SUCCESS"} or processing_state == "complete":
        artifacts = payload.get("sii_completion_artifacts") or (payload.get("result_summary") or {}).get("sii_completion_artifacts") or {}
        return "completed_compatibility" if _truthy(artifacts.get("compatibility_mode")) else "completed"
    if normalized in {"FAILED", "FAILURE", "ERROR", "TIMEOUT"} or processing_state in {"failed", "error", "timeout"}:
        return "failed"
    if normalized == "CANCELLED" or processing_state == "cancelled":
        return "cancelled"
    if normalized in {"PENDING", "QUEUED", "QUEUE"} or processing_state in {"queued", "pending"}:
        return "queued"
    return "processing"


def _completion_artifacts(payload: dict) -> dict:
    artifacts = payload.get("sii_completion_artifacts") or (payload.get("result_summary") or {}).get("sii_completion_artifacts") or {}
    return artifacts if isinstance(artifacts, dict) else {}


def _missing_completion_artifacts(payload: dict) -> list[str]:
    artifacts = _completion_artifacts(payload)
    return [key for key in REQUIRED_COMPLETION_ARTIFACTS if not _truthy(artifacts.get(key))]

def _with_propagation_fields(normalized: dict, raw_payload: dict, normalized_status: str) -> dict:
    stage = infer_legacy_stage(raw_payload, normalized_status)
    default_progress, default_label = LEGACY_STAGE_DEFAULTS.get(stage, (0, "Processing telemetry."))
    backend_progress = normalized.get("percent", normalized.get("progress", default_progress))
    try:
        backend_progress = int(max(0, min(100, float(backend_progress))))
    except (TypeError, ValueError):
        backend_progress = default_progress
    if normalized_status == "COMPLETE":
        backend_progress = 100
        stage = "complete"
        default_label = LEGACY_STAGE_DEFAULTS["complete"][1]
    normalized["propagation_stage"] = str(raw_payload.get("propagation_stage") or stage)
    raw_label = str(raw_payload.get("propagation_label") or "")
    if normalized_status == "COMPLETE" and raw_label.strip() in {"", "Complete.", "Complete"}:
        raw_label = "Analysis ready."
    explicit_progress = raw_payload.get("propagation_progress")
    if explicit_progress is None:
        normalized["propagation_progress"] = int(max(default_progress, backend_progress))
    else:
        normalized["propagation_progress"] = int(max(0, min(100, float(explicit_progress))))
    normalized["propagation_label"] = raw_label or str(default_label)
    normalized.update(
        canonical_stage_payload(
            legacy_stage=normalized["propagation_stage"],
            status=normalized.get("status"),
            progress=raw_payload.get("contract_progress", normalized["propagation_progress"]),
            label=raw_payload.get("contract_label") or normalized["propagation_label"],
        )
    )
    normalized["job_state"] = _canonical_job_state(normalized.get("status"), normalized)
    normalized["terminal"] = normalized["job_state"] in {"completed", "completed_compatibility", "failed", "cancelled"}
    return normalized


def normalize_upload_status_payload(payload: dict) -> dict:
    raw_status = str(payload.get("status", "")).upper()
    status = {
        "QUEUED": "PENDING",
        "QUEUE": "PENDING",
        "FAILED": "FAILED",
        "FAILURE": "FAILED",
        "CANCELLED": "CANCELLED",
        "TIMEOUT": "TIMEOUT",
    }.get(raw_status, raw_status)
    normalized = dict(payload)
    normalized["status"] = status
    normalized.setdefault("job_id", payload.get("job_id"))
    normalized.setdefault("percent", int(payload.get("progress", payload.get("percent", 0)) or 0))
    normalized.setdefault("progress", int(payload.get("percent", payload.get("progress", 0)) or 0))
    if status in {"RUNNING_SII", "PROCESSING", "PENDING", "QUEUED"}:
        normalized.setdefault("message", "Dataset analysis is in progress.")
    if status in {"TIMEOUT", "CANCELLED"}:
        normalized.setdefault("error", str(normalized.get("message") or status.title()))
        return _with_propagation_fields(normalized, payload, status)
    if status == "COMPLETE":
        artifacts = _completion_artifacts(payload)
        sii_completed = bool(payload.get("sii_completed") or (payload.get("result_summary") or {}).get("sii_completed"))
        requires_contract_enforcement = "result_summary" in payload or "result_available" in payload
        missing_artifacts = _missing_completion_artifacts(payload)
        if requires_contract_enforcement and (not sii_completed or missing_artifacts):
            normalized["status"] = "FAILED"
            normalized["sii_completed"] = False
            normalized["error_type"] = "sii_completion_missing"
            normalized["error"] = "sii_completion_missing"
            normalized["message"] = "Analysis could not save a complete result. Retry the analysis."
            return _with_propagation_fields(normalized, payload, "FAILED")
        if str(normalized.get("progress_label") or "").strip() in {"", "Complete.", "Complete", "Telemetry processing complete."}:
            normalized["progress_label"] = "Analysis ready."
        if str(normalized.get("message") or "").strip() in {"", "Complete.", "Complete", "Telemetry processing complete."}:
            normalized["message"] = "Analysis ready."
        normalized.setdefault("error", None)
        normalized.setdefault(
            "result_summary",
            {
                "job_id": normalized.get("job_id"),
                "filename": normalized.get("filename"),
                "rows_processed": normalized.get("rows_processed", normalized.get("row_count", 0)),
                "columns_detected": normalized.get("columns_detected", normalized.get("column_count", 0)),
                "runner_errors": [],
            },
        )
    return _with_propagation_fields(normalized, payload, normalized.get("status", status))
