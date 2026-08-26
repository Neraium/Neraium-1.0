from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.services.phase4_scope import current_authenticated_phase4_scope
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.workspace_authorization import (
    WorkspaceContext,
    current_workspace_context,
)


OPAQUE_TELEMETRY_NOT_FOUND = "Telemetry resource not found."
OPAQUE_TELEMETRY_WORKSPACE_NOT_FOUND = "Telemetry workspace not found."
_AUTHORITATIVE_SCOPE_FIELDS = (
    "tenant_scope_id",
    "workspace_id",
    "resource_scope_id",
    "facility_id",
)
_ResourceT = TypeVar("_ResourceT")


class TelemetryScopeUnavailableError(PermissionError):
    """Fail-closed error for absent or ineligible server authority."""


class TelemetryResourceNotFoundError(LookupError):
    """Opaque missing/out-of-scope resource failure used by API adapters."""


def telemetry_scope_from_authority(
    *,
    workspace_context: WorkspaceContext,
    phase4_scope: AuthenticatedPhase4Scope | None,
) -> TelemetryScopeRef:
    """Resolve production telemetry authority from attested server objects.

    A production connection belongs to an active explicit facility workspace.
    Personal defaults and legacy free-form workspace labels remain available to
    historical uploads but are never accepted here. The user-dependent dataset
    storage id is deliberately ignored.
    """
    if not isinstance(workspace_context, WorkspaceContext):
        raise TelemetryScopeUnavailableError(OPAQUE_TELEMETRY_WORKSPACE_NOT_FOUND)
    workspace_id = str(workspace_context.workspace_id or "").strip()
    tenant_scope_id = str(workspace_context.dataset_scope.tenant_id or "").strip()
    if (
        workspace_context.kind != "facility"
        or workspace_context.membership_active is not True
        or not workspace_context.is_explicit
        or not workspace_id.startswith("ws-")
        or not tenant_scope_id
        or not isinstance(phase4_scope, AuthenticatedPhase4Scope)
        or phase4_scope.tenant_scope_id != tenant_scope_id
        or phase4_scope.workspace_id != workspace_id
    ):
        raise TelemetryScopeUnavailableError(OPAQUE_TELEMETRY_WORKSPACE_NOT_FOUND)
    # Reconstructing verifies the deterministic resource key even if a future
    # deserializer bypasses AuthenticatedPhase4Scope.__post_init__.
    try:
        verified = AuthenticatedPhase4Scope(
            tenant_scope_id=phase4_scope.tenant_scope_id,
            workspace_id=phase4_scope.workspace_id,
            resource_scope_id=phase4_scope.resource_scope_id,
            version=phase4_scope.version,
        )
    except (TypeError, ValueError) as error:
        raise TelemetryScopeUnavailableError(
            OPAQUE_TELEMETRY_WORKSPACE_NOT_FOUND
        ) from error
    return TelemetryScopeRef(
        tenant_scope_id=verified.tenant_scope_id,
        workspace_id=verified.workspace_id,
        resource_scope_id=verified.resource_scope_id,
        facility_id=workspace_id,
    )


def current_telemetry_scope() -> TelemetryScopeRef:
    """Return current request authority; never derives it from a payload."""
    return telemetry_scope_from_authority(
        workspace_context=current_workspace_context(),
        phase4_scope=current_authenticated_phase4_scope(),
    )


def phase4_scope_from_telemetry_scope(
    scope: TelemetryScopeRef,
) -> AuthenticatedPhase4Scope:
    """Revalidate persisted telemetry scope before handing data to Phase 4."""
    if not isinstance(scope, TelemetryScopeRef):
        raise TelemetryScopeUnavailableError(OPAQUE_TELEMETRY_WORKSPACE_NOT_FOUND)
    try:
        return AuthenticatedPhase4Scope(
            tenant_scope_id=scope.tenant_scope_id,
            workspace_id=scope.workspace_id,
            resource_scope_id=scope.resource_scope_id,
        )
    except (TypeError, ValueError) as error:
        raise TelemetryScopeUnavailableError(
            OPAQUE_TELEMETRY_WORKSPACE_NOT_FOUND
        ) from error


def authoritative_scope_values(scope: TelemetryScopeRef) -> dict[str, str]:
    """Return repository columns sourced only from the verified scope."""
    return {
        "tenant_scope_id": scope.tenant_scope_id,
        "workspace_id": scope.workspace_id,
        "resource_scope_id": scope.resource_scope_id,
        "facility_id": scope.facility_id,
    }


def apply_authoritative_scope(
    payload: Mapping[str, Any] | None,
    *,
    scope: TelemetryScopeRef,
) -> dict[str, Any]:
    """Copy safe write values while overriding all payload scope claims."""
    values = dict(payload or {})
    values.update(authoritative_scope_values(scope))
    # Actor identity may be supplied separately by an authenticated router for
    # audit, but it cannot become data ownership authority.
    values.pop("user_id", None)
    values.pop("scope_storage_id", None)
    return values


def _field_value(resource: Any, field_name: str) -> Any:
    if isinstance(resource, Mapping):
        if field_name in resource:
            return resource.get(field_name)
        nested_scope = resource.get("scope")
    else:
        if hasattr(resource, field_name):
            return getattr(resource, field_name)
        nested_scope = getattr(resource, "scope", None)
    if isinstance(nested_scope, TelemetryScopeRef):
        return getattr(nested_scope, field_name)
    if isinstance(nested_scope, Mapping):
        return nested_scope.get(field_name)
    return None


def resource_matches_scope(resource: Any, scope: TelemetryScopeRef) -> bool:
    if resource is None or not isinstance(scope, TelemetryScopeRef):
        return False
    return all(
        str(_field_value(resource, field_name) or "").strip()
        == getattr(scope, field_name)
        for field_name in _AUTHORITATIVE_SCOPE_FIELDS
    )


def require_scoped_resource(
    resource: _ResourceT | None,
    *,
    scope: TelemetryScopeRef,
) -> _ResourceT:
    """Make an absent resource indistinguishable from a cross-scope resource."""
    if not resource_matches_scope(resource, scope):
        raise TelemetryResourceNotFoundError(OPAQUE_TELEMETRY_NOT_FOUND)
    return resource


def normalize_audit_actor(auth_context: Mapping[str, Any] | None) -> str:
    """Resolve audit identity without allowing it to affect resource scope."""
    context = auth_context if isinstance(auth_context, Mapping) else {}
    if context.get("authenticated") is not True:
        raise TelemetryScopeUnavailableError(OPAQUE_TELEMETRY_WORKSPACE_NOT_FOUND)
    actor = str(context.get("auth_subject") or "").strip().lower()
    if not actor:
        raise TelemetryScopeUnavailableError(OPAQUE_TELEMETRY_WORKSPACE_NOT_FOUND)
    return actor
