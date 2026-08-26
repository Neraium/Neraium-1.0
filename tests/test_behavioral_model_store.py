from __future__ import annotations

from copy import deepcopy

import pytest

from app.engine.sii.behavioral_model_contract import (
    AuthenticatedPhase4Scope,
    BehavioralModelScopeMismatch,
    BehavioralModelVersionConflict,
    canonical_phase4_resource_scope_id,
    scoped_behavioral_model_id,
)
from app.engine.sii.behavioral_model_store import InMemoryBehavioralModelStore


def _scope(tenant: str = "org-1", workspace: str = "ws-1") -> AuthenticatedPhase4Scope:
    return AuthenticatedPhase4Scope(
        tenant_scope_id=tenant,
        workspace_id=workspace,
    )


def _model_id(scope: AuthenticatedPhase4Scope, business_id: str) -> str:
    return scoped_behavioral_model_id(scope, business_id)


def _model(model_id: str, version: str = "v1") -> dict:
    return {
        "model_id": model_id,
        "model_version": version,
        "signal_memory": {"flow": {"historical_center": 10.0}},
        "relationship_memory": {},
        "behavioral_graph": {},
        "operating_mode_memory": {},
        "expected_behavior_models": {},
        "baseline_versions": [],
    }


def test_model_identity_isolation_and_defensive_copies() -> None:
    store = InMemoryBehavioralModelStore()
    scope = _scope()
    model_a = _model_id(scope, "facility-a")
    model_b = _model_id(scope, "facility-b")
    store.create_model(scope, _model(model_a), source_run_id="run-a")
    store.create_model(scope, _model(model_b), source_run_id="run-b")

    loaded_a = store.load_model(scope, model_a)
    loaded_b = store.load_model(scope, model_b)
    assert loaded_a is not None and loaded_b is not None
    loaded_a["signal_memory"]["flow"]["historical_center"] = 999.0

    assert store.load_model(scope, model_a)["signal_memory"]["flow"]["historical_center"] == 10.0
    assert store.load_model(scope, model_b)["source_run_id"] == "run-b"


def test_snapshot_is_immutable_and_restore_creates_forward_model_version() -> None:
    store = InMemoryBehavioralModelStore()
    scope = _scope()
    model_id = _model_id(scope, "facility-a")
    store.create_model(scope, _model(model_id), source_run_id="run-1")
    snapshot = {
        "snapshot_id": "snapshot-1",
        "model_id": model_id,
        "model_version": "v1",
        "behavioral_identity": {},
        "signal_memory": {"flow": {"historical_center": 10.0}},
        "relationship_memory": {},
        "behavioral_graph": {},
        "operating_mode_memory": {},
        "expected_behavior_models": {},
        "baseline_versions": [],
    }
    store.create_snapshot(scope, snapshot, source_run_id="run-1")
    read_back = store.load_snapshot(scope, model_id, "snapshot-1")
    read_back["signal_memory"]["flow"]["historical_center"] = 200.0

    expected_snapshot = {
        **snapshot,
        "source_run_id": "run-1",
        "authenticated_scope": scope.as_dict(),
        "scope_digest": scope.scope_digest,
    }
    assert store.load_snapshot(scope, model_id, "snapshot-1") == expected_snapshot
    restored = store.restore_snapshot(scope, model_id, "snapshot-1", source_run_id="run-2")
    assert restored["model_version"] == "v2"
    assert restored["restored_from_snapshot_id"] == "snapshot-1"
    assert store.load_snapshot(scope, model_id, "snapshot-1")["model_version"] == "v1"


def test_versions_and_append_only_records_cannot_be_overwritten() -> None:
    store = InMemoryBehavioralModelStore()
    scope = _scope()
    model_id = _model_id(scope, "facility-a")
    store.create_model(scope, _model(model_id), source_run_id="run-1")
    with pytest.raises(BehavioralModelVersionConflict):
        store.save_model(scope, _model(model_id), source_run_id="run-2")

    event = {"event_id": "event-1", "event_type": "baseline_update"}
    assert store.append_event(scope, model_id, event, source_run_id="run-1")["event_id"] == "event-1"
    changed = deepcopy(event)
    changed["event_type"] = "maintenance_event"
    with pytest.raises(BehavioralModelVersionConflict):
        store.append_event(scope, model_id, changed, source_run_id="run-1")


def test_candidate_baseline_requires_approval_when_marked_pending() -> None:
    store = InMemoryBehavioralModelStore()
    scope = _scope()
    model_id = _model_id(scope, "facility-a")
    store.create_model(scope, _model(model_id), source_run_id="run-1")
    candidate = {
        "candidate_version": "baseline-v1",
        "approval_status": "pending_validation",
        "source_run_id": "run-1",
    }
    store.save_candidate_baseline(scope, model_id, candidate, source_run_id="run-1")

    with pytest.raises(BehavioralModelVersionConflict, match="human_validation_required"):
        store.activate_baseline(scope, model_id, "baseline-v1", source_run_id="run-1")

    active = store.activate_baseline(
        scope,
        model_id,
        "baseline-v1",
        source_run_id="run-2",
        approval={"actor": "operator", "outcome": "approved"},
    )
    assert active["active_version"] == "baseline-v1"
    assert active["human_approval"]["actor"] == "operator"
    state = store.export_state(scope, model_id)
    assert state["candidate_baselines"]["baseline-v1"]["approval_status"] == "pending_validation"
    assert state["activated_baselines"]["baseline-v1"]["approval_status"] == "approved"


def test_cross_scope_read_restore_event_and_baseline_operations_fail_closed() -> None:
    store = InMemoryBehavioralModelStore()
    owner = _scope("org-1", "ws-owner")
    attacker = _scope("org-1", "ws-attacker")
    model_id = _model_id(owner, "shared-system")
    store.create_model(owner, _model(model_id), source_run_id="owner-run")

    for operation in (
        lambda: store.load_model(attacker, model_id),
        lambda: store.save_model(attacker, _model(model_id, "v2"), source_run_id="attack"),
        lambda: store.create_snapshot(
            attacker,
            {"model_id": model_id, "snapshot_id": "attack"},
            source_run_id="attack",
        ),
        lambda: store.load_snapshot(attacker, model_id, "snapshot-1"),
        lambda: store.list_snapshots(attacker, model_id),
        lambda: store.restore_snapshot(attacker, model_id, "snapshot-1", source_run_id="attack"),
        lambda: store.append_event(attacker, model_id, {"event_id": "attack"}, source_run_id="attack"),
        lambda: store.record_learning_decision(
            attacker,
            model_id,
            {"decision_id": "attack"},
            source_run_id="attack",
        ),
        lambda: store.list_learning_decisions(attacker, model_id),
        lambda: store.retire_relationship(
            attacker,
            model_id,
            "relationship-1",
            source_run_id="attack",
            reason="attack",
        ),
        lambda: store.load_active_baseline(attacker, model_id),
        lambda: store.save_candidate_baseline(
            attacker,
            model_id,
            {"candidate_version": "attack"},
            source_run_id="attack",
        ),
        lambda: store.activate_baseline(attacker, model_id, "baseline-v1", source_run_id="attack"),
    ):
        with pytest.raises(BehavioralModelScopeMismatch, match="model_id_authenticated_scope_mismatch"):
            operation()

    assert store.export_state(owner, model_id)["write_audit"] == [
        {"operation": "create_model", "source_run_id": "owner-run", "reference": "v1"}
    ]


def test_same_business_id_is_distinct_across_workspace_and_tenant_scope() -> None:
    workspace_a = _scope("org-1", "ws-shared-a")
    workspace_b = _scope("org-1", "ws-shared-b")
    tenant_b = _scope("org-2", "ws-shared-a")
    ids = {_model_id(scope, "same-system") for scope in (workspace_a, workspace_b, tenant_b)}
    assert len(ids) == 3
    assert workspace_a.resource_scope_id == canonical_phase4_resource_scope_id("org-1", "ws-shared-a")
    assert workspace_a.resource_scope_id != workspace_b.resource_scope_id
    assert workspace_a.resource_scope_id != tenant_b.resource_scope_id


@pytest.mark.parametrize("field", ["tenant_scope_id", "workspace_id"])
def test_authenticated_scope_rejects_missing_tenant_or_workspace(field: str) -> None:
    values = {
        "tenant_scope_id": "org-1",
        "workspace_id": "ws-1",
        "resource_scope_id": "phase4-scope:incorrect",
    }
    values[field] = ""
    with pytest.raises(ValueError, match=f"authenticated_phase4_scope_missing:{field}"):
        AuthenticatedPhase4Scope(**values)


def test_authenticated_scope_rejects_noncanonical_resource_scope_override() -> None:
    with pytest.raises(ValueError, match="authenticated_phase4_scope_resource_mismatch"):
        AuthenticatedPhase4Scope(
            tenant_scope_id="org-1",
            workspace_id="ws-1",
            resource_scope_id="phase4-scope:incorrect",
        )
