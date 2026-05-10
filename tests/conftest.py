import pytest
import time

from app.services.sii_runner import STATE_PATH
from app.services.evidence_store import evidence_runs_path
from app.services.runtime_db import db_connection, init_runtime_db
from app.services.upload_jobs import JOB_DIR, UPLOAD_DIR, latest_upload_history_path, latest_upload_path, latest_upload_result_path
from app.services.upload_worker import stop_upload_worker


@pytest.fixture(autouse=True)
def clear_runtime_state():
    cleanup_runtime_state()
    yield
    cleanup_runtime_state()


def cleanup_runtime_state() -> None:
    stop_upload_worker()
    remove_path_if_present(STATE_PATH)
    remove_path_if_present(latest_upload_path())
    remove_path_if_present(latest_upload_result_path())
    remove_path_if_present(latest_upload_history_path())
    remove_path_if_present(evidence_runs_path())
    clear_runtime_db()
    for directory in (JOB_DIR, UPLOAD_DIR):
        if directory.exists():
            for path in directory.glob("*"):
                if path.is_file():
                    remove_path_if_present(path)


def clear_runtime_db() -> None:
    init_runtime_db()
    last_error = None
    for attempt in range(10):
        try:
            with db_connection() as connection:
                connection.executescript(
                    """
                    DELETE FROM upload_jobs;
                    DELETE FROM upload_queue;
                    DELETE FROM evidence_runs;
                    DELETE FROM audit_events;
                    DELETE FROM latest_payloads;
                    """
                )
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.02 * (attempt + 1))
    if last_error is not None:
        raise last_error


def remove_path_if_present(path) -> None:
    if not path.exists():
        return
    last_error = None
    for attempt in range(10):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.02 * (attempt + 1))
    if last_error is not None:
        raise last_error
