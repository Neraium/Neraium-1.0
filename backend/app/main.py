import logging
import re
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.routers import app_info, connectors, data, data_connections, evidence, facility, health, observability, replay
from app.services.data_connection_poller import start_data_connection_poller, stop_data_connection_poller
from app.services.data_connections import ensure_default_data_connection
from app.services.runtime_db import init_runtime_db
from app.services.upload_worker import start_upload_worker, stop_upload_worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    settings = app.state.settings
    init_runtime_db()
    ensure_default_data_connection(settings)

    upload_worker_started = False
    data_poller_started = False

    if settings.start_background_workers:
        start_upload_worker()
        upload_worker_started = True

    if settings.start_data_connection_poller:
        start_data_connection_poller()
        data_poller_started = True

    logger.info(
        "runtime_services_started process_role=%s upload_worker=%s data_poller=%s",
        settings.process_role,
        upload_worker_started,
        data_poller_started,
    )
    try:
        yield
    finally:
        if data_poller_started:
            stop_data_connection_poller()
        if upload_worker_started:
            stop_upload_worker()
        logger.info("runtime_services_stopped process_role=%s", settings.process_role)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Neraium API",
        version="0.1.0",
        description="Customer-facing API for the Neraium application.",
        lifespan=app_lifespan,
    )
    app.state.settings = settings

    app.include_router(health.router, prefix="/api")
    app.include_router(app_info.router, prefix="/api")
    app.include_router(connectors.router, prefix="/api")
    app.include_router(data_connections.router, prefix="/api")
    app.include_router(facility.router, prefix="/api")
    app.include_router(data.router, prefix="/api")
    app.include_router(evidence.router, prefix="/api")
    app.include_router(observability.router, prefix="/api")
    app.include_router(replay.router, prefix="/api")

    @app.middleware("http")
    async def add_request_id_header(request: Request, call_next):
        response = await call_next(request)
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            response.headers["X-Request-Id"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'")
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

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
            return JSONResponse(
                status_code=exc.status_code,
                content=auth_error_payload(exc.detail),
                headers=exc.headers,
            )
        if not request.url.path.startswith("/api/data/upload"):
            detail = exc.detail
            return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)

        return JSONResponse(
            status_code=exc.status_code,
            content=upload_error_payload(exc.detail, status_code=exc.status_code),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def upload_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        if not request.url.path.startswith("/api/data/upload"):
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
        return JSONResponse(
            status_code=500,
            content=upload_error_payload("Unexpected processing error", status_code=500),
            headers=cors_error_headers(request),
        )

    @app.get("/")
    def read_root():
        return {
            "service": "neraium-api",
            "status": "ok",
            "docs": "/docs",
            "health": "/health",
            "process_role": settings.process_role,
            "background_workers": settings.start_background_workers,
            "data_poller": settings.start_data_connection_poller,
        }

    @app.get("/health")
    def health_check_alias():
        return {
            "status": "ok",
            "service": "neraium-api",
            "process_role": settings.process_role,
        }

    return app


def upload_error_payload(detail: Any, status_code: int) -> dict[str, Any]:
    error_type = "upload_request_error"
    message = "Upload interrupted. Refresh your workspace and try again."
    if isinstance(detail, dict):
        error_type = str(detail.get("error_type") or error_type)
        message = normalize_error_message(detail.get("message") or detail.get("detail") or detail.get("error") or message)
    else:
        message = normalize_error_message(detail)

    if status_code in {401, 403}:
        return auth_error_payload(detail)

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
    message = "Telemetry processing session could not be validated."
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
    if not error:
        return "Unknown error"
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        for key in ("message", "detail", "error"):
            if error.get(key):
                return normalize_error_message(error[key])
        return str(error)
    message = getattr(error, "message", None)
    if message:
        return normalize_error_message(message)
    return str(error) or "Unexpected processing error"


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
