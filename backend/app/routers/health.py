import logging
import os

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.services.runtime_db import db_connection, queue_metrics, queue_operational_metrics, upload_queue_backend
from app.services.service_status import STARTUP_STATUS, service_health_snapshot
from app.services.sii_runner import build_runner_status
from app.services.upload_session_service import resolve_latest_upload_session, session_metrics_snapshot
from app.services.upload_state_repository import shared_state_configured, upload_state_backend

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


def _build_sha() -> str:
    for key in ("NERAIUM_BUILD_SHA", "GIT_SHA", "RENDER_GIT_COMMIT", "VERCEL_GIT_COMMIT_SHA", "HEROKU_SLUG_COMMIT"):
        value = os.getenv(key, "").strip()
        if value:
            return value[:12]
    return "unknown"


def _production_config_warnings(settings, *, state_shared: bool, queue_backend: str) -> list[str]:
    warnings: list[str] = []
    app_env = str(settings.app_env or "").strip().lower()
    if app_env not in {"prod", "production"}:
        return warnings
    if not any("app.neraium.com" in str(origin) for origin in settings.cors_origins) and not settings.cors_origin_regex:
        warnings.append("production_cors_origin_missing")
    if str(settings.process_role or "").lower() in {"api", "worker"} and not state_shared:
        warnings.append("split_role_shared_upload_state_not_configured")
    if queue_backend == "runtime_db" and str(settings.process_role or "").lower() == "api" and not settings.start_background_workers:
        warnings.append("api_runtime_db_queue_requires_local_worker_or_poll_processing")
    if not os.access(settings.runtime_dir, os.W_OK):
        warnings.append("runtime_dir_not_writable")
    return warnings


def runtime_diagnostics(settings=None, *, include_upload_session: bool = True) -> dict[str, object]:
    settings = settings or get_settings()
    state_backend = upload_state_backend()
    state_shared = shared_state_configured()
    queue_backend = upload_queue_backend()
    if include_upload_session:
        latest_session = resolve_latest_upload_session(include_persisted=True)
        snapshot = latest_session.get("snapshot") if isinstance(latest_session.get("snapshot"), dict) else {}
    else:
        latest_session = {}
        snapshot = {}
    warnings = _production_config_warnings(settings, state_shared=state_shared, queue_backend=queue_backend)
    return {
        "deployment": {
            "app_env": settings.app_env,
            "process_role": settings.process_role,
            "build_sha": _build_sha(),
            "runtime_dir": str(settings.runtime_dir),
            "runtime_dir_writable": os.access(settings.runtime_dir, os.W_OK),
        },
        "api": {
            "backend_host": settings.backend_host,
            "backend_port": settings.backend_port,
            "upload_endpoint": "/api/data/upload",
            "upload_status_endpoint": "/api/data/upload-status/{job_id}",
            "cors_origins": settings.cors_origins,
            "cors_origin_regex": settings.cors_origin_regex,
        },
        "upload": {
            "upload_state_backend": state_backend,
            "upload_state_shared_configured": state_shared,
            "queue_backend": queue_backend,
            "max_upload_size_bytes": settings.max_upload_size_bytes,
            "max_pending_upload_jobs": settings.max_pending_upload_jobs,
            "latest_upload_session_id": latest_session.get("upload_session_id"),
            "latest_upload_state": latest_session.get("session_state"),
            "latest_upload_status": snapshot.get("status") or snapshot.get("processing_state"),
            "latest_upload_error_type": snapshot.get("error_type"),
            "latest_upload_message": snapshot.get("message") or snapshot.get("error"),
        },
        "worker": {
            "configured_start_background_workers": settings.start_background_workers,
            "startup_worker_started": STARTUP_STATUS.get("upload_worker_started", False),
            "data_poller_started": STARTUP_STATUS.get("data_poller_started", False),
        },
        "warnings": warnings,
    }


def _runtime_db_available() -> bool:
    try:
        with db_connection() as connection:
            row = connection.execute("SELECT 1 AS ready").fetchone()
        return row is not None
    except Exception:
        logger.warning(
            "readiness_dependency_failed",
            extra={"event": "readiness_dependency_failed", "dependency": "runtime_db"},
        )
        return False


def readiness_snapshot(settings) -> tuple[dict[str, str], list[str]]:
    checks: dict[str, str] = {
        "startup": "ok",
        "runtime_db": "ok",
        "default_connection": "ok",
        "shared_upload_state": "ok",
    }
    failed_modules = list(STARTUP_STATUS.get("failed_modules") or [])
    if failed_modules or not STARTUP_STATUS.get("startup_complete", False):
        checks["startup"] = "error"
    if not STARTUP_STATUS.get("runtime_db_ready", False) or not _runtime_db_available():
        checks["runtime_db"] = "error"
    if not STARTUP_STATUS.get("default_connection_ready", False):
        checks["default_connection"] = "error"
    if (
        str(settings.app_env or "").strip().lower() in {"prod", "production"}
        and str(settings.process_role or "").strip().lower() in {"api", "worker"}
        and not shared_state_configured()
    ):
        checks["shared_upload_state"] = "error"
    return checks, failed_modules


@router.get("/health")
def read_health(request: Request) -> JSONResponse:
    snapshot = service_health_snapshot(include_upload_session=False)
    payload = {**snapshot, "service": "neraium-api", "diagnostics": runtime_diagnostics(request.app.state.settings, include_upload_session=False)}
    return JSONResponse(
        status_code=status.HTTP_200_OK if snapshot["status"] == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )


@router.get("/ready")
def read_ready(request: Request, verbose: bool = False) -> JSONResponse:
    settings = request.app.state.settings
    checks, failed_modules = readiness_snapshot(settings)
    diagnostics = runtime_diagnostics(settings, include_upload_session=verbose)
    details: dict[str, object] = {
        "mode": "verbose" if verbose else "lightweight",
    }

    if verbose:
        snapshot = service_health_snapshot(include_upload_session=True)
        latest_session = resolve_latest_upload_session(include_persisted=True)
        session_state = str(latest_session.get("session_state") or "empty")
        if snapshot["status"] != "ok":
            checks["startup"] = "error"
        details["upload_session"] = {
            "state": session_state,
            "source": latest_session.get("session_source"),
            "upload_session_id": latest_session.get("upload_session_id"),
        }
        details["upload_session_metrics"] = session_metrics_snapshot(current_state=session_state)
        try:
            details["queue_metrics"] = queue_metrics()
        except Exception:
            checks["runtime_db"] = "error"
            details["queue_metrics"] = {}
        try:
            details["queue_operational_metrics"] = queue_operational_metrics()
        except Exception:
            details["queue_operational_metrics"] = {}
        try:
            details["runner_status"] = build_runner_status()
        except Exception:
            details["runner_status"] = {"runner_available": False}

    is_ready = all(value == "ok" for value in checks.values())
    payload = {
        "status": "ready" if is_ready else "not_ready",
        "service": "neraium-api",
        "checks": checks,
        "details": details,
        "startup_complete": bool(STARTUP_STATUS.get("startup_complete", False)),
        "failed_modules": failed_modules,
        "runtime_db_ready": STARTUP_STATUS.get("runtime_db_ready", False),
        "default_connection_ready": STARTUP_STATUS.get("default_connection_ready", False),
        "upload_worker_started": STARTUP_STATUS.get("upload_worker_started", False),
        "data_poller_started": STARTUP_STATUS.get("data_poller_started", False),
        "upload_state_backend": upload_state_backend(),
        "upload_state_shared_configured": shared_state_configured(),
        "diagnostics": diagnostics,
        "config_warnings": diagnostics.get("warnings", []),
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )
