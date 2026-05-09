from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status

from app.services.sii_runner import read_latest_sii_state
from app.services.upload_jobs import (
    create_upload_job,
    latest_completed_job_summary,
    process_upload_job,
    read_job,
)

router = APIRouter(tags=["data"])


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
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    background_tasks.add_task(process_upload_job, metadata["job_id"])
    return {
        "job_id": metadata["job_id"],
        "status": metadata["status"],
        "filename": metadata["filename"],
        "message": "Telemetry batch received. Processing started.",
        "status_url": f"/api/data/upload-status/{metadata['job_id']}",
        "file_size_bytes": metadata["file_size_bytes"],
    }


@router.get("/data/upload-status/{job_id}")
def read_upload_status(job_id: str) -> dict[str, Any]:
    metadata = read_job(job_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Upload job was not found.")
    return {
        "job_id": metadata["job_id"],
        "status": metadata.get("status", "queued"),
        "progress_label": metadata.get("progress_label"),
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
