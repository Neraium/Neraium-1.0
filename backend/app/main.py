import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers

from app.core.config import Settings, get_settings
from app.core.logging_config import bind_log_context, configure_logging, reset_log_context
from app.core.security import require_admin_role
from app.routers import app_info, audit, auth, connectors, data, data_connections, distributed_cognition, ecosystem, evidence, facility, health, observability, replay
from app.routers.data import wait_for_upload_workers
from app.services.data_connection_poller import start_data_connection_poller, stop_data_connection_poller
from app.services.data_connections import ensure_default_data_connection
from app.services.rate_limiter import clear_rate_limits
from app.services.runtime_db import clear_stale_processing_queue_jobs, configure_runtime_dir as configure_runtime_db_dir, init_runtime_db, prune_runtime_db_records
from app.services.service_status import STARTUP_STATUS, reset_startup_status, service_health_snapshot
from app.services.sii_runner import build_runner_status, configure_runtime_dir as configure_sii_runner_dir
from app.services.upload_jobs import configure_runtime_dir as configure_upload_jobs_dir
from app.services.upload_state_repository import shared_state_configured, upload_state_backend, warm_latest_upload_cache
from app.services.upload_worker import start_upload_worker, stop_upload_worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    settings = app.state.settings
    upload_worker_started = False
    data_poller_started = False
    startup_started_at = time.perf_counter()
    reset_startup_status()
    STARTUP_STATUS["upload_state_backend"] = upload_state_backend()
    STARTUP_STATUS["upload_state_shared_configured"] = shared_state_configured()

    logger.info(
        "runtime_services_starting",
        extra={
            "event": "runtime_services_starting",
            "app_env": settings.app_env,
            "process_role": settings.process_role,
            "runtime_dir": str(settings.runtime_dir),
            "upload_state_backend": STARTUP_STATUS["upload_state_backend"],
            "upload_state_shared_configured": STARTUP_STATUS["upload_state_shared_configured"],
        },
    )
    if settings.app_env == "production" and not shared_state_configured():
        logger.warning(
            "upload_state_shared_storage_not_configured",
            extra={
                "event": "upload_state_shared_storage_not_configured",
                "app_env": settings.app_env,
                "upload_state_backend": upload_state_backend(),
                "expected_env": "NERAIUM_UPLOAD_STATE_BUCKET",
            },
        )

    try:
        try:
            init_runtime_db()
            recovered_jobs = clear_stale_processing_queue_jobs()
            prune_stats = prune_runtime_db_records()
            if prune_stats.get("upload_queue_deleted") or prune_stats.get("evidence_runs_deleted"):
                logger.info("runtime_db_pruned", extra={"event": "runtime_db_pruned", **prune_stats})
            if recovered_jobs:
                logger.warning(
                    "stale_processing_jobs_recovered",
                    extra={"event": "stale_processing_jobs_recovered", "count": recovered_jobs},
                )
            STARTUP_STATUS["runtime_db_ready"] = True
        except Exception as error:
            STARTUP_STATUS["failed_modules"].append("runtime_db: initialization_failed")
            logger.exception("runtime_db_startup_failure")
            raise RuntimeError("Required runtime database initialization failed.") from error

        try:
            warm_latest_upload_cache()
        except Exception:
            logger.exception("latest_upload_cache_warmup_failure")

        try:
            ensure_default_data_connection(settings)
            STARTUP_STATUS["default_connection_ready"] = True
        except Exception as error:
            STARTUP_STATUS["failed_modules"].append("default_connection: initialization_failed")
            logger.exception("default_connection_startup_failure")
            raise RuntimeError("Default data connection initialization failed.") from error

        if settings.start_background_workers:
            try:
                start_upload_worker()
                upload_worker_started = True
                STARTUP_STATUS["upload_worker_started"] = True
            except Exception as error:
                STARTUP_STATUS["failed_modules"].append("upload_worker: startup_failed")
                logger.exception("upload_worker_startup_failure")
                raise RuntimeError("Upload worker startup failed.") from error

        if settings.start_data_connection_poller:
            try:
                start_data_connection_poller()
                data_poller_started = True
                STARTUP_STATUS["data_poller_started"] = True
            except Exception as error:
                STARTUP_STATUS["failed_modules"].append("data_poller: startup_failed")
                logger.exception("data_poller_startup_failure")
                raise RuntimeError("Data connection poller startup failed.") from error

        STARTUP_STATUS["startup_complete"] = True
        logger.info(
            "runtime_services_started",
            extra={
                "event": "runtime_services_started",
                "process_role": settings.process_role,
                "upload_worker": upload_worker_started,
                "data_poller": data_poller_started,
                "startup_duration_ms": round((time.perf_counter() - startup_started_at) * 1000, 2),
            },
        )
        yield
    finally:
        shutdown_started_at = time.perf_counter()
        shutdown_failures: list[str] = []
        if data_poller_started:
            try:
                if not stop_data_connection_poller(timeout_seconds=settings.shutdown_timeout_seconds):
                    shutdown_failures.append("data_poller_timeout")
            except Exception:
                shutdown_failures.append("data_poller_failure")
                logger.exception("data_poller_shutdown_failure")
        if upload_worker_started:
            try:
                if not stop_upload_worker(timeout_seconds=settings.shutdown_timeout_seconds):
                    shutdown_failures.append("upload_worker_timeout")
            except Exception:
                shutdown_failures.append("upload_worker_failure")
                logger.exception("upload_worker_shutdown_failure")
        if not wait_for_upload_workers(timeout=settings.shutdown_timeout_seconds):
            shutdown_failures.append("request_upload_workers_timeout")
            logger.error(
                "request_upload_workers_shutdown_timeout",
                extra={
                    "event": "request_upload_workers_shutdown_timeout",
                    "timeout_seconds": settings.shutdown_timeout_seconds,
                },
            )
        clear_rate_limits()
        STARTUP_STATUS["upload_worker_started"] = False
        STARTUP_STATUS["data_poller_started"] = False
        logger.info(
            "runtime_services_stopped",
            extra={
                "event": "runtime_services_stopped",
                "process_role": settings.process_role,
                "shutdown_duration_ms": round((time.perf_counter() - shutdown_started_at) * 1000, 2),
                "shutdown_failures": shutdown_failures,
            },
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    reset_startup_status()
    # Keep service runtime paths aligned with app settings, especially in tests
    # where each app instance may use a dedicated tmp runtime directory.
    configure_runtime_db_dir(settings.runtime_dir)
    configure_upload_jobs_dir(settings.runtime_dir)
    configure_sii_runner_dir(settings.runtime_dir)
    data.invalidate_latest_upload_cache()
    app = FastAPI(
        title="Neraium API",
        version="0.1.0",
        description="API for the Neraium platform and its Systemic Infrastructure Intelligence (SII).",
        lifespan=app_lifespan,
    )
    app.state.settings = settings

    app.include_router(health.router, prefix="/api")
    app.include_router(app_info.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(connectors.router, prefix="/api")
    app.include_router(data_connections.router, prefix="/api")
    app.include_router(facility.router, prefix="/api")
    app.include_router(data.router, prefix="/api")
    app.include_router(evidence.router, prefix="/api")
    app.include_router(observability.router, prefix="/api")
    app.include_router(replay.router, prefix="/api")
    app.include_router(audit.router, prefix="/api")
    app.include_router(ecosystem.router, prefix="/api")
    app.include_router(distributed_cognition.router, prefix="/api")

    @app.middleware("http")
    async def add_request_context(request: Request, call_next):
        inbound_request_id = str(request.headers.get("X-Request-Id") or "").strip()
        request_id = (
            inbound_request_id
            if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", inbound_request_id)
            else uuid.uuid4().hex
        )
        inbound_upload_session_id = str(request.headers.get("X-Upload-Session-Id") or "").strip()
        upload_session_id = (
            inbound_upload_session_id
            if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", inbound_upload_session_id)
            else None
        )
        request.state.request_id = request_id
        if not inbound_request_id:
            request.scope["headers"] = [
                *request.scope.get("headers", []),
                (b"x-request-id", request_id.encode("ascii")),
            ]
            # Request.headers may already be cached by header validation.
            request._headers = Headers(scope=request.scope)
        if upload_session_id:
            request.state.upload_session_id = upload_session_id
        tokens = bind_log_context(request_id=request_id, upload_session_id=upload_session_id)
        started_at = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            if upload_session_id:
                response.headers["X-Upload-Session-Id"] = upload_session_id
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault("Content-Security-Policy", "default-src 'self'")
            if request.url.scheme == "https":
                response.headers.setdefault(
                    "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                )
            return response
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            status_code = getattr(response, "status_code", 500)
            log_method = (
                logger.debug
                if request.url.path in {"/health", "/api/health", "/api/ready"}
                else logger.info
            )
            log_method(
                "http_request_completed",
                extra={
                    "event": "http_request_completed",
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": status_code,
                    "duration_ms": duration_ms,
                },
            )
            reset_log_context(tokens)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def upload_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        if exc.status_code in {401, 403}:
            if request.url.path.startswith("/api/auth/"):
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers,
                )
            return JSONResponse(
                status_code=exc.status_code,
                content=auth_error_payload(exc.detail),
                headers=exc.headers,
            )
        if not is_upload_analysis_path(request.url.path):
            detail = exc.detail
            return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)

        return JSONResponse(
            status_code=exc.status_code,
            content=upload_error_payload(exc.detail, status_code=exc.status_code),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def upload_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        if not is_upload_analysis_path(request.url.path):
            logger.exception("api_request_failed path=%s", request.url.path)
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Unexpected API error.",
                    "error_type": "api_request_error",
                    "path": request.url.path,
                },
                headers=cors_error_headers(request),
            )
        logger.exception("upload_request_failed path=%s", request.url.path)
        return JSONResponse(
            status_code=500,
            content=upload_error_payload(
                {
                    "message": "Upload interrupted. Refresh your workspace and try again.",
                    "error_type": "upload_request_error",
                },
                status_code=500,
            ),
            headers=cors_error_headers(request),
        )

    @app.get("/")
    def read_root():
        return {
            "service": "neraium-api",
            "status": service_health_snapshot()["status"],
            "docs": "/docs",
            "health": "/health",
            "process_role": settings.process_role,
            "background_workers": settings.start_background_workers,
            "data_poller": settings.start_data_connection_poller,
        }

    @app.get("/health")
    def health_check_alias():
        snapshot = service_health_snapshot()
        return JSONResponse(
            status_code=200 if snapshot["status"] == "ok" else 503,
            content={**snapshot, "service": "neraium-api", "process_role": settings.process_role},
        )

    # Legacy frontend compatibility aliases. Older bundles may call shorthand
    # endpoints without the "/api/..." prefix.
    @app.get("/latest-upload")
    async def latest_upload_alias(include_persisted: int | bool = True):
        return await data.latest_upload(include_persisted=include_persisted)

    @app.get("/systems")
    def systems_alias(include_persisted: bool = True, domain_mode: str | None = None):
        return facility.read_facility_systems(include_persisted=include_persisted, domain_mode=domain_mode)

    @app.get("/api/startup-status", dependencies=[Depends(require_admin_role)])
    def read_startup_status():
        return STARTUP_STATUS

    @app.get("/api/routes/debug", dependencies=[Depends(require_admin_role)])
    def read_route_debug():
        return {
            "mounted": True,
            "route_count": len(app.routes),
            "routes": [
                {
                    "path": route.path,
                    "name": route.name,
                    "methods": sorted(route.methods) if getattr(route, "methods", None) else [],
                }
                for route in app.routes
            ],
        }

    return app


UPLOAD_SERVICE_UNAVAILABLE_MESSAGE = "Analysis service temporarily unavailable. Please retry."
UPLOAD_SERVICE_UNAVAILABLE_STATUSES = {502, 503, 504}
UPLOAD_SPECIFIC_TRANSIENT_ERRORS = {
    "shared_upload_queue_not_configured",
    "upload_queue_saturated",
    "upload_rate_limited",
    "upload_status_rate_limited",
}
HTML_ERROR_MARKERS = (
    "<!doctype html",
    "<html",
    "<head>",
    "<body",
    "<title>502 bad gateway</title>",
    "<title>503 service temporarily unavailable</title>",
    "<title>504 gateway time-out</title>",
)


def is_upload_analysis_path(path: str) -> bool:
    normalized = str(path or "")
    return (
        normalized.startswith("/api/data/upload")
        or bool(re.match(r"^/api/data/intake/[^/]+/result$", normalized))
    )


def is_html_error_message(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    if not text:
        return False
    return any(marker in text for marker in HTML_ERROR_MARKERS)


def is_service_unavailable_upload_error(status_code: int, error_type: str | None, message: str) -> bool:
    if is_html_error_message(message):
        return True
    if status_code not in UPLOAD_SERVICE_UNAVAILABLE_STATUSES:
        return False
    return not error_type or error_type == "upload_request_error" or error_type not in UPLOAD_SPECIFIC_TRANSIENT_ERRORS


def upload_error_payload(detail: Any, status_code: int) -> dict[str, Any]:
    error_type = "upload_request_error"
    message = "Dataset import was interrupted. Refresh the workspace and retry the analysis."
    if isinstance(detail, dict):
        error_type = str(detail.get("error_type") or error_type)
        message = normalize_error_message(detail.get("message") or detail.get("detail") or detail.get("error") or message)
    else:
        message = normalize_error_message(detail)

    if status_code in {401, 403}:
        return auth_error_payload(detail)

    if is_service_unavailable_upload_error(status_code, error_type, message):
        error_type = "service_unavailable"
        message = UPLOAD_SERVICE_UNAVAILABLE_MESSAGE

    return {
        "job_id": None,
        "status": "FAILED",
        "progress": 0,
        "processing_state": "failed",
        "message": message,
        "error_type": error_type,
        "error": message,
    }


def auth_error_payload(detail: Any | None = None) -> dict[str, Any]:
    message = "Your analysis session could not be verified. Sign in again, then retry the analysis."
    payload = {
        "job_id": None,
        "status": "unauthorized",
        "progress": 0,
        "processing_state": "unauthorized",
        "message": message,
        "error_type": "auth",
        "error": message,
    }
    if isinstance(detail, dict) and isinstance(detail.get("auth_diagnostic"), dict):
        payload["auth_diagnostic"] = detail["auth_diagnostic"]
    return payload


def normalize_error_message(error: Any) -> str:
    fallback = "Analysis could not complete. Retry the analysis. If it happens again, contact an administrator."
    if not error:
        return fallback
    if isinstance(error, dict):
        for key in ("message", "detail", "error"):
            if error.get(key):
                return normalize_error_message(error[key])
        return fallback
    message = str(getattr(error, "message", None) or error or "").strip()
    if not message:
        return fallback
    if re.search(r"traceback|stack trace|exception|localhost|/api/|\b(?:sql|python|uvicorn|psycopg|sqlite|errno)\b|[a-z]:\\", message, re.IGNORECASE):
        return fallback
    return message


def cors_error_headers(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    if not origin:
        return {}
    settings = request.app.state.settings
    origin_allowed = origin in settings.cors_origins
    if not origin_allowed and settings.cors_origin_regex:
        origin_allowed = re.match(settings.cors_origin_regex, origin) is not None
    if not origin_allowed:
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Vary": "Origin",
    }


app = create_app()
