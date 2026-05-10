import pytest
import time
from pathlib import Path

from app.services.data_connection_poller import stop_data_connection_poller
from app.services.runtime_db import db_connection, init_runtime_db
from app.services.upload_worker import stop_upload_worker
from app.services import evidence_store, runtime_db, sii_runner, upload_jobs


@pytest.fixture(autouse=True)
def clear_runtime_state(monkeypatch, tmp_path):
    apply_test_runtime(tmp_path, monkeypatch)
    cleanup_runtime_state()
    yield
    cleanup_runtime_state()


def apply_test_runtime(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setattr(runtime_db, "RUNTIME_DIR", runtime_root)
    monkeypatch.setattr(runtime_db, "DB_PATH", runtime_root / "runtime.db")

    monkeypatch.setattr(upload_jobs, "RUNTIME_DIR", runtime_root)
    monkeypatch.setattr(upload_jobs, "UPLOAD_DIR", runtime_root / "uploads")
    monkeypatch.setattr(upload_jobs, "JOB_DIR", runtime_root / "upload_jobs")
    monkeypatch.setattr(upload_jobs, "LEGACY_JOB_DIR", runtime_root / "jobs")

    monkeypatch.setattr(evidence_store, "RUNTIME_DIR", runtime_root)
    monkeypatch.setattr(evidence_store, "EVIDENCE_DIR", runtime_root / "evidence")
    monkeypatch.setattr(evidence_store, "EVIDENCE_RUNS_PATH", runtime_root / "evidence" / "runs.json")

    monkeypatch.setattr(sii_runner, "STATE_PATH", runtime_root / "latest_sii_state.json")


def cleanup_runtime_state() -> None:
    stop_data_connection_poller()
    stop_upload_worker()
    remove_path_if_present(sii_runner.STATE_PATH)
    remove_path_if_present(upload_jobs.latest_upload_path())
    remove_path_if_present(upload_jobs.latest_upload_result_path())
    remove_path_if_present(upload_jobs.latest_upload_history_path())
    remove_path_if_present(evidence_store.evidence_runs_path())
    clear_runtime_db()
    for directory in (upload_jobs.JOB_DIR, upload_jobs.UPLOAD_DIR):
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
                    DELETE FROM data_connections;
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
