from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.phase4_scope import ServerBoundSystemIdentityV2
from app.services.telemetry_analysis_window import AnalysisWindowValidationError
from app.services.telemetry_analysis_window_v2 import (
    EndpointBindingV2,
    build_endpoint_analysis_window_v2,
)
from app.services.telemetry_domain import ExternalSignalRecord, SignalMappingStatus, TelemetryScopeRef
from app.services.telemetry_endpoint_identity import project_physical_endpoint_identity
from app.services.telemetry_ingestion import MappingSnapshot


CONNECTION = "00000000-0000-0000-0000-000000000001"
CONCEPT_PRESSURE = "00000000-0000-0000-0000-000000000301"
CONCEPT_FLOW = "00000000-0000-0000-0000-000000000302"
DIGEST = "a" * 64
START = datetime(2026, 8, 25, tzinfo=UTC)


def _scope() -> TelemetryScopeRef:
    tenant, workspace = "tenant-a", "ws-facility-a"
    return TelemetryScopeRef(
        tenant_scope_id=tenant,
        workspace_id=workspace,
        resource_scope_id=canonical_phase4_resource_scope_id(tenant, workspace),
        facility_id=workspace,
    )


def _binding(index: int, concept: str = CONCEPT_PRESSURE) -> EndpointBindingV2:
    scope = _scope()
    signal_id = f"00000000-0000-0000-0000-{index:012d}"
    tag = f"PUMP1.SENSOR.{index}"
    mapping = MappingSnapshot(
        scope=scope,
        connection_id=CONNECTION,
        external_tag_id=tag,
        external_signal_id=signal_id,
        mapping_id=f"00000000-0000-0000-0001-{index:012d}",
        revision=3,
        actor_id="operator-a",
        mapped_at=START,
        authority_digest=DIGEST,
        facility_id=scope.facility_id,
        system_id="system-a",
        asset_id="pump-1",
        canonical_signal_id=concept,
        canonical_signal_name="discharge_pressure" if concept == CONCEPT_PRESSURE else "flow",
        source_unit="psi",
        canonical_unit="kPa",
        expected_dimension="pressure",
        conversion_id="psi_to_kpa",
        conversion_version="1",
        source_timezone="UTC",
    )
    signal = ExternalSignalRecord(
        signal_id=signal_id,
        scope=scope,
        connection_id=CONNECTION,
        external_tag_id=tag,
        external_tag_name=tag,
        canonical_signal_id=concept,
        system_id="system-a",
        asset_id="pump-1",
        enabled=True,
        mapping_status=SignalMappingStatus.MAPPED,
    )
    return EndpointBindingV2(project_physical_endpoint_identity(mapping, signal), mapping, signal)


def _observation(binding: EndpointBindingV2, minute: int) -> dict:
    mapping = binding.mapping
    timestamp = START + timedelta(minutes=minute)
    return {
        "observation_id": f"obs-{mapping.external_signal_id}-{minute}",
        "connection_id": mapping.connection_id,
        "ingestion_run_id": "run-a",
        "external_signal_id": mapping.external_signal_id,
        "mapping_id": mapping.mapping_id,
        "mapping_revision": mapping.revision,
        "canonical_signal_id": mapping.canonical_signal_id,
        "canonical_signal_name": mapping.canonical_signal_name,
        "system_id": mapping.system_id,
        "asset_id": mapping.asset_id,
        "external_tag_id": mapping.external_tag_id,
        "source_timestamp_raw": timestamp.isoformat(),
        "source_timezone": "UTC",
        "source_offset": "+00:00",
        "timestamp_normalization_version": "timestamp-normalization.v1",
        "observed_at_utc": timestamp,
        "original_unit": mapping.source_unit,
        "canonical_unit": mapping.canonical_unit,
        "conversion_id": mapping.conversion_id,
        "conversion_version": mapping.conversion_version,
        "source_record_digest": f"{minute + 1:064x}",
        "mapping_authority_digest": mapping.authority_digest,
        "analysis_eligible": True,
        "quality_state": "good",
        "normalized_value": float(100 + minute),
    }


def _window(bindings=None, observations=None):
    bindings = tuple(bindings or (_binding(1), _binding(2), _binding(3, CONCEPT_FLOW)))
    observations = observations or tuple(
        _observation(binding, minute) for minute in (0, 1) for binding in bindings
    )
    scope = _scope()
    return build_endpoint_analysis_window_v2(
        window_id="window-a",
        source_run_id="run-a",
        scope=scope,
        system_identity=ServerBoundSystemIdentityV2(
            system_id="system-a",
            resource_scope_id=scope.resource_scope_id,
            authority_record_digest=DIGEST,
        ),
        asset_id="pump-1",
        bindings=bindings,
        observations=observations,
    )


def test_same_concept_endpoints_remain_separate_series_with_semantic_metadata() -> None:
    window = _window()
    pressure = [item for item in window.series if item.identity.canonical_concept_id == CONCEPT_PRESSURE]
    assert window.contract_version == "telemetry-analysis-window.v2"
    assert len(pressure) == 2
    assert pressure[0].series_id != pressure[1].series_id
    assert set(window.numeric_columns) == {item.series_id for item in window.series}
    assert all(series_id in row for row in window.rows for series_id in window.numeric_columns)
    assert all(item.as_dict()["canonical_concept_id"] == CONCEPT_PRESSURE for item in pressure)
    assert window.as_dict()["schema_fingerprint"].startswith("telemetry-analysis-schema.v2:")


def test_same_endpoint_cannot_appear_twice() -> None:
    first = _binding(1)
    with pytest.raises(AnalysisWindowValidationError, match="endpoint_duplicate"):
        _window((first, first))


def test_endpoint_substitution_changes_schema_and_relationship_ref() -> None:
    first = _window((_binding(1), _binding(3, CONCEPT_FLOW)))
    second = _window((_binding(2), _binding(3, CONCEPT_FLOW)))
    assert first.schema_fingerprint != second.schema_fingerprint
    assert first.content_digest != second.content_digest
    assert first.relationship_pair(first.numeric_columns[0], first.numeric_columns[1]).ref != second.relationship_pair(
        second.numeric_columns[0], second.numeric_columns[1]
    ).ref


def test_same_concept_relationship_sources_remain_distinct() -> None:
    window = _window()
    pressure = [item.series_id for item in window.series if item.identity.canonical_concept_id == CONCEPT_PRESSURE]
    flow = next(item.series_id for item in window.series if item.identity.canonical_concept_id == CONCEPT_FLOW)
    left = window.relationship_pair(pressure[0], flow)
    right = window.relationship_pair(pressure[1], flow)
    assert left.ref != right.ref
    assert left.as_dict()["contract_version"] == "relationship-endpoint-pair.v2"


@pytest.mark.parametrize("field,value", [
    ("mapping_revision", 4),
    ("mapping_id", "00000000-0000-0000-0001-000000000999"),
    ("canonical_signal_id", CONCEPT_FLOW),
    ("system_id", "system-b"),
    ("asset_id", "pump-2"),
    ("mapping_authority_digest", "b" * 64),
    ("external_signal_id", "00000000-0000-0000-0000-000000000999"),
])
def test_observation_authority_mismatch_fails_closed(field, value) -> None:
    binding = _binding(1)
    observations = (_observation(binding, 0), _observation(binding, 1))
    changed = dict(observations[0], **{field: value})
    with pytest.raises(AnalysisWindowValidationError, match="observation_"):
        _window((binding,), (changed, observations[1]))


def test_missing_or_stale_projection_fails_closed() -> None:
    binding = _binding(1)
    with pytest.raises(AnalysisWindowValidationError, match="binding_invalid"):
        EndpointBindingV2(None, binding.mapping, binding.signal)  # type: ignore[arg-type]
    with pytest.raises(AnalysisWindowValidationError, match="binding_invalid"):
        EndpointBindingV2(binding.identity, replace(binding.mapping, revision=4), binding.signal)
    with pytest.raises(AnalysisWindowValidationError, match="binding_invalid"):
        EndpointBindingV2(binding.identity, replace(binding.mapping, authority_digest="b" * 64), binding.signal)
    with pytest.raises(ValueError, match="authority_digest_invalid"):
        replace(binding.identity, authority_digest="")


def test_unsupported_window_version_and_v1_memory_fail_closed() -> None:
    window = _window()
    with pytest.raises(AnalysisWindowValidationError, match="version_invalid"):
        replace(window, contract_version="canonical-analysis-window.v1")
    with pytest.raises(AnalysisWindowValidationError, match="prior_memory_unsupported"):
        window.relationship_pair(
            window.numeric_columns[0], window.numeric_columns[1],
            prior_memory={"state_schema": "relationship-temporal-state.v1"},
        )
    with pytest.raises(AnalysisWindowValidationError, match="version_invalid"):
        replace(
            window.relationship_pair(window.numeric_columns[0], window.numeric_columns[1]),
            contract_version="relationship-lineage.v1",
        )


def test_direct_window_construction_cannot_misattribute_lineage() -> None:
    window = _window()
    first = window.series[0]
    with pytest.raises(AnalysisWindowValidationError, match="series_lineage_invalid"):
        replace(window, series=(replace(first, observation_ids=("not-an-observation",)), *window.series[1:]))
    with pytest.raises(AnalysisWindowValidationError, match="lineage_authority_mismatch"):
        replace(
            window,
            observation_lineage=(replace(window.observation_lineage[0], mapping_revision=4), *window.observation_lineage[1:]),
        )


def test_v2_is_explicit_and_does_not_call_numerical_engine(monkeypatch) -> None:
    from app.services import telemetry_analysis_window as v1

    monkeypatch.setattr(v1, "evaluate_sii", lambda **_: pytest.fail("V2 construction ran SII"))
    window = _window()
    assert len(window.rows) == 2
    assert v1.ANALYSIS_WINDOW_CONTRACT_VERSION == "canonical-analysis-window.v1"
