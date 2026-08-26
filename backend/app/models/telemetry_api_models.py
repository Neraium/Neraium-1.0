"""Strict public contracts for facility-scoped production telemetry connections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.services.telemetry_domain import (
    ConnectorCapability,
    ConnectorType,
    reject_sensitive_telemetry_fields,
    sanitize_telemetry_public_value,
)


_HTTPS_CONFIG_KEYS = frozenset(
    {
        "base_url", "request_path", "static_query", "authentication_scheme",
        "records_path", "timestamp_field", "value_field", "external_tag_id_field",
        "external_tag_name_field", "display_label_field", "unit_field", "quality_field",
        "event_id_field", "metadata_fields", "next_cursor_path", "cursor_query_parameter",
        "next_page_path", "page_size_query_parameter", "page_size",
        "start_time_query_parameter", "end_time_query_parameter", "timeout_seconds",
        "max_response_bytes", "max_pages", "max_records", "max_retries",
        "max_retry_after_seconds",
    }
)
_HISTORIAN_CONFIG_KEYS = frozenset({"template_id", "network_profile_id", "parameters"})


class TelemetryApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _validate_safe_configuration(
    connector_type: ConnectorType, configuration: dict[str, Any]
) -> dict[str, Any]:
    reject_sensitive_telemetry_fields(
        configuration,
        code="telemetry_connection_safe_config_invalid",
        path="configuration",
    )
    allowed = (
        _HTTPS_CONFIG_KEYS
        if connector_type is ConnectorType.HTTPS_TELEMETRY
        else _HISTORIAN_CONFIG_KEYS
    )
    if set(configuration) - allowed:
        raise ValueError("Configuration contains unsupported fields.")
    if connector_type is ConnectorType.HTTPS_TELEMETRY:
        base_url = str(configuration.get("base_url") or "").strip()
        parsed = urlsplit(base_url)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("base_url must be an HTTPS origin without credentials, query, or fragment.")
        if parsed.port not in (None, 443):
            raise ValueError("base_url must use HTTPS port 443.")
        authentication_scheme = str(
            configuration.get("authentication_scheme") or "none"
        ).strip().lower()
        if authentication_scheme not in {"none", "bearer", "api_key"}:
            raise ValueError("authentication_scheme is invalid.")
        request_path = str(configuration.get("request_path") or "").strip()
        if not request_path.startswith("/") or request_path.startswith("//"):
            raise ValueError("request_path must be an origin-relative path.")
    else:
        template_id = str(configuration.get("template_id") or "").strip()
        network_profile_id = str(configuration.get("network_profile_id") or "").strip()
        if not template_id or not network_profile_id:
            raise ValueError("Server-owned historian template and network profile IDs are required.")
        parameters = configuration.get("parameters") or {}
        if not isinstance(parameters, dict) or len(parameters) > 32:
            raise ValueError("Historian parameters are invalid.")
        for key, value in parameters.items():
            lowered = str(key).lower()
            if (
                not key
                or len(key) > 128
                or any(term in lowered for term in ("sql", "query", "dsn", "database", "schema", "table", "path", "file", "url", "host", "port", "command"))
                or not isinstance(value, (str, int, float, bool))
                or len(str(value)) > 1024
            ):
                raise ValueError("Historian parameters are invalid.")
    return dict(sanitize_telemetry_public_value(configuration))


class ConnectionCreateRequest(TelemetryApiModel):
    name: str = Field(min_length=1, max_length=160)
    connector_type: ConnectorType
    configuration: dict[str, Any] = Field(default_factory=dict)
    timezone: str = Field(default="UTC", min_length=1, max_length=128)
    polling_interval_seconds: int = Field(default=300, ge=30, le=86_400)

    @model_validator(mode="after")
    def configuration_is_safe(self) -> "ConnectionCreateRequest":
        self.configuration = _validate_safe_configuration(self.connector_type, self.configuration)
        return self


class ConnectorProviderPublicResponse(TelemetryApiModel):
    connector_type: ConnectorType
    display_name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=500)
    capabilities: list[ConnectorCapability] = Field(default_factory=list)
    available: bool
    retrieval_only: Literal[True] = True
    configuration_mode: Literal["safe_https_metadata", "server_owned_template"]


class ConnectorProvidersResponse(TelemetryApiModel):
    providers: list[ConnectorProviderPublicResponse]


class ConnectionPatchRequest(TelemetryApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    configuration: dict[str, Any] | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=128)
    polling_interval_seconds: int | None = Field(default=None, ge=30, le=86_400)


class DiscoveryCheckpointRequest(TelemetryApiModel):
    """Opaque continuation token; provider cursor fields are never public API."""

    checkpoint: str | None = Field(default=None, min_length=16, max_length=4096)


class CredentialPutRequest(TelemetryApiModel):
    values: dict[str, SecretStr] = Field(min_length=1, max_length=20)

    @field_validator("values")
    @classmethod
    def validate_credential_values(cls, value: dict[str, SecretStr]) -> dict[str, SecretStr]:
        total = 0
        for key, secret in value.items():
            if not key or len(key) > 64 or not key[0].isalpha() or not all(
                character.isalnum() or character in "_.-" for character in key
            ):
                raise ValueError("Credential field names are invalid.")
            raw = secret.get_secret_value()
            if not raw or len(raw) > 16_384:
                raise ValueError("Credential values are invalid.")
            total += len(key.encode()) + len(raw.encode())
        if total > 32_768:
            raise ValueError("Credential payload is too large.")
        return value

    def unsealed_values(self) -> dict[str, str]:
        return {key: value.get_secret_value() for key, value in self.values.items()}


class SignalMappingPutRequest(TelemetryApiModel):
    system_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    asset_id: str | None = Field(default=None, min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    canonical_signal_id: UUID
    source_unit: str = Field(min_length=1, max_length=64)
    source_timezone: str = Field(default="UTC", min_length=1, max_length=128)
    expected_cadence_seconds: float | None = Field(default=None, gt=0, le=86_400)
    provenance: Literal["manual", "approved_suggestion", "imported_verified"] = "manual"
    reason: str | None = Field(default=None, max_length=1000)
    expected_revision: int | None = Field(default=None, ge=1)


class ConnectionPublicResponse(TelemetryApiModel):
    connection_id: UUID
    resource_scope_id: str
    facility_id: str
    name: str
    connector_type: ConnectorType
    lifecycle_status: str
    enabled: bool
    configuration: dict[str, Any] = Field(default_factory=dict)
    timezone: str
    polling_interval_seconds: int
    capabilities: list[str] = Field(default_factory=list)
    credentials_configured: bool = False
    credential_version: str | None = None
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_healthy_at: datetime | None = None
    last_telemetry_at: datetime | None = None
    last_error_code: str | None = None
    last_error_summary: str | None = None
    health: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConnectionsListResponse(TelemetryApiModel):
    connections: list[ConnectionPublicResponse]


class ConnectionActionResponse(TelemetryApiModel):
    connection: ConnectionPublicResponse
    message: str


class CredentialStatusResponse(TelemetryApiModel):
    credentials_configured: Literal[True]
    credential_version: str | None = None
    credentials_updated_at: datetime | None = None


class ValidationResponse(TelemetryApiModel):
    connection: ConnectionPublicResponse
    valid: bool
    reachable: bool
    authenticated: bool
    observations_sampled: int = 0
    code: str


class DiscoveryResponse(TelemetryApiModel):
    connection_id: UUID
    discovered_count: int = Field(ge=0)
    registered_count: int = Field(ge=0)
    has_more: bool = False
    checkpoint: str | None = None


MAX_TELEMETRY_BACKFILL_SPAN = timedelta(days=31)


class BackfillCreateRequest(TelemetryApiModel):
    start_at: datetime
    end_at: datetime

    @model_validator(mode="after")
    def bounds_are_bounded_utc(self) -> "BackfillCreateRequest":
        for value in (self.start_at, self.end_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Backfill bounds must be timezone-aware UTC timestamps.")
            if value.utcoffset() != timedelta(0):
                raise ValueError("Backfill bounds must use UTC.")
        self.start_at = self.start_at.astimezone(UTC)
        self.end_at = self.end_at.astimezone(UTC)
        if self.start_at >= self.end_at:
            raise ValueError("Backfill end_at must be later than start_at.")
        if self.end_at - self.start_at > MAX_TELEMETRY_BACKFILL_SPAN:
            raise ValueError("Backfill range exceeds the maximum span.")
        return self


class IngestionRunPublicResponse(TelemetryApiModel):
    run_id: UUID
    connection_id: UUID
    mode: Literal["validation", "discovery", "incremental", "backfill", "retry"]
    status: Literal["pending", "running", "succeeded", "partial", "failed", "cancelled"]
    range_start: datetime | None = None
    range_end: datetime | None = None
    started_at: datetime
    finished_at: datetime | None = None
    attempt_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    pages_processed: int = Field(default=0, ge=0)
    observations_received: int = Field(default=0, ge=0)
    observations_accepted: int = Field(default=0, ge=0)
    observations_rejected: int = Field(default=0, ge=0)
    observations_duplicate: int = Field(default=0, ge=0)
    observations_out_of_order: int = Field(default=0, ge=0)
    error_code: str | None = Field(default=None, max_length=160)
    error_summary: str | None = Field(default=None, max_length=500)
    actor_id: str | None = Field(default=None, max_length=320)


class IngestionRunsListResponse(TelemetryApiModel):
    runs: list[IngestionRunPublicResponse]


class IngestionErrorPublicResponse(TelemetryApiModel):
    error_id: UUID
    run_id: UUID
    external_signal_id: UUID | None = None
    external_tag_id: str | None = Field(default=None, max_length=512)
    quality_state: str = Field(min_length=1, max_length=160)
    reason_code: str = Field(min_length=1, max_length=160)
    disposition: Literal["duplicate", "quarantined", "rejected"]
    occurrence_count: int = Field(default=1, ge=1)
    first_seen_at: datetime
    last_seen_at: datetime


class IngestionErrorsListResponse(TelemetryApiModel):
    errors: list[IngestionErrorPublicResponse]


class IngestionRunActionResponse(TelemetryApiModel):
    run: IngestionRunPublicResponse
    message: str


class CanonicalAnalysisResultSummaryResponse(TelemetryApiModel):
    result_id: UUID
    analysis_window_id: UUID
    connection_id: UUID
    source_run_id: UUID
    facility_id: str = Field(min_length=1, max_length=512)
    system_id: str = Field(min_length=1, max_length=512)
    asset_id: str | None = Field(default=None, max_length=512)
    window_start: datetime
    window_end: datetime
    analytical_status: str = Field(min_length=1, max_length=64)
    artifact_schema_version: str = Field(min_length=1, max_length=160)
    execution_contract_version: str = Field(min_length=1, max_length=160)
    analysis_schema_version: str = Field(min_length=1, max_length=160)
    analysis_contract_version: str = Field(min_length=1, max_length=160)
    engine_name: str | None = Field(default=None, max_length=512)
    engine_version: str | None = Field(default=None, max_length=512)
    observation_count: int = Field(ge=0, le=5_000)
    observation_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    finding_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_uncompressed_bytes: int = Field(gt=0, le=268_435_456)
    payload_stored_bytes: int = Field(gt=0)
    serialization_ms: float = Field(ge=0)
    created_at: datetime | None = None


class CanonicalAnalysisResultsListResponse(TelemetryApiModel):
    results: list[CanonicalAnalysisResultSummaryResponse] = Field(max_length=200)


class CanonicalAnalysisResultResponse(CanonicalAnalysisResultSummaryResponse):
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_metadata: dict[str, Any] = Field(default_factory=dict)
    payload_encoding: Literal["zlib+canonical-json.v1"]
    projection_bytes: int = Field(ge=0, le=3_407_872)
    shared_envelope_bytes: int = Field(ge=0, le=1_048_576)
    technical_channels_bytes: int = Field(ge=0, le=2_097_152)
    evidence_audit_bytes: int = Field(ge=0, le=262_144)
    projection_serialization_ms: float = Field(ge=0)
    retrieval_ms: float = Field(ge=0)
    lineage_verified: Literal[True]
    product_result: dict[str, Any]


class CanonicalAnalysisLineageRecordResponse(TelemetryApiModel):
    contract_version: str = Field(min_length=1, max_length=160)
    observation_id: UUID
    connection_id: UUID
    ingestion_run_id: UUID
    external_signal_id: UUID
    mapping_id: UUID
    mapping_revision: int = Field(ge=1)
    canonical_signal_id: UUID
    canonical_signal_name: str = Field(min_length=1, max_length=2_048)
    system_id: str = Field(min_length=1, max_length=2_048)
    asset_id: str | None = Field(default=None, max_length=2_048)
    external_tag_id: str = Field(min_length=1, max_length=2_048)
    source_timestamp_raw: str = Field(min_length=1, max_length=2_048)
    source_timezone: str = Field(min_length=1, max_length=2_048)
    source_offset: str | None = Field(default=None, max_length=2_048)
    timestamp_normalization_version: str = Field(min_length=1, max_length=2_048)
    observed_at_utc: datetime
    original_unit: str | None = Field(default=None, max_length=2_048)
    canonical_unit: str = Field(min_length=1, max_length=2_048)
    conversion_id: str = Field(min_length=1, max_length=2_048)
    conversion_version: str = Field(min_length=1, max_length=2_048)
    source_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CanonicalAnalysisLineageResponse(TelemetryApiModel):
    result_id: UUID
    analysis_window_id: UUID
    observation_count: int = Field(ge=0, le=5_000)
    observation_lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage_verified: Literal[True]
    records: list[CanonicalAnalysisLineageRecordResponse] = Field(max_length=5_000)
    next_cursor: str | None = Field(default=None, max_length=512)


class SignalPublicResponse(TelemetryApiModel):
    signal_id: UUID
    connection_id: UUID
    external_tag_id: str
    external_tag_name: str
    display_label: str | None = None
    source_unit: str | None = None
    sample_cadence_seconds: float | None = None
    enabled: bool
    mapping_status: str
    last_observed_at: datetime | None = None
    quality_state: str | None = None
    mapping_id: UUID | None = None
    system_id: str | None = None
    asset_id: str | None = None
    canonical_signal_id: UUID | None = None
    canonical_signal_name: str | None = None
    canonical_unit: str | None = None
    conversion_id: str | None = None
    conversion_version: str | None = None
    source_timezone: str | None = None
    expected_cadence_seconds: float | None = None
    provenance: str | None = None
    mapping_revision: int | None = None


class SignalsListResponse(TelemetryApiModel):
    signals: list[SignalPublicResponse]


class CanonicalSignalConceptResponse(TelemetryApiModel):
    canonical_signal_id: UUID
    canonical_name: str
    display_name: str
    physical_dimension: str
    canonical_unit: str
    taxonomy_version: int = Field(ge=1)


class CanonicalSignalConceptsResponse(TelemetryApiModel):
    concepts: list[CanonicalSignalConceptResponse]


class MappingResponse(TelemetryApiModel):
    signal: SignalPublicResponse
    message: str


class RetiredOperationResponse(TelemetryApiModel):
    code: Literal["legacy_connection_operation_retired"]
    message: str
