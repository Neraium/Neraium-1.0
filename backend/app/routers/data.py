from pathlib import Path
from typing import Any
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from app.core.security import require_api_access
from app.models.api_models import LatestUploadResponse, UploadAcceptedResponse, UploadStatusResponse
from app.services.data_connections import read_connection_status
from app.services.runtime_db import record_audit_event
from app.services.sii_runner import read_latest_sii_state
from app.services.upload_jobs import (
    create_upload_job,
    delete_upload_file,
    latest_completed_job_summary,
    process_next_queued_upload_job,
    read_upload_history,
    read_latest_upload_result,
    read_job,
)

router = APIRouter(tags=["data"], dependencies=[Depends(require_api_access)])
logger = logging.getLogger(__name__)
DEFAULT_CONNECTION_ID = "node-red-cultivation-telemetry"


def upload_status_payload(metadata: dict[str, Any] | None, job_id: str | None = None) -> dict[str, Any]:
    if metadata is None:
        return {
            "job_id": job_id,
            "status": "NOT_FOUND",
            "progress": 0,
            "processing_state": "not_found",
            "progress_label": "Upload session expired or was not found.",
            "message": "Upload session expired or was not found.",
            "error_type": "upload_session_missing",
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
            "error": "upload_session_missing",
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


@router.post("/data/upload", status_code=status.HTTP_202_ACCEPTED, response_model=UploadAcceptedResponse)
async def upload_csv(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    filename = file.filename or ""
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    auth_context = getattr(request.state, "auth_context", {})
    metadata = await create_upload_job(file, initiated_by=auth_context.get("auth_subject", "anonymous"))
    if metadata["file_size_bytes"] == 0:
        delete_upload_file(metadata)
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    background_tasks.add_task(process_next_queued_upload_job)
    logger.info(
        "upload_job_accepted job_id=%s returned_job_id=%s filename=%s size_bytes=%s auth_subject=%s auth_source=%s metadata_exists=%s",
        metadata["job_id"],
        metadata["job_id"],
        metadata["filename"],
        metadata["file_size_bytes"],
        auth_context.get("auth_subject", "unknown"),
        auth_context.get("auth_source", "unknown"),
        read_job(metadata["job_id"]) is not None,
    )
    record_audit_event(
        actor=auth_context.get("auth_subject", "unknown"),
        action="upload.accepted",
        resource_type="upload_job",
        resource_id=metadata["job_id"],
        request_id=auth_context.get("request_id"),
        detail={"filename": metadata["filename"], "size_bytes": metadata["file_size_bytes"]},
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


@router.get("/data/upload-status/{job_id}", response_model=UploadStatusResponse)
def read_upload_status(request: Request, job_id: str) -> dict[str, Any]:
    metadata = read_job(job_id)
    auth_context = getattr(request.state, "auth_context", {})
    if metadata is None:
        latest_summary = latest_completed_job_summary()
        if latest_summary and latest_summary.get("job_id") == job_id:
            return upload_status_payload(completed_metadata_from_summary(job_id, latest_summary), job_id)
        logger.warning(
            "upload_status_not_found polling_job_id=%s auth_subject=%s auth_source=%s metadata_exists=%s validation_failure_reason=%s",
            job_id,
            auth_context.get("auth_subject", "unknown"),
            auth_context.get("auth_source", "unknown"),
            False,
            "upload_session_missing",
        )
        return JSONResponse(status_code=404, content=upload_status_payload(None, job_id))
    payload = upload_status_payload(metadata, job_id)
    logger.info(
        "upload_status_polled polling_job_id=%s persisted_job_id=%s status=%s rows=%s chunks=%s auth_subject=%s auth_source=%s metadata_exists=%s",
        job_id,
        payload["job_id"],
        payload["status"],
        payload["rows_processed"],
        payload["chunk_count"],
        auth_context.get("auth_subject", "unknown"),
        auth_context.get("auth_source", "unknown"),
        True,
    )
    return payload


def completed_metadata_from_summary(job_id: str, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "filename": summary.get("filename"),
        "file_size_bytes": summary.get("file_size_bytes", 0),
        "status": "COMPLETE",
        "rows_processed": summary.get("rows_processed", 0),
        "columns_detected": summary.get("columns_detected", 0),
        "chunk_count": summary.get("chunk_count", 0),
        "memory_estimate_bytes": summary.get("memory_estimate_bytes", 0),
        "processing_duration_seconds": summary.get("processing_duration_seconds"),
        "engine_runtime_seconds": summary.get("engine_runtime_seconds"),
        "runner_used": summary.get("runner_used", False),
        "runner_module": summary.get("runner_module"),
        "core_engine": summary.get("core_engine"),
        "started_at": summary.get("started_at"),
        "completed_at": summary.get("last_processed_at"),
        "error": None,
        "result_summary": summary,
    }


@router.get("/data/latest-upload", response_model=LatestUploadResponse)
def read_latest_upload() -> dict[str, Any]:
    summary = latest_completed_job_summary()
    detailed_result = read_latest_upload_result()
    latest_state = read_latest_sii_state()
    try:
        live_connection = read_connection_status(DEFAULT_CONNECTION_ID)
    except ValueError:
        live_connection = None
    valid_sources = {"uploaded", "rest_poll"}
    if latest_state is not None and latest_state.get("source") not in valid_sources:
        latest_state = None
    if summary is None and latest_state is None and detailed_result is None:
        baseline_status = live_connection.get("baseline_status") if live_connection else None
        status = "building_baseline" if baseline_status == "building" else "empty"
        message = (
            "Building live baseline from REST telemetry."
            if baseline_status == "building"
            else "No data connected yet."
        )
        payload = {
            "status": status,
            "source": "none",
            "message": message,
            "last_filename": None,
            "rows_processed": 0,
            "columns_detected": 0,
            "last_processed_at": None,
            "runner_module": None,
            "core_engine": None,
            "state_available": False,
            "connection_status": "no_data",
            "result_source": None,
            "history": [],
            "latest_result": None,
            "baseline_source": live_connection.get("baseline_source") if live_connection else None,
            "baseline_status": baseline_status,
            "baseline_samples_collected": live_connection.get("baseline_samples_collected", 0) if live_connection else 0,
            "baseline_samples_required": live_connection.get("baseline_samples_required", 0) if live_connection else 0,
            "last_baseline_update": live_connection.get("last_baseline_update") if live_connection else None,
        }
        logger.info("latest_result_served status=%s source=%s state_available=%s", payload["status"], payload["source"], payload["state_available"])
        return payload
    summary = summary or {}
    last_processed_at = summary.get("last_processed_at")
    if last_processed_at is None and latest_state:
        last_processed_at = latest_state.get("last_processed_at")
    if last_processed_at is None and detailed_result:
        last_processed_at = (
            detailed_result.get("sii_intelligence", {}).get("last_updated")
            or detailed_result.get("processing_trace", {}).get("completed_at")
        )
    last_filename = summary.get("filename")
    if last_filename is None and detailed_result:
        last_filename = detailed_result.get("filename")
    rows_processed = summary.get("rows_processed", 0)
    if not rows_processed and detailed_result:
        rows_processed = detailed_result.get("row_count", 0)
    columns_detected = summary.get("columns_detected", 0)
    if not columns_detected and detailed_result:
        columns_detected = detailed_result.get("column_count", 0)
    payload = {
        "status": "active" if detailed_result is not None else ("baseline_active" if (live_connection or {}).get("baseline_status") == "active" else "building_baseline"),
        "source": summary.get("source") or (detailed_result or {}).get("sii_intelligence", {}).get("source") or "uploaded",
        "message": (
            "Latest result active."
            if detailed_result is not None
            else "Live baseline active. Waiting for the next telemetry comparison."
        ),
        "last_filename": last_filename,
        "rows_processed": rows_processed,
        "columns_detected": columns_detected,
        "last_processed_at": last_processed_at,
        "runner_module": summary.get("runner_module") or (latest_state or {}).get("runner_module"),
        "core_engine": summary.get("core_engine") or (latest_state or {}).get("core_engine"),
        "state_available": latest_state is not None,
        "connection_status": "connected",
        "result_source": summary.get("upload_result_source") or "file_upload",
        "history": read_upload_history(limit=6),
        "runner_used": summary.get("runner_used", False),
        "chunk_count": summary.get("chunk_count", 0),
        "memory_estimate_bytes": summary.get("memory_estimate_bytes", 0),
        "engine_runtime_seconds": summary.get("engine_runtime_seconds"),
        "latest_result": detailed_result,
        "baseline_source": summary.get("baseline_source") or (live_connection or {}).get("baseline_source"),
        "baseline_status": summary.get("baseline_status") or (live_connection or {}).get("baseline_status"),
        "baseline_samples_collected": summary.get("baseline_samples_collected", (live_connection or {}).get("baseline_samples_collected", 0)),
        "baseline_samples_required": summary.get("baseline_samples_required", (live_connection or {}).get("baseline_samples_required", 0)),
        "last_baseline_update": summary.get("last_baseline_update") or (live_connection or {}).get("last_baseline_update"),
    }
    logger.info(
        "latest_result_served status=%s source=%s filename=%s rows=%s columns=%s state_available=%s",
        payload["status"],
        payload["source"],
        payload["last_filename"],
        payload["rows_processed"],
        payload["columns_detected"],
        payload["state_available"],
    )
    return payload
