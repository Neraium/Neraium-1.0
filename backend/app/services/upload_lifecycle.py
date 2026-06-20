from __future__ import annotations

from typing import Any


LEGACY_STAGE_DEFAULTS: dict[str, tuple[int, str]] = {
    "accepted": (5, "Upload received."),
    "queued": (10, "Queued."),
    "parsing_telemetry": (20, "Parsing telemetry."),
    "building_relationship_baselines": (40, "Building relationship baselines."),
    "scoring_relationship_drift": (60, "Scoring relationship drift."),
    "building_propagation_model": (80, "Building propagation model."),
    "generating_system_interpretation": (90, "Generating interpretation."),
    "partial_complete": (95, "Core upload artifacts available."),
    "complete": (100, "Complete."),
    "failed": (100, "Upload failed."),
}

CANONICAL_STAGE_BY_LEGACY_STAGE = {
    "accepted": "accepted",
    "queued": "queued",
    "parsing_telemetry": "parsing",
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
    "accepted": "Upload received.",
    "queued": "Queued.",
    "validating_schema": "Validating schema.",
    "parsing": "Parsing telemetry.",
    "baseline_modeling": "Learning reference behavior.",
    "processing": "Telemetry batch processing in progress.",
    "structural_scoring": "Scoring relationship drift.",
    "cognition_ready": "Core upload artifacts available.",
    "generating_replay": "Building propagation model.",
    "writing_state": "Generating interpretation.",
    "complete": "Telemetry processing complete.",
    "failed": "Upload failed.",
    "error": "Upload failed.",
    "validation_error": "Validation needs attention.",
}

CANONICAL_STAGE_PROGRESS = {
    "idle": 0,
    "validated": 3,
    "uploading": 12,
    "accepted": 18,
    "queued": 22,
    "validating_schema": 36,
    "parsing": 48,
    "baseline_modeling": 62,
    "processing": 70,
    "structural_scoring": 74,
    "cognition_ready": 90,
    "generating_replay": 94,
    "writing_state": 97,
    "complete": 100,
    "failed": 100,
    "error": 100,
    "validation_error": 100,
}

PROCESSING_STATES = {
    "queued",
    "pending",
    "processing",
    "parsing_telemetry",
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
        "parsing": "parsing",
        "baseline_modeling": "baseline_modeling",
        "processing": "processing",
        "running": "processing",
        "running_sii": "structural_scoring",
        "structural_scoring": "structural_scoring",
        "cognition_ready": "cognition_ready",
        "generating_replay": "generating_replay",
        "generating_evidence": "writing_state",
        "writing_state": "writing_state",
        "complete": "complete",
        "completed": "complete",
        "success": "complete",
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
