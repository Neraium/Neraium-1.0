from __future__ import annotations

import logging
import signal
import threading
import time
from types import FrameType
from typing import Any

import uvicorn

from app.core.config import Settings, get_settings, validate_environment_completeness
from app.core.logging_config import configure_logging
from app.services.worker_heartbeat import (
    publish_telemetry_worker_heartbeat,
    publish_worker_heartbeat,
)
logger = logging.getLogger(__name__)


def _publish_worker_health(**kwargs: Any) -> None:
    try:
        publish_worker_heartbeat(**kwargs)
    except Exception:
        logger.exception("worker_heartbeat_publish_failed", extra={"event": "worker_heartbeat_publish_failed"})


def _publish_telemetry_worker_health(**kwargs: Any) -> None:
    try:
        publish_telemetry_worker_heartbeat(**kwargs)
    except Exception:
        logger.exception(
            "telemetry_worker_heartbeat_publish_failed",
            extra={"event": "telemetry_worker_heartbeat_publish_failed"},
        )


# Keep service imports behind configuration validation. Several service modules
# resolve runtime paths at import time, so importing them at module load would
# bypass the entrypoint's structured configuration-failure diagnostics.
def configure_runtime_db_dir(runtime_dir) -> None:
    from app.services.runtime_db import configure_runtime_dir

    configure_runtime_dir(runtime_dir)


def init_runtime_db() -> None:
    from app.services.runtime_db import init_runtime_db as initialize

    initialize()


def configure_sii_runner_dir(runtime_dir) -> None:
    from app.services.sii_runner import configure_runtime_dir

    configure_runtime_dir(runtime_dir)


def configure_upload_jobs_dir(runtime_dir) -> None:
    from app.services.upload_jobs import configure_runtime_dir

    configure_runtime_dir(runtime_dir)


def process_next_queued_upload_job() -> bool:
    from app.services.upload_jobs import process_next_queued_upload_job as process_next

    return process_next()


def run_due_live_analysis_jobs() -> dict[str, Any]:
    from app.services.live_analysis import run_due_live_analyses

    return run_due_live_analyses()


def build_worker_telemetry_runtime(settings: Settings) -> Any:
    from app.services.telemetry_runtime import build_telemetry_runtime

    return build_telemetry_runtime(settings)


def shared_state_configured() -> bool:
    from app.services.upload_state_repository import shared_state_configured as configured

    return configured()


def upload_state_backend() -> str:
    from app.services.upload_state_repository import upload_state_backend as backend

    return backend()


def _configure_logging(settings: Settings | None = None) -> None:
    configure_logging(
        level=getattr(settings, "log_level", "INFO"),
        log_format=getattr(settings, "log_format", "json"),
    )


def _normalize_startup_role(role: str) -> str:
    normalized = str(role or "").strip().lower()
    if normalized == "monolith":
        return "all"
    if normalized in {"api", "worker", "all"}:
        return normalized
    return "all"


def _configure_runtime_services(settings: Settings) -> None:
    configure_runtime_db_dir(settings.runtime_dir)
    configure_upload_jobs_dir(settings.runtime_dir)
    configure_sii_runner_dir(settings.runtime_dir)


def _configure_worker_telemetry_scheduler(settings: Settings) -> Any | None:
    database_url = str(getattr(settings, "telemetry_database_url", "") or "").strip()
    if not database_url:
        logger.info(
            "telemetry_worker_not_configured",
            extra={"event": "telemetry_worker_not_configured"},
        )
        return None

    runtime = build_worker_telemetry_runtime(settings)
    if not bool(getattr(runtime, "available", False)):
        logger.error(
            "telemetry_worker_configuration_invalid",
            extra={
                "event": "telemetry_worker_configuration_invalid",
                "error_code": str(
                    getattr(runtime, "unavailable_code", None)
                    or "telemetry_runtime_configuration_invalid"
                ),
            },
        )
        raise RuntimeError("Configured telemetry runtime is unavailable.")

    try:
        runtime.verify_readiness()
    except Exception as error:
        logger.error(
            "telemetry_worker_readiness_failed",
            extra={
                "event": "telemetry_worker_readiness_failed",
                "error_type": type(error).__name__,
            },
        )
        raise RuntimeError("Configured telemetry runtime is not ready.") from None

    scheduler = getattr(runtime, "scheduler", None)
    if scheduler is None or not callable(getattr(scheduler, "run_once", None)):
        logger.error(
            "telemetry_worker_scheduler_unavailable",
            extra={"event": "telemetry_worker_scheduler_unavailable"},
        )
        raise RuntimeError("Configured telemetry scheduler is unavailable.")
    return scheduler


def run_api(settings: Settings) -> None:
    logger.info(
        "neraium_api_starting",
        extra={
            "event": "neraium_api_starting",
            "process_role": settings.process_role,
            "host": settings.backend_host,
            "port": settings.backend_port,
        },
    )
    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        log_config=None,
        access_log=False,
    )


def _install_shutdown_handlers(
    shutdown_event: threading.Event,
) -> dict[signal.Signals, Any]:
    previous: dict[signal.Signals, Any] = {}

    def request_shutdown(signum: int, frame: FrameType | None) -> None:
        del frame
        logger.info(
            "worker_shutdown_requested",
            extra={"event": "worker_shutdown_requested", "signal": signum},
        )
        shutdown_event.set()

    if threading.current_thread() is not threading.main_thread():
        return previous
    for signame in ("SIGTERM", "SIGINT"):
        selected = getattr(signal, signame, None)
        if selected is None:
            continue
        previous[selected] = signal.getsignal(selected)
        signal.signal(selected, request_shutdown)
    return previous


def _restore_shutdown_handlers(previous: dict[signal.Signals, Any]) -> None:
    if threading.current_thread() is not threading.main_thread():
        return
    for selected, handler in previous.items():
        signal.signal(selected, handler)


def run_worker(
    settings: Settings,
    poll_interval_seconds: float = 1.0,
    *,
    shutdown_event: threading.Event | None = None,
) -> None:
    stop_event = shutdown_event or threading.Event()
    previous_handlers = _install_shutdown_handlers(stop_event)
    telemetry_scheduler: Any | None = None
    logger.info(
        "neraium_worker_starting",
        extra={
            "event": "neraium_worker_starting",
            "process_role": settings.process_role,
            "runtime_dir": str(settings.runtime_dir),
            "upload_state_backend": upload_state_backend(),
            "upload_state_shared_configured": shared_state_configured(),
        },
    )
    try:
        _configure_runtime_services(settings)
        init_runtime_db()
        telemetry_scheduler = _configure_worker_telemetry_scheduler(settings)
        if telemetry_scheduler is not None:
            _publish_telemetry_worker_health(status="starting", force=True)
        logger.info(
            "worker_runtime_initialized",
            extra={
                "event": "worker_runtime_initialized",
                "process_role": settings.process_role,
                "runtime_dir": str(settings.runtime_dir),
                "runtime_db_initialized": True,
                "upload_state_backend": upload_state_backend(),
            },
        )
        logger.info(
            "worker_loop_started",
            extra={
                "event": "worker_loop_started",
                "poll_interval_seconds": poll_interval_seconds,
            },
        )
        _publish_worker_health(status="healthy", force=True)
        while not stop_event.is_set():
            logger.debug(
                "worker_polling_queue",
                extra={
                    "event": "worker_polling_queue",
                    "process_role": settings.process_role,
                    "runtime_dir": str(settings.runtime_dir),
                },
            )
            try:
                processed = process_next_queued_upload_job()
                if processed:
                    logger.info(
                        "worker_poll_result",
                        extra={
                            "event": "worker_poll_result",
                            "processed": True,
                            "runtime_dir": str(settings.runtime_dir),
                        },
                    )
                _publish_worker_health(status="healthy", processed_job=bool(processed))
                live_summary = run_due_live_analysis_jobs()
                if live_summary["attempted_systems"]:
                    logger.info(
                        "worker_live_analysis_result",
                        extra={
                            "event": "worker_live_analysis_result",
                            "attempted_systems": live_summary["attempted_systems"],
                            "completed": live_summary["completed"],
                            "skipped": live_summary["skipped"],
                            "failed": live_summary["failed"],
                        },
                    )

                if telemetry_scheduler is not None:
                    try:
                        telemetry_result = telemetry_scheduler.run_once()
                        if getattr(telemetry_result, "outcome", None) != "idle":
                            logger.info(
                                "worker_telemetry_result",
                                extra={
                                    "event": "worker_telemetry_result",
                                    "outcome": getattr(
                                        telemetry_result, "outcome", None
                                    ),
                                    "connection_id": getattr(
                                        telemetry_result, "connection_id", None
                                    ),
                                    "run_id": getattr(
                                        telemetry_result, "run_id", None
                                    ),
                                    "error_code": getattr(
                                        telemetry_result, "error_code", None
                                    ),
                                },
                            )
                    except Exception as error:
                        logger.error(
                            "telemetry_scheduler_iteration_failed",
                            extra={
                                "event": "telemetry_scheduler_iteration_failed",
                                "error_type": type(error).__name__,
                            },
                        )
                        _publish_telemetry_worker_health(
                            status="degraded",
                            error_code="telemetry_scheduler_iteration_failed",
                            force=True,
                        )

                if not processed:
                    logger.debug(
                        "worker_poll_result",
                        extra={
                            "event": "worker_poll_result",
                            "processed": False,
                            "runtime_dir": str(settings.runtime_dir),
                        },
                    )
            except KeyboardInterrupt:
                stop_event.set()
            except Exception as error:
                logger.exception(
                    "upload_worker_iteration_failed",
                    extra={
                        "event": "upload_worker_iteration_failed",
                        "runtime_dir": str(settings.runtime_dir),
                    },
                )
                _publish_worker_health(status="degraded", error_type=type(error).__name__, force=True)
            stop_event.wait(max(float(poll_interval_seconds), 0.01))
    finally:
        if telemetry_scheduler is not None:
            try:
                if not telemetry_scheduler.stop(
                    timeout_seconds=float(
                        getattr(settings, "shutdown_timeout_seconds", 30.0)
                    )
                ):
                    logger.error(
                        "telemetry_worker_shutdown_timeout",
                        extra={"event": "telemetry_worker_shutdown_timeout"},
                    )
            except Exception as error:
                logger.error(
                    "telemetry_worker_shutdown_failed",
                    extra={
                        "event": "telemetry_worker_shutdown_failed",
                        "error_type": type(error).__name__,
                    },
                )
            _publish_telemetry_worker_health(status="stopped", force=True)
        _publish_worker_health(status="stopped", force=True)
        _restore_shutdown_handlers(previous_handlers)
        logger.info("worker_loop_stopped", extra={"event": "worker_loop_stopped"})


def main() -> None:
    _configure_logging()
    try:
        settings = get_settings()
        validate_environment_completeness(settings)
    except Exception:
        logger.exception("configuration_validation_failed", extra={"event": "configuration_validation_failed"})
        raise SystemExit(1) from None

    _configure_logging(settings)
    role = _normalize_startup_role(settings.process_role)
    try:
        if role == "worker":
            run_worker(settings)
            return
        # "all" preserves dev/local monolith behavior by running FastAPI app, which
        # starts background workers via lifespan according to settings.
        run_api(settings)
    except Exception:
        logger.exception(
            "neraium_process_startup_failed",
            extra={"event": "neraium_process_startup_failed", "process_role": role},
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
