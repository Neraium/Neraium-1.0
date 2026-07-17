import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services import evidence_store, rate_limiter, upload_worker
from app.services.upload_jobs import configure_runtime_dir as configure_upload_runtime_dir
from app.services.upload_runtime_state import UploadRuntimeState


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "app_env": "development",
        "backend_host": "127.0.0.1",
        "backend_port": 8010,
        "cors_origins": ["http://127.0.0.1:3010"],
        "runtime_dir": tmp_path,
        "start_background_workers": False,
        "start_data_connection_poller": False,
        "shutdown_timeout_seconds": 0.01,
    }
    values.update(overrides)
    return Settings(**values)


def test_shared_state_warning_only_applies_to_split_production_roles(
    monkeypatch, tmp_path, caplog
) -> None:
    monkeypatch.delenv("NERAIUM_UPLOAD_STATE_BUCKET", raising=False)

    with caplog.at_level(logging.WARNING):
        with TestClient(create_app(_settings(tmp_path / "all", app_env="prod", process_role="all"))):
            pass
    assert "upload_state_shared_storage_not_configured" not in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        with TestClient(create_app(_settings(tmp_path / "api", app_env="prod", process_role="api"))):
            pass
    assert "upload_state_shared_storage_not_configured" in caplog.text


def test_production_smoke_requires_explicit_target() -> None:
    import os
    import shutil
    import subprocess

    node = shutil.which("node") or shutil.which("node.exe")
    if node is None:
        pytest.skip("Node.js is not installed")
    environment = os.environ.copy()
    environment.pop("BASE_URL", None)
    environment.pop("API_BASE_URL", None)
    repository_root = Path(__file__).resolve().parents[1]

    completed = subprocess.run(
        [node, str(repository_root / "scripts" / "smoke-production.js")],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 2
    assert "Smoke target is required" in completed.stderr
    assert "Neraium production smoke test" not in completed.stdout

def test_required_runtime_database_failure_aborts_startup(monkeypatch, tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    monkeypatch.setattr(
        "app.main.init_runtime_db",
        lambda: (_ for _ in ()).throw(RuntimeError("password=do-not-leak")),
    )

    with pytest.raises(RuntimeError, match="Required runtime database initialization failed"):
        with TestClient(app):
            pass


def test_required_auth_database_failure_aborts_startup(monkeypatch, tmp_path) -> None:
    app = create_app(_settings(tmp_path))
    monkeypatch.setattr(
        "app.main.initialize_auth_store",
        lambda: (_ for _ in ()).throw(RuntimeError("postgres unavailable")),
    )

    with pytest.raises(RuntimeError, match="Required authentication database initialization failed"):
        with TestClient(app):
            pass


def test_configured_worker_failure_aborts_startup(monkeypatch, tmp_path) -> None:
    app = create_app(_settings(tmp_path, start_background_workers=True))
    monkeypatch.setattr(
        "app.main.start_upload_worker",
        lambda: (_ for _ in ()).throw(RuntimeError("worker unavailable")),
    )

    with pytest.raises(RuntimeError, match="Upload worker startup failed"):
        with TestClient(app):
            pass


def test_upload_worker_shutdown_reports_live_thread_timeout(monkeypatch, caplog) -> None:
    class StuckThread:
        name = "stuck-upload-worker"

        def is_alive(self) -> bool:
            return True

        def join(self, timeout: float) -> None:
            assert timeout == 0.01

    monkeypatch.setattr(upload_worker, "_worker_thread", StuckThread())

    with caplog.at_level(logging.ERROR):
        stopped = upload_worker.stop_upload_worker(timeout_seconds=0.01)

    assert stopped is False
    assert upload_worker._worker_thread is not None
    assert "upload_worker_shutdown_timeout" in caplog.text


def test_rate_limit_buckets_are_swept_after_expiration(monkeypatch) -> None:
    rate_limiter.clear_rate_limits()
    now = [0.0]
    monkeypatch.setattr(rate_limiter.time, "monotonic", lambda: now[0])
    for index in range(300):
        rate_limiter.consume_rate_limit("upload", str(index), limit=1, window_seconds=10)

    assert rate_limiter.rate_limit_bucket_count() == 300

    now[0] = 100.0
    for index in range(256):
        rate_limiter.consume_rate_limit("upload", f"new-{index}", limit=1, window_seconds=10)

    assert rate_limiter.rate_limit_bucket_count() <= 256
    rate_limiter.clear_rate_limits()


def test_upload_runtime_cache_has_a_fixed_bound() -> None:
    state = UploadRuntimeState(max_cached_jobs=3)

    for index in range(5):
        state.cache_job(str(index), {"job_id": str(index)})

    assert list(state.jobs) == ["2", "3", "4"]



def test_runtime_dependency_failure_marks_readiness_not_ready(monkeypatch, tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        monkeypatch.setattr("app.routers.health._runtime_db_available", lambda: False)
        response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["runtime_db"] == "error"


def test_lifespan_stops_every_started_background_service(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    monkeypatch.setattr("app.main.start_upload_worker", lambda: calls.append("worker_started"))
    monkeypatch.setattr(
        "app.main.stop_upload_worker",
        lambda timeout_seconds: calls.append(f"worker_stopped:{timeout_seconds}") or True,
    )
    monkeypatch.setattr("app.main.start_data_connection_poller", lambda: calls.append("poller_started"))
    monkeypatch.setattr(
        "app.main.stop_data_connection_poller",
        lambda timeout_seconds: calls.append(f"poller_stopped:{timeout_seconds}") or True,
    )

    settings = _settings(
        tmp_path,
        start_background_workers=True,
        start_data_connection_poller=True,
        shutdown_timeout_seconds=0.25,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/ready").status_code == 200

    assert calls == [
        "worker_started",
        "poller_started",
        "poller_stopped:0.25",
        "worker_stopped:0.25",
    ]


def test_evidence_mirror_follows_reconfigured_runtime_boundary(tmp_path) -> None:
    first_runtime = tmp_path / "first-runtime"
    second_runtime = tmp_path / "second-runtime"

    configure_upload_runtime_dir(first_runtime)
    evidence_store.upsert_evidence_run(
        {
            "run_id": "first-runtime-run",
            "status": "completed",
            "created_at": "2026-07-16T00:00:00Z",
            "completed_at": "2026-07-16T00:01:00Z",
            "source_name": "first.csv",
        }
    )
    assert (first_runtime / "evidence" / "runs.json").exists()

    configure_upload_runtime_dir(second_runtime)
    evidence_store.upsert_evidence_run(
        {
            "run_id": "second-runtime-run",
            "status": "completed",
            "created_at": "2026-07-16T01:00:00Z",
            "completed_at": "2026-07-16T01:01:00Z",
            "source_name": "second.csv",
        }
    )

    assert evidence_store.EVIDENCE_RUNS_PATH == second_runtime / "evidence" / "runs.json"
    assert evidence_store.read_evidence_run("second-runtime-run") is not None
    assert evidence_store.read_evidence_run("first-runtime-run") is None
