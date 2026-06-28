from __future__ import annotations

from typing import Any


LEGACY_STAGE_DEFAULTS: dict[str, tuple[int, str]] = {
    "queued": (5, "Worker starting..."),
    "accepted": (10, "Validating CSV..."),
    "reading_csv": (10, "Validating CSV..."),
    "parsing_telemetry": (20, "Normalizing telemetry..."),
    "detecting_schema_signals": (35, "Validating CSV..."),
    "cleaning_imputing_data": (45, "Normalizing telemetry..."),
    "profiling_data_quality": (55, "Normalizing telemetry..."),
    "building_baseline": (60, "Identifying systems..."),
    "scoring_drift_relationships": (72, "Mapping relationships..."),
    "building_fingerprint": (84, "Building fingerprint..."),
    "generating_findings_evidence": (90, "Generating insights..."),
    "writing_result_replay": (95, "Saving result..."),
    "building_relationship_baselines": (65, "Building baseline..."),
    "scoring_relationship_drift": (75, "Scoring operating changes..."),
    "building_propagation_model": (85, "Preparing findings..."),
    "generating_system_interpretation": (95, "Writing result and replay..."),
    "partial_complete": (95, "Writing result and replay..."),
    "complete": (100, "Analysis ready."),
    "failed": (100, "Upload failed."),
}

CANONICAL_STAGE_BY_LEGACY_STAGE = {
    "accepted": "accepted",
    "queued": "queued",
    "reading_csv": "accepted",
    "parsing_telemetry": "parsing",
    "detecting_schema_signals": "validating_schema",
    "cleaning_imputing_data": "processing",
    "profiling_data_quality": "processing",
    "building_baseline": "baseline_modeling",
    "scoring_drift_relationships": "structural_scoring",
    "building_fingerprint": "building_fingerprint",
    "generating_findings_evidence": "writing_state",
    "writing_result_replay": "generating_replay",
    "building_relationship_baselines": "baseline_modeling",
    "scoring_relationship_drift": "structural_scoring",
    "building_propagation_model": "generating_replay",
    "generating_system_interpretation": "writing_state",
    "partial_complete": "cognition_ready",
    "complete": "complete",
    "failed": "failed",
}

CANONICAL_STAGE_LABELS = {
    "idle": "Awaiting file selection.",
    "validated": "Telemetry export validated.",
    "uploading": "Uploading telemetry batch.",
    "accepted": "Validating CSV...",
    "queued": "Worker starting...",
    "validating_schema": "Validating CSV...",
    "parsing": "Normalizing telemetry...",
    "baseline_modeling": "Identifying systems...",
    "processing": "Normalizing telemetry...",
    "structural_scoring": "Mapping relationships...",
    "building_fingerprint": "Building fingerprint...",
    "cognition_ready": "Saving result...",
    "generating_replay": "Saving result...",
    "writing_state": "Generating insights...",
    "complete": "Analysis ready.",
    "cancelled": "Analysis cancelled.",
    "timeout": "Analysis timed out.",
    "failed": "Upload failed.",
    "error": "Upload failed.",
    "validation_error": "Validation needs attention.",
}

CANONICAL_STAGE_PROGRESS = {
    "idle": 0,
    "validated": 3,
    "uploading": 12,
    "accepted": 10,
    "queued": 5,
    "validating_schema": 35,
    "parsing": 20,
    "baseline_modeling": 60,
    "processing": 55,
    "structural_scoring": 72,
    "building_fingerprint": 84,
    "cognition_ready": 95,
    "generating_replay": 95,
    "writing_state": 90,
    "complete": 100,
    "cancelled": 100,
    "timeout": 100,
    "failed": 100,
    "error": 100,
    "validation_error": 100,
}

PROCESSING_STATES = {
    "queued",
    "pending",
    "processing",
    "accepted",
    "reading_csv",
    "parsing_telemetry",
    "detecting_schema_signals",
    "cleaning_imputing_data",
    "profiling_data_quality",
    "building_baseline",
    "scoring_drift_relationships",
    "building_fingerprint",
    "generating_findings_evidence",
    "writing_result_replay",
    "building_relationship_baselines",
    "scoring_relationship_drift",
    "building_propagation_model",
    "generating_system_interpretation",
}
COMPLETE_STATES = {"complete", "partial_complete", "active"}
ACTIVE_UPLOAD_STATUSES = PROCESSING_STATES | COMPLETE_STATES | {"active"}
VISIBLE_UPLOAD_STATES = ACTIVE_UPLOAD_STATUSES | {"failed"}


def canonical_stage_for(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "idle"
    aliases = {
        "idle": "idle",
        "validated": "validated",
        "uploading": "uploading",
        "upload_started": "uploading",
        "accepted": "accepted",
        "queued": "queued",
        "queue": "queued",
        "pending": "queued",
        "validating_schema": "validating_schema",
        "detecting_schema_signals": "validating_schema",
        "parsing": "parsing",
        "reading_csv": "accepted",
        "baseline_modeling": "baseline_modeling",
        "building_baseline": "baseline_modeling",
        "cleaning_imputing_data": "processing",
        "profiling_data_quality": "processing",
        "processing": "processing",
        "running": "processing",
        "running_sii": "structural_scoring",
        "structural_scoring": "structural_scoring",
        "scoring_drift_relationships": "structural_scoring",
        "building_fingerprint": "building_fingerprint",
        "cognition_ready": "cognition_ready",
        "generating_replay": "generating_replay",
        "generating_evidence": "writing_state",
        "generating_findings_evidence": "writing_state",
        "writing_result_replay": "generating_replay",
        "writing_state": "writing_state",
        "complete": "complete",
        "completed": "complete",
        "success": "complete",
        "cancelled": "cancelled",
        "timeout": "timeout",
        "failed": "failed",
        "failure": "failed",
        "error": "error",
        "validation_error": "validation_error",
        "not_found": "error",
        "missing": "error",
    }
    if raw in aliases:
        return aliases[raw]
    if raw in CANONICAL_STAGE_BY_LEGACY_STAGE:
        return CANONICAL_STAGE_BY_LEGACY_STAGE[raw]
    return raw


def infer_legacy_stage(payload: dict[str, Any], normalized_status: str) -> str:
    explicit = str(payload.get("propagation_stage") or "").strip().lower()
    if explicit:
        return explicit
    processing_state = str(payload.get("processing_state") or "").strip().lower()
    if processing_state in LEGACY_STAGE_DEFAULTS:
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


def canonical_stage_payload(
    *,
    legacy_stage: str | None = None,
    status: str | None = None,
    progress: Any = None,
    label: str | None = None,
) -> dict[str, Any]:
    normalized_legacy = str(legacy_stage or "").strip().lower()
    canonical_stage = canonical_stage_for(normalized_legacy or status)
    default_progress = CANONICAL_STAGE_PROGRESS.get(canonical_stage, 0)
    if progress is None:
        progress = default_progress
    try:
        normalized_progress = int(max(0, min(100, float(progress))))
    except (TypeError, ValueError):
        normalized_progress = default_progress
    return {
        "contract_stage": canonical_stage,
        "contract_progress": normalized_progress,
        "contract_label": str(label or CANONICAL_STAGE_LABELS.get(canonical_stage, "Telemetry batch processing in progress.")),
    }
