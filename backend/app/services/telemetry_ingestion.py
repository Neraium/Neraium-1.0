"""Pure, source-neutral preparation of production telemetry connector pages.

This module deliberately has no repository, provider, upload, or SII dependency.
The ingestion worker loads one authoritative mapping snapshot and the existing
idempotency/order state, calls :func:`prepare_connector_page`, and persists the
returned immutable records and checkpoint in one transaction.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any

from app.connectors.base import (
    ConnectorCheckpoint,
    ConnectorPage,
    RawObservationEnvelope,
)
from app.services.telemetry_domain import (
    IngestionDisposition,
    TelemetryQualityState,
    TelemetryScopeRef,
    is_sensitive_telemetry_key,
)
from app.services.telemetry_timestamps import normalize_telemetry_timestamp
from app.services.telemetry_units import normalize_telemetry_unit


SOURCE_RECORD_DIGEST_VERSION = "neraium.telemetry.source-record/v1"
MAX_PREPARED_METADATA_BYTES = 16 * 1024
MAX_PREPARED_METADATA_KEYS = 32
MAX_PREPARED_METADATA_DEPTH = 4

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "body",
        "cookie",
        "cookies",
        "headers",
        "http_headers",
        "log",
        "logs",
        "payload",
        "query",
        "query_string",
        "raw_payload",
        "request",
        "request_body",
        "request_headers",
        "response",
        "response_body",
        "response_headers",
        "url",
    }
)
_GOOD_QUALITY = frozenset(
    {"", "0", "good", "normal", "ok", "pass", "passed", "true", "valid"}
)
_STALE_QUALITY = frozenset({"old", "stale"})
_MISSING_QUALITY = frozenset({"missing", "no_data", "nodata", "offline", "unavailable"})
_BAD_QUALITY = frozenset(
    {"bad", "error", "fault", "invalid", "poor", "questionable", "suspect", "uncertain"}
)


def _required_text(value: Any, code: str, *, maximum: int = 512) -> str:
    result = str(value or "").strip()
    if not result or len(result) > maximum:
        raise ValueError(code)
    return result


def _optional_text(value: Any, code: str, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    if not result or len(result) > maximum:
        raise ValueError(code)
    return result


def _aware_utc(value: datetime, code: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(code)
    return value.astimezone(UTC)


def _metadata_key(value: Any) -> str:
    raw = str(value or "").strip()
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw)
    return re.sub(r"[^a-z0-9]+", "_", snake.lower()).strip("_")


def _safe_metadata_value(value: Any, *, depth: int, key_count: list[int]) -> Any:
    if depth > MAX_PREPARED_METADATA_DEPTH:
        raise ValueError("source_metadata_too_deep")
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized_key = _metadata_key(key)
            key_count[0] += 1
            if key_count[0] > MAX_PREPARED_METADATA_KEYS:
                raise ValueError("source_metadata_too_many_keys")
            if (
                not normalized_key
                or len(key) > 128
                or is_sensitive_telemetry_key(key)
                or normalized_key in _FORBIDDEN_METADATA_KEYS
            ):
                raise ValueError("source_metadata_unsafe")
            result[key] = _safe_metadata_value(
                item, depth=depth + 1, key_count=key_count
            )
        return MappingProxyType(result)
    if isinstance(value, (list, tuple)):
        if len(value) > 64:
            raise ValueError("source_metadata_list_too_large")
        return tuple(
            _safe_metadata_value(item, depth=depth + 1, key_count=key_count)
            for item in value
        )
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > 2_048:
            raise ValueError("source_metadata_value_too_large")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("source_metadata_nonfinite")
        return value
    raise ValueError("source_metadata_type_invalid")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _safe_metadata(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("source_metadata_type_invalid")
    frozen = _safe_metadata_value(value, depth=0, key_count=[0])
    assert isinstance(frozen, Mapping)
    encoded = json.dumps(
        _jsonable(frozen), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if len(encoded) > MAX_PREPARED_METADATA_BYTES:
        raise ValueError("source_metadata_too_large")
    return frozen


def _digest_scalar(value: Any) -> Mapping[str, Any]:
    """Encode source scalars without conflating strings, numbers, or booleans."""

    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(value, int):
        return {"type": "int", "value": str(value)}
    if isinstance(value, float):
        if math.isnan(value):
            rendered = "nan"
        elif math.isinf(value):
            rendered = "infinity" if value > 0 else "-infinity"
        else:
            rendered = value.hex()
        return {"type": "float", "value": rendered}
    if isinstance(value, Decimal):
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, str):
        return {"type": "str", "value": value}
    return {
        "type": "unsupported",
        "value": f"{type(value).__module__}.{type(value).__qualname__}",
    }


def stable_source_record_digest(observation: RawObservationEnvelope) -> str:
    """Return the stable SHA-256 identity of one provider measurement.

    Provider metadata is excluded intentionally: metadata is ancillary and may
    be enriched between retries, while the source measurement identity must not
    change. Mapping and tenant authority are likewise excluded and are enforced
    by the scoped persistence uniqueness key.
    """

    projection = {
        "version": SOURCE_RECORD_DIGEST_VERSION,
        "external_tag_id": _digest_scalar(
            getattr(observation, "external_tag_id", None)
        ),
        "source_timestamp": _digest_scalar(
            getattr(observation, "source_timestamp", None)
        ),
        "raw_value": _digest_scalar(getattr(observation, "raw_value", None)),
        "reported_unit": _digest_scalar(
            getattr(observation, "reported_unit", None)
        ),
        "reported_quality": _digest_scalar(
            getattr(observation, "reported_quality", None)
        ),
        "provider_event_id": _digest_scalar(
            getattr(observation, "provider_event_id", None)
        ),
    }
    encoded = json.dumps(
        projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class MappingSnapshot:
    """One server-authoritative mapping loaded once for a fetched page."""

    scope: TelemetryScopeRef
    connection_id: str
    external_tag_id: str
    external_signal_id: str
    mapping_id: str
    revision: int
    actor_id: str
    mapped_at: datetime
    authority_digest: str
    facility_id: str
    system_id: str
    canonical_signal_id: str
    canonical_signal_name: str
    source_unit: str
    canonical_unit: str
    expected_dimension: str
    conversion_id: str
    conversion_version: str
    source_timezone: str
    asset_id: str | None = None
    provenance: str = "manual"
    enabled: bool = True

    def __post_init__(self) -> None:
        for field_name in (
            "connection_id",
            "external_tag_id",
            "external_signal_id",
            "mapping_id",
            "actor_id",
            "facility_id",
            "system_id",
            "canonical_signal_id",
            "canonical_signal_name",
            "source_unit",
            "canonical_unit",
            "expected_dimension",
            "conversion_id",
            "conversion_version",
            "source_timezone",
            "provenance",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(
                    getattr(self, field_name), f"mapping_{field_name}_invalid"
                ),
            )
        object.__setattr__(
            self, "asset_id", _optional_text(self.asset_id, "mapping_asset_id_invalid")
        )
        if self.revision < 1:
            raise ValueError("mapping_revision_invalid")
        if not isinstance(self.scope, TelemetryScopeRef):
            raise TypeError("mapping_scope_required")
        if self.facility_id != self.scope.facility_id:
            raise ValueError("mapping_facility_scope_mismatch")
        object.__setattr__(
            self,
            "mapped_at",
            _aware_utc(self.mapped_at, "mapping_mapped_at_invalid"),
        )
        digest = str(self.authority_digest or "").strip().lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError("mapping_authority_digest_invalid")
        object.__setattr__(self, "authority_digest", digest)


@dataclass(frozen=True, slots=True)
class PreparedObservation:
    scope: TelemetryScopeRef
    connection_id: str
    ingestion_run_id: str
    external_signal_id: str
    mapping_id: str
    mapping_revision: int
    mapping_actor_id: str
    mapping_mapped_at: datetime
    mapping_authority_digest: str
    mapping_provenance: str
    system_id: str
    asset_id: str | None
    canonical_signal_id: str
    canonical_signal_name: str
    external_tag_id: str
    external_tag_name: str
    provider_event_id: str | None
    source_timestamp_raw: str = field(repr=False)
    source_timezone: str
    source_offset: str | None
    timestamp_normalization_version: str
    observed_at_utc: datetime
    ingested_at_utc: datetime
    original_value: Any = field(repr=False)
    original_unit: str | None
    normalized_value: float
    canonical_unit: str
    conversion_id: str
    conversion_version: str
    reported_quality: str | None
    quality_state: TelemetryQualityState
    ingestion_disposition: IngestionDisposition
    analysis_eligible: bool
    reason_codes: tuple[str, ...]
    source_record_digest: str
    source_metadata: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({}), repr=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.scope, TelemetryScopeRef):
            raise TypeError("prepared_observation_scope_required")
        for field_name in (
            "connection_id",
            "ingestion_run_id",
            "external_signal_id",
            "mapping_id",
            "mapping_actor_id",
            "mapping_authority_digest",
            "mapping_provenance",
            "system_id",
            "canonical_signal_id",
            "canonical_signal_name",
            "external_tag_id",
            "external_tag_name",
            "source_timestamp_raw",
            "source_timezone",
            "timestamp_normalization_version",
            "canonical_unit",
            "conversion_id",
            "conversion_version",
        ):
            _required_text(
                getattr(self, field_name),
                f"prepared_observation_{field_name}_invalid",
                maximum=2_048 if field_name == "source_timestamp_raw" else 512,
            )
        if self.mapping_revision < 1:
            raise ValueError("prepared_observation_mapping_revision_invalid")
        if not _SHA256.fullmatch(self.mapping_authority_digest):
            raise ValueError("prepared_observation_authority_digest_invalid")
        object.__setattr__(
            self,
            "mapping_mapped_at",
            _aware_utc(
                self.mapping_mapped_at,
                "prepared_observation_mapping_mapped_at_invalid",
            ),
        )
        object.__setattr__(
            self,
            "observed_at_utc",
            _aware_utc(
                self.observed_at_utc, "prepared_observation_observed_at_invalid"
            ),
        )
        object.__setattr__(
            self,
            "ingested_at_utc",
            _aware_utc(
                self.ingested_at_utc, "prepared_observation_ingested_at_invalid"
            ),
        )
        object.__setattr__(self, "quality_state", TelemetryQualityState(self.quality_state))
        object.__setattr__(
            self, "ingestion_disposition", IngestionDisposition(self.ingestion_disposition)
        )
        if self.ingestion_disposition not in {
            IngestionDisposition.ACCEPTED,
            IngestionDisposition.OUT_OF_ORDER_ACCEPTED,
        }:
            raise ValueError("prepared_observation_disposition_invalid")
        if not self.analysis_eligible:
            raise ValueError("prepared_observation_must_be_analysis_eligible")
        if not math.isfinite(self.normalized_value):
            raise ValueError("prepared_observation_value_nonfinite")
        if not _SHA256.fullmatch(self.source_record_digest):
            raise ValueError("prepared_observation_digest_invalid")
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "source_metadata", _safe_metadata(self.source_metadata))


@dataclass(frozen=True, slots=True)
class PreparedRejection:
    scope: TelemetryScopeRef
    connection_id: str
    ingestion_run_id: str
    external_tag_id: str | None
    external_signal_id: str | None
    mapping_id: str | None
    provider_event_id: str | None
    source_timestamp_raw: str | None = field(repr=False)
    original_value: Any = field(repr=False)
    original_unit: str | None = field(repr=False)
    reported_quality: str | None = field(repr=False)
    quality_state: TelemetryQualityState
    ingestion_disposition: IngestionDisposition
    reason_code: str
    source_record_digest: str
    safe_context: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({}), repr=False
    )
    analysis_eligible: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.scope, TelemetryScopeRef):
            raise TypeError("prepared_rejection_scope_required")
        _required_text(self.connection_id, "prepared_rejection_connection_id_invalid")
        _required_text(self.ingestion_run_id, "prepared_rejection_run_id_invalid")
        object.__setattr__(self, "quality_state", TelemetryQualityState(self.quality_state))
        object.__setattr__(
            self, "ingestion_disposition", IngestionDisposition(self.ingestion_disposition)
        )
        if self.ingestion_disposition not in {
            IngestionDisposition.DUPLICATE,
            IngestionDisposition.REJECTED,
            IngestionDisposition.QUARANTINED,
        }:
            raise ValueError("prepared_rejection_disposition_invalid")
        if self.analysis_eligible:
            raise ValueError("prepared_rejection_cannot_be_analysis_eligible")
        _required_text(self.reason_code, "prepared_rejection_reason_invalid", maximum=128)
        if not _SHA256.fullmatch(self.source_record_digest):
            raise ValueError("prepared_rejection_digest_invalid")
        object.__setattr__(self, "safe_context", _safe_metadata(self.safe_context))


@dataclass(frozen=True, slots=True)
class PreparedPage:
    observations: tuple[PreparedObservation, ...]
    rejections: tuple[PreparedRejection, ...]
    next_checkpoint: ConnectorCheckpoint | None
    has_more: bool
    pages_read: int
    response_bytes: int
    retry_count: int
    received_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    out_of_order_count: int
    high_watermark_utc: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "rejections", tuple(self.rejections))
        counters = (
            self.pages_read,
            self.response_bytes,
            self.retry_count,
            self.received_count,
            self.accepted_count,
            self.rejected_count,
            self.duplicate_count,
            self.out_of_order_count,
        )
        if any(value < 0 for value in counters):
            raise ValueError("prepared_page_counter_invalid")
        if self.accepted_count != len(self.observations):
            raise ValueError("prepared_page_accepted_count_mismatch")
        if self.rejected_count + self.duplicate_count != len(self.rejections):
            raise ValueError("prepared_page_rejection_count_mismatch")
        if self.received_count != self.accepted_count + len(self.rejections):
            raise ValueError("prepared_page_received_count_mismatch")
        if self.out_of_order_count > self.accepted_count:
            raise ValueError("prepared_page_out_of_order_count_invalid")
        if self.next_checkpoint is not None and not isinstance(
            self.next_checkpoint, ConnectorCheckpoint
        ):
            raise TypeError("prepared_page_checkpoint_invalid")
        if self.high_watermark_utc is not None:
            object.__setattr__(
                self,
                "high_watermark_utc",
                _aware_utc(
                    self.high_watermark_utc,
                    "prepared_page_high_watermark_invalid",
                ),
            )


def _source_timestamp_raw(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return value if isinstance(value, str) else str(value)


def _bounded_original_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, Decimal)):
        return value
    if isinstance(value, str) and len(value) <= 2_048:
        return value
    return None


def _is_source_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, Decimal, str))


def _reported_quality_decision(value: str | None) -> tuple[TelemetryQualityState, str | None]:
    token = _metadata_key(value or "")
    if token in _GOOD_QUALITY:
        return TelemetryQualityState.GOOD, None
    if token in _STALE_QUALITY:
        return TelemetryQualityState.STALE, "reported_quality_stale"
    if token in _MISSING_QUALITY:
        return TelemetryQualityState.MISSING, "reported_quality_missing"
    if token in _BAD_QUALITY:
        return TelemetryQualityState.INVALID_VALUE, "reported_quality_ineligible"
    return TelemetryQualityState.FORMAT_INVALID, "reported_quality_unrecognized"


def _rejection(
    *,
    scope: TelemetryScopeRef,
    connection_id: str,
    ingestion_run_id: str,
    observation: Any,
    mapping: MappingSnapshot | None,
    digest: str,
    quality_state: TelemetryQualityState,
    reason_code: str,
    disposition: IngestionDisposition = IngestionDisposition.REJECTED,
    safe_context: Mapping[str, Any] | None = None,
) -> PreparedRejection:
    return PreparedRejection(
        scope=scope,
        connection_id=connection_id,
        ingestion_run_id=ingestion_run_id,
        external_tag_id=_optional_text(
            getattr(observation, "external_tag_id", None),
            "rejection_external_tag_id_invalid",
        ),
        external_signal_id=mapping.external_signal_id if mapping else None,
        mapping_id=mapping.mapping_id if mapping else None,
        provider_event_id=_optional_text(
            getattr(observation, "provider_event_id", None),
            "rejection_provider_event_id_invalid",
        ),
        source_timestamp_raw=_source_timestamp_raw(
            getattr(observation, "source_timestamp", "")
        ),
        original_value=_bounded_original_value(getattr(observation, "raw_value", None)),
        original_unit=getattr(observation, "reported_unit", None),
        reported_quality=getattr(observation, "reported_quality", None),
        quality_state=quality_state,
        ingestion_disposition=disposition,
        reason_code=reason_code,
        source_record_digest=digest,
        safe_context=safe_context or {},
    )


def _issue_rejection(
    *,
    scope: TelemetryScopeRef,
    connection_id: str,
    ingestion_run_id: str,
    record_index: int,
    code: str,
) -> PreparedRejection:
    safe_code = re.sub(r"[^a-z0-9_.-]+", "_", str(code).strip().lower())[:128]
    projection = {
        "version": SOURCE_RECORD_DIGEST_VERSION,
        "connector_issue": safe_code,
        "record_index": record_index,
    }
    digest = hashlib.sha256(
        json.dumps(projection, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return PreparedRejection(
        scope=scope,
        connection_id=connection_id,
        ingestion_run_id=ingestion_run_id,
        external_tag_id=None,
        external_signal_id=None,
        mapping_id=None,
        provider_event_id=None,
        source_timestamp_raw=None,
        original_value=None,
        original_unit=None,
        reported_quality=None,
        quality_state=TelemetryQualityState.FORMAT_INVALID,
        ingestion_disposition=IngestionDisposition.QUARANTINED,
        reason_code=f"connector_record_{safe_code}"[:128],
        source_record_digest=digest,
        safe_context={
            "connector_record_index": record_index,
            "connector_issue_code": safe_code,
        },
    )


def prepare_connector_page(
    *,
    page: ConnectorPage,
    scope: TelemetryScopeRef,
    connection_id: str,
    ingestion_run_id: str,
    mappings_by_external_tag: Mapping[str, MappingSnapshot],
    existing_source_record_digests: Collection[str] = (),
    high_watermark_utc: datetime | None = None,
    now: datetime | None = None,
    ingested_at_utc: datetime | None = None,
    future_tolerance: timedelta = timedelta(minutes=5),
) -> PreparedPage:
    """Normalize one connector page without performing I/O.

    Structural caller errors fail the call. Every source-record error becomes a
    deterministic rejection so one bad record cannot discard valid siblings.
    """

    if not isinstance(page, ConnectorPage):
        raise TypeError("connector_page_required")
    if not isinstance(scope, TelemetryScopeRef):
        raise TypeError("telemetry_scope_required")
    connection_id = _required_text(connection_id, "connection_id_required")
    ingestion_run_id = _required_text(ingestion_run_id, "ingestion_run_id_required")
    reference_now = _aware_utc(now or datetime.now(UTC), "now_must_be_aware")
    ingested_at = _aware_utc(
        ingested_at_utc or reference_now, "ingested_at_utc_must_be_aware"
    )
    high_water = (
        _aware_utc(high_watermark_utc, "high_watermark_utc_must_be_aware")
        if high_watermark_utc is not None
        else None
    )
    if future_tolerance < timedelta(0):
        raise ValueError("future_tolerance_must_not_be_negative")

    mappings: dict[str, MappingSnapshot] = {}
    for raw_key, mapping in mappings_by_external_tag.items():
        key = str(raw_key).strip()
        if not isinstance(mapping, MappingSnapshot):
            raise TypeError("mapping_snapshot_required")
        if key != mapping.external_tag_id:
            raise ValueError("mapping_snapshot_external_tag_mismatch")
        if mapping.scope != scope or mapping.facility_id != scope.facility_id:
            raise ValueError("mapping_snapshot_scope_mismatch")
        if mapping.connection_id != connection_id:
            raise ValueError("mapping_snapshot_connection_mismatch")
        mappings[key] = mapping

    seen_digests: set[str] = set()
    for value in existing_source_record_digests:
        digest = str(value).strip().lower()
        if not _SHA256.fullmatch(digest):
            raise ValueError("existing_source_record_digest_invalid")
        seen_digests.add(digest)

    prepared: list[PreparedObservation] = []
    rejected: list[PreparedRejection] = [
        _issue_rejection(
            scope=scope,
            connection_id=connection_id,
            ingestion_run_id=ingestion_run_id,
            record_index=issue.record_index,
            code=issue.code,
        )
        for issue in page.issues
    ]

    for observation in page.observations:
        digest = stable_source_record_digest(observation)
        external_tag_id = str(getattr(observation, "external_tag_id", "") or "").strip()
        mapping = mappings.get(external_tag_id)
        if mapping is None:
            rejected.append(
                _rejection(
                    scope=scope,
                    connection_id=connection_id,
                    ingestion_run_id=ingestion_run_id,
                    observation=observation,
                    mapping=None,
                    digest=digest,
                    quality_state=TelemetryQualityState.MAPPING_REQUIRED,
                    reason_code="mapping_not_approved",
                )
            )
            seen_digests.add(digest)
            continue
        if not mapping.enabled:
            rejected.append(
                _rejection(
                    scope=scope,
                    connection_id=connection_id,
                    ingestion_run_id=ingestion_run_id,
                    observation=observation,
                    mapping=mapping,
                    digest=digest,
                    quality_state=TelemetryQualityState.MAPPING_REQUIRED,
                    reason_code="signal_disabled",
                )
            )
            seen_digests.add(digest)
            continue

        try:
            source_metadata = _safe_metadata(getattr(observation, "metadata", {}))
        except (TypeError, ValueError) as error:
            rejected.append(
                _rejection(
                    scope=scope,
                    connection_id=connection_id,
                    ingestion_run_id=ingestion_run_id,
                    observation=observation,
                    mapping=mapping,
                    digest=digest,
                    quality_state=TelemetryQualityState.FORMAT_INVALID,
                    reason_code=str(error),
                )
            )
            seen_digests.add(digest)
            continue

        quality_state, quality_reason = _reported_quality_decision(
            getattr(observation, "reported_quality", None)
        )
        if quality_reason is not None:
            rejected.append(
                _rejection(
                    scope=scope,
                    connection_id=connection_id,
                    ingestion_run_id=ingestion_run_id,
                    observation=observation,
                    mapping=mapping,
                    digest=digest,
                    quality_state=quality_state,
                    reason_code=quality_reason,
                )
            )
            seen_digests.add(digest)
            continue

        timestamp = normalize_telemetry_timestamp(
            source_timestamp=getattr(observation, "source_timestamp", None),
            source_timezone=mapping.source_timezone,
            now=reference_now,
            future_tolerance=future_tolerance,
            high_watermark_utc=high_water,
        )
        if not timestamp.analysis_eligible:
            rejected.append(
                _rejection(
                    scope=scope,
                    connection_id=connection_id,
                    ingestion_run_id=ingestion_run_id,
                    observation=observation,
                    mapping=mapping,
                    digest=digest,
                    quality_state=TelemetryQualityState.TIMESTAMP_INVALID,
                    reason_code=timestamp.reason_code or "timestamp_invalid",
                )
            )
            seen_digests.add(digest)
            continue

        raw_value = getattr(observation, "raw_value", None)
        if not _is_source_scalar(raw_value):
            rejected.append(
                _rejection(
                    scope=scope,
                    connection_id=connection_id,
                    ingestion_run_id=ingestion_run_id,
                    observation=observation,
                    mapping=mapping,
                    digest=digest,
                    quality_state=TelemetryQualityState.INVALID_VALUE,
                    reason_code="value_type_invalid",
                )
            )
            seen_digests.add(digest)
            continue

        reported_unit = getattr(observation, "reported_unit", None)
        effective_source_unit = (
            reported_unit if reported_unit is not None else mapping.source_unit
        )
        unit = normalize_telemetry_unit(
            value=raw_value,
            source_unit=effective_source_unit,
            canonical_unit=mapping.canonical_unit,
            expected_dimension=mapping.expected_dimension,
        )
        if not unit.analysis_eligible:
            rejected.append(
                _rejection(
                    scope=scope,
                    connection_id=connection_id,
                    ingestion_run_id=ingestion_run_id,
                    observation=observation,
                    mapping=mapping,
                    digest=digest,
                    quality_state=TelemetryQualityState(unit.quality_state),
                    reason_code=unit.reason_code or "unit_normalization_failed",
                )
            )
            seen_digests.add(digest)
            continue
        if (
            unit.conversion_id != mapping.conversion_id
            or unit.conversion_version != mapping.conversion_version
        ):
            rejected.append(
                _rejection(
                    scope=scope,
                    connection_id=connection_id,
                    ingestion_run_id=ingestion_run_id,
                    observation=observation,
                    mapping=mapping,
                    digest=digest,
                    quality_state=TelemetryQualityState.UNIT_UNRESOLVED,
                    reason_code="reported_unit_mapping_mismatch",
                )
            )
            seen_digests.add(digest)
            continue
        if digest in seen_digests:
            rejected.append(
                _rejection(
                    scope=scope,
                    connection_id=connection_id,
                    ingestion_run_id=ingestion_run_id,
                    observation=observation,
                    mapping=mapping,
                    digest=digest,
                    quality_state=TelemetryQualityState.FORMAT_INVALID,
                    reason_code="source_record_duplicate",
                    disposition=IngestionDisposition.DUPLICATE,
                )
            )
            continue

        assert timestamp.observed_at_utc is not None
        assert unit.canonical_value is not None
        assert unit.canonical_unit is not None
        assert unit.conversion_id is not None
        disposition = IngestionDisposition(timestamp.ingestion_disposition)
        prepared.append(
            PreparedObservation(
                scope=scope,
                connection_id=connection_id,
                ingestion_run_id=ingestion_run_id,
                external_signal_id=mapping.external_signal_id,
                mapping_id=mapping.mapping_id,
                mapping_revision=mapping.revision,
                mapping_actor_id=mapping.actor_id,
                mapping_mapped_at=mapping.mapped_at,
                mapping_authority_digest=mapping.authority_digest,
                mapping_provenance=mapping.provenance,
                system_id=mapping.system_id,
                asset_id=mapping.asset_id,
                canonical_signal_id=mapping.canonical_signal_id,
                canonical_signal_name=mapping.canonical_signal_name,
                external_tag_id=observation.external_tag_id,
                external_tag_name=observation.external_tag_name,
                provider_event_id=observation.provider_event_id,
                source_timestamp_raw=timestamp.source_timestamp_raw,
                source_timezone=timestamp.source_timezone or mapping.source_timezone,
                source_offset=timestamp.source_offset,
                timestamp_normalization_version=timestamp.normalization_version,
                observed_at_utc=timestamp.observed_at_utc,
                ingested_at_utc=ingested_at,
                original_value=observation.raw_value,
                original_unit=observation.reported_unit,
                normalized_value=unit.canonical_value,
                canonical_unit=unit.canonical_unit,
                conversion_id=unit.conversion_id,
                conversion_version=unit.conversion_version,
                reported_quality=observation.reported_quality,
                quality_state=TelemetryQualityState.GOOD,
                ingestion_disposition=disposition,
                analysis_eligible=True,
                reason_codes=(timestamp.reason_code,) if timestamp.reason_code else (),
                source_record_digest=digest,
                source_metadata=source_metadata,
            )
        )
        seen_digests.add(digest)
        if high_water is None or timestamp.observed_at_utc > high_water:
            high_water = timestamp.observed_at_utc

    duplicate_count = sum(
        item.ingestion_disposition is IngestionDisposition.DUPLICATE for item in rejected
    )
    out_of_order_count = sum(
        item.ingestion_disposition is IngestionDisposition.OUT_OF_ORDER_ACCEPTED
        for item in prepared
    )
    return PreparedPage(
        observations=tuple(prepared),
        rejections=tuple(rejected),
        next_checkpoint=page.next_checkpoint,
        has_more=page.has_more,
        pages_read=page.pages_read,
        response_bytes=page.response_bytes,
        retry_count=page.retry_count,
        received_count=len(page.observations) + len(page.issues),
        accepted_count=len(prepared),
        rejected_count=len(rejected) - duplicate_count,
        duplicate_count=duplicate_count,
        out_of_order_count=out_of_order_count,
        high_watermark_utc=high_water,
    )


__all__ = [
    "MAX_PREPARED_METADATA_BYTES",
    "MappingSnapshot",
    "PreparedObservation",
    "PreparedPage",
    "PreparedRejection",
    "SOURCE_RECORD_DIGEST_VERSION",
    "prepare_connector_page",
    "stable_source_record_digest",
]
