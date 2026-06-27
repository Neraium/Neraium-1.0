import os
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

DEFAULT_APP_ENV = "development"
DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8010
DEFAULT_TELEMETRY_URL = ""
DEFAULT_PROCESS_ROLE = "all"
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
# Allow larger historical telemetry uploads by default.
# Override with NERAIUM_MAX_UPLOAD_SIZE_BYTES in production when needed.
DEFAULT_MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024 * 1024
DEFAULT_MAX_PENDING_UPLOAD_JOBS = 50


@dataclass(frozen=True)
class Settings:
    app_env: str
    backend_host: str
    backend_port: int
    cors_origins: list[str]
    process_role: str = DEFAULT_PROCESS_ROLE
    start_background_workers: bool = False
    start_data_connection_poller: bool = False
    default_telemetry_url: str = DEFAULT_TELEMETRY_URL
    cors_origin_regex: str | None = None
    runtime_dir: Path = field(default_factory=lambda: DEFAULT_RUNTIME_DIR)
    max_upload_size_bytes: int = DEFAULT_MAX_UPLOAD_SIZE_BYTES
    max_pending_upload_jobs: int = DEFAULT_MAX_PENDING_UPLOAD_JOBS
    notification_webhook_url: str = ""
    notification_email_recipients: list[str] = field(default_factory=list)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_sender: str = ""
    smtp_use_tls: bool = True


def get_settings() -> Settings:
    app_env = os.getenv("APP_ENV", DEFAULT_APP_ENV)
    process_role = parse_process_role(os.getenv("NERAIUM_PROCESS_ROLE"))
    settings = Settings(
        app_env=app_env,
        backend_host=os.getenv("BACKEND_HOST", DEFAULT_BACKEND_HOST),
        backend_port=parse_port(os.getenv("BACKEND_PORT"), DEFAULT_BACKEND_PORT),
        cors_origins=parse_cors_origins(os.getenv("CORS_ORIGINS"), app_env=app_env),
        process_role=process_role,
        start_background_workers=parse_bool(os.getenv("NERAIUM_START_BACKGROUND_WORKERS"), process_role in {"all", "monolith", "worker"}),
        start_data_connection_poller=parse_bool(os.getenv("NERAIUM_START_DATA_POLLER"), False),
        default_telemetry_url=parse_default_telemetry_url(os.getenv("NERAIUM_DEFAULT_TELEMETRY_URL"), app_env),
        cors_origin_regex=parse_cors_origin_regex(os.getenv("CORS_ORIGIN_REGEX")),
        runtime_dir=parse_runtime_dir(os.getenv("NERAIUM_RUNTIME_DIR")),
        max_upload_size_bytes=parse_positive_int(os.getenv("NERAIUM_MAX_UPLOAD_SIZE_BYTES"), DEFAULT_MAX_UPLOAD_SIZE_BYTES),
        max_pending_upload_jobs=parse_positive_int(os.getenv("NERAIUM_MAX_PENDING_UPLOAD_JOBS"), DEFAULT_MAX_PENDING_UPLOAD_JOBS),
        notification_webhook_url=os.getenv("NERAIUM_NOTIFICATION_WEBHOOK_URL", "").strip(),
        notification_email_recipients=parse_csv_list(os.getenv("NERAIUM_NOTIFICATION_EMAIL_RECIPIENTS")),
        smtp_host=os.getenv("NERAIUM_SMTP_HOST", "").strip(),
        smtp_port=parse_positive_int(os.getenv("NERAIUM_SMTP_PORT"), 587),
        smtp_username=os.getenv("NERAIUM_SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("NERAIUM_SMTP_PASSWORD", "").strip(),
        smtp_sender=os.getenv("NERAIUM_SMTP_SENDER", "").strip(),
        smtp_use_tls=parse_bool(os.getenv("NERAIUM_SMTP_USE_TLS"), True),
    )
    validate_settings(settings)
    return settings


def parse_process_role(raw_value: str | None) -> str:
    if raw_value is None or raw_value.strip() == "":
        return DEFAULT_PROCESS_ROLE
    normalized = raw_value.strip().lower()
    if normalized in {"api", "worker", "all", "monolith"}:
        return normalized
    return DEFAULT_PROCESS_ROLE


def parse_bool(raw_value: str | None, default: bool) -> bool:
    if raw_value is None or raw_value.strip() == "":
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def parse_port(raw_value: str | None, default: int) -> int:
    if raw_value is None or raw_value.strip() == "":
        return default
    return int(raw_value)


def parse_cors_origins(raw_value: str | None, app_env: str = DEFAULT_APP_ENV) -> list[str]:
    if raw_value is None or raw_value.strip() == "":
        return DEFAULT_CORS_ORIGINS.copy()
    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    if str(app_env or "").strip().lower() in {"prod", "production"}:
        return origins
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
    return DEFAULT_TELEMETRY_URL


def parse_positive_int(raw_value: str | None, default: int) -> int:
    if raw_value is None or raw_value.strip() == "":
        return default
    value = int(raw_value)
    return value if value > 0 else default


def parse_csv_list(raw_value: str | None) -> list[str]:
    if raw_value is None or raw_value.strip() == "":
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def validate_settings(settings: Settings) -> None:
    app_env = str(settings.app_env or "").strip().lower()
    if app_env not in {"prod", "production"}:
        return
    if os.getenv("PYTEST_CURRENT_TEST"):
        return
    if settings.runtime_dir == DEFAULT_RUNTIME_DIR:
        raise ValueError("NERAIUM_RUNTIME_DIR must be set explicitly in production.")
