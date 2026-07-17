from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_APP_ENV = "development"
DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8010
DEFAULT_TELEMETRY_URL = ""
DEFAULT_PROCESS_ROLE = "all"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "json"
DEFAULT_SHUTDOWN_TIMEOUT_SECONDS = 30.0
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

_VALID_APP_ENVS = {"development", "test", "staging", "prod", "production"}
_VALID_PROCESS_ROLES = {"api", "worker", "all", "monolith"}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_VALID_LOG_FORMATS = {"json", "console"}
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


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
    log_level: str = DEFAULT_LOG_LEVEL
    log_format: str = DEFAULT_LOG_FORMAT
    shutdown_timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT_SECONDS


def get_settings() -> Settings:
    app_env = parse_app_env(os.getenv("APP_ENV"))
    process_role = parse_process_role(os.getenv("NERAIUM_PROCESS_ROLE"))
    settings = Settings(
        app_env=app_env,
        backend_host=parse_nonempty_string(os.getenv("BACKEND_HOST"), DEFAULT_BACKEND_HOST, "BACKEND_HOST"),
        backend_port=parse_port(os.getenv("BACKEND_PORT"), DEFAULT_BACKEND_PORT),
        cors_origins=parse_cors_origins(os.getenv("CORS_ORIGINS"), app_env=app_env),
        process_role=process_role,
        start_background_workers=parse_bool(
            os.getenv("NERAIUM_START_BACKGROUND_WORKERS"),
            process_role in {"all", "monolith", "worker"},
            name="NERAIUM_START_BACKGROUND_WORKERS",
        ),
        start_data_connection_poller=parse_bool(
            os.getenv("NERAIUM_START_DATA_POLLER"),
            False,
            name="NERAIUM_START_DATA_POLLER",
        ),
        default_telemetry_url=parse_default_telemetry_url(
            os.getenv("NERAIUM_DEFAULT_TELEMETRY_URL"), app_env
        ),
        cors_origin_regex=parse_cors_origin_regex(os.getenv("CORS_ORIGIN_REGEX")),
        runtime_dir=parse_runtime_dir(os.getenv("NERAIUM_RUNTIME_DIR")),
        max_upload_size_bytes=parse_positive_int(
            os.getenv("NERAIUM_MAX_UPLOAD_SIZE_BYTES"),
            DEFAULT_MAX_UPLOAD_SIZE_BYTES,
            name="NERAIUM_MAX_UPLOAD_SIZE_BYTES",
        ),
        max_pending_upload_jobs=parse_positive_int(
            os.getenv("NERAIUM_MAX_PENDING_UPLOAD_JOBS"),
            DEFAULT_MAX_PENDING_UPLOAD_JOBS,
            name="NERAIUM_MAX_PENDING_UPLOAD_JOBS",
        ),
        notification_webhook_url=os.getenv("NERAIUM_NOTIFICATION_WEBHOOK_URL", "").strip(),
        notification_email_recipients=parse_csv_list(
            os.getenv("NERAIUM_NOTIFICATION_EMAIL_RECIPIENTS")
        ),
        smtp_host=os.getenv("NERAIUM_SMTP_HOST", "").strip(),
        smtp_port=parse_port(os.getenv("NERAIUM_SMTP_PORT"), 587, name="NERAIUM_SMTP_PORT"),
        smtp_username=os.getenv("NERAIUM_SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("NERAIUM_SMTP_PASSWORD", "").strip(),
        smtp_sender=os.getenv("NERAIUM_SMTP_SENDER", "").strip(),
        smtp_use_tls=parse_bool(
            os.getenv("NERAIUM_SMTP_USE_TLS"), True, name="NERAIUM_SMTP_USE_TLS"
        ),
        log_level=parse_log_level(os.getenv("LOG_LEVEL")),
        log_format=parse_log_format(os.getenv("LOG_FORMAT")),
        shutdown_timeout_seconds=parse_positive_float(
            os.getenv("NERAIUM_SHUTDOWN_TIMEOUT_SECONDS"),
            DEFAULT_SHUTDOWN_TIMEOUT_SECONDS,
            name="NERAIUM_SHUTDOWN_TIMEOUT_SECONDS",
        ),
    )
    validate_settings(settings)
    return settings


def parse_app_env(raw_value: str | None) -> str:
    normalized = str(raw_value or DEFAULT_APP_ENV).strip().lower()
    if normalized not in _VALID_APP_ENVS:
        raise ValueError(
            f"APP_ENV must be one of {', '.join(sorted(_VALID_APP_ENVS))}; got {normalized!r}."
        )
    return normalized


def parse_process_role(raw_value: str | None) -> str:
    if raw_value is None or raw_value.strip() == "":
        return DEFAULT_PROCESS_ROLE
    normalized = raw_value.strip().lower()
    if normalized not in _VALID_PROCESS_ROLES:
        raise ValueError(
            f"NERAIUM_PROCESS_ROLE must be one of {', '.join(sorted(_VALID_PROCESS_ROLES))}; "
            f"got {normalized!r}."
        )
    return normalized


def parse_bool(raw_value: str | None, default: bool, *, name: str = "boolean setting") -> bool:
    if raw_value is None or raw_value.strip() == "":
        return default
    normalized = raw_value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(
        f"{name} must be a boolean value ({', '.join(sorted(_TRUE_VALUES | _FALSE_VALUES))}); "
        f"got {raw_value!r}."
    )


def parse_nonempty_string(raw_value: str | None, default: str, name: str) -> str:
    if raw_value is None:
        return default
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty.")
    return normalized


def parse_port(raw_value: str | None, default: int, *, name: str = "BACKEND_PORT") -> int:
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = int(raw_value)
    except ValueError:
        raise ValueError(f"{name} must be an integer between 1 and 65535; got {raw_value!r}.") from None
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535; got {value}.")
    return value


def parse_cors_origins(raw_value: str | None, app_env: str = DEFAULT_APP_ENV) -> list[str]:
    if raw_value is None or raw_value.strip() == "":
        return DEFAULT_CORS_ORIGINS.copy()
    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    if not origins:
        raise ValueError("CORS_ORIGINS must contain at least one origin.")
    if str(app_env or "").strip().lower() in {"prod", "production"}:
        return origins
    for required_origin in DEFAULT_CORS_ORIGINS:
        if required_origin not in origins:
            origins.append(required_origin)
    return origins


def parse_cors_origin_regex(raw_value: str | None) -> str | None:
    value = raw_value.strip() if raw_value and raw_value.strip() else DEFAULT_CORS_ORIGIN_REGEX
    try:
        re.compile(value)
    except re.error as error:
        raise ValueError(f"CORS_ORIGIN_REGEX is invalid: {error}.") from None
    return value


def parse_runtime_dir(raw_value: str | None) -> Path:
    if raw_value and raw_value.strip():
        return Path(raw_value.strip()).expanduser()
    return DEFAULT_RUNTIME_DIR


def parse_default_telemetry_url(raw_value: str | None, app_env: str) -> str:
    del app_env
    if raw_value and raw_value.strip():
        return raw_value.strip()
    return DEFAULT_TELEMETRY_URL


def parse_positive_int(raw_value: str | None, default: int, *, name: str = "setting") -> int:
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = int(raw_value)
    except ValueError:
        raise ValueError(f"{name} must be a positive integer; got {raw_value!r}.") from None
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero; got {value}.")
    return value


def parse_positive_float(raw_value: str | None, default: float, *, name: str = "setting") -> float:
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = float(raw_value)
    except ValueError:
        raise ValueError(f"{name} must be a positive number; got {raw_value!r}.") from None
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero; got {value}.")
    return value


def parse_log_level(raw_value: str | None) -> str:
    normalized = str(raw_value or DEFAULT_LOG_LEVEL).strip().upper()
    if normalized not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"LOG_LEVEL must be one of {', '.join(sorted(_VALID_LOG_LEVELS))}; got {normalized!r}."
        )
    return normalized


def parse_log_format(raw_value: str | None) -> str:
    normalized = str(raw_value or DEFAULT_LOG_FORMAT).strip().lower()
    if normalized not in _VALID_LOG_FORMATS:
        raise ValueError(
            f"LOG_FORMAT must be one of {', '.join(sorted(_VALID_LOG_FORMATS))}; got {normalized!r}."
        )
    return normalized


def parse_csv_list(raw_value: str | None) -> list[str]:
    if raw_value is None or raw_value.strip() == "":
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def validate_settings(settings: Settings) -> None:
    app_env = parse_app_env(settings.app_env)
    parse_port(str(settings.backend_port), DEFAULT_BACKEND_PORT)
    parse_log_level(settings.log_level)
    parse_log_format(settings.log_format)
    if not str(settings.backend_host or "").strip():
        raise ValueError("BACKEND_HOST must not be empty.")
    if not settings.cors_origins:
        raise ValueError("CORS_ORIGINS must contain at least one origin.")
    parse_cors_origin_regex(settings.cors_origin_regex)

    if settings.notification_webhook_url:
        webhook = urlsplit(settings.notification_webhook_url)
        if webhook.scheme not in {"http", "https"} or not webhook.netloc:
            raise ValueError("NERAIUM_NOTIFICATION_WEBHOOK_URL must be an absolute HTTP(S) URL.")
        if webhook.username or webhook.password:
            raise ValueError(
                "NERAIUM_NOTIFICATION_WEBHOOK_URL must not contain embedded credentials."
            )

    smtp_fields_configured = any(
        (
            settings.smtp_host,
            settings.notification_email_recipients,
            settings.smtp_sender,
            settings.smtp_username,
            settings.smtp_password,
        )
    )
    if smtp_fields_configured:
        missing: list[str] = []
        if not settings.smtp_host:
            missing.append("NERAIUM_SMTP_HOST")
        if not settings.notification_email_recipients:
            missing.append("NERAIUM_NOTIFICATION_EMAIL_RECIPIENTS")
        if not settings.smtp_sender:
            missing.append("NERAIUM_SMTP_SENDER")
        if missing:
            raise ValueError(
                "SMTP notification configuration is incomplete; missing " + ", ".join(missing) + "."
            )
        if settings.smtp_username and not settings.smtp_password:
            raise ValueError(
                "NERAIUM_SMTP_PASSWORD is required when NERAIUM_SMTP_USERNAME is set."
            )
        if settings.smtp_password and not settings.smtp_username:
            raise ValueError(
                "NERAIUM_SMTP_USERNAME is required when NERAIUM_SMTP_PASSWORD is set."
            )

    if app_env not in {"prod", "production"}:
        return
    if settings.runtime_dir == DEFAULT_RUNTIME_DIR:
        raise ValueError("NERAIUM_RUNTIME_DIR must be set explicitly in production.")
    if "*" in settings.cors_origins:
        raise ValueError("Production CORS_ORIGINS must not include a wildcard origin.")



def validate_environment_completeness(settings: Settings) -> None:
    app_env = str(getattr(settings, "app_env", DEFAULT_APP_ENV) or "").strip().lower()
    if app_env in {"prod", "production"}:
        if not str(os.getenv("CORS_ORIGINS", "")).strip():
            raise ValueError("CORS_ORIGINS must be set explicitly in production.")
        if (
            str(getattr(settings, "process_role", DEFAULT_PROCESS_ROLE) or "").strip().lower() in {"api", "worker"}
            and not str(os.getenv("NERAIUM_UPLOAD_STATE_BUCKET", "")).strip()
        ):
            raise ValueError(
                "NERAIUM_UPLOAD_STATE_BUCKET is required for split-role production."
            )

    for label, email_name, password_name in (
        (
            "admin bootstrap",
            "NERAIUM_BOOTSTRAP_ADMIN_EMAIL",
            "NERAIUM_BOOTSTRAP_ADMIN_PASSWORD",
        ),
        (
            "operator bootstrap",
            "NERAIUM_BOOTSTRAP_OPERATOR_EMAIL",
            "NERAIUM_BOOTSTRAP_OPERATOR_PASSWORD",
        ),
    ):
        email_set = bool(str(os.getenv(email_name, "")).strip())
        password_set = bool(str(os.getenv(password_name, "")).strip())
        if email_set != password_set:
            missing = password_name if email_set else email_name
            raise ValueError(f"{label} configuration is incomplete; missing {missing}.")
