import os
from dataclasses import dataclass

DEFAULT_APP_ENV = "development"
DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8010
DEFAULT_CORS_ORIGINS = [
    "http://127.0.0.1:3010",
    "http://localhost:3010",
]


@dataclass(frozen=True)
class Settings:
    app_env: str
    backend_host: str
    backend_port: int
    cors_origins: list[str]


def get_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", DEFAULT_APP_ENV),
        backend_host=os.getenv("BACKEND_HOST", DEFAULT_BACKEND_HOST),
        backend_port=parse_port(os.getenv("BACKEND_PORT"), DEFAULT_BACKEND_PORT),
        cors_origins=parse_cors_origins(os.getenv("CORS_ORIGINS")),
    )


def parse_port(raw_value: str | None, default: int) -> int:
    if raw_value is None or raw_value.strip() == "":
        return default
    return int(raw_value)


def parse_cors_origins(raw_value: str | None) -> list[str]:
    if raw_value is None or raw_value.strip() == "":
        return DEFAULT_CORS_ORIGINS.copy()
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]
