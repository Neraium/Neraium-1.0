"""Executor admission bounds must precede authentication and JSON parsing."""
import asyncio

import pytest

from app.services.connector_execution import MAX_JOB_BYTES, build_executor_app


@pytest.fixture
def executor(tmp_path, monkeypatch):
    import boto3

    monkeypatch.setenv("NERAIUM_CONNECTOR_EXECUTOR_AUTH_SECRET_ARN", "test-auth")
    monkeypatch.setenv("NERAIUM_CONNECTOR_EXECUTOR_REPLAY_DB", str(tmp_path / "replay.sqlite"))
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: object())
    calls = []

    def execute(self, body, **kwargs):
        calls.append(body)
        return {"result": {"observations": []}}

    monkeypatch.setattr("app.services.connector_execution.ConnectorExecutionBroker.execute", execute)
    return build_executor_app(), calls


def request_chunks(app, chunks, headers=()):
    consumed = 0
    sent = []

    async def receive():
        nonlocal consumed
        index = consumed
        consumed += 1
        assert index < len(chunks), "Read beyond the provided request"
        return {"type": "http.request", "body": chunks[index], "more_body": index < len(chunks) - 1}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "scheme": "https", "method": "POST", "path": "/v1/connector-jobs",
        "raw_path": b"/v1/connector-jobs", "query_string": b"",
        "headers": [(b"host", b"testserver"), *headers],
        "client": ("192.0.2.1", 1000), "server": ("testserver", 443),
    }
    asyncio.run(app(scope, receive, send))
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    return status, consumed


@pytest.mark.parametrize("declared", [None, b"1", str(MAX_JOB_BYTES + 1).encode()])
def test_oversized_stream_stops_before_authentication(executor, declared):
    app, calls = executor
    headers = [] if declared is None else [(b"content-length", declared)]
    status, consumed = request_chunks(app, [b"a" * MAX_JOB_BYTES, b"x", b"never read"], headers)
    assert status == 413
    assert consumed == 2
    assert calls == []


def test_single_oversized_chunk_never_reaches_broker(executor):
    app, calls = executor
    assert request_chunks(app, [b"a" * (MAX_JOB_BYTES + 1)]) == (413, 1)
    assert calls == []


def test_exact_limit_preserves_original_job_bytes(executor):
    app, calls = executor
    body = b"a" * (MAX_JOB_BYTES - 1) + b"\n"
    assert request_chunks(app, [body[:100], body[100:]]) == (200, 2)
    assert calls == [body]
