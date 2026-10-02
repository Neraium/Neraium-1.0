"""Opt-in connector analysis with physical endpoint series and V2 lineage.

The scheduler selects this module only from server configuration. It never
accepts a client-requested version or treats concept metadata as series identity.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.engine.sii_engine import evaluate_sii
from app.services.phase4_scope import ServerBoundSystemIdentityV2
from app.services.relationship_evidence_binding import REGISTRY
from app.services.telemetry_analysis_window import AnalysisWindowValidationError, TIMESTAMP_COLUMN, _numeric_profiles
from app.services.telemetry_analysis_window_v2 import (
    EndpointBindingV2, EndpointAnalysisWindowV2, EndpointSeriesV2,
    build_endpoint_analysis_window_v2,
)
from app.services.telemetry_domain import ExternalSignalRecord, TelemetryScopeRef
from app.services.telemetry_endpoint_identity import PhysicalEndpointIdentity, project_physical_endpoint_identity
from app.services.telemetry_ingestion import MappingSnapshot
from app.services.telemetry_lineage import ObservationLineage
from app.services.telemetry_endpoint_execution_v2_repository import EndpointExecutionV2Error


EXECUTION_IDENTITY_VERSION = "physical-endpoint-keyed.v2"


def _bindings(
    scope: TelemetryScopeRef, connection_id: str, observations: Sequence[Mapping[str, Any]],
    authority_rows: Sequence[Mapping[str, Any]],
) -> tuple[EndpointBindingV2, ...]:
    requested = {str(item.get("external_signal_id")) for item in observations}
    if not requested or len(authority_rows) != len(requested):
        raise AnalysisWindowValidationError("endpoint_analysis_authority_incomplete")
    bindings = []
    for row in authority_rows:
        signal_id = str(row.get("external_signal_id") or "")
        if (signal_id not in requested or str(row.get("connection_id") or "") != connection_id
                or row.get("signal_enabled") is not True or row.get("mapping_enabled") is not True
                or row.get("mapping_status") != "mapped"):
            raise AnalysisWindowValidationError("endpoint_analysis_authority_invalid")
        mapping = MappingSnapshot(
            scope=scope, connection_id=connection_id,
            external_tag_id=str(row["external_tag_id"]), external_signal_id=signal_id,
            mapping_id=str(row["mapping_id"]), revision=int(row["revision"]),
            actor_id=str(row["mapped_by"]), mapped_at=row["mapped_at"],
            authority_digest=str(row["authority_digest"]), facility_id=scope.facility_id,
            system_id=str(row["system_id"]), asset_id=row.get("asset_id"),
            canonical_signal_id=str(row["canonical_concept_id"]),
            canonical_signal_name=str(row["canonical_signal_name"]),
            source_unit=str(row["source_unit"]), canonical_unit=str(row["canonical_unit"]),
            expected_dimension=str(row["expected_dimension"]),
            conversion_id=str(row["conversion_id"]),
            conversion_version=str(row["conversion_version"]),
            source_timezone=str(row["source_timezone"]),
            provenance=str(row["provenance"]), enabled=True,
        )
        signal = ExternalSignalRecord(
            signal_id=signal_id, scope=scope, connection_id=connection_id,
            external_tag_id=str(row["external_tag_id"]),
            external_tag_name=str(row["external_tag_name"]),
            canonical_signal_id=mapping.canonical_signal_id,
            system_id=mapping.system_id, asset_id=mapping.asset_id,
            enabled=True, mapping_status="mapped",
        )
        bindings.append(EndpointBindingV2(project_physical_endpoint_identity(mapping, signal), mapping, signal))
    if len({binding.identity.endpoint_id for binding in bindings}) != len(requested):
        raise AnalysisWindowValidationError("endpoint_analysis_authority_ambiguous")
    return tuple(bindings)


def _evaluate(window: EndpointAnalysisWindowV2, *, evaluator: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    """Pass ordinary numerical series to the unchanged SII evaluator."""
    scope = AuthenticatedPhase4Scope(
        tenant_scope_id=window.scope.tenant_scope_id,
        workspace_id=window.scope.workspace_id,
        resource_scope_id=window.scope.resource_scope_id,
    )
    columns = [TIMESTAMP_COLUMN, *window.numeric_columns]
    rows = [dict(row) for row in window.rows]
    catalog = {
        item.series_id: {
            "column": item.series_id,
            "canonical_signal_id": item.identity.canonical_concept_id,
            "canonical_signal_name": item.canonical_signal_name,
            "display_name": item.canonical_signal_name,
            "engineering_units": item.canonical_unit,
            "canonical_unit": item.canonical_unit,
            "physical_dimension": item.expected_dimension,
        }
        for item in window.series
    }
    config = {
        "numeric_columns": list(window.numeric_columns),
        "row_count_total": len(rows),
        "source_run_id": window.source_run_id,
        "infrastructure_identity": {
            "tenant_id": scope.tenant_scope_id,
            "workspace_id": scope.workspace_id,
            "resource_scope_id": scope.resource_scope_id,
            "facility_id": scope.workspace_id,
            "system_id": window.system_identity.system_id,
            "asset_id": window.asset_id,
            # The existing Phase 4 model store derives a different model ID.
            # No V1 behavioral memory is loaded or updated by this V2 run.
            "configured_model_id": (
                f"{EXECUTION_IDENTITY_VERSION}:"
                f"{window.series[0].identity.connection_id}:"
                f"{window.system_identity.system_id}:{window.asset_id or ''}:"
                f"{window.schema_fingerprint}"
            ),
        },
    }
    result = (evaluator or evaluate_sii)(
        columns=columns, rows=rows,
        numeric_profiles=[dict(item) for item in _numeric_profiles(tuple(rows), window.numeric_columns)],
        timestamp_column=TIMESTAMP_COLUMN,
        telemetry_signal_catalog=catalog,
        data_quality={"status": "ready", "readiness": "ready"},
        sensor_health={}, operating_mode={}, config=config,
        phase4_scope=scope,
        phase4_system_identity=window.system_identity,
        phase4_asset_id=window.asset_id,
        phase4_observation_lineage=window.observation_lineage,
        # No V1 concept-keyed endpoint descriptor or temporal state is supplied.
        canonical_endpoint_identity=None,
        relationship_persistence_state=None,
    )
    if not isinstance(result, dict) or result.get("status") == "failed":
        raise RuntimeError("endpoint_analysis_engine_failed")
    return result


def _pairs(window: EndpointAnalysisWindowV2, result: Mapping[str, Any]) -> list[tuple[Any, Mapping[str, Any], Mapping[str, Any]]]:
    model = ((result.get("compatibility") or {}).get("relationship_model") or {})
    candidates = [
        *(model.get("top_relationship_changes") or []),
        *((model.get("relationship_graph") or {}).get("edges") or []),
    ]
    registry = result.get(REGISTRY) or {}
    records = registry.get("records") or {}
    pairs = []
    seen = set()
    for candidate in candidates:
        source = candidate.get("relationship_source_evidence") or {}
        columns = source.get("columns")
        if not isinstance(columns, list) or len(columns) != 2 or any(column not in window.numeric_columns for column in columns):
            raise AnalysisWindowValidationError("endpoint_analysis_relationship_identity_invalid")
        ref = candidate.get("relationship_evidence_ref") or candidate.get("relationship_evidence_id")
        evidence = records.get(ref) if ref else source
        if not isinstance(evidence, Mapping):
            raise AnalysisWindowValidationError("endpoint_analysis_relationship_evidence_missing")
        pair = window.relationship_pair(columns[0], columns[1])
        if pair.ref in seen:
            continue
        seen.add(pair.ref)
        pairs.append((pair, candidate, evidence))
    return pairs


def run_post_ingestion_analysis_v2(
    *, repository: Any, lineage_repository: Any, execution_repository: Any,
    scope: TelemetryScopeRef,
    connection_id: str, source_run_id: str, system_id: str, asset_id: str | None,
    window_start: datetime, window_end: datetime, persisted_authority_digest: str,
    evaluator: Callable[..., dict[str, Any]] | None = None,
    progress_reporter: Any | None = None,
) -> Any:
    """Run one server-selected V2 window and verify every persisted relationship."""
    from app.services.telemetry_analysis_service import TelemetryAnalysisServiceResult, deterministic_analysis_window_id
    if not isinstance(scope, TelemetryScopeRef) or lineage_repository is None or execution_repository is None:
        raise AnalysisWindowValidationError("endpoint_analysis_server_authority_required")
    identity = repository.resolve_analysis_authority_snapshot(
        scope, system_id=system_id, asset_id=asset_id,
        authority_digest=persisted_authority_digest,
    )
    if not isinstance(identity, ServerBoundSystemIdentityV2):
        raise AnalysisWindowValidationError("endpoint_analysis_scope_authority_unavailable")
    observations = repository.list_analysis_eligible_observations(
        scope, connection_id=connection_id, source_run_id=None,
        system_id=system_id, asset_id=asset_id, asset_filter_applied=True,
        window_start=window_start, window_end=window_end,
        authority_digest=persisted_authority_digest,
    )
    if not observations:
        raise AnalysisWindowValidationError("endpoint_analysis_observations_missing")
    source_ids = {str(item.get("external_signal_id")) for item in observations}
    authority_rows = repository.list_analysis_endpoint_authority(
        scope, connection_id=connection_id, external_signal_ids=tuple(source_ids),
    )
    bindings = _bindings(scope, connection_id, observations, authority_rows)
    base_id = deterministic_analysis_window_id(
        scope=scope, connection_id=connection_id, source_run_id=source_run_id,
        system_id=system_id, asset_id=asset_id, window_start=window_start,
        window_end=window_end, authority_digest=persisted_authority_digest,
    )
    window_id = str(uuid5(UUID(base_id), EXECUTION_IDENTITY_VERSION))
    window = build_endpoint_analysis_window_v2(
        window_id=window_id, source_run_id=source_run_id, scope=scope,
        system_identity=identity, asset_id=asset_id,
        bindings=bindings, observations=observations,
    )
    existing = execution_repository.load_window_row(scope, window_id=window.window_id)
    if existing is not None:
        pair_rows = execution_repository.list_window_pairs(scope, window_id=window.window_id)
        pairs = tuple(window.relationship_pair(item["source_endpoint_id"], item["target_endpoint_id"])
                      for item in pair_rows)
        if sorted(pair.ref for pair in pairs) != existing.get("relationship_refs"):
            raise EndpointExecutionV2Error("endpoint_execution_replay_relationship_mismatch")
        replay = execution_repository.read_execution(
            scope, window=window, pairs=pairs, lineage_repository=lineage_repository,
        )
        if replay is None or replay["ref"] != existing.get("execution_ref"):
            raise EndpointExecutionV2Error("endpoint_execution_replay_invalid")
        return TelemetryAnalysisServiceResult(
            window_id=window_id, status="completed",
            result_id=replay["ref"], artifact_digest=replay["ref"].split(":", 1)[1],
            reused_existing=True, contract_version=EXECUTION_IDENTITY_VERSION,
        )
    result = _evaluate(window, evaluator=evaluator)
    artifacts = []
    evaluated_pairs = _pairs(window, result)
    if not evaluated_pairs:
        return TelemetryAnalysisServiceResult(
            window_id=window_id, status="ineligible",
            reason_code="endpoint_analysis_no_relationship_evidence",
            persisted=False, contract_version=EXECUTION_IDENTITY_VERSION,
        )
    for pair, candidate, evidence in evaluated_pairs:
        artifact = lineage_repository.persist(
            scope, window=window, pair=pair, result=candidate, evidence=evidence,
        )
        if lineage_repository.read(scope, window=window, pair=pair) != artifact:
            raise AnalysisWindowValidationError("endpoint_analysis_readback_mismatch")
        artifacts.append(artifact)
    pairs = tuple(pair for pair, _, _ in evaluated_pairs)
    execution = execution_repository.persist_execution(
        scope, window=window, result=result, pairs=pairs,
        lineage_repository=lineage_repository,
    )
    if execution_repository.read_execution(
        scope, window=window, pairs=pairs, lineage_repository=lineage_repository,
    ) != execution:
        raise AnalysisWindowValidationError("endpoint_analysis_execution_readback_mismatch")
    return TelemetryAnalysisServiceResult(
        window_id=window_id, status="completed",
        result_id=execution["ref"],
        artifact_digest=execution["ref"].split(":", 1)[1],
        contract_version=EXECUTION_IDENTITY_VERSION,
    )


def read_persisted_execution_v2(
    *, repository: Any, lineage_repository: Any, execution_repository: Any,
    scope: TelemetryScopeRef, connection_id: str, source_run_id: str,
    system_id: str, asset_id: str | None, execution_ref: str,
) -> dict[str, Any]:
    """Rebuild V2 authority from server records before returning stored evidence."""
    row = execution_repository.load_execution_row(scope, execution_ref=execution_ref)
    if row is None or any((
        str(row.get("connection_id")) != connection_id,
        str(row.get("source_run_id")) != source_run_id,
        row.get("system_id") != system_id,
        row.get("asset_id") != asset_id,
    )):
        raise EndpointExecutionV2Error("endpoint_execution_not_found")
    raw = row.get("window_payload")
    if not isinstance(raw, Mapping) or raw.get("contract_version") != "telemetry-analysis-window.v2":
        raise EndpointExecutionV2Error("endpoint_execution_window_invalid")
    try:
        raw_series = raw["series"]
        identities = tuple(PhysicalEndpointIdentity(**item["endpoint_identity"]) for item in raw_series)
        digest_set = {item.authority_digest for item in identities}
        if len(digest_set) != 1:
            raise EndpointExecutionV2Error("endpoint_execution_authority_mismatch")
        authority_digest = next(iter(digest_set))
        system_identity = repository.resolve_analysis_authority_snapshot(
            scope, system_id=system_id, asset_id=asset_id,
            authority_digest=authority_digest,
        )
        if not isinstance(system_identity, ServerBoundSystemIdentityV2):
            raise EndpointExecutionV2Error("endpoint_execution_authority_unavailable")
        lineage = tuple(ObservationLineage(
            **{**item, "observed_at_utc": datetime.fromisoformat(item["observed_at_utc"])}
        ) for item in raw["observation_lineage"])
        series = tuple(EndpointSeriesV2(
            identity=identity,
            canonical_signal_name=item["canonical_signal_name"],
            source_unit=item["source_unit"], canonical_unit=item["canonical_unit"],
            expected_dimension=item["expected_dimension"],
            conversion_id=item["conversion_id"],
            conversion_version=item["conversion_version"],
            mapping_provenance=item["mapping_provenance"],
            observation_ids=tuple(item["observation_ids"]),
        ) for item, identity in zip(raw_series, identities, strict=True))
        window = EndpointAnalysisWindowV2(
            window_id=raw["window_id"], source_run_id=raw["source_run_id"],
            scope=scope, system_identity=system_identity, asset_id=raw["asset_id"],
            series=series, rows=tuple(raw["rows"]), observation_lineage=lineage,
        )
        if window.as_dict() != raw:
            raise EndpointExecutionV2Error("endpoint_execution_window_mismatch")
        authority_rows = repository.list_analysis_endpoint_authority(
            scope, connection_id=connection_id,
            external_signal_ids=tuple(item.external_signal_id for item in identities),
        )
        live_bindings = _bindings(scope, connection_id, raw["observation_lineage"], authority_rows)
        if {item.identity for item in live_bindings} != set(identities):
            raise EndpointExecutionV2Error("endpoint_execution_mapping_stale")
        pair_rows = execution_repository.list_window_pairs(scope, window_id=window.window_id)
        pairs = tuple(window.relationship_pair(item["source_endpoint_id"], item["target_endpoint_id"])
                      for item in pair_rows)
        if sorted(item.ref for item in pairs) != row.get("relationship_refs") or any(
            item.ref != pair_row["pair_ref"] for item, pair_row in zip(pairs, pair_rows, strict=True)
        ):
            raise EndpointExecutionV2Error("endpoint_execution_relationship_mismatch")
        execution = execution_repository.read_execution(
            scope, window=window, pairs=pairs, lineage_repository=lineage_repository,
        )
        if execution is None or execution["ref"] != execution_ref:
            raise EndpointExecutionV2Error("endpoint_execution_readback_mismatch")
        return execution
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, EndpointExecutionV2Error):
            raise
        raise EndpointExecutionV2Error("endpoint_execution_readback_invalid") from exc
