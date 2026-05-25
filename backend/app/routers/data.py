from __future__ import annotations

import logging
import threading
import asyncio
import json
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
import uuid
from datetime import datetime, timezone
import re

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from app.services import adaptive_learning
from app.services.evidence_store import read_evidence_run, upsert_evidence_run
from app.services import upload_jobs
from app.services.sii_runner import CORE_ENGINE, RUNNER_MODULE
from app.services.runtime_db import record_audit_event
from app.services.runtime_db import enqueue_upload_job
from app.services.runtime_db import queue_metrics as runtime_queue_metrics

router = APIRouter(prefix="/data", tags=["data"])
logger = logging.getLogger(__name__)
UPLOAD_JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)
_UPLOAD_STATUS_CACHE: dict[str, tuple[float, dict]] = {}
_LATEST_UPLOAD_CACHE: tuple[float, dict] | None = None


def _cache_get_status(job_id: str) -> dict | None:
    entry = _UPLOAD_STATUS_CACHE.get(str(job_id))
    if not entry:
        return None
    expires_at, payload = entry
    if time.monotonic() >= expires_at:
        _UPLOAD_STATUS_CACHE.pop(str(job_id), None)
        return None
    return dict(payload)


def _cache_set_status(job_id: str, payload: dict, ttl_seconds: float = 1.5) -> None:
    _UPLOAD_STATUS_CACHE[str(job_id)] = (time.monotonic() + max(0.2, float(ttl_seconds)), dict(payload or {}))


def _cache_get_latest() -> dict | None:
    global _LATEST_UPLOAD_CACHE
    if not _LATEST_UPLOAD_CACHE:
        return None
    expires_at, payload = _LATEST_UPLOAD_CACHE
    if time.monotonic() >= expires_at:
        _LATEST_UPLOAD_CACHE = None
        return None
    return dict(payload)


def _cache_set_latest(payload: dict, ttl_seconds: float = 2.0) -> None:
    global _LATEST_UPLOAD_CACHE
    _LATEST_UPLOAD_CACHE = (time.monotonic() + max(0.2, float(ttl_seconds)), dict(payload or {}))


def _clear_endpoint_caches() -> None:
    global _LATEST_UPLOAD_CACHE
    _UPLOAD_STATUS_CACHE.clear()
    _LATEST_UPLOAD_CACHE = None

def _extract_timeline(result: dict | None, job_id: str | None = None) -> list[dict]:
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


def _resolve_upload_status_payload(job_id: str, state_backend: str) -> dict:
    status = upload_jobs.read_upload_status(job_id)
    if status and str(status.get("status", "")).upper() in {"PENDING", "QUEUED", "PROCESSING"}:
        upload_jobs.process_next_queued_upload_job()
        status = upload_jobs.read_upload_status(job_id)
    if status:
        normalized = normalize_upload_status_payload(status)
        normalized.setdefault("state_backend", state_backend)
        return normalized
    latest_summary = upload_jobs.read_latest_upload_summary() or {}
    if str(latest_summary.get("job_id") or "") == str(job_id):
        normalized = normalize_upload_status_payload(latest_summary)
        normalized.setdefault("state_backend", state_backend)
        return normalized
    latest_result = upload_jobs.read_upload_result_by_job_id(job_id)
    if isinstance(latest_result, dict) and latest_result.get("job_id") == job_id:
        timeline = _extract_timeline(latest_result, job_id)
        return {
            "job_id": job_id,
            "status_url": f"/api/data/upload-status/{job_id}",
            "status": "COMPLETE",
            "processing_state": "complete",
            "percent": 100,
            "progress": 100,
            "result_available": True,
            "first_usable_available": True,
            "sii_completed": True,
            "replay_ready": len(timeline or []) > 0,
            "replay_frame_count": len(timeline or []),
            "latest_replay_frames": len(timeline or []),
            "replay_source": "persisted" if timeline else "unknown",
            "last_processed_at": latest_result.get("last_processed_at") or latest_result.get("completed_at"),
            "filename": latest_result.get("filename"),
            "row_count": latest_result.get("row_count", 0),
            "column_count": latest_result.get("column_count", 0),
            "rows_processed": latest_result.get("row_count", 0),
            "columns_detected": latest_result.get("column_count", 0),
            "progress_label": "Telemetry processing complete.",
            "message": "Telemetry processing complete.",
            "error": None,
            "state_backend": state_backend,
        }
    if UPLOAD_JOB_ID_PATTERN.match(str(job_id or "")):
        return {
            "job_id": job_id,
            "status_url": f"/api/data/upload-status/{job_id}",
            "status": "PENDING",
            "processing_state": "queued",
            "percent": 0,
            "progress": 0,
            "replay_ready": False,
            "replay_frame_count": 0,
            "result_available": False,
            "first_usable_available": False,
            "sii_completed": False,
            "message": "Upload accepted. Waiting for status propagation.",
            "state_backend": state_backend,
        }
    return {
        "job_id": job_id,
        "status": "NOT_FOUND",
        "processing_state": "missing",
        "percent": 0,
        "replay_ready": False,
        "replay_frame_count": 0,
        "result_available": False,
        "error_type": "upload_session_missing",
        "error": "upload_session_missing",
        "message": "Upload session expired or was not found.",
        "state_backend": state_backend,
    }


@router.post("/upload", status_code=202)
async def upload_data(request: Request, file: UploadFile = File(...)):
    content = await file.read()
    settings = request.app.state.settings
    filename = file.filename or "upload.csv"
    lowered = filename.lower()
    if not (lowered.endswith(".csv") or lowered.endswith(".json")):
        return JSONResponse(
            status_code=400,
            content={
                "status": "FAILED",
                "processing_state": "failed",
                "message": "Only .csv and .json telemetry files are supported.",
            },
        )
    if lowered.endswith(".csv") and not content.strip():
        return JSONResponse(
            status_code=400,
            content={
                "status": "FAILED",
                "processing_state": "failed",
                "message": "CSV file is empty.",
            },
        )
    max_size_bytes = int(getattr(settings, "max_upload_size_bytes", 250 * 1024 * 1024))
    if len(content) > max_size_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "status": "FAILED",
                "error_type": "upload_too_large",
                "message": f"Upload exceeds maximum allowed size of {max_size_bytes} bytes.",
            },
        )
    metrics = queue_metrics()
    if int(metrics.get("pending", 0)) >= int(getattr(settings, "max_pending_upload_jobs", 3)):
        return JSONResponse(
            status_code=503,
            headers={"retry-after": "30"},
            content={
                "status": "FAILED",
                "error_type": "upload_queue_saturated",
                "message": "Upload queue is saturated. Retry shortly.",
            },
        )
    
    content_type = (file.content_type or "").lower()
    auth_context = getattr(request.state, "auth_context", {})
    actor = (
        auth_context.get("auth_subject")
        or request.headers.get("X-Neraium-User")
        or request.headers.get("X-Authenticated-User")
        or request.headers.get("X-Forwarded-Email")
        or "anonymous"
    )
    try:
        job_id = uuid.uuid4().hex
        with NamedTemporaryFile(delete=False, suffix=Path(filename).suffix or ".csv") as temp:
            temp.write(content)
            temp_path = temp.name
        summary = {
            "job_id": job_id,
            "filename": filename,
            "status_url": f"/api/data/upload-status/{job_id}",
            "status": "PENDING",
            "processing_state": "queued",
            "percent": 0,
            "progress": 0,
            "message": "Upload accepted. Processing is queued.",
            "runner_used": False if str(getattr(settings, "process_role", "")).lower() == "api" else True,
            "runner_module": RUNNER_MODULE,
            "core_engine": CORE_ENGINE,
            "file_path": temp_path,
            "file_size_bytes": len(content),
            "content_type": content_type,
            "initiated_by": actor,
        }
        upload_jobs.write_job(summary)
        enqueue_upload_job(job_id)
        threading.Thread(target=upload_jobs.process_next_queued_upload_job, daemon=True).start()
        record_audit_event(
            actor=actor,
            action="upload.accepted",
            resource_type="upload_job",
            resource_id=str(job_id or "unknown"),
            request_id=auth_context.get("request_id"),
            detail={"filename": filename, "size_bytes": len(content)},
        )
        run_id = summary.get("job_id")
        if run_id:
            record = upsert_evidence_run(
                {
                    "run_id": run_id,
                    "source_name": filename,
                    "source_type": "csv_upload",
                    "status": "queued",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "completed_at": None,
                    "rows_received": 0,
                    "rows_accepted": 0,
                    "rows_rejected": 0,
                    "sensors_detected": summary.get("columns_detected", summary.get("column_count", 0)),
                    "room": "Uploaded telemetry",
                    "operating_state": "Monitoring",
                    "drift_status": "info",
                    "warnings": [],
                    "errors": [],
                    "primary_drivers": [],
                    "evidence_summary": [],
                    "structural_archetypes": [],
                    "initiated_by": actor,
                    "adaptive_site_key": "site::default",
                    "operator_feedback_history": [],
                }
            )
            if record:
                upsert_evidence_run(record)
    except Exception as exc:
        failed_job_id = uuid.uuid4().hex
        failed_at = datetime.now(timezone.utc).isoformat()
        upload_jobs.write_job(
            {
                "job_id": failed_job_id,
                "filename": filename,
                "status": "FAILED",
                "processing_state": "failed",
                "error": str(exc),
                "message": "Telemetry processing failed.",
                "progress_label": "Telemetry processing failed.",
                "result_available": False,
            }
        )
        upsert_evidence_run(
            {
                "run_id": failed_job_id,
                "source_name": filename,
                "source_type": "csv_upload",
                "status": "failed",
                "created_at": failed_at,
                "completed_at": failed_at,
                "rows_received": 0,
                "rows_accepted": 0,
                "rows_rejected": 0,
                "sensors_detected": 0,
                "room": "Uploaded telemetry",
                "operating_state": "error",
                "drift_status": "error",
                "warnings": [],
                "errors": [str(exc)],
                "primary_drivers": [],
                "evidence_summary": [],
                "structural_archetypes": [],
                "initiated_by": actor,
                "adaptive_site_key": "site::default",
                "operator_feedback_history": [],
            }
        )
        summary = {"job_id": failed_job_id}
    return {
        "job_id": summary.get("job_id"),
        "status": "PENDING",
        "filename": filename,
        "message": "Preparing telemetry intake. Upload received and queued for background processing.",
        "status_url": f"/api/data/upload-status/{summary.get('job_id')}",
        "file_size_bytes": len(content),
    }


@router.get("/upload-status/{job_id}")
async def upload_status(job_id: str):
    cached = _cache_get_status(job_id)
    if isinstance(cached, dict):
        if str(cached.get("status", "")).upper() == "NOT_FOUND":
            return JSONResponse(status_code=404, content=cached)
        return cached
    state_backend = upload_jobs.upload_state_backend()
    normalized = _resolve_upload_status_payload(job_id, state_backend)
    if str(normalized.get("status", "")).upper() == "NOT_FOUND":
        logger.warning(
            "upload_status_missing polling_job_id=%s validation_failure_reason=upload_session_missing metadata_exists=False",
            job_id,
        )
        _cache_set_status(job_id, normalized, ttl_seconds=1.0)
        return JSONResponse(status_code=404, content=normalized)

    if str(normalized.get("status", "")).upper() in {"COMPLETE", "FAILED"}:
        if str(normalized.get("status", "")).upper() == "COMPLETE":
            existing = read_evidence_run(str(job_id))
            if isinstance(existing, dict) and str(existing.get("status", "")).lower() == "queued":
                now = datetime.now(timezone.utc).isoformat()
                upload_result = upload_jobs.read_upload_result_by_job_id(job_id) or {}
                upsert_evidence_run(
                    {
                        **existing,
                        "status": "completed",
                        "completed_at": now,
                        "rows_received": upload_result.get("row_count", existing.get("rows_received", 0)),
                        "rows_accepted": upload_result.get("row_count", existing.get("rows_accepted", 0)),
                        "sensors_detected": max(0, int(upload_result.get("column_count", existing.get("sensors_detected", 0))) - 1),
                        "room": (((upload_result.get("sii_intelligence") or {}).get("primary_room")) or existing.get("room")),
                    }
                )
        if str(normalized.get("status", "")).upper() == "FAILED":
            existing = read_evidence_run(str(job_id))
            if isinstance(existing, dict) and str(existing.get("status", "")).lower() == "queued":
                now = datetime.now(timezone.utc).isoformat()
                upsert_evidence_run(
                    {
                        **existing,
                        "status": "failed",
                        "completed_at": now,
                        "errors": existing.get("errors") or [str(normalized.get("error") or "processing_error")],
                    }
                )
    terminal = str(normalized.get("status", "")).upper() in {"COMPLETE", "FAILED"}
    _cache_set_status(job_id, normalized, ttl_seconds=4.0 if terminal else 1.5)
    return normalized


@router.get("/upload-stream/{job_id}")
async def upload_stream(job_id: str):
    state_backend = upload_jobs.upload_state_backend()

    async def event_generator():
        # Stream for up to ~12 minutes with heartbeat-like cadence.
        for _ in range(180):
            payload = _resolve_upload_status_payload(job_id, state_backend)
            yield f"data: {json.dumps(payload)}\n\n"
            if str(payload.get("status", "")).upper() in {"COMPLETE", "FAILED"}:
                break
            await asyncio.sleep(4)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/latest-upload")
async def latest_upload(include_persisted: int | bool = True):
    cached = _cache_get_latest()
    if isinstance(cached, dict):
        return cached
    state_backend = upload_jobs.upload_state_backend()
    result = upload_jobs.read_latest_upload_result()
    summary = latest_completed_job_summary() or upload_jobs.read_latest_upload_summary() or {}
    history = upload_jobs.read_upload_history(limit=20)

    if upload_jobs.reset_block_persisted_active():
        summary = {}
        result = None
        history = []

    def _has_persisted_status(job_id: str | None) -> bool:
        if not job_id:
            return False
        status = upload_jobs.read_upload_status(str(job_id))
        return isinstance(status, dict) and bool(status.get("job_id"))

    def _is_rich_persisted_result(candidate: dict | None) -> bool:
        if not isinstance(candidate, dict):
            return False
        if int(candidate.get("row_count") or 0) > 0:
            return True
        if isinstance(candidate.get("data_quality"), dict):
            return True
        if isinstance(candidate.get("room_summary"), dict):
            return True
        return False

    # If latest cache points to an incomplete artifact, refresh from
    # canonical per-job persisted result when available.
    result_job_id = str((result or {}).get("job_id") or "")
    if isinstance(result, dict) and result_job_id and not result.get("filename"):
        by_job_result = upload_jobs.read_upload_result_by_job_id(result_job_id)
        if isinstance(by_job_result, dict) and by_job_result.get("filename"):
            result = by_job_result

    # If latest summary/result are stale or empty, recover from any completed
    # persisted upload status. This keeps latest-upload aligned with
    # upload-status in multi-task ECS deployments.
    if not summary and history:
        for item in history:
            candidate_job_id = str(item.get("job_id") or "") if isinstance(item, dict) else ""
            if not _has_persisted_status(candidate_job_id):
                continue
            if isinstance(item, dict) and (
                item.get("status") == "COMPLETE"
                or item.get("result_available")
                or item.get("sii_completed")
            ):
                summary = dict(item)
                break

    result_job_id = str((result or {}).get("job_id") or "")
    if not summary and not _is_rich_persisted_result(result):
        result = None
    elif summary and not _has_persisted_status(result_job_id) and not _is_rich_persisted_result(result):
        result = None

    # Recovery path for split API/worker containers:
    # if the full result is not visible in this container but a completed
    # upload summary/history is visible, return a non-empty latest-upload
    # snapshot so the frontend stops treating the system as empty.
    if not result and summary:
        job_id = summary.get("job_id")
        by_job = upload_jobs.read_upload_result_by_job_id(str(job_id)) if job_id else None
        result = by_job or None

    if not result and history:
        latest = history[0] if isinstance(history[0], dict) else {}
        latest_job_id = str(latest.get("job_id") or "")
        if latest_job_id and not _has_persisted_status(latest_job_id):
            latest = {}
        if latest.get("status") == "COMPLETE" or latest.get("result_available"):
            result = {
                "job_id": latest.get("job_id"),
                "filename": latest.get("filename"),
                "row_count": latest.get("row_count") or latest.get("rows_processed") or 0,
                "column_count": latest.get("column_count") or latest.get("columns_detected") or 0,
                "replay_timeline": {"timeline": [None] * int(latest.get("replay_frame_count") or latest.get("latest_replay_frames") or 0)},
                "last_processed_at": latest.get("last_processed_at"),
                "sii_completion_artifacts": latest.get("sii_completion_artifacts") or {},
                "result_summary": latest.get("result_summary") or {},
            }
            summary = {**latest, **summary}
    frames = _extract_timeline(result if isinstance(result, dict) else None, summary.get("job_id") if isinstance(summary, dict) else None)
    adaptive = adaptive_learning.build_adaptive_snapshot(result, summary) if isinstance(result, dict) else {}
    if isinstance(adaptive, dict):
        recent_feedback = (((adaptive.get("event_memory") or {}).get("recent_feedback_history")) or [])
        if not recent_feedback:
            fallback_site = adaptive_learning.build_adaptive_snapshot({"room_summary": {"rooms": []}}, {"last_processed_at": snapshot_time(summary)} if isinstance(summary, dict) else {})
            fallback_recent = (((fallback_site.get("event_memory") or {}).get("recent_feedback_history")) or [])
            if fallback_recent:
                adaptive["event_memory"] = adaptive.get("event_memory", {})
                adaptive["event_memory"]["recent_feedback_history"] = fallback_recent
    snapshot = {
        **summary,
        "state_backend": state_backend,
        "source": "uploaded" if result else "none",
        "last_filename": (result or {}).get("filename") or summary.get("filename"),
        "rows_processed": (result or {}).get("row_count") or summary.get("rows_processed") or summary.get("row_count") or 0,
        "columns_detected": (result or {}).get("column_count") or summary.get("columns_detected") or summary.get("column_count") or 0,
        "state_available": bool(result),
        "status": "COMPLETE" if result else summary.get("status", "empty"),
        "processing_state": "complete" if result else summary.get("processing_state", "empty"),
        "result_available": bool(result) or bool(summary.get("result_available")),
        "sii_completed": bool(result) or bool(summary.get("sii_completed")),
        "replay_ready": bool(frames),
        "replay_frame_count": len(frames or []),
        "latest_replay_frames": len(frames or []),
        "replay_source": "persisted" if frames else "unknown",
    }
    if history and snapshot.get("last_filename"):
        history[0]["filename"] = snapshot["last_filename"]
    response_payload = {
        "snapshot": snapshot,
        "latest_result": result,
        "latestResult": result,
        "summary": summary,
        "history": history,
        "adaptive_learning": adaptive,
        "state_backend": state_backend,
        **snapshot,
    }
    cache_ttl = 4.0 if bool(result) else 1.5
    _cache_set_latest(response_payload, ttl_seconds=cache_ttl)
    return response_payload


@router.get("/replay/{job_id}")
async def data_replay(job_id: str):
    return upload_jobs.replay_payload(job_id)


@router.get("/intake/{job_id}/result")
async def intake_result(job_id: str):
    result = upload_jobs.read_upload_result_by_job_id(job_id)
    if not result:
        return {
            "job_id": job_id,
            "result_available": False,
            "status": "NOT_FOUND",
            "result": None,
        }
    return {
        "job_id": job_id,
        "result_available": True,
        "status": "COMPLETE",
        "result": result,
    }


@router.post("/reset")
async def reset_data():
    upload_jobs.reset_upload_state()
    _clear_endpoint_caches()
    return {"ok": True, "status": "reset"}


def rebuild_upload_replay_from_source(job_id: str | dict | None = None, *args, **kwargs):
    payload = job_id if isinstance(job_id, dict) else {}
    requested_job_id = str(payload.get("job_id") or job_id or "")
    file_path = payload.get("file_path")
    if not file_path:
        return upload_jobs.replay_payload(requested_job_id or None)

    result = upload_jobs.process_csv_file(Path(file_path))
    replay = result.get("replay_timeline") or {}
    timeline = replay.get("timeline", []) if isinstance(replay, dict) else []
    replay_mode = "minimal_timestamp_fallback"
    try:
        lines = Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
        if lines:
            headers = [h.strip().lower() for h in lines[0].split(",")]
            ts_idx = next((idx for idx, value in enumerate(headers) if "time" in value or "date" in value), 0)
            data_lines = lines[1: min(len(lines), 30)]
            numeric_like = 0
            for row in data_lines:
                cells = [cell.strip() for cell in row.split(",")]
                for idx, cell in enumerate(cells):
                    if idx == ts_idx:
                        continue
                    if any(ch.isdigit() for ch in cell):
                        numeric_like += 1
            if numeric_like >= 8:
                replay_mode = "standard"
    except OSError:
        pass

    return {
        "job_id": requested_job_id or result.get("job_id"),
        "timeline": timeline,
        "frame_count": len(timeline),
        "meta": {**(replay.get("meta", {}) if isinstance(replay, dict) else {}), "replay_mode": replay_mode},
        "message": "Replay reconstructed from the retained source CSV.",
    }


def queue_metrics() -> dict[str, int]:
    return runtime_queue_metrics()


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
            return normalized
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
    return normalized


def snapshot_time(summary: dict) -> str:
    return str(summary.get("last_processed_at") or summary.get("completed_at") or datetime.now(timezone.utc).isoformat())


def latest_completed_job_summary() -> dict:
    return upload_jobs.read_latest_upload_summary() or {}
