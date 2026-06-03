from __future__ import annotations

import logging
import threading
import time

from app.services.runtime_db import upload_queue_backend
from app.services.upload_jobs import process_next_queued_upload_job


logger = logging.getLogger(__name__)
_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


def start_upload_worker(poll_interval_seconds: float = 1.0) -> None:
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(
        target=_worker_loop,
        args=(poll_interval_seconds,),
        daemon=True,
        name="neraium-upload-worker",
    )
    _worker_thread.start()
    logger.info("upload_worker_started poll_interval_seconds=%s", poll_interval_seconds)


def stop_upload_worker() -> None:
    global _worker_thread
    _stop_event.set()
    if _worker_thread is not None and _worker_thread.is_alive():
        _worker_thread.join(timeout=2.0)
    _worker_thread = None


def _worker_loop(poll_interval_seconds: float) -> None:
    while not _stop_event.is_set():
        logger.info("upload_worker_polling_queue queue_backend=%s", upload_queue_backend())
        try:
            processed = process_next_queued_upload_job()
            logger.info("upload_worker_poll_result processed=%s", processed)
        except Exception:
            logger.exception("upload_worker_iteration_failed")
        _stop_event.wait(poll_interval_seconds)
