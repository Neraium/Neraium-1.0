from __future__ import annotations

from datetime import UTC, datetime
from dataclasses import dataclass
import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.connectors.base import ConnectorFailureKind, TelemetryConnectorError
from app.services.connector_execution import (
    APPROVED_HOST,
    EXECUTOR_VERSION,
    ConnectorExecutionBroker,
    _page_from_wire,
)


class FakeSecretClient:
    def __init__(self, key: str) -> None:
        self.key = key

    def get_secret_value(self, *, SecretId: str):
        assert SecretId == "executor-auth"
        return {"SecretString": self.key}


class FakeConnectorSecretStore:
    _client = None

    def __init__(self, secret_client, secret_values=None):
        self._client = secret_client
        self.secret_values = secret_values or {}

    def resolve(self, binding):
        from app.services.telemetry_secrets import ResolvedSecret

        assert binding._internal_reference == "arn:aws:secretsmanager:us-east-2:000000000000:secret:neraium/prod/telemetry-connections/scope-x/connection-y"
        return ResolvedSecret(self.secret_values)


def make_job(**changes):
    job = {
        "version": EXECUTOR_VERSION,
        "request_identity": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "tenant_scope_id": "tenant-x",
        "workspace_id": "ws-x",
        "facility_id": "ws-x",
        "resource_scope_id": "scope-x",
        "connection_id": "connection-y",
        "connector_type": "https_telemetry",
        "operation": "incremental",
        "approved_destination": f"https://{APPROVED_HOST}:443",
        "configuration": {
            "base_url": f"https://{APPROVED_HOST}",
            "request_path": "/telemetry",
            "authentication_scheme": "none",
            "timestamp_field": "timestamp",
            "value_field": "value",
            "external_tag_id_field": "tag_id",
        },
        "credential": None,
        "checkpoint": None,
        "time_range": None,
    }
    job.update(changes)
    return job


def signed(job, key="a" * 64, timestamp=None):
    body = json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    timestamp = str(timestamp or int(datetime.now(UTC).timestamp()))
    signature = hmac.new(key.encode(), timestamp.encode() + b"\n" + body, hashlib.sha256).hexdigest()
    return body, timestamp, signature


def test_broker_requires_valid_hmac_and_rejects_tampering(tmp_path, monkeypatch):
    key = "a" * 64
    store = FakeConnectorSecretStore(FakeSecretClient(key))
    broker = ConnectorExecutionBroker(secret_store=store, auth_secret_arn="executor-auth",
                                      replay_db_path=str(tmp_path / "replay.sqlite"))
    monkeypatch.setattr("app.services.connector_execution._execute_unprivileged",
                        lambda request, secret: {"observations": [], "signals": [], "issues": [],
                                                 "next_checkpoint": None, "has_more": False,
                                                 "pages_read": 1, "response_bytes": 2,
                                                 "retry_count": 0})
    body, timestamp, signature = signed(make_job(), key)
    response = broker.execute(body, timestamp=timestamp, signature=signature)
    assert response["result"]["pages_read"] == 1
    assert "secret" not in json.dumps(response).lower()

    altered = json.loads(body)
    altered["tenant_scope_id"] = "tenant-attacker"
    with pytest.raises(TelemetryConnectorError) as error:
        broker.execute(json.dumps(altered, sort_keys=True, separators=(",", ":")).encode(),
                       timestamp=timestamp, signature=signature)
    assert error.value.code == "connector_authority_invalid"


def test_broker_rejects_replay_and_unapproved_destinations(tmp_path, monkeypatch):
    key = "b" * 64
    broker = ConnectorExecutionBroker(
        secret_store=FakeConnectorSecretStore(FakeSecretClient(key)),
        auth_secret_arn="executor-auth", replay_db_path=str(tmp_path / "replay.sqlite"),
    )
    monkeypatch.setattr("app.services.connector_execution._execute_unprivileged",
                        lambda request, secret: {"observations": []})
    body, timestamp, signature = signed(make_job(), key)
    broker.execute(body, timestamp=timestamp, signature=signature)
    with pytest.raises(TelemetryConnectorError) as replay:
        broker.execute(body, timestamp=timestamp, signature=signature)
    assert replay.value.code == "connector_job_replayed"

    denied_job = make_job()
    denied_job["configuration"]["base_url"] = "https://example.com"
    denied_body, denied_timestamp, denied_signature = signed(denied_job, key)
    with pytest.raises(TelemetryConnectorError) as denied:
        broker.execute(denied_body, timestamp=denied_timestamp, signature=denied_signature)
    assert denied.value.code == "unapproved_destination"
    assert denied.value.kind is ConnectorFailureKind.CONFIGURATION


def test_secret_binding_is_required_to_match_connection_and_scope(tmp_path):
    key = "c" * 64
    store = FakeConnectorSecretStore(FakeSecretClient(key), {"api_key": "never-return-this"})
    broker = ConnectorExecutionBroker(secret_store=store, auth_secret_arn="executor-auth",
                                      replay_db_path=str(tmp_path / "replay.sqlite"))
    job = make_job(credential={
        "binding_id": "binding-y", "provider": "aws_secrets_manager",
        "resource_scope_id": "wrong-scope", "connection_id": "connection-y",
        "reference": "arn:aws:secretsmanager:us-east-2:000000000000:secret:neraium/prod/telemetry-connections/scope-x/connection-y",
        "version_marker": "version-y",
    })
    body, timestamp, signature = signed(job, key)
    with pytest.raises(TelemetryConnectorError) as error:
        broker.execute(body, timestamp=timestamp, signature=signature)
    assert error.value.code == "credential_binding_mismatch"


def test_executor_http_route_authenticates_request_and_returns_normalized_result(
    tmp_path, monkeypatch
):
    import boto3

    key = "d" * 64
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    monkeypatch.setenv("NERAIUM_CONNECTOR_EXECUTOR_AUTH_SECRET_ARN", "executor-auth")
    monkeypatch.setenv("NERAIUM_CONNECTOR_EXECUTOR_REPLAY_DB", str(tmp_path / "replay.sqlite"))
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: FakeSecretClient(key))
    monkeypatch.setattr(
        "app.services.connector_execution._execute_unprivileged",
        lambda request, secret: {"observations": [], "signals": [], "issues": [],
                                 "next_checkpoint": None, "has_more": False,
                                 "pages_read": 1, "response_bytes": 2, "retry_count": 0},
    )

    from app.services.connector_execution import build_executor_app

    client = TestClient(build_executor_app())
    body, timestamp, signature = signed(make_job(), key)
    response = client.post(
        "/v1/connector-jobs",
        content=body,
        headers={"x-neraium-timestamp": timestamp, "x-neraium-signature": signature},
    )
    assert response.status_code == 200
    assert response.json()["result"]["pages_read"] == 1
    assert "secret" not in response.text.lower()

    response = client.post(
        "/v1/connector-jobs",
        content=body,
        headers={"x-neraium-timestamp": timestamp, "x-neraium-signature": "0" * 64},
    )
    assert response.status_code == 403


def test_result_adapter_tolerates_older_production_observation_contract(monkeypatch):
    @dataclass
    class LegacyObservation:
        external_tag_id: str
        external_tag_name: str
        source_timestamp: object
        raw_value: object
        reported_unit: str | None = None
        reported_quality: str | None = None
        provider_event_id: str | None = None
        metadata: dict | None = None

    monkeypatch.setattr(
        "app.services.connector_execution.RawObservationEnvelope", LegacyObservation
    )
    page = _page_from_wire(
        {
            "observations": [
                {
                    "external_tag_id": "flow",
                    "external_tag_name": "Flow",
                    "source_timestamp": "2026-10-02T00:00:00Z",
                    "raw_value": 42,
                    "native_quality": "good",
                    "acquired_at_utc": "2026-10-02T00:00:01Z",
                }
            ]
        }
    )
    assert page.observations[0].external_tag_id == "flow"
