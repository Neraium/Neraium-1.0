from __future__ import annotations

from app.services.upload_lifecycle import (
    LEGACY_STAGE_DEFAULTS,
    canonical_stage_payload,
    infer_legacy_stage,
)


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
    return normalized


def normalize_upload_status_payload(payload: dict) -> dict:
    raw_status = str(payload.get("status", "")).upper()
    status = {
        "QUEUED": "PENDING",
        "QUEUE": "PENDING",
        "FAILED": "FAILED",
        "FAILURE": "FAILED",
    }.get(raw_status, raw_status)
    normalized = dict(payload)
    normalized["status"] = status
    normalized.setdefault("job_id", payload.get("job_id"))
    normalized.setdefault("percent", int(payload.get("progress", payload.get("percent", 0)) or 0))
    normalized.setdefault("progress", int(payload.get("percent", payload.get("progress", 0)) or 0))
    if status in {"RUNNING_SII", "PROCESSING", "PENDING", "QUEUED"}:
        normalized.setdefault("message", "Telemetry batch processing in progress.")
    if status == "COMPLETE":
        artifacts = payload.get("sii_completion_artifacts") or (payload.get("result_summary") or {}).get("sii_completion_artifacts") or {}
        sii_completed = bool(payload.get("sii_completed") or (payload.get("result_summary") or {}).get("sii_completed"))
        requires_contract_enforcement = "result_summary" in payload or "result_available" in payload
        if requires_contract_enforcement and (not sii_completed or not artifacts):
            normalized["status"] = "FAILED"
            normalized["sii_completed"] = False
            normalized["error_type"] = "sii_completion_missing"
            normalized["error"] = "sii_completion_missing"
            normalized["message"] = "SII completion artifacts are missing."
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
