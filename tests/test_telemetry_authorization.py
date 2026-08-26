from __future__ import annotations

import pytest

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.services.dataset_scope import build_dataset_scope
from app.services.phase4_scope import authenticated_phase4_scope_context
from app.services.telemetry_scope import (
    OPAQUE_TELEMETRY_NOT_FOUND,
    OPAQUE_TELEMETRY_WORKSPACE_NOT_FOUND,
    TelemetryResourceNotFoundError,
    TelemetryScopeUnavailableError,
    apply_authoritative_scope,
    current_telemetry_scope,
    normalize_audit_actor,
    require_scoped_resource,
    resource_matches_scope,
    telemetry_scope_from_authority,
)
from app.services.workspace_authorization import (
    WorkspaceContext,
    current_workspace_context,
    set_current_workspace_context,
)


def _workspace(
    *,
    tenant_id: str = "tenant-a",
    user_id: str = "operator-a@example.com",
    workspace_id: str = "ws-facility-a",
    kind: str = "facility",
    membership_active: bool = True,
) -> WorkspaceContext:
    return WorkspaceContext(
        workspace_id=workspace_id,
        display_name="Synthetic facility",
        kind=kind,
        membership_active=membership_active,
        dataset_scope=build_dataset_scope(
            tenant_id=tenant_id,
            user_id=user_id,
            workspace_id="resource-data",
        ),
    )


def _scope(context: WorkspaceContext):
    return telemetry_scope_from_authority(
        workspace_context=context,
        phase4_scope=AuthenticatedPhase4Scope(
            tenant_scope_id=context.dataset_scope.tenant_id,
            workspace_id=context.workspace_id,
        ),
    )


def test_authorized_users_share_facility_resource_scope_and_user_is_audit_only() -> None:
    operator_a = _workspace(user_id="operator-a@example.com")
    operator_b = _workspace(user_id="operator-b@example.com")

    scope_a = _scope(operator_a)
    scope_b = _scope(operator_b)

    assert scope_a == scope_b
    assert scope_a.resource_scope_id == scope_b.resource_scope_id
    assert "operator-a" not in scope_a.resource_scope_id
    assert "operator-b" not in scope_b.resource_scope_id
    assert normalize_audit_actor(
        {"authenticated": True, "auth_subject": "Operator-A@Example.com"}
    ) == "operator-a@example.com"


def test_current_scope_uses_only_request_bound_server_authority() -> None:
    context = _workspace()
    authority = AuthenticatedPhase4Scope(
        tenant_scope_id=context.dataset_scope.tenant_id,
        workspace_id=context.workspace_id,
    )
    previous_workspace = current_workspace_context()
    try:
        set_current_workspace_context(context)
        with authenticated_phase4_scope_context(authority):
            assert current_telemetry_scope() == _scope(context)
    finally:
        set_current_workspace_context(previous_workspace)


def test_different_tenants_and_workspaces_never_share_authority() -> None:
    base = _scope(_workspace())
    other_tenant = _scope(_workspace(tenant_id="tenant-b"))
    other_workspace = _scope(_workspace(workspace_id="ws-facility-b"))

    assert len(
        {base.resource_scope_id, other_tenant.resource_scope_id, other_workspace.resource_scope_id}
    ) == 3
    assert not resource_matches_scope(
        {
            "tenant_scope_id": base.tenant_scope_id,
            "workspace_id": base.workspace_id,
            "resource_scope_id": base.resource_scope_id,
            "facility_id": base.facility_id,
        },
        other_tenant,
    )


def test_payload_scope_claims_cannot_override_server_authority() -> None:
    scope = _scope(_workspace())
    payload = apply_authoritative_scope(
        {
            "tenant_scope_id": "tenant-attacker",
            "workspace_id": "ws-attacker",
            "resource_scope_id": "phase4-scope:attacker",
            "facility_id": "facility-attacker",
            "user_id": "attacker@example.com",
            "scope_storage_id": "attacker-storage",
            "name": "Synthetic connection",
        },
        scope=scope,
    )

    assert payload == {
        "tenant_scope_id": scope.tenant_scope_id,
        "workspace_id": scope.workspace_id,
        "resource_scope_id": scope.resource_scope_id,
        "facility_id": scope.facility_id,
        "name": "Synthetic connection",
    }


@pytest.mark.parametrize(
    "context",
    [
        _workspace(workspace_id="default", kind="personal"),
        _workspace(workspace_id="plant-a", kind="personal"),
        _workspace(membership_active=False),
    ],
)
def test_personal_free_form_and_inactive_workspaces_are_rejected(
    context: WorkspaceContext,
) -> None:
    phase4_scope = AuthenticatedPhase4Scope(
        tenant_scope_id=context.dataset_scope.tenant_id,
        workspace_id=context.workspace_id,
    )
    with pytest.raises(TelemetryScopeUnavailableError) as captured:
        telemetry_scope_from_authority(
            workspace_context=context,
            phase4_scope=phase4_scope,
        )
    assert str(captured.value) == OPAQUE_TELEMETRY_WORKSPACE_NOT_FOUND


def test_phase4_authority_must_match_current_workspace() -> None:
    context = _workspace()
    for phase4_scope in (
        None,
        AuthenticatedPhase4Scope(
            tenant_scope_id="tenant-b",
            workspace_id=context.workspace_id,
        ),
        AuthenticatedPhase4Scope(
            tenant_scope_id=context.dataset_scope.tenant_id,
            workspace_id="ws-facility-b",
        ),
    ):
        with pytest.raises(TelemetryScopeUnavailableError) as captured:
            telemetry_scope_from_authority(
                workspace_context=context,
                phase4_scope=phase4_scope,
            )
        assert str(captured.value) == OPAQUE_TELEMETRY_WORKSPACE_NOT_FOUND


def test_scope_reference_rejects_a_forged_resource_key() -> None:
    scope = _scope(_workspace())
    with pytest.raises(ValueError, match="telemetry_scope_resource_mismatch"):
        type(scope)(
            tenant_scope_id=scope.tenant_scope_id,
            workspace_id=scope.workspace_id,
            resource_scope_id="phase4-scope:attacker",
            facility_id=scope.facility_id,
        )


def test_missing_and_cross_scope_resources_fail_with_same_opaque_error() -> None:
    scope = _scope(_workspace())
    other_scope = _scope(_workspace(tenant_id="tenant-b"))
    in_scope = {
        "connection_id": "connection-1",
        **{
            "tenant_scope_id": scope.tenant_scope_id,
            "workspace_id": scope.workspace_id,
            "resource_scope_id": scope.resource_scope_id,
            "facility_id": scope.facility_id,
        },
    }

    assert require_scoped_resource(in_scope, scope=scope) is in_scope
    errors = []
    for resource in (None, in_scope):
        with pytest.raises(TelemetryResourceNotFoundError) as captured:
            require_scoped_resource(resource, scope=other_scope)
        errors.append(str(captured.value))
    assert errors == [OPAQUE_TELEMETRY_NOT_FOUND, OPAQUE_TELEMETRY_NOT_FOUND]


def test_unauthenticated_actor_is_not_accepted_for_audit() -> None:
    with pytest.raises(TelemetryScopeUnavailableError):
        normalize_audit_actor(
            {"authenticated": False, "auth_subject": "attacker@example.com"}
        )
