from __future__ import annotations

import pytest

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.services import runtime_db
from app.services.dataset_scope import build_dataset_scope, dataset_scope_context
from app.services.facility_context import (
    facility_context_storage_key,
    facility_system_authority_digest,
    read_facility_context_for_scope,
    resolve_telemetry_analysis_authority,
    write_facility_context,
)
from app.services.phase4_scope import (
    ServerBoundSystemIdentity,
    ServerBoundSystemIdentityV2,
    authenticated_phase4_scope_context,
)
from app.services.telemetry_domain import TelemetryScopeRef


def _scope(
    *, tenant: str = "tenant-a", workspace: str = "ws-plant-a"
) -> AuthenticatedPhase4Scope:
    return AuthenticatedPhase4Scope(tenant_scope_id=tenant, workspace_id=workspace)


def _telemetry_scope(scope: AuthenticatedPhase4Scope) -> TelemetryScopeRef:
    return TelemetryScopeRef(
        tenant_scope_id=scope.tenant_scope_id,
        workspace_id=scope.workspace_id,
        resource_scope_id=scope.resource_scope_id,
        facility_id=scope.workspace_id,
    )


def _system(system_id: str = "ahu-1", *asset_ids: str) -> dict[str, object]:
    return {
        "system_id": system_id,
        "name": f"System {system_id}",
        "system_type": "air_handler",
        "equipment_ids": list(asset_ids),
    }


def _facility(
    systems: list[dict[str, object]],
    equipment: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "contract_version": "facility-context.v1",
        "systems": systems,
        "equipment": list(equipment or []),
    }


def _persist(scope: AuthenticatedPhase4Scope, payload: dict[str, object]) -> None:
    runtime_db.upsert_latest_payload(
        facility_context_storage_key(
            tenant_scope_id=scope.tenant_scope_id,
            workspace_id=scope.workspace_id,
        ),
        payload,
    )


def test_v2_identity_is_resource_scoped_and_v1_remains_upload_only() -> None:
    resource_scope_id = _scope().resource_scope_id
    v1 = ServerBoundSystemIdentity(
        system_id="ahu-1",
        dataset_scope_storage_id="dataset-storage-for-operator-a",
        authority_record_digest="a" * 64,
    )
    v2 = ServerBoundSystemIdentityV2(
        system_id="ahu-1",
        resource_scope_id=resource_scope_id,
        authority_record_digest="a" * 64,
    )

    assert v1.as_dict() == {
        "version": "server-bound-system-identity.v1",
        "system_id": "ahu-1",
        "authority": "facility-context.v1",
        "dataset_scope_storage_id": "dataset-storage-for-operator-a",
        "authority_record_digest": "a" * 64,
    }
    assert v2.as_dict() == {
        "version": "server-bound-system-identity.v2",
        "system_id": "ahu-1",
        "authority": "facility-context.v1",
        "resource_scope_id": resource_scope_id,
        "authority_record_digest": "a" * 64,
    }
    assert "resource_scope_id" not in v1.as_dict()
    assert "dataset_scope_storage_id" not in v2.as_dict()
    assert not isinstance(v1, ServerBoundSystemIdentityV2)


def test_two_operators_resolve_the_same_current_resource_identity(tmp_path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    phase_scope = _scope()
    system = _system("ahu-1", "fan-1")
    _persist(
        phase_scope,
        _facility(
            [system],
            [{"equipment_id": "fan-1", "system_id": "ahu-1"}],
        ),
    )
    digest = facility_system_authority_digest(system)

    # Operator identity is intentionally absent from both authority inputs.
    operator_a = resolve_telemetry_analysis_authority(
        _telemetry_scope(phase_scope), "ahu-1", "fan-1", digest
    )
    operator_b = resolve_telemetry_analysis_authority(
        phase_scope, "ahu-1", "fan-1", digest
    )

    assert operator_a.available and operator_b.available
    assert operator_a.identity == operator_b.identity
    assert operator_a.identity is not None
    assert operator_a.identity.resource_scope_id == phase_scope.resource_scope_id
    assert "operator" not in operator_a.identity.identity_digest


def test_scoped_facility_read_does_not_fall_back_to_another_workspace(tmp_path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    authorized = _scope(workspace="ws-plant-a")
    other = _scope(workspace="ws-plant-b")
    _persist(authorized, _facility([_system("ahu-1")]))

    assert read_facility_context_for_scope(authorized) is not None
    assert read_facility_context_for_scope(other) is None
    resolution = resolve_telemetry_analysis_authority(
        other,
        "ahu-1",
        None,
        facility_system_authority_digest(_system("ahu-1")),
    )
    assert resolution.identity is None
    assert resolution.reason == "facility_context_authority_unavailable"


def test_existing_facility_write_also_publishes_stable_server_authority(tmp_path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    phase_scope = _scope()
    operator_dataset = build_dataset_scope(
        tenant_id="tenant-a",
        user_id="operator-a@example.com",
        workspace_id="legacy-upload-storage",
    )
    payload = _facility([_system("ahu-1")])

    with dataset_scope_context(operator_dataset), authenticated_phase4_scope_context(
        phase_scope
    ):
        written = write_facility_context(payload, actor="operator-a@example.com")

    stable = read_facility_context_for_scope(phase_scope)
    assert stable == written
    assert stable is not None
    assert stable["updated_by"] == "operator-a@example.com"


@pytest.mark.parametrize("workspace", ["default", "plant-a", ""])
def test_personal_free_form_and_missing_scope_fail_closed(workspace: str) -> None:
    if workspace:
        authority: object = _scope(workspace=workspace)
    else:
        authority = object()
    resolution = resolve_telemetry_analysis_authority(
        authority, "ahu-1", None, "a" * 64  # type: ignore[arg-type]
    )
    assert resolution.identity is None
    assert resolution.reason == "telemetry_scope_unauthorized"


def test_missing_duplicate_stale_and_wrong_asset_authority_fail_closed(
    tmp_path,
) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    scope = _scope()
    system = _system("ahu-1", "fan-1")
    digest = facility_system_authority_digest(system)
    _persist(
        scope,
        _facility(
            [system],
            [
                {"equipment_id": "fan-1", "system_id": "ahu-1"},
                {"equipment_id": "fan-2", "system_id": "ahu-2"},
            ],
        ),
    )

    cases = [
        ("missing", None, digest, "system_id_not_registered"),
        ("ahu-1", "missing", digest, "asset_not_unique_or_registered"),
        ("ahu-1", "fan-2", digest, "asset_system_mismatch"),
        ("ahu-1", "fan-1", "b" * 64, "authority_digest_stale"),
        ("ahu-1", "fan-1", "not-a-digest", "authority_digest_invalid"),
    ]
    for system_id, asset_id, persisted_digest, reason in cases:
        resolution = resolve_telemetry_analysis_authority(
            scope, system_id, asset_id, persisted_digest
        )
        assert resolution.identity is None
        assert resolution.reason == reason

    _persist(scope, _facility([system, system]))
    duplicate = resolve_telemetry_analysis_authority(
        scope, "ahu-1", "fan-1", digest
    )
    assert duplicate.identity is None
    assert duplicate.reason == "system_id_not_unique"


def test_asset_identity_alias_conflict_fails_closed(tmp_path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    scope = _scope()
    system = _system("ahu-1", "fan-1")
    _persist(
        scope,
        _facility(
            [system],
            [
                {
                    "asset_id": "fan-1",
                    "equipment_id": "legacy-fan-1",
                    "system_id": "ahu-1",
                }
            ],
        ),
    )

    resolution = resolve_telemetry_analysis_authority(
        scope,
        "ahu-1",
        "fan-1",
        facility_system_authority_digest(system),
    )
    assert resolution.identity is None
    assert resolution.reason == "asset_identity_ambiguous"
