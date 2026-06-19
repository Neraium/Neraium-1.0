from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.services.runtime_db import queue_metrics, queue_operational_metrics
from app.services.service_status import STARTUP_STATUS, service_health_snapshot
from app.services.sii_runner import build_runner_status
from app.services.upload_state_repository import shared_state_configured, upload_state_backend

router = APIRouter(tags=["health"])


@router.get("/health")
def read_health() -> JSONResponse:
    snapshot = service_health_snapshot()
    payload = {**snapshot, "service": "neraium-api"}
    return JSONResponse(
        status_code=status.HTTP_200_OK if snapshot["status"] == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )


@router.get("/ready")
def read_ready() -> JSONResponse:
    checks: dict[str, str] = {
        "startup": "ok",
        "runtime_db": "ok",
        "queue": "ok",
        "inference_path": "ok",
    }
    details: dict[str, object] = {}

    snapshot = service_health_snapshot()
    if snapshot["status"] != "ok":
        checks["startup"] = "error"

    try:
        metrics = queue_metrics()
        details["queue_metrics"] = metrics
        try:
            details["queue_operational_metrics"] = queue_operational_metrics()
        except Exception:
            details["queue_operational_metrics"] = {}
    except Exception:
        checks["runtime_db"] = "error"
        checks["queue"] = "error"

    try:
        details["runner_status"] = build_runner_status()
    except Exception:
        checks["inference_path"] = "error"

    is_ready = all(value == "ok" for value in checks.values())
    payload = {
        "status": "ready" if is_ready else "not_ready",
        "service": "neraium-api",
        "checks": checks,
        "details": details,
        "startup_complete": snapshot["startup_complete"],
        "failed_modules": snapshot["failed_modules"],
        "runtime_db_ready": STARTUP_STATUS.get("runtime_db_ready", False),
        "default_connection_ready": STARTUP_STATUS.get("default_connection_ready", False),
        "upload_worker_started": STARTUP_STATUS.get("upload_worker_started", False),
        "data_poller_started": STARTUP_STATUS.get("data_poller_started", False),
        "upload_state_backend": upload_state_backend(),
        "upload_state_shared_configured": shared_state_configured(),
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )
