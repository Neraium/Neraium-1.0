from __future__ import annotations

from typing import Any

STARTUP_STATUS: dict[str, Any] = {
    "startup_complete": False,
    "failed_modules": [],
    "runtime_db_ready": False,
    "default_connection_ready": False,
    "upload_worker_started": False,
    "data_poller_started": False,
    "upload_state_backend": "unknown",
    "upload_state_shared_configured": False,
}


def reset_startup_status() -> None:
    STARTUP_STATUS.update(
        {
            "startup_complete": False,
            "failed_modules": [],
            "runtime_db_ready": False,
            "default_connection_ready": False,
            "upload_worker_started": False,
            "data_poller_started": False,
            "upload_state_backend": "unknown",
            "upload_state_shared_configured": False,
        }
    )


def service_health_snapshot() -> dict[str, Any]:
    failed_modules = list(STARTUP_STATUS.get("failed_modules") or [])
    startup_complete = bool(STARTUP_STATUS.get("startup_complete"))
    degraded = bool(failed_modules)
    return {
        "status": "degraded" if degraded else "ok",
        "startup_complete": startup_complete,
        "failed_modules": failed_modules,
    }
