from __future__ import annotations

import logging
import time

import uvicorn

from app.core.config import Settings, get_settings
from app.services.runtime_db import configure_runtime_dir as configure_runtime_db_dir, init_runtime_db
from app.services.sii_runner import configure_runtime_dir as configure_sii_runner_dir
from app.services.upload_jobs import configure_runtime_dir as configure_upload_jobs_dir, process_next_queued_upload_job

logger = logging.getLogger(__name__)


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


def run_api(settings: Settings) -> None:
    logger.info("neraium_startup_role=api host=%s port=%s", settings.backend_host, settings.backend_port)
    uvicorn.run("app.main:app", host=settings.backend_host, port=settings.backend_port)


def run_worker(settings: Settings, poll_interval_seconds: float = 1.0) -> None:
    logger.info("neraium_startup_role=worker")
    _configure_runtime_services(settings)
    init_runtime_db()
    logger.info("worker_loop_started poll_interval_seconds=%s", poll_interval_seconds)
    while True:
        logger.info("worker_polling_queue")
        try:
            process_next_queued_upload_job()
        except Exception:
            logger.exception("upload_worker_iteration_failed")
        time.sleep(poll_interval_seconds)


def main() -> None:
    settings = get_settings()
    role = _normalize_startup_role(settings.process_role)
    if role == "worker":
        run_worker(settings)
        return
    # "all" preserves dev/local monolith behavior by running FastAPI app, which
    # starts background workers via lifespan according to settings.
    run_api(settings)


if __name__ == "__main__":
    main()
