"""Explicit endpoint-keyed telemetry window; no production caller selects V2 yet.

V1 windows, relationship lineage, temporal memory, and numerical execution are
unchanged. A V2 series is built only from the Phase 1 server-owned projection
and exact normalized observation lineage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from types import MappingProxyType
from typing import Any

from app.services.phase4_scope import ServerBoundSystemIdentityV2
from app.services.relationship_evidence_binding import digest
from app.services.telemetry_analysis_window import (
    MAX_ANALYSIS_ROWS,
    MAX_ANALYSIS_SIGNALS,
    TIMESTAMP_COLUMN,
    AnalysisWindowValidationError,
)
from app.services.telemetry_domain import ExternalSignalRecord, TelemetryScopeRef
from app.services.telemetry_endpoint_identity import (
    PhysicalEndpointIdentity,
    verify_physical_endpoint_identity,
)
from app.services.telemetry_ingestion import MappingSnapshot
from app.services.telemetry_lineage import MAX_LINEAGE_RECORDS, ObservationLineage


WINDOW_VERSION = "telemetry-analysis-window.v2"
RELATIONSHIP_PAIR_VERSION = "relationship-endpoint-pair.v2"
SCHEMA_FINGERPRINT_VERSION = "telemetry-analysis-schema.v2"
CONTENT_DIGEST_VERSION = "telemetry-analysis-window-content.v2"


def _timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AnalysisWindowValidationError("endpoint_window_timestamp_invalid") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AnalysisWindowValidationError("endpoint_window_timestamp_invalid")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class EndpointBindingV2:
    """Projection plus the two server-loaded records from which it was issued."""

    identity: PhysicalEndpointIdentity
    mapping: MappingSnapshot
    signal: ExternalSignalRecord

    def __post_init__(self) -> None:
        if not verify_physical_endpoint_identity(self.identity, self.mapping, self.signal):
            raise AnalysisWindowValidationError("endpoint_window_binding_invalid")


@dataclass(frozen=True, slots=True)
class EndpointSeriesV2:
    identity: PhysicalEndpointIdentity
    canonical_signal_name: str
    source_unit: str
    canonical_unit: str
    expected_dimension: str
    conversion_id: str
    conversion_version: str
    mapping_provenance: str
    observation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, PhysicalEndpointIdentity):
            raise AnalysisWindowValidationError("endpoint_window_identity_required")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.canonical_signal_name, self.source_unit, self.canonical_unit,
                self.expected_dimension, self.conversion_id, self.conversion_version,
                self.mapping_provenance,
            )
        ):
            raise AnalysisWindowValidationError("endpoint_window_series_metadata_missing")
        if not self.observation_ids or len(set(self.observation_ids)) != len(self.observation_ids):
            raise AnalysisWindowValidationError("endpoint_window_series_lineage_invalid")

    @property
    def series_id(self) -> str:
        return self.identity.endpoint_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "endpoint_identity": self.identity.as_dict(),
            "canonical_concept_id": self.identity.canonical_concept_id,
            "canonical_signal_name": self.canonical_signal_name,
            "source_unit": self.source_unit,
            "canonical_unit": self.canonical_unit,
            "expected_dimension": self.expected_dimension,
            "conversion_id": self.conversion_id,
            "conversion_version": self.conversion_version,
            "mapping_provenance": self.mapping_provenance,
            "observation_ids": list(self.observation_ids),
        }


@dataclass(frozen=True, slots=True)
class EndpointRelationshipPairV2:
    """Ordered endpoint identity boundary; full lineage persistence follows later."""

    source: PhysicalEndpointIdentity
    target: PhysicalEndpointIdentity
    schema_fingerprint: str
    contract_version: str = RELATIONSHIP_PAIR_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != RELATIONSHIP_PAIR_VERSION:
            raise AnalysisWindowValidationError("endpoint_relationship_version_invalid")
        if not isinstance(self.source, PhysicalEndpointIdentity) or not isinstance(self.target, PhysicalEndpointIdentity):
            raise AnalysisWindowValidationError("endpoint_relationship_identity_required")
        if self.source.endpoint_id == self.target.endpoint_id:
            raise AnalysisWindowValidationError("endpoint_relationship_self_pair")
        if not isinstance(self.schema_fingerprint, str) or not self.schema_fingerprint.startswith(
            SCHEMA_FINGERPRINT_VERSION + ":"
        ):
            raise AnalysisWindowValidationError("endpoint_relationship_schema_invalid")

    @property
    def ref(self) -> str:
        return digest(self.contract_version, {
            "source": self.source.as_dict(),
            "target": self.target.as_dict(),
            "schema_fingerprint": self.schema_fingerprint,
        })

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "source_endpoint": self.source.as_dict(),
            "target_endpoint": self.target.as_dict(),
            "schema_fingerprint": self.schema_fingerprint,
            "ref": self.ref,
        }


@dataclass(frozen=True, slots=True)
class EndpointAnalysisWindowV2:
    window_id: str
    source_run_id: str
    scope: TelemetryScopeRef
    system_identity: ServerBoundSystemIdentityV2
    asset_id: str | None
    series: tuple[EndpointSeriesV2, ...]
    rows: tuple[Mapping[str, Any], ...]
    observation_lineage: tuple[ObservationLineage, ...]
    contract_version: str = WINDOW_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != WINDOW_VERSION:
            raise AnalysisWindowValidationError("endpoint_window_version_invalid")
        if not isinstance(self.window_id, str) or not self.window_id.strip() or not isinstance(
            self.source_run_id, str
        ) or not self.source_run_id.strip():
            raise AnalysisWindowValidationError("endpoint_window_source_invalid")
        if not isinstance(self.scope, TelemetryScopeRef) or not isinstance(
            self.system_identity, ServerBoundSystemIdentityV2
        ):
            raise AnalysisWindowValidationError("endpoint_window_scope_invalid")
        if not 1 <= len(self.series) <= MAX_ANALYSIS_SIGNALS:
            raise AnalysisWindowValidationError("endpoint_window_series_count_invalid")
        if any(not isinstance(item, EndpointSeriesV2) for item in self.series):
            raise AnalysisWindowValidationError("endpoint_window_identity_required")
        ids = [item.series_id for item in self.series]
        if len(ids) != len(set(ids)):
            raise AnalysisWindowValidationError("endpoint_window_endpoint_duplicate")
        for item in self.series:
            identity = item.identity
            if (
                identity.resource_scope_id != self.scope.resource_scope_id
                or identity.facility_id != self.scope.facility_id
                or identity.system_id != self.system_identity.system_id
                or identity.asset_id != self.asset_id
                or identity.authority_digest != self.system_identity.authority_record_digest
            ):
                raise AnalysisWindowValidationError("endpoint_window_authority_mismatch")
        if self.system_identity.resource_scope_id != self.scope.resource_scope_id:
            raise AnalysisWindowValidationError("endpoint_window_scope_mismatch")
        if not 2 <= len(self.rows) <= MAX_ANALYSIS_ROWS:
            raise AnalysisWindowValidationError("endpoint_window_row_count_invalid")
        expected = {TIMESTAMP_COLUMN, *ids}
        previous: datetime | None = None
        normalized_rows = []
        rows_at: dict[datetime, Mapping[str, Any]] = {}
        for row in self.rows:
            if not isinstance(row, Mapping) or set(row) != expected:
                raise AnalysisWindowValidationError("endpoint_window_row_fields_invalid")
            timestamp = _timestamp(row[TIMESTAMP_COLUMN])
            if previous is not None and timestamp <= previous:
                raise AnalysisWindowValidationError("endpoint_window_row_order_invalid")
            previous = timestamp
            normalized = {TIMESTAMP_COLUMN: timestamp.isoformat()}
            present = False
            for endpoint_id in ids:
                value = row[endpoint_id]
                if value is not None:
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                        raise AnalysisWindowValidationError("endpoint_window_value_invalid")
                    present = True
                normalized[endpoint_id] = value
            if not present:
                raise AnalysisWindowValidationError("endpoint_window_row_empty")
            normalized_rows.append(MappingProxyType(normalized))
            rows_at[timestamp] = normalized_rows[-1]
        object.__setattr__(self, "rows", tuple(normalized_rows))
        if not self.observation_lineage or len(self.observation_lineage) > MAX_LINEAGE_RECORDS:
            raise AnalysisWindowValidationError("endpoint_window_lineage_required")
        if len({item.observation_id for item in self.observation_lineage}) != len(self.observation_lineage):
            raise AnalysisWindowValidationError("endpoint_window_observation_duplicate")
        claimed_ids = [observation_id for item in self.series for observation_id in item.observation_ids]
        if len(claimed_ids) != len(set(claimed_ids)) or set(claimed_ids) != {
            item.observation_id for item in self.observation_lineage
        }:
            raise AnalysisWindowValidationError("endpoint_window_series_lineage_invalid")
        if self.source_run_id not in {item.ingestion_run_id for item in self.observation_lineage}:
            raise AnalysisWindowValidationError("endpoint_window_source_run_missing")
        by_id = {item.series_id: item for item in self.series}
        for item in self.observation_lineage:
            try:
                endpoint_id = next(
                    key for key, series in by_id.items()
                    if series.identity.connection_id == item.connection_id
                    and series.identity.external_signal_id == item.external_signal_id
                )
            except StopIteration as exc:
                raise AnalysisWindowValidationError("endpoint_window_lineage_endpoint_missing") from exc
            identity = by_id[endpoint_id].identity
            if (
                item.mapping_id != identity.mapping_id
                or item.mapping_revision != identity.mapping_revision
                or item.canonical_signal_id != identity.canonical_concept_id
                or item.system_id != identity.system_id
                or item.asset_id != identity.asset_id
                or item.mapping_authority_digest != identity.authority_digest
                or item.observation_id not in by_id[endpoint_id].observation_ids
                or item.observed_at_utc not in rows_at
                or rows_at[item.observed_at_utc][endpoint_id] is None
                or item.original_unit != by_id[endpoint_id].source_unit
                or item.canonical_unit != by_id[endpoint_id].canonical_unit
                or item.conversion_id != by_id[endpoint_id].conversion_id
                or item.conversion_version != by_id[endpoint_id].conversion_version
            ):
                raise AnalysisWindowValidationError("endpoint_window_lineage_authority_mismatch")

    @property
    def numeric_columns(self) -> tuple[str, ...]:
        return tuple(item.series_id for item in self.series)

    @property
    def schema_fingerprint(self) -> str:
        return digest(SCHEMA_FINGERPRINT_VERSION, [
            {key: value for key, value in item.as_dict().items() if key != "observation_ids"}
            for item in self.series
        ])

    @property
    def content_digest(self) -> str:
        return digest(CONTENT_DIGEST_VERSION, {
            "schema_fingerprint": self.schema_fingerprint,
            "rows": [dict(row) for row in self.rows],
            "observation_ids": sorted(item.observation_id for item in self.observation_lineage),
        })

    def relationship_pair(
        self, source_endpoint_id: str, target_endpoint_id: str, *, prior_memory: Any = None
    ) -> EndpointRelationshipPairV2:
        # No V2 temporal storage contract exists yet. Reject all prior memory,
        # including concept-keyed V1, rather than treating it as endpoint-keyed.
        if prior_memory is not None:
            raise AnalysisWindowValidationError("endpoint_window_prior_memory_unsupported")
        by_id = {item.series_id: item.identity for item in self.series}
        if source_endpoint_id not in by_id or target_endpoint_id not in by_id:
            raise AnalysisWindowValidationError("endpoint_relationship_endpoint_missing")
        return EndpointRelationshipPairV2(
            source=by_id[source_endpoint_id],
            target=by_id[target_endpoint_id],
            schema_fingerprint=self.schema_fingerprint,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "window_id": self.window_id,
            "source_run_id": self.source_run_id,
            "resource_scope_id": self.scope.resource_scope_id,
            "system_id": self.system_identity.system_id,
            "asset_id": self.asset_id,
            "numeric_columns": list(self.numeric_columns),
            "series": [item.as_dict() for item in self.series],
            "rows": [dict(row) for row in self.rows],
            "observation_lineage": [item.as_dict() for item in self.observation_lineage],
            "schema_fingerprint": self.schema_fingerprint,
            "content_digest": self.content_digest,
        }


def build_endpoint_analysis_window_v2(
    *, window_id: str, source_run_id: str, scope: TelemetryScopeRef,
    system_identity: ServerBoundSystemIdentityV2, asset_id: str | None,
    bindings: Sequence[EndpointBindingV2], observations: Sequence[Mapping[str, Any]],
) -> EndpointAnalysisWindowV2:
    """Pivot exact normalized observations by physical endpoint, never concept."""
    if not bindings or len(bindings) > MAX_ANALYSIS_SIGNALS:
        raise AnalysisWindowValidationError("endpoint_window_series_count_invalid")
    by_source: dict[tuple[str, str], EndpointBindingV2] = {}
    for binding in bindings:
        if not isinstance(binding, EndpointBindingV2) or not verify_physical_endpoint_identity(
            binding.identity, binding.mapping, binding.signal
        ):
            raise AnalysisWindowValidationError("endpoint_window_binding_invalid")
        key = (binding.identity.connection_id, binding.identity.external_signal_id)
        if key in by_source:
            raise AnalysisWindowValidationError("endpoint_window_endpoint_duplicate")
        by_source[key] = binding
    if not observations or len(observations) > MAX_LINEAGE_RECORDS:
        raise AnalysisWindowValidationError("endpoint_window_lineage_required")
    rows_by_time: dict[datetime, dict[str, Any]] = {}
    lineage: list[ObservationLineage] = []
    observation_ids: dict[str, list[str]] = {binding.identity.endpoint_id: [] for binding in bindings}
    seen: set[tuple[str, datetime]] = set()
    for observation in observations:
        if not isinstance(observation, Mapping) or observation.get("analysis_eligible") is not True or observation.get("quality_state") != "good":
            raise AnalysisWindowValidationError("endpoint_window_observation_ineligible")
        key = (observation.get("connection_id"), observation.get("external_signal_id"))
        binding = by_source.get(key)
        if binding is None:
            raise AnalysisWindowValidationError("endpoint_window_observation_endpoint_missing")
        identity = binding.identity
        record = ObservationLineage.from_observation(observation)
        if (
            record.mapping_id != identity.mapping_id
            or record.mapping_revision != identity.mapping_revision
            or record.canonical_signal_id != identity.canonical_concept_id
            or record.system_id != identity.system_id
            or record.asset_id != identity.asset_id
            or record.mapping_authority_digest != identity.authority_digest
            or record.external_tag_id != binding.mapping.external_tag_id
            or record.original_unit != binding.mapping.source_unit
            or record.canonical_unit != binding.mapping.canonical_unit
            or record.conversion_id != binding.mapping.conversion_id
            or record.conversion_version != binding.mapping.conversion_version
        ):
            raise AnalysisWindowValidationError("endpoint_window_observation_authority_mismatch")
        timestamp = record.observed_at_utc
        duplicate = (identity.endpoint_id, timestamp)
        if duplicate in seen:
            raise AnalysisWindowValidationError("endpoint_window_endpoint_time_duplicate")
        seen.add(duplicate)
        value = observation.get("normalized_value")
        if isinstance(value, bool):
            raise AnalysisWindowValidationError("endpoint_window_value_invalid")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise AnalysisWindowValidationError("endpoint_window_value_invalid") from exc
        if not isfinite(number):
            raise AnalysisWindowValidationError("endpoint_window_value_invalid")
        rows_by_time.setdefault(timestamp, {})[identity.endpoint_id] = number
        lineage.append(record)
        observation_ids[identity.endpoint_id].append(record.observation_id)
    series = tuple(
        EndpointSeriesV2(
            identity=binding.identity,
            canonical_signal_name=binding.mapping.canonical_signal_name,
            source_unit=binding.mapping.source_unit,
            canonical_unit=binding.mapping.canonical_unit,
            expected_dimension=binding.mapping.expected_dimension,
            conversion_id=binding.mapping.conversion_id,
            conversion_version=binding.mapping.conversion_version,
            mapping_provenance=binding.mapping.provenance,
            observation_ids=tuple(sorted(observation_ids[binding.identity.endpoint_id])),
        )
        for binding in sorted(bindings, key=lambda item: item.identity.endpoint_id)
    )
    if any(not item.observation_ids for item in series):
        raise AnalysisWindowValidationError("endpoint_window_series_empty")
    ids = tuple(item.series_id for item in series)
    rows = tuple(
        {TIMESTAMP_COLUMN: timestamp.isoformat(), **{
            endpoint_id: rows_by_time[timestamp].get(endpoint_id) for endpoint_id in ids
        }}
        for timestamp in sorted(rows_by_time)
    )
    return EndpointAnalysisWindowV2(
        window_id=window_id, source_run_id=source_run_id, scope=scope,
        system_identity=system_identity, asset_id=asset_id,
        series=series, rows=rows, observation_lineage=tuple(sorted(
            lineage, key=lambda item: (item.observed_at_utc, item.connection_id,
                                       item.external_signal_id, item.observation_id),
        )),
    )
