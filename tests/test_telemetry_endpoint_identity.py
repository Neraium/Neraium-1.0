from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_domain import (
    ExternalSignalRecord,
    SignalMappingStatus,
    TelemetryScopeRef,
)
from app.services.telemetry_endpoint_identity import (
    ENDPOINT_IDENTITY_VERSION,
    physical_endpoint_id,
    project_physical_endpoint_identity,
    verify_physical_endpoint_identity,
)
from app.services.telemetry_ingestion import MappingSnapshot


CONNECTION = "00000000-0000-0000-0000-000000000001"
SIGNAL_A = "00000000-0000-0000-0000-000000000101"
SIGNAL_B = "00000000-0000-0000-0000-000000000102"
CONCEPT = "00000000-0000-0000-0000-000000000301"


@pytest.fixture
def records() -> tuple[MappingSnapshot, ExternalSignalRecord]:
    scope = TelemetryScopeRef(
        tenant_scope_id="tenant-a",
        workspace_id="facility-a",
        resource_scope_id=canonical_phase4_resource_scope_id("tenant-a", "facility-a"),
        facility_id="facility-a",
    )
    mapping = MappingSnapshot(
        scope=scope,
        connection_id=CONNECTION,
        external_tag_id="PUMP1.PRESSURE.A",
        external_signal_id=SIGNAL_A,
        mapping_id="00000000-0000-0000-0000-000000000201",
        revision=3,
        actor_id="operator-a",
        mapped_at=datetime(2026, 8, 20, tzinfo=UTC),
        authority_digest="a" * 64,
        facility_id=scope.facility_id,
        system_id="system-a",
        asset_id="pump-1",
        canonical_signal_id=CONCEPT,
        canonical_signal_name="discharge_pressure",
        source_unit="psi",
        canonical_unit="kPa",
        expected_dimension="pressure",
        conversion_id="psi_to_kpa",
        conversion_version="1",
        source_timezone="UTC",
    )
    signal = ExternalSignalRecord(
        signal_id=SIGNAL_A,
        scope=scope,
        connection_id=CONNECTION,
        external_tag_id="PUMP1.PRESSURE.A",
        external_tag_name="Pressure sensor A",
        canonical_signal_id=CONCEPT,
        system_id="system-a",
        asset_id="pump-1",
        enabled=True,
        mapping_status=SignalMappingStatus.MAPPED,
    )
    return mapping, signal


def test_identity_is_stable_versioned_and_distinct_from_concept(records) -> None:
    mapping, signal = records
    first = project_physical_endpoint_identity(mapping, signal)
    second = project_physical_endpoint_identity(mapping, signal)

    assert first == second
    assert first.contract_version == ENDPOINT_IDENTITY_VERSION
    assert first.endpoint_id == physical_endpoint_id(
        mapping.scope.resource_scope_id, CONNECTION, SIGNAL_A
    )
    assert first.endpoint_id != first.canonical_concept_id
    assert first.mapping_revision == 3
    assert first.mapping_id == mapping.mapping_id
    assert first.as_dict()["authority_digest"] == mapping.authority_digest
    assert verify_physical_endpoint_identity(first, mapping, signal)
    with pytest.raises(FrozenInstanceError):
        first.mapping_revision = 4  # type: ignore[misc]


def test_same_concept_distinct_signals_remain_distinct(records) -> None:
    mapping, signal = records
    second_mapping = replace(
        mapping,
        external_signal_id=SIGNAL_B,
        external_tag_id="PUMP1.PRESSURE.B",
        mapping_id="00000000-0000-0000-0000-000000000202",
        authority_digest="b" * 64,
    )
    second_signal = replace(
        signal, signal_id=SIGNAL_B, external_tag_id="PUMP1.PRESSURE.B"
    )
    first_identity = project_physical_endpoint_identity(mapping, signal)
    second_identity = project_physical_endpoint_identity(second_mapping, second_signal)

    assert first_identity.canonical_concept_id == second_identity.canonical_concept_id
    assert first_identity.endpoint_id != second_identity.endpoint_id
    assert first_identity.external_signal_id != second_identity.external_signal_id
    # The current database constraint still prevents simultaneously enabling
    # these two mappings in one hierarchy; this tests identity representation.


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mapping_id", "00000000-0000-0000-0000-000000000299"),
        ("mapping_revision", 4),
        ("connection_id", "00000000-0000-0000-0000-000000000002"),
        ("external_signal_id", SIGNAL_B),
        ("system_id", "system-b"),
        ("asset_id", "pump-2"),
        ("authority_digest", "b" * 64),
        ("canonical_concept_id", "00000000-0000-0000-0000-000000000302"),
    ],
)
def test_substituted_authority_fails_verification(records, field, value) -> None:
    mapping, signal = records
    identity = project_physical_endpoint_identity(mapping, signal)
    replacements = {field: value}
    if field in {"connection_id", "external_signal_id"}:
        replacements["endpoint_id"] = physical_endpoint_id(
            identity.resource_scope_id,
            replacements.get("connection_id", identity.connection_id),
            replacements.get("external_signal_id", identity.external_signal_id),
        )
    assert not verify_physical_endpoint_identity(
        replace(identity, **replacements), mapping, signal
    )


def test_endpoint_cannot_alias_concept_or_use_unversioned_contract(records) -> None:
    mapping, signal = records
    identity = project_physical_endpoint_identity(mapping, signal)
    with pytest.raises(ValueError, match="identity_mismatch"):
        replace(identity, endpoint_id=CONCEPT)
    with pytest.raises(ValueError, match="concept_alias"):
        replace(identity, canonical_concept_id=identity.endpoint_id)
    with pytest.raises(ValueError, match="version_invalid"):
        replace(identity, contract_version="relationship-lineage.v1")


@pytest.mark.parametrize(
    "change",
    [
        {"connection_id": "00000000-0000-0000-0000-000000000002"},
        {"signal_id": SIGNAL_B},
        {"system_id": "system-b"},
        {"asset_id": "pump-2"},
        {"canonical_signal_id": "00000000-0000-0000-0000-000000000302"},
        {"enabled": False},
        {"mapping_status": SignalMappingStatus.UNMAPPED},
    ],
)
def test_source_record_mismatch_fails_closed(records, change) -> None:
    mapping, signal = records
    with pytest.raises(ValueError):
        project_physical_endpoint_identity(mapping, replace(signal, **change))


def test_mapping_disabled_or_wrong_scope_fails_closed(records) -> None:
    mapping, signal = records
    with pytest.raises(ValueError, match="not_enabled"):
        project_physical_endpoint_identity(replace(mapping, enabled=False), signal)
    other_scope = TelemetryScopeRef(
        tenant_scope_id="tenant-b",
        workspace_id="facility-a",
        resource_scope_id=canonical_phase4_resource_scope_id("tenant-b", "facility-a"),
        facility_id="facility-a",
    )
    with pytest.raises(ValueError, match="source_mismatch"):
        project_physical_endpoint_identity(mapping, replace(signal, scope=other_scope))


def test_mapping_snapshot_is_not_mutated_or_reinterpreted(records) -> None:
    mapping, signal = records
    project_physical_endpoint_identity(mapping, signal)
    assert mapping.revision == 3
    assert mapping.canonical_signal_id == CONCEPT
    assert mapping.external_signal_id == SIGNAL_A
    assert mapping.authority_digest == "a" * 64
