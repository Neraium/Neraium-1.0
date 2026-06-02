from __future__ import annotations


_PROPAGATION_STAGE_DEFAULTS = {
    "accepted": (5, "Upload received."),
    "queued": (10, "Queued."),
    "parsing_telemetry": (20, "Parsing telemetry."),
    "building_relationship_baselines": (40, "Building relationship baselines."),
    "scoring_relationship_drift": (60, "Scoring relationship drift."),
    "building_propagation_model": (80, "Building propagation model."),
    "generating_system_interpretation": (90, "Generating interpretation."),
    "complete": (100, "Complete."),
}


def _infer_propagation_stage(payload: dict, normalized_status: str) -> str:
    explicit = str(payload.get("propagation_stage") or "").strip().lower()
    if explicit:
        return explicit
    processing_state = str(payload.get("processing_state") or "").strip().lower()
    if processing_state in _PROPAGATION_STAGE_DEFAULTS:
        return processing_state
    message = f"{payload.get('progress_label') or ''} {payload.get('message') or ''}".lower()
    if normalized_status == "COMPLETE":
        return "complete"
    if "baseline" in message:
        return "building_relationship_baselines"
    if "drift" in message or "scoring" in message:
        return "scoring_relationship_drift"
    if "propagation" in message or "replay" in message:
        return "building_propagation_model"
    if "interpretation" in message or "cognition" in message or "writing" in message:
        return "generating_system_interpretation"
    if "parsing" in message:
        return "parsing_telemetry"
    if normalized_status in {"PENDING", "QUEUED"}:
        return "queued"
    if normalized_status in {"PROCESSING", "RUNNING_SII"}:
        return "parsing_telemetry"
    return "queued"


def _with_propagation_fields(normalized: dict, raw_payload: dict, normalized_status: str) -> dict:
    stage = _infer_propagation_stage(raw_payload, normalized_status)
    default_progress, default_label = _PROPAGATION_STAGE_DEFAULTS.get(stage, (0, "Processing telemetry."))
    backend_progress = normalized.get("percent", normalized.get("progress", default_progress))
    try:
        backend_progress = int(max(0, min(100, float(backend_progress))))
    except (TypeError, ValueError):
        backend_progress = default_progress
    if normalized_status == "COMPLETE":
        backend_progress = 100
        stage = "complete"
        default_label = _PROPAGATION_STAGE_DEFAULTS["complete"][1]
    normalized["propagation_stage"] = str(raw_payload.get("propagation_stage") or stage)
    explicit_progress = raw_payload.get("propagation_progress")
    if explicit_progress is None:
        normalized["propagation_progress"] = int(max(default_progress, backend_progress))
    else:
        normalized["propagation_progress"] = int(max(0, min(100, float(explicit_progress))))
    normalized["propagation_label"] = str(raw_payload.get("propagation_label") or default_label)
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
        normalized.setdefault("progress_label", "Telemetry processing complete.")
        normalized.setdefault("message", "Telemetry processing complete.")
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
