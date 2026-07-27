from __future__ import annotations

import math

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


def test_phase4_persists_signal_relationship_graph_and_immutable_snapshots() -> None:
    store = InMemoryBehavioralModelStore()
    first = evaluate_phase4(**_phase4_args(store, run_id="run-1"))
    assert first["behavioral_model"]["status"] == "complete"
    assert first["behavioral_model"]["model_version"] == "v1"
    assert first["behavioral_model"]["signal_memory_summary"]["signals_tracked"] == 2
    assert first["behavioral_model"]["relationship_memory_summary"]["relationships_tracked"] == 1
    first_snapshot_id = first["behavioral_snapshots"]["current_snapshot_id"]
    model_id = first["behavioral_model"]["model_id"]
    first_snapshot = store.load_snapshot(model_id, first_snapshot_id)

    second = evaluate_phase4(**_phase4_args(store, run_id="run-2"))
    assert second["behavioral_model"]["model_version"] == "v2"
    assert second["expected_behavior"]["status"] == "complete"
    assert second["expected_behavior"]["models_evaluated"] == 2
    assert second["behavioral_snapshots"]["previous_snapshot_id"] == first_snapshot_id
    assert store.load_snapshot(model_id, first_snapshot_id) == first_snapshot
    assert len(store.list_snapshots(model_id)) == 2
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
    model_before = store.load_model(model_id)
    inputs = _phase4_args(store, run_id="quality-bad")
    inputs["data_quality"] = {"readiness": "not_ready", "data_confidence": {"rating": "low"}}
    result = evaluate_phase4(**inputs)
    assert result["behavioral_model"]["learning_decision"]["decision"] == "blocked_by_data_quality"
    assert store.load_model(model_id) == model_before
