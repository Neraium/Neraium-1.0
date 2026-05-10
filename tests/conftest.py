import pytest
import time

from app.services.sii_runner import STATE_PATH
from app.services.evidence_store import evidence_runs_path
from app.services.upload_jobs import JOB_DIR, UPLOAD_DIR, latest_upload_history_path, latest_upload_path, latest_upload_result_path


@pytest.fixture(autouse=True)
def clear_runtime_state():
    cleanup_runtime_state()
    yield
    cleanup_runtime_state()


def cleanup_runtime_state() -> None:
    remove_path_if_present(STATE_PATH)
    remove_path_if_present(latest_upload_path())
    remove_path_if_present(latest_upload_result_path())
    remove_path_if_present(latest_upload_history_path())
    remove_path_if_present(evidence_runs_path())
    for directory in (JOB_DIR, UPLOAD_DIR):
        if directory.exists():
            for path in directory.glob("*"):
                if path.is_file():
                    remove_path_if_present(path)


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
