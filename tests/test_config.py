from app.core.config import (
    DEFAULT_CORS_ORIGIN_REGEX,
    DEFAULT_CORS_ORIGINS,
    DEFAULT_RUNTIME_DIR,
    get_settings,
    parse_cors_origin_regex,
    parse_cors_origins,
    parse_process_role,
)


def test_settings_use_local_defaults(monkeypatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("BACKEND_HOST", raising=False)
    monkeypatch.delenv("BACKEND_PORT", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    monkeypatch.delenv("NERAIUM_RUNTIME_DIR", raising=False)

    settings = get_settings()

    assert settings.app_env == "development"
    assert settings.backend_host == "127.0.0.1"
    assert settings.backend_port == 8010
    assert settings.cors_origins == DEFAULT_CORS_ORIGINS
    assert settings.cors_origin_regex == DEFAULT_CORS_ORIGIN_REGEX
    assert settings.default_telemetry_url == ""
    assert settings.start_data_connection_poller is False


def test_settings_read_environment_values(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("BACKEND_HOST", "0.0.0.0")
    monkeypatch.setenv("BACKEND_PORT", "8080")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com, https://admin.example.com")
    monkeypatch.setenv("CORS_ORIGIN_REGEX", "^https://([a-z0-9-]+\\.)?example\\.com$")

    settings = get_settings()

    assert settings.app_env == "production"
    assert settings.backend_host == "0.0.0.0"
    assert settings.backend_port == 8080
    assert settings.cors_origin_regex == "^https://([a-z0-9-]+\\.)?example\\.com$"
    assert settings.default_telemetry_url == ""
    assert settings.start_data_connection_poller is False
    assert settings.cors_origins == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_parse_cors_origins_ignores_empty_values() -> None:
    assert parse_cors_origins("https://app.example.com, ,https://ops.example.com") == [
        "https://app.example.com",
        "https://ops.example.com",
        "http://127.0.0.1:3010",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:3010",
        "http://localhost:5173",
        "https://app.neraium.com",
        "https://www.app.neraium.com",
    ]


def test_parse_cors_origins_does_not_add_local_defaults_in_production() -> None:
    assert parse_cors_origins("https://app.example.com", app_env="production") == ["https://app.example.com"]


def test_default_cors_origins_include_local_and_production_frontends() -> None:
    assert DEFAULT_CORS_ORIGINS == [
        "http://127.0.0.1:3010",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:3010",
        "http://localhost:5173",
        "https://app.neraium.com",
        "https://www.app.neraium.com",
    ]


def test_parse_cors_origin_regex_uses_default_when_not_set() -> None:
    assert parse_cors_origin_regex(None) == DEFAULT_CORS_ORIGIN_REGEX
    assert parse_cors_origin_regex("") == DEFAULT_CORS_ORIGIN_REGEX


def test_parse_process_role_accepts_monolith_alias() -> None:
    assert parse_process_role("monolith") == "monolith"
    assert parse_process_role("worker") == "worker"
    assert parse_process_role("invalid") == "all"


def test_production_settings_require_explicit_runtime_dir(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("NERAIUM_RUNTIME_DIR", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    try:
        get_settings()
    except ValueError as error:
        assert str(error) == "NERAIUM_RUNTIME_DIR must be set explicitly in production."
    else:
        raise AssertionError("Expected production config validation to fail without NERAIUM_RUNTIME_DIR.")


def test_production_settings_accept_explicit_runtime_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))

    settings = get_settings()

    assert settings.runtime_dir == tmp_path
    assert settings.runtime_dir != DEFAULT_RUNTIME_DIR
