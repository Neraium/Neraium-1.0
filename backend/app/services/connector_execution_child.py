"""Unprivileged child process used only for connector network operations."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import sys
from typing import Any, Mapping

from app.connectors.base import (
    BoundedBackfillRange,
    ConnectorCheckpoint,
    ConnectorExecutionContext,
    TelemetryConnectorError,
)
from app.connectors.https_telemetry import HttpsTelemetryConnector
from app.services.connector_execution import _wire
from app.services.telemetry_secrets import ResolvedSecret, SecretBinding


class _JobSecretStore:
    def __init__(self, binding: SecretBinding, secret: ResolvedSecret) -> None:
        self.binding = binding
        self.secret = secret

    def resolve(self, binding: SecretBinding, *, force_refresh: bool = False) -> ResolvedSecret:
        del force_refresh
        if (binding.binding_id, binding.connection_id, binding.resource_scope_id,
            binding.provider, binding._internal_reference) != (
            self.binding.binding_id, self.binding.connection_id,
            self.binding.resource_scope_id, self.binding.provider,
            self.binding._internal_reference):
            raise ValueError("credential_binding_mismatch")
        return self.secret

    def resolve_after_auth_failure(self, binding: SecretBinding) -> ResolvedSecret:
        return self.resolve(binding, force_refresh=True)


def _binding(raw: Mapping[str, Any], connection_id: str, scope_id: str) -> SecretBinding:
    return SecretBinding(
        binding_id=raw["binding_id"], provider=raw["provider"],
        resource_scope_id=scope_id, connection_id=connection_id,
        internal_reference=raw["reference"], version_marker=raw["version_marker"],
        updated_at=None,
    )


def execute(request: Mapping[str, Any]) -> dict[str, Any]:
    credential = request.get("credential")
    secret = None
    binding = None
    if credential is not None:
        if not isinstance(credential, Mapping) or not isinstance(request.get("secret_values"), Mapping):
            raise ValueError("credential_binding_mismatch")
        binding = _binding(credential, str(request["connection_id"]), str(request["resource_scope_id"]))
        secret = ResolvedSecret(request["secret_values"])
    context = ConnectorExecutionContext(
        connection_id=str(request["connection_id"]),
        resource_scope_id=str(request["resource_scope_id"]),
        configuration=request["configuration"],
        secret_binding=binding,
        tenant_scope_id=str(request["tenant_scope_id"]),
        workspace_id=str(request["workspace_id"]),
        facility_id=str(request["facility_id"]),
    )
    connector = HttpsTelemetryConnector(secret_store=_JobSecretStore(binding, secret) if binding and secret else None)
    operation = request["operation"]
    checkpoint_raw = request.get("checkpoint")
    checkpoint = None
    if checkpoint_raw:
        checkpoint = ConnectorCheckpoint(
            cursor=checkpoint_raw.get("cursor"),
            high_water_at=_parse_datetime(checkpoint_raw.get("high_water_at")),
        )
    if operation == "validate":
        return _wire(connector.validate(context))
    if operation == "health":
        return _wire(connector.health(context))
    if operation == "discovery":
        return _wire(connector.discover_signals(context, checkpoint=checkpoint))
    if operation == "incremental":
        return _wire(connector.fetch_incremental(context, checkpoint=checkpoint))
    if operation == "backfill":
        time_raw = request.get("time_range")
        if not isinstance(time_raw, Mapping):
            raise ValueError("backfill_range_invalid")
        time_range = BoundedBackfillRange(
            _parse_datetime(time_raw.get("start_at")),
            _parse_datetime(time_raw.get("end_at")),
        )
        return _wire(connector.fetch_backfill(context, time_range=time_range, checkpoint=checkpoint))
    raise ValueError("connector_operation_not_allowed")


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("connector_timestamp_invalid")
    return parsed.astimezone(UTC)


def main() -> int:
    try:
        request = json.load(sys.stdin)
        result = execute(request)
        sys.stdout.write(json.dumps(result, separators=(",", ":"), default=str))
        return 0
    except TelemetryConnectorError as error:
        sys.stdout.write(json.dumps({"error": {"code": error.code,
            "kind": error.kind.value, "retryable": error.retryable}}))
        return 0
    except Exception:
        sys.stdout.write(json.dumps({"error": {"code": "connector_execution_failed",
            "kind": "network", "retryable": False}}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
