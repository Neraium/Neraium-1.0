from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.services.runtime_db import queue_metrics
from app.services.sii_runner import build_runner_status

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
    }
    return JSONResponse(
        status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )

@router.get("/auth-debug")
async def auth_debug(request: Request):
    import hashlib
    import os

    configured = os.getenv("NERAIUM_API_TOKEN", "").strip()
    received = request.headers.get("X-Neraium-Access-Code", "").strip()

    def digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()[:16] if value else ""

    return {
        "configured_present": bool(configured),
        "configured_len": len(configured),
        "configured_sha16": digest(configured),
        "received_present": bool(received),
        "received_len": len(received),
        "received_sha16": digest(received),
        "match": bool(configured) and configured == received,
    }
