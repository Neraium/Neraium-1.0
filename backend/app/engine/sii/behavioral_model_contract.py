from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BehavioralModelStorageError(RuntimeError):
    """Base error for recoverable Phase 4 persistence failures."""


class BehavioralModelStorageUnavailable(BehavioralModelStorageError):
    """The configured storage backend cannot be reached."""


class BehavioralModelVersionConflict(BehavioralModelStorageError):
    """A write attempted to replace or reuse an immutable version."""


class BehavioralModelStore(ABC):
    """Storage-neutral, append-only contract for behavioral model memory.

    Implementations must return defensive copies and must never overwrite a
    model version, snapshot, event, decision, or candidate baseline.
    """

    @abstractmethod
    def load_model(self, model_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def save_model(self, model: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_model(self, model: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def create_snapshot(self, snapshot: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def load_snapshot(self, model_id: str, snapshot_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def list_snapshots(self, model_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def append_event(self, model_id: str, event: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def record_learning_decision(
        self,
        model_id: str,
        decision: dict[str, Any],
        *,
        source_run_id: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_learning_decisions(self, model_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def retire_relationship(
        self,
        model_id: str,
        relationship_id: str,
        *,
        source_run_id: str,
        reason: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def load_active_baseline(self, model_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def save_candidate_baseline(
        self,
        model_id: str,
        baseline: dict[str, Any],
        *,
        source_run_id: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def activate_baseline(
        self,
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
        model_id: str,
        snapshot_id: str,
        *,
        source_run_id: str,
    ) -> dict[str, Any]:
        raise NotImplementedError
