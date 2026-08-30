from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.connectors.base import ConnectorPage, RawObservationEnvelope
from app.connectors.jsonl_package import load_jsonl_connector_page
from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services import telemetry_units
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_ingestion import MappingSnapshot, prepare_connector_page
from app.services.telemetry_units import normalize_telemetry_unit, unit_key


ARTIFACT = Path(
    "/home/ubuntu/Neraium-BuildingX-Connector/artifacts/neraium-ingestion-sample.jsonl"
)
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
def scope() -> TelemetryScopeRef:
    tenant, workspace = "alias-proof-tenant", "alias-proof-workspace"
    return TelemetryScopeRef(
        tenant,
        workspace,
        canonical_phase4_resource_scope_id(tenant, workspace),
        workspace,
    )


def _mapping(scope: TelemetryScopeRef, *, tag: str, source_unit: str, canonical_unit: str, dimension: str) -> MappingSnapshot:
    result = normalize_telemetry_unit(
        value=1.0,
        source_unit=source_unit,
        canonical_unit=canonical_unit,
        expected_dimension=dimension,
    )
    assert result.analysis_eligible
    return MappingSnapshot(
        scope=scope,
        connection_id="alias-proof-connection",
        external_tag_id=tag,
        external_signal_id=f"test-signal:{tag}",
        mapping_id=f"test-mapping:{tag}",
        revision=1,
        actor_id="alias-proof-reviewer",
        mapped_at=NOW,
        authority_digest="c" * 64,
        facility_id=scope.facility_id,
        system_id="test-approved-system",
        asset_id="test-approved-asset",
        canonical_signal_id="test-approved-canonical-signal",
        canonical_signal_name="test-approved-signal",
        source_unit=source_unit,
        canonical_unit=canonical_unit,
        expected_dimension=dimension,
        conversion_id=result.conversion_id or "",
        conversion_version=result.conversion_version,
        source_timezone="UTC",
    )


def test_qudt_celsius_has_an_existing_canonical_concept_but_no_current_alias() -> None:
    result = normalize_telemetry_unit(
        value=24.0,
        source_unit="qudt:DEG_C",
        canonical_unit="degC",
        expected_dimension="temperature",
    )
    assert result.analysis_eligible is False
    assert result.reason_code == "source_unit_unknown"
    native = normalize_telemetry_unit(
        value=24.0,
        source_unit="degC",
        canonical_unit="degC",
        expected_dimension="temperature",
    )
    assert native.analysis_eligible is True
    assert native.canonical_unit == "degC"


@pytest.mark.parametrize("source_unit", ["qudt:MicroGM-PER-M3", "qudt:PPM"])
def test_qudt_particulate_and_ppm_remain_unsupported(source_unit: str) -> None:
    result = normalize_telemetry_unit(
        value=1.0,
        source_unit=source_unit,
        canonical_unit=source_unit,
        expected_dimension=None,
    )
    assert result.analysis_eligible is False
    assert result.reason_code == "source_unit_unknown"


def test_test_only_celsius_alias_preserves_source_unit_and_value(monkeypatch: pytest.MonkeyPatch) -> None:
    # This is deliberately scoped to the proof. It demonstrates the smallest
    # generic registry addition without changing the dirty user-owned module.
    monkeypatch.setitem(
        telemetry_units._SUPPORTED_LOOKUP,
        unit_key("qudt:DEG_C"),
        telemetry_units._SUPPORTED_LOOKUP[unit_key("degC")],
    )
    result = normalize_telemetry_unit(
        value=24.0,
        source_unit="qudt:DEG_C",
        canonical_unit="degC",
        expected_dimension="temperature",
    )
    assert result.analysis_eligible is True
    assert result.original_unit == "qudt:DEG_C"
    assert result.canonical_unit == "degC"
    assert result.canonical_value == pytest.approx(24.0)
    assert result.dimension == "temperature"


def test_test_only_celsius_alias_increases_real_preparation_without_touching_signal_gate(
    scope: TelemetryScopeRef, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = load_jsonl_connector_page(ARTIFACT)
    power = [item for item in page.observations if item.external_tag_name.startswith("Power")]
    room_temperature = next(item for item in page.observations if item.external_tag_name == "RoomT0")
    # The three power points share the same test-only explicit signal fixture.
    mappings = {
        item.external_tag_id: _mapping(
            scope,
            tag=item.external_tag_id,
            source_unit="kW",
            canonical_unit="kW",
            dimension="power",
        )
        for item in {item.external_tag_id: item for item in power}.values()
    }
    monkeypatch.setitem(
        telemetry_units._SUPPORTED_LOOKUP,
        unit_key("qudt:DEG_C"),
        telemetry_units._SUPPORTED_LOOKUP[unit_key("degC")],
    )
    mappings[room_temperature.external_tag_id] = _mapping(
        scope,
        tag=room_temperature.external_tag_id,
        source_unit="qudt:DEG_C",
        canonical_unit="degC",
        dimension="temperature",
    )
    prepared = prepare_connector_page(
        page=page,
        scope=scope,
        connection_id="alias-proof-connection",
        ingestion_run_id="alias-proof-run",
        mappings_by_external_tag=mappings,
        now=NOW,
        ingested_at_utc=NOW,
    )
    assert prepared.accepted_count == 16
    assert prepared.rejected_count == 9
    assert Counter(item.reason_code for item in prepared.rejections) == Counter(
        {"mapping_not_approved": 9}
    )
    result = next(item for item in prepared.observations if item.external_tag_id == room_temperature.external_tag_id)
    assert result.original_unit == "qudt:DEG_C"
    assert result.canonical_unit == "degC"
    assert result.original_value == room_temperature.raw_value
    assert result.normalized_value == pytest.approx(room_temperature.raw_value)


def test_bad_communication_has_no_truthful_existing_translation(scope: TelemetryScopeRef) -> None:
    observation = RawObservationEnvelope(
        external_tag_id="quality-gap",
        external_tag_name="Communication quality test",
        source_timestamp="2026-08-30T11:00:00Z",
        raw_value=0.0,
        reported_quality="bad_communication",
        reported_unit="kW",
    )
    mapping = _mapping(scope, tag="quality-gap", source_unit="kW", canonical_unit="kW", dimension="power")
    prepared = prepare_connector_page(
        page=ConnectorPage(observations=(observation,)),
        scope=scope,
        connection_id="alias-proof-connection",
        ingestion_run_id="alias-proof-run",
        mappings_by_external_tag={"quality-gap": mapping},
        now=NOW,
        ingested_at_utc=NOW,
    )
    assert prepared.accepted_count == 0
    assert prepared.rejections[0].reason_code == "reported_quality_unrecognized"
    assert prepared.rejections[0].reported_quality == "bad_communication"
