from app.entrypoint import _normalize_startup_role, main


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
