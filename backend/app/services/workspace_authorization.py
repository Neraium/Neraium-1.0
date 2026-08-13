from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import os
from typing import Any

from app.services.auth_store import get_authorized_workspace, get_workspace
from app.services.dataset_scope import (
    DEFAULT_WORKSPACE_ID,
    DatasetScope,
    build_dataset_scope,
    normalize_workspace_id,
)


EXPLICIT_WORKSPACE_PREFIX = "ws-"


class WorkspaceAuthorizationError(Exception):
    """Opaque failure used when a selected facility is absent or unauthorized."""


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: str
    display_name: str
    kind: str
    membership_active: bool
    dataset_scope: DatasetScope

    @property
    def is_explicit(self) -> bool:
        return self.kind == "facility"

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "membership_active": self.membership_active,
        }


_DEFAULT_CONTEXT = WorkspaceContext(
    workspace_id=DEFAULT_WORKSPACE_ID,
    display_name="Personal workspace",
    kind="personal",
    membership_active=True,
    dataset_scope=build_dataset_scope(user_id="anonymous"),
)
_CURRENT_WORKSPACE_CONTEXT: ContextVar[WorkspaceContext] = ContextVar(
    "neraium_workspace_context", default=_DEFAULT_CONTEXT
)


def is_explicit_workspace_id(workspace_id: Any) -> bool:
    return str(workspace_id or "").strip().startswith(EXPLICIT_WORKSPACE_PREFIX)


def _service_workspace_allowlist() -> set[str]:
    return {
        value.strip()
        for value in str(os.getenv("NERAIUM_API_TOKEN_WORKSPACE_IDS", "")).split(",")
        if value.strip().startswith(EXPLICIT_WORKSPACE_PREFIX)
    }


def _context_from_workspace(workspace: dict[str, Any]) -> WorkspaceContext:
    return WorkspaceContext(
        workspace_id=str(workspace["workspace_id"]),
        display_name=str(workspace["display_name"]),
        kind="facility",
        membership_active=True,
        dataset_scope=build_dataset_scope(
            tenant_id=workspace["scope_tenant_id"],
            user_id=workspace["scope_user_id"],
            workspace_id=workspace["scope_workspace_id"],
        ),
    )


def resolve_workspace_context(
    *,
    subject: str,
    requested_workspace_id: Any = None,
    auth_source: str = "session",
) -> WorkspaceContext:
    """Resolve a selected workspace to its immutable resource scope.

    The header is only a selector. Explicit facility IDs require active
    membership, except service identities which require an exact environment
    allowlist entry. Legacy labels stay inside the actor's personal scope.
    """
    workspace_id = normalize_workspace_id(requested_workspace_id)
    normalized_subject = str(subject or "anonymous").strip().lower() or "anonymous"
    if not is_explicit_workspace_id(workspace_id):
        return WorkspaceContext(
            workspace_id=workspace_id,
            display_name="Personal workspace",
            kind="personal",
            membership_active=True,
            dataset_scope=build_dataset_scope(
                tenant_id=normalized_subject,
                user_id=normalized_subject,
                workspace_id=workspace_id,
            ),
        )

    if auth_source == "service_token":
        if workspace_id not in _service_workspace_allowlist():
            raise WorkspaceAuthorizationError("Workspace not found.")
        workspace = get_workspace(workspace_id)
        if not workspace or not workspace.get("is_active", True):
            raise WorkspaceAuthorizationError("Workspace not found.")
        return _context_from_workspace(workspace)

    if auth_source == "public_readonly_get":
        raise WorkspaceAuthorizationError("Workspace not found.")

    workspace = get_authorized_workspace(workspace_id, normalized_subject)
    if not workspace:
        raise WorkspaceAuthorizationError("Workspace not found.")
    return _context_from_workspace(workspace)


def set_current_workspace_context(context: WorkspaceContext) -> None:
    _CURRENT_WORKSPACE_CONTEXT.set(context)


def current_workspace_context() -> WorkspaceContext:
    return _CURRENT_WORKSPACE_CONTEXT.get()

