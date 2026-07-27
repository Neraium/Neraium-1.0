from __future__ import annotations

from copy import deepcopy

import pytest

from app.engine.sii.behavioral_model_contract import BehavioralModelVersionConflict
from app.engine.sii.behavioral_model_store import InMemoryBehavioralModelStore


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
    store.create_model(_model("facility-a"), source_run_id="run-a")
    store.create_model(_model("facility-b"), source_run_id="run-b")

    loaded_a = store.load_model("facility-a")
    loaded_b = store.load_model("facility-b")
    assert loaded_a is not None and loaded_b is not None
    loaded_a["signal_memory"]["flow"]["historical_center"] = 999.0

    assert store.load_model("facility-a")["signal_memory"]["flow"]["historical_center"] == 10.0
    assert store.load_model("facility-b")["source_run_id"] == "run-b"


def test_snapshot_is_immutable_and_restore_creates_forward_model_version() -> None:
    store = InMemoryBehavioralModelStore()
    store.create_model(_model("facility-a"), source_run_id="run-1")
    snapshot = {
        "snapshot_id": "snapshot-1",
        "model_id": "facility-a",
        "model_version": "v1",
        "behavioral_identity": {},
        "signal_memory": {"flow": {"historical_center": 10.0}},
        "relationship_memory": {},
        "behavioral_graph": {},
        "operating_mode_memory": {},
        "expected_behavior_models": {},
        "baseline_versions": [],
    }
    store.create_snapshot(snapshot, source_run_id="run-1")
    read_back = store.load_snapshot("facility-a", "snapshot-1")
    read_back["signal_memory"]["flow"]["historical_center"] = 200.0

    assert store.load_snapshot("facility-a", "snapshot-1") == {**snapshot, "source_run_id": "run-1"}
    restored = store.restore_snapshot("facility-a", "snapshot-1", source_run_id="run-2")
    assert restored["model_version"] == "v2"
    assert restored["restored_from_snapshot_id"] == "snapshot-1"
    assert store.load_snapshot("facility-a", "snapshot-1")["model_version"] == "v1"


def test_versions_and_append_only_records_cannot_be_overwritten() -> None:
    store = InMemoryBehavioralModelStore()
    store.create_model(_model("facility-a"), source_run_id="run-1")
    with pytest.raises(BehavioralModelVersionConflict):
        store.save_model(_model("facility-a"), source_run_id="run-2")

    event = {"event_id": "event-1", "event_type": "baseline_update"}
    assert store.append_event("facility-a", event, source_run_id="run-1")["event_id"] == "event-1"
    changed = deepcopy(event)
    changed["event_type"] = "maintenance_event"
    with pytest.raises(BehavioralModelVersionConflict):
        store.append_event("facility-a", changed, source_run_id="run-1")


def test_candidate_baseline_requires_approval_when_marked_pending() -> None:
    store = InMemoryBehavioralModelStore()
    store.create_model(_model("facility-a"), source_run_id="run-1")
    candidate = {
        "candidate_version": "baseline-v1",
        "approval_status": "pending_validation",
        "source_run_id": "run-1",
    }
    store.save_candidate_baseline("facility-a", candidate, source_run_id="run-1")

    with pytest.raises(BehavioralModelVersionConflict, match="human_validation_required"):
        store.activate_baseline("facility-a", "baseline-v1", source_run_id="run-1")

    active = store.activate_baseline(
        "facility-a",
        "baseline-v1",
        source_run_id="run-2",
        approval={"actor": "operator", "outcome": "approved"},
    )
    assert active["active_version"] == "baseline-v1"
    assert active["human_approval"]["actor"] == "operator"
    state = store.export_state("facility-a")
    assert state["candidate_baselines"]["baseline-v1"]["approval_status"] == "pending_validation"
    assert state["activated_baselines"]["baseline-v1"]["approval_status"] == "approved"
