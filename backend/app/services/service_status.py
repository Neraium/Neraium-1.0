from __future__ import annotations

from typing import Any

from app.services.upload_session_service import resolve_latest_upload_session, session_metrics_snapshot

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
    latest_session = resolve_latest_upload_session(include_persisted=True)
    session_state = str(latest_session.get("session_state") or "empty")
    metrics = session_metrics_snapshot(current_state=session_state)
    degraded_reasons: list[str] = []
    if session_state in {"stale", "error"}:
        degraded_reasons.append(f"upload_session:{session_state}")
    if failed_modules:
        degraded_reasons.extend(failed_modules)
    return {
        "status": "degraded" if degraded_reasons else "ok",
        "startup_complete": startup_complete,
        "failed_modules": failed_modules,
        "degraded_reasons": degraded_reasons,
        "upload_session_state": session_state,
        "upload_session_metrics": metrics,
    }
