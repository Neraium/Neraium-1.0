from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import re
from typing import Any


DEFAULT_WORKSPACE_ID = "default"
WORKSPACE_HEADER = "X-Neraium-Workspace-Id"
_SCOPE_VERSION = 1
_WORKSPACE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class DatasetScope:
    tenant_id: str
    user_id: str
    workspace_id: str

    @property
    def storage_id(self) -> str:
        canonical = f"v{_SCOPE_VERSION}:{self.tenant_id}:{self.user_id}:{self.workspace_id}"
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    def as_dict(self) -> dict[str, str | int]:
        return {
            "version": _SCOPE_VERSION,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
        }


_DEFAULT_SCOPE = DatasetScope(tenant_id="anonymous", user_id="anonymous", workspace_id=DEFAULT_WORKSPACE_ID)
_CURRENT_DATASET_SCOPE: ContextVar[DatasetScope] = ContextVar("neraium_dataset_scope", default=_DEFAULT_SCOPE)


def normalize_workspace_id(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return DEFAULT_WORKSPACE_ID
    if not _WORKSPACE_PATTERN.fullmatch(normalized):
        raise ValueError("Workspace id contains invalid characters.")
    return normalized


def normalize_principal(value: Any, fallback: str = "anonymous") -> str:
    normalized = str(value or "").strip().lower()
    return normalized or fallback


def build_dataset_scope(
    *,
    user_id: Any,
    workspace_id: Any = DEFAULT_WORKSPACE_ID,
    tenant_id: Any | None = None,
) -> DatasetScope:
    normalized_user = normalize_principal(user_id)
    normalized_tenant = normalize_principal(tenant_id, normalized_user) if tenant_id is not None else normalized_user
    return DatasetScope(
        tenant_id=normalized_tenant,
        user_id=normalized_user,
        workspace_id=normalize_workspace_id(workspace_id),
    )


def dataset_scope_from_auth_context(auth_context: dict[str, Any] | None, workspace_id: Any = None) -> DatasetScope:
    context = auth_context if isinstance(auth_context, dict) else {}
    subject = normalize_principal(context.get("auth_subject"))
    # A session identity is its own tenant boundary until Neraium has an
    # authoritative organization membership model. Never trust a browser header
    # to select another user's tenant.
    return build_dataset_scope(user_id=subject, tenant_id=subject, workspace_id=workspace_id)


def dataset_scope_from_payload(payload: dict[str, Any] | None) -> DatasetScope | None:
    if not isinstance(payload, dict):
        return None
    candidate = payload.get("dataset_scope")
    if not isinstance(candidate, dict):
        candidate = payload.get("session_scope")
    if not isinstance(candidate, dict):
        return None
    tenant_id = str(candidate.get("tenant_id") or "").strip()
    user_id = str(candidate.get("user_id") or "").strip()
    workspace_id = str(candidate.get("workspace_id") or "").strip()
    if not tenant_id or not user_id or not workspace_id:
        return None
    try:
        return build_dataset_scope(tenant_id=tenant_id, user_id=user_id, workspace_id=workspace_id)
    except ValueError:
        return None


def current_dataset_scope() -> DatasetScope:
    return _CURRENT_DATASET_SCOPE.get()


def set_current_dataset_scope(scope: DatasetScope) -> None:
    _CURRENT_DATASET_SCOPE.set(scope)


def payload_matches_dataset_scope(payload: dict[str, Any] | None, scope: DatasetScope | None = None) -> bool:
    payload_scope = dataset_scope_from_payload(payload)
    return payload_scope is not None and payload_scope == (scope or current_dataset_scope())


def attach_dataset_scope(
    payload: dict[str, Any],
    *,
    scope: DatasetScope | None = None,
    dataset_id: Any = None,
) -> dict[str, Any]:
    resolved = scope or dataset_scope_from_payload(payload) or current_dataset_scope()
    payload["dataset_scope"] = resolved.as_dict()
    if dataset_id is not None:
        payload["dataset_id"] = str(dataset_id or "").strip() or None
    return payload
