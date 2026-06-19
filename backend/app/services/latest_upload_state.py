from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services import upload_jobs
from app.services.system_interpretation import build_system_interpretation
from app.services.upload_persistence import read_upload_history
from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE
from app.services.upload_state import build_empty_latest_upload_record, has_active_session_artifact
from app.services.upload_state_repository import (
    read_latest_upload_record,
    reset_block_persisted_active,
    resolve_upload_artifacts,
    upload_state_backend,
)

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


def extract_timeline(result: dict[str, Any] | None, job_id: str | None = None) -> list[dict[str, Any]]:
    replay = (
        (result or {}).get("replay_timeline")
        or ((result or {}).get("sii_intelligence") or {}).get("replay_timeline")
        or {}
    )
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    if timeline:
        return timeline
    fallback = upload_jobs.replay_payload(job_id)
    fallback_timeline = fallback.get("timeline", []) if isinstance(fallback, dict) else []
    return fallback_timeline if isinstance(fallback_timeline, list) else []


def _resolve_history(*, use_persisted: bool, canonical_job_id: str, has_result: bool, has_summary: bool, artifacts: dict[str, Any], summary: dict[str, Any]) -> list[dict[str, Any]]:
    if not (use_persisted and canonical_job_id and (has_result or has_summary)):
        return []

    history = [
        item
        for item in read_upload_history(
            UPLOAD_RUNTIME_STATE.runtime_dir,
            limit=20,
            current_result=artifacts.get("active_result") if isinstance(artifacts.get("active_result"), dict) else None,
        )
        if isinstance(item, dict)
    ]
    current_history = next((item for item in history if str(item.get("job_id") or "") == canonical_job_id), None)
    if current_history is None and summary:
        current_history = dict(summary)
    remaining = [item for item in history if str(item.get("job_id") or "") != canonical_job_id]
    return ([current_history] if current_history else []) + remaining


def resolve_latest_upload_payload(*, include_persisted: int | bool = True) -> dict[str, Any]:
    use_persisted = bool(include_persisted)
    state_backend = upload_state_backend()
    canonical = read_latest_upload_record() if use_persisted else build_empty_latest_upload_record()
    artifacts = resolve_upload_artifacts() if use_persisted else {}

    if state_backend == "local" and not (UPLOAD_RUNTIME_STATE.runtime_dir / "latest_upload.json").exists():
        canonical = build_empty_latest_upload_record()
        artifacts = {}
    if reset_block_persisted_active():
        canonical = build_empty_latest_upload_record()
        artifacts = {}
    if not isinstance(canonical, dict):
        canonical = build_empty_latest_upload_record()
        artifacts = {}

    summary = canonical.get("summary") if isinstance(canonical.get("summary"), dict) else {}
    record_result = canonical.get("result") if isinstance(canonical.get("result"), dict) else None
    active_result = artifacts.get("active_result") if isinstance(artifacts.get("active_result"), dict) else None
    canonical_record_job_id = str(canonical.get("job_id") or summary.get("job_id") or "").strip() or None

    persisted_result = None
    if isinstance(record_result, dict):
        persisted_result_job_id = str(record_result.get("job_id") or canonical_record_job_id or "").strip()
        if persisted_result_job_id and (
            persisted_result_job_id == str(canonical_record_job_id or "").strip()
            or str(canonical.get("status") or summary.get("processing_state") or summary.get("status") or "").strip().lower() in COMPLETE_STATES
        ):
            persisted_result = record_result

    result = active_result if isinstance(active_result, dict) else (
        record_result if has_active_session_artifact(record_result, job_id=canonical_record_job_id) else persisted_result
    )
    canonical_job_id = str(artifacts.get("job_id") or canonical.get("job_id") or summary.get("job_id") or (result or {}).get("job_id") or "").strip()
    canonical_status = str(canonical.get("status") or summary.get("processing_state") or summary.get("status") or "empty").strip().lower()

    has_result = bool(result) and has_active_session_artifact(result, job_id=canonical_job_id)
    has_summary = bool(summary) and (
        has_active_session_artifact(summary, job_id=canonical_job_id)
        or canonical_status in PROCESSING_STATES
        or canonical_status in COMPLETE_STATES
    )

    if canonical_status in COMPLETE_STATES and not has_result and not persisted_result:
        canonical = build_empty_latest_upload_record()
        summary = {}
        result = None
        canonical_job_id = ""
        canonical_status = "empty"
        has_summary = False
    elif not has_result and not has_summary:
        canonical = build_empty_latest_upload_record()
        summary = {}
        result = None
        canonical_job_id = ""
        canonical_status = "empty"

    history = _resolve_history(
        use_persisted=use_persisted,
        canonical_job_id=canonical_job_id,
        has_result=has_result,
        has_summary=has_summary,
        artifacts=artifacts,
        summary=summary,
    )

    frames = artifacts.get("replay", {}).get("timeline") if isinstance(artifacts.get("replay"), dict) else None
    if not isinstance(frames, list):
        frames = extract_timeline(result if isinstance(result, dict) else None, canonical_job_id or None)

    traceability = canonical.get("traceability") if isinstance(canonical.get("traceability"), dict) else {}
    state_available = bool(result)
    snapshot_status = "COMPLETE" if state_available else (summary.get("status") if isinstance(summary, dict) else canonical_status or "empty")
    snapshot_processing_state = "complete" if state_available else (summary.get("processing_state") if isinstance(summary, dict) else canonical_status or "empty")
    snapshot = {
        **(summary if isinstance(summary, dict) else {}),
        "state_backend": state_backend,
        "source": "uploaded" if state_available else ("processing" if canonical_job_id and canonical_status in PROCESSING_STATES else "none"),
        "last_filename": (result or {}).get("filename") or (summary.get("filename") if isinstance(summary, dict) else None),
        "rows_processed": (result or {}).get("row_count") or (summary.get("rows_processed") if isinstance(summary, dict) else 0) or (summary.get("row_count") if isinstance(summary, dict) else 0) or 0,
        "columns_detected": (result or {}).get("column_count") or (summary.get("columns_detected") if isinstance(summary, dict) else 0) or (summary.get("column_count") if isinstance(summary, dict) else 0) or 0,
        "state_available": state_available,
        "status": snapshot_status,
        "processing_state": snapshot_processing_state,
        "result_available": state_available,
        "sii_completed": bool((result or {}).get("sii_reliable_enough_to_show") is not False and state_available) if state_available else bool((summary or {}).get("sii_completed")),
        "replay_ready": bool(frames),
        "replay_frame_count": len(frames or []),
        "latest_replay_frames": len(frames or []),
        "replay_source": "persisted" if frames else "empty",
        "job_id": canonical_job_id or None,
        "run_id": str(canonical.get("run_id") or (summary.get("run_id") if isinstance(summary, dict) else "") or (result or {}).get("run_id") or canonical_job_id or "") or None,
        "upload_id": str(canonical.get("upload_id") or (summary.get("upload_id") if isinstance(summary, dict) else "") or (result or {}).get("upload_id") or canonical_job_id or "") or None,
        "traceability": traceability,
        "current_upload": canonical,
    }

    system_interpretation = (
        build_system_interpretation(
            result if isinstance(result, dict) else None,
            summary if isinstance(summary, dict) else None,
            snapshot,
            frames if isinstance(frames, list) else [],
        )
        if state_available or canonical_job_id
        else build_system_interpretation(None, None, {}, [])
    )

    return {
        "snapshot": snapshot,
        "current_upload": canonical,
        "current_result": result,
        "latest_result": result,
        "latestResult": result,
        "summary": summary if isinstance(summary, dict) else {},
        "history": history if state_available or canonical_job_id else [],
        "adaptive_learning": {},
        "state_backend": state_backend,
        "system_interpretation": system_interpretation,
        **snapshot,
    }
