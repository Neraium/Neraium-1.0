from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import json
from types import MappingProxyType
from typing import Any, Mapping

from app.connectors.models import ConnectorHealthStatus, NormalizedConnectorBatch
from app.services.telemetry_domain import (
    ConnectorCapability,
    ConnectorType,
    reject_sensitive_telemetry_fields,
)
from app.services.telemetry_secrets import SecretBinding


class ConnectorBase(ABC):
    """Compatibility contract for the historical/manual connector workflow.

    Continuous production telemetry uses :class:`TelemetryConnector` below.
    Keeping these contracts separate prevents the legacy normalization path
    from becoming an accidental authority for canonical observations.
    """

    connector_type = "base"
    display_name = "Base Connector"
    functional = False

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    def connect(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def validate_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_historical(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def stream_latest(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_data: list[dict[str, Any]]) -> NormalizedConnectorBatch:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> ConnectorHealthStatus:
        raise NotImplementedError


class ConnectorOperation(StrEnum):
    VALIDATE = "validate"
    DISCOVERY = "discovery"
    INCREMENTAL = "incremental"
    BACKFILL = "backfill"
    HEALTH = "health"


class ConnectorFailureKind(StrEnum):
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    RATE_LIMITED = "rate_limited"
    PROVIDER = "provider"
    PAYLOAD = "payload"
    BUDGET = "budget"
    NOT_CONFIGURED = "not_configured"


class TelemetryConnectorError(RuntimeError):
    """Stable provider failure safe for API responses, logs, and run records."""

    def __init__(
        self,
        code: str,
        *,
        kind: ConnectorFailureKind = ConnectorFailureKind.PROVIDER,
        retryable: bool = False,
        safe_message: str = "Telemetry retrieval failed.",
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.code = str(code)
        self.kind = ConnectorFailureKind(kind)
        self.retryable = bool(retryable)
        self.safe_message = str(safe_message)
        self.retry_after_seconds = retry_after_seconds


def _frozen_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(
        {str(key): _frozen_value(item) for key, item in (value or {}).items()}
    )


def _frozen_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _frozen_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_frozen_value(item) for item in value)
    return value


def _validate_source_metadata(value: Mapping[str, Any], *, path: str) -> None:
    try:
        reject_sensitive_telemetry_fields(
            value,
            code="source_metadata_credential_field_forbidden",
            path=path,
        )
        encoded = json.dumps(dict(value), default=str).encode("utf-8")
    except ValueError:
        raise ValueError("source_metadata_invalid") from None
    if len(encoded) > 16 * 1024:
        raise ValueError("source_metadata_too_large")


@dataclass(frozen=True, slots=True)
class ConnectorProviderDescriptor:
    connector_type: ConnectorType
    display_name: str
    description: str
    capabilities: frozenset[ConnectorCapability]
    production_available: bool
    retrieval_only: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "connector_type", ConnectorType(self.connector_type))
        object.__setattr__(
            self,
            "capabilities",
            frozenset(ConnectorCapability(item) for item in self.capabilities),
        )
        if not self.retrieval_only:
            raise ValueError("telemetry_connectors_must_be_retrieval_only")
        required = {ConnectorCapability.VALIDATE, ConnectorCapability.HEALTH_CHECK}
        if not required.issubset(self.capabilities):
            raise ValueError("connector_descriptor_missing_required_capability")


@dataclass(frozen=True, slots=True)
class ConnectorExecutionContext:
    """Server-owned connection context; source payloads cannot change scope."""

    connection_id: str
    resource_scope_id: str
    configuration: Mapping[str, Any]
    secret_binding: SecretBinding | None = None

    def __post_init__(self) -> None:
        if not str(self.connection_id or "").strip():
            raise ValueError("connection_id_required")
        if not str(self.resource_scope_id or "").strip():
            raise ValueError("resource_scope_id_required")
        if self.secret_binding is not None:
            if self.secret_binding.connection_id != self.connection_id:
                raise ValueError("secret_binding_connection_mismatch")
            if self.secret_binding.resource_scope_id != self.resource_scope_id:
                raise ValueError("secret_binding_scope_mismatch")
        object.__setattr__(self, "configuration", _frozen_mapping(self.configuration))


@dataclass(frozen=True, slots=True)
class ConnectorCheckpoint:
    cursor: str | None = None
    high_water_at: datetime | None = None

    def __post_init__(self) -> None:
        cursor = str(self.cursor).strip() if self.cursor is not None else None
        if cursor is not None and (not cursor or len(cursor) > 2_048):
            raise ValueError("checkpoint_cursor_invalid")
        if self.high_water_at is not None:
            if self.high_water_at.tzinfo is None or self.high_water_at.utcoffset() is None:
                raise ValueError("checkpoint_high_water_must_be_aware")
            object.__setattr__(self, "high_water_at", self.high_water_at.astimezone(UTC))
        object.__setattr__(self, "cursor", cursor)


@dataclass(frozen=True, slots=True)
class BoundedBackfillRange:
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        for value in (self.start_at, self.end_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("backfill_bounds_must_be_aware")
        start = self.start_at.astimezone(UTC)
        end = self.end_at.astimezone(UTC)
        if start >= end:
            raise ValueError("backfill_range_invalid")
        object.__setattr__(self, "start_at", start)
        object.__setattr__(self, "end_at", end)


@dataclass(frozen=True, slots=True)
class RawObservationEnvelope:
    """Source-neutral raw input; hierarchy is resolved by signal mappings."""

    external_tag_id: str
    external_tag_name: str
    source_timestamp: Any
    raw_value: Any
    reported_unit: str | None = None
    reported_quality: str | None = None
    provider_event_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        tag_id = str(self.external_tag_id or "").strip()
        tag_name = str(self.external_tag_name or "").strip()
        if not tag_id or len(tag_id) > 512 or not tag_name or len(tag_name) > 512:
            raise ValueError("external_tag_identifier_invalid")
        if self.reported_unit is not None and len(str(self.reported_unit)) > 128:
            raise ValueError("reported_unit_invalid")
        if self.reported_quality is not None and len(str(self.reported_quality)) > 128:
            raise ValueError("reported_quality_invalid")
        if self.provider_event_id is not None and len(str(self.provider_event_id)) > 512:
            raise ValueError("provider_event_id_invalid")
        if len(self.metadata) > 32:
            raise ValueError("observation_metadata_too_large")
        _validate_source_metadata(self.metadata, path="observation_metadata")
        object.__setattr__(self, "external_tag_id", tag_id)
        object.__setattr__(self, "external_tag_name", tag_name)
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class DiscoveredSignal:
    external_tag_id: str
    external_tag_name: str
    display_label: str | None = None
    reported_unit: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.external_tag_id or "").strip():
            raise ValueError("external_tag_id_required")
        if not str(self.external_tag_name or "").strip():
            raise ValueError("external_tag_name_required")
        _validate_source_metadata(self.metadata, path="signal_metadata")
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class ConnectorRecordIssue:
    record_index: int
    code: str
    safe_message: str = "Telemetry source returned an invalid record."

    def __post_init__(self) -> None:
        if self.record_index < 0:
            raise ValueError("connector_record_index_invalid")
        if not str(self.code or "").strip() or len(self.code) > 128:
            raise ValueError("connector_record_issue_code_invalid")


@dataclass(frozen=True, slots=True)
class ConnectorPage:
    observations: tuple[RawObservationEnvelope, ...] = ()
    signals: tuple[DiscoveredSignal, ...] = ()
    issues: tuple[ConnectorRecordIssue, ...] = ()
    next_checkpoint: ConnectorCheckpoint | None = None
    has_more: bool = False
    pages_read: int = 0
    response_bytes: int = 0
    retry_count: int = 0


@dataclass(frozen=True, slots=True)
class ConnectorValidationResult:
    valid: bool
    reachable: bool
    authenticated: bool
    observations_sampled: int = 0
    code: str = "validated"


@dataclass(frozen=True, slots=True)
class ProviderHealthResult:
    reachable: bool
    authenticated: bool
    provider_healthy: bool
    checked_at: datetime
    code: str

    def __post_init__(self) -> None:
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("health_timestamp_must_be_aware")


class TelemetryConnector(ABC):
    """Capability-driven production retrieval contract.

    Deliberately absent: write, execute, command, publish, acknowledge, or
    control primitives. Provider output contains source facts only and cannot
    select Neraium hierarchy or analysis authority.
    """

    @classmethod
    @abstractmethod
    def descriptor(cls) -> ConnectorProviderDescriptor:
        raise NotImplementedError

    @abstractmethod
    def validate(self, context: ConnectorExecutionContext) -> ConnectorValidationResult:
        raise NotImplementedError

    @abstractmethod
    def discover_signals(
        self,
        context: ConnectorExecutionContext,
        *,
        checkpoint: ConnectorCheckpoint | None = None,
    ) -> ConnectorPage:
        raise NotImplementedError

    @abstractmethod
    def fetch_incremental(
        self,
        context: ConnectorExecutionContext,
        *,
        checkpoint: ConnectorCheckpoint | None = None,
    ) -> ConnectorPage:
        raise NotImplementedError

    @abstractmethod
    def fetch_backfill(
        self,
        context: ConnectorExecutionContext,
        *,
        time_range: BoundedBackfillRange,
        checkpoint: ConnectorCheckpoint | None = None,
    ) -> ConnectorPage:
        raise NotImplementedError

    @abstractmethod
    def health(self, context: ConnectorExecutionContext) -> ProviderHealthResult:
        raise NotImplementedError
