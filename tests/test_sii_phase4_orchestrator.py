from __future__ import annotations

import math
from copy import deepcopy

from app.engine.sii.behavioral_graph import compare_behavioral_graph, compare_long_horizon_graph, relationship_memory_id
from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.engine.sii.behavioral_model_store import InMemoryBehavioralModelStore
from app.engine.sii.phase4 import evaluate_phase4


def _rows(*, violation: float = 0.0) -> list[dict]:
    output = []
    for index in range(120):
        flow = 100.0 + math.sin(index / 8.0) * 4.0
        pressure = 20.0 + flow * 0.5
        if index >= 84:
            pressure += violation
        output.append(
            {
                "timestamp": f"2026-01-01T{index // 60:02d}:{index % 60:02d}:00Z",
                "flow": flow,
                "pressure": pressure,
            }
        )
    return output


def _phase4_args(store, *, run_id: str, violation: float = 0.0) -> dict:
    rows = _rows(violation=violation)
    edge = {
        "id": "relationship:flow:pressure",
        "source": "metric:flow",
        "target": "metric:pressure",
        "columns": ["flow", "pressure"],
        "relationship": "flow <-> pressure",
        "relationship_type": "linear_correlation",
        "baseline_correlation": 0.99,
        "current_correlation": 0.99,
        "baseline_strength": 0.99,
        "current_strength": 0.99,
        "baseline_sample_count": 84,
        "current_sample_count": 36,
        "confidence": 0.95,
    }
    graph = {
        "status": "complete",
        "nodes": [
            {"id": "metric:flow", "type": "metric", "source_column": "flow"},
            {"id": "metric:pressure", "type": "metric", "source_column": "pressure"},
        ],
        "edges": [edge],
        "eligible_edges": [edge],
        "changed_edges": [],
    }
    return {
        "phase4_scope": AuthenticatedPhase4Scope(
            tenant_scope_id="org-1",
            workspace_id="ws-1",
        ),
        "columns": ["timestamp", "flow", "pressure"],
        "rows": rows,
        "numeric_columns": ["flow", "pressure"],
        "timestamp_column": "timestamp",
        "telemetry_signal_catalog": {},
        "data_quality": {"readiness": "ready", "data_confidence": {"rating": "high"}},
        "sensor_health": {
            "signals": [
                {"signal": "flow", "health": "healthy", "conditions": []},
                {"signal": "pressure", "health": "healthy", "conditions": []},
            ]
        },
        "operating_mode": {
            "baseline_mode": "running",
            "recent_mode": "running",
            "match": "strong",
            "confidence": "high",
            "features": {"baseline": {"state": "running"}, "recent": {"state": "running"}},
        },
        "signal_drift": {"status": "complete", "column_drift": [{"column": "flow", "direction": "flat"}, {"column": "pressure", "direction": "flat"}]},
        "relationship_analysis": {"status": "complete"},
        "relationship_graph": graph,
        "temporal_analysis": {
            "status": "complete",
            "instability_index": {"score": 0.02},
            "decision_thresholding": {"state": "Normal"},
            "mutual_information_drift": {"score": 0.0},
            "lagged_relationships": {"dominant_lag_shift": 0},
            "rate_of_change": {"velocity": 0.0, "acceleration": 0.0},
        },
        "multiscale_analysis": {"status": "complete", "cross_scale_classification": "stable_across_scales", "scales_used": ["15_minutes", "1_hour"]},
        "physics_reasoning": {"status": "limited", "applicable_priors": [], "contradictory_priors": []},
        "covariance_analysis": {"status": "complete"},
        "config": {
            "source_run_id": run_id,
            "infrastructure_identity": {"organization_id": "org-1", "facility_id": "facility-1", "system_id": "system-1"},
            "behavioral_model_store": store,
        },
    }


def _strength_args(store, run_id: str, strength: float) -> dict:
    args = _phase4_args(store, run_id=run_id)
    edge = args["relationship_graph"]["edges"][0]
    edge["current_strength"] = strength
    edge["current_correlation"] = strength
    return args


def _cumulative_edge(result: dict) -> dict:
    return result["behavioral_graph_comparison"]["long_horizon_cumulative"]["edges"][0]


def _cumulative_from_snapshots(store, snapshots: list[dict]) -> dict:
    args = _strength_args(store, "current", 0.64)
    scope = args["phase4_scope"]
    return compare_long_horizon_graph(
        current_graph=args["relationship_graph"], snapshots=snapshots, operating_mode="running",
        authenticated_scope=scope.as_dict(), model_id=snapshots[0]["model_id"],
        source_run_id="current", model_version="v2",
    )


def _carried_snapshot(previous: dict, snapshot_id: str) -> dict:
    copy = deepcopy(previous)
    copy["snapshot_id"] = snapshot_id
    copy["previous_snapshot_id"] = previous["snapshot_id"]
    copy["source_run_id"] = snapshot_id
    return copy


def test_cumulative_reference_provenance_tracks_one_and_multiple_carried_edges() -> None:
    store = InMemoryBehavioralModelStore()
    first = evaluate_phase4(**_strength_args(store, "base", 0.4))
    scope = _strength_args(store, "unused", 0.4)["phase4_scope"]
    origin = store.list_snapshots(scope, first["behavioral_model"]["model_id"])[0]
    one = _carried_snapshot(origin, "carried-1")
    two = _carried_snapshot(one, "carried-2")
    for snapshots in ([one, origin], [two, one, origin]):
        comparison = _cumulative_from_snapshots(store, snapshots)
        edge = comparison["edges"][0]
        assert edge["status"] == "available"
        assert edge["reference_strength"] == 0.4
        assert edge["signed_displacement"] == 0.24
        assert (edge["reference_snapshot_id"], edge["reference_source_run_id"], edge["reference_model_version"]) == (
            origin["snapshot_id"], "base", "v1",
        )
        assert comparison["reference_snapshot_id"] == origin["snapshot_id"]


def test_cumulative_reference_provenance_is_unavailable_without_unique_retained_origin() -> None:
    store = InMemoryBehavioralModelStore()
    first = evaluate_phase4(**_strength_args(store, "base", 0.4))
    scope = _strength_args(store, "unused", 0.4)["phase4_scope"]
    origin = store.list_snapshots(scope, first["behavioral_model"]["model_id"])[0]
    one = _carried_snapshot(origin, "carried-1")
    two = _carried_snapshot(one, "carried-2")
    duplicate = deepcopy(one)
    duplicate["behavioral_graph"]["edges"].clear()
    false_root = deepcopy(one)
    false_root["previous_snapshot_id"] = None
    for snapshots in ([one], [two, one], [two, one, duplicate, origin], [false_root]):
        comparison = _cumulative_from_snapshots(store, snapshots)
        edge = comparison["edges"][0]
        assert edge["status"] == "available"
        assert edge["reference_strength"] == 0.4
        assert edge["signed_displacement"] == 0.24
        assert (edge["reference_snapshot_id"], edge["reference_source_run_id"], edge["reference_model_version"]) == (
            None, None, None,
        )
        assert comparison["reference_snapshot_id"] is None


def test_cumulative_drift_survives_accepted_active_baseline_updates() -> None:
    store = InMemoryBehavioralModelStore()
    first = evaluate_phase4(**_strength_args(store, "run-base", 0.99))
    assert _cumulative_edge(first)["status"] == "unavailable"
    assert _cumulative_edge(first)["reference_snapshot_id"] is None
    first_id = first["behavioral_snapshots"]["current_snapshot_id"]
    for index, strength in enumerate((0.87, 0.75, 0.63), start=1):
        result = evaluate_phase4(**_strength_args(store, f"run-{index}", strength))
        comparison = result["behavioral_graph_comparison"]
        edge = _cumulative_edge(result)
        assert comparison["changed_edges"] == []
        assert comparison["processing_trace"]["change_threshold"] == 0.20
        assert result["behavioral_model"]["model_version"] == f"v{index + 1}"
        assert result["processing_trace"]["learning_allowed"] is True
        assert edge["reference_snapshot_id"] == first_id
        assert edge["signed_displacement"] == round(strength - 0.99, 6)
        assert edge["threshold_crossed"] is (index >= 2)
        assert edge["persistence_inferred"] is False
    assert len(store.list_snapshots(_strength_args(store, "unused", 0.99)["phase4_scope"], first["behavioral_model"]["model_id"])) == 4


def test_cumulative_transient_and_alternating_values_do_not_accumulate_or_imply_persistence() -> None:
    store = InMemoryBehavioralModelStore()
    first = evaluate_phase4(**_strength_args(store, "base", 0.4))
    reference_id = first["behavioral_snapshots"]["current_snapshot_id"]
    for run_id, strength, expected in (("step", 0.75, 0.35), ("return", 0.4, 0.0), ("up", 0.52, 0.12), ("down", 0.34, -0.06), ("up-again", 0.52, 0.12)):
        result = evaluate_phase4(**_strength_args(store, run_id, strength))
        edge = _cumulative_edge(result)
        assert edge["reference_snapshot_id"] == reference_id
        assert edge["signed_displacement"] == expected
        assert edge["persistence_inferred"] is False
        if run_id == "step":
            assert result["behavioral_graph_comparison"]["edge_strengthening"][0]["strength_delta"] == 0.35
            assert edge["threshold_crossed"] is True
        if run_id == "return":
            assert edge["threshold_crossed"] is False


def test_cumulative_provenance_missing_edge_and_active_numerics_are_independent() -> None:
    store = InMemoryBehavioralModelStore()
    first = evaluate_phase4(**_strength_args(store, "base", 0.4))
    scope = _strength_args(store, "unused", 0.4)["phase4_scope"]
    model_id = first["behavioral_model"]["model_id"]
    snapshot = store.list_snapshots(scope, model_id)[0]
    active = store.load_model(scope, model_id)["behavioral_graph"]
    args = _strength_args(store, "current", 0.64)
    before = compare_behavioral_graph(current_graph=args["relationship_graph"], active_graph=active, operating_mode="running")
    current_graph_copy = deepcopy(args["relationship_graph"])
    snapshot_copy = deepcopy(snapshot)
    cumulative = compare_long_horizon_graph(
        current_graph=args["relationship_graph"], snapshots=[snapshot], operating_mode="running",
        authenticated_scope=scope.as_dict(), model_id=model_id, source_run_id="current",
        model_version="v1", operating_context=args["operating_mode"],
    )
    edge = cumulative["edges"][0]
    assert edge["relationship_id"] == relationship_memory_id("flow", "pressure", "linear_correlation", "running")
    assert edge["authenticated_scope"] == scope.as_dict()
    assert edge["model_id"] == model_id
    assert edge["operating_mode"] == "running"
    assert edge["current_operating_context"] == args["operating_mode"]
    assert edge["reference_mode_context"]["mode_id"] == "running"
    assert edge["reference_snapshot_id"] == snapshot["snapshot_id"]
    assert edge["reference_source_run_id"] == "base"
    assert edge["reference_model_version"] == "v1"
    assert edge["source_run_id"] == "current"
    assert edge["model_version"] == "v1"
    assert edge["signed_displacement"] == 0.24
    assert args["relationship_graph"] == current_graph_copy
    assert snapshot == snapshot_copy
    assert compare_behavioral_graph(current_graph=args["relationship_graph"], active_graph=active, operating_mode="running") == before
    assert before["changed_edges"][0]["strength_delta"] == 0.24
    assert before["processing_trace"]["change_threshold"] == 0.20

    absent = deepcopy(snapshot)
    absent["behavioral_graph"]["edges"].pop(edge["relationship_id"])
    absent["behavioral_graph"]["edges"][relationship_memory_id("other", "signal", "linear_correlation", "running")] = {
        "source_signal": "other", "target_signal": "signal", "relationship_type": "linear_correlation", "current_strength": 0.8,
    }
    missing = compare_long_horizon_graph(current_graph=args["relationship_graph"], snapshots=[absent, snapshot], operating_mode="running", authenticated_scope=scope.as_dict(), model_id=model_id, source_run_id="current", model_version="v1")["edges"][0]
    assert missing["status"] == "unavailable"
    assert missing["unavailable_reason"] == "relationship_reference_unavailable"
    assert missing["reference_snapshot_id"] is None
    assert missing["signed_displacement"] is None
    no_mode = compare_long_horizon_graph(current_graph=args["relationship_graph"], snapshots=[snapshot], operating_mode="idle", authenticated_scope=scope.as_dict(), model_id=model_id, source_run_id="current", model_version="v1")["edges"][0]
    assert no_mode["status"] == "unavailable"
    assert no_mode["unavailable_reason"] == "mode_matched_reference_unavailable"
    wrong_scope = compare_long_horizon_graph(current_graph=args["relationship_graph"], snapshots=[snapshot], operating_mode="running", authenticated_scope={**scope.as_dict(), "workspace_id": "different"}, model_id=model_id, source_run_id="current", model_version="v1")["edges"][0]
    assert wrong_scope["status"] == "unavailable"


def test_phase4_persists_signal_relationship_graph_and_immutable_snapshots() -> None:
    store = InMemoryBehavioralModelStore()
    first = evaluate_phase4(**_phase4_args(store, run_id="run-1"))
    assert first["behavioral_model"]["status"] == "complete"
    assert first["behavioral_model"]["model_version"] == "v1"
    assert first["behavioral_model"]["signal_memory_summary"]["signals_tracked"] == 2
    assert first["behavioral_model"]["relationship_memory_summary"]["relationships_tracked"] == 1
    first_snapshot_id = first["behavioral_snapshots"]["current_snapshot_id"]
    model_id = first["behavioral_model"]["model_id"]
    scope = _phase4_args(store, run_id="unused")["phase4_scope"]
    first_snapshot = store.load_snapshot(scope, model_id, first_snapshot_id)

    second = evaluate_phase4(**_phase4_args(store, run_id="run-2"))
    assert second["behavioral_model"]["model_version"] == "v2"
    assert second["expected_behavior"]["status"] == "complete"
    assert second["expected_behavior"]["models_evaluated"] == 2
    assert second["behavioral_snapshots"]["previous_snapshot_id"] == first_snapshot_id
    assert store.load_snapshot(scope, model_id, first_snapshot_id) == first_snapshot
    assert len(store.list_snapshots(scope, model_id)) == 2
    assert second["processing_trace"]["current_evidence_evaluated_before_model_update"] is True


def test_injected_residual_is_evidence_and_blocks_learning_without_diagnosis() -> None:
    store = InMemoryBehavioralModelStore()
    evaluate_phase4(**_phase4_args(store, run_id="run-1"))
    result = evaluate_phase4(**_phase4_args(store, run_id="run-violation", violation=30.0))
    assert result["expected_behavior"]["residual_evidence"]
    assert result["behavioral_model"]["learning_decision"]["decision"] == "blocked_by_active_observation"
    assert result["behavioral_model"]["model_version"] == "v1"
    assert all(item["diagnosis"] is None for item in result["expected_behavior"]["residual_evidence"])
    assert result["processing_trace"]["learning_allowed"] is False


def test_identical_starting_models_and_inputs_produce_identical_phase4_output() -> None:
    left_store = InMemoryBehavioralModelStore()
    right_store = InMemoryBehavioralModelStore()
    left = evaluate_phase4(**_phase4_args(left_store, run_id="deterministic-run"))
    right = evaluate_phase4(**_phase4_args(right_store, run_id="deterministic-run"))
    assert left == right


def test_identity_isolation_prevents_cross_facility_memory() -> None:
    store = InMemoryBehavioralModelStore()
    facility_a = _phase4_args(store, run_id="facility-a")
    facility_b = _phase4_args(store, run_id="facility-b")
    facility_b["config"]["infrastructure_identity"]["facility_id"] = "facility-2"
    facility_b["config"]["infrastructure_identity"]["system_id"] = "system-2"
    first = evaluate_phase4(**facility_a)
    second = evaluate_phase4(**facility_b)
    assert first["behavioral_model"]["model_id"] != second["behavioral_model"]["model_id"]
    assert first["behavioral_model"]["model_version"] == "v1"
    assert second["behavioral_model"]["model_version"] == "v1"


class _FailingStore:
    def load_model(self, _model_id):
        raise RuntimeError("storage offline")

    def list_snapshots(self, _model_id):
        raise RuntimeError("storage offline")


def test_storage_failure_returns_limited_phase4_without_raising() -> None:
    result = evaluate_phase4(**_phase4_args(_FailingStore(), run_id="storage-failure"))
    assert result["behavioral_model"]["status"] == "limited"
    assert result["behavioral_model"]["active"] is False
    assert result["behavioral_model"]["learning_decision"]["decision"] == "insufficient_evidence"
    assert result["processing_trace"]["storage_failures"]
    assert result["bayesian_evidence"]["posterior"] is None


def test_data_quality_block_does_not_change_active_model_version_or_memory() -> None:
    store = InMemoryBehavioralModelStore()
    first = evaluate_phase4(**_phase4_args(store, run_id="quality-good"))
    model_id = first["behavioral_model"]["model_id"]
    scope = inputs_scope = _phase4_args(store, run_id="unused")["phase4_scope"]
    model_before = store.load_model(scope, model_id)
    inputs = _phase4_args(store, run_id="quality-bad")
    inputs["data_quality"] = {"readiness": "not_ready", "data_confidence": {"rating": "low"}}
    result = evaluate_phase4(**inputs)
    assert result["behavioral_model"]["learning_decision"]["decision"] == "blocked_by_data_quality"
    assert store.load_model(inputs_scope, model_id) == model_before


def test_missing_authenticated_scope_is_limited_and_performs_no_storage() -> None:
    store = InMemoryBehavioralModelStore()
    inputs = _phase4_args(store, run_id="missing-scope")
    inputs["phase4_scope"] = None
    result = evaluate_phase4(**inputs)

    assert result["behavioral_model"]["status"] == "limited"
    assert result["behavioral_model"]["limitations"] == ["authenticated_scope_unavailable"]
    assert result["behavioral_model"]["identity"] == {
        "identity_status": "limited",
        "identity_limitations": ["authenticated_scope_unavailable"],
        "memory_update_allowed": False,
    }
    assert result["processing_trace"]["storage_writes"] == []


def test_payload_scope_mismatch_is_limited_and_performs_no_storage() -> None:
    store = InMemoryBehavioralModelStore()
    for claim, value in (("workspace_id", "ws-other"), ("tenant_id", "org-other")):
        inputs = _phase4_args(store, run_id=f"mismatch-{claim}")
        inputs["config"]["infrastructure_identity"][claim] = value
        result = evaluate_phase4(**inputs)
        assert result["behavioral_model"]["limitations"] == [
            f"authenticated_scope_mismatch:{claim}"
        ]
        assert result["processing_trace"]["storage_writes"] == []


def test_same_business_identity_isolated_by_authenticated_workspace() -> None:
    store = InMemoryBehavioralModelStore()
    first_inputs = _phase4_args(store, run_id="workspace-a")
    second_inputs = _phase4_args(store, run_id="workspace-b")
    second_inputs["phase4_scope"] = AuthenticatedPhase4Scope(
        tenant_scope_id="org-1",
        workspace_id="ws-2",
    )
    first = evaluate_phase4(**first_inputs)
    second = evaluate_phase4(**second_inputs)
    assert first["behavioral_model"]["model_id"] != second["behavioral_model"]["model_id"]
    assert first["behavioral_model"]["model_version"] == "v1"
    assert second["behavioral_model"]["model_version"] == "v1"


def test_configured_learning_delay_matures_from_persisted_decision_history() -> None:
    store = InMemoryBehavioralModelStore()
    first_inputs = _phase4_args(store, run_id="delay-run-1")
    first_inputs["config"]["phase_4_config"] = {
        "baseline_evolution_config": {"learning_delay_runs": 2}
    }
    first = evaluate_phase4(**first_inputs)
    assert first["behavioral_model"]["learning_decision"]["decision"] == "deferred"
    assert first["behavioral_model"]["model_version"] is None

    second_inputs = _phase4_args(store, run_id="delay-run-2")
    second_inputs["config"]["phase_4_config"] = {
        "baseline_evolution_config": {"learning_delay_runs": 2}
    }
    second = evaluate_phase4(**second_inputs)
    assert second["behavioral_model"]["learning_decision"]["decision"] == "accepted"
    assert second["behavioral_model"]["model_version"] == "v1"
