import logging
from pathlib import Path

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
