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


def stop_upload_worker(timeout_seconds: float = 30.0) -> bool:
    global _worker_thread
    _stop_event.set()
    thread = _worker_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=max(float(timeout_seconds), 0.0))
    stopped = thread is None or not thread.is_alive()
    if stopped:
        _worker_thread = None
        logger.info("upload_worker_stopped", extra={"event": "upload_worker_stopped"})
    else:
        logger.error(
            "upload_worker_shutdown_timeout",
            extra={
                "event": "upload_worker_shutdown_timeout",
                "timeout_seconds": timeout_seconds,
                "thread_name": thread.name,
            },
        )
    return stopped


def _worker_loop(poll_interval_seconds: float) -> None:
    while not _stop_event.is_set():
        logger.debug("upload_worker_polling_queue queue_backend=%s", upload_queue_backend())
        try:
            processed = process_next_queued_upload_job()
            if processed:
                logger.info("upload_worker_poll_result processed=true")
            else:
                logger.debug("upload_worker_poll_result processed=false")
        except Exception:
            logger.exception("upload_worker_iteration_failed")
        _stop_event.wait(poll_interval_seconds)
