from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any, Callable

from app.engine.sii.behavioral_model_contract import (
    BehavioralModelStorageUnavailable,
    BehavioralModelStore,
    BehavioralModelVersionConflict,
)


class InMemoryBehavioralModelStore(BehavioralModelStore):
    """Thread-safe append-only store intended for unit tests and local callers."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._state: dict[str, dict[str, Any]] = {}

    def _model_state(self, model_id: str) -> dict[str, Any]:
        return self._state.setdefault(
            str(model_id),
            {
                "models": {},
                "active_model_version": None,
                "snapshots": {},
                "snapshot_order": [],
                "events": {},
                "event_order": [],
                "learning_decisions": {},
                "decision_order": [],
                "candidate_baselines": {},
                "activated_baselines": {},
                "active_baseline_version": None,
                "write_audit": [],
            },
        )

    def load_model(self, model_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._state.get(str(model_id))
            if not state or state.get("active_model_version") is None:
                return None
            model = state["models"].get(str(state["active_model_version"]))
            return deepcopy(model) if isinstance(model, dict) else None

    def save_model(self, model: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        model_id, version = _model_identity(model)
        with self._lock:
            state = self._model_state(model_id)
            if version in state["models"]:
                raise BehavioralModelVersionConflict(f"model_version_already_exists:{model_id}:{version}")
            active = state.get("active_model_version")
            if active is not None and _version_number(version) <= _version_number(str(active)):
                raise BehavioralModelVersionConflict(f"model_version_not_forward:{model_id}:{version}")
            stored = _attributed(model, source_run_id)
            state["models"][version] = stored
            state["active_model_version"] = version
            self._audit(state, "save_model", source_run_id, version)
            return deepcopy(stored)

    def create_model(self, model: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        model_id, version = _model_identity(model)
        with self._lock:
            state = self._model_state(model_id)
            if state["models"]:
                raise BehavioralModelVersionConflict(f"model_already_exists:{model_id}")
            stored = _attributed(model, source_run_id)
            state["models"][version] = stored
            state["active_model_version"] = version
            self._audit(state, "create_model", source_run_id, version)
            return deepcopy(stored)

    def create_snapshot(self, snapshot: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        model_id = _required_text(snapshot, "model_id")
        snapshot_id = _required_text(snapshot, "snapshot_id")
        with self._lock:
            state = self._model_state(model_id)
            existing = state["snapshots"].get(snapshot_id)
            stored = _attributed(snapshot, source_run_id)
            if existing is not None:
                if existing == stored:
                    return deepcopy(existing)
                raise BehavioralModelVersionConflict(f"snapshot_id_already_exists:{model_id}:{snapshot_id}")
            state["snapshots"][snapshot_id] = stored
            state["snapshot_order"].append(snapshot_id)
            self._audit(state, "create_snapshot", source_run_id, snapshot_id)
            return deepcopy(stored)

    def load_snapshot(self, model_id: str, snapshot_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._state.get(str(model_id))
            snapshot = state.get("snapshots", {}).get(str(snapshot_id)) if state else None
            return deepcopy(snapshot) if isinstance(snapshot, dict) else None

    def list_snapshots(self, model_id: str) -> list[dict[str, Any]]:
        with self._lock:
            state = self._state.get(str(model_id))
            if not state:
                return []
            return [
                deepcopy(state["snapshots"][snapshot_id])
                for snapshot_id in state["snapshot_order"]
                if snapshot_id in state["snapshots"]
            ]

    def append_event(self, model_id: str, event: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        event_id = _required_text(event, "event_id")
        with self._lock:
            state = self._model_state(model_id)
            stored = _append_immutable(state["events"], event_id, event, source_run_id, "event")
            if event_id not in state["event_order"]:
                state["event_order"].append(event_id)
                self._audit(state, "append_event", source_run_id, event_id)
            return stored

    def record_learning_decision(
        self,
        model_id: str,
        decision: dict[str, Any],
        *,
        source_run_id: str,
    ) -> dict[str, Any]:
        decision_id = _required_text(decision, "decision_id")
        with self._lock:
            state = self._model_state(model_id)
            stored = _append_immutable(
                state["learning_decisions"], decision_id, decision, source_run_id, "learning_decision"
            )
            if decision_id not in state["decision_order"]:
                state["decision_order"].append(decision_id)
                self._audit(state, "record_learning_decision", source_run_id, decision_id)
            return stored

    def list_learning_decisions(self, model_id: str) -> list[dict[str, Any]]:
        with self._lock:
            state = self._state.get(str(model_id))
            if not state:
                return []
            return [
                deepcopy(state["learning_decisions"][decision_id])
                for decision_id in state["decision_order"]
                if decision_id in state["learning_decisions"]
            ]

    def retire_relationship(
        self,
        model_id: str,
        relationship_id: str,
        *,
        source_run_id: str,
        reason: str,
    ) -> dict[str, Any]:
        with self._lock:
            current = self.load_model(model_id)
            if current is None:
                raise KeyError(f"model_not_found:{model_id}")
            relationships = current.get("relationship_memory")
            if not isinstance(relationships, dict) or relationship_id not in relationships:
                raise KeyError(f"relationship_not_found:{relationship_id}")
            retired = deepcopy(relationships[relationship_id])
            retired["status"] = "retired"
            retired["retirement"] = {"reason": str(reason), "source_run_id": str(source_run_id)}
            history = list(retired.get("change_history") or [])
            history.append({"status": "retired", "reason": str(reason), "source_run_id": str(source_run_id)})
            retired["change_history"] = history
            current["relationship_memory"] = {**relationships, relationship_id: retired}
            current["model_version"] = _next_version(str(current.get("model_version") or "1"))
            current["source_run_id"] = str(source_run_id)
            return self.save_model(current, source_run_id=source_run_id)

    def load_active_baseline(self, model_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._state.get(str(model_id))
            if not state or state.get("active_baseline_version") is None:
                return None
            baseline = state["activated_baselines"].get(str(state["active_baseline_version"]))
            return deepcopy(baseline) if isinstance(baseline, dict) else None

    def save_candidate_baseline(
        self,
        model_id: str,
        baseline: dict[str, Any],
        *,
        source_run_id: str,
    ) -> dict[str, Any]:
        version = _required_text(baseline, "candidate_version")
        with self._lock:
            state = self._model_state(model_id)
            stored = _append_immutable(
                state["candidate_baselines"], version, baseline, source_run_id, "baseline_version"
            )
            self._audit(state, "save_candidate_baseline", source_run_id, version)
            return stored

    def activate_baseline(
        self,
        model_id: str,
        baseline_version: str,
        *,
        source_run_id: str,
        approval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._model_state(model_id)
            baseline = state["candidate_baselines"].get(str(baseline_version))
            if baseline is None:
                raise KeyError(f"candidate_baseline_not_found:{baseline_version}")
            if baseline.get("approval_status") == "pending_validation" and not approval:
                raise BehavioralModelVersionConflict("human_validation_required")
            activated = deepcopy(baseline)
            activated["active_version"] = str(baseline_version)
            activated["approval_status"] = "approved" if approval else "automatic"
            if approval:
                activated["human_approval"] = deepcopy(approval)
            activated["activation_source_run_id"] = str(source_run_id)
            existing_activation = state["activated_baselines"].get(str(baseline_version))
            if existing_activation is not None and existing_activation != activated:
                raise BehavioralModelVersionConflict(
                    f"baseline_activation_already_exists:{baseline_version}"
                )
            state["activated_baselines"].setdefault(str(baseline_version), activated)
            state["active_baseline_version"] = str(baseline_version)
            self._audit(state, "activate_baseline", source_run_id, str(baseline_version))
            return deepcopy(activated)

    def restore_snapshot(
        self,
        model_id: str,
        snapshot_id: str,
        *,
        source_run_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            snapshot = self.load_snapshot(model_id, snapshot_id)
            current = self.load_model(model_id)
            if snapshot is None:
                raise KeyError(f"snapshot_not_found:{snapshot_id}")
            if current is None:
                raise KeyError(f"model_not_found:{model_id}")
            restored = {
                **current,
                "model_version": _next_version(str(current.get("model_version") or "1")),
                "behavioral_identity": deepcopy(snapshot.get("behavioral_identity", {})),
                "signal_memory": deepcopy(snapshot.get("signal_memory", {})),
                "relationship_memory": deepcopy(snapshot.get("relationship_memory", {})),
                "behavioral_graph": deepcopy(snapshot.get("behavioral_graph", {})),
                "operating_mode_memory": deepcopy(snapshot.get("operating_mode_memory", {})),
                "expected_behavior_models": deepcopy(snapshot.get("expected_behavior_models", {})),
                "baseline_versions": deepcopy(snapshot.get("baseline_versions", [])),
                "restored_from_snapshot_id": str(snapshot_id),
                "source_run_id": str(source_run_id),
            }
            return self.save_model(restored, source_run_id=source_run_id)

    def export_state(self, model_id: str) -> dict[str, Any]:
        """Return a defensive test-only view of all immutable records."""
        with self._lock:
            return deepcopy(self._state.get(str(model_id), {}))

    @staticmethod
    def _audit(state: dict[str, Any], operation: str, source_run_id: str, reference: str) -> None:
        state["write_audit"].append(
            {"operation": operation, "source_run_id": str(source_run_id), "reference": str(reference)}
        )


class RuntimeBehavioralModelStore(InMemoryBehavioralModelStore):
    """Append-only behavioral store using the existing runtime latest-payload repository.

    A complete per-model ledger is persisted under one namespaced payload. This
    deliberately requires no new database schema and keeps the analytical layer
    independent of SQLite.
    """

    KEY_PREFIX = "sii_behavioral_model_ledger_v1::"

    def __init__(
        self,
        *,
        reader: Callable[[str], Any] | None = None,
        writer: Callable[[str, Any], None] | None = None,
        mutator: Callable[[str, Callable[[Any | None], Any]], Any] | None = None,
    ) -> None:
        super().__init__()
        if reader is None or writer is None:
            try:
                from app.services.runtime_db import (
                    mutate_latest_payload,
                    read_latest_payload,
                    upsert_latest_payload,
                )
            except Exception as exc:  # pragma: no cover - import environment failure
                raise BehavioralModelStorageUnavailable(f"runtime_persistence_import_failed:{type(exc).__name__}:{exc}") from exc
            reader = reader or read_latest_payload
            writer = writer or upsert_latest_payload
            mutator = mutator or mutate_latest_payload
        self._reader = reader
        self._writer = writer
        self._mutator = mutator
        self._loaded: set[str] = set()

    def _model_state(self, model_id: str) -> dict[str, Any]:
        self._load_ledger(model_id)
        return super()._model_state(model_id)

    def load_model(self, model_id: str) -> dict[str, Any] | None:
        self._load_ledger(model_id)
        return super().load_model(model_id)

    def load_snapshot(self, model_id: str, snapshot_id: str) -> dict[str, Any] | None:
        self._load_ledger(model_id)
        return super().load_snapshot(model_id, snapshot_id)

    def list_snapshots(self, model_id: str) -> list[dict[str, Any]]:
        self._load_ledger(model_id)
        return super().list_snapshots(model_id)

    def load_active_baseline(self, model_id: str) -> dict[str, Any] | None:
        self._load_ledger(model_id)
        return super().load_active_baseline(model_id)

    def list_learning_decisions(self, model_id: str) -> list[dict[str, Any]]:
        self._load_ledger(model_id)
        return super().list_learning_decisions(model_id)

    def _load_ledger(self, model_id: str) -> None:
        model_id = str(model_id)
        with self._lock:
            if model_id in self._loaded:
                return
            try:
                payload = self._reader(self.KEY_PREFIX + model_id)
            except Exception as exc:
                raise BehavioralModelStorageUnavailable(
                    f"behavioral_model_load_failed:{type(exc).__name__}:{exc}"
                ) from exc
            if isinstance(payload, dict):
                self._state[model_id] = deepcopy(payload)
            self._loaded.add(model_id)

    def _persist(self, model_id: str) -> None:
        try:
            local = deepcopy(self._state[str(model_id)])
            if self._mutator is not None:
                merged = self._mutator(
                    self.KEY_PREFIX + str(model_id),
                    lambda current: _merge_ledgers(current, local),
                )
                if isinstance(merged, dict):
                    self._state[str(model_id)] = deepcopy(merged)
            else:
                self._writer(self.KEY_PREFIX + str(model_id), local)
        except BehavioralModelVersionConflict:
            raise
        except Exception as exc:
            raise BehavioralModelStorageUnavailable(
                f"behavioral_model_write_failed:{type(exc).__name__}:{exc}"
            ) from exc

    def _with_persist(self, model_id: str, operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        result = operation()
        self._persist(model_id)
        return result

    def save_model(self, model: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        model_id = _required_text(model, "model_id")
        return self._with_persist(model_id, lambda: super(RuntimeBehavioralModelStore, self).save_model(model, source_run_id=source_run_id))

    def create_model(self, model: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        model_id = _required_text(model, "model_id")
        return self._with_persist(model_id, lambda: super(RuntimeBehavioralModelStore, self).create_model(model, source_run_id=source_run_id))

    def create_snapshot(self, snapshot: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        model_id = _required_text(snapshot, "model_id")
        return self._with_persist(model_id, lambda: super(RuntimeBehavioralModelStore, self).create_snapshot(snapshot, source_run_id=source_run_id))

    def append_event(self, model_id: str, event: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
        return self._with_persist(model_id, lambda: super(RuntimeBehavioralModelStore, self).append_event(model_id, event, source_run_id=source_run_id))

    def record_learning_decision(
        self, model_id: str, decision: dict[str, Any], *, source_run_id: str
    ) -> dict[str, Any]:
        return self._with_persist(model_id, lambda: super(RuntimeBehavioralModelStore, self).record_learning_decision(model_id, decision, source_run_id=source_run_id))

    def retire_relationship(
        self, model_id: str, relationship_id: str, *, source_run_id: str, reason: str
    ) -> dict[str, Any]:
        return self._with_persist(model_id, lambda: super(RuntimeBehavioralModelStore, self).retire_relationship(model_id, relationship_id, source_run_id=source_run_id, reason=reason))

    def save_candidate_baseline(
        self, model_id: str, baseline: dict[str, Any], *, source_run_id: str
    ) -> dict[str, Any]:
        return self._with_persist(model_id, lambda: super(RuntimeBehavioralModelStore, self).save_candidate_baseline(model_id, baseline, source_run_id=source_run_id))

    def activate_baseline(
        self,
        model_id: str,
        baseline_version: str,
        *,
        source_run_id: str,
        approval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._with_persist(model_id, lambda: super(RuntimeBehavioralModelStore, self).activate_baseline(model_id, baseline_version, source_run_id=source_run_id, approval=approval))

    def restore_snapshot(
        self, model_id: str, snapshot_id: str, *, source_run_id: str
    ) -> dict[str, Any]:
        return self._with_persist(model_id, lambda: super(RuntimeBehavioralModelStore, self).restore_snapshot(model_id, snapshot_id, source_run_id=source_run_id))


def _model_identity(model: dict[str, Any]) -> tuple[str, str]:
    return _required_text(model, "model_id"), _required_text(model, "model_version")


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = str(payload.get(field) or "").strip() if isinstance(payload, dict) else ""
    if not value:
        raise ValueError(f"missing_required_field:{field}")
    return value


def _attributed(payload: dict[str, Any], source_run_id: str) -> dict[str, Any]:
    stored = deepcopy(payload)
    stored["source_run_id"] = str(source_run_id)
    return stored


def _append_immutable(
    target: dict[str, Any],
    record_id: str,
    payload: dict[str, Any],
    source_run_id: str,
    record_type: str,
) -> dict[str, Any]:
    stored = _attributed(payload, source_run_id)
    existing = target.get(record_id)
    if existing is not None and existing != stored:
        raise BehavioralModelVersionConflict(f"{record_type}_already_exists:{record_id}")
    target.setdefault(record_id, stored)
    return deepcopy(target[record_id])


def _version_number(version: str) -> int:
    digits = "".join(character for character in str(version) if character.isdigit())
    return int(digits or 0)


def _next_version(version: str) -> str:
    prefix = "v" if str(version).startswith("v") else ""
    return f"{prefix}{_version_number(version) + 1}"


def _merge_ledgers(current: Any, local: dict[str, Any]) -> dict[str, Any]:
    """Merge append-only runtime ledgers inside one repository transaction."""

    if not isinstance(current, dict):
        return deepcopy(local)
    merged = deepcopy(current)
    mapping_fields = (
        "models",
        "snapshots",
        "events",
        "learning_decisions",
        "candidate_baselines",
        "activated_baselines",
    )
    for field in mapping_fields:
        merged.setdefault(field, {})
        for key, value in (local.get(field) or {}).items():
            existing = merged[field].get(key)
            if existing is not None and existing != value:
                raise BehavioralModelVersionConflict(
                    f"runtime_ledger_immutable_record_conflict:{field}:{key}"
                )
            merged[field].setdefault(key, deepcopy(value))
    for field in ("snapshot_order", "event_order", "decision_order"):
        merged[field] = list(
            dict.fromkeys([*(merged.get(field) or []), *(local.get(field) or [])])
        )
    merged["write_audit"] = [
        *merged.get("write_audit", []),
        *[
            item
            for item in local.get("write_audit", [])
            if item not in merged.get("write_audit", [])
        ],
    ]
    current_model = str(merged.get("active_model_version") or "")
    local_model = str(local.get("active_model_version") or "")
    merged["active_model_version"] = (
        local_model
        if _version_number(local_model) >= _version_number(current_model)
        else current_model or None
    )
    current_baseline = str(merged.get("active_baseline_version") or "")
    local_baseline = str(local.get("active_baseline_version") or "")
    merged["active_baseline_version"] = local_baseline or current_baseline or None
    return merged
