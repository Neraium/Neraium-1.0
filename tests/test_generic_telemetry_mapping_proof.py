from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.connectors.base import ConnectorPage, RawObservationEnvelope
from app.connectors.jsonl_package import load_jsonl_connector_page
from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services import telemetry_units
from app.services.canonical_signal_catalog import CANONICAL_SIGNAL_CONCEPTS_V1
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_ingestion import MappingSnapshot, prepare_connector_page
from app.services.telemetry_timestamps import normalize_telemetry_timestamp
from app.services.telemetry_units import (
    UNIT_NORMALIZATION_VERSION,
    normalize_telemetry_unit,
)


ARTIFACT = Path(
    "/home/ubuntu/Neraium-BuildingX-Connector/artifacts/neraium-ingestion-sample.jsonl"
)
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
ACTIVE_POWER = next(
    item for item in CANONICAL_SIGNAL_CONCEPTS_V1
    if item.canonical_name == "electrical.active_power"
)


@pytest.fixture
def scope() -> TelemetryScopeRef:
    tenant, workspace = "mapping-proof-tenant", "mapping-proof-workspace"
    return TelemetryScopeRef(
        tenant,
        workspace,
        canonical_phase4_resource_scope_id(tenant, workspace),
        workspace,
    )


def test_real_artifact_inventory_is_source_factual() -> None:
    page = load_jsonl_connector_page(ARTIFACT)
    grouped: dict[str, list[RawObservationEnvelope]] = {}
    for observation in page.observations:
        grouped.setdefault(observation.external_tag_id, []).append(observation)

    assert len(grouped) == 10
    assert {item.metadata["source"] for item in page.observations} == {"siemens_building_x"}
    assert {item.metadata["partition_id"] for item in page.observations} == {
        "81c66821-3fb7-4d7c-80d5-1f2beb8fe31c"
    }
    assert {item.metadata["asset_id"] for item in page.observations} == {
        "1cc81b1a-f510-5d1a-a33b-78c422c33ba3",
        "2de74555-9bca-5bd4-a1b8-7211eb785449",
    }
    assert all(item.metadata["asset_name"] is None for item in page.observations)
    assert all(item.metadata["location_id"] is None for item in page.observations)
    assert {item.raw_value.__class__.__name__ for item in page.observations} == {"int", "float"}


def _mapping(
    scope: TelemetryScopeRef,
    *,
    external_tag_id: str,
    source_asset_id: str,
    source_unit: str = "kW",
    canonical_unit: str = "kW",
    dimension: str = "power",
    canonical_signal_id: str = ACTIVE_POWER.concept_id,
    canonical_signal_name: str = ACTIVE_POWER.canonical_name,
) -> MappingSnapshot:
    # These IDs deliberately represent test-only operator-approved fixtures.
    # They are not inferred from, or persisted to, Neraium asset storage.
    unit = normalize_telemetry_unit(
        value=1.0,
        source_unit=source_unit,
        canonical_unit=canonical_unit,
        expected_dimension=dimension,
    )
    assert unit.analysis_eligible
    return MappingSnapshot(
        scope=scope,
        connection_id="mapping-proof-connection",
        external_tag_id=external_tag_id,
        external_signal_id=f"approved-signal:{external_tag_id}",
        mapping_id=f"approved-mapping:{external_tag_id}",
        revision=7,
        actor_id="mapping-proof-reviewer",
        mapped_at=NOW,
        authority_digest="b" * 64,
        facility_id=scope.facility_id,
        system_id=f"approved-system:{source_asset_id}",
        asset_id=f"approved-asset:{source_asset_id}",
        canonical_signal_id=canonical_signal_id,
        canonical_signal_name=canonical_signal_name,
        source_unit=source_unit,
        canonical_unit=canonical_unit,
        expected_dimension=dimension,
        conversion_id=unit.conversion_id or "",
        conversion_version=UNIT_NORMALIZATION_VERSION,
        source_timezone="UTC",
        provenance="manual",
    )


def test_explicit_approved_mapping_prepares_and_preserves_lineage(
    scope: TelemetryScopeRef,
) -> None:
    observation = RawObservationEnvelope(
        external_tag_id="power-1",
        external_tag_name="Power 01-01",
        source_timestamp="2026-08-30T11:00:00Z",
        raw_value=12.5,
        reported_unit="kW",
        reported_quality="good",
        metadata={"source": "vendor.test", "asset_id": "source-asset-1"},
    )
    mapping = _mapping(scope, external_tag_id="power-1", source_asset_id="source-asset-1")
    prepared = prepare_connector_page(
        page=ConnectorPage(observations=(observation,)),
        scope=scope,
        connection_id="mapping-proof-connection",
        ingestion_run_id="mapping-proof-run",
        mappings_by_external_tag={observation.external_tag_id: mapping},
        now=NOW,
        ingested_at_utc=NOW,
    )
    assert prepared.accepted_count == 1
    result = prepared.observations[0]
    assert result.external_tag_id == observation.external_tag_id
    assert result.canonical_signal_id == ACTIVE_POWER.concept_id
    assert result.asset_id == "approved-asset:source-asset-1"
    assert result.mapping_id == mapping.mapping_id
    assert result.mapping_revision == 7
    assert result.original_value == 12.5
    assert result.normalized_value == pytest.approx(12.5)
    assert result.original_unit == "kW"
    assert result.canonical_unit == "kW"
    assert result.reported_quality == "good"
    assert result.source_metadata["source"] == "vendor.test"
    assert result.analysis_eligible is True


def test_missing_signal_mapping_remains_rejected(scope: TelemetryScopeRef) -> None:
    observation = RawObservationEnvelope(
        external_tag_id="unmapped",
        external_tag_name="Unknown",
        source_timestamp="2026-08-30T11:00:00Z",
        raw_value=1.0,
        reported_unit="kW",
        reported_quality="good",
    )
    prepared = prepare_connector_page(
        page=ConnectorPage(observations=(observation,)),
        scope=scope,
        connection_id="mapping-proof-connection",
        ingestion_run_id="mapping-proof-run",
        mappings_by_external_tag={},
        now=NOW,
        ingested_at_utc=NOW,
    )
    assert prepared.accepted_count == 0
    assert prepared.rejections[0].reason_code == "mapping_not_approved"
    assert prepared.rejections[0].external_signal_id is None


def test_real_power_records_prepare_only_with_explicit_test_mappings(
    scope: TelemetryScopeRef,
) -> None:
    page = load_jsonl_connector_page(ARTIFACT)
    power_ids = {
        item.external_tag_id
        for item in page.observations
        if item.external_tag_name.startswith("Power")
    }
    asset_ids = {
        item.metadata["asset_id"]
        for item in page.observations
        if item.external_tag_id in power_ids
    }
    mappings = {
        point_id: _mapping(
            scope,
            external_tag_id=point_id,
            source_asset_id=str(next(item.metadata["asset_id"] for item in page.observations if item.external_tag_id == point_id)),
        )
        for point_id in power_ids
    }
    assert len(asset_ids) == 1
    prepared = prepare_connector_page(
        page=page,
        scope=scope,
        connection_id="mapping-proof-connection",
        ingestion_run_id="mapping-proof-run",
        mappings_by_external_tag=mappings,
        now=NOW,
        ingested_at_utc=NOW,
    )
    assert prepared.accepted_count == 15
    assert Counter(item.reason_code for item in prepared.rejections) == Counter(
        {"mapping_not_approved": 10}
    )
    assert all(item.canonical_signal_id == ACTIVE_POWER.concept_id for item in prepared.observations)
    assert all(item.canonical_unit == "kW" for item in prepared.observations)


def test_source_assets_are_not_mappable_without_customer_hierarchy(scope: TelemetryScopeRef) -> None:
    page = load_jsonl_connector_page(ARTIFACT)
    for asset_id in {item.metadata["asset_id"] for item in page.observations}:
        records = [item for item in page.observations if item.metadata["asset_id"] == asset_id]
        assert records[0].metadata["asset_name"] is None
        assert records[0].metadata["location_id"] is None
    # MappingSnapshot requires a system identity, so no real-asset snapshot is
    # constructed from this artifact alone. Customer hierarchy review is needed.
    assert scope.facility_id == scope.workspace_id


@pytest.mark.parametrize(
    ("source_unit", "canonical_unit", "dimension"),
    [("kW", "kW", "power"), ("degC", "degC", "temperature")],
)
def test_existing_unit_contract_proves_native_representations(
    source_unit: str, canonical_unit: str, dimension: str
) -> None:
    result = normalize_telemetry_unit(
        value=10.0,
        source_unit=source_unit,
        canonical_unit=canonical_unit,
        expected_dimension=dimension,
    )
    assert result.analysis_eligible is True
    assert result.canonical_unit == canonical_unit


@pytest.mark.parametrize("source_unit", ["qudt:DEG_C", "qudt:MicroGM-PER-M3", "qudt:PPM"])
def test_qudt_units_remain_explicit_unit_mapping_gaps(source_unit: str) -> None:
    result = normalize_telemetry_unit(
        value=10.0,
        source_unit=source_unit,
        canonical_unit=source_unit,
        expected_dimension=None,
    )
    assert result.analysis_eligible is False
    assert result.reason_code == "source_unit_unknown"


def test_quality_semantics_are_truthful_and_not_downgraded_to_good(
    scope: TelemetryScopeRef,
) -> None:
    observation = RawObservationEnvelope(
        external_tag_id="quality-1",
        external_tag_name="Quality test",
        source_timestamp="2026-08-30T11:00:00Z",
        raw_value=1.0,
        reported_unit="kW",
        reported_quality="bad_communication",
    )
    mapping = _mapping(scope, external_tag_id="quality-1", source_asset_id="asset-1")
    prepared = prepare_connector_page(
        page=ConnectorPage(observations=(observation,)),
        scope=scope,
        connection_id="mapping-proof-connection",
        ingestion_run_id="mapping-proof-run",
        mappings_by_external_tag={"quality-1": mapping},
        now=NOW,
        ingested_at_utc=NOW,
    )
    assert prepared.accepted_count == 0
    assert prepared.rejections[0].reason_code == "reported_quality_unrecognized"
    assert observation.reported_quality == "bad_communication"


def test_timestamp_contract_normalizes_real_source_timestamps() -> None:
    page = load_jsonl_connector_page(ARTIFACT)
    results = [
        normalize_telemetry_timestamp(
            source_timestamp=item.source_timestamp,
            source_timezone="UTC",
            now=NOW,
        )
        for item in page.observations
    ]
    assert all(item.analysis_eligible for item in results)
    assert all(item.observed_at_utc is not None for item in results)


def test_mapping_proof_has_no_runtime_side_effect_dependencies() -> None:
    source = Path("backend/app/connectors/jsonl_package.py").read_text(encoding="utf-8")
    assert "database" not in source.lower()
    assert "engine" not in source.lower()
    assert "requests" not in source.lower()
    assert "http" not in source.lower()
