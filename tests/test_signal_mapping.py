from __future__ import annotations

from datetime import UTC, datetime
import uuid
from typing import Any

import pytest

from app.engine.sii.behavioral_model_contract import (
    AuthenticatedPhase4Scope,
    canonical_phase4_resource_scope_id,
)
from app.services.dataset_scope import build_dataset_scope, dataset_scope_context
from app.services.phase4_scope import (
    ServerBoundSystemIdentity,
    authenticated_phase4_scope_context,
)
from app.services.signal_registry import (
    AuthorizedSignalHierarchy,
    FacilityContextHierarchyAuthority,
    SignalRegistryError,
    SignalRegistryService,
)
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.workspace_authorization import (
    WorkspaceContext,
    current_workspace_context,
    set_current_workspace_context,
)


CONNECTION_ID = "00000000-0000-0000-0000-000000000001"
SIGNAL_ID = "00000000-0000-0000-0000-000000000002"
CONCEPT_ID = "00000000-0000-0000-0000-000000000003"


class _Repository:
    def __init__(self, *, source_unit: str = "°F") -> None:
        self.source_unit = source_unit
        self.saved: dict[str, Any] | None = None

    def get_mapping_context(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "source_unit": self.source_unit,
            "canonical_unit": "degC",
            "physical_dimension": "temperature",
            "canonical_name": "supply_air_temperature",
        }

    def save_signal_mapping(self, _scope: Any, **kwargs: Any) -> dict[str, Any]:
        self.saved = kwargs
        return kwargs

    def disable_signal_mapping(self, _scope: Any, **kwargs: Any) -> dict[str, Any]:
        return kwargs


@pytest.fixture
def scope() -> TelemetryScopeRef:
    return TelemetryScopeRef(
        tenant_scope_id="tenant-a",
        workspace_id="facility-a",
        facility_id="facility-a",
        resource_scope_id=canonical_phase4_resource_scope_id(
            "tenant-a", "facility-a"
        ),
    )


def _authority(
    scope: TelemetryScopeRef, system_id: str, asset_id: str | None
) -> AuthorizedSignalHierarchy:
    return AuthorizedSignalHierarchy(
        facility_id=scope.facility_id,
        system_id=system_id,
        asset_id=asset_id,
        authority_digest="a" * 64,
    )


def test_mapping_uses_server_authority_and_versioned_explicit_units(
    scope: TelemetryScopeRef,
) -> None:
    repository = _Repository()
    uuids = iter((uuid.UUID(int=10), uuid.UUID(int=11)))
    service = SignalRegistryService(
        repository,
        _authority,
        uuid_factory=lambda: next(uuids),
        clock=lambda: datetime(2026, 8, 25, tzinfo=UTC),
    )
    mapped = service.map_signal(
        scope,
        connection_id=CONNECTION_ID,
        signal_id=SIGNAL_ID,
        system_id="ahu-1",
        asset_id="fan-1",
        canonical_concept_id=CONCEPT_ID,
        source_unit="degF",
        source_timezone="America/New_York",
        actor_id="operator@example.test",
        expected_cadence_seconds=300,
    )

    assert repository.saved is not None
    assert mapped["system_id"] == "ahu-1"
    assert mapped["asset_id"] == "fan-1"
    assert mapped["canonical_signal_name"] == "supply_air_temperature"
    assert mapped["conversion_id"] == "f_to_c"
    assert mapped["conversion_version"] == "neraium.telemetry.units/v1"
    assert mapped["authority_digest"] == "a" * 64
    assert mapped["authority_snapshot"] == {
        "contract_version": "telemetry-analysis-authority-snapshot.v1",
        "facility_id": scope.facility_id,
        "system_id": "ahu-1",
        "asset_id": "fan-1",
    }


def test_mapping_rejects_operator_unit_that_conflicts_with_discovery(
    scope: TelemetryScopeRef,
) -> None:
    service = SignalRegistryService(_Repository(source_unit="degC"), _authority)
    with pytest.raises(SignalRegistryError, match="source_unit_mismatch"):
        service.map_signal(
            scope,
            connection_id=CONNECTION_ID,
            signal_id=SIGNAL_ID,
            system_id="ahu-1",
            asset_id=None,
            canonical_concept_id=CONCEPT_ID,
            source_unit="degF",
            source_timezone="UTC",
            actor_id="operator@example.test",
        )


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("provenance", "automatic_guess", "provenance_invalid"),
        ("expected_cadence_seconds", 86_401, "cadence_invalid"),
        ("source_timezone", "Local/Guess", "timezone_invalid"),
    ],
)
def test_mapping_rejects_unapproved_provenance_and_unbounded_settings(
    scope: TelemetryScopeRef, field: str, value: Any, code: str
) -> None:
    kwargs: dict[str, Any] = {
        "connection_id": CONNECTION_ID,
        "signal_id": SIGNAL_ID,
        "system_id": "ahu-1",
        "asset_id": None,
        "canonical_concept_id": CONCEPT_ID,
        "source_unit": "degF",
        "source_timezone": "UTC",
        "actor_id": "operator@example.test",
    }
    kwargs[field] = value
    with pytest.raises(SignalRegistryError, match=code):
        SignalRegistryService(_Repository(), _authority).map_signal(scope, **kwargs)


def test_production_authority_rejects_asset_owned_by_another_system(
    scope: TelemetryScopeRef, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset_scope = build_dataset_scope(
        user_id="operator@example.test",
        tenant_id="tenant-a",
        workspace_id="facility-a",
    )

    class _Resolution:
        reason = "resolved_explicit_registered_system"
        identity = ServerBoundSystemIdentity(
            system_id="ahu-1",
            dataset_scope_storage_id=dataset_scope.storage_id,
            authority_record_digest="b" * 64,
        )

    monkeypatch.setattr(
        "app.services.facility_context.resolve_server_bound_system_identity",
        lambda **_kwargs: _Resolution(),
    )
    monkeypatch.setattr(
        "app.services.facility_context.read_facility_context",
        lambda: {
            "systems": [
                {"system_id": "ahu-1", "equipment_ids": ["fan-1"]},
                {"system_id": "ahu-2", "equipment_ids": ["fan-2"]},
            ],
            "equipment": [
                {"equipment_id": "fan-2", "system_id": "ahu-2"},
            ],
        },
    )
    monkeypatch.setattr(
        "app.services.telemetry_scope.current_telemetry_scope", lambda: scope
    )
    with dataset_scope_context(dataset_scope), pytest.raises(
        SignalRegistryError, match="asset_system_mismatch"
    ):
        FacilityContextHierarchyAuthority()(scope, "ahu-1", "fan-2")


def test_production_authority_rejects_ambiguous_asset_compatibility_record(
    scope: TelemetryScopeRef, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset_scope = build_dataset_scope(
        user_id="operator@example.test",
        tenant_id="tenant-a",
        workspace_id="facility-a",
    )

    class _Resolution:
        reason = "resolved_explicit_registered_system"
        identity = ServerBoundSystemIdentity(
            system_id="ahu-1",
            dataset_scope_storage_id=dataset_scope.storage_id,
            authority_record_digest="d" * 64,
        )

    monkeypatch.setattr(
        "app.services.facility_context.resolve_server_bound_system_identity",
        lambda **_kwargs: _Resolution(),
    )
    monkeypatch.setattr(
        "app.services.facility_context.read_facility_context",
        lambda: {
            "systems": [{"system_id": "ahu-1", "equipment_ids": ["fan-1"]}],
            "equipment": [
                {
                    "asset_id": "fan-1",
                    "equipment_id": "legacy-fan-1",
                    "system_id": "ahu-1",
                }
            ],
        },
    )
    monkeypatch.setattr(
        "app.services.telemetry_scope.current_telemetry_scope", lambda: scope
    )
    with dataset_scope_context(dataset_scope), pytest.raises(
        SignalRegistryError, match="asset_identity_ambiguous"
    ):
        FacilityContextHierarchyAuthority()(scope, "ahu-1", "fan-1")


def test_production_authority_rejects_other_attested_workspace(
    scope: TelemetryScopeRef, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = build_dataset_scope(
        user_id="operator@example.test", tenant_id="tenant-a", workspace_id="default"
    )
    other = TelemetryScopeRef(
        tenant_scope_id="tenant-a",
        workspace_id="facility-b",
        facility_id="facility-b",
        resource_scope_id=canonical_phase4_resource_scope_id(
            "tenant-a", "facility-b"
        ),
    )
    monkeypatch.setattr(
        "app.services.telemetry_scope.current_telemetry_scope", lambda: other
    )
    with dataset_scope_context(dataset), pytest.raises(
        SignalRegistryError, match="scope_authority_mismatch"
    ):
        FacilityContextHierarchyAuthority()(scope, "ahu-1", None)


def test_production_authority_uses_outer_facility_with_inner_default_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = build_dataset_scope(
        user_id="operator@example.test",
        tenant_id="tenant-a",
        workspace_id="default",
    )
    workspace = WorkspaceContext(
        workspace_id="ws-plant-a",
        display_name="Plant A",
        kind="facility",
        membership_active=True,
        dataset_scope=dataset,
    )
    phase = AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a", workspace_id="ws-plant-a"
    )
    telemetry_scope = TelemetryScopeRef(
        tenant_scope_id="tenant-a",
        workspace_id="ws-plant-a",
        facility_id="ws-plant-a",
        resource_scope_id=phase.resource_scope_id,
    )

    class _Resolution:
        reason = "resolved_explicit_registered_system"
        identity = ServerBoundSystemIdentity(
            system_id="ahu-1",
            dataset_scope_storage_id=dataset.storage_id,
            authority_record_digest="c" * 64,
        )

    monkeypatch.setattr(
        "app.services.facility_context.resolve_server_bound_system_identity",
        lambda **_kwargs: _Resolution(),
    )
    monkeypatch.setattr(
        "app.services.facility_context.read_facility_context",
        lambda: {
            "systems": [{"system_id": "ahu-1", "equipment_ids": ["fan-1"]}],
            "equipment": [
                {"equipment_id": "fan-1", "system_id": "ahu-1"},
            ],
        },
    )
    previous_workspace = current_workspace_context()
    set_current_workspace_context(workspace)
    try:
        with dataset_scope_context(dataset), authenticated_phase4_scope_context(phase):
            resolved = FacilityContextHierarchyAuthority()(
                telemetry_scope, "ahu-1", "fan-1"
            )
    finally:
        set_current_workspace_context(previous_workspace)
    assert resolved.facility_id == "ws-plant-a"
    assert resolved.asset_id == "fan-1"
    assert resolved.authority_digest == "c" * 64
