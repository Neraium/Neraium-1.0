from __future__ import annotations

import logging
import threading
import time

from app.services.data_connections import is_connection_due, list_registered_data_connections, poll_data_connection_once


logger = logging.getLogger(__name__)
_stop_event = threading.Event()
_poller_thread: threading.Thread | None = None
_poll_lock = threading.Lock()


def start_data_connection_poller(poll_interval_seconds: float = 1.0) -> None:
    global _poller_thread
    if _poller_thread is not None and _poller_thread.is_alive():
        return
    _stop_event.clear()
    _poller_thread = threading.Thread(
        target=_poller_loop,
        args=(poll_interval_seconds,),
        daemon=True,
        name="neraium-data-connection-poller",
    )
    _poller_thread.start()
    logger.info("data_connection_poller_started poll_interval_seconds=%s", poll_interval_seconds)


def stop_data_connection_poller(timeout_seconds: float = 30.0) -> bool:
    global _poller_thread
    _stop_event.set()
    thread = _poller_thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=max(float(timeout_seconds), 0.0))
    stopped = thread is None or not thread.is_alive()
    if stopped:
        _poller_thread = None
        logger.info(
            "data_connection_poller_stopped",
            extra={"event": "data_connection_poller_stopped"},
        )
    else:
        logger.error(
            "data_connection_poller_shutdown_timeout",
            extra={
                "event": "data_connection_poller_shutdown_timeout",
                "timeout_seconds": timeout_seconds,
                "thread_name": thread.name,
            },
        )
    return stopped


def run_due_data_connection_polls() -> None:
    with _poll_lock:
        for connection in list_registered_data_connections():
            if is_connection_due(connection):
                poll_data_connection_once(connection["connection_id"])


def _poller_loop(poll_interval_seconds: float) -> None:
    while not _stop_event.is_set():
        try:
            run_due_data_connection_polls()
        except Exception:
            logger.exception("data_connection_poller_iteration_failed")
        _stop_event.wait(poll_interval_seconds)
