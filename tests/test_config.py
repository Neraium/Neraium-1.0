from app.core.config import (
    DEFAULT_CORS_ORIGIN_REGEX,
    DEFAULT_CORS_ORIGINS,
    get_settings,
    parse_cors_origin_regex,
    parse_cors_origins,
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
        "http://127.0.0.1:3010",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://localhost:3010",
        "http://localhost:5173",
        "https://app.neraium.com",
        "https://www.app.neraium.com",
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
