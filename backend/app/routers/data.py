from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse
from app.services import adaptive_learning
from app.services.evidence_store import upsert_evidence_run
from app.services import upload_jobs
from app.services.sii_runner import CORE_ENGINE, RUNNER_MODULE
from app.services.runtime_db import record_audit_event

router = APIRouter(prefix="/data", tags=["data"])
logger = logging.getLogger(__name__)


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
        if lowered.endswith(".json") or "json" in content_type:
            summary = upload_jobs.process_json_payload(content, filename=filename)
        else:
            with NamedTemporaryFile(delete=False, suffix=".csv") as temp:
                temp.write(content)
                temp_path = temp.name
            try:
                result = upload_jobs.process_csv_file(temp_path, filename=filename)
            finally:
                Path(temp_path).unlink(missing_ok=True)
            summary = upload_jobs.read_latest_upload_summary() or {}
            summary["job_id"] = result.get("job_id", summary.get("job_id"))
            summary["filename"] = filename
            summary["runner_used"] = settings.process_role != "api"
            summary["runner_module"] = RUNNER_MODULE
            summary["core_engine"] = CORE_ENGINE
            upload_jobs.write_latest_upload_summary(summary)
            latest_result = result or upload_jobs.read_latest_upload_result() or {}
            if latest_result:
                latest_result["filename"] = filename
                latest_result["job_id"] = summary.get("job_id")
                upload_jobs.write_latest_upload_result(summary.get("job_id"), latest_result)
                upload_jobs.write_latest_upload_result(latest_result)
        record_audit_event(
            actor=actor,
            action="upload.accepted",
            resource_type="upload_job",
            resource_id=str(summary.get("job_id") or "unknown"),
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
                    "status": "completed",
                    "created_at": summary.get("last_processed_at"),
                    "completed_at": summary.get("last_processed_at"),
                    "rows_received": summary.get("rows_processed", summary.get("row_count", 0)),
                    "rows_accepted": summary.get("rows_processed", summary.get("row_count", 0)),
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
    status = upload_jobs.read_upload_status(job_id)
    if status:
        return normalize_upload_status_payload(status)
    latest_summary = upload_jobs.read_latest_upload_summary() or {}
    if str(latest_summary.get("job_id") or "") == str(job_id):
        return normalize_upload_status_payload(latest_summary)
    payload = {
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
    }
    logger.warning(
        "upload_status_missing polling_job_id=%s validation_failure_reason=upload_session_missing metadata_exists=False",
        job_id,
    )
    return JSONResponse(
        status_code=404,
        content=payload,
    )


@router.get("/latest-upload")
async def latest_upload(include_persisted: int | bool = True):
    result = upload_jobs.read_latest_upload_result()
    summary = latest_completed_job_summary() or {}
    history = upload_jobs.read_upload_history(limit=20)
    replay = (result or {}).get("replay_timeline") or {}
    frames = replay.get("timeline") if isinstance(replay, dict) else []
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
        "source": "uploaded" if result else "none",
        "last_filename": (result or {}).get("filename") or summary.get("filename"),
        "rows_processed": (result or {}).get("row_count") or summary.get("rows_processed") or summary.get("row_count") or 0,
        "columns_detected": (result or {}).get("column_count") or summary.get("columns_detected") or summary.get("column_count") or 0,
        "state_available": bool(result),
        "status": summary.get("status", "COMPLETE" if result else "empty"),
        "processing_state": summary.get("processing_state", "complete" if result else "empty"),
        "result_available": bool(result),
        "sii_completed": bool(result),
        "replay_ready": bool(frames),
        "replay_frame_count": len(frames or []),
        "latest_replay_frames": len(frames or []),
        "replay_source": "persisted" if frames else "unknown",
    }
    if history and snapshot.get("last_filename"):
        history[0]["filename"] = snapshot["last_filename"]
    return {
        "snapshot": snapshot,
        "latest_result": result,
        "latestResult": result,
        "summary": summary,
        "history": history,
        "adaptive_learning": adaptive,
        **snapshot,
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
    return {"pending": 0, "processing": 0}


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
