from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any


PHASE4_SCOPE_VERSION = "phase4-authenticated-scope-v1"


def canonical_phase4_resource_scope_id(tenant_scope_id: str, workspace_id: str) -> str:
    canonical = json.dumps(
        {
            "version": PHASE4_SCOPE_VERSION,
            "tenant_scope_id": str(tenant_scope_id or "").strip(),
            "workspace_id": str(workspace_id or "").strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"phase4-scope:{sha256(canonical.encode('utf-8')).hexdigest()[:32]}"


@dataclass(frozen=True, slots=True)
class AuthenticatedPhase4Scope:
    """Server-attested identity boundary for all durable Phase 4 memory.

    This value is deliberately passed separately from analytical configuration:
    callers must construct it from authenticated server context, never from the
    request's analytical payload.
    """

    tenant_scope_id: str
    workspace_id: str
    resource_scope_id: str = ""
    version: str = PHASE4_SCOPE_VERSION

    def __post_init__(self) -> None:
        if self.version != PHASE4_SCOPE_VERSION:
            raise ValueError("unsupported_authenticated_phase4_scope_version")
        for field in ("tenant_scope_id", "workspace_id"):
            value = str(getattr(self, field) or "").strip()
            if not value:
                raise ValueError(f"authenticated_phase4_scope_missing:{field}")
            object.__setattr__(self, field, value)
        expected_resource_scope_id = canonical_phase4_resource_scope_id(
            self.tenant_scope_id,
            self.workspace_id,
        )
        resource_scope_id = str(self.resource_scope_id or "").strip()
        if resource_scope_id and resource_scope_id != expected_resource_scope_id:
            raise ValueError("authenticated_phase4_scope_resource_mismatch")
        object.__setattr__(self, "resource_scope_id", expected_resource_scope_id)

    def as_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "tenant_scope_id": self.tenant_scope_id,
            "workspace_id": self.workspace_id,
            "resource_scope_id": self.resource_scope_id,
        }

    @property
    def scope_digest(self) -> str:
        encoded = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return sha256(encoded.encode("utf-8")).hexdigest()

    @property
    def model_id_scope(self) -> str:
        return self.scope_digest[:24]


def scoped_behavioral_model_id(scope: AuthenticatedPhase4Scope, business_seed: str) -> str:
    digest = sha256(str(business_seed).encode("utf-8")).hexdigest()[:24]
    return f"behavioral-model:{scope.model_id_scope}:{digest}"


class BehavioralModelStorageError(RuntimeError):
    """Base error for recoverable Phase 4 persistence failures."""


class BehavioralModelStorageUnavailable(BehavioralModelStorageError):
    """The configured storage backend cannot be reached."""


class BehavioralModelVersionConflict(BehavioralModelStorageError):
    """A write attempted to replace or reuse an immutable version."""


class BehavioralModelScopeMismatch(BehavioralModelStorageError):
    """A record or identifier did not belong to the authenticated scope."""


class BehavioralModelStore(ABC):
    """Storage-neutral, append-only contract for behavioral model memory.

    Implementations must return defensive copies and must never overwrite a
    model version, snapshot, event, decision, or candidate baseline.
    """

    @abstractmethod
    def load_model(self, scope: AuthenticatedPhase4Scope, model_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def save_model(self, scope: AuthenticatedPhase4Scope, model: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_model(self, scope: AuthenticatedPhase4Scope, model: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_snapshot(self, scope: AuthenticatedPhase4Scope, snapshot: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def load_snapshot(self, scope: AuthenticatedPhase4Scope, model_id: str, snapshot_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def list_snapshots(self, scope: AuthenticatedPhase4Scope, model_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def append_event(self, scope: AuthenticatedPhase4Scope, model_id: str, event: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def record_learning_decision(
        self,
        scope: AuthenticatedPhase4Scope,
        model_id: str,
        decision: dict[str, Any],
        *,
        source_run_id: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_learning_decisions(self, scope: AuthenticatedPhase4Scope, model_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def retire_relationship(
        self,
        scope: AuthenticatedPhase4Scope,
        model_id: str,
        relationship_id: str,
        *,
        source_run_id: str,
        reason: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def load_active_baseline(self, scope: AuthenticatedPhase4Scope, model_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def save_candidate_baseline(
        self,
        scope: AuthenticatedPhase4Scope,
        model_id: str,
        baseline: dict[str, Any],
        *,
        source_run_id: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def activate_baseline(
        self,
        scope: AuthenticatedPhase4Scope,
        model_id: str,
        baseline_version: str,
        *,
        source_run_id: str,
        approval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def restore_snapshot(
        self,
        scope: AuthenticatedPhase4Scope,
        model_id: str,
        snapshot_id: str,
        *,
        source_run_id: str,
    ) -> dict[str, Any]:
        raise NotImplementedError
