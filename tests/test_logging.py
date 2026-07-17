import io
import json
import logging

from fastapi.testclient import TestClient

from app.core.logging_config import (
    DuplicateMessageFilter,
    NeraiumJsonFormatter,
    bind_log_context,
    reset_log_context,
)
from app.main import create_app


def _formatted_record(message: str, *args, **extra) -> dict:
    record = logging.LogRecord(
        name="neraium.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=args,
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(NeraiumJsonFormatter().format(record))


def test_json_logging_includes_structured_correlation_context() -> None:
    tokens = bind_log_context(request_id="request-123", upload_session_id="upload-456")
    try:
        payload = _formatted_record(
            "upload_completed",
            event="upload_completed",
            job_id="job-789",
            row_count=42,
        )
    finally:
        reset_log_context(tokens)

    assert payload["event"] == "upload_completed"
    assert payload["request_id"] == "request-123"
    assert payload["correlation_id"] == "request-123"
    assert payload["upload_session_id"] == "upload-456"
    assert payload["job_id"] == "job-789"
    assert payload["row_count"] == 42


def test_json_logging_redacts_secrets_in_messages_and_fields() -> None:
    payload = _formatted_record(
        "connector failed authorization=Bearer top-secret "
        "url=https://operator:password@db.example.test/path "
        "access_key=AKIAABCDEFGHIJKLMNOP "
        "cookie=session=browser-secret; refresh=other-secret",
        smtp_password="mail-secret",
        headers={"Authorization": "Bearer hidden", "safe": "value"},
    )
    rendered = json.dumps(payload)

    assert "top-secret" not in rendered
    assert "operator" not in rendered
    assert "password@db" not in rendered
    assert "AKIAABCDEFGHIJKLMNOP" not in rendered
    assert "mail-secret" not in rendered
    assert "browser-secret" not in rendered
    assert "other-secret" not in rendered
    assert "Bearer hidden" not in rendered
    assert rendered.count("[REDACTED]") >= 4
    assert payload["headers"]["safe"] == "value"


def test_duplicate_filter_suppresses_repeated_non_error_messages() -> None:
    duplicate_filter = DuplicateMessageFilter(window_seconds=60)
    first = logging.LogRecord("worker", logging.INFO, __file__, 1, "idle", (), None)
    second = logging.LogRecord("worker", logging.INFO, __file__, 2, "idle", (), None)
    error = logging.LogRecord("worker", logging.ERROR, __file__, 3, "idle", (), None)

    assert duplicate_filter.filter(first) is True
    assert duplicate_filter.filter(second) is False
    assert duplicate_filter.filter(error) is True


def test_request_id_is_echoed_and_generated_when_missing() -> None:
    with TestClient(create_app()) as client:
        valid = client.get("/api/health", headers={"X-Request-Id": "ops-request:123"})
        generated = client.get("/api/health")

    assert valid.headers["X-Request-Id"] == "ops-request:123"
    assert len(generated.headers["X-Request-Id"]) == 32
