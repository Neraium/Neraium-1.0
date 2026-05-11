import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.routers import app_info, connectors, data, data_connections, evidence, facility, health, observability
from app.services.data_connection_poller import start_data_connection_poller, stop_data_connection_poller
from app.services.data_connections import ensure_default_data_connection
from app.services.runtime_db import init_runtime_db
from app.services.upload_worker import start_upload_worker, stop_upload_worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    init_runtime_db()
    ensure_default_data_connection(app.state.settings)
    start_upload_worker()
    start_data_connection_poller()
    logger.info("runtime_services_started")
    try:
        yield
    finally:
        stop_data_connection_poller()
        stop_upload_worker()
        logger.info("runtime_services_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Neraium API",
        version="0.1.0",
        description="Customer-facing API for the Neraium application.",
        lifespan=app_lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(app_info.router, prefix="/api")
    app.include_router(connectors.router, prefix="/api")
    app.include_router(data_connections.router, prefix="/api")
    app.include_router(facility.router, prefix="/api")
    app.include_router(data.router, prefix="/api")
    app.include_router(evidence.router, prefix="/api")
    app.include_router(observability.router, prefix="/api")

    @app.middleware("http")
    async def add_request_id_header(request: Request, call_next):
        response = await call_next(request)
        request_id = getattr(request.state, "request_id", None)
        if request_id:
            response.headers["X-Request-Id"] = request_id
        return response

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
            raise exc
        return JSONResponse(
            status_code=500,
            content=upload_error_payload("Unexpected processing error", status_code=500),
        )

    @app.get("/")
    def read_root():
        return {
            "service": "neraium-api",
            "status": "ok",
            "docs": "/docs",
            "health": "/health",
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


app = create_app()


@app.get("/health")
def health_check_alias():
    return {"status": "ok", "service": "neraium-api"}





