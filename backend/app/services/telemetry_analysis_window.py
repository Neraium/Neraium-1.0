"""Authoritative, source-neutral telemetry analysis-window handoff.

Connector observations are already normalized before reaching this module.
This module never imports upload parsing code and never accepts analytical
configuration capable of overriding server scope or hierarchy identity.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import math
from types import MappingProxyType
from typing import Any

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.engine.sii_engine import evaluate_sii
from app.services.analysis_result_contract import build_analysis_result
from app.services.phase4_scope import ServerBoundSystemIdentityV2
from app.services.telemetry_domain import TelemetryScopeRef, sanitize_telemetry_public_value
from app.services.telemetry_lineage import (
    DEFAULT_LINEAGE_SAMPLE_LIMIT,
    MAX_LINEAGE_RECORDS,
    ObservationLineage,
    build_lineage_summary,
    build_observation_lineage,
    project_analysis_window_observations,
    project_analysis_window_persistence,
)


ANALYSIS_WINDOW_CONTRACT_VERSION = "canonical-analysis-window.v1"
ANALYSIS_WINDOW_EXECUTION_VERSION = "analysis-window-execution.v1"
CONNECTOR_SOURCE_KINDS = frozenset({"connector", "telemetry_connector"})
TIMESTAMP_COLUMN = "observed_at_utc"
MAX_ANALYSIS_ROWS = 5_000
MAX_ANALYSIS_SIGNALS = 64
_AUTHORITY_KEYS = frozenset(
    {
        "asset_id",
        "configured_model_id",
        "equipment_group_id",
        "facility_id",
        "infrastructure_identity",
        "organization_id",
        "phase4_scope",
        "portfolio_id",
        "resource_scope_id",
        "subsystem_id",
        "system_id",
        "tenant_id",
        "tenant_scope_id",
        "workspace_id",
    }
)
_CANONICAL_CATALOG_KEYS = frozenset(
    {
        "analysis_role",
        "canonical_role",
        "canonical_signal_id",
        "canonical_signal_name",
        "canonical_unit",
        "category",
        "column",
        "display_name",
        "engineering_units",
        "physical_dimension",
        "structural_class",
        "taxonomy_version",
        "unit_normalization_version",
    }
)


class AnalysisWindowValidationError(ValueError):
    """Raised before the SII entry point can be invoked."""


class AnalysisWindowExecutionError(RuntimeError):
    """A single authoritative SII invocation failed; this seam never retries."""


def _required_text(value: Any, code: str, *, maximum: int = 512) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise AnalysisWindowValidationError(code)
    return normalized


def _optional_text(value: Any, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise AnalysisWindowValidationError("telemetry_analysis_window_text_too_long")
    return normalized


def _aware_utc(value: Any, code: str) -> datetime:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            value = datetime.fromisoformat(candidate)
        except ValueError as error:
            raise AnalysisWindowValidationError(code) from error
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AnalysisWindowValidationError(code)
    return value.astimezone(UTC)


def _immutable_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    public = sanitize_telemetry_public_value(dict(value or {}))
    if not isinstance(public, dict):
        raise AnalysisWindowValidationError("telemetry_analysis_window_mapping_invalid")
    return MappingProxyType(public)


def _source_neutral_report(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Remove every identity-shaped key from source-derived reports."""
    public = sanitize_telemetry_public_value(dict(value or {}))
    if not isinstance(public, dict):
        return {}

    def strip_authority(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {
                str(key): strip_authority(nested)
                for key, nested in item.items()
                if str(key) not in _AUTHORITY_KEYS
            }
        if isinstance(item, (list, tuple)):
            return [strip_authority(nested) for nested in item]
        return item

    return strip_authority(public)


@dataclass(frozen=True, slots=True)
class CanonicalAnalysisWindow:
    window_id: str
    source_kind: str
    source_run_id: str
    phase4_scope: AuthenticatedPhase4Scope
    phase4_system_identity: ServerBoundSystemIdentityV2
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    numeric_profiles: tuple[Mapping[str, Any], ...]
    timestamp_column: str
    numeric_columns: tuple[str, ...]
    telemetry_signal_catalog: Mapping[str, Mapping[str, Any]]
    ingestion_report: Mapping[str, Any]
    normalization_report: Mapping[str, Any]
    data_quality: Mapping[str, Any]
    sensor_health: Mapping[str, Any]
    operating_mode: Mapping[str, Any]
    observation_lineage: tuple[ObservationLineage, ...]
    asset_id: str | None = None
    contract_version: str = ANALYSIS_WINDOW_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != ANALYSIS_WINDOW_CONTRACT_VERSION:
            raise AnalysisWindowValidationError("telemetry_analysis_window_version_invalid")
        object.__setattr__(
            self, "window_id", _required_text(self.window_id, "telemetry_analysis_window_id_invalid")
        )
        object.__setattr__(
            self,
            "source_run_id",
            _required_text(self.source_run_id, "telemetry_analysis_window_source_run_invalid"),
        )
        source_kind = _required_text(
            self.source_kind, "telemetry_analysis_window_source_kind_invalid"
        )
        if source_kind not in CONNECTOR_SOURCE_KINDS:
            raise AnalysisWindowValidationError("telemetry_analysis_window_source_kind_invalid")
        object.__setattr__(self, "source_kind", source_kind)
        if not isinstance(self.phase4_scope, AuthenticatedPhase4Scope):
            raise AnalysisWindowValidationError("authenticated_phase4_scope_required")
        if not self.phase4_scope.workspace_id.startswith("ws-"):
            raise AnalysisWindowValidationError("telemetry_analysis_scope_not_explicit_facility")
        if not isinstance(self.phase4_system_identity, ServerBoundSystemIdentityV2):
            raise AnalysisWindowValidationError("telemetry_analysis_system_identity_v2_required")
        if (
            self.phase4_system_identity.resource_scope_id
            != self.phase4_scope.resource_scope_id
        ):
            raise AnalysisWindowValidationError("telemetry_analysis_identity_scope_mismatch")
        object.__setattr__(self, "asset_id", _optional_text(self.asset_id))

        columns = tuple(_required_text(item, "telemetry_analysis_column_invalid") for item in self.columns)
        numeric_columns = tuple(
            _required_text(item, "telemetry_analysis_numeric_column_invalid")
            for item in self.numeric_columns
        )
        if self.timestamp_column != TIMESTAMP_COLUMN:
            raise AnalysisWindowValidationError("telemetry_analysis_timestamp_column_invalid")
        if columns != (TIMESTAMP_COLUMN, *numeric_columns):
            raise AnalysisWindowValidationError("telemetry_analysis_columns_not_canonical")
        if not numeric_columns or len(numeric_columns) > MAX_ANALYSIS_SIGNALS:
            raise AnalysisWindowValidationError("telemetry_analysis_signal_count_invalid")
        if len(set(numeric_columns)) != len(numeric_columns):
            raise AnalysisWindowValidationError("telemetry_analysis_signal_duplicate")
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "numeric_columns", numeric_columns)

        catalog = {str(key): dict(item) for key, item in self.telemetry_signal_catalog.items()}
        if set(catalog) != set(numeric_columns):
            raise AnalysisWindowValidationError("telemetry_analysis_catalog_coverage_invalid")
        for signal_id, item in catalog.items():
            if str(item.get("canonical_signal_id") or signal_id) != signal_id:
                raise AnalysisWindowValidationError("telemetry_analysis_catalog_identity_mismatch")
            if set(item) - _CANONICAL_CATALOG_KEYS:
                raise AnalysisWindowValidationError("telemetry_analysis_catalog_vendor_field_forbidden")
            item["canonical_signal_id"] = signal_id
            item["column"] = signal_id
        object.__setattr__(
            self,
            "telemetry_signal_catalog",
            MappingProxyType({key: MappingProxyType(item) for key, item in catalog.items()}),
        )

        if not self.rows or len(self.rows) > MAX_ANALYSIS_ROWS:
            raise AnalysisWindowValidationError("telemetry_analysis_row_count_invalid")
        normalized_rows: list[Mapping[str, Any]] = []
        expected_keys = set(columns)
        previous_timestamp: datetime | None = None
        for raw_row in self.rows:
            if set(raw_row) != expected_keys:
                raise AnalysisWindowValidationError("telemetry_analysis_row_fields_not_canonical")
            timestamp = _aware_utc(
                raw_row.get(TIMESTAMP_COLUMN), "telemetry_analysis_row_timestamp_invalid"
            )
            if previous_timestamp is not None and timestamp <= previous_timestamp:
                raise AnalysisWindowValidationError("telemetry_analysis_rows_not_strictly_ordered")
            previous_timestamp = timestamp
            row: dict[str, Any] = {TIMESTAMP_COLUMN: timestamp.isoformat()}
            present = 0
            for signal_id in numeric_columns:
                value = raw_row.get(signal_id)
                if value is None:
                    row[signal_id] = None
                    continue
                if isinstance(value, bool):
                    raise AnalysisWindowValidationError("telemetry_analysis_value_non_numeric")
                try:
                    number = float(value)
                except (TypeError, ValueError) as error:
                    raise AnalysisWindowValidationError(
                        "telemetry_analysis_value_non_numeric"
                    ) from error
                if not math.isfinite(number):
                    raise AnalysisWindowValidationError("telemetry_analysis_value_nonfinite")
                row[signal_id] = number
                present += 1
            if not present:
                raise AnalysisWindowValidationError("telemetry_analysis_empty_row")
            normalized_rows.append(MappingProxyType(row))
        object.__setattr__(self, "rows", tuple(normalized_rows))

        profiles = tuple(MappingProxyType(dict(item)) for item in self.numeric_profiles)
        if {str(item.get("column")) for item in profiles} != set(numeric_columns):
            raise AnalysisWindowValidationError("telemetry_analysis_profiles_coverage_invalid")
        object.__setattr__(self, "numeric_profiles", profiles)
        lineage = build_observation_lineage(self.observation_lineage)
        if not lineage:
            raise AnalysisWindowValidationError("telemetry_analysis_lineage_required")
        connection_ids = {item.connection_id for item in lineage}
        if len(connection_ids) != 1:
            raise AnalysisWindowValidationError("telemetry_analysis_lineage_connection_mismatch")
        contributing_runs = {item.ingestion_run_id for item in lineage}
        if self.source_run_id not in contributing_runs:
            raise AnalysisWindowValidationError(
                "telemetry_analysis_trigger_run_not_in_lineage"
            )
        for item in lineage:
            if item.system_id != self.phase4_system_identity.system_id:
                raise AnalysisWindowValidationError("telemetry_analysis_lineage_system_mismatch")
            if item.asset_id != self.asset_id:
                raise AnalysisWindowValidationError("telemetry_analysis_lineage_asset_mismatch")
            if item.canonical_signal_id not in numeric_columns:
                raise AnalysisWindowValidationError("telemetry_analysis_lineage_signal_mismatch")
            if item.mapping_authority_digest != self.phase4_system_identity.authority_record_digest:
                raise AnalysisWindowValidationError("telemetry_analysis_lineage_authority_stale")
        object.__setattr__(self, "observation_lineage", lineage)
        for field_name in (
            "ingestion_report",
            "normalization_report",
            "data_quality",
            "sensor_health",
            "operating_mode",
        ):
            object.__setattr__(self, field_name, _immutable_mapping(getattr(self, field_name)))

    @property
    def window_start(self) -> datetime:
        return _aware_utc(self.rows[0][TIMESTAMP_COLUMN], "telemetry_analysis_window_start_invalid")

    @property
    def window_end(self) -> datetime:
        return _aware_utc(self.rows[-1][TIMESTAMP_COLUMN], "telemetry_analysis_window_end_invalid")

    def lineage_summary(self, *, sample_limit: int = DEFAULT_LINEAGE_SAMPLE_LIMIT) -> dict[str, Any]:
        summary = build_lineage_summary(self.observation_lineage, sample_limit=sample_limit)
        return {
            **summary,
            "window_id": self.window_id,
            "source_kind": self.source_kind,
            "source_run_id": self.source_run_id,
        }


@dataclass(frozen=True, slots=True)
class AnalysisWindowExecution:
    window_id: str
    source_kind: str
    source_run_id: str
    sii_result: Mapping[str, Any]
    analysis_result: Mapping[str, Any]
    telemetry_lineage: Mapping[str, Any]
    contract_version: str = ANALYSIS_WINDOW_EXECUTION_VERSION
    status: str = "completed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "status": self.status,
            "window_id": self.window_id,
            "source_kind": self.source_kind,
            "source_run_id": self.source_run_id,
            "sii_result": dict(self.sii_result),
            "analysis_result": dict(self.analysis_result),
            "telemetry_lineage": dict(self.telemetry_lineage),
        }


def _scope_from(value: TelemetryScopeRef | AuthenticatedPhase4Scope) -> AuthenticatedPhase4Scope:
    if isinstance(value, AuthenticatedPhase4Scope):
        scope = AuthenticatedPhase4Scope(
            tenant_scope_id=value.tenant_scope_id,
            workspace_id=value.workspace_id,
            resource_scope_id=value.resource_scope_id,
            version=value.version,
        )
    elif isinstance(value, TelemetryScopeRef):
        scope = AuthenticatedPhase4Scope(
            tenant_scope_id=value.tenant_scope_id,
            workspace_id=value.workspace_id,
            resource_scope_id=value.resource_scope_id,
        )
        if value.facility_id != scope.workspace_id:
            raise AnalysisWindowValidationError("telemetry_analysis_facility_scope_mismatch")
    else:
        raise AnalysisWindowValidationError("authenticated_phase4_scope_required")
    if not scope.workspace_id.startswith("ws-"):
        raise AnalysisWindowValidationError("telemetry_analysis_scope_not_explicit_facility")
    return scope


def _numeric_profiles(
    rows: Sequence[Mapping[str, Any]], numeric_columns: Sequence[str]
) -> tuple[Mapping[str, Any], ...]:
    profiles: list[Mapping[str, Any]] = []
    for column in numeric_columns:
        values = [float(row[column]) for row in rows if row.get(column) is not None]
        profiles.append(
            {
                "column": column,
                "count": len(values),
                "missing_count": len(rows) - len(values),
                "non_numeric_count": 0,
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / len(values),
                "constant_or_stuck": min(values) == max(values),
            }
        )
    return tuple(profiles)


def build_canonical_analysis_window(
    *,
    window_id: str,
    source_run_id: str,
    scope: TelemetryScopeRef | AuthenticatedPhase4Scope,
    system_id: str,
    asset_id: str | None,
    persisted_authority_digest: str,
    phase4_system_identity: ServerBoundSystemIdentityV2,
    observations: Sequence[Mapping[str, Any]],
    source_kind: str = "telemetry_connector",
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    minimum_signal_observations: int = 2,
    minimum_signal_coverage: float = 0.5,
    ingestion_report: Mapping[str, Any] | None = None,
    normalization_report: Mapping[str, Any] | None = None,
    data_quality: Mapping[str, Any] | None = None,
    sensor_health: Mapping[str, Any] | None = None,
    operating_mode: Mapping[str, Any] | None = None,
) -> CanonicalAnalysisWindow:
    """Validate authority and pivot eligible observations by canonical ID."""
    verified_scope = _scope_from(scope)
    if not isinstance(phase4_system_identity, ServerBoundSystemIdentityV2):
        raise AnalysisWindowValidationError(
            "telemetry_analysis_shared_authority_snapshot_required"
        )
    identity = phase4_system_identity
    persisted_digest = str(persisted_authority_digest or "").strip().lower()
    if (
        identity.resource_scope_id != verified_scope.resource_scope_id
        or identity.system_id != str(system_id or "").strip()
        or identity.authority_record_digest != persisted_digest
    ):
        raise AnalysisWindowValidationError(
            "telemetry_analysis_shared_authority_snapshot_mismatch"
        )
    if int(minimum_signal_observations) < 1:
        raise AnalysisWindowValidationError("telemetry_analysis_minimum_observations_invalid")
    if len(observations) > MAX_LINEAGE_RECORDS:
        raise AnalysisWindowValidationError("telemetry_analysis_window_observation_limit_exceeded")
    try:
        minimum_coverage = float(minimum_signal_coverage)
    except (TypeError, ValueError) as error:
        raise AnalysisWindowValidationError("telemetry_analysis_minimum_coverage_invalid") from error
    if not 0 < minimum_coverage <= 1:
        raise AnalysisWindowValidationError("telemetry_analysis_minimum_coverage_invalid")
    start = _aware_utc(window_start, "telemetry_analysis_window_start_invalid") if window_start else None
    end = _aware_utc(window_end, "telemetry_analysis_window_end_invalid") if window_end else None
    if start and end and end <= start:
        raise AnalysisWindowValidationError("telemetry_analysis_window_range_invalid")

    selected: list[tuple[datetime, Mapping[str, Any], ObservationLineage]] = []
    seen_signal_times: set[tuple[str, datetime]] = set()
    for observation in observations:
        if not isinstance(observation, Mapping):
            raise AnalysisWindowValidationError("telemetry_analysis_observation_invalid")
        if observation.get("analysis_eligible") is not True:
            continue
        if str(observation.get("quality_state") or "") != "good":
            continue
        if str(observation.get("system_id") or "").strip() != identity.system_id:
            continue
        observation_asset = _optional_text(observation.get("asset_id"))
        if observation_asset != _optional_text(asset_id):
            continue
        timestamp = _aware_utc(
            observation.get("observed_at_utc"), "telemetry_analysis_observation_timestamp_invalid"
        )
        if start is not None and timestamp < start:
            continue
        if end is not None and timestamp >= end:
            continue
        signal_id = _required_text(
            observation.get("canonical_signal_id") or observation.get("canonical_concept_id"),
            "telemetry_analysis_canonical_signal_id_invalid",
        )
        duplicate_key = (signal_id, timestamp)
        if duplicate_key in seen_signal_times:
            raise AnalysisWindowValidationError("telemetry_analysis_canonical_pivot_duplicate")
        seen_signal_times.add(duplicate_key)
        try:
            value = float(observation.get("normalized_value"))
        except (TypeError, ValueError) as error:
            raise AnalysisWindowValidationError("telemetry_analysis_value_non_numeric") from error
        if not math.isfinite(value):
            raise AnalysisWindowValidationError("telemetry_analysis_value_nonfinite")
        lineage = ObservationLineage.from_observation(observation)
        selected.append((timestamp, {**dict(observation), "_signal_id": signal_id, "_value": value}, lineage))
    if not selected:
        raise AnalysisWindowValidationError("telemetry_analysis_no_eligible_observations")

    timestamps = sorted({item[0] for item in selected})
    if len(timestamps) < 2:
        raise AnalysisWindowValidationError("telemetry_analysis_insufficient_time_coverage")
    counts: dict[str, int] = {}
    for _, observation, _ in selected:
        signal_id = str(observation["_signal_id"])
        counts[signal_id] = counts.get(signal_id, 0) + 1
    eligible_signals = tuple(
        sorted(
            signal_id
            for signal_id, count in counts.items()
            if count >= int(minimum_signal_observations)
            and count / len(timestamps) >= minimum_coverage
        )
    )
    if not eligible_signals:
        raise AnalysisWindowValidationError("telemetry_analysis_insufficient_signal_coverage")
    eligible_set = set(eligible_signals)
    rows_by_time: dict[datetime, dict[str, Any]] = {
        timestamp: {TIMESTAMP_COLUMN: timestamp.isoformat(), **{signal: None for signal in eligible_signals}}
        for timestamp in timestamps
    }
    lineage: list[ObservationLineage] = []
    catalog: dict[str, dict[str, Any]] = {}
    for timestamp, observation, observation_lineage in selected:
        signal_id = str(observation["_signal_id"])
        if signal_id not in eligible_set:
            continue
        rows_by_time[timestamp][signal_id] = observation["_value"]
        lineage.append(observation_lineage)
        entry = catalog.setdefault(
            signal_id,
            {
                "canonical_signal_id": signal_id,
                "canonical_signal_name": observation_lineage.canonical_signal_name,
                "display_name": observation_lineage.canonical_signal_name,
                "engineering_units": observation_lineage.canonical_unit,
                "canonical_unit": observation_lineage.canonical_unit,
                "column": signal_id,
            },
        )
        if (
            entry["canonical_signal_name"] != observation_lineage.canonical_signal_name
            or entry["canonical_unit"] != observation_lineage.canonical_unit
        ):
            raise AnalysisWindowValidationError("telemetry_analysis_canonical_signal_conflict")
    rows = tuple(rows_by_time[timestamp] for timestamp in timestamps if any(
        rows_by_time[timestamp][signal] is not None for signal in eligible_signals
    ))
    quality = {
        "status": "ready",
        "readiness": "ready",
        "eligible_observation_count": len(lineage),
        "eligible_signal_count": len(eligible_signals),
        "timestamp_count": len(rows),
        "minimum_signal_observations": int(minimum_signal_observations),
        "minimum_signal_coverage": minimum_coverage,
        **dict(data_quality or {}),
    }
    return CanonicalAnalysisWindow(
        window_id=window_id,
        source_kind=source_kind,
        source_run_id=source_run_id,
        phase4_scope=verified_scope,
        phase4_system_identity=identity,
        asset_id=asset_id,
        columns=(TIMESTAMP_COLUMN, *eligible_signals),
        rows=rows,
        numeric_profiles=_numeric_profiles(rows, eligible_signals),
        timestamp_column=TIMESTAMP_COLUMN,
        numeric_columns=eligible_signals,
        telemetry_signal_catalog=catalog,
        ingestion_report=_source_neutral_report(ingestion_report),
        normalization_report=_source_neutral_report(normalization_report),
        data_quality=_source_neutral_report(quality),
        sensor_health=_source_neutral_report(sensor_health),
        operating_mode=_source_neutral_report(operating_mode),
        observation_lineage=tuple(lineage),
    )


def _normalized_telemetry(window: CanonicalAnalysisWindow) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for row in window.rows:
        for signal_id in window.numeric_columns:
            if row.get(signal_id) is None:
                continue
            signal = window.telemetry_signal_catalog[signal_id]
            records.append(
                {
                    "timestamp": row[TIMESTAMP_COLUMN],
                    "tag_name": signal.get("display_name") or signal.get("canonical_signal_name"),
                    "value": row[signal_id],
                    "unit": signal.get("canonical_unit"),
                    "source_column": signal_id,
                    "quality": "good",
                    "canonical_signal_id": signal_id,
                }
            )
    return {
        "status": "ready",
        "source_kind": window.source_kind,
        "source_file": "",
        "timestamp_column": TIMESTAMP_COLUMN,
        "row_count": len(window.rows),
        "tag_count": len(window.numeric_columns),
        "record_count": len(records),
        "record_limit": len(records),
        "truncated": False,
        "records": records,
        "tags": [dict(window.telemetry_signal_catalog[item]) for item in window.numeric_columns],
        "signals": [dict(window.telemetry_signal_catalog[item]) for item in window.numeric_columns],
        "calculation_method": "Canonical normalized observations were projected by canonical signal identity.",
    }


def run_analysis_window(
    window: CanonicalAnalysisWindow,
    progress_reporter: Any | None = None,
    *,
    evaluator: Callable[..., dict[str, Any]] | None = None,
    lineage_sample_limit: int = DEFAULT_LINEAGE_SAMPLE_LIMIT,
) -> AnalysisWindowExecution:
    """Revalidate authority and invoke the authoritative SII entry point once."""
    if not isinstance(window, CanonicalAnalysisWindow):
        raise AnalysisWindowValidationError("canonical_analysis_window_required")
    if not isinstance(window.phase4_system_identity, ServerBoundSystemIdentityV2):
        raise AnalysisWindowValidationError("telemetry_analysis_system_identity_v2_required")
    identity = window.phase4_system_identity
    if identity.resource_scope_id != window.phase4_scope.resource_scope_id:
        raise AnalysisWindowValidationError("telemetry_analysis_identity_scope_mismatch")

    progress_callback = progress_reporter if callable(progress_reporter) else None
    if progress_callback is None and callable(getattr(progress_reporter, "report", None)):
        def progress_callback(step: str, fraction: float, metadata: dict[str, Any]) -> None:
            progress_reporter.report(
                stage="analysis",
                substage=step,
                completed_units=metadata.get("completed_units"),
                total_units=metadata.get("total_units"),
                unit_type=metadata.get("unit_type"),
                message=metadata.get("message"),
                metadata=metadata,
                force=bool(metadata.get("operation_complete")),
            )

    config = {
        "numeric_columns": list(window.numeric_columns),
        "row_count_total": len(window.rows),
        "ingestion_report": _source_neutral_report(window.ingestion_report),
        "normalization_report": _source_neutral_report(window.normalization_report),
        "source_run_id": window.source_run_id,
        "infrastructure_identity": {
            "tenant_id": window.phase4_scope.tenant_scope_id,
            "workspace_id": window.phase4_scope.workspace_id,
            "resource_scope_id": window.phase4_scope.resource_scope_id,
            "facility_id": window.phase4_scope.workspace_id,
            "system_id": identity.system_id,
            "asset_id": window.asset_id,
        },
    }
    authoritative_evaluator = evaluator or evaluate_sii
    try:
        sii_result = authoritative_evaluator(
            columns=list(window.columns),
            rows=[dict(row) for row in window.rows],
            numeric_profiles=[dict(item) for item in window.numeric_profiles],
            timestamp_column=window.timestamp_column,
            telemetry_signal_catalog={
                key: dict(item) for key, item in window.telemetry_signal_catalog.items()
            },
            data_quality=dict(window.data_quality),
            sensor_health=dict(window.sensor_health),
            operating_mode=dict(window.operating_mode),
            config=config,
            progress_callback=progress_callback,
            phase4_scope=window.phase4_scope,
        )
    except Exception as error:
        raise AnalysisWindowExecutionError("telemetry_analysis_engine_execution_failed") from error
    if not isinstance(sii_result, dict):
        raise AnalysisWindowExecutionError("telemetry_analysis_engine_result_invalid")
    if str(sii_result.get("status") or "").lower() == "failed":
        raise AnalysisWindowExecutionError("telemetry_analysis_engine_reported_failure")

    compatibility = sii_result.get("compatibility")
    compatibility = compatibility if isinstance(compatibility, dict) else {}
    lineage_summary = window.lineage_summary(sample_limit=lineage_sample_limit)
    result_payload = {
        "analysis_id": window.window_id,
        "run_id": window.source_run_id,
        "source_kind": window.source_kind,
        "source_type": "telemetry_connector",
        "row_count": len(window.rows),
        "column_count": len(window.columns),
        "columns": list(window.columns),
        "numeric_columns": list(window.numeric_columns),
        "sii_result": sii_result,
        "telemetry_signal_catalog": {
            key: dict(item) for key, item in window.telemetry_signal_catalog.items()
        },
        "data_quality": compatibility.get("data_quality") or dict(window.data_quality),
        "sensor_health": compatibility.get("sensor_health") or dict(window.sensor_health),
        "operating_mode": compatibility.get("operating_mode") or dict(window.operating_mode),
        "timestamp_profile": compatibility.get("timestamp_profile") or {},
        "baseline_analysis": compatibility.get("baseline_analysis") or {},
        "relationship_model": compatibility.get("relationship_model") or {},
        "operator_report": compatibility.get("operator_report") or {},
        "processing_trace": sii_result.get("processing_trace") or {},
        "telemetry_lineage": lineage_summary,
    }
    analysis_result = build_analysis_result(
        result_payload, normalized_telemetry=_normalized_telemetry(window)
    )
    return AnalysisWindowExecution(
        window_id=window.window_id,
        source_kind=window.source_kind,
        source_run_id=window.source_run_id,
        sii_result=MappingProxyType(dict(sii_result)),
        analysis_result=MappingProxyType(analysis_result),
        telemetry_lineage=MappingProxyType(lineage_summary),
    )


def run_upload_analysis_compatibility(
    *,
    evaluator: Callable[..., dict[str, Any]],
    evaluation_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    """Historical-upload adapter with an explicit one-call/no-retry contract."""
    if not callable(evaluator):
        raise TypeError("upload_analysis_evaluator_required")
    return evaluator(**dict(evaluation_kwargs))


def project_window_persistence(
    window: CanonicalAnalysisWindow,
    *,
    status: str = "eligible",
) -> tuple[dict[str, Any], tuple[dict[str, str], ...]]:
    """Pure projections a repository worker can persist transactionally."""
    summary = window.lineage_summary(sample_limit=0)
    window_record = project_analysis_window_persistence(
        window_id=window.window_id,
        tenant_scope_id=window.phase4_scope.tenant_scope_id,
        workspace_id=window.phase4_scope.workspace_id,
        resource_scope_id=window.phase4_scope.resource_scope_id,
        facility_id=window.phase4_scope.workspace_id,
        system_id=window.phase4_system_identity.system_id,
        asset_id=window.asset_id,
        source_run_id=window.source_run_id,
        window_start=window.window_start,
        window_end=window.window_end,
        authority_digest=window.phase4_system_identity.authority_record_digest,
        quality_summary={
            **dict(window.data_quality),
            "lineage_digest": summary["lineage_digest"],
            "observation_count": summary["observation_count"],
        },
        status=status,
    )
    join_records = project_analysis_window_observations(
        window_id=window.window_id,
        tenant_scope_id=window.phase4_scope.tenant_scope_id,
        workspace_id=window.phase4_scope.workspace_id,
        resource_scope_id=window.phase4_scope.resource_scope_id,
        facility_id=window.phase4_scope.workspace_id,
        lineage=window.observation_lineage,
    )
    return window_record, join_records


__all__ = [
    "ANALYSIS_WINDOW_CONTRACT_VERSION",
    "ANALYSIS_WINDOW_EXECUTION_VERSION",
    "AnalysisWindowExecution",
    "AnalysisWindowExecutionError",
    "AnalysisWindowValidationError",
    "CanonicalAnalysisWindow",
    "build_canonical_analysis_window",
    "project_window_persistence",
    "run_analysis_window",
    "run_upload_analysis_compatibility",
]
