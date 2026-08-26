from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
import re
from types import MappingProxyType
from typing import Any

from app.engine.sii.behavioral_model_contract import (
    canonical_phase4_resource_scope_id,
)


TELEMETRY_DOMAIN_VERSION = "telemetry-domain.v1"


class ConnectionLifecycleStatus(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    DISABLED = "disabled"
    ERROR = "error"
    ARCHIVED = "archived"


class ConnectorCapability(StrEnum):
    VALIDATE = "validate"
    DISCOVER_SIGNALS = "discover_signals"
    INCREMENTAL_POLLING = "incremental_polling"
    BOUNDED_BACKFILL = "bounded_backfill"
    HEALTH_CHECK = "health_check"
    READ_EVENTS = "read_events"


class ConnectorType(StrEnum):
    """Production connector providers accepted by persistence and APIs."""

    HTTPS_TELEMETRY = "https_telemetry"
    HISTORIAN_TEMPLATE = "historian_template"


class CheckpointMode(StrEnum):
    """Cursor namespaces that may be persisted for a connection."""

    DISCOVERY = "discovery"
    INCREMENTAL = "incremental"
    BACKFILL = "backfill"


class SignalMappingStatus(StrEnum):
    UNMAPPED = "unmapped"
    MAPPED = "mapped"
    INVALID = "invalid"
    DISABLED = "disabled"


class TelemetryQualityState(StrEnum):
    GOOD = "good"
    STALE = "stale"
    MISSING = "missing"
    INVALID_VALUE = "invalid_value"
    UNIT_UNRESOLVED = "unit_unresolved"
    TIMESTAMP_INVALID = "timestamp_invalid"
    MAPPING_REQUIRED = "mapping_required"
    FORMAT_INVALID = "format_invalid"


class IngestionDisposition(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER_ACCEPTED = "out_of_order_accepted"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


class AnalysisIneligibilityReason(StrEnum):
    MAPPING_NOT_APPROVED = "mapping_not_approved"
    SIGNAL_DISABLED = "signal_disabled"
    UNIT_UNRESOLVED = "unit_unresolved"
    TIMESTAMP_INVALID = "timestamp_invalid"
    QUALITY_INELIGIBLE = "quality_ineligible"
    TELEMETRY_STALE = "telemetry_stale"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    AUTHORITY_UNAVAILABLE = "authority_unavailable"


class IngestionRunMode(StrEnum):
    VALIDATION = "validation"
    DISCOVERY = "discovery"
    INCREMENTAL = "incremental"
    BACKFILL = "backfill"
    RETRY = "retry"


class IngestionRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HealthFacetStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class ConnectionHealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    UNKNOWN = "unknown"


class TelemetryAuditAction(StrEnum):
    CONNECTION_CREATED = "connection_created"
    CONNECTION_UPDATED = "connection_updated"
    CREDENTIAL_BINDING_CHANGED = "credential_binding_changed"
    VALIDATION_COMPLETED = "validation_completed"
    SIGNAL_MAPPING_CHANGED = "signal_mapping_changed"
    CONNECTION_ENABLED = "connection_enabled"
    CONNECTION_DISABLED = "connection_disabled"
    CONNECTION_ARCHIVED = "connection_archived"
    BACKFILL_STARTED = "backfill_started"
    BACKFILL_COMPLETED = "backfill_completed"
    BACKFILL_FAILED = "backfill_failed"
    INGESTION_RETRY_REQUESTED = "ingestion_retry_requested"


LIFECYCLE_TRANSITIONS: Mapping[
    ConnectionLifecycleStatus, frozenset[ConnectionLifecycleStatus]
] = MappingProxyType(
    {
        ConnectionLifecycleStatus.DRAFT: frozenset(
            {ConnectionLifecycleStatus.VALIDATING}
        ),
        ConnectionLifecycleStatus.VALIDATING: frozenset(
            {
                ConnectionLifecycleStatus.CONNECTED,
                ConnectionLifecycleStatus.DEGRADED,
                ConnectionLifecycleStatus.DISCONNECTED,
                ConnectionLifecycleStatus.ERROR,
            }
        ),
        ConnectionLifecycleStatus.CONNECTED: frozenset(
            {
                ConnectionLifecycleStatus.DEGRADED,
                ConnectionLifecycleStatus.DISCONNECTED,
                ConnectionLifecycleStatus.DISABLED,
                ConnectionLifecycleStatus.ARCHIVED,
            }
        ),
        ConnectionLifecycleStatus.DEGRADED: frozenset(
            {
                ConnectionLifecycleStatus.CONNECTED,
                ConnectionLifecycleStatus.DISCONNECTED,
                ConnectionLifecycleStatus.DISABLED,
                ConnectionLifecycleStatus.ERROR,
                ConnectionLifecycleStatus.ARCHIVED,
            }
        ),
        ConnectionLifecycleStatus.DISCONNECTED: frozenset(
            {
                ConnectionLifecycleStatus.VALIDATING,
                ConnectionLifecycleStatus.CONNECTED,
                ConnectionLifecycleStatus.DISABLED,
                ConnectionLifecycleStatus.ARCHIVED,
            }
        ),
        ConnectionLifecycleStatus.DISABLED: frozenset(
            {
                ConnectionLifecycleStatus.DISCONNECTED,
                ConnectionLifecycleStatus.ARCHIVED,
            }
        ),
        ConnectionLifecycleStatus.ERROR: frozenset(
            {
                ConnectionLifecycleStatus.VALIDATING,
                ConnectionLifecycleStatus.CONNECTED,
                ConnectionLifecycleStatus.DISABLED,
                ConnectionLifecycleStatus.ARCHIVED,
            }
        ),
        ConnectionLifecycleStatus.ARCHIVED: frozenset(),
    }
)


class InvalidLifecycleTransition(ValueError):
    """Raised when an ordinary API attempts an invalid lifecycle change."""


def can_transition_connection(
    current: ConnectionLifecycleStatus | str,
    target: ConnectionLifecycleStatus | str,
) -> bool:
    try:
        current_status = ConnectionLifecycleStatus(current)
        target_status = ConnectionLifecycleStatus(target)
    except ValueError:
        return False
    return target_status in LIFECYCLE_TRANSITIONS[current_status]


def require_connection_transition(
    current: ConnectionLifecycleStatus | str,
    target: ConnectionLifecycleStatus | str,
) -> ConnectionLifecycleStatus:
    try:
        current_status = ConnectionLifecycleStatus(current)
        target_status = ConnectionLifecycleStatus(target)
    except ValueError as error:
        raise InvalidLifecycleTransition("invalid_connection_lifecycle_status") from error
    if target_status not in LIFECYCLE_TRANSITIONS[current_status]:
        raise InvalidLifecycleTransition(
            f"invalid_connection_lifecycle_transition:{current_status.value}:{target_status.value}"
        )
    return target_status


_SENSITIVE_TELEMETRY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "api_token",
        "auth_token",
        "authorization",
        "bearer_token",
        "client_secret",
        "clientsecret",
        "credential",
        "credentials",
        "dsn",
        "internal_reference",
        "password",
        "secret",
        "secret_arn",
        "secret_binding_id",
        "secret_ref",
        "secret_reference",
        "token",
        "x_api_key",
    }
)

_SENSITIVE_TELEMETRY_KEY_PATTERN = re.compile(
    r"(?:^|_)(?:"
    r"authorization|credentials?|dsn|password|passwd|private_key|"
    r"secret(?:_arn|_binding_id|_ref(?:erence)?)?|internal_reference|"
    r"(?:access|api|auth|bearer|refresh)_token|api_key|x_api_key|token"
    r")(?:$|_)"
)


def _normalized_key(value: Any) -> str:
    raw = str(value or "").strip()
    # Normalize camelCase as well as header- and JSON-style separators so
    # clientSecret, X-API-Key, and x_api_key share one policy path.
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw)
    return re.sub(r"[^a-z0-9]+", "_", snake.lower()).strip("_")


def is_sensitive_telemetry_key(value: Any) -> bool:
    """Return whether a JSON key is shaped like credential material."""

    key = _normalized_key(value)
    compact = key.replace("_", "")
    return (
        key in _SENSITIVE_TELEMETRY_KEYS
        or compact in {"clientsecret", "internalreference", "secretref"}
        or _SENSITIVE_TELEMETRY_KEY_PATTERN.search(key) is not None
    )


def reject_sensitive_telemetry_fields(
    value: Any,
    *,
    code: str,
    path: str = "telemetry_json",
) -> None:
    """Reject credential-shaped keys at any depth before persistence."""

    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            if is_sensitive_telemetry_key(key):
                raise ValueError(f"{code}:{path}.{key}")
            reject_sensitive_telemetry_fields(
                item,
                code=code,
                path=f"{path}.{key}",
            )
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            reject_sensitive_telemetry_fields(
                item,
                code=code,
                path=f"{path}[{index}]",
            )


def sanitize_telemetry_public_value(value: Any) -> Any:
    """Recursively drop credential-shaped keys from a public JSON value."""

    if isinstance(value, Mapping):
        return {
            str(key): sanitize_telemetry_public_value(item)
            for key, item in value.items()
            if not is_sensitive_telemetry_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_telemetry_public_value(item) for item in value]
    return value


def _freeze_public_value(value: Any, *, path: str) -> Any:
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if is_sensitive_telemetry_key(key):
                raise ValueError(f"sensitive_public_field_forbidden:{path}.{key}")
            frozen[key] = _freeze_public_value(raw_value, path=f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_public_value(item, path=f"{path}[]") for item in value
        )
    if isinstance(value, (str, int, float, bool, type(None), datetime, StrEnum)):
        return value
    raise TypeError(f"unsupported_public_value:{path}")


def _public_value(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("public_datetime_must_be_timezone_aware")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, PublicTelemetryRecord):
        return value.as_public_dict()
    if isinstance(value, Mapping):
        return {str(key): _public_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_public_value(item) for item in value]
    return value


def _required_text(instance: Any, *field_names: str) -> None:
    for field_name in field_names:
        value = str(getattr(instance, field_name) or "").strip()
        if not value:
            raise ValueError(f"telemetry_domain_missing:{field_name}")
        object.__setattr__(instance, field_name, value)


def _optional_text(instance: Any, *field_names: str) -> None:
    for field_name in field_names:
        value = getattr(instance, field_name)
        object.__setattr__(instance, field_name, str(value).strip() if value is not None else None)


def _aware_datetimes(instance: Any, *field_names: str) -> None:
    for field_name in field_names:
        value = getattr(instance, field_name)
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError(f"telemetry_domain_datetime_must_be_aware:{field_name}")


class PublicTelemetryRecord:
    """Mixin for immutable API-safe telemetry projections.

    Internal secret binding identifiers deliberately have no field in these
    records. Nested public metadata is frozen and rejects credential-shaped
    keys before it can reach a router response or audit event.
    """

    def as_public_dict(self) -> dict[str, Any]:
        return {
            field.name: _public_value(getattr(self, field.name))
            for field in fields(self)
        }

    def as_dict(self) -> dict[str, Any]:
        return self.as_public_dict()


@dataclass(frozen=True, slots=True)
class TelemetryScopeRef(PublicTelemetryRecord):
    tenant_scope_id: str
    workspace_id: str
    resource_scope_id: str
    facility_id: str

    def __post_init__(self) -> None:
        _required_text(
            self,
            "tenant_scope_id",
            "workspace_id",
            "resource_scope_id",
            "facility_id",
        )
        expected_resource_scope_id = canonical_phase4_resource_scope_id(
            self.tenant_scope_id,
            self.workspace_id,
        )
        if self.resource_scope_id != expected_resource_scope_id:
            raise ValueError("telemetry_scope_resource_mismatch")
        if self.facility_id != self.workspace_id:
            raise ValueError("telemetry_scope_facility_workspace_mismatch")


@dataclass(frozen=True, slots=True)
class AnalysisEligibility(PublicTelemetryRecord):
    eligible: bool
    reason_codes: tuple[AnalysisIneligibilityReason, ...] = ()

    def __post_init__(self) -> None:
        reasons = tuple(AnalysisIneligibilityReason(reason) for reason in self.reason_codes)
        if self.eligible and reasons:
            raise ValueError("eligible_observation_cannot_have_ineligibility_reasons")
        if not self.eligible and not reasons:
            raise ValueError("ineligible_observation_requires_reason")
        object.__setattr__(self, "reason_codes", reasons)

    @classmethod
    def allowed(cls) -> AnalysisEligibility:
        return cls(eligible=True)

    @classmethod
    def denied(
        cls, *reason_codes: AnalysisIneligibilityReason | str
    ) -> AnalysisEligibility:
        return cls(
            eligible=False,
            reason_codes=tuple(AnalysisIneligibilityReason(reason) for reason in reason_codes),
        )


@dataclass(frozen=True, slots=True)
class DataConnectionRecord(PublicTelemetryRecord):
    connection_id: str
    scope: TelemetryScopeRef
    name: str
    connector_type: ConnectorType
    lifecycle_status: ConnectionLifecycleStatus = ConnectionLifecycleStatus.DRAFT
    enabled: bool = False
    safe_configuration: Mapping[str, Any] = MappingProxyType({})
    timezone: str = "UTC"
    polling_interval_seconds: int = 300
    capabilities: tuple[ConnectorCapability, ...] = ()
    credentials_configured: bool = False
    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_telemetry_at: datetime | None = None
    last_error_code: str | None = None
    last_error_summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _required_text(self, "connection_id", "name", "connector_type", "timezone")
        _optional_text(self, "last_error_code", "last_error_summary")
        if self.polling_interval_seconds <= 0:
            raise ValueError("polling_interval_seconds_must_be_positive")
        _aware_datetimes(
            self,
            "last_success_at",
            "last_attempt_at",
            "last_telemetry_at",
            "created_at",
            "updated_at",
        )
        object.__setattr__(
            self,
            "lifecycle_status",
            ConnectionLifecycleStatus(self.lifecycle_status),
        )
        object.__setattr__(self, "connector_type", ConnectorType(self.connector_type))
        object.__setattr__(
            self,
            "capabilities",
            tuple(ConnectorCapability(item) for item in self.capabilities),
        )
        object.__setattr__(
            self,
            "safe_configuration",
            _freeze_public_value(self.safe_configuration, path="safe_configuration"),
        )


@dataclass(frozen=True, slots=True)
class ExternalSignalRecord(PublicTelemetryRecord):
    signal_id: str
    scope: TelemetryScopeRef
    connection_id: str
    external_tag_id: str
    external_tag_name: str
    display_label: str | None = None
    canonical_signal_id: str | None = None
    canonical_signal_name: str | None = None
    system_id: str | None = None
    asset_id: str | None = None
    source_unit: str | None = None
    sample_cadence_seconds: float | None = None
    # Discovery never opts a source tag into ingestion or analysis. An
    # authorized mapping/enable action must make that decision explicitly.
    enabled: bool = False
    mapping_status: SignalMappingStatus = SignalMappingStatus.UNMAPPED
    last_observed_at: datetime | None = None
    quality_state: TelemetryQualityState = TelemetryQualityState.MAPPING_REQUIRED
    metadata: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        _required_text(
            self,
            "signal_id",
            "connection_id",
            "external_tag_id",
            "external_tag_name",
        )
        _optional_text(
            self,
            "display_label",
            "canonical_signal_id",
            "canonical_signal_name",
            "system_id",
            "asset_id",
            "source_unit",
        )
        if self.sample_cadence_seconds is not None and self.sample_cadence_seconds <= 0:
            raise ValueError("sample_cadence_seconds_must_be_positive")
        _aware_datetimes(self, "last_observed_at")
        object.__setattr__(self, "mapping_status", SignalMappingStatus(self.mapping_status))
        object.__setattr__(self, "quality_state", TelemetryQualityState(self.quality_state))
        object.__setattr__(
            self, "metadata", _freeze_public_value(self.metadata, path="signal_metadata")
        )


@dataclass(frozen=True, slots=True)
class SignalMappingRecord(PublicTelemetryRecord):
    mapping_id: str
    scope: TelemetryScopeRef
    connection_id: str
    signal_id: str
    facility_id: str
    system_id: str
    canonical_signal_id: str
    canonical_signal_name: str
    source_unit: str
    canonical_unit: str
    conversion_id: str
    conversion_version: str
    source_timezone: str
    expected_cadence_seconds: float | None
    actor_id: str
    mapped_at: datetime
    revision: int
    asset_id: str | None = None
    reason: str | None = None
    enabled: bool = True
    provenance: str = "manual"

    def __post_init__(self) -> None:
        _required_text(
            self,
            "mapping_id",
            "connection_id",
            "signal_id",
            "facility_id",
            "system_id",
            "canonical_signal_id",
            "canonical_signal_name",
            "source_unit",
            "canonical_unit",
            "conversion_id",
            "conversion_version",
            "source_timezone",
            "actor_id",
            "provenance",
        )
        _optional_text(self, "asset_id", "reason")
        if self.facility_id != self.scope.facility_id:
            raise ValueError("mapping_facility_scope_mismatch")
        if self.expected_cadence_seconds is not None and self.expected_cadence_seconds <= 0:
            raise ValueError("expected_cadence_seconds_must_be_positive")
        if self.revision < 1:
            raise ValueError("mapping_revision_must_be_positive")
        _aware_datetimes(self, "mapped_at")


@dataclass(frozen=True, slots=True)
class IngestionRunRecord(PublicTelemetryRecord):
    run_id: str
    scope: TelemetryScopeRef
    connection_id: str
    mode: IngestionRunMode
    status: IngestionRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    attempt_count: int = 0
    retry_count: int = 0
    pages: int = 0
    observations_received: int = 0
    observations_accepted: int = 0
    observations_rejected: int = 0
    observations_duplicate: int = 0
    observations_out_of_order: int = 0
    latency_ms: int | None = None
    error_code: str | None = None
    error_summary: str | None = None
    actor_id: str | None = None

    def __post_init__(self) -> None:
        _required_text(self, "run_id", "connection_id")
        _optional_text(self, "error_code", "error_summary", "actor_id")
        object.__setattr__(self, "mode", IngestionRunMode(self.mode))
        object.__setattr__(self, "status", IngestionRunStatus(self.status))
        counters = (
            self.attempt_count,
            self.retry_count,
            self.pages,
            self.observations_received,
            self.observations_accepted,
            self.observations_rejected,
            self.observations_duplicate,
            self.observations_out_of_order,
        )
        if any(value < 0 for value in counters):
            raise ValueError("ingestion_run_counters_must_be_non_negative")
        _aware_datetimes(self, "started_at", "finished_at")


@dataclass(frozen=True, slots=True)
class HealthFacet(PublicTelemetryRecord):
    status: HealthFacetStatus
    observed_at: datetime | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", HealthFacetStatus(self.status))
        _optional_text(self, "reason_code")
        _aware_datetimes(self, "observed_at")


@dataclass(frozen=True, slots=True)
class ConnectionHealthRecord(PublicTelemetryRecord):
    connection_id: str
    scope: TelemetryScopeRef
    aggregate_state: ConnectionHealthState
    reachability: HealthFacet
    authentication: HealthFacet
    telemetry_freshness: HealthFacet
    mapping_completeness: HealthFacet
    data_quality: HealthFacet
    worker_checkpoint: HealthFacet
    last_healthy_at: datetime | None = None
    mapped_signal_count: int = 0
    healthy_signal_count: int = 0
    stale_signal_count: int = 0

    def __post_init__(self) -> None:
        _required_text(self, "connection_id")
        object.__setattr__(
            self, "aggregate_state", ConnectionHealthState(self.aggregate_state)
        )
        if min(
            self.mapped_signal_count,
            self.healthy_signal_count,
            self.stale_signal_count,
        ) < 0:
            raise ValueError("health_signal_counts_must_be_non_negative")
        _aware_datetimes(self, "last_healthy_at")


@dataclass(frozen=True, slots=True)
class TelemetryAuditEventRecord(PublicTelemetryRecord):
    event_id: str
    scope: TelemetryScopeRef
    connection_id: str
    actor_id: str
    action: TelemetryAuditAction
    occurred_at: datetime
    before_digest: str | None = None
    after_digest: str | None = None
    detail: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        _required_text(self, "event_id", "connection_id", "actor_id")
        _optional_text(self, "before_digest", "after_digest")
        object.__setattr__(self, "action", TelemetryAuditAction(self.action))
        object.__setattr__(
            self,
            "detail",
            _freeze_public_value(self.detail, path="audit_detail"),
        )
        _aware_datetimes(self, "occurred_at")


# Short aliases keep repository/provider type annotations readable while the
# longer names make public-response intent explicit at API boundaries.
ConnectionRecord = DataConnectionRecord
SignalRecord = ExternalSignalRecord
MappingRecord = SignalMappingRecord
RunRecord = IngestionRunRecord
HealthRecord = ConnectionHealthRecord
AuditRecord = TelemetryAuditEventRecord
