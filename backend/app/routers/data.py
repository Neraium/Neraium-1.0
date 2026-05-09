from pathlib import Path
from typing import Any
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.core.security import require_api_access
from app.services.sii_runner import read_latest_sii_state
from app.services.upload_jobs import (
    create_upload_job,
    delete_upload_file,
    latest_completed_job_summary,
    process_upload_job,
    read_job,
)

router = APIRouter(tags=["data"], dependencies=[Depends(require_api_access)])
logger = logging.getLogger(__name__)


def upload_status_payload(metadata: dict[str, Any] | None, job_id: str | None = None) -> dict[str, Any]:
    if metadata is None:
        return {
            "job_id": job_id,
            "status": "NOT_FOUND",
            "progress": 0,
            "processing_state": "not_found",
            "progress_label": "Upload job was not found.",
            "message": "Telemetry upload interrupted.",
            "error_type": "job_not_found",
            "filename": None,
            "file_size_bytes": 0,
            "rows_processed": 0,
            "columns_detected": 0,
            "chunk_count": 0,
            "memory_estimate_bytes": 0,
            "processing_duration_seconds": None,
            "engine_runtime_seconds": None,
            "runner_used": False,
            "runner_module": None,
            "core_engine": None,
            "started_at": None,
            "completed_at": None,
            "error": "Upload job was not found.",
            "result_summary": None,
        }

    normalized_status = str(metadata.get("status", "PENDING")).upper()
    progress_map = {
        "PENDING": 8,
        "PARSING": 22,
        "BASELINE_MODELING": 42,
        "RUNNING_SII": 68,
        "GENERATING_EVIDENCE": 86,
        "COMPLETE": 100,
        "FAILED": 100,
    }
    message_map = {
        "PENDING": "Telemetry batch processing in progress.",
        "PARSING": "Telemetry batch processing in progress.",
        "BASELINE_MODELING": "Large telemetry uploads may require additional processing time.",
        "RUNNING_SII": "Telemetry batch processing in progress.",
        "GENERATING_EVIDENCE": "Telemetry batch processing in progress.",
        "COMPLETE": "Telemetry processing complete.",
        "FAILED": "Telemetry processing failed.",
    }
    error_type = "sii_processing_failure" if normalized_status == "FAILED" else None
    return {
        "job_id": metadata.get("job_id"),
        "status": normalized_status,
        "progress": progress_map.get(normalized_status, 0),
        "processing_state": normalized_status.lower(),
        "progress_label": metadata.get("progress_label"),
        "message": message_map.get(normalized_status, "Telemetry processing in progress."),
        "error_type": error_type,
        "filename": metadata.get("filename"),
        "file_size_bytes": metadata.get("file_size_bytes", 0),
        "rows_processed": metadata.get("rows_processed", 0),
        "columns_detected": metadata.get("columns_detected", 0),
        "chunk_count": metadata.get("chunk_count", 0),
        "memory_estimate_bytes": metadata.get("memory_estimate_bytes", 0),
        "processing_duration_seconds": metadata.get("processing_duration_seconds"),
        "engine_runtime_seconds": metadata.get("engine_runtime_seconds"),
        "runner_used": metadata.get("runner_used", False),
        "runner_module": metadata.get("runner_module"),
        "core_engine": metadata.get("core_engine"),
        "started_at": metadata.get("started_at"),
        "completed_at": metadata.get("completed_at"),
        "error": metadata.get("error"),
        "result_summary": metadata.get("result_summary"),
    }


@router.post("/data/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    metadata = await create_upload_job(file)
    if metadata["file_size_bytes"] == 0:
        delete_upload_file(metadata)
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    background_tasks.add_task(process_upload_job, metadata["job_id"])
    logger.info(
        "upload_job_accepted job_id=%s filename=%s size_bytes=%s",
        metadata["job_id"],
        metadata["filename"],
        metadata["file_size_bytes"],
    )
    return {
        "job_id": metadata["job_id"],
        "status": metadata["status"],
        "progress": 8,
        "processing_state": "pending",
        "error_type": None,
        "filename": metadata["filename"],
        "message": "Telemetry batch received. Processing started.",
        "status_url": f"/api/data/upload-status/{metadata['job_id']}",
        "file_size_bytes": metadata["file_size_bytes"],
    }


@router.get("/data/upload-status/{job_id}")
def read_upload_status(job_id: str) -> dict[str, Any]:
    metadata = read_job(job_id)
    if metadata is None:
        logger.warning("upload_status_not_found job_id=%s", job_id)
        return JSONResponse(status_code=404, content=upload_status_payload(None, job_id))
    payload = upload_status_payload(metadata, job_id)
    logger.info(
        "upload_status_polled job_id=%s status=%s rows=%s chunks=%s",
        payload["job_id"],
        payload["status"],
        payload["rows_processed"],
        payload["chunk_count"],
    )
    return payload


@router.get("/data/latest-upload")
def read_latest_upload() -> dict[str, Any]:
    summary = latest_completed_job_summary()
    latest_state = read_latest_sii_state()
    if summary is None and latest_state is None:
        return {
            "source": "sample",
            "last_filename": None,
            "rows_processed": 0,
            "columns_detected": 0,
            "last_processed_at": None,
            "runner_module": None,
            "core_engine": None,
            "state_available": False,
        }
    summary = summary or {}
    last_processed_at = summary.get("last_processed_at")
    if last_processed_at is None and latest_state:
        last_processed_at = latest_state.get("last_processed_at")
    return {
        "source": "uploaded",
        "last_filename": summary.get("filename"),
        "rows_processed": summary.get("rows_processed", 0),
        "columns_detected": summary.get("columns_detected", 0),
        "last_processed_at": last_processed_at,
        "runner_module": summary.get("runner_module") or (latest_state or {}).get("runner_module"),
        "core_engine": summary.get("core_engine") or (latest_state or {}).get("core_engine"),
        "state_available": latest_state is not None,
        "runner_used": summary.get("runner_used", False),
        "chunk_count": summary.get("chunk_count", 0),
        "memory_estimate_bytes": summary.get("memory_estimate_bytes", 0),
        "engine_runtime_seconds": summary.get("engine_runtime_seconds"),
    }
