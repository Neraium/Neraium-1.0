from __future__ import annotations

import logging
import threading
import asyncio
import json
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Any
import uuid
from datetime import datetime, timedelta, timezone
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path as ApiPath, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from app.services.evidence_store import upsert_evidence_run
from app.services.dataset_scope import payload_matches_dataset_scope
from app.services.analysis_result_contract import ensure_analysis_result
from app.core.security import _strict_auth_mode, require_api_access, require_operator_role
from app.core.path_safety import StoragePathError, ensure_storage_root, resolve_existing_storage_path, safe_upload_suffix, storage_key_for_server_path
from app.services import upload_jobs
from app.services.baseline_contracts import (
    WORKFLOW_ANALYZE_NEW_DATA,
    WORKFLOW_EXTEND_BASELINE,
    WORKFLOW_LEGACY_ANALYSIS,
    is_baseline_workflow,
    normalize_workflow,
)
from app.services.behavioral_model_repository import (
    activate_candidate,
    read_active_behavioral_model,
    read_baseline_result,
    read_latest_candidate,
    read_model,
    read_model_index,
)
from app.models.api_models import BehavioralModelApprovalRequest
from app.services.upload_evidence import build_evidence_record_from_result
from app.services.upload_persistence import summarize_result
from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE
from app.services.upload_state import has_active_session_artifact
from app.services.sii_runner import CORE_ENGINE, RUNNER_MODULE
from app.services.runtime_db import record_audit_event
from app.services.runtime_db import enqueue_upload_job
from app.services.runtime_db import queue_metrics as runtime_queue_metrics
from app.services.runtime_db import touch_upload_queue_job, peek_next_upload_job_for_worker
from app.services.runtime_db import configure_runtime_dir as configure_runtime_db_dir
from app.services.upload_state_repository import (
    create_presigned_upload_target,
    inspect_upload_source,
    persist_upload_source,
    read_large_upload_session,
    read_latest_upload_record,
    read_replay_payload,
    read_upload_result_by_job_id,
    reset_upload_state,
    resolve_upload_artifacts,
    shared_state_configured,
    write_large_upload_session,
)
from app.services.rate_limiter import consume_rate_limit
from app.services.latest_upload_state import resolve_latest_upload_payload
from app.services.upload_session_service import resolve_upload_status
from app.services.upload_errors import build_upload_error_payload, canonical_upload_error_code

router = APIRouter(prefix="/data", tags=["data"], dependencies=[Depends(require_api_access)])
logger = logging.getLogger(__name__)
UPLOAD_JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)
UPLOAD_RATE_LIMIT = 20
UPLOAD_RATE_WINDOW_SECONDS = 60
UPLOAD_STATUS_RATE_LIMIT = 240
UPLOAD_STATUS_RATE_WINDOW_SECONDS = 60
_UPLOAD_WORKERS: set[threading.Thread] = set()
_UPLOAD_WORKERS_LOCK = threading.Lock()
UploadJobPath = Annotated[str, ApiPath(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]


class LargeUploadSessionRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    content_type: str = Field(default="text/csv", max_length=255)
    workflow: str = Field(default=WORKFLOW_LEGACY_ANALYSIS, max_length=64)
    approval_required: bool | None = None


class LargeUploadCompleteRequest(BaseModel):
    etag: str | None = Field(default=None, max_length=256)


def _upload_storage_root(runtime_dir: Path) -> Path:
    return ensure_storage_root(Path(runtime_dir) / "uploads")


def _resolve_upload_source_path(runtime_dir: Path, file_path: Any) -> Path | None:
    try:
        return resolve_existing_storage_path(_upload_storage_root(runtime_dir), file_path)
    except StoragePathError:
        return None


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
        content=build_upload_error_payload(
            "server_unavailable",
            message=message,
            failed_stage="dataset_creation",
            retryable=True,
            legacy_error_type=error_type,
        ),
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
                **build_upload_error_payload(
                    "server_unavailable",
                    message="The import service could not start baseline processing. Retry shortly.",
                    failed_stage="baseline_job_creation",
                    retryable=True,
                    legacy_error_type="worker_start_failed",
                    job_id=worker_job_id,
                ),
                "progress_label": "Baseline processing could not start.",
                "worker_state": "stalled",
                "worker_last_seen_at": now,
                "result_available": False,
            })
            upload_jobs.write_job(failed)
            if not is_baseline_workflow(failed.get("workflow")):
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



def _upload_actor(request: Request) -> str:
    auth_context = getattr(request.state, "auth_context", {})
    return str(
        auth_context.get("auth_subject")
        or request.headers.get("X-Neraium-User")
        or request.headers.get("X-Authenticated-User")
        or request.headers.get("X-Forwarded-Email")
        or "anonymous"
    )


def _large_upload_error(status_code: int, error_type: str, message: str, **extra: Any) -> JSONResponse:
    job_id = extra.pop("job_id", None)
    error_code = extra.pop("error_code", canonical_upload_error_code(error_type))
    failed_stage = extra.pop("failed_stage", None)
    retryable = extra.pop("retryable", None)
    return JSONResponse(
        status_code=status_code,
        content=build_upload_error_payload(
            error_code,
            message=message,
            failed_stage=failed_stage,
            retryable=retryable,
            legacy_error_type=error_type,
            job_id=job_id,
            **extra,
        ),
    )


def _valid_large_upload_filename(filename: str) -> bool:
    return str(filename or "").lower().endswith(".csv")


@router.post("/upload-session", status_code=201, dependencies=[Depends(require_operator_role)])
def create_large_upload_session(request: Request, payload: LargeUploadSessionRequest):
    if _strict_auth_mode(request):
        allowed, retry_after = consume_rate_limit(
            "data.upload-session",
            _rate_limit_key(request),
            limit=UPLOAD_RATE_LIMIT,
            window_seconds=UPLOAD_RATE_WINDOW_SECONDS,
        )
        if not allowed:
            return _rate_limit_response(retry_after, error_type="upload_rate_limited", message="Upload rate limit exceeded. Retry shortly.")

    settings = request.app.state.settings
    filename = str(payload.filename or "").strip()
    size_bytes = int(payload.size_bytes)
    max_size_bytes = int(getattr(settings, "max_large_upload_size_bytes", 512 * 1024 * 1024))
    request_id = getattr(request.state, "request_id", None)
    try:
        workflow = normalize_workflow(payload.workflow)
    except ValueError as exc:
        return _large_upload_error(422, "invalid_workflow", str(exc))
    active_baseline = read_active_behavioral_model()
    if workflow in {WORKFLOW_ANALYZE_NEW_DATA, WORKFLOW_EXTEND_BASELINE} and not active_baseline:
        return _large_upload_error(
            409,
            "active_behavioral_baseline_required",
            "Activate a suitable Behavioral Digital Model before starting this workflow.",
            workflow=workflow,
        )
    resolved_approval_required = (
        bool(getattr(settings, "baseline_approval_required", True))
        if payload.approval_required is None
        else bool(payload.approval_required)
    )
    if not _valid_large_upload_filename(filename):
        return _large_upload_error(400, "unsupported_file_type", "Large-file intake supports CSV telemetry files only.")
    if size_bytes > max_size_bytes:
        _log_upload_event(
            "large_upload_session_rejected",
            request_id=request_id,
            endpoint="/api/data/upload-session",
            filename=filename,
            file_size_bytes=size_bytes,
            failure_reason="upload_too_large",
        )
        return _large_upload_error(
            413,
            "upload_too_large",
            f"File is larger than the supported upload limit of {format_upload_capacity(max_size_bytes)}.",
            max_upload_size_bytes=max_size_bytes,
            received_size_bytes=size_bytes,
        )
    if not shared_state_configured():
        return _large_upload_error(
            503,
            "large_upload_storage_unavailable",
            "Secure file storage is temporarily unavailable. Retry shortly.",
            failed_stage="file_storage",
            retryable=True,
        )

    upload_session_id = uuid.uuid4().hex
    content_type = str(payload.content_type or "text/csv").strip().lower() or "text/csv"
    if "csv" not in content_type and content_type not in {"application/octet-stream", "text/plain"}:
        content_type = "text/csv"
    try:
        target = create_presigned_upload_target(
            upload_session_id,
            filename=filename,
            content_type=content_type,
            expires_in_seconds=3600,
        )
    except Exception:
        logger.exception("large_upload_session_create_failed request_id=%s size_bytes=%s", request_id, size_bytes)
        return _large_upload_error(
            503,
            "large_upload_storage_unavailable",
            "Secure file storage is temporarily unavailable. Retry shortly.",
            failed_stage="file_storage",
            retryable=True,
        )

    now = datetime.now(timezone.utc)
    try:
        session = write_large_upload_session(
            upload_session_id,
            {
                "upload_session_id": upload_session_id,
                "filename": filename,
                "size_bytes": size_bytes,
                "content_type": content_type,
                "object_key": target["object_key"],
                "state": "awaiting_upload",
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(hours=1)).isoformat(),
                "initiated_by": _upload_actor(request),
                "request_id": request_id,
                "workflow": workflow,
                "approval_required": resolved_approval_required if is_baseline_workflow(workflow) else None,
                "active_baseline_model_id": (active_baseline or {}).get("model_id"),
                "active_baseline_version": (active_baseline or {}).get("version"),
            },
        )
    except Exception:
        logger.exception("large_upload_session_persist_failed request_id=%s upload_session_id=%s", request_id, upload_session_id)
        return _large_upload_error(
            503,
            "large_upload_storage_unavailable",
            "The upload session could not be created. Retry the import.",
            error_code="dataset_record_creation_failed",
            failed_stage="dataset_creation",
            retryable=True,
        )
    request.state.upload_session_id = upload_session_id
    _log_upload_event(
        "large_upload_session_created",
        request_id=request_id,
        upload_session_id=upload_session_id,
        endpoint="/api/data/upload-session",
        filename=filename,
        file_size_bytes=size_bytes,
        processing_stage="awaiting_upload",
    )
    return {
        "upload_session_id": upload_session_id,
        "upload_url": target["upload_url"],
        "upload_headers": target["upload_headers"],
        "expires_at": session["expires_at"],
        "max_upload_size_bytes": max_size_bytes,
        "upload_method": "PUT",
        "workflow": workflow,
    }


@router.post("/upload-session/{upload_session_id}/complete", status_code=202, dependencies=[Depends(require_operator_role)])
def complete_large_upload_session(
    request: Request,
    upload_session_id: UploadJobPath,
    payload: LargeUploadCompleteRequest,
):
    request_id = getattr(request.state, "request_id", None)
    session = read_large_upload_session(upload_session_id)
    if not session:
        return _large_upload_error(
            404,
            "upload_session_missing",
            "The stored upload session expired or was not found.",
            job_id=upload_session_id,
            upload_session_id=upload_session_id,
            failed_stage="dataset_creation",
            retryable=False,
        )

    existing_job = upload_jobs.read_upload_status(upload_session_id)
    if existing_job and str(existing_job.get("status") or "").upper() in {"PENDING", "QUEUED", "PROCESSING", "RUNNING_SII", "COMPLETE"}:
        return {
            **existing_job,
            "job_id": upload_session_id,
            "status_url": existing_job.get("status_url") or f"/api/data/upload-status/{upload_session_id}",
        }

    expires_at = str(session.get("expires_at") or "").strip()
    try:
        expired = bool(expires_at) and datetime.fromisoformat(expires_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    except ValueError:
        expired = True
    if expired:
        return _large_upload_error(
            410,
            "upload_session_missing",
            "The stored upload session expired or was not found.",
            job_id=upload_session_id,
            upload_session_id=upload_session_id,
            failed_stage="dataset_creation",
            retryable=False,
        )

    expected_size = int(session.get("size_bytes") or 0)
    max_size_bytes = int(getattr(request.app.state.settings, "max_large_upload_size_bytes", 512 * 1024 * 1024))
    if expected_size <= 0 or expected_size > max_size_bytes:
        return _large_upload_error(
            413,
            "upload_too_large",
            f"File is larger than the supported upload limit of {format_upload_capacity(max_size_bytes)}.",
            max_upload_size_bytes=max_size_bytes,
        )

    source_key = str(session.get("object_key") or "").strip()
    try:
        uploaded = inspect_upload_source(source_key)
    except Exception:
        logger.warning(
            "large_upload_source_confirmation_failed request_id=%s upload_session_id=%s",
            request_id,
            upload_session_id,
            exc_info=True,
        )
        return _large_upload_error(
            409,
            "upload_not_complete",
            "The file transfer could not be confirmed. Retry the transfer.",
            job_id=upload_session_id,
            upload_session_id=upload_session_id,
            failed_stage="upload_transfer",
            retryable=True,
            transfer_succeeded=False,
        )

    received_size = int(uploaded.get("content_length") or 0)
    if received_size != expected_size:
        _log_upload_event(
            "large_upload_completion_rejected",
            request_id=request_id,
            upload_session_id=upload_session_id,
            endpoint=f"/api/data/upload-session/{upload_session_id}/complete",
            filename=session.get("filename"),
            file_size_bytes=received_size,
            failure_reason="upload_size_mismatch",
        )
        return _large_upload_error(
            409,
            "upload_size_mismatch",
            "The file transfer was incomplete. Retry the transfer.",
            job_id=upload_session_id,
            upload_session_id=upload_session_id,
            failed_stage="upload_transfer",
            retryable=True,
            transfer_succeeded=False,
            expected_size_bytes=expected_size,
            received_size_bytes=received_size,
        )
    submitted_etag = str(payload.etag or "").strip().strip('"')
    uploaded_etag = str(uploaded.get("etag") or "").strip().strip('"')
    if submitted_etag and uploaded_etag and submitted_etag != uploaded_etag:
        return _large_upload_error(
            409,
            "upload_etag_mismatch",
            "The file transfer could not be verified. Retry the transfer.",
            job_id=upload_session_id,
            upload_session_id=upload_session_id,
            failed_stage="upload_transfer",
            retryable=True,
            transfer_succeeded=False,
        )

    stored_upload_fields = {
        "job_id": upload_session_id,
        "upload_session_id": upload_session_id,
        "file_stored": True,
        "transfer_succeeded": True,
        "retry_url": f"/api/data/upload-session/{upload_session_id}/complete",
    }

    metrics = queue_metrics()
    if int(metrics.get("pending", 0)) >= int(getattr(request.app.state.settings, "max_pending_upload_jobs", 3)):
        return JSONResponse(
            status_code=503,
            headers={"retry-after": "30"},
            content=build_upload_error_payload(
                "server_unavailable",
                message="The file was transferred, but the import service is busy. Retry shortly.",
                failed_stage="dataset_creation",
                retryable=True,
                legacy_error_type="upload_queue_saturated",
                **stored_upload_fields,
            ),
        )

    filename = str(session.get("filename") or "upload.csv")
    actor = str(session.get("initiated_by") or _upload_actor(request))
    try:
        workflow = normalize_workflow(session.get("workflow") or WORKFLOW_LEGACY_ANALYSIS)
    except ValueError as exc:
        return _large_upload_error(422, "invalid_workflow", str(exc))
    active_baseline = read_active_behavioral_model()
    if workflow in {WORKFLOW_ANALYZE_NEW_DATA, WORKFLOW_EXTEND_BASELINE} and not active_baseline:
        return _large_upload_error(
            409,
            "active_behavioral_baseline_required",
            "Activate a suitable Behavioral Digital Model before starting this workflow.",
            workflow=workflow,
        )
    worker_dispatch_status = "thread_dispatched" if _should_dispatch_upload_worker(request.app.state.settings) else "external_worker_queue"
    summary = {
        "job_id": upload_session_id,
        "filename": filename,
        "status_url": f"/api/data/upload-status/{upload_session_id}",
        "status": "PENDING",
        "processing_state": "queued",
        "percent": 5,
        "progress": 5,
        "progress_label": "Validating data",
        "message": "Validating data",
        "propagation_stage": "queued",
        "propagation_progress": 5,
        "propagation_label": "Validating data",
        "runner_used": False if str(getattr(request.app.state.settings, "process_role", "")).lower() == "api" else True,
        "runner_module": RUNNER_MODULE,
        "core_engine": CORE_ENGINE,
        "file_path": None,
        "shared_upload_source_key": source_key,
        "file_size_bytes": received_size,
        "content_type": session.get("content_type") or uploaded.get("content_type") or "text/csv",
        "initiated_by": actor,
        "request_id": request_id or session.get("request_id"),
        "upload_session_id": upload_session_id,
        "worker_dispatch_status": worker_dispatch_status,
        "upload_transport": "presigned_s3_put",
        "workflow": workflow,
        "workflow_state": "queued",
        "approval_required": session.get("approval_required") if is_baseline_workflow(workflow) else None,
        "active_baseline_model_id": (active_baseline or {}).get("model_id") or session.get("active_baseline_model_id"),
        "active_baseline_version": (active_baseline or {}).get("version") or session.get("active_baseline_version"),
    }
    if is_baseline_workflow(workflow):
        summary.update(
            {
                "runner_used": False,
                "runner_module": None,
                "core_engine": None,
                "sii_completed": False,
                "sii_engine_invoked": False,
                "baseline_result_url": f"/api/data/baselines/jobs/{upload_session_id}",
                "message": "Baseline construction queued.",
                "progress_label": "Baseline construction queued.",
                "propagation_label": "Baseline construction queued.",
            }
        )
    try:
        upload_jobs.write_job(summary)
    except Exception:
        logger.exception("large_upload_job_state_write_failed request_id=%s upload_session_id=%s", request_id, upload_session_id)
        return _large_upload_error(
            503,
            "upload_enqueue_failed",
            "The file was transferred, but the dataset record could not be created.",
            error_code="dataset_record_creation_failed",
            failed_stage="dataset_creation",
            retryable=True,
            **stored_upload_fields,
        )

    if not is_baseline_workflow(workflow):
        try:
            upsert_evidence_run(
                {
                    "run_id": upload_session_id,
                    "source_name": filename,
                    "source_type": "csv_upload",
                    "status": "queued",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "completed_at": None,
                    "rows_received": 0,
                    "rows_accepted": 0,
                    "rows_rejected": 0,
                    "sensors_detected": 0,
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
        except Exception:
            logger.warning("large_upload_evidence_write_failed upload_session_id=%s", upload_session_id, exc_info=True)

    try:
        enqueue_upload_job(upload_session_id)
    except Exception:
        logger.exception("large_upload_job_enqueue_failed request_id=%s upload_session_id=%s", request_id, upload_session_id)
        try:
            upload_jobs.write_job(
                {
                    **summary,
                    **build_upload_error_payload(
                        "dataset_record_creation_failed",
                        message="The file was transferred successfully, but Neraium could not begin processing it.",
                        failed_stage="dataset_creation",
                        retryable=True,
                        legacy_error_type="upload_enqueue_failed",
                        **stored_upload_fields,
                    ),
                }
            )
        except Exception:
            logger.exception("large_upload_job_failure_state_write_failed upload_session_id=%s", upload_session_id)
        if not is_baseline_workflow(workflow):
            try:
                _upsert_failed_evidence_record(
                    job_id=upload_session_id,
                    filename=filename,
                    source_type="csv_upload",
                    error_message="Upload completed, but analysis could not be started.",
                    initiated_by=actor,
                )
            except Exception:
                logger.warning("large_upload_failure_evidence_write_failed upload_session_id=%s", upload_session_id, exc_info=True)
        return _large_upload_error(
            503,
            "upload_enqueue_failed",
            "The file was transferred successfully, but Neraium could not begin processing it.",
            error_code="dataset_record_creation_failed",
            failed_stage="dataset_creation",
            retryable=True,
            **stored_upload_fields,
        )

    try:
        write_large_upload_session(
            upload_session_id,
            {
                **session,
                "state": "job_created",
                "job_id": upload_session_id,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        logger.warning("large_upload_session_completion_state_write_failed upload_session_id=%s", upload_session_id, exc_info=True)
    request.state.upload_session_id = upload_session_id
    try:
        record_audit_event(
            actor=actor,
            action="upload.accepted",
            resource_type="upload_job",
            resource_id=upload_session_id,
            request_id=getattr(request.state, "auth_context", {}).get("request_id"),
            detail={"filename": filename, "size_bytes": received_size, "transport": "presigned_s3_put", "workflow": workflow},
        )
    except Exception:
        logger.warning("large_upload_audit_write_failed upload_session_id=%s", upload_session_id, exc_info=True)
    if worker_dispatch_status == "thread_dispatched":
        _dispatch_upload_worker_for_runtime(request.app.state.settings.runtime_dir)
    _log_upload_event(
        "large_upload_job_created",
        request_id=request_id,
        upload_session_id=upload_session_id,
        endpoint=f"/api/data/upload-session/{upload_session_id}/complete",
        filename=filename,
        file_size_bytes=received_size,
        job_id=upload_session_id,
        queue_status="pending",
        worker_dispatch_status=worker_dispatch_status,
        processing_stage="queued",
    )
    return {
        "job_id": upload_session_id,
        "status": "PENDING",
        "processing_state": "queued",
        "filename": filename,
        "percent": 5,
        "progress": 5,
        "progress_label": "Validating data",
        "message": "Validating data",
        "status_url": f"/api/data/upload-status/{upload_session_id}",
        "file_size_bytes": received_size,
        "worker_dispatch_status": worker_dispatch_status,
        "upload_transport": "presigned_s3_put",
        "workflow": workflow,
        "workflow_state": "queued",
        "baseline_result_url": f"/api/data/baselines/jobs/{upload_session_id}" if is_baseline_workflow(workflow) else None,
        "sii_engine_invoked": False if is_baseline_workflow(workflow) else None,
    }


@router.post("/upload", status_code=202, dependencies=[Depends(require_operator_role)])
async def upload_data(
    request: Request,
    file: UploadFile = File(...),
    workflow: str = Form(WORKFLOW_LEGACY_ANALYSIS),
    approval_required: bool | None = Form(None),
):
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
    try:
        workflow = normalize_workflow(workflow)
    except ValueError as exc:
        return _large_upload_error(
            422,
            "invalid_workflow",
            str(exc),
            failed_stage="validation",
            retryable=False,
        )
    active_baseline = read_active_behavioral_model()
    if workflow in {WORKFLOW_ANALYZE_NEW_DATA, WORKFLOW_EXTEND_BASELINE} and not active_baseline:
        return _large_upload_error(
            409,
            "active_behavioral_baseline_required",
            "Activate a suitable Behavioral Digital Model before starting this workflow.",
            failed_stage="validation",
            retryable=False,
            workflow=workflow,
        )
    resolved_approval_required = (
        bool(getattr(settings, "baseline_approval_required", True))
        if approval_required is None
        else bool(approval_required)
    )
    handler_started_at = time.perf_counter()
    handler_started_wall = datetime.now(timezone.utc).isoformat()
    request_started_at = float(getattr(request.state, "request_started_perf", handler_started_at))
    request_received_at = getattr(request.state, "request_received_at", datetime.now(timezone.utc).isoformat())
    upload_transfer_ms = max(0.0, (handler_started_at - request_started_at) * 1000)
    started_at = handler_started_at
    request_id = getattr(request.state, "request_id", None)
    filename = file.filename or "upload.csv"
    if len(filename) > 255:
        return _large_upload_error(
            400,
            "invalid_filename",
            "Filename must not exceed 255 characters.",
            failed_stage="validation",
            retryable=False,
        )
    lowered = filename.lower()
    if not (lowered.endswith(".csv") or lowered.endswith(".json") or lowered.endswith(".txt")):
        _log_upload_event("request_rejected", request_id=request_id, endpoint="/api/data/upload", filename=filename, processing_stage="validate_file_type", failure_reason="unsupported_file_type")
        return _large_upload_error(
            400,
            "unsupported_file_type",
            "Only .csv, .txt, and .json telemetry files are supported.",
            failed_stage="validation",
            retryable=False,
        )

    max_size_bytes = int(getattr(settings, "max_upload_size_bytes", 10 * 1024 * 1024 * 1024))
    metrics = queue_metrics()
    if int(metrics.get("pending", 0)) >= int(getattr(settings, "max_pending_upload_jobs", 3)):
        _log_upload_event("request_rejected", request_id=request_id, endpoint="/api/data/upload", filename=filename, queue_status="saturated", processing_stage="queue_capacity", failure_reason="upload_queue_saturated")
        return JSONResponse(
            status_code=503,
            headers={"retry-after": "30"},
            content=build_upload_error_payload(
                "server_unavailable",
                message="The import service is busy. Retry shortly.",
                failed_stage="dataset_creation",
                retryable=True,
                legacy_error_type="upload_queue_saturated",
            ),
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
    transfer_succeeded = False
    csv_has_non_whitespace = False
    job_id = uuid.uuid4().hex
    temp_path = ""
    upload_storage_key: str | None = None
    summary: dict[str, Any] = {}
    failure_stage = "file_storage"
    try:
        spool_started_at = time.perf_counter()
        spool_dir = _upload_storage_root(settings.runtime_dir)
        with NamedTemporaryFile(
            delete=False,
            dir=spool_dir,
            prefix=f"{job_id}-",
            suffix=safe_upload_suffix(filename),
        ) as temp:
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
                    return _large_upload_error(
                        413,
                        "upload_too_large",
                        f"File too large. Maximum supported size is {format_upload_capacity(max_size_bytes)}.",
                        failed_stage="validation",
                        retryable=False,
                        max_upload_size_bytes=max_size_bytes,
                        received_size_bytes=file_size_bytes,
                    )
                if lowered.endswith(".csv") and not csv_has_non_whitespace and chunk.strip():
                    csv_has_non_whitespace = True
                temp.write(chunk)
        transfer_succeeded = True

        if lowered.endswith(".csv") and (file_size_bytes == 0 or not csv_has_non_whitespace):
            _log_upload_event("request_rejected", request_id=request_id, endpoint="/api/data/upload", filename=filename, file_size_bytes=file_size_bytes, processing_stage="validate_csv", failure_reason="csv_empty")
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
            return _large_upload_error(
                400,
                "csv_parse_error",
                "CSV file is empty.",
                error_code="csv_parsing_failed",
                failed_stage="csv_parsing",
                retryable=False,
            )

        backend_spool_ms = max(0.0, (time.perf_counter() - spool_started_at) * 1000)
        upload_storage_key = storage_key_for_server_path(spool_dir, temp_path)

        _log_upload_event(
            "request_bytes_received",
            request_id=request_id,
            endpoint="/api/data/upload",
            filename=filename,
            file_size_bytes=file_size_bytes,
            content_type=content_type or "unknown",
            processing_stage="spooled",
            upload_transfer_ms=round(upload_transfer_ms, 3),
            backend_spool_ms=round(backend_spool_ms, 3),
        )

        request.state.upload_session_id = job_id
        shared_upload_source_key = None
        failure_stage = "file_storage"
        if shared_state_configured():
            shared_upload_source_key = persist_upload_source(
                job_id,
                temp_path,
                filename=filename,
                content_type=content_type or None,
            )
        worker_dispatch_status = "thread_dispatched" if _should_dispatch_upload_worker(settings) else "external_worker_queue"
        failure_stage = "dataset_creation"
        job_creation_started_at = time.perf_counter()
        job_created_at = datetime.now(timezone.utc).isoformat()
        enqueued_at = job_created_at
        processing_file_path = (
            None
            if worker_dispatch_status == "external_worker_queue" and shared_upload_source_key
            else upload_storage_key
        )
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
            "file_path": processing_file_path,
            "shared_upload_source_key": shared_upload_source_key,
            "file_size_bytes": file_size_bytes,
            "content_type": content_type,
            "initiated_by": actor,
            "request_id": request_id,
            "upload_session_id": job_id,
            "worker_dispatch_status": worker_dispatch_status,
            "request_received_at": request_received_at,
            "backend_handler_started_at": handler_started_wall,
            "upload_completed_at": datetime.now(timezone.utc).isoformat(),
            "job_created_at": job_created_at,
            "enqueued_at": enqueued_at,
            "stage_changed_at": job_created_at,
            "timings": {
                "upload_transfer_ms": round(upload_transfer_ms, 3),
                "backend_spool_ms": round(backend_spool_ms, 3),
                "backend_request_handling_ms": round((time.perf_counter() - handler_started_at) * 1000, 3),
            },
            "workflow": workflow,
            "workflow_state": "queued",
            "approval_required": resolved_approval_required if is_baseline_workflow(workflow) else None,
            "active_baseline_model_id": (active_baseline or {}).get("model_id"),
            "active_baseline_version": (active_baseline or {}).get("version"),
        }
        if is_baseline_workflow(workflow):
            summary.update(
                {
                    "runner_used": False,
                    "runner_module": None,
                    "core_engine": None,
                    "sii_completed": False,
                    "sii_engine_invoked": False,
                    "baseline_result_url": f"/api/data/baselines/jobs/{job_id}",
                    "message": "Baseline construction queued.",
                    "progress_label": "Baseline construction queued.",
                    "propagation_label": "Baseline construction queued.",
                }
            )
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
        if run_id and not is_baseline_workflow(workflow):
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
        failure_stage = "baseline_job_creation"
        enqueue_upload_job(job_id)
        job_creation_ms = max(0.0, (time.perf_counter() - job_creation_started_at) * 1000)
        if processing_file_path is None:
            Path(temp_path).unlink(missing_ok=True)
            temp_path = ""
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
            upload_transfer_ms=round(upload_transfer_ms, 3),
            backend_request_handling_ms=round((time.perf_counter() - handler_started_at) * 1000, 3),
            job_creation_ms=round(job_creation_ms, 3),
        )
    except Exception as exc:
        try:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
        except Exception:
            pass
        failed_job_id = str(summary.get("job_id") or job_id)
        failed_at = datetime.now(timezone.utc).isoformat()
        internal_error = str(exc) or exc.__class__.__name__
        shared_queue_missing = "shared_upload_queue_not_configured" in internal_error
        if failure_stage == "file_storage":
            if transfer_succeeded:
                error_code = "file_storage_failed"
                error_type = "large_upload_storage_unavailable"
                safe_message = "The transfer completed, but the file could not be saved to secure storage."
            else:
                error_code = "upload_transfer_failed"
                error_type = "object_storage_upload_failed"
                failure_stage = "upload_transfer"
                safe_message = "The file transfer could not complete. Check the connection and try again."
        elif failure_stage == "dataset_creation":
            error_code = "dataset_record_creation_failed"
            error_type = "upload_enqueue_failed"
            safe_message = "The file was transferred, but the dataset record could not be created."
        else:
            error_code = "server_unavailable" if shared_queue_missing else "dataset_record_creation_failed"
            error_type = "shared_upload_queue_not_configured" if shared_queue_missing else "upload_enqueue_failed"
            safe_message = (
                "The import service is temporarily unavailable. Retry shortly."
                if shared_queue_missing
                else "The file was transferred successfully, but Neraium could not begin processing it."
            )
        retryable = True
        failure_payload = build_upload_error_payload(
            error_code,
            message=safe_message,
            failed_stage=failure_stage,
            retryable=retryable,
            legacy_error_type=error_type,
            job_id=failed_job_id,
            filename=filename,
            status_url=f"/api/data/upload-status/{failed_job_id}",
            transfer_succeeded=transfer_succeeded,
            file_stored=bool(locals().get("shared_upload_source_key")),
        )
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
        logger.exception(
            "upload_request_failed request_id=%s job_id=%s filename=%s size_bytes=%s failed_stage=%s error_code=%s",
            request_id,
            failed_job_id,
            filename,
            file_size_bytes,
            failure_stage,
            error_code,
        )
        try:
            upload_jobs.write_job(
                {
                    **summary,
                    **failure_payload,
                    "progress_label": safe_message,
                    "result_available": False,
                    "propagation_stage": "failed",
                    "propagation_progress": 0,
                    "propagation_label": "Failed.",
                }
            )
        except Exception:
            logger.exception("upload_failure_state_write_failed request_id=%s job_id=%s", request_id, failed_job_id)
        if not is_baseline_workflow(workflow):
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
                "errors": [internal_error],
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
                "data_conditions": [internal_error],
                "regime_label": None,
                "structural_state": "Error",
                "deformation_started_at": None,
                }
            )
        return JSONResponse(
            status_code=503 if retryable or shared_queue_missing else 500,
            content=failure_payload,
        )
    response_finished_at = time.perf_counter()
    response_timings = {
        "upload_transfer_ms": round(upload_transfer_ms, 3),
        "backend_spool_ms": round(float(locals().get("backend_spool_ms", 0.0)), 3),
        "backend_request_handling_ms": round(max(0.0, (response_finished_at - handler_started_at) * 1000), 3),
        "job_creation_ms": round(float(locals().get("job_creation_ms", 0.0)), 3),
        "request_to_job_created_ms": round(max(0.0, (response_finished_at - request_started_at) * 1000), 3),
    }
    _log_upload_event(
        "request_timing",
        request_id=request_id,
        endpoint="/api/data/upload",
        filename=filename,
        job_id=summary.get("job_id"),
        **response_timings,
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
        "request_received_at": request_received_at,
        "job_created_at": summary.get("job_created_at"),
        "enqueued_at": summary.get("enqueued_at"),
        "stage_changed_at": summary.get("stage_changed_at"),
        "timings": response_timings,
        "workflow": workflow,
        "workflow_state": "queued",
        "baseline_result_url": f"/api/data/baselines/jobs/{summary.get('job_id')}" if is_baseline_workflow(workflow) else None,
        "sii_completed": False,
        "sii_engine_invoked": False if is_baseline_workflow(workflow) else None,
    }


@router.post("/upload/{job_id}/retry", status_code=202, dependencies=[Depends(require_operator_role)])
async def retry_upload_analysis(request: Request, job_id: UploadJobPath):
    settings = request.app.state.settings
    request_id = getattr(request.state, "request_id", None)
    requested_job_id = str(job_id or "").strip()
    if not UPLOAD_JOB_ID_PATTERN.match(requested_job_id):
        return _large_upload_error(
            400,
            "invalid_upload_job",
            "The stored import identifier is invalid.",
            error_code="validation_failed",
            failed_stage="validation",
            retryable=False,
        )

    status_payload = upload_jobs.read_upload_status(requested_job_id) or {}
    if status_payload and not payload_matches_dataset_scope(status_payload):
        status_payload = {}
    active_status = str(status_payload.get("status") or "").strip().upper()
    active_processing_state = str(status_payload.get("processing_state") or "").strip().lower()
    if active_status in {"PENDING", "QUEUED", "PROCESSING", "RUNNING_SII"} or active_processing_state in {"queued", "pending", "processing", "running_sii"}:
        return JSONResponse(
            status_code=409,
            content={
                **status_payload,
                **build_upload_error_payload(
                    "validation_failed",
                    message="This import is already queued or running.",
                    failed_stage="baseline_job_creation",
                    retryable=False,
                    legacy_error_type="upload_job_already_active",
                    job_id=requested_job_id,
                    status_url=f"/api/data/upload-status/{requested_job_id}",
                ),
            },
        )

    file_path = status_payload.get("file_path")
    shared_upload_source_key = str(status_payload.get("shared_upload_source_key") or "").strip()
    has_local_file = _resolve_upload_source_path(settings.runtime_dir, file_path) is not None
    if not status_payload or (not has_local_file and not shared_upload_source_key):
        return _large_upload_error(
            404,
            "upload_source_missing",
            "The stored file is no longer available. Choose another file.",
            error_code="file_storage_failed",
            failed_stage="file_storage",
            retryable=False,
            job_id=requested_job_id,
            status_url=f"/api/data/upload-status/{requested_job_id}",
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
        "error_code": None,
        "error_details": None,
        "failed_stage": None,
        "retryable": None,
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
    try:
        upload_jobs.write_job(retried)
        enqueue_upload_job(requested_job_id)
    except Exception:
        logger.exception("upload_retry_enqueue_failed request_id=%s job_id=%s", request_id, requested_job_id)
        failure = build_upload_error_payload(
            "server_unavailable",
            message="The stored file is available, but the import could not be queued. Retry shortly.",
            failed_stage="baseline_job_creation",
            retryable=True,
            legacy_error_type="upload_enqueue_failed",
            job_id=requested_job_id,
            file_stored=True,
            retry_url=f"/api/data/upload/{requested_job_id}/retry",
            status_url=f"/api/data/upload-status/{requested_job_id}",
        )
        try:
            upload_jobs.write_job({**retried, **failure})
        except Exception:
            logger.exception("upload_retry_failure_state_write_failed job_id=%s", requested_job_id)
        return JSONResponse(status_code=503, content=failure)
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
async def upload_status(request: Request, job_id: UploadJobPath):
    status_started_at = time.perf_counter()
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
    status_request_ms = round(max(0.0, (time.perf_counter() - status_started_at) * 1000), 3)
    normalized["status_server_sent_at"] = datetime.now(timezone.utc).isoformat()
    normalized["status_request_ms"] = status_request_ms
    logger.info(
        "upload_poll_timing event=status_response job_id=%s request_id=%s stage=%s status_request_ms=%s",
        job_id,
        request_id,
        normalized.get("processing_state") or normalized.get("status"),
        status_request_ms,
    )
    if str(normalized.get("status", "")).upper() == "NOT_FOUND":
        logger.warning("upload_status_missing polling_job_id=%s validation_failure_reason=upload_session_missing metadata_exists=False", job_id)
        return JSONResponse(status_code=404, content=normalized)
    return normalized


@router.get("/upload-stream/{job_id}")
async def upload_stream(job_id: UploadJobPath, request: Request = None):
    request_id = getattr(request.state, "request_id", None) if request is not None else None

    async def event_generator():
        # One-second cadence keeps backend stage transitions visible within the
        # same two-second budget as direct status polling.
        for _ in range(720):
            payload = resolve_upload_status(job_id, request_id=request_id)
            yield f"data: {json.dumps(payload)}\n\n"
            if str(payload.get("status", "")).upper() in {"COMPLETE", "FAILED", "TIMEOUT", "CANCELLED"}:
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/latest-upload")
async def latest_upload(include_persisted: bool = Query(True), request: Request = None):
    request_id = getattr(request.state, "request_id", None) if request is not None else None
    payload = resolve_latest_upload_payload(include_persisted=include_persisted, request_id=request_id)
    if request is not None:
        request.state.upload_session_id = payload.get("upload_session_id")
    return payload


@router.get("/system-interpretation")
async def system_interpretation_contract(include_persisted: bool = Query(True), request: Request = None):
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
async def data_replay(job_id: UploadJobPath):
    payload = resolve_upload_artifacts(job_id).get("replay") or read_replay_payload(job_id)
    if not payload or not payload.get("timeline"):
        raise HTTPException(status_code=404, detail="Replay was not found.")
    return payload


@router.get("/intake/{job_id}/result")
async def intake_result(job_id: UploadJobPath):
    result = read_upload_result_by_job_id(job_id)
    if not result or not payload_matches_dataset_scope(result):
        raise HTTPException(status_code=404, detail="Upload result was not found.")
    return {
        "job_id": job_id,
        "result_available": True,
        "status": "COMPLETE",
        "result": result,
        "analysis_result": ensure_analysis_result(result),
    }


@router.get("/baselines")
async def behavioral_baseline_state():
    return {
        "active_model": read_active_behavioral_model(),
        "latest_candidate": read_latest_candidate(),
        "model_index": read_model_index(),
        "workflows": {
            "create": "create_baseline",
            "analyze": "analyze_new_data",
            "extend": "extend_baseline",
        },
    }


@router.get("/baselines/jobs/{job_id}")
async def baseline_construction_result(job_id: UploadJobPath):
    result = read_baseline_result(job_id)
    if not isinstance(result, dict) or not payload_matches_dataset_scope(result):
        raise HTTPException(status_code=404, detail="Baseline construction result was not found.")
    return result


@router.get("/baselines/candidates/{model_id}")
async def behavioral_model_candidate(model_id: UploadJobPath):
    model = read_model(model_id)
    if not isinstance(model, dict) or not payload_matches_dataset_scope(model):
        raise HTTPException(status_code=404, detail="Behavioral model candidate was not found.")
    return model


@router.post(
    "/baselines/candidates/{model_id}/approve",
    dependencies=[Depends(require_operator_role)],
)
async def approve_behavioral_model_candidate(
    request: Request,
    model_id: UploadJobPath,
    approval: BehavioralModelApprovalRequest,
):
    auth_context = getattr(request.state, "auth_context", {})
    actor = str(
        auth_context.get("auth_subject")
        or request.headers.get("X-Neraium-User")
        or "operator"
    )
    try:
        activated = activate_candidate(model_id, approved_by=actor)
    except ValueError as exc:
        error_type = str(exc)
        status_code = 404 if error_type == "behavioral_model_candidate_not_found" else 409
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "FAILED",
                "error_type": error_type,
                "message": "The Behavioral Digital Model candidate could not be activated.",
            },
        )

    source_job_id = str((activated.get("source") or {}).get("job_id") or "").strip()
    if source_job_id:
        current = upload_jobs.read_upload_status(source_job_id) or {}
        upload_jobs.write_job(
            {
                **current,
                "job_id": source_job_id,
                "baseline_activation_state": "active",
                "workflow_state": "active",
                "approval": {
                    "approved_by": actor,
                    "approved_at": (activated.get("activation") or {}).get("activated_at"),
                    "note": approval.note,
                },
            }
        )
    record_audit_event(
        actor=actor,
        action="behavioral_model.approved",
        resource_type="behavioral_model",
        resource_id=model_id,
        request_id=auth_context.get("request_id"),
        detail={"version": activated.get("version"), "source_job_id": source_job_id},
    )
    return {
        "status": "active",
        "message": "Behavioral Digital Model activated.",
        "active_model": activated,
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
    path = _resolve_upload_source_path(UPLOAD_RUNTIME_STATE.runtime_dir, file_path)
    if path is None:
        return read_replay_payload(requested_job_id or None)

    result = upload_jobs.process_csv_file(path)
    replay = result.get("replay_timeline") or {}
    timeline = replay.get("timeline", []) if isinstance(replay, dict) else []
    replay_mode = "minimal_timestamp_fallback"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
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
