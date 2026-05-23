from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Request, UploadFile
from fastapi.responses import JSONResponse
from app.services import adaptive_learning
from app.services.evidence_store import upsert_evidence_run
from app.services import upload_jobs
from app.services.sii_runner import CORE_ENGINE, RUNNER_MODULE

router = APIRouter(prefix="/data", tags=["data"])
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_upload_failure(job_id: str, filename: str, actor: str, exc: Exception) -> None:
    failed_at = _now_iso()
    error_message = str(exc)
    upload_jobs.write_job(
        {
            "job_id": job_id,
            "filename": filename,
            "status": "FAILED",
            "processing_state": "failed",
            "percent": 100,
            "progress": 100,
            "error": error_message,
            "errors": [error_message],
            "message": "Telemetry processing failed.",
            "progress_label": "Telemetry processing failed.",
            "result_available": False,
            "completed_at": failed_at,
        }
    )
    upsert_evidence_run(
        {
            "run_id": job_id,
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
            "errors": [error_message],
            "primary_drivers": [],
            "evidence_summary": [],
            "structural_archetypes": [],
            "initiated_by": actor,
            "adaptive_site_key": "site::default",
            "operator_feedback_history": [],
        }
    )


def _process_uploaded_file(job_id: str, file_path: str, filename: str, content_type: str, actor: str) -> None:
    try:
        upload_jobs.write_job(
            {
                "job_id": job_id,
                "filename": filename,
                "status": "RUNNING_SII",
                "processing_state": "running_sii",
                "percent": 18,
                "progress": 18,
                "message": "Telemetry batch processing in progress.",
                "progress_label": "Parsing uploaded telemetry file.",
                "result_available": False,
                "started_at": _now_iso(),
            }
        )
        lowered = filename.lower()
        path = Path(file_path)
        if lowered.endswith(".json") or "json" in content_type:
            content = path.read_bytes()
            summary = upload_jobs.process_json_payload(content, filename=filename)
            summary["job_id"] = job_id
        else:
            content = path.read_bytes()
            summary = upload_jobs.process_upload_bytes(filename, content, job_id=job_id)
            summary["job_id"] = job_id
            summary["filename"] = filename
            summary["runner_used"] = True
            summary["runner_module"] = RUNNER_MODULE
            summary["core_engine"] = CORE_ENGINE
            summary["last_processed_at"] = summary.get("last_processed_at") or _now_iso()
            upload_jobs.write_latest_upload_summary(summary)
            latest_result = upload_jobs.read_latest_upload_result() or {}
            if latest_result:
                latest_result["filename"] = filename
                latest_result["job_id"] = job_id
                upload_jobs.write_latest_upload_result(job_id, latest_result)
                upload_jobs.write_latest_upload_result(latest_result)

        summary = dict(summary or {})
        summary["job_id"] = job_id
        summary["filename"] = filename
        summary["status"] = "COMPLETE"
        summary["processing_state"] = "complete"
        summary["percent"] = 100
        summary["progress"] = 100
        summary["message"] = "Telemetry processing complete."
        summary["progress_label"] = "Telemetry processing complete."
        summary["result_available"] = True
        upload_jobs.write_job(summary)
        upload_jobs.write_latest_upload_summary(summary)

        upsert_evidence_run(
            {
                "run_id": job_id,
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
    except Exception as exc:
        logger.exception("upload_processing_failed job_id=%s filename=%s", job_id, filename)
        _write_upload_failure(job_id, filename, actor, exc)
    finally:
        Path(file_path).unlink(missing_ok=True)


@router.post("/upload", status_code=202)
async def upload_data(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    settings = request.app.state.settings
    max_size_bytes = int(getattr(settings, "max_upload_size_bytes", 250 * 1024 * 1024))
    filename = file.filename or "upload.csv"
    lowered = filename.lower()
    content_type = (file.content_type or "").lower()
    if not (lowered.endswith(".csv") or lowered.endswith(".json") or "csv" in content_type or "json" in content_type or content_type in {"", "text/plain"}):
        return JSONResponse(
            status_code=400,
            content={"status": "FAILED", "error_type": "unsupported_upload_type", "message": "Only CSV and JSON telemetry files are supported."},
        )

    auth_context = getattr(request.state, "auth_context", {})
    actor = (
        auth_context.get("auth_subject")
        or request.headers.get("X-Neraium-User")
        or request.headers.get("X-Authenticated-User")
        or request.headers.get("X-Forwarded-Email")
        or "anonymous"
    )
    metrics = queue_metrics()
    if int(metrics.get("pending", 0)) >= int(getattr(settings, "max_pending_upload_jobs", 3)):
        return JSONResponse(
            status_code=503,
            headers={"retry-after": "30"},
            content={"status": "FAILED", "error_type": "upload_queue_saturated", "message": "Upload queue is saturated. Retry shortly."},
        )

    suffix = ".json" if lowered.endswith(".json") or "json" in content_type else ".csv"
    job_id = uuid.uuid4().hex
    bytes_written = 0
    with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp_path = temp.name
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > max_size_bytes:
                Path(temp_path).unlink(missing_ok=True)
                return JSONResponse(
                    status_code=413,
                    content={"status": "FAILED", "error_type": "upload_too_large", "message": f"Upload exceeds maximum allowed size of {max_size_bytes} bytes."},
                )
            temp.write(chunk)

    if bytes_written <= 0:
        Path(temp_path).unlink(missing_ok=True)
        return JSONResponse(status_code=400, content={"status": "FAILED", "error_type": "empty_upload", "message": "Uploaded telemetry file is empty."})

    queued_at = _now_iso()
    upload_jobs.write_job(
        {
            "job_id": job_id,
            "filename": filename,
            "status": "PENDING",
            "processing_state": "pending",
            "percent": 8,
            "progress": 8,
            "message": "Upload received and queued for background processing.",
            "progress_label": "File accepted. Background intake job is queued.",
            "file_size_bytes": bytes_written,
            "bytes_processed": bytes_written,
            "rows_processed": 0,
            "columns_detected": 0,
            "result_available": False,
            "started_at": queued_at,
            "initiated_by": actor,
        }
    )
    background_tasks.add_task(_process_uploaded_file, job_id, temp_path, filename, content_type, actor)
    return {
        "job_id": job_id,
        "status": "PENDING",
        "processing_state": "pending",
        "stage": "pending",
        "percent": 8,
        "progress": 8,
        "filename": filename,
        "message": "Preparing telemetry intake. Upload received and queued for background processing.",
        "status_url": f"/api/data/upload-status/{job_id}",
        "result_url": f"/api/data/intake/{job_id}/result",
        "file_size_bytes": bytes_written,
        "bytes_processed": bytes_written,
        "result_available": False,
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
    logger.warning("upload_status_missing polling_job_id=%s validation_failure_reason=upload_session_missing metadata_exists=False", job_id)
    return JSONResponse(status_code=404, content=payload)


@router.get("/latest-upload")
async def latest_upload(include_persisted: int | bool = True):
    result = upload_jobs.read_latest_upload_result()
    summary = upload_jobs.read_latest_upload_summary() or {}
    history = upload_jobs.read_upload_history(limit=20)
    replay = (result or {}).get("replay_timeline") or {}
    frames = replay.get("timeline") if isinstance(replay, dict) else []
    adaptive = adaptive_learning.build_adaptive_snapshot(result, summary) if isinstance(result, dict) else {}
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
    return {"snapshot": snapshot, "latest_result": result, "latestResult": result, "summary": summary, "history": history, "adaptive_learning": adaptive, **snapshot}


@router.get("/replay/{job_id}")
async def data_replay(job_id: str):
    return upload_jobs.replay_payload(job_id)


@router.get("/intake/{job_id}/result")
async def intake_result(job_id: str):
    result = upload_jobs.read_upload_result_by_job_id(job_id)
    if not result:
        return {"job_id": job_id, "result_available": False, "status": "NOT_FOUND", "result": None}
    return {"job_id": job_id, "result_available": True, "status": "COMPLETE", "result": result}


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
    return {"job_id": requested_job_id or result.get("job_id"), "timeline": timeline, "frame_count": len(timeline), "meta": {**(replay.get("meta", {}) if isinstance(replay, dict) else {}), "replay_mode": replay_mode}, "message": "Replay reconstructed from the retained source CSV."}


def queue_metrics() -> dict[str, int]:
    return {"pending": 0, "processing": 0}


def normalize_upload_status_payload(payload: dict) -> dict:
    raw_status = str(payload.get("status", "")).upper()
    status = {"QUEUED": "PENDING", "QUEUE": "PENDING", "FAILED": "FAILED", "FAILURE": "FAILED"}.get(raw_status, raw_status)
    normalized = dict(payload)
    normalized["status"] = status
    normalized.setdefault("job_id", payload.get("job_id"))
    normalized.setdefault("percent", int(payload.get("progress", payload.get("percent", 0)) or 0))
    normalized.setdefault("progress", int(payload.get("percent", payload.get("progress", 0)) or 0))
    if status in {"RUNNING_SII", "PROCESSING", "PENDING", "QUEUED"}:
        normalized.setdefault("message", "Telemetry batch processing in progress.")
    if status == "FAILED":
        normalized.setdefault("progress_label", "Telemetry processing failed.")
        normalized.setdefault("message", normalized.get("error") or "Telemetry processing failed.")
        normalized.setdefault("result_available", False)
    if status == "COMPLETE":
        normalized.setdefault("progress_label", "Telemetry processing complete.")
        normalized.setdefault("message", "Telemetry processing complete.")
        normalized.setdefault("error", None)
        normalized.setdefault("result_available", True)
        normalized.setdefault("result_summary", {"job_id": normalized.get("job_id"), "filename": normalized.get("filename"), "rows_processed": normalized.get("rows_processed", normalized.get("row_count", 0)), "columns_detected": normalized.get("columns_detected", normalized.get("column_count", 0))})
    return normalized
