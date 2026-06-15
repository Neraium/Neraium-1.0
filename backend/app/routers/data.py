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

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from app.services.evidence_store import read_evidence_run, upsert_evidence_run
from app.services import upload_jobs
from app.services.upload_jobs import build_evidence_record_from_result
from app.services.upload_status_contract import normalize_upload_status_payload
from app.services.system_interpretation import build_system_interpretation as _build_system_interpretation
from app.services.sii_runner import CORE_ENGINE, RUNNER_MODULE
from app.services.runtime_db import record_audit_event
from app.services.runtime_db import enqueue_upload_job
from app.services.runtime_db import queue_metrics as runtime_queue_metrics
from app.services.runtime_db import read_upload_queue_job, touch_upload_queue_job, peek_next_upload_job_for_worker
from app.services.runtime_db import configure_runtime_dir as configure_runtime_db_dir

router = APIRouter(prefix="/data", tags=["data"])
logger = logging.getLogger(__name__)
UPLOAD_JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)
def _clear_endpoint_caches() -> None:
    return None


def invalidate_latest_upload_cache() -> None:
    return None


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


def _dispatch_upload_worker_for_runtime(runtime_dir: Path) -> None:
    logger.info("worker_dispatch_requested runtime_dir=%s", runtime_dir)
    try:
        worker = threading.Thread(
            target=_run_upload_worker_for_runtime,
            args=(runtime_dir,),
            daemon=True,
            name="upload-worker-dispatch",
        )
        worker.start()
    except Exception:
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
        return failed




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
    latest_record = upload_jobs.read_latest_upload_record() or {}
    latest_summary = latest_record.get("summary") if isinstance(latest_record.get("summary"), dict) else {}
    if str(latest_summary.get("job_id") or latest_record.get("job_id") or "") == str(job_id):
        normalized = normalize_upload_status_payload(latest_summary)
        normalized.setdefault("state_backend", state_backend)
        return _with_worker_visibility(normalized, job_id)
    latest_result = upload_jobs.read_upload_result_by_job_id(job_id)
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
            "progress_label": "Telemetry processing complete.",
            "message": "Telemetry processing complete.",
            "error": None,
            "propagation_stage": "complete",
            "propagation_progress": 100,
            "propagation_label": "Complete.",
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


@router.post("/upload", status_code=202)
async def upload_data(request: Request, file: UploadFile = File(...)):
    settings = request.app.state.settings
    filename = file.filename or "upload.csv"
    lowered = filename.lower()
    if not (lowered.endswith(".csv") or lowered.endswith(".json") or lowered.endswith(".txt")):
        return JSONResponse(
            status_code=400,
            content={
                "status": "FAILED",
                "processing_state": "failed",
                "message": "Only .csv, .txt, and .json telemetry files are supported.",
            },
        )

    max_size_bytes = int(getattr(settings, "max_upload_size_bytes", 250 * 1024 * 1024))
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
                            "message": f"Upload exceeds maximum allowed size of {max_size_bytes} bytes.",
                        },
                    )
                if lowered.endswith(".csv") and not csv_has_non_whitespace and chunk.strip():
                    csv_has_non_whitespace = True
                temp.write(chunk)

        if lowered.endswith(".csv") and (file_size_bytes == 0 or not csv_has_non_whitespace):
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
            return JSONResponse(
                status_code=400,
                content={
                    "status": "FAILED",
                    "processing_state": "failed",
                    "message": "CSV file is empty.",
                },
            )

        job_id = uuid.uuid4().hex
        summary = {
            "job_id": job_id,
            "filename": filename,
            "status_url": f"/api/data/upload-status/{job_id}",
            "status": "PENDING",
            "processing_state": "queued",
            "percent": 0,
            "progress": 0,
            "message": "Upload accepted. Processing is queued.",
            "propagation_stage": "queued",
            "propagation_progress": 10,
            "propagation_label": "Queued.",
            "runner_used": False if str(getattr(settings, "process_role", "")).lower() == "api" else True,
            "runner_module": RUNNER_MODULE,
            "core_engine": CORE_ENGINE,
            "file_path": temp_path,
            "file_size_bytes": file_size_bytes,
            "content_type": content_type,
            "initiated_by": actor,
        }
        upload_jobs.write_job(summary)
        enqueue_upload_job(job_id)
        _dispatch_upload_worker_for_runtime(request.app.state.settings.runtime_dir)
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
            record = upsert_evidence_run(
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
            if record:
                upsert_evidence_run(record)
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
        "filename": filename,
        "message": "Preparing telemetry intake. Upload received and queued for background processing.",
        "status_url": f"/api/data/upload-status/{summary.get('job_id')}",
        "file_size_bytes": file_size_bytes,
        "propagation_stage": "accepted",
        "propagation_progress": 5,
        "propagation_label": "Upload received.",
        "worker_state": "starting",
        "worker_last_seen_at": datetime.now(timezone.utc).isoformat(),
        "queue_position": None,
        "queued_seconds": 0,
        "status_checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/upload-status/{job_id}")
async def upload_status(job_id: str):
    state_backend = upload_jobs.upload_state_backend()
    logger.warning("upload_status_request job_id=%s state_backend=%s", job_id, state_backend)
    try:
        normalized = _resolve_upload_status_payload(job_id, state_backend)
        if str(normalized.get("status", "")).upper() == "NOT_FOUND":
            logger.warning(
                "upload_status_missing polling_job_id=%s validation_failure_reason=upload_session_missing metadata_exists=False",
                job_id,
            )
            logger.warning("upload_status_response job_id=%s status_code=%s payload_status=%s cached=%s", job_id, 404, "NOT_FOUND", False)
            return JSONResponse(status_code=404, content=normalized)

        if str(normalized.get("status", "")).upper() in {"COMPLETE", "FAILED"}:
            if str(normalized.get("status", "")).upper() == "COMPLETE":
                existing = read_evidence_run(str(job_id))
                if isinstance(existing, dict) and str(existing.get("status", "")).lower() == "queued":
                    now = datetime.now(timezone.utc).isoformat()
                    upload_result = upload_jobs.read_upload_result_by_job_id(job_id) or {}
                    enriched = build_evidence_record_from_result(
                        run_id=str(job_id),
                        filename=str(upload_result.get("filename") or existing.get("source_name") or "upload.csv"),
                        source_type=str(existing.get("source_type") or "csv_upload"),
                        result=upload_result,
                        created_at=str(existing.get("created_at") or now),
                        completed_at=now,
                        status="completed",
                        initiated_by=str(existing.get("initiated_by") or "anonymous"),
                    )
                    upsert_evidence_run({**existing, **enriched, "status": "completed", "completed_at": now})
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
                            "observation_status": "failed",
                        }
                    )
        logger.warning("upload_status_response job_id=%s status_code=%s payload_status=%s cached=%s", job_id, 200, str(normalized.get("status", "")).upper(), False)
        return normalized
    except Exception:
        logger.exception("upload_status_error job_id=%s state_backend=%s", job_id, state_backend)
        raise


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
    use_persisted = bool(include_persisted)
    state_backend = upload_jobs.upload_state_backend()
    canonical = upload_jobs.read_latest_upload_record() if use_persisted else upload_jobs.build_empty_latest_upload_record()
    if upload_jobs.reset_block_persisted_active():
        canonical = upload_jobs.build_empty_latest_upload_record()

    if not isinstance(canonical, dict):
        canonical = upload_jobs.build_empty_latest_upload_record()

    summary = canonical.get("summary") if isinstance(canonical.get("summary"), dict) else {}
    result = canonical.get("result") if isinstance(canonical.get("result"), dict) else None
    canonical_job_id = str(canonical.get("job_id") or summary.get("job_id") or (result or {}).get("job_id") or "").strip()
    canonical_status = str(canonical.get("status") or summary.get("processing_state") or summary.get("status") or "empty").strip().lower()
    processing_states = {
        "queued", "pending", "processing", "parsing_telemetry", "building_relationship_baselines",
        "scoring_relationship_drift", "building_propagation_model", "generating_system_interpretation",
    }
    complete_states = {"complete", "partial_complete", "active"}

    has_result = bool(result) and upload_jobs.has_active_session_artifact(result, job_id=canonical_job_id)
    has_summary = bool(summary) and (
        upload_jobs.has_active_session_artifact(summary, job_id=canonical_job_id)
        or canonical_status in processing_states
        or canonical_status in complete_states
    )

    if canonical_status in complete_states and not has_result:
        canonical = upload_jobs.build_empty_latest_upload_record()
        summary = {}
        result = None
        canonical_job_id = ""
        canonical_status = "empty"
        has_summary = False
    elif not has_result and not has_summary:
        canonical = upload_jobs.build_empty_latest_upload_record()
        summary = {}
        result = None
        canonical_job_id = ""
        canonical_status = "empty"

    history = []
    if use_persisted and canonical_job_id and (has_result or has_summary):
        history = [item for item in upload_jobs.read_upload_history(limit=20) if isinstance(item, dict)]
        current_history = next((item for item in history if str(item.get("job_id") or "") == canonical_job_id), None)
        if current_history is None and summary:
            current_history = dict(summary)
        remaining = [item for item in history if str(item.get("job_id") or "") != canonical_job_id]
        history = ([current_history] if current_history else []) + remaining

    frames = canonical.get("replay", {}).get("timeline") if isinstance(canonical.get("replay"), dict) else None
    if not isinstance(frames, list):
        frames = _extract_timeline(result if isinstance(result, dict) else None, canonical_job_id or None)
    traceability = canonical.get("traceability") if isinstance(canonical.get("traceability"), dict) else {}
    state_available = bool(result)
    snapshot_status = "COMPLETE" if state_available else (summary.get("status") if isinstance(summary, dict) else canonical_status or "empty")
    snapshot_processing_state = "complete" if state_available else (summary.get("processing_state") if isinstance(summary, dict) else canonical_status or "empty")
    snapshot = {
        **(summary if isinstance(summary, dict) else {}),
        "state_backend": state_backend,
        "source": "uploaded" if state_available else ("processing" if canonical_job_id and canonical_status in processing_states else "none"),
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
    if state_available or canonical_job_id:
        system_interpretation = _build_system_interpretation(result if isinstance(result, dict) else None, summary if isinstance(summary, dict) else None, snapshot, frames if isinstance(frames, list) else [])
    else:
        system_interpretation = _build_system_interpretation(None, None, {}, [])
    response_payload = {
        "snapshot": snapshot,
        "current_upload": canonical,
        "latest_result": result,
        "latestResult": result,
        "summary": summary if isinstance(summary, dict) else {},
        "history": history if state_available or canonical_job_id else [],
        "adaptive_learning": {},
        "state_backend": state_backend,
        "system_interpretation": system_interpretation,
        **snapshot,
    }
    return response_payload


@router.get("/system-interpretation")
async def system_interpretation_contract(include_persisted: int | bool = True):
    payload = await latest_upload(include_persisted=include_persisted)
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


def snapshot_time(summary: dict) -> str:
    return str(summary.get("last_processed_at") or summary.get("completed_at") or datetime.now(timezone.utc).isoformat())


def latest_completed_job_summary() -> dict:
    record = upload_jobs.read_latest_upload_record() or {}
    result = record.get("result") if isinstance(record.get("result"), dict) else None
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else None
    if result and upload_jobs.has_active_session_artifact(result):
        return summary or upload_jobs.summarize_result(result)
    return {}
