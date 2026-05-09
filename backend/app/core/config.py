import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_APP_ENV = "development"
DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8010
DEFAULT_CORS_ORIGINS = [
    "http://127.0.0.1:3010",
    "http://localhost:3010",
    "https://app.neraium.com",
]
DEFAULT_DEV_ACCESS_CODE = "neraium-dev"
DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"


@dataclass(frozen=True)
class Settings:
    app_env: str
    backend_host: str
    backend_port: int
    cors_origins: list[str]
    app_access_code: str
    runtime_dir: Path


def get_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", DEFAULT_APP_ENV),
        backend_host=os.getenv("BACKEND_HOST", DEFAULT_BACKEND_HOST),
        backend_port=parse_port(os.getenv("BACKEND_PORT"), DEFAULT_BACKEND_PORT),
        cors_origins=parse_cors_origins(os.getenv("CORS_ORIGINS")),
        app_access_code=parse_access_code(os.getenv("NERAIUM_API_ACCESS_CODE"), os.getenv("APP_ENV", DEFAULT_APP_ENV)),
        runtime_dir=parse_runtime_dir(os.getenv("NERAIUM_RUNTIME_DIR")),
    )


def parse_port(raw_value: str | None, default: int) -> int:
    if raw_value is None or raw_value.strip() == "":
        return default
    return int(raw_value)


def parse_cors_origins(raw_value: str | None) -> list[str]:
    if raw_value is None or raw_value.strip() == "":
        return DEFAULT_CORS_ORIGINS.copy()
    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    for required_origin in DEFAULT_CORS_ORIGINS:
        if required_origin not in origins:
            origins.append(required_origin)
    return origins


def parse_access_code(raw_value: str | None, app_env: str) -> str:
    if raw_value and raw_value.strip():
        return raw_value.strip()
    if app_env == "production":
        raise RuntimeError("NERAIUM_API_ACCESS_CODE must be configured in production.")
    return DEFAULT_DEV_ACCESS_CODE


def parse_runtime_dir(raw_value: str | None) -> Path:
    if raw_value and raw_value.strip():
        return Path(raw_value.strip()).expanduser()
    return DEFAULT_RUNTIME_DIR
