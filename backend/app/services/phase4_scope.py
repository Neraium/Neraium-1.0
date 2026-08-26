from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterator

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.services.dataset_scope import DEFAULT_WORKSPACE_ID, DatasetScope


SERVER_BOUND_SYSTEM_IDENTITY_VERSION = "server-bound-system-identity.v1"
SERVER_BOUND_SYSTEM_IDENTITY_V2_VERSION = "server-bound-system-identity.v2"
SERVER_BOUND_SYSTEM_IDENTITY_AUTHORITY = "facility-context.v1"
LEGACY_UPLOAD_QUEUE_PHASE4_SCOPE_VERSION = "upload-queue-phase4-scope.v1"
UPLOAD_QUEUE_PHASE4_SCOPE_VERSION = "upload-queue-phase4-scope.v2"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_RESOURCE_SCOPE_PATTERN = re.compile(r"^phase4-scope:[0-9a-f]{32}$")
_CURRENT_AUTHENTICATED_PHASE4_SCOPE: ContextVar[AuthenticatedPhase4Scope | None] = ContextVar(
    "neraium_authenticated_phase4_scope",
    default=None,
)
_CURRENT_SERVER_BOUND_SYSTEM_IDENTITY: ContextVar[ServerBoundSystemIdentity | None]


@dataclass(frozen=True, slots=True)
class ServerBoundSystemIdentity:
    """A workspace-registry identity transported outside client payloads."""

    system_id: str
    dataset_scope_storage_id: str
    authority_record_digest: str
    authority: str = SERVER_BOUND_SYSTEM_IDENTITY_AUTHORITY
    version: str = SERVER_BOUND_SYSTEM_IDENTITY_VERSION

    def __post_init__(self) -> None:
        if self.version != SERVER_BOUND_SYSTEM_IDENTITY_VERSION:
            raise ValueError("unsupported_server_bound_system_identity_version")
        if self.authority != SERVER_BOUND_SYSTEM_IDENTITY_AUTHORITY:
            raise ValueError("unsupported_server_bound_system_identity_authority")
        system_id = str(self.system_id or "").strip()
        storage_id = str(self.dataset_scope_storage_id or "").strip()
        authority_record_digest = str(self.authority_record_digest or "").strip().lower()
        if not system_id:
            raise ValueError("server_bound_system_identity_missing:system_id")
        if not storage_id:
            raise ValueError("server_bound_system_identity_missing:dataset_scope_storage_id")
        if not _SHA256_PATTERN.fullmatch(authority_record_digest):
            raise ValueError("server_bound_system_identity_authority_digest_invalid")
        object.__setattr__(self, "system_id", system_id)
        object.__setattr__(self, "dataset_scope_storage_id", storage_id)
        object.__setattr__(self, "authority_record_digest", authority_record_digest)

    def as_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "system_id": self.system_id,
            "authority": self.authority,
            "dataset_scope_storage_id": self.dataset_scope_storage_id,
            "authority_record_digest": self.authority_record_digest,
        }

    @property
    def identity_digest(self) -> str:
        return _canonical_digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ServerBoundSystemIdentityV2:
    """Resource-scoped system authority for ongoing telemetry analysis.

    Unlike the upload-only v1 identity, this identity is deliberately bound to
    the stable tenant/workspace resource scope and never to a user's dataset
    storage identifier.
    """

    system_id: str
    resource_scope_id: str
    authority_record_digest: str
    authority: str = SERVER_BOUND_SYSTEM_IDENTITY_AUTHORITY
    version: str = SERVER_BOUND_SYSTEM_IDENTITY_V2_VERSION

    def __post_init__(self) -> None:
        if self.version != SERVER_BOUND_SYSTEM_IDENTITY_V2_VERSION:
            raise ValueError("unsupported_server_bound_system_identity_version")
        if self.authority != SERVER_BOUND_SYSTEM_IDENTITY_AUTHORITY:
            raise ValueError("unsupported_server_bound_system_identity_authority")
        system_id = str(self.system_id or "").strip()
        resource_scope_id = str(self.resource_scope_id or "").strip()
        authority_record_digest = str(self.authority_record_digest or "").strip().lower()
        if not system_id:
            raise ValueError("server_bound_system_identity_missing:system_id")
        if not resource_scope_id:
            raise ValueError("server_bound_system_identity_missing:resource_scope_id")
        if not _RESOURCE_SCOPE_PATTERN.fullmatch(resource_scope_id):
            raise ValueError("server_bound_system_identity_resource_scope_invalid")
        if not _SHA256_PATTERN.fullmatch(authority_record_digest):
            raise ValueError("server_bound_system_identity_authority_digest_invalid")
        object.__setattr__(self, "system_id", system_id)
        object.__setattr__(self, "resource_scope_id", resource_scope_id)
        object.__setattr__(self, "authority_record_digest", authority_record_digest)

    def as_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "system_id": self.system_id,
            "authority": self.authority,
            "resource_scope_id": self.resource_scope_id,
            "authority_record_digest": self.authority_record_digest,
        }

    @property
    def identity_digest(self) -> str:
        return _canonical_digest(self.as_dict())


def build_telemetry_server_bound_system_identity(
    *,
    scope: AuthenticatedPhase4Scope,
    system_id: Any,
    authority_record_digest: Any,
) -> ServerBoundSystemIdentityV2:
    """Build v2 identity only from a canonical authenticated resource scope."""
    if not isinstance(scope, AuthenticatedPhase4Scope):
        raise TypeError("authenticated_phase4_scope_required")
    verified_scope = AuthenticatedPhase4Scope(
        tenant_scope_id=scope.tenant_scope_id,
        workspace_id=scope.workspace_id,
        resource_scope_id=scope.resource_scope_id,
        version=scope.version,
    )
    return ServerBoundSystemIdentityV2(
        system_id=str(system_id or ""),
        resource_scope_id=verified_scope.resource_scope_id,
        authority_record_digest=str(authority_record_digest or ""),
    )


_CURRENT_SERVER_BOUND_SYSTEM_IDENTITY = ContextVar(
    "neraium_server_bound_system_identity",
    default=None,
)


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def authenticated_phase4_scope_from_request_context(
    *,
    auth_context: dict[str, Any] | None,
    workspace_context: Any,
) -> AuthenticatedPhase4Scope | None:
    """Build Phase 4 authority only from server-resolved request state.

    Explicit workspaces have already passed membership or service-token
    allowlist authorization. Personal scope is eligible only for the canonical
    authenticated default; legacy free-form workspace labels are deliberately
    excluded from longitudinal storage.
    """
    if not isinstance(auth_context, dict) or auth_context.get("authenticated") is not True:
        return None
    dataset_scope = getattr(workspace_context, "dataset_scope", None)
    workspace_id = str(getattr(workspace_context, "workspace_id", "") or "").strip()
    kind = str(getattr(workspace_context, "kind", "") or "").strip()
    membership_active = getattr(workspace_context, "membership_active", False) is True
    if not isinstance(dataset_scope, DatasetScope) or not membership_active:
        return None
    is_authorized_explicit = kind == "facility" and workspace_id.startswith("ws-")
    is_authenticated_personal_default = kind == "personal" and workspace_id == DEFAULT_WORKSPACE_ID
    if not (is_authorized_explicit or is_authenticated_personal_default):
        return None
    tenant_scope_id = str(dataset_scope.tenant_id or "").strip()
    if not tenant_scope_id or not workspace_id:
        return None
    try:
        return AuthenticatedPhase4Scope(
            tenant_scope_id=tenant_scope_id,
            workspace_id=workspace_id,
        )
    except (TypeError, ValueError):
        return None


def current_authenticated_phase4_scope() -> AuthenticatedPhase4Scope | None:
    return _CURRENT_AUTHENTICATED_PHASE4_SCOPE.get()


def set_current_authenticated_phase4_scope(scope: AuthenticatedPhase4Scope | None) -> None:
    _CURRENT_AUTHENTICATED_PHASE4_SCOPE.set(scope)


@contextmanager
def authenticated_phase4_scope_context(
    scope: AuthenticatedPhase4Scope | None,
) -> Iterator[None]:
    token = _CURRENT_AUTHENTICATED_PHASE4_SCOPE.set(scope)
    try:
        yield
    finally:
        _CURRENT_AUTHENTICATED_PHASE4_SCOPE.reset(token)


def current_server_bound_system_identity() -> ServerBoundSystemIdentity | None:
    return _CURRENT_SERVER_BOUND_SYSTEM_IDENTITY.get()


def set_current_server_bound_system_identity(
    identity: ServerBoundSystemIdentity | None,
) -> None:
    _CURRENT_SERVER_BOUND_SYSTEM_IDENTITY.set(identity)


@contextmanager
def server_bound_system_identity_context(
    identity: ServerBoundSystemIdentity | None,
) -> Iterator[None]:
    token = _CURRENT_SERVER_BOUND_SYSTEM_IDENTITY.set(identity)
    try:
        yield
    finally:
        _CURRENT_SERVER_BOUND_SYSTEM_IDENTITY.reset(token)


def _normalized_binding_id(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def build_upload_queue_phase4_scope_envelope(
    *,
    dataset_scope: DatasetScope,
    phase4_scope: AuthenticatedPhase4Scope | None = None,
    system_identity: ServerBoundSystemIdentity | None = None,
    job_id: Any = None,
    dataset_id: Any = None,
    upload_session_id: Any = None,
) -> dict[str, Any] | None:
    resolved = phase4_scope if phase4_scope is not None else current_authenticated_phase4_scope()
    if resolved is None:
        return None
    if str(dataset_scope.tenant_id or "").strip() != resolved.tenant_scope_id:
        return None
    if (
        system_identity is not None
        and system_identity.dataset_scope_storage_id != dataset_scope.storage_id
    ):
        return None
    bound_ids = {
        "job_id": _normalized_binding_id(job_id),
        "dataset_id": _normalized_binding_id(dataset_id),
        "upload_session_id": _normalized_binding_id(upload_session_id),
    }
    # An incomplete upload lineage cannot carry system authority. Keep the
    # authenticated workspace envelope so Phases 1-3 can still run safely.
    bound_identity = system_identity if system_identity is not None and all(bound_ids.values()) else None
    binding = {
        "version": UPLOAD_QUEUE_PHASE4_SCOPE_VERSION,
        "authenticated_scope": resolved.as_dict(),
        "authenticated_scope_digest": resolved.scope_digest,
        "dataset_scope_storage_id": dataset_scope.storage_id,
        "system_identity": bound_identity.as_dict() if bound_identity is not None else None,
        "system_identity_digest": bound_identity.identity_digest if bound_identity is not None else None,
        **bound_ids,
    }
    return {**binding, "binding_digest": _canonical_digest(binding)}


def _validated_phase4_queue_binding(
    payload: dict[str, Any] | None,
    *,
    dataset_scope: DatasetScope,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    routing = payload.get("routing")
    if not isinstance(routing, dict):
        return None
    envelope = routing.get("phase4_scope")
    if not isinstance(envelope, dict):
        return None
    version = str(envelope.get("version") or "")
    if version == LEGACY_UPLOAD_QUEUE_PHASE4_SCOPE_VERSION:
        binding = {
            "version": envelope.get("version"),
            "authenticated_scope": envelope.get("authenticated_scope"),
            "authenticated_scope_digest": envelope.get("authenticated_scope_digest"),
            "dataset_scope_storage_id": envelope.get("dataset_scope_storage_id"),
        }
    elif version == UPLOAD_QUEUE_PHASE4_SCOPE_VERSION:
        binding = {
            "version": envelope.get("version"),
            "authenticated_scope": envelope.get("authenticated_scope"),
            "authenticated_scope_digest": envelope.get("authenticated_scope_digest"),
            "dataset_scope_storage_id": envelope.get("dataset_scope_storage_id"),
            "system_identity": envelope.get("system_identity"),
            "system_identity_digest": envelope.get("system_identity_digest"),
            "job_id": envelope.get("job_id"),
            "dataset_id": envelope.get("dataset_id"),
            "upload_session_id": envelope.get("upload_session_id"),
        }
    else:
        return None
    if str(binding["dataset_scope_storage_id"] or "") != dataset_scope.storage_id:
        return None
    if str(envelope.get("binding_digest") or "") != _canonical_digest(binding):
        return None
    return binding


def authenticated_phase4_scope_from_queue_routing(
    payload: dict[str, Any] | None,
    *,
    dataset_scope: DatasetScope,
) -> AuthenticatedPhase4Scope | None:
    """Validate the internal queue envelope without consulting job payloads."""
    binding = _validated_phase4_queue_binding(payload, dataset_scope=dataset_scope)
    if binding is None:
        return None
    scope_payload = binding["authenticated_scope"]
    if not isinstance(scope_payload, dict):
        return None
    try:
        scope = AuthenticatedPhase4Scope(
            version=str(scope_payload.get("version") or ""),
            tenant_scope_id=str(scope_payload.get("tenant_scope_id") or ""),
            workspace_id=str(scope_payload.get("workspace_id") or ""),
            resource_scope_id=str(scope_payload.get("resource_scope_id") or ""),
        )
    except (TypeError, ValueError):
        return None
    if scope.scope_digest != str(binding["authenticated_scope_digest"] or ""):
        return None
    if str(dataset_scope.tenant_id or "").strip() != scope.tenant_scope_id:
        return None
    return scope


def server_bound_system_identity_from_queue_routing(
    payload: dict[str, Any] | None,
    *,
    dataset_scope: DatasetScope,
    phase4_scope: AuthenticatedPhase4Scope | None,
    job_id: Any = None,
    dataset_id: Any = None,
    upload_session_id: Any = None,
) -> ServerBoundSystemIdentity | None:
    """Recover a system identity only from a complete server queue binding."""
    if phase4_scope is None:
        return None
    binding = _validated_phase4_queue_binding(payload, dataset_scope=dataset_scope)
    if binding is None or binding.get("version") != UPLOAD_QUEUE_PHASE4_SCOPE_VERSION:
        return None
    scope_payload = binding.get("authenticated_scope")
    if not isinstance(scope_payload, dict) or scope_payload != phase4_scope.as_dict():
        return None
    expected_ids = {
        "job_id": _normalized_binding_id(job_id),
        "dataset_id": _normalized_binding_id(dataset_id),
        "upload_session_id": _normalized_binding_id(upload_session_id),
    }
    # The outer queue row is the independent authority for the job identifier.
    outer_job_id = _normalized_binding_id(payload.get("job_id") if isinstance(payload, dict) else None)
    if outer_job_id is not None and binding.get("job_id") != outer_job_id:
        return None
    for field, expected in expected_ids.items():
        if expected is not None and binding.get(field) != expected:
            return None
    if not all(_normalized_binding_id(binding.get(field)) for field in expected_ids):
        return None
    identity_payload = binding.get("system_identity")
    if not isinstance(identity_payload, dict):
        return None
    try:
        identity = ServerBoundSystemIdentity(
            version=str(identity_payload.get("version") or ""),
            system_id=str(identity_payload.get("system_id") or ""),
            authority=str(identity_payload.get("authority") or ""),
            dataset_scope_storage_id=str(identity_payload.get("dataset_scope_storage_id") or ""),
            authority_record_digest=str(identity_payload.get("authority_record_digest") or ""),
        )
    except (TypeError, ValueError):
        return None
    if identity.dataset_scope_storage_id != dataset_scope.storage_id:
        return None
    if identity.identity_digest != str(binding.get("system_identity_digest") or ""):
        return None
    return identity
