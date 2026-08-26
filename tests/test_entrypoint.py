import logging
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.entrypoint import _normalize_startup_role, main, run_worker


def test_normalize_startup_role() -> None:
    assert _normalize_startup_role("api") == "api"
    assert _normalize_startup_role("worker") == "worker"
    assert _normalize_startup_role("all") == "all"
    assert _normalize_startup_role("monolith") == "all"
    assert _normalize_startup_role("unknown") == "all"


def test_main_dispatches_to_worker(monkeypatch) -> None:
    class Settings:
        process_role = "worker"

    calls: list[str] = []

    monkeypatch.setattr("app.entrypoint.get_settings", lambda: Settings())
    monkeypatch.setattr("app.entrypoint.run_worker", lambda settings: calls.append("worker"))
    monkeypatch.setattr("app.entrypoint.run_api", lambda settings: calls.append("api"))

    main()

    assert calls == ["worker"]


def test_main_dispatches_to_api_for_monolith(monkeypatch) -> None:
    class Settings:
        process_role = "monolith"

    calls: list[str] = []

    monkeypatch.setattr("app.entrypoint.get_settings", lambda: Settings())
    monkeypatch.setattr("app.entrypoint.run_worker", lambda settings: calls.append("worker"))
    monkeypatch.setattr("app.entrypoint.run_api", lambda settings: calls.append("api"))

    main()

    assert calls == ["api"]


def test_run_worker_logs_startup_and_polls_queue_without_uvicorn(monkeypatch, caplog, tmp_path) -> None:
    class Settings:
        process_role = "worker"
        runtime_dir = Path(tmp_path)

    calls: list[str] = []

    monkeypatch.setattr("app.entrypoint.configure_runtime_db_dir", lambda runtime_dir: calls.append(f"runtime_db:{runtime_dir}"))
    monkeypatch.setattr("app.entrypoint.configure_upload_jobs_dir", lambda runtime_dir: calls.append(f"upload_jobs:{runtime_dir}"))
    monkeypatch.setattr("app.entrypoint.configure_sii_runner_dir", lambda runtime_dir: calls.append(f"sii_runner:{runtime_dir}"))
    monkeypatch.setattr("app.entrypoint.init_runtime_db", lambda: calls.append("init_runtime_db"))
    monkeypatch.setattr("app.entrypoint.upload_state_backend", lambda: "runtime_db")
    monkeypatch.setattr("app.entrypoint.shared_state_configured", lambda: False)
    monkeypatch.setattr("app.entrypoint.uvicorn.run", lambda *args, **kwargs: calls.append("uvicorn"))

    def fake_process_next() -> bool:
        calls.append("process_next")
        raise KeyboardInterrupt()

    monkeypatch.setattr("app.entrypoint.process_next_queued_upload_job", fake_process_next)
    monkeypatch.setattr("app.entrypoint.time.sleep", lambda _: calls.append("sleep"))

    with caplog.at_level(logging.INFO):
        try:
            run_worker(Settings(), poll_interval_seconds=0.01)
        except KeyboardInterrupt:
            pass

    assert any(item.startswith("runtime_db:") for item in calls)
    assert any(item.startswith("upload_jobs:") for item in calls)
    assert any(item.startswith("sii_runner:") for item in calls)
    assert "init_runtime_db" in calls
    assert "process_next" in calls
    assert "uvicorn" not in calls
    assert "neraium_worker_starting" in caplog.text
    assert "worker_runtime_initialized" in caplog.text
    assert "worker_loop_started" in caplog.text
    assert "worker_loop_stopped" in caplog.text
    assert "worker_polling_queue" not in caplog.text


def test_run_worker_polls_due_live_analyses_independently(monkeypatch, tmp_path) -> None:
    class Settings:
        process_role = "worker"
        runtime_dir = Path(tmp_path)

    stop_event = threading.Event()
    calls: list[str] = []

    monkeypatch.setattr("app.entrypoint.configure_runtime_db_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.configure_upload_jobs_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.configure_sii_runner_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.init_runtime_db", lambda: None)
    monkeypatch.setattr("app.entrypoint.upload_state_backend", lambda: "runtime_db")
    monkeypatch.setattr("app.entrypoint.shared_state_configured", lambda: False)
    monkeypatch.setattr("app.entrypoint._publish_worker_health", lambda **kwargs: None)
    monkeypatch.setattr(
        "app.entrypoint.process_next_queued_upload_job",
        lambda: calls.append("upload") or False,
    )

    def run_live() -> dict[str, int]:
        calls.append("live")
        stop_event.set()
        return {"attempted_systems": 1, "completed": 1, "skipped": 0, "failed": 0}

    monkeypatch.setattr("app.entrypoint.run_due_live_analysis_jobs", run_live)
    run_worker(Settings(), poll_interval_seconds=0.01, shutdown_event=stop_event)

    assert calls == ["upload", "live"]


def test_dedicated_worker_runs_configured_telemetry_scheduler_without_nested_loop(
    monkeypatch, tmp_path
) -> None:
    class Settings:
        process_role = "worker"
        runtime_dir = Path(tmp_path)
        telemetry_database_url = "postgresql://configured"
        shutdown_timeout_seconds = 0.25

    stop_event = threading.Event()
    calls: list[object] = []

    class Scheduler:
        def start(self):
            calls.append("telemetry_start")
            raise AssertionError("dedicated worker must not start a nested scheduler loop")

        def run_once(self):
            calls.append("telemetry_run_once")
            stop_event.set()
            return SimpleNamespace(
                outcome="processed",
                connection_id="connection-a",
                run_id="run-a",
                error_code=None,
            )

        def stop(self, *, timeout_seconds):
            calls.append(("telemetry_stop", timeout_seconds))
            return True

    class Runtime:
        available = True
        scheduler = Scheduler()

        def verify_readiness(self):
            calls.append("telemetry_readiness")
            return True

    monkeypatch.setattr("app.entrypoint.configure_runtime_db_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.configure_upload_jobs_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.configure_sii_runner_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.init_runtime_db", lambda: None)
    monkeypatch.setattr("app.entrypoint.upload_state_backend", lambda: "runtime_db")
    monkeypatch.setattr("app.entrypoint.shared_state_configured", lambda: False)
    monkeypatch.setattr("app.entrypoint._publish_worker_health", lambda **kwargs: None)
    monkeypatch.setattr(
        "app.entrypoint._publish_telemetry_worker_health",
        lambda **kwargs: calls.append(("telemetry_heartbeat", kwargs["status"])),
    )
    monkeypatch.setattr("app.entrypoint.build_worker_telemetry_runtime", lambda settings: Runtime())
    monkeypatch.setattr(
        "app.entrypoint.process_next_queued_upload_job",
        lambda: calls.append("upload") or False,
    )
    monkeypatch.setattr(
        "app.entrypoint.run_due_live_analysis_jobs",
        lambda: calls.append("live")
        or {"attempted_systems": 0, "completed": 0, "skipped": 0, "failed": 0},
    )

    run_worker(Settings(), poll_interval_seconds=0.01, shutdown_event=stop_event)

    assert calls == [
        "telemetry_readiness",
        ("telemetry_heartbeat", "starting"),
        "upload",
        "live",
        "telemetry_run_once",
        ("telemetry_stop", 0.25),
        ("telemetry_heartbeat", "stopped"),
    ]


def test_dedicated_worker_fails_closed_when_configured_runtime_is_unavailable(
    monkeypatch, tmp_path
) -> None:
    class Settings:
        process_role = "worker"
        runtime_dir = Path(tmp_path)
        telemetry_database_url = "postgresql://configured"

    calls: list[str] = []
    runtime = SimpleNamespace(
        available=False,
        unavailable_code="telemetry_runtime_configuration_invalid",
    )

    monkeypatch.setattr("app.entrypoint.configure_runtime_db_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.configure_upload_jobs_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.configure_sii_runner_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.init_runtime_db", lambda: None)
    monkeypatch.setattr("app.entrypoint.upload_state_backend", lambda: "runtime_db")
    monkeypatch.setattr("app.entrypoint.shared_state_configured", lambda: False)
    monkeypatch.setattr("app.entrypoint._publish_worker_health", lambda **kwargs: None)
    monkeypatch.setattr(
        "app.entrypoint._publish_telemetry_worker_health", lambda **kwargs: None
    )
    monkeypatch.setattr("app.entrypoint.build_worker_telemetry_runtime", lambda settings: runtime)
    monkeypatch.setattr(
        "app.entrypoint.process_next_queued_upload_job",
        lambda: calls.append("upload") or False,
    )

    with pytest.raises(RuntimeError, match="Configured telemetry runtime is unavailable"):
        run_worker(Settings(), poll_interval_seconds=0.01)

    assert calls == []


def test_dedicated_worker_fails_closed_when_configured_schema_is_not_ready(
    monkeypatch, tmp_path
) -> None:
    class Settings:
        process_role = "worker"
        runtime_dir = Path(tmp_path)
        telemetry_database_url = "postgresql://configured"

    calls: list[str] = []

    class Runtime:
        available = True
        scheduler = SimpleNamespace(run_once=lambda: None)

        def verify_readiness(self):
            raise OSError("database details must not escape")

    monkeypatch.setattr("app.entrypoint.configure_runtime_db_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.configure_upload_jobs_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.configure_sii_runner_dir", lambda runtime_dir: None)
    monkeypatch.setattr("app.entrypoint.init_runtime_db", lambda: None)
    monkeypatch.setattr("app.entrypoint.upload_state_backend", lambda: "runtime_db")
    monkeypatch.setattr("app.entrypoint.shared_state_configured", lambda: False)
    monkeypatch.setattr("app.entrypoint._publish_worker_health", lambda **kwargs: None)
    monkeypatch.setattr(
        "app.entrypoint._publish_telemetry_worker_health", lambda **kwargs: None
    )
    monkeypatch.setattr("app.entrypoint.build_worker_telemetry_runtime", lambda settings: Runtime())
    monkeypatch.setattr(
        "app.entrypoint.process_next_queued_upload_job",
        lambda: calls.append("upload") or False,
    )

    with pytest.raises(RuntimeError, match="Configured telemetry runtime is not ready"):
        run_worker(Settings(), poll_interval_seconds=0.01)

    assert calls == []
