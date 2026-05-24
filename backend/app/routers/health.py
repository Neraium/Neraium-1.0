from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.services.runtime_db import queue_metrics
from app.services.sii_runner import build_runner_status
from app.services.upload_jobs import shared_state_configured, upload_state_backend

router = APIRouter(tags=["health"])


@router.get("/health")
def read_health() -> dict[str, str]:
    return {"status": "ok", "service": "neraium-api"}


@router.get("/ready")
def read_ready() -> JSONResponse:
    checks: dict[str, str] = {
        "runtime_db": "ok",
        "queue": "ok",
        "inference_path": "ok",
    }
    details: dict[str, object] = {}

    try:
        metrics = queue_metrics()
        details["queue_metrics"] = metrics
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
        "upload_state_backend": upload_state_backend(),
        "upload_state_shared_configured": shared_state_configured(),
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )
