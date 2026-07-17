from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import threading
import time
from datetime import UTC, datetime
from typing import Any

_REQUEST_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("neraium_request_id", default=None)
_UPLOAD_SESSION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "neraium_upload_session_id", default=None
)

_STANDARD_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}
_SENSITIVE_KEY = re.compile(
    r"(?:^(?:session|refresh)$|authorization|cookie|password|passwd|secret|token|api[_-]?key|access[_-]?code|credential)",
    re.IGNORECASE,
)
_REDACTION_PATTERNS = (
    re.compile(r"(?i)\b(Bearer|Basic)\s+[^\s,;]+"),
    re.compile(r"(?i)\bcookie\s*[=:]\s*[^\s,]+"),
    re.compile(
        r"(?i)\b(authorization|cookie|password|passwd|secret|token|api[_-]?key|access[_-]?code|session|refresh)"
        r"(\s*[=:]\s*|\s+)([^\s,;&]+)"
    ),
    re.compile(r"(?i)([a-z][a-z0-9+.-]*://)([^/@\s:]+):([^@\s]+)@"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
)


def current_request_id() -> str | None:
    return _REQUEST_ID.get()


def current_upload_session_id() -> str | None:
    return _UPLOAD_SESSION_ID.get()


def bind_log_context(
    *,
    request_id: str | None = None,
    upload_session_id: str | None = None,
) -> tuple[contextvars.Token, contextvars.Token]:
    return (
        _REQUEST_ID.set(request_id),
        _UPLOAD_SESSION_ID.set(upload_session_id),
    )


def reset_log_context(tokens: tuple[contextvars.Token, contextvars.Token]) -> None:
    request_token, upload_token = tokens
    _REQUEST_ID.reset(request_token)
    _UPLOAD_SESSION_ID.reset(upload_token)


def redact_text(value: Any) -> str:
    text = str(value)
    for pattern in _REDACTION_PATTERNS:
        if "://" in pattern.pattern:
            text = pattern.sub(r"\1[REDACTED]:[REDACTED]@", text)
        elif "Bearer" in pattern.pattern:
            text = pattern.sub(r"\1 [REDACTED]", text)
        elif "authorization" in pattern.pattern:
            text = pattern.sub(r"\1\2[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def _sanitize(value: Any, *, key: str | None = None) -> Any:
    if key and _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(item_key): _sanitize(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(item) for item in value]
    return redact_text(value)


class DuplicateMessageFilter(logging.Filter):
    """Suppress identical low-severity messages for a short, bounded window."""

    def __init__(self, window_seconds: float = 30.0, max_entries: int = 2048) -> None:
        super().__init__()
        self.window_seconds = max(float(window_seconds), 0.0)
        self.max_entries = max(int(max_entries), 1)
        self._seen: dict[tuple[str, int, str], float] = {}
        self._lock = threading.Lock()

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR or self.window_seconds <= 0:
            return True
        try:
            message = redact_text(record.getMessage())
        except Exception:
            message = redact_text(record.msg)
        key = (record.name, record.levelno, message)
        now = time.monotonic()
        with self._lock:
            last_seen = self._seen.get(key)
            if last_seen is not None and now - last_seen < self.window_seconds:
                return False
            self._seen[key] = now
            if len(self._seen) > self.max_entries:
                cutoff = now - self.window_seconds
                self._seen = {
                    seen_key: timestamp
                    for seen_key, timestamp in self._seen.items()
                    if timestamp >= cutoff
                }
                while len(self._seen) > self.max_entries:
                    self._seen.pop(next(iter(self._seen)))
        return True


class NeraiumJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = redact_text(record.getMessage())
        event = getattr(record, "event", None) or (message.split(" ", 1)[0] if message else "log")
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": redact_text(event),
            "message": message,
        }
        parsed_fields = {
            match.group("key"): _sanitize(match.group("value"), key=match.group("key"))
            for match in re.finditer(
                r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>[^\s]+)",
                message,
            )
        }
        parsed_request_id = parsed_fields.pop("request_id", None)
        parsed_upload_session_id = parsed_fields.pop("upload_session_id", None)
        parsed_event = parsed_fields.pop("event", None)
        if parsed_event:
            payload["operation"] = parsed_event
        payload.update({key: value for key, value in parsed_fields.items() if key not in payload})

        request_id = (
            getattr(record, "request_id", None)
            or parsed_request_id
            or current_request_id()
        )
        upload_session_id = (
            getattr(record, "upload_session_id", None)
            or parsed_upload_session_id
            or current_upload_session_id()
        )
        if request_id:
            payload["request_id"] = redact_text(request_id)
            payload["correlation_id"] = redact_text(request_id)
        if upload_session_id:
            payload["upload_session_id"] = redact_text(upload_session_id)

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_FIELDS or key.startswith("_") or key in payload:
                continue
            payload[key] = _sanitize(value, key=key)

        if record.exc_info:
            payload["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Exception",
                "message": redact_text(record.exc_info[1]),
                "stacktrace": redact_text(self.formatException(record.exc_info)),
            }
        if record.stack_info:
            payload["stacktrace"] = redact_text(self.formatStack(record.stack_info))
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)


class NeraiumConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(UTC).isoformat()
        request_id = getattr(record, "request_id", None) or current_request_id()
        context = f" request_id={redact_text(request_id)}" if request_id else ""
        message = redact_text(record.getMessage())
        rendered = f"{timestamp} {record.levelname} {record.name}{context} {message}"
        if record.exc_info:
            rendered = f"{rendered}\n{redact_text(self.formatException(record.exc_info))}"
        return rendered


def configure_logging(*, level: str = "INFO", log_format: str = "json") -> None:
    normalized_level = str(level or "INFO").strip().upper()
    normalized_format = str(log_format or "json").strip().lower()
    numeric_level = getattr(logging, normalized_level, logging.INFO)
    # Pytest owns capture handlers and levels. Installing a production stdout
    # handler during collection duplicates every record and materially distorts
    # timing-sensitive lifecycle tests.
    if "pytest" in sys.modules:
        return
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    formatter: logging.Formatter
    formatter = NeraiumJsonFormatter() if normalized_format == "json" else NeraiumConsoleFormatter()

    managed_handlers = [
        handler for handler in root_logger.handlers if getattr(handler, "_neraium_managed", False)
    ]
    if managed_handlers:
        for handler in managed_handlers:
            handler.setLevel(numeric_level)
            handler.setFormatter(formatter)
        return

    # Reuse host-provided root handlers without duplicating output, but enforce
    # the production format/redaction contract on them.
    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setLevel(numeric_level)
            handler.setFormatter(formatter)
            if not getattr(handler, "_neraium_duplicate_filter", False):
                handler.addFilter(DuplicateMessageFilter())
                handler._neraium_duplicate_filter = True  # type: ignore[attr-defined]
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(formatter)
    handler.addFilter(DuplicateMessageFilter())
    handler._neraium_managed = True  # type: ignore[attr-defined]
    root_logger.addHandler(handler)
