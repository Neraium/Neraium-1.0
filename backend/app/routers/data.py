from __future__ import annotations

import logging
import threading
import asyncio
import json
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
import uuid
from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from app.services.evidence_store import read_evidence_run, upsert_evidence_run
from app.services.analysis_result_contract import empty_analysis_result, ensure_analysis_result
from app.core.security import _strict_auth_mode, require_operator_role
from app.services import upload_jobs
from app.services.upload_evidence import build_evidence_record_from_result
from app.services.upload_persistence import summarize_result
from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE
from app.services.upload_state import build_empty_latest_upload_record, has_active_session_artifact
from app.services.upload_status_contract import normalize_upload_status_payload
from app.services.sii_runner import CORE_ENGINE, RUNNER_MODULE
from app.services.runtime_db import record_audit_event
from app.services.runtime_db import enqueue_upload_job
from app.services.runtime_db import queue_metrics as runtime_queue_metrics
from app.services.runtime_db import read_upload_queue_job, touch_upload_queue_job, peek_next_upload_job_for_worker
from app.services.runtime_db import configure_runtime_dir as configure_runtime_db_dir
from app.services.upload_state_repository import persist_upload_source, read_replay_payload, read_upload_result_by_job_id, reset_upload_state, resolve_upload_artifacts, shared_state_configured, upload_state_backend
from app.services.rate_limiter import consume_rate_limit
from app.services.latest_upload_state import resolve_latest_upload_payload
from app.services.upload_session_service import resolve_upload_status

router = APIRouter(prefix="/data", tags=["data"])
logger = logging.getLogger(__name__)
UPLOAD_JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)
UPLOAD_RATE_LIMIT = 20
UPLOAD_RATE_WINDOW_SECONDS = 60
UPLOAD_STATUS_RATE_LIMIT = 240
UPLOAD_STATUS_RATE_WINDOW_SECONDS = 60
_UPLOAD_WORKERS: set[threading.Thread] = set()
_UPLOAD_WORKERS_LOCK = threading.Lock()


def format_upload_capacity(size_bytes: int) -> str:
    size = max(int(size_bytes or 0), 0)
    if size >= 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024 * 1024):.0f} GB"
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.0f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} bytes"


def _request_client_ip(request: Request) -> str:
    forwarded_for = str(request.headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
    if forwarded_for:
        return forwarded_for
    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"


def _rate_limit_key(request: Request) -> str:
    auth_context = getattr(request.state, "auth_context", {})
    subject = str(auth_context.get("auth_subject") or "").strip()
    if subject and subject != "readonly":
        return subject
    return _request_client_ip(request)


def _rate_limit_response(retry_after: int, *, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        headers={"retry-after": str(retry_after)},
        content={
            "status": "FAILED",
            "error_type": error_type,
            "message": message,
        },
    )


def _clear_endpoint_caches() -> None:
    return None


def invalidate_latest_upload_cache() -> None:
    return None


def _log_upload_event(event: str, **fields: Any) -> None:
    normalized = {"event": event, **fields}
    parts = []
    for key, value in normalized.items():
        if value is None:
            continue
        text = str(value).replace("\n", " ").replace("\r", " ")
        if len(text) > 500:
            text = f"{text[:500]}..."
        parts.append(f"{key}={text}")
    logger.info("upload_lifecycle_event %s", " ".join(parts))


def _should_dispatch_upload_worker(settings: Any) -> bool:
    app_env = str(getattr(settings, "app_env", "") or "").strip().lower()
    process_role = str(getattr(settings, "process_role", "") or "").strip().lower()
    if app_env in {"prod", "production"} and process_role == "api" and shared_state_configured():
        return False
    return True


def _run_upload_worker_for_runtime(runtime_dir: Path) -> None:
    worker_job_id: str | None = None
    try:
        logger.info("worker_thread_started runtime_dir=%s", runtime_dir)
        configure_runtime_db_dir(runtime_dir)
        worker_job_id = peek_next_upload_job_for_worker()
        if worker_job_id:
            now = datetime.now(timezone.utc).isoformat()
            try:
                touch_upload_queue_job(worker_job_id)
            except Exception:
                logger.exception("worker_first_heartbeat_touch_failed job_id=%s runtime_dir=%s", worker_job_id, runtime_dir)
            current = upload_jobs.read_upload_status(worker_job_id) or {"job_id": worker_job_id}
            staged = {
                **current,
                "job_id": worker_job_id,
                "worker_state": "running",
                "worker_last_seen_at": now,
            }
            if not staged.get("propagation_stage"):
                staged["propagation_stage"] = "queued"
            if staged.get("processing_state") in {None, "", "queued", "pending"}:
                staged["processing_state"] = "queued"
            if not staged.get("propagation_label"):
                staged["propagation_label"] = "Queued."
            if not staged.get("progress_label"):
                staged["progress_label"] = staged.get("propagation_label")
            upload_jobs.write_job(staged)
            logger.info("worker_first_heartbeat_written job_id=%s runtime_dir=%s", worker_job_id, runtime_dir)

        upload_jobs.configure_runtime_dir(runtime_dir)
        logger.info("worker_process_next_started job_id=%s runtime_dir=%s", worker_job_id, runtime_dir)
        processed = upload_jobs.process_next_queued_upload_job()
        logger.info("worker_process_next_finished job_id=%s runtime_dir=%s processed=%s", worker_job_id, runtime_dir, processed)
    except Exception as exc:
        logger.exception("worker_process_next_failed runtime_dir=%s", runtime_dir)
        if worker_job_id:
            now = datetime.now(timezone.utc).isoformat()
            failed = upload_jobs.read_upload_status(worker_job_id) or {"job_id": worker_job_id}
            failed.update({
                "job_id": worker_job_id,
                "status": "FAILED",
                "processing_state": "failed",
                "error_type": "worker_start_failed",
                "error": str(exc),
                "message": "Telemetry processing failed.",
                "progress_label": "Telemetry processing failed.",
                "worker_state": "stalled",
                "worker_last_seen_at": now,
                "result_available": False,
            })
            upload_jobs.write_job(failed)
            _upsert_failed_evidence_record(
                job_id=worker_job_id,
                filename=str(failed.get("filename") or "upload.csv"),
                source_type="json_upload" if str(failed.get("filename") or "").lower().endswith(".json") else "csv_upload",
                error_message=str(exc) or exc.__class__.__name__,
                initiated_by=str(failed.get("initiated_by") or "anonymous"),
            )


def _run_tracked_upload_worker(runtime_dir: Path) -> None:
    try:
        _run_upload_worker_for_runtime(runtime_dir)
    finally:
        with _UPLOAD_WORKERS_LOCK:
            _UPLOAD_WORKERS.discard(threading.current_thread())


def wait_for_upload_workers(timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + max(float(timeout), 0.0)
    current_thread = threading.current_thread()
    while True:
        with _UPLOAD_WORKERS_LOCK:
            workers = [
                worker
                for worker in _UPLOAD_WORKERS
                if worker is not current_thread and worker.is_alive()
            ]
        if not workers:
            return True
        for worker in workers:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            worker.join(remaining)


def _dispatch_upload_worker_for_runtime(runtime_dir: Path) -> None:
    logger.info("worker_dispatch_requested runtime_dir=%s", runtime_dir)
    worker: threading.Thread | None = None
    try:
        worker = threading.Thread(
            target=_run_tracked_upload_worker,
            args=(runtime_dir,),
            daemon=True,
            name="upload-worker-dispatch",
        )
        with _UPLOAD_WORKERS_LOCK:
            _UPLOAD_WORKERS.add(worker)
        worker.start()
    except Exception:
        if worker is not None:
            with _UPLOAD_WORKERS_LOCK:
                _UPLOAD_WORKERS.discard(worker)
        logger.exception("upload_worker_thread_start_failed runtime_dir=%s", runtime_dir)


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


def _process_upload_inline(job_id: str, status: dict) -> dict:
    file_path = status.get("file_path")
    if not file_path or not Path(str(file_path)).exists():
        return status
    try:
        path = Path(str(file_path))
        filename = status.get("filename") or path.name
        if path.suffix.lower() == ".json":
            upload_jobs.process_json_payload(path.read_text(encoding="utf-8"), filename=filename, job_id=job_id)
        else:
            upload_jobs.process_csv_file(path, filename=filename, job_id=job_id)
        return upload_jobs.read_upload_status(job_id) or status
    except Exception as exc:
        logger.exception("upload_status_inline_processing_failed job_id=%s", job_id)
        failed = {
            **status,
            "job_id": job_id,
            "status": "FAILED",
            "processing_state": "failed",
            "error_type": "processing_error",
            "error": str(exc),
            "message": "Telemetry processing failed.",
            "progress_label": "Telemetry processing failed.",
            "result_available": False,
        }
        upload_jobs.write_job(failed)
        _upsert_failed_evidence_record(
            job_id=job_id,
            filename=str(failed.get("filename") or "upload.csv"),
            source_type="json_upload" if str(failed.get("filename") or "").lower().endswith(".json") else "csv_upload",
            error_message=str(exc) or exc.__class__.__name__,
            initiated_by=str(failed.get("initiated_by") or "anonymous"),
        )
        return failed



def _upsert_failed_evidence_record(
    *,
    job_id: str,
    filename: str,
    source_type: str,
    error_message: str,
    initiated_by: str = "anonymous",
) -> None:
    failed_at = datetime.now(timezone.utc).isoformat()
    upsert_evidence_run(
        {
            "run_id": job_id,
            "source_name": filename,
            "source_type": source_type,
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
            "errors": [error_message],
            "primary_drivers": [],
            "evidence_summary": [],
            "structural_archetypes": [],
            "initiated_by": initiated_by,
            "adaptive_site_key": "site::default",
            "operator_feedback_history": [],
            "observation_type": "data_condition",
            "observation_status": "failed",
            "variables": [],
            "drift_metrics": {},
            "data_conditions": [error_message],
            "regime_label": None,
            "structural_state": "Error",
            "deformation_started_at": None,
        }
    )



def _parse_iso_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _with_worker_visibility(payload: dict, job_id: str) -> dict:
    enriched = dict(payload or {})
    now = datetime.now(timezone.utc)
    enriched["status_checked_at"] = now.isoformat()

    queue_entry = read_upload_queue_job(str(job_id))
    queue_position = queue_entry.get("queue_position") if isinstance(queue_entry, dict) else None
    enriched["queue_position"] = int(queue_position) if isinstance(queue_position, int) else None

    created_at = _parse_iso_ts((queue_entry or {}).get("created_at") if isinstance(queue_entry, dict) else None)
    queued_seconds = max(0, int((now - created_at).total_seconds())) if created_at else None
    enriched["queued_seconds"] = queued_seconds

    payload_last_seen = _parse_iso_ts(enriched.get("worker_last_seen_at"))
    last_seen = _parse_iso_ts((queue_entry or {}).get("updated_at") if isinstance(queue_entry, dict) else None) or payload_last_seen
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
    if queue_status == "processing" or status_text in {"PROCESSING", "RUNNING_SII"} or processing_state in {"parsing_telemetry", "building_relationship_baselines", "scoring_relationship_drift", "building_propagation_model", "generating_system_interpretation", "complete"}:
        state = "running"

    if state == "starting" and queued_seconds is not None and queued_seconds > 15:
        stale = True
        if last_seen and (now - last_seen).total_seconds() <= 15:
            stale = False
        state = "stalled" if stale else "starting"

    if not isinstance(queue_entry, dict):
        state = "unknown" if status_text not in {"PENDING", "PROCESSING", "RUNNING_SII"} else "starting"

    enriched["worker_state"] = state
    return enriched


def _resolve_upload_status_payload(job_id: str, state_backend: str) -> dict:
    status = upload_jobs.read_upload_status(job_id)
    if status and str(status.get("status", "")).upper() in {"PENDING", "QUEUED", "PROCESSING"}:
        processed = upload_jobs.process_next_queued_upload_job()
        status = upload_jobs.read_upload_status(job_id) or status
        if not processed and str(status.get("status", "")).upper() in {"PENDING", "QUEUED", "PROCESSING"}:
            status = _process_upload_inline(job_id, status)
    if status:
        normalized = normalize_upload_status_payload(status)
        normalized.setdefault("state_backend", state_backend)
        return _with_worker_visibility(normalized, job_id)
    latest_record = read_latest_upload_record() or {}
    latest_summary = latest_record.get("summary") if isinstance(latest_record.get("summary"), dict) else {}
    if str(latest_summary.get("job_id") or latest_record.get("job_id") or "") == str(job_id):
        normalized = normalize_upload_status_payload(latest_summary)
        normalized.setdefault("state_backend", state_backend)
        return _with_worker_visibility(normalized, job_id)
    latest_result = read_upload_result_by_job_id(job_id)
    if isinstance(latest_result, dict) and latest_result.get("job_id") == job_id:
        timeline = _extract_timeline(latest_result, job_id)
        return _with_worker_visibility({
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
            "progress_label": "Analysis ready.",
            "message": "Analysis ready.",
            "job_state": "completed",
            "terminal": True,
            "sii_completion_artifacts": latest_result.get("sii_completion_artifacts", {}),
            "error": None,
            "propagation_stage": "complete",
            "propagation_progress": 100,
            "propagation_label": "Analysis ready.",
            "state_backend": state_backend,
        }, job_id)
    if UPLOAD_JOB_ID_PATTERN.match(str(job_id or "")):
        return _with_worker_visibility({
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
            "propagation_stage": "queued",
            "propagation_progress": 10,
            "propagation_label": "Queued.",
            "state_backend": state_backend,
        }, job_id)
    return _with_worker_visibility({
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
    }, job_id)


@router.post("/upload", status_code=202, dependencies=[Depends(require_operator_role)])
async def upload_data(request: Request, file: UploadFile = File(...)):
    if _strict_auth_mode(request):
        allowed, retry_after = consume_rate_limit(
            "data.upload",
            _rate_limit_key(request),
            limit=UPLOAD_RATE_LIMIT,
            window_seconds=UPLOAD_RATE_WINDOW_SECONDS,
        )
        if not allowed:
            return _rate_limit_response(retry_after, error_type="upload_rate_limited", message="Upload rate limit exceeded. Retry shortly.")
    settings = request.app.state.settings
    started_at = time.perf_counter()
    request_id = getattr(request.state, "request_id", None)
    filename = file.filename or "upload.csv"
    lowered = filename.lower()
    if not (lowered.endswith(".csv") or lowered.endswith(".json") or lowered.endswith(".txt")):
        _log_upload_event("request_rejected", request_id=request_id, endpoint="/api/data/upload", filename=filename, processing_stage="validate_file_type", failure_reason="unsupported_file_type")
        return JSONResponse(
            status_code=400,
            content={
                "status": "FAILED",
                "processing_state": "failed",
                "error_type": "unsupported_file_type",
                "message": "Only .csv, .txt, and .json telemetry files are supported.",
            },
        )

    max_size_bytes = int(getattr(settings, "max_upload_size_bytes", 10 * 1024 * 1024 * 1024))
    metrics = queue_metrics()
    if int(metrics.get("pending", 0)) >= int(getattr(settings, "max_pending_upload_jobs", 3)):
        _log_upload_event("request_rejected", request_id=request_id, endpoint="/api/data/upload", filename=filename, queue_status="saturated", processing_stage="queue_capacity", failure_reason="upload_queue_saturated")
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
    _log_upload_event(
        "request_started",
        request_id=request_id,
        endpoint="/api/data/upload",
        filename=filename,
        content_type=content_type or "unknown",
        content_length=request.headers.get("content-length"),
        max_upload_size_bytes=max_size_bytes,
    )
    auth_context = getattr(request.state, "auth_context", {})
    actor = (
        auth_context.get("auth_subject")
        or request.headers.get("X-Neraium-User")
        or request.headers.get("X-Authenticated-User")
        or request.headers.get("X-Forwarded-Email")
        or "anonymous"
    )
    file_size_bytes = 0
    csv_has_non_whitespace = False
    temp_path = ""
    summary: dict[str, Any] = {}
    try:
        with NamedTemporaryFile(delete=False, suffix=Path(filename).suffix or ".csv") as temp:
            temp_path = temp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                file_size_bytes += len(chunk)
                if file_size_bytes > max_size_bytes:
                    try:
                        Path(temp_path).unlink(missing_ok=True)
                    except OSError:
                        pass
                    return JSONResponse(
                        status_code=413,
                        content={
                            "status": "FAILED",
                            "error_type": "upload_too_large",
                            "message": f"File too large. Maximum supported size is {format_upload_capacity(max_size_bytes)}.",
                            "max_upload_size_bytes": max_size_bytes,
                            "received_size_bytes": file_size_bytes,
                        },
                    )
                if lowered.endswith(".csv") and not csv_has_non_whitespace and chunk.strip():
                    csv_has_non_whitespace = True
                temp.write(chunk)

        if lowered.endswith(".csv") and (file_size_bytes == 0 or not csv_has_non_whitespace):
            _log_upload_event("request_rejected", request_id=request_id, endpoint="/api/data/upload", filename=filename, file_size_bytes=file_size_bytes, processing_stage="validate_csv", failure_reason="csv_empty")
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
            return JSONResponse(
                status_code=400,
                content={
                    "status": "FAILED",
                    "processing_state": "failed",
                    "error_type": "csv_parse_error",
                    "message": "CSV file is empty.",
                },
            )

        _log_upload_event("request_bytes_received", request_id=request_id, endpoint="/api/data/upload", filename=filename, file_size_bytes=file_size_bytes, content_type=content_type or "unknown", processing_stage="spooled")

        job_id = uuid.uuid4().hex
        request.state.upload_session_id = job_id
        shared_upload_source_key = None
        if shared_state_configured():
            shared_upload_source_key = persist_upload_source(
                job_id,
                temp_path,
                filename=filename,
                content_type=content_type or None,
            )
        worker_dispatch_status = "thread_dispatched" if _should_dispatch_upload_worker(settings) else "external_worker_queue"
        summary = {
            "job_id": job_id,
            "filename": filename,
            "status_url": f"/api/data/upload-status/{job_id}",
            "status": "PENDING",
            "processing_state": "queued",
            "percent": 5,
            "progress": 5,
            "progress_label": "Worker starting...",
            "message": "Worker starting...",
            "propagation_stage": "queued",
            "propagation_progress": 5,
            "propagation_label": "Worker starting...",
            "runner_used": False if str(getattr(settings, "process_role", "")).lower() == "api" else True,
            "runner_module": RUNNER_MODULE,
            "core_engine": CORE_ENGINE,
            "file_path": temp_path,
            "shared_upload_source_key": shared_upload_source_key,
            "file_size_bytes": file_size_bytes,
            "content_type": content_type,
            "initiated_by": actor,
            "request_id": request_id,
            "upload_session_id": job_id,
            "worker_dispatch_status": worker_dispatch_status,
        }
        upload_jobs.write_job(summary)
        record_audit_event(
            actor=actor,
            action="upload.accepted",
            resource_type="upload_job",
            resource_id=str(job_id or "unknown"),
            request_id=auth_context.get("request_id"),
            detail={"filename": filename, "size_bytes": file_size_bytes},
        )
        run_id = summary.get("job_id")
        if run_id:
            upsert_evidence_run(
                {
                    "run_id": run_id,
                    "source_name": filename,
                    "source_type": "json_upload" if lowered.endswith(".json") else "csv_upload",
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
                    "observation_type": "baseline_shift",
                    "observation_status": "queued",
                    "variables": [],
                    "drift_metrics": {},
                    "data_conditions": [],
                    "regime_label": "State Group A",
                    "structural_state": "Monitoring",
                    "deformation_started_at": None,
                }
            )
        enqueue_upload_job(job_id)
        if worker_dispatch_status == "thread_dispatched":
            _dispatch_upload_worker_for_runtime(request.app.state.settings.runtime_dir)
        _log_upload_event(
            "job_queued",
            request_id=request_id,
            endpoint="/api/data/upload",
            filename=filename,
            file_size_bytes=file_size_bytes,
            job_id=job_id,
            queue_status="pending",
            worker_dispatch_status=worker_dispatch_status,
            processing_stage="queued",
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
    except Exception as exc:
        try:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
        except Exception:
            pass
        failed_job_id = str(summary.get("job_id") or uuid.uuid4().hex)
        failed_at = datetime.now(timezone.utc).isoformat()
        error_message = str(exc) or exc.__class__.__name__
        error_type = "shared_upload_queue_not_configured" if "shared_upload_queue_not_configured" in error_message else "upload_enqueue_failed"
        _log_upload_event(
            "request_failed",
            request_id=request_id,
            endpoint="/api/data/upload",
            filename=filename,
            file_size_bytes=file_size_bytes,
            job_id=failed_job_id,
            processing_stage="enqueue",
            elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
            failure_reason=error_type,
        )
        logger.exception("upload_request_enqueue_failed request_id=%s job_id=%s filename=%s size_bytes=%s", request_id, failed_job_id, filename, file_size_bytes)
        upload_jobs.write_job(
            {
                **summary,
                "job_id": failed_job_id,
                "filename": filename,
                "status": "FAILED",
                "processing_state": "failed",
                "error_type": error_type,
                "error": error_message,
                "message": "Telemetry processing failed." if error_type != "shared_upload_queue_not_configured" else "Shared upload queue is not configured for split-role production.",
                "progress_label": "Telemetry processing failed.",
                "result_available": False,
                "propagation_stage": "failed",
                "propagation_progress": 0,
                "propagation_label": "Failed.",
            }
        )
        upsert_evidence_run(
            {
                "run_id": failed_job_id,
                "source_name": filename,
                "source_type": "json_upload" if lowered.endswith(".json") else "csv_upload",
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
                "errors": [error_message],
                "primary_drivers": [],
                "evidence_summary": [],
                "structural_archetypes": [],
                "initiated_by": actor,
                "adaptive_site_key": "site::default",
                "operator_feedback_history": [],
                "observation_type": "data_condition",
                "observation_status": "failed",
                "variables": [],
                "drift_metrics": {},
                "data_conditions": [error_message],
                "regime_label": None,
                "structural_state": "Error",
                "deformation_started_at": None,
            }
        )
        return JSONResponse(
            status_code=503 if error_type == "shared_upload_queue_not_configured" else 500,
            content={
                "job_id": failed_job_id,
                "status": "FAILED",
                "filename": filename,
                "message": "Shared upload queue is not configured for split-role production." if error_type == "shared_upload_queue_not_configured" else "Telemetry processing failed.",
                "error_type": error_type,
                "error": error_message,
                "status_url": f"/api/data/upload-status/{failed_job_id}",
            },
        )
    return {
        "job_id": summary.get("job_id"),
        "status": "PENDING",
        "processing_state": "queued",
        "filename": filename,
        "percent": 5,
        "progress": 5,
        "progress_label": "Worker starting...",
        "message": "Worker starting...",
        "status_url": f"/api/data/upload-status/{summary.get('job_id')}",
        "file_size_bytes": file_size_bytes,
        "propagation_stage": "queued",
        "propagation_progress": 5,
        "propagation_label": "Worker starting...",
        "worker_state": "starting" if summary.get("worker_dispatch_status") == "thread_dispatched" else "queued",
        "worker_dispatch_status": summary.get("worker_dispatch_status"),
        "worker_last_seen_at": datetime.now(timezone.utc).isoformat(),
        "queue_position": None,
        "queued_seconds": 0,
        "status_checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/upload/{job_id}/retry", status_code=202, dependencies=[Depends(require_operator_role)])
async def retry_upload_analysis(request: Request, job_id: str):
    settings = request.app.state.settings
    request_id = getattr(request.state, "request_id", None)
    requested_job_id = str(job_id or "").strip()
    if not UPLOAD_JOB_ID_PATTERN.match(requested_job_id):
        return JSONResponse(
            status_code=400,
            content={
                "status": "FAILED",
                "error_type": "invalid_upload_job",
                "message": "Upload job id is invalid.",
            },
        )

    status_payload = upload_jobs.read_upload_status(requested_job_id) or {}
    file_path = status_payload.get("file_path")
    shared_upload_source_key = str(status_payload.get("shared_upload_source_key") or "").strip()
    has_local_file = bool(file_path and Path(str(file_path)).exists())
    if not status_payload or (not has_local_file and not shared_upload_source_key):
        return JSONResponse(
            status_code=404,
            content={
                "job_id": requested_job_id,
                "status": "FAILED",
                "error_type": "upload_source_missing",
                "message": "The uploaded source file is no longer available. Select the CSV again.",
                "status_url": f"/api/data/upload-status/{requested_job_id}",
            },
        )

    now = datetime.now(timezone.utc).isoformat()
    worker_dispatch_status = "thread_dispatched" if _should_dispatch_upload_worker(settings) else "external_worker_queue"
    retried = {
        **status_payload,
        "job_id": requested_job_id,
        "status": "PENDING",
        "processing_state": "queued",
        "percent": 5,
        "progress": 5,
        "progress_label": "Retry queued.",
        "message": "Retry queued.",
        "error": None,
        "error_type": None,
        "result_available": False,
        "first_usable_available": False,
        "sii_completed": False,
        "replay_ready": False,
        "propagation_stage": "queued",
        "propagation_progress": 5,
        "propagation_label": "Retry queued.",
        "retry_requested_at": now,
        "worker_state": "starting" if worker_dispatch_status == "thread_dispatched" else "queued",
        "worker_dispatch_status": worker_dispatch_status,
        "worker_last_seen_at": now,
    }
    upload_jobs.write_job(retried)
    enqueue_upload_job(requested_job_id)
    if worker_dispatch_status == "thread_dispatched":
        _dispatch_upload_worker_for_runtime(request.app.state.settings.runtime_dir)
    _log_upload_event(
        "retry_queued",
        request_id=request_id,
        endpoint=f"/api/data/upload/{requested_job_id}/retry",
        filename=status_payload.get("filename"),
        job_id=requested_job_id,
        queue_status="pending",
        worker_dispatch_status=worker_dispatch_status,
        processing_stage="queued",
    )
    return {
        "job_id": requested_job_id,
        "status": "PENDING",
        "processing_state": "queued",
        "percent": 5,
        "progress": 5,
        "progress_label": "Retry queued.",
        "message": "Retry queued.",
        "status_url": f"/api/data/upload-status/{requested_job_id}",
        "worker_state": "starting" if worker_dispatch_status == "thread_dispatched" else "queued",
        "worker_dispatch_status": worker_dispatch_status,
        "worker_last_seen_at": now,
    }


@router.get("/upload-status/{job_id}")
async def upload_status(request: Request, job_id: str):
    if _strict_auth_mode(request):
        allowed, retry_after = consume_rate_limit(
            "data.upload_status",
            _request_client_ip(request),
            limit=UPLOAD_STATUS_RATE_LIMIT,
            window_seconds=UPLOAD_STATUS_RATE_WINDOW_SECONDS,
        )
        if not allowed:
            return _rate_limit_response(retry_after, error_type="upload_status_rate_limited", message="Upload status polling rate limit exceeded. Retry shortly.")
    request_id = getattr(request.state, "request_id", None)
    request.state.upload_session_id = job_id
    normalized = resolve_upload_status(job_id, request_id=request_id)
    if str(normalized.get("status", "")).upper() == "NOT_FOUND":
        logger.warning("upload_status_missing polling_job_id=%s validation_failure_reason=upload_session_missing metadata_exists=False", job_id)
        return JSONResponse(status_code=404, content=normalized)
    return normalized


@router.get("/upload-stream/{job_id}")
async def upload_stream(job_id: str, request: Request = None):
    request_id = getattr(request.state, "request_id", None) if request is not None else None

    async def event_generator():
        # Stream for up to ~12 minutes with heartbeat-like cadence.
        for _ in range(180):
            payload = resolve_upload_status(job_id, request_id=request_id)
            yield f"data: {json.dumps(payload)}\n\n"
            if str(payload.get("status", "")).upper() in {"COMPLETE", "FAILED", "TIMEOUT", "CANCELLED"}:
                break
            await asyncio.sleep(4)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/latest-upload")
async def latest_upload(include_persisted: int | bool = True, request: Request = None):
    request_id = getattr(request.state, "request_id", None) if request is not None else None
    payload = resolve_latest_upload_payload(include_persisted=include_persisted, request_id=request_id)
    if request is not None:
        request.state.upload_session_id = payload.get("upload_session_id")
    return payload


@router.get("/system-interpretation")
async def system_interpretation_contract(include_persisted: int | bool = True, request: Request = None):
    payload = await latest_upload(include_persisted=include_persisted, request=request)
    interpretation = payload.get("system_interpretation") if isinstance(payload, dict) else None
    raw_source = str((payload or {}).get("source") or (payload or {}).get("snapshot", {}).get("source") or "").lower()
    if raw_source in {"uploaded", "latest_upload"}:
        source = "latest_upload"
    elif raw_source == "live":
        source = "live"
    else:
        source = "none"
    return {
        "system_interpretation": interpretation if isinstance(interpretation, dict) else {},
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/replay/{job_id}")
async def data_replay(job_id: str):
    return resolve_upload_artifacts(job_id).get("replay") or read_replay_payload(job_id)


@router.get("/intake/{job_id}/result")
async def intake_result(job_id: str):
    result = read_upload_result_by_job_id(job_id)
    if not result:
        return {
            "job_id": job_id,
            "result_available": False,
            "status": "NOT_FOUND",
            "result": None,
            "analysis_result": empty_analysis_result(
                analysis_id=job_id,
                upload_id=job_id,
                status="missing",
                message="Upload result was not found.",
                errors=["upload_result_missing"],
            ),
        }
    return {
        "job_id": job_id,
        "result_available": True,
        "status": "COMPLETE",
        "result": result,
        "analysis_result": ensure_analysis_result(result),
    }


@router.post("/reset", dependencies=[Depends(require_operator_role)])
async def reset_data():
    reset_upload_state()
    _clear_endpoint_caches()
    return {"ok": True, "status": "reset"}


def rebuild_upload_replay_from_source(job_id: str | dict | None = None, *args, **kwargs):
    payload = job_id if isinstance(job_id, dict) else {}
    requested_job_id = str(payload.get("job_id") or job_id or "")
    file_path = payload.get("file_path")
    if not file_path:
        return read_replay_payload(requested_job_id or None)

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


def snapshot_time(summary: dict) -> str:
    return str(summary.get("last_processed_at") or summary.get("completed_at") or datetime.now(timezone.utc).isoformat())


def latest_completed_job_summary() -> dict:
    record = read_latest_upload_record() or {}
    result = record.get("result") if isinstance(record.get("result"), dict) else None
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else None
    if result and has_active_session_artifact(result):
        return summary or summarize_result(result)
    return {}
