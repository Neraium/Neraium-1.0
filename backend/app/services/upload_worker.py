from __future__ import annotations

import logging
import threading
import time

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
    _stop_event.set()


def _worker_loop(poll_interval_seconds: float) -> None:
    while not _stop_event.is_set():
        try:
            process_next_queued_upload_job()
        except Exception:
            logger.exception("upload_worker_iteration_failed")
        _stop_event.wait(poll_interval_seconds)
