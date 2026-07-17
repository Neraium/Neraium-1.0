from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.services import upload_jobs
from app.services.analysis_result_contract import empty_analysis_result, ensure_analysis_result
from app.services.runtime_db import (
    queue_metrics,
    queue_operational_metrics,
    read_upload_queue_job,
    upload_duration_samples,
)
from app.services.system_interpretation import build_system_interpretation
from app.services.upload_lifecycle import COMPLETE_STATES, PROCESSING_STATES
from app.services.upload_persistence import read_upload_history
from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE
from app.services.upload_state import (
    build_empty_latest_upload_record,
    build_latest_upload_record,
    build_replay_payload_from_result,
    has_active_session_artifact,
)
from app.services.upload_state_repository import (
    read_latest_upload_record,
    read_upload_result_by_job_id,
    read_upload_status,
    resolve_upload_artifacts,
    reset_block_persisted_active,
    upload_state_backend,
)
from app.services.upload_status_contract import normalize_upload_status_payload

logger = logging.getLogger(__name__)

SESSION_STATE_EMPTY = "empty"
SESSION_STATE_QUEUED = "queued"
SESSION_STATE_PROCESSING = "processing"
SESSION_STATE_VERIFIED = "verified"
SESSION_STATE_RESTORED = "restored"
SESSION_STATE_STALE = "stale"
SESSION_STATE_ERROR = "error"

SESSION_SOURCE_MEMORY = "active_in_memory_session"
SESSION_SOURCE_PERSISTED = "persisted_canonical_current_upload"
SESSION_SOURCE_HISTORY = "historical_artifacts"
SESSION_SOURCE_EMPTY = "no_session_fallback"

VISIBLE_ERROR_STATUSES = {"failed", "error", "validation_error", "timeout", "cancelled", "not_found", "missing"}


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _lifecycle_log(*, event: str, upload_session_id: str | None, request_id: str | None, state: str, source: str, **extra: Any) -> None:
    fields = {
        "event": event,
        "upload_session_id": upload_session_id,
        "request_id": request_id,
        "state": state,
        "source": source,
        **extra,
    }
    logger.info("upload_session_event %s", " ".join(f"{key}={value}" for key, value in fields.items() if value is not None))


def _resolve_session_state(*, status: str, result: dict[str, Any] | None, source: str, summary: dict[str, Any] | None = None) -> str:
    normalized = str(status or "").strip().lower()
    if source == SESSION_SOURCE_EMPTY:
        return SESSION_STATE_EMPTY
    if source == SESSION_SOURCE_HISTORY:
        return SESSION_STATE_STALE
    if normalized in {"pending", "queued"}:
        return SESSION_STATE_QUEUED
    if normalized in PROCESSING_STATES or normalized in {"processing", "running_sii"}:
        return SESSION_STATE_PROCESSING
    if normalized in VISIBLE_ERROR_STATUSES or (summary or {}).get("error") or (result or {}).get("error"):
        return SESSION_STATE_ERROR
    if source == SESSION_SOURCE_PERSISTED:
        return SESSION_STATE_RESTORED
    if isinstance(result, dict):
        return SESSION_STATE_VERIFIED
    return SESSION_STATE_STALE


def _analysis_completed(result: dict[str, Any] | None, analysis_result: dict[str, Any] | None = None) -> bool:
    if not isinstance(result, dict):
        return False
    candidate = analysis_result if isinstance(analysis_result, dict) else ensure_analysis_result(result)
    status = str(candidate.get("status") or "").strip().lower()
    return bool(
        status in {"complete", "completed", "ready"}
        or result.get("sii_completed") is True
        or (result.get("processing_trace") or {}).get("sii_completed") is True
    )


def _merge_completed_result_fields(status_payload: dict[str, Any], result_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result_payload, dict):
        return status_payload
    normalized = dict(status_payload or {})
    analysis_result = ensure_analysis_result(result_payload)
    analysis_completed = _analysis_completed(result_payload, analysis_result)
    raw_status = str(status_payload.get("status") or "").strip().upper()
    if analysis_completed:
        normalized["result_available"] = True
        normalized["first_usable_available"] = True
        normalized["sii_completed"] = True
        if raw_status in {"COMPLETE", "COMPLETED", "SUCCESS"}:
            normalized["status"] = "COMPLETE"
            normalized["processing_state"] = "complete"
            normalized["percent"] = 100
            normalized["progress"] = 100
            normalized["error"] = None
            normalized["error_type"] = None
            normalized["message"] = normalized.get("message") or "Analysis ready."
            normalized["progress_label"] = normalized.get("progress_label") or "Analysis ready."
    normalized["analysis_result"] = analysis_result
    if isinstance(result_payload.get("sii_completion_artifacts"), dict):
        normalized["sii_completion_artifacts"] = dict(result_payload["sii_completion_artifacts"])
    normalized["sii_reliable_enough_to_show"] = bool(result_payload.get("sii_reliable_enough_to_show"))

    evidence_persisted = bool(
        normalized.get("evidence_persisted")
        or (result_payload.get("evidence_persistence") or {}).get("persisted")
    )
    normalized["evidence_persisted"] = evidence_persisted
    if isinstance(result_payload.get("evidence_persistence"), dict):
        normalized["evidence_persistence"] = dict(result_payload["evidence_persistence"])
    if isinstance(result_payload.get("report_finalization"), dict):
        normalized["report_finalization"] = dict(result_payload["report_finalization"])
    return normalized


def _with_worker_visibility(payload: dict[str, Any], job_id: str | None) -> dict[str, Any]:
    if not job_id:
        return payload
    enriched = dict(payload or {})
    now = datetime.now(timezone.utc)
    enriched["status_checked_at"] = now.isoformat()
    queue_entry = read_upload_queue_job(str(job_id))
    queue_position = queue_entry.get("queue_position") if isinstance(queue_entry, dict) else None
    enriched["queue_position"] = int(queue_position) if isinstance(queue_position, int) else None

    created_at = _parse_iso((queue_entry or {}).get("created_at") if isinstance(queue_entry, dict) else None)
    enriched["queued_seconds"] = max(0, int((now - created_at).total_seconds())) if created_at else None

    payload_last_seen = _parse_iso(enriched.get("worker_last_seen_at"))
    last_seen = _parse_iso((queue_entry or {}).get("updated_at") if isinstance(queue_entry, dict) else None) or payload_last_seen
    worker_last_seen_at = last_seen.isoformat() if last_seen else None
    enriched["worker_last_seen_at"] = worker_last_seen_at

    if str(enriched.get("worker_state") or "").lower() == "running" and worker_last_seen_at:
        enriched["worker_state"] = "running"
        return enriched

    state = "unknown"
    status_text = str(enriched.get("status") or "").upper()
    processing_state = str(enriched.get("processing_state") or "").lower()
    queue_status = str((queue_entry or {}).get("status") or "").lower() if isinstance(queue_entry, dict) else ""

    if status_text == "PENDING" and processing_state == "queued":
        state = "starting"
    if queue_status == "processing" or status_text in {"PROCESSING", "RUNNING_SII"} or processing_state in PROCESSING_STATES:
        state = "running"
    if state == "starting" and enriched.get("queued_seconds") is not None and int(enriched["queued_seconds"]) > 15:
        state = "stalled" if not last_seen or (now - last_seen).total_seconds() > 15 else "starting"
    if not isinstance(queue_entry, dict):
        state = "unknown" if status_text not in {"PENDING", "PROCESSING", "RUNNING_SII"} else "starting"

    enriched["worker_state"] = state
    return enriched


def _build_history(include_persisted: bool, current_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not include_persisted:
        return []
    return [
        item
        for item in read_upload_history(
            UPLOAD_RUNTIME_STATE.runtime_dir,
            limit=20,
            current_result=current_result,
        )
        if isinstance(item, dict)
    ]


def _empty_response(*, include_persisted: bool, request_id: str | None) -> dict[str, Any]:
    record = build_empty_latest_upload_record()
    snapshot = {
        "state_backend": upload_state_backend(),
        "session_state": SESSION_STATE_EMPTY,
        "session_source": SESSION_SOURCE_EMPTY,
        "upload_session_id": None,
        "request_id": request_id,
        "source": "none",
        "result_source": None,
        "last_filename": None,
        "rows_processed": 0,
        "columns_detected": 0,
        "state_available": False,
        "status": "empty",
        "processing_state": "empty",
        "result_available": False,
        "sii_completed": False,
        "replay_ready": False,
        "replay_frame_count": 0,
        "latest_replay_frames": 0,
        "replay_source": "empty",
        "job_id": None,
        "run_id": None,
        "upload_id": None,
        "traceability": {},
        "current_upload": record,
        "metrics": session_metrics_snapshot(),
        "analysis_result": empty_analysis_result(status="empty", message="No active upload session."),
    }
    _lifecycle_log(
        event="latest_session_resolved",
        upload_session_id=None,
        request_id=request_id,
        state=SESSION_STATE_EMPTY,
        source=SESSION_SOURCE_EMPTY,
    )
    return {
        "snapshot": snapshot,
        "current_upload": record,
        "current_result": None,
        "latest_result": None,
        "latestResult": None,
        "analysis_result": snapshot["analysis_result"],
        "summary": {},
        "history": [] if not include_persisted else [],
        "adaptive_learning": {},
        "state_backend": upload_state_backend(),
        "session_state": SESSION_STATE_EMPTY,
        "session_source": SESSION_SOURCE_EMPTY,
        "upload_session_id": None,
        "request_id": request_id,
        "system_interpretation": build_system_interpretation(None, None, snapshot, []),
        **snapshot,
    }


def _record_from_history(history_entry: dict[str, Any]) -> dict[str, Any]:
    job_id = str(history_entry.get("job_id") or "").strip() or None
    result = read_upload_result_by_job_id(job_id) if job_id else None
    record = build_latest_upload_record(
        summary={**history_entry, "status": "COMPLETE", "processing_state": "complete"},
        result=result,
        status="stale",
        message="Historical upload artifacts found without an active session.",
    )
    record["session_scope"] = {**record.get("session_scope", {}), "active": False, "status": "stale"}
    return record


def resolve_latest_upload_session(*, include_persisted: int | bool = True, request_id: str | None = None) -> dict[str, Any]:
    use_persisted = bool(include_persisted)
    state_backend = upload_state_backend()
    if reset_block_persisted_active():
        return _empty_response(include_persisted=use_persisted, request_id=request_id)

    canonical = read_latest_upload_record() if use_persisted else build_empty_latest_upload_record()
    if state_backend == "local" and use_persisted and not (UPLOAD_RUNTIME_STATE.runtime_dir / "latest_upload.json").exists():
        canonical = build_empty_latest_upload_record()
    if not isinstance(canonical, dict):
        canonical = build_empty_latest_upload_record()

    summary = canonical.get("summary") if isinstance(canonical.get("summary"), dict) else {}
    canonical_job_id = str(canonical.get("job_id") or summary.get("job_id") or "").strip() or None

    memory_summary = read_upload_status(canonical_job_id) if canonical_job_id else None
    memory_result = read_upload_result_by_job_id(canonical_job_id) if canonical_job_id else None
    persisted_result = canonical.get("result") if isinstance(canonical.get("result"), dict) else None
    artifacts = resolve_upload_artifacts(canonical_job_id) if canonical_job_id else {}
    active_result = artifacts.get("active_result") if isinstance(artifacts.get("active_result"), dict) else None
    history = _build_history(use_persisted, active_result or persisted_result or memory_result)

    source = SESSION_SOURCE_EMPTY
    working_record = canonical
    result = None
    working_summary = summary

    if isinstance(memory_summary, dict):
        source = SESSION_SOURCE_MEMORY
        working_summary = memory_summary
        if isinstance(active_result, dict):
            result = active_result
        elif isinstance(memory_result, dict) and has_active_session_artifact(memory_result, job_id=canonical_job_id):
            result = memory_result
        elif isinstance(persisted_result, dict) and has_active_session_artifact(persisted_result, job_id=canonical_job_id):
            result = persisted_result
        working_record = build_latest_upload_record(summary=working_summary, result=result)
    elif canonical_job_id and (isinstance(persisted_result, dict) or isinstance(summary, dict) and summary):
        source = SESSION_SOURCE_PERSISTED
        result = persisted_result if isinstance(persisted_result, dict) else None
        working_record = canonical
    elif history:
        source = SESSION_SOURCE_HISTORY
        working_record = _record_from_history(history[0])
        working_summary = working_record.get("summary") if isinstance(working_record.get("summary"), dict) else {}
        result = working_record.get("result") if isinstance(working_record.get("result"), dict) else None

    if source == SESSION_SOURCE_EMPTY:
        return _empty_response(include_persisted=use_persisted, request_id=request_id)

    working_job_id = str(
        working_record.get("job_id")
        or working_summary.get("job_id")
        or (result or {}).get("job_id")
        or ""
    ).strip() or None
    raw_status = str(
        working_record.get("status")
        or working_summary.get("processing_state")
        or working_summary.get("status")
        or ("complete" if result else "empty")
    ).strip().lower()
    session_state = _resolve_session_state(
        status=raw_status,
        result=result,
        source=source,
        summary=working_summary,
    )
    if session_state == SESSION_STATE_STALE and source != SESSION_SOURCE_HISTORY:
        source = SESSION_SOURCE_HISTORY

    if isinstance(result, dict):
        analysis_result = ensure_analysis_result(result)
        if result.get("analysis_result") != analysis_result:
            result = {**result, "analysis_result": analysis_result}
    else:
        analysis_result = empty_analysis_result(
            analysis_id=working_job_id,
            upload_id=working_job_id,
            source_file=(working_summary or {}).get("filename"),
            status=session_state if session_state in {SESSION_STATE_QUEUED, SESSION_STATE_PROCESSING} else "empty",
        )

    replay_payload = build_replay_payload_from_result(result, job_id=working_job_id)
    analysis_complete = _analysis_completed(result, analysis_result)
    traceability = working_record.get("traceability") if isinstance(working_record.get("traceability"), dict) else {}
    snapshot_status = "COMPLETE" if session_state in {SESSION_STATE_VERIFIED, SESSION_STATE_RESTORED, SESSION_STATE_STALE} and result else (
        working_summary.get("status") if isinstance(working_summary, dict) else raw_status or session_state
    )
    snapshot_processing_state = "complete" if snapshot_status == "COMPLETE" else raw_status or session_state
    resolved_result_source = (
        (result or {}).get("result_source")
        or working_summary.get("result_source")
        or working_summary.get("upload_result_source")
    )
    snapshot = {
        **(working_summary if isinstance(working_summary, dict) else {}),
        "state_backend": state_backend,
        "session_state": session_state,
        "session_source": source,
        "upload_session_id": working_job_id,
        "request_id": request_id,
        "source": "rest_poll" if resolved_result_source == "rest_poll" else ("uploaded" if result else ("processing" if session_state in {SESSION_STATE_QUEUED, SESSION_STATE_PROCESSING} else "history")),
        "result_source": resolved_result_source,
        "last_filename": (result or {}).get("filename") or working_summary.get("filename"),
        "rows_processed": (result or {}).get("row_count") or working_summary.get("rows_processed") or working_summary.get("row_count") or 0,
        "columns_detected": (result or {}).get("column_count") or working_summary.get("columns_detected") or working_summary.get("column_count") or 0,
        "state_available": isinstance(result, dict),
        "status": snapshot_status,
        "processing_state": snapshot_processing_state,
        "result_available": isinstance(result, dict),
        "first_usable_available": analysis_complete if result else bool((working_summary or {}).get("first_usable_available")),
        "sii_completed": analysis_complete if result else bool((working_summary or {}).get("sii_completed")),
        "replay_ready": bool(replay_payload.get("timeline")),
        "replay_frame_count": int(replay_payload.get("frame_count") or 0),
        "latest_replay_frames": int(replay_payload.get("frame_count") or 0),
        "replay_source": replay_payload.get("source") or "empty",
        "job_id": working_job_id,
        "run_id": working_record.get("run_id") or working_summary.get("run_id") or (result or {}).get("run_id"),
        "upload_id": working_record.get("upload_id") or working_summary.get("upload_id") or (result or {}).get("upload_id"),
        "traceability": traceability,
        "current_upload": working_record,
        "metrics": session_metrics_snapshot(current_state=session_state),
        "analysis_result": analysis_result,
    }
    system_interpretation = build_system_interpretation(
        result if isinstance(result, dict) else None,
        working_summary if isinstance(working_summary, dict) else None,
        snapshot,
        replay_payload.get("timeline") if isinstance(replay_payload.get("timeline"), list) else [],
    )
    payload = {
        "snapshot": snapshot,
        "current_upload": working_record,
        "current_result": result,
        "latest_result": result,
        "latestResult": result,
        "analysis_result": analysis_result,
        "summary": working_summary if isinstance(working_summary, dict) else {},
        "history": history if use_persisted else [],
        "adaptive_learning": {},
        "state_backend": state_backend,
        "session_state": session_state,
        "session_source": source,
        "upload_session_id": working_job_id,
        "request_id": request_id,
        "system_interpretation": system_interpretation,
        **snapshot,
    }
    _lifecycle_log(
        event="latest_session_resolved",
        upload_session_id=working_job_id,
        request_id=request_id,
        state=session_state,
        source=source,
    )
    return payload


def resolve_upload_status(job_id: str, *, request_id: str | None = None) -> dict[str, Any]:
    requested_id = str(job_id or "").strip()
    if not requested_id:
        payload = {
            "job_id": None,
            "status": "NOT_FOUND",
            "processing_state": "missing",
            "session_state": SESSION_STATE_EMPTY,
            "session_source": SESSION_SOURCE_EMPTY,
            "upload_session_id": None,
            "request_id": request_id,
            "message": "Upload session expired or was not found.",
            "state_backend": upload_state_backend(),
            "analysis_result": empty_analysis_result(
                analysis_id=requested_id or None,
                upload_id=requested_id or None,
                status="missing",
                message="Upload session expired or was not found.",
                errors=["upload_session_missing"],
            ),
        }
        return payload

    current = resolve_latest_upload_session(include_persisted=True, request_id=request_id)
    current_job_id = str(current.get("upload_session_id") or "").strip()
    current_snapshot = current.get("snapshot") if isinstance(current.get("snapshot"), dict) else {}
    status_payload = read_upload_status(requested_id) or upload_jobs.read_upload_status(requested_id)
    result_payload = read_upload_result_by_job_id(requested_id)
    if not isinstance(status_payload, dict) and requested_id == current_job_id and isinstance(current_snapshot, dict) and current_snapshot:
        status_payload = dict(current_snapshot)

    if isinstance(status_payload, dict):
        normalized = normalize_upload_status_payload(status_payload)
        if isinstance(result_payload, dict):
            normalized = _merge_completed_result_fields(normalized, result_payload)
        elif str(normalized.get("status") or "").upper() == "FAILED":
            normalized["analysis_result"] = empty_analysis_result(
                analysis_id=requested_id,
                upload_id=requested_id,
                source_file=normalized.get("filename"),
                status="failed",
                message=normalized.get("message"),
                errors=[str(normalized.get("error") or normalized.get("error_type") or "analysis failed")],
            )
        else:
            normalized["analysis_result"] = empty_analysis_result(
                analysis_id=requested_id,
                upload_id=requested_id,
                source_file=normalized.get("filename"),
                status=str(normalized.get("processing_state") or normalized.get("status") or "processing").lower(),
            )
        session_scope = normalized.get("session_scope") if isinstance(normalized.get("session_scope"), dict) else {}
        normalized_status = str(normalized.get("processing_state") or normalized.get("status") or "").lower()
        terminal_status = normalized_status in {"complete", "completed", "failed", "cancelled", "timeout"}
        is_active_session = requested_id == current_job_id or (session_scope.get("active") is True and not terminal_status)
        session_source = SESSION_SOURCE_MEMORY if is_active_session else SESSION_SOURCE_HISTORY
        state = _resolve_session_state(
            status=str(normalized.get("processing_state") or normalized.get("status") or ""),
            result=result_payload if isinstance(result_payload, dict) else None,
            source=session_source,
            summary=normalized,
        )
        normalized.update(
            {
                "session_state": state,
                "session_source": session_source,
                "upload_session_id": requested_id,
                "request_id": request_id,
                "state_backend": upload_state_backend(),
            }
        )
        return _with_worker_visibility(normalized, requested_id)

    if isinstance(result_payload, dict):
        replay = build_replay_payload_from_result(result_payload, job_id=requested_id)
        payload = {
            "job_id": requested_id,
            "status_url": f"/api/data/upload-status/{requested_id}",
            "status": "COMPLETE",
            "processing_state": "complete",
            "percent": 100,
            "progress": 100,
            "result_available": True,
            "first_usable_available": True,
            "sii_completed": True,
            "replay_ready": bool(replay.get("timeline")),
            "replay_frame_count": int(replay.get("frame_count") or 0),
            "latest_replay_frames": int(replay.get("frame_count") or 0),
            "replay_source": replay.get("source") or "persisted",
            "last_processed_at": result_payload.get("last_processed_at") or result_payload.get("completed_at"),
            "filename": result_payload.get("filename"),
            "row_count": result_payload.get("row_count", 0),
            "column_count": result_payload.get("column_count", 0),
            "rows_processed": result_payload.get("row_count", 0),
            "columns_detected": result_payload.get("column_count", 0),
            "progress_label": "Analysis ready.",
            "message": "Analysis ready.",
            "job_state": "completed",
            "terminal": True,
            "sii_completion_artifacts": result_payload.get("sii_completion_artifacts", {}),
            "error": None,
            "state_backend": upload_state_backend(),
            "analysis_result": ensure_analysis_result(result_payload),
            "session_state": SESSION_STATE_VERIFIED if requested_id == current_job_id else SESSION_STATE_STALE,
            "session_source": SESSION_SOURCE_MEMORY if requested_id == current_job_id else SESSION_SOURCE_HISTORY,
            "upload_session_id": requested_id,
            "request_id": request_id,
        }
        return _with_worker_visibility(payload, requested_id)

    payload = {
        "job_id": requested_id,
        "status": "NOT_FOUND",
        "processing_state": "missing",
        "percent": 0,
        "progress": 0,
        "replay_ready": False,
        "replay_frame_count": 0,
        "result_available": False,
        "error_type": "upload_session_missing",
        "error": "upload_session_missing",
        "message": "Upload session expired or was not found.",
        "state_backend": upload_state_backend(),
        "analysis_result": empty_analysis_result(
            analysis_id=requested_id or None,
            upload_id=requested_id or None,
            status="missing",
            message="Upload session expired or was not found.",
            errors=["upload_session_missing"],
        ),
        "session_state": SESSION_STATE_EMPTY,
        "session_source": SESSION_SOURCE_EMPTY,
        "upload_session_id": requested_id,
        "request_id": request_id,
    }
    return _with_worker_visibility(payload, requested_id)


def session_metrics_snapshot(*, current_state: str | None = None) -> dict[str, Any]:
    durations = upload_duration_samples(limit=200)
    average_latency = round(sum(durations) / len(durations), 2) if durations else None
    percentile_95 = None
    if durations:
        ordered = sorted(durations)
        index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * 0.95))))
        percentile_95 = round(float(ordered[index]), 2)
    try:
        queue_depth = queue_metrics()
    except Exception:
        queue_depth = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    try:
        operational_metrics = queue_operational_metrics()
    except Exception:
        operational_metrics = {}
    return {
        "queue_depth": queue_depth,
        "queue_operational_metrics": operational_metrics,
        "upload_failures": int(queue_depth.get("failed", 0)),
        "analysis_latency_seconds_avg": average_latency,
        "analysis_latency_seconds_p95": percentile_95,
        "stale_sessions": 1 if current_state == SESSION_STATE_STALE else 0,
        "upload_state_problems": 1 if current_state in {SESSION_STATE_STALE, SESSION_STATE_ERROR} else 0,
    }

