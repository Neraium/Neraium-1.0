import os
from dataclasses import dataclass
from pathlib import Path
from dataclasses import field

DEFAULT_APP_ENV = "development"
DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8010
DEFAULT_LOCAL_TELEMETRY_URL = "http://127.0.0.1:1880/telemetry/latest"
DEFAULT_PRODUCTION_TELEMETRY_URL = "http://18.216.253.180:1880/telemetry/latest"
DEFAULT_CORS_ORIGINS = [
    "http://127.0.0.1:3010",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://localhost:3010",
    "http://localhost:5173",
    "https://app.neraium.com",
    "https://www.app.neraium.com",
]
DEFAULT_CORS_ORIGIN_REGEX = r"^https://([a-z0-9-]+\.)?neraium\.com$"
DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"


@dataclass(frozen=True)
class Settings:
    app_env: str
    backend_host: str
    backend_port: int
    cors_origins: list[str]
    default_telemetry_url: str = DEFAULT_LOCAL_TELEMETRY_URL
    cors_origin_regex: str | None = None
    runtime_dir: Path = field(default_factory=lambda: DEFAULT_RUNTIME_DIR)


def get_settings() -> Settings:
    app_env = os.getenv("APP_ENV", DEFAULT_APP_ENV)
    return Settings(
        app_env=app_env,
        backend_host=os.getenv("BACKEND_HOST", DEFAULT_BACKEND_HOST),
        backend_port=parse_port(os.getenv("BACKEND_PORT"), DEFAULT_BACKEND_PORT),
        cors_origins=parse_cors_origins(os.getenv("CORS_ORIGINS")),
        default_telemetry_url=parse_default_telemetry_url(os.getenv("NERAIUM_DEFAULT_TELEMETRY_URL"), app_env),
        cors_origin_regex=parse_cors_origin_regex(os.getenv("CORS_ORIGIN_REGEX")),
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


def parse_cors_origin_regex(raw_value: str | None) -> str | None:
    if raw_value and raw_value.strip():
        return raw_value.strip()
    return DEFAULT_CORS_ORIGIN_REGEX


def parse_runtime_dir(raw_value: str | None) -> Path:
    if raw_value and raw_value.strip():
        return Path(raw_value.strip()).expanduser()
    return DEFAULT_RUNTIME_DIR


def parse_default_telemetry_url(raw_value: str | None, app_env: str) -> str:
    if raw_value and raw_value.strip():
        return raw_value.strip()
    if app_env.strip().lower() == "production":
        return DEFAULT_PRODUCTION_TELEMETRY_URL
    return DEFAULT_LOCAL_TELEMETRY_URL
