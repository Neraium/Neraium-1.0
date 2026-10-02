"""Authenticated client and isolated EC2 execution service for HTTPS telemetry.

The API/worker side submits only server-owned authority and receives the
existing ConnectorPage contract. The EC2 broker resolves secrets, then runs
the connector in a separate unprivileged process with no AWS environment.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import sqlite3
import ssl
import subprocess
import sys
import time
from typing import Any, Mapping
from urllib.parse import urlsplit
import uuid

import httpx
from fastapi import Request

from app.connectors.base import (
    BoundedBackfillRange,
    ConnectorCheckpoint,
    ConnectorExecutionContext,
    ConnectorFailureKind,
    ConnectorPage,
    ConnectorProviderDescriptor,
    ConnectorRecordIssue,
    ConnectorValidationResult,
    DiscoveredSignal,
    ProviderHealthResult,
    RawObservationEnvelope,
    TelemetryConnector,
    TelemetryConnectorError,
)
from app.connectors.https_telemetry import HttpsTelemetryConnector
from app.services.telemetry_domain import ConnectorCapability, ConnectorType
from app.services.telemetry_egress import TelemetryEgressError, TelemetryEgressPolicy
from app.services.telemetry_secrets import (
    AwsSecretsManagerTelemetryStore,
    ResolvedSecret,
    SecretBinding,
    TelemetrySecretError,
)

logger = logging.getLogger(__name__)

EXECUTOR_VERSION = "neraium-connector-executor.v1"
APPROVED_HOST = "bfzcudq5o2.execute-api.us-east-2.amazonaws.com"
MAX_JOB_BYTES = 256 * 1024
MAX_RESULT_BYTES = 10 * 1024 * 1024
MAX_CLOCK_SKEW_SECONDS = 120


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _wire(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: _wire(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _wire(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(item) for item in value]
    return value


def _datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("connector_result_timestamp_invalid")
    return parsed.astimezone(UTC)


def _page_from_wire(raw: Mapping[str, Any]) -> ConnectorPage:
    checkpoint_raw = raw.get("next_checkpoint")
    checkpoint = None
    if checkpoint_raw is not None:
        checkpoint = ConnectorCheckpoint(
            cursor=checkpoint_raw.get("cursor"),
            high_water_at=_datetime(checkpoint_raw.get("high_water_at")),
        )
    observation_fields = {item.name for item in fields(RawObservationEnvelope)}
    observations = tuple(
        RawObservationEnvelope(
            **{
                key: value
                for key, value in {
                    "external_tag_id": item["external_tag_id"],
                    "external_tag_name": item["external_tag_name"],
                    "source_timestamp": item.get("source_timestamp"),
                    "raw_value": item.get("raw_value"),
                    "reported_unit": item.get("reported_unit"),
                    "reported_quality": item.get("reported_quality"),
                    "provider_event_id": item.get("provider_event_id"),
                    "metadata": item.get("metadata") or {},
                    "native_quality": item.get("native_quality"),
                    "acquired_at_utc": _datetime(item.get("acquired_at_utc")),
                }.items()
                if key in observation_fields
            }
        )
        for item in raw.get("observations", [])
    )
    signals = tuple(
        DiscoveredSignal(
            external_tag_id=item["external_tag_id"],
            external_tag_name=item["external_tag_name"],
            display_label=item.get("display_label"),
            reported_unit=item.get("reported_unit"),
            metadata=item.get("metadata") or {},
        )
        for item in raw.get("signals", [])
    )
    issues = tuple(
        ConnectorRecordIssue(
            record_index=item["record_index"],
            code=item["code"],
            safe_message=item.get("safe_message") or "Telemetry source returned an invalid record.",
        )
        for item in raw.get("issues", [])
    )
    return ConnectorPage(
        observations=observations,
        signals=signals,
        issues=issues,
        next_checkpoint=checkpoint,
        has_more=bool(raw.get("has_more", False)),
        pages_read=int(raw.get("pages_read", 0)),
        response_bytes=int(raw.get("response_bytes", 0)),
        retry_count=int(raw.get("retry_count", 0)),
    )


def _secret_key(client: Any, secret_arn: str) -> bytes:
    if not secret_arn:
        raise RuntimeError("connector_executor_auth_unavailable")
    try:
        raw = client.get_secret_value(SecretId=secret_arn).get("SecretString")
    except Exception:
        raise RuntimeError("connector_executor_auth_unavailable") from None
    if not isinstance(raw, str) or len(raw) < 32 or len(raw) > 512:
        raise RuntimeError("connector_executor_auth_unavailable")
    return raw.encode("utf-8")


class RemoteHttpsTelemetryConnector(TelemetryConnector):
    """Synchronous adapter preserving the existing connector contract."""

    def __init__(self, *, endpoint: str, ca_pem: str, auth_secret_arn: str,
                 secret_client: Any, timeout_seconds: float = 90.0) -> None:
        self.endpoint = str(endpoint).rstrip("/")
        parts = urlsplit(self.endpoint)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ValueError("connector_executor_endpoint_invalid")
        self._ca_pem = str(ca_pem)
        if "BEGIN CERTIFICATE" not in self._ca_pem:
            raise ValueError("connector_executor_ca_invalid")
        self._auth_secret_arn = str(auth_secret_arn)
        self._secret_client = secret_client
        self._timeout = min(max(float(timeout_seconds), 5.0), 120.0)

    @classmethod
    def descriptor(cls) -> ConnectorProviderDescriptor:
        return HttpsTelemetryConnector.descriptor()

    def _call(self, operation: str, context: ConnectorExecutionContext, *,
              checkpoint: ConnectorCheckpoint | None = None,
              time_range: BoundedBackfillRange | None = None) -> dict[str, Any]:
        binding = context.secret_binding
        if not all((context.tenant_scope_id, context.workspace_id,
                    context.facility_id, context.resource_scope_id,
                    context.connection_id)):
            raise TelemetryConnectorError("connector_authority_missing",
                kind=ConnectorFailureKind.CONFIGURATION)
        config = dict(context.configuration)
        try:
            destination = TelemetryEgressPolicy().normalize_url(str(config.get("base_url") or ""))
            parts = urlsplit(destination)
            if parts.hostname != APPROVED_HOST or parts.port not in (None, 443):
                raise TelemetryEgressError("unapproved_destination")
        except TelemetryEgressError as error:
            raise TelemetryConnectorError(error.code,
                kind=ConnectorFailureKind.CONFIGURATION,
                safe_message="Telemetry destination is not allowed.") from None
        job_id = str(uuid.uuid4())
        created = datetime.now(UTC).isoformat()
        secret_reference = binding._internal_reference if binding else None
        job = {
            "version": EXECUTOR_VERSION,
            "request_identity": job_id,
            "created_at": created,
            "tenant_scope_id": context.tenant_scope_id,
            "workspace_id": context.workspace_id,
            "facility_id": context.facility_id,
            "resource_scope_id": context.resource_scope_id,
            "connection_id": context.connection_id,
            "connector_type": ConnectorType.HTTPS_TELEMETRY.value,
            "operation": operation,
            "approved_destination": f"https://{APPROVED_HOST}:443",
            "configuration": config,
            "credential": None if binding is None else {
                "binding_id": binding.binding_id,
                "provider": binding.provider,
                "resource_scope_id": binding.resource_scope_id,
                "connection_id": binding.connection_id,
                "reference": secret_reference,
                "version_marker": binding.version_marker,
            },
            "checkpoint": _wire(checkpoint) if checkpoint else None,
            "time_range": _wire(time_range) if time_range else None,
        }
        body = _canonical_json(job)
        if len(body) > MAX_JOB_BYTES:
            raise TelemetryConnectorError("connector_job_too_large",
                kind=ConnectorFailureKind.BUDGET)
        timestamp = str(int(time.time()))
        key = _secret_key(self._secret_client, self._auth_secret_arn)
        signature = hmac.new(key, timestamp.encode() + b"\n" + body, hashlib.sha256).hexdigest()
        try:
            with httpx.Client(verify=ssl.create_default_context(cadata=self._ca_pem),
                              timeout=self._timeout, trust_env=False) as client:
                response = client.post(
                    f"{self.endpoint}/v1/connector-jobs",
                    content=body,
                    headers={"content-type": "application/json",
                             "x-neraium-timestamp": timestamp,
                             "x-neraium-signature": signature},
                )
        except httpx.HTTPError:
            raise TelemetryConnectorError("connector_executor_unavailable",
                kind=ConnectorFailureKind.NETWORK, retryable=True,
                safe_message="The isolated telemetry executor could not be reached.") from None
        if len(response.content) > MAX_RESULT_BYTES:
            raise TelemetryConnectorError("connector_executor_result_too_large",
                kind=ConnectorFailureKind.BUDGET)
        try:
            payload = response.json()
        except ValueError:
            raise TelemetryConnectorError("connector_executor_response_invalid",
                kind=ConnectorFailureKind.PAYLOAD) from None
        if response.status_code != 200:
            code = str(payload.get("code") or "connector_executor_rejected")
            kind = ConnectorFailureKind(payload.get("kind", "network")) if payload.get("kind") in {x.value for x in ConnectorFailureKind} else ConnectorFailureKind.NETWORK
            raise TelemetryConnectorError(code, kind=kind,
                retryable=bool(payload.get("retryable", False)),
                safe_message="Isolated telemetry execution failed.")
        if payload.get("request_identity") != job_id:
            raise TelemetryConnectorError("connector_executor_identity_mismatch",
                kind=ConnectorFailureKind.PAYLOAD)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise TelemetryConnectorError("connector_executor_result_invalid",
                kind=ConnectorFailureKind.PAYLOAD)
        return result

    def validate(self, context: ConnectorExecutionContext) -> ConnectorValidationResult:
        result = self._call("validate", context)
        return ConnectorValidationResult(**result)

    def health(self, context: ConnectorExecutionContext) -> ProviderHealthResult:
        result = self._call("health", context)
        result["checked_at"] = _datetime(result["checked_at"])
        return ProviderHealthResult(**result)

    def discover_signals(self, context: ConnectorExecutionContext, *,
                         checkpoint: ConnectorCheckpoint | None = None) -> ConnectorPage:
        return _page_from_wire(self._call("discovery", context, checkpoint=checkpoint))

    def fetch_incremental(self, context: ConnectorExecutionContext, *,
                          checkpoint: ConnectorCheckpoint | None = None) -> ConnectorPage:
        return _page_from_wire(self._call("incremental", context, checkpoint=checkpoint))

    def fetch_backfill(self, context: ConnectorExecutionContext, *,
                       time_range: BoundedBackfillRange,
                       checkpoint: ConnectorCheckpoint | None = None) -> ConnectorPage:
        return _page_from_wire(self._call("backfill", context,
                                          checkpoint=checkpoint, time_range=time_range))


class _BoundSecretStore:
    def __init__(self, binding: SecretBinding, secret: ResolvedSecret) -> None:
        self._binding = binding
        self._secret = secret

    def resolve(self, binding: SecretBinding, *, force_refresh: bool = False) -> ResolvedSecret:
        del force_refresh
        if (binding.binding_id, binding.connection_id, binding.resource_scope_id,
            binding.provider, binding._internal_reference) != (
            self._binding.binding_id, self._binding.connection_id,
            self._binding.resource_scope_id, self._binding.provider,
            self._binding._internal_reference):
            raise TelemetrySecretError("secret_ownership_mismatch")
        return self._secret

    def resolve_after_auth_failure(self, binding: SecretBinding) -> ResolvedSecret:
        return self.resolve(binding, force_refresh=True)


def _execute_unprivileged(request: Mapping[str, Any], *,
                          secret: ResolvedSecret | None) -> dict[str, Any]:
    """Child entrypoint; only this process performs the upstream HTTP call."""
    user_uid = 10002
    user_gid = 10002
    payload = dict(request)
    payload["secret_values"] = getattr(secret, "_values", {}) if secret else None
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONPATH": "/app",
           "HOME": "/nonexistent", "PYTHONUNBUFFERED": "1"}

    try:
        completed = subprocess.run(
            [sys.executable, "-m", "app.services.connector_execution_child"],
            input=_canonical_json(payload), stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=75, check=False,
            env=env, user=user_uid, group=user_gid, extra_groups=(),
        )
    except (OSError, subprocess.TimeoutExpired):
        raise TelemetryConnectorError("connector_process_failed",
            kind=ConnectorFailureKind.NETWORK,
            safe_message="Isolated telemetry execution failed.") from None
    if completed.returncode != 0 or len(completed.stdout) > MAX_RESULT_BYTES:
        raise TelemetryConnectorError("connector_process_failed",
            kind=ConnectorFailureKind.NETWORK,
            safe_message="Isolated telemetry execution failed.")
    try:
        result = json.loads(completed.stdout)
    except (ValueError, UnicodeDecodeError):
        raise TelemetryConnectorError("connector_process_result_invalid",
            kind=ConnectorFailureKind.PAYLOAD) from None
    if not isinstance(result, dict) or "error" in result:
        error = result.get("error") if isinstance(result, dict) else None
        if isinstance(error, dict):
            code = str(error.get("code") or "connector_execution_failed")
            kind_raw = str(error.get("kind") or "network")
            kind = ConnectorFailureKind(kind_raw) if kind_raw in {x.value for x in ConnectorFailureKind} else ConnectorFailureKind.NETWORK
            raise TelemetryConnectorError(code, kind=kind,
                retryable=bool(error.get("retryable", False)),
                safe_message="Isolated telemetry execution failed.")
        raise TelemetryConnectorError("connector_process_result_invalid",
            kind=ConnectorFailureKind.PAYLOAD)
    return result


class ConnectorExecutionBroker:
    def __init__(self, *, secret_store: AwsSecretsManagerTelemetryStore,
                 auth_secret_arn: str, replay_db_path: str) -> None:
        self.secret_store = secret_store
        self.auth_secret_arn = auth_secret_arn
        self._db_path = replay_db_path
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS used_jobs (request_identity TEXT PRIMARY KEY, digest TEXT NOT NULL, created_at INTEGER NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS ix_used_jobs_created ON used_jobs(created_at)")

    def execute(self, raw_body: bytes, *, timestamp: str, signature: str) -> dict[str, Any]:
        if len(raw_body) > MAX_JOB_BYTES:
            raise TelemetryConnectorError("connector_job_too_large", kind=ConnectorFailureKind.BUDGET)
        try:
            issued = int(timestamp)
        except (TypeError, ValueError):
            raise TelemetryConnectorError("connector_authority_invalid", kind=ConnectorFailureKind.CONFIGURATION) from None
        now = int(time.time())
        if abs(now - issued) > MAX_CLOCK_SKEW_SECONDS:
            raise TelemetryConnectorError("connector_authority_expired", kind=ConnectorFailureKind.CONFIGURATION)
        key = _secret_key(self.secret_store._client, self.auth_secret_arn)
        expected = hmac.new(key, timestamp.encode() + b"\n" + raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(signature)):
            raise TelemetryConnectorError("connector_authority_invalid", kind=ConnectorFailureKind.CONFIGURATION)
        try:
            job = json.loads(raw_body)
        except (UnicodeDecodeError, ValueError):
            raise TelemetryConnectorError("connector_job_invalid", kind=ConnectorFailureKind.CONFIGURATION) from None
        self._validate_authority(job)
        identity = job["request_identity"]
        digest = hashlib.sha256(raw_body).hexdigest()
        try:
            with sqlite3.connect(self._db_path, timeout=5) as db:
                db.execute("DELETE FROM used_jobs WHERE created_at < ?", (now - 86_400,))
                db.execute("INSERT INTO used_jobs(request_identity,digest,created_at) VALUES(?,?,?)", (identity,digest,now))
        except sqlite3.IntegrityError:
            raise TelemetryConnectorError("connector_job_replayed", kind=ConnectorFailureKind.CONFIGURATION) from None
        except sqlite3.Error:
            raise TelemetryConnectorError("connector_replay_store_unavailable", kind=ConnectorFailureKind.NETWORK, retryable=True) from None
        binding, secret = self._load_secret(job)
        request = {key: value for key, value in job.items() if key not in {"version", "request_identity", "created_at", "approved_destination"}}
        request["secret_values"] = getattr(secret, "_values", {}) if secret else None
        result = _execute_unprivileged(request, secret=secret)
        return {"request_identity": identity, "result": result}

    @staticmethod
    def _validate_authority(job: Any) -> None:
        if not isinstance(job, dict) or job.get("version") != EXECUTOR_VERSION:
            raise TelemetryConnectorError("connector_authority_invalid", kind=ConnectorFailureKind.CONFIGURATION)
        try:
            uuid.UUID(job["request_identity"])
            created = _datetime(job["created_at"])
        except (KeyError, TypeError, ValueError):
            raise TelemetryConnectorError("connector_authority_invalid", kind=ConnectorFailureKind.CONFIGURATION) from None
        if created is None or abs((datetime.now(UTC) - created).total_seconds()) > MAX_CLOCK_SKEW_SECONDS:
            raise TelemetryConnectorError("connector_authority_expired", kind=ConnectorFailureKind.CONFIGURATION)
        for field in ("tenant_scope_id", "workspace_id", "facility_id", "resource_scope_id", "connection_id"):
            value = job.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise TelemetryConnectorError("connector_authority_invalid", kind=ConnectorFailureKind.CONFIGURATION)
        if job.get("connector_type") != ConnectorType.HTTPS_TELEMETRY.value:
            raise TelemetryConnectorError("connector_type_not_allowed", kind=ConnectorFailureKind.CONFIGURATION)
        if job.get("operation") not in {"validate", "health", "discovery", "incremental", "backfill"}:
            raise TelemetryConnectorError("connector_operation_not_allowed", kind=ConnectorFailureKind.CONFIGURATION)
        configuration = job.get("configuration")
        if not isinstance(configuration, dict):
            raise TelemetryConnectorError("connector_configuration_invalid", kind=ConnectorFailureKind.CONFIGURATION)
        try:
            normalized = TelemetryEgressPolicy().normalize_url(str(configuration.get("base_url") or ""))
            parts = urlsplit(normalized)
        except TelemetryEgressError as error:
            raise TelemetryConnectorError(error.code, kind=ConnectorFailureKind.CONFIGURATION,
                safe_message="Telemetry destination is not allowed.") from None
        expected_destination = f"https://{APPROVED_HOST}:443"
        if parts.hostname != APPROVED_HOST or job.get("approved_destination") != expected_destination:
            raise TelemetryConnectorError("unapproved_destination", kind=ConnectorFailureKind.CONFIGURATION)
        credential = job.get("credential")
        if credential is not None:
            if not isinstance(credential, dict) or (
                credential.get("connection_id") != job["connection_id"]
                or credential.get("resource_scope_id") != job["resource_scope_id"]
                or not credential.get("reference") or not credential.get("binding_id")
                or not credential.get("version_marker")
            ):
                raise TelemetryConnectorError("credential_binding_mismatch", kind=ConnectorFailureKind.CONFIGURATION)

    def _load_secret(self, job: Mapping[str, Any]) -> tuple[SecretBinding | None, ResolvedSecret | None]:
        credential = job.get("credential")
        if credential is None:
            return None, None
        try:
            binding = SecretBinding(
                binding_id=credential["binding_id"], provider=credential["provider"],
                resource_scope_id=job["resource_scope_id"], connection_id=job["connection_id"],
                internal_reference=credential["reference"],
                version_marker=credential["version_marker"], updated_at=None,
            )
            resolved = self.secret_store.resolve(binding)
        except Exception:
            raise TelemetryConnectorError("credential_binding_mismatch", kind=ConnectorFailureKind.CONFIGURATION,
                safe_message="Telemetry credentials are unavailable.") from None
        return binding, resolved


def build_executor_app():
    """Create the isolated service ASGI app; no telemetry DB or migrations."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import boto3

    region = os.environ.get("AWS_REGION", "us-east-2")
    auth_secret_arn = os.environ["NERAIUM_CONNECTOR_EXECUTOR_AUTH_SECRET_ARN"]
    store = AwsSecretsManagerTelemetryStore(
        client=boto3.client("secretsmanager", region_name=region),
        environment="prod", dynamic_writes_enabled=False,
    )
    broker = ConnectorExecutionBroker(
        secret_store=store, auth_secret_arn=auth_secret_arn,
        replay_db_path=os.environ.get("NERAIUM_CONNECTOR_EXECUTOR_REPLAY_DB", "/var/lib/neraium-connector/replay.sqlite3"),
    )
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "healthy", "version": EXECUTOR_VERSION}

    @app.post("/v1/connector-jobs")
    async def execute(request: Request):
        body = await request.body()
        try:
            result = broker.execute(body,
                timestamp=request.headers.get("x-neraium-timestamp", ""),
                signature=request.headers.get("x-neraium-signature", ""))
            content = _canonical_json(result)
            if len(content) > MAX_RESULT_BYTES:
                return JSONResponse({"code": "connector_result_too_large"}, status_code=413)
            return JSONResponse(result)
        except TelemetryConnectorError as error:
            return JSONResponse({"code": error.code, "kind": error.kind.value,
                                 "retryable": error.retryable}, status_code=403 if error.kind is ConnectorFailureKind.CONFIGURATION else 502)
        except Exception:
            logger.error("connector_executor_internal_failure", extra={"event": "connector_executor_internal_failure"})
            return JSONResponse({"code": "connector_execution_failed", "kind": "network", "retryable": True}, status_code=502)
    return app
