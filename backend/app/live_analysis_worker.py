from __future__ import annotations

import argparse
import logging
import signal
import threading
from types import FrameType
from typing import Any

from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.services.live_analysis import run_due_live_analyses
from app.services.runtime_db import configure_runtime_dir, init_runtime_db


logger = logging.getLogger(__name__)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Neraium live-analysis orchestration.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one due-analysis iteration and exit.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=5.0,
        help="Worker poll interval when running continuously.",
    )
    return parser.parse_args()


def _install_shutdown(stop_event: threading.Event) -> dict[signal.Signals, Any]:
    previous: dict[signal.Signals, Any] = {}

    def request_shutdown(signum: int, frame: FrameType | None) -> None:
        del frame
        logger.info(
            "live_analysis_worker_shutdown_requested",
            extra={"event": "live_analysis_worker_shutdown_requested", "signal": signum},
        )
        stop_event.set()

    for name in ("SIGTERM", "SIGINT"):
        selected = getattr(signal, name, None)
        if selected is None:
            continue
        previous[selected] = signal.getsignal(selected)
        signal.signal(selected, request_shutdown)
    return previous


def main() -> None:
    args = _arguments()
    settings = get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    configure_runtime_dir(settings.runtime_dir)
    init_runtime_db()

    if args.once:
        run_due_live_analyses()
        return

    stop_event = threading.Event()
    previous = _install_shutdown(stop_event)
    try:
        while not stop_event.is_set():
            run_due_live_analyses()
            stop_event.wait(max(0.1, float(args.poll_interval_seconds)))
    finally:
        for selected, handler in previous.items():
            signal.signal(selected, handler)
        logger.info(
            "live_analysis_worker_stopped",
            extra={"event": "live_analysis_worker_stopped"},
        )


if __name__ == "__main__":
    main()
