from pathlib import Path 
from typing import Any 
import logging 

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse

from app.core.security import require_api_access
from app.models.api_models import LatestUploadResponse, UploadAcceptedResponse, UploadStatusResponse
from app.services.data_connections import read_connection_status
from app.services.runtime_db import record_audit_event
from app.services.runtime_db import queue_metrics
from app.services.adaptive_learning import build_adaptive_snapshot
from app.services.sii_runner import read_latest_sii_state
from app.services.sii_runner import reset_latest_sii_state
from app.services.upload_jobs import (
    SUPPORTED_UPLOAD_EXTENSIONS,
    UploadTooLargeError,
    create_upload_job,
    delete_upload_file,
    latest_completed_job_summary,
    now_iso,
    process_next_queued_upload_job,
    process_telemetry_file,
    read_upload_history,
    read_latest_upload_summary,
    read_latest_upload_result,
    read_job,
    reset_latest_upload_state,
    sii_completion_artifacts,
    summarize_result,
    update_job,
    write_latest_upload_summary,
)
from app.services.data_connections import clear_all_connection_runtime_state

router = APIRouter(tags=["data"], dependencies=[Depends(require_api_access)])
logger = logging.getLogger(__name__) 
DEFAULT_CONNECTION_ID = "rest-telemetry-intake" 
MULTIPART_ENVELOPE_ALLOWANCE_BYTES = 5 * 1024 * 1024 


def format_upload_capacity(size_bytes: int) -> str:
    if size_bytes < 1024 * 1024:
        return f"{size_bytes} bytes"
    return f"{size_bytes / (1024 * 1024):.0f} MB"


def upload_status_payload(metadata: dict[str, Any] | None, job_id: str | None = None) -> dict[str, Any]: 
    if metadata is None:
        return {
            "job_id": job_id,
            "status": "NOT_FOUND",
            "progress": 0,
            "processing_state": "not_found",
            "progress_label": "Upload session expired or was not found.",
            "stage": "not_found",
            "percent": 0,
            "message": "Upload session expired or was not found.",
            "error_type": "upload_session_missing",
            "filename": None,
            "file_size_bytes": 0,
            "bytes_processed": 0,
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
            "warnings": [],
            "errors": ["upload_session_missing"],
            "result_available": False,
            "first_usable_available": False,
            "sii_completed": False,
            "sii_completion_artifacts": {},
            "timings": {},
            "result_summary": None, 
            "ingest_request_id": None,
            "request_id": None,
        } 

    normalized_status = str(metadata.get("status", "PENDING")).upper()
    progress_map = {
        "PENDING": 8,
        "VALIDATING_SCHEMA": 18,
        "PARSING": 34,
        "BASELINE_MODELING": 52,
        "RUNNING_SII": 68,
        "STRUCTURAL_SCORING": 68,
        "COGNITION_READY": 78,
        "GENERATING_REPLAY": 88,
        "GENERATING_EVIDENCE": 94,
        "COMPLETE": 100,
        "FAILED": 100,
    }
    message_map = {
        "PENDING": "File accepted. Background intake job is queued.",
        "VALIDATING_SCHEMA": "Validating schema.",
        "PARSING": "Parsing signal matrix.",
        "BASELINE_MODELING": "Building relational baseline.",
        "RUNNING_SII": "Telemetry batch processing in progress.",
        "STRUCTURAL_SCORING": "Computing structural drift.",
        "COGNITION_READY": "Cognition ready; downstream replay/evidence continues.",
        "GENERATING_REPLAY": "Generating replay frames.",
        "GENERATING_EVIDENCE": "Writing evidence and state.",
        "COMPLETE": "Telemetry processing complete.",
        "FAILED": "Telemetry processing failed.",
    }
    error_type = "sii_processing_failure" if normalized_status == "FAILED" else None
    measured_percent = metadata.get("percent") or metadata.get("progress") or progress_map.get(normalized_status, 0)
    summary = metadata.get("result_summary") if isinstance(metadata.get("result_summary"), dict) else {}
    artifacts = metadata.get("sii_completion_artifacts") or summary.get("sii_completion_artifacts") or {}
    sii_completed = bool(metadata.get("sii_completed") or summary.get("sii_completed"))
    is_summary_fallback = bool(metadata.get("summary_fallback"))
    if normalized_status == "COMPLETE" and not sii_completed and not is_summary_fallback:
        normalized_status = "FAILED"
        measured_percent = 100
        error_type = "sii_completion_missing"
    return {
        "job_id": metadata.get("job_id"),
        "status": normalized_status,
        "progress": measured_percent,
        "processing_state": normalized_status.lower(),
        "progress_label": metadata.get("progress_label"),
        "stage": normalized_status.lower(),
        "percent": measured_percent,
        "message": (
            "Telemetry processing failed validation: SII completion artifacts are missing."
            if normalized_status == "FAILED" and error_type == "sii_completion_missing"
            else message_map.get(normalized_status, "Telemetry processing in progress.")
        ),
        "error_type": error_type,
        "filename": metadata.get("filename"),
        "file_size_bytes": metadata.get("file_size_bytes", 0),
        "bytes_processed": metadata.get("bytes_processed", 0),
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
        "warnings": metadata.get("warnings", []),
        "errors": metadata.get("errors", []),
        "result_available": bool(metadata.get("result_available") or normalized_status == "COMPLETE"),
        "first_usable_available": bool(metadata.get("first_usable_available") or normalized_status in {"COGNITION_READY", "GENERATING_REPLAY", "GENERATING_EVIDENCE", "COMPLETE"}),
        "sii_completed": sii_completed and normalized_status == "COMPLETE",
        "sii_completion_artifacts": artifacts if isinstance(artifacts, dict) else {},
        "timings": metadata.get("timings", {}), 
        "result_summary": metadata.get("result_summary"), 
        "ingest_request_id": metadata.get("ingest_request_id"),
        "request_id": None,
    } 


@router.post("/data/upload", status_code=status.HTTP_202_ACCEPTED, response_model=UploadAcceptedResponse)
async def upload_csv(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    settings = request.app.state.settings
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size_bytes = int(content_length)
            if size_bytes > settings.max_upload_size_bytes + MULTIPART_ENVELOPE_ALLOWANCE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "error_type": "upload_too_large",
                        "message": (
                            "High-volume export identified above configured operational intake capacity "
                            f"({format_upload_capacity(settings.max_upload_size_bytes)}). "
                            "Use a partitioned export or enterprise batch intake path."
                        ),
                        "max_upload_size_bytes": settings.max_upload_size_bytes,
                    },
                )
        except ValueError:
            pass

    queue = queue_metrics()
    active_queue_depth = queue.get("pending", 0) + queue.get("processing", 0)
    if active_queue_depth >= settings.max_pending_upload_jobs:
        raise HTTPException(
            status_code=503,
            detail={
                "error_type": "upload_queue_saturated",
                "message": "Upload queue is saturated. Retry after current processing backlog clears.",
                "active_queue_depth": active_queue_depth,
                "max_pending_upload_jobs": settings.max_pending_upload_jobs,
                "retry_after_seconds": 30,
            },
            headers={"Retry-After": "30"},
        )

    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only .csv and .json telemetry files are supported.")

    auth_context = getattr(request.state, "auth_context", {})
    try: 
        metadata = await create_upload_job( 
            file, 
            initiated_by=auth_context.get("auth_subject", "anonymous"), 
            ingest_request_id=auth_context.get("request_id"),
            max_size_bytes=settings.max_upload_size_bytes, 
        ) 
    except UploadTooLargeError:
        logger.warning(
            "upload_rejected_oversize filename=%s max_size_bytes=%s auth_subject=%s auth_source=%s",
            filename,
            settings.max_upload_size_bytes,
            auth_context.get("auth_subject", "unknown"),
            auth_context.get("auth_source", "unknown"),
        )
        raise HTTPException(
            status_code=413,
            detail={
                "error_type": "upload_too_large",
                "message": (
                    "High-volume export identified above configured operational intake capacity "
                    f"({format_upload_capacity(settings.max_upload_size_bytes)}). "
                    "Use a partitioned export or enterprise batch intake path."
                ),
                "max_upload_size_bytes": settings.max_upload_size_bytes,
            },
        ) from None
    if metadata["file_size_bytes"] == 0:
        delete_upload_file(metadata)
        raise HTTPException(status_code=400, detail=f"{extension.upper().lstrip('.')} file is empty.")

    # Always attempt processing after enqueue so uploads work regardless of
    # process role configuration (api/worker/all).
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
        "message": "Preparing telemetry intake. Upload received and queued for background processing.",
        "status_url": f"/api/data/upload-status/{metadata['job_id']}",
        "result_url": f"/api/data/intake/{metadata['job_id']}/result",
        "file_size_bytes": metadata["file_size_bytes"],
        "stage": "pending",
        "percent": 8,
        "bytes_processed": metadata["file_size_bytes"],
        "rows_processed": 0,
        "result_available": False,
        "sii_completed": False,
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
    payload["request_id"] = auth_context.get("request_id")
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


@router.post("/data/upload-reprocess/{job_id}", response_model=UploadAcceptedResponse)
def reprocess_upload_job(job_id: str) -> dict[str, Any]:
    metadata = read_job(job_id)
    latest_result = read_latest_upload_result()
    latest_summary = read_latest_upload_summary() or {}
    if metadata is None and (not latest_result or latest_result.get("job_id") != job_id):
        raise HTTPException(status_code=404, detail={"error_type": "upload_session_missing", "message": "Upload session expired or was not found."})

    if latest_result and latest_result.get("job_id") == job_id:
        artifacts = sii_completion_artifacts(latest_result)
        completed_at = latest_summary.get("last_processed_at") or now_iso()
        summary = latest_summary if latest_summary.get("job_id") == job_id else summarize_result(latest_result, completed_at)
        summary["sii_completed"] = bool(all(artifacts.values()))
        summary["sii_completion_artifacts"] = artifacts
        if not summary["sii_completed"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "error_type": "sii_completion_missing",
                    "message": "SII completion artifacts are still missing. Re-upload source telemetry to rebuild.",
                },
            )
        update_job(
            job_id,
            status="COMPLETE",
            result_available=True,
            first_usable_available=True,
            sii_completed=True,
            sii_completion_artifacts=artifacts,
            result_summary=summary,
            completed_at=completed_at,
            error=None,
        )
        write_latest_upload_summary(job_id, summary, append_history=False)
        payload = upload_status_payload(read_job(job_id), job_id)
        return {
            "job_id": job_id,
            "status": payload["status"],
            "progress": payload["progress"],
            "processing_state": payload["processing_state"],
            "error_type": None,
            "filename": payload.get("filename") or latest_result.get("filename") or "telemetry.csv",
            "message": "Upload session reprocessed from persisted artifacts.",
            "status_url": f"/api/data/upload-status/{job_id}",
            "result_url": f"/api/data/intake/{job_id}/result",
            "file_size_bytes": int(payload.get("file_size_bytes") or 0),
            "stage": payload.get("stage"),
            "percent": payload.get("percent"),
            "bytes_processed": int(payload.get("bytes_processed") or 0),
            "rows_processed": int(payload.get("rows_processed") or 0),
            "result_available": True,
            "sii_completed": True,
        }

    raise HTTPException(
        status_code=409,
        detail={
            "error_type": "reprocess_source_unavailable",
            "message": "Original upload source is unavailable for reprocess. Re-upload source telemetry.",
        },
    )


@router.get("/data/intake/{job_id}/status", response_model=UploadStatusResponse)
def read_intake_status(request: Request, job_id: str) -> dict[str, Any]:
    return read_upload_status(request, job_id)


@router.get("/data/intake/{job_id}/result")
def read_intake_result(job_id: str) -> dict[str, Any]:
    metadata = read_job(job_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail={"error_type": "upload_session_missing", "message": "Upload session expired or was not found."})
    if not metadata.get("result_available") and str(metadata.get("status", "")).upper() != "COMPLETE":
        return {
            "job_id": job_id,
            "status": metadata.get("status", "PENDING"),
            "result_available": False,
            "first_usable_available": bool(metadata.get("first_usable_available")),
            "message": "Intake result is not available yet; continue polling status.",
            "status_url": f"/api/data/intake/{job_id}/status",
        }
    latest_result = read_latest_upload_result()
    if latest_result and latest_result.get("job_id") == job_id:
        return {
            "job_id": job_id,
            "status": metadata.get("status", "COMPLETE"),
            "result_available": True,
            "result": latest_result,
            "summary": metadata.get("result_summary"),
        }
    return {
        "job_id": job_id,
        "status": metadata.get("status", "COMPLETE"),
        "result_available": bool(metadata.get("result_summary")),
        "summary": metadata.get("result_summary"),
        "message": "Detailed result is still being persisted; summary is returned when available.",
    }


@router.get("/data/replay/{job_id}")
def read_upload_replay(job_id: str) -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    metadata = read_job(job_id)
    persisted = replay_payload_from_result(latest_result, job_id=job_id)
    if persisted is not None:
        return persisted
    if metadata is None:
        raise HTTPException(status_code=404, detail={"error_type": "upload_session_missing", "message": "Upload session expired or was not found."})

    source_replay = rebuild_upload_replay_from_source(metadata)
    if source_replay is not None:
        return source_replay

    return {
        "job_id": job_id,
        "frame_count": 0,
        "timeline": [],
        "meta": {},
        "message": "No replay frames are available for this CSV yet. The source file may be missing, or the upload did not retain replayable timestamp and numeric signals.",
    }


def replay_payload_from_result(result: dict[str, Any] | None, *, job_id: str) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    replay = (
        result.get("replay_timeline")
        or (result.get("sii_intelligence") or {}).get("replay_timeline")
        or {}
    )
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    if not isinstance(timeline, list) or not timeline:
        return None
    return {
        "job_id": job_id,
        "frame_count": len(timeline),
        "timeline": timeline,
        "meta": replay.get("meta", {}) if isinstance(replay, dict) else {},
    }


def rebuild_upload_replay_from_source(metadata: dict[str, Any]) -> dict[str, Any] | None:
    raw_path = metadata.get("file_path")
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if not path.exists() or not path.is_file():
        return None
    filename = str(metadata.get("filename") or path.name)
    try:
        rebuilt = process_telemetry_file(file_path=path, filename=filename)
    except Exception as exc:
        logger.warning(
            "upload_replay_rebuild_failed job_id=%s filename=%s error_type=%s",
            metadata.get("job_id"),
            filename,
            type(exc).__name__,
        )
        return None

    replay = ((rebuilt.get("sii_intelligence") or {}).get("replay_timeline") or {})
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    if not isinstance(timeline, list) or not timeline:
        return None
    return {
        "job_id": metadata.get("job_id"),
        "frame_count": len(timeline),
        "timeline": timeline,
        "meta": replay.get("meta", {}) if isinstance(replay, dict) else {},
        "message": "Replay reconstructed from the retained source CSV.",
    }


def completed_metadata_from_summary(job_id: str, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "summary_fallback": True,
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
        "sii_completed": bool(summary.get("sii_completed")),
        "sii_completion_artifacts": summary.get("sii_completion_artifacts", {}),
    }


@router.get("/data/latest-upload", response_model=LatestUploadResponse) 
def read_latest_upload(include_persisted: bool = Query(True)) -> dict[str, Any]: 
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
    if not include_persisted:
        summary = None
        detailed_result = None
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
            "adaptive_learning": {},
        } 
        logger.info("latest_result_served status=%s source=%s state_available=%s", payload["status"], payload["source"], payload["state_available"]) 
        return payload 
    summary = summary or {}
    live_baseline_source = (live_connection or {}).get("baseline_source")
    live_baseline_status = (live_connection or {}).get("baseline_status")
    live_baseline_samples_collected = (live_connection or {}).get("baseline_samples_collected", 0)
    live_baseline_samples_required = (live_connection or {}).get("baseline_samples_required", 0)
    live_baseline_last_updated = (live_connection or {}).get("last_baseline_update")
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
        "status": "active" if (detailed_result is not None and bool((summary or {}).get("sii_completed"))) else ("baseline_active" if (live_connection or {}).get("baseline_status") == "active" else "building_baseline"),
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
        "sii_completed": bool((summary or {}).get("sii_completed")),
        "sii_completion_artifacts": (summary or {}).get("sii_completion_artifacts", {}),
        "runner_used": summary.get("runner_used", False),
        "chunk_count": summary.get("chunk_count", 0),
        "memory_estimate_bytes": summary.get("memory_estimate_bytes", 0),
        "engine_runtime_seconds": summary.get("engine_runtime_seconds"),
        "latest_result": detailed_result,
        "baseline_source": live_baseline_source or summary.get("baseline_source"),
        "baseline_status": live_baseline_status or summary.get("baseline_status"),
        "baseline_samples_collected": live_baseline_samples_collected if live_connection is not None else summary.get("baseline_samples_collected", 0),
        "baseline_samples_required": live_baseline_samples_required if live_connection is not None else summary.get("baseline_samples_required", 0),
        "last_baseline_update": live_baseline_last_updated or summary.get("last_baseline_update"),
        "adaptive_learning": build_adaptive_snapshot(detailed_result or {}, summary or {}) if detailed_result else {},
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


@router.post("/data/reset")
def reset_data_session() -> dict[str, Any]: 
    reset_latest_upload_state(purge_job_records=True) 
    reset_latest_sii_state() 
    clear_all_connection_runtime_state() 
    return { 
        "status": "reset",
        "message": "Demo session cleared. Baseline pending with no active telemetry result.",
        "snapshot": {
            "status": "empty",
            "source": "none",
            "message": "Awaiting uploaded telemetry.",
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
            "baseline_source": None,
            "baseline_status": "none",
            "baseline_samples_collected": 0,
            "baseline_samples_required": 0,
            "last_baseline_update": None,
        },
    }
