from __future__ import annotations

from app.engine.sii.behavioral_graph import compare_behavioral_graph, update_behavioral_graph
from app.engine.sii.expected_behavior import evaluate_expected_behavior, train_expected_behavior_models


def _rows(count: int = 80, violation: float = 0.0) -> list[dict]:
    rows = []
    for index in range(count):
        flow = 10.0 + index * 0.2
        pressure = 2.0 + flow * 3.0
        if index >= int(count * 0.7):
            pressure += violation
        rows.append(
            {
                "timestamp": f"2026-01-01T{index // 60:02d}:{index % 60:02d}:00Z",
                "flow": flow,
                "pressure": pressure,
            }
        )
    return rows


def _relationship_memory() -> dict:
    return {
        "rel-1": {
            "source_signal": "flow",
            "target_signal": "pressure",
            "status": "active",
            "operating_modes_observed": ["running"],
            "current_strength": 0.99,
        }
    }


def _health() -> dict:
    return {
        "signals": [
            {"signal": "flow", "health": "healthy"},
            {"signal": "pressure", "health": "healthy"},
        ]
    }


def test_expected_behavior_is_transparent_and_violation_is_evidence_not_diagnosis() -> None:
    models = train_expected_behavior_models(
        rows=_rows(),
        relationship_memory=_relationship_memory(),
        operating_mode="running",
        timestamp_column="timestamp",
        source_run_id="run-1",
        training_time="2026-01-01T01:19:00Z",
    )
    assert len(models) == 2
    pressure_model = next(item for item in models.values() if item["target_signal"] == "pressure")
    assert pressure_model["model_type"] == "robust_theil_sen_linear_response"
    assert pressure_model["model_parameters"]["slope"] == 3.0
    assert pressure_model["validation"]["passed"] is True

    result = evaluate_expected_behavior(
        active_model={"expected_behavior_models": models},
        rows=_rows(80, violation=25.0),
        operating_mode="running",
        data_quality={"readiness": "ready", "data_confidence": {"rating": "high"}},
        sensor_health=_health(),
        source_model_version="v1",
        evaluation_time="2026-01-02T01:19:00Z",
    )

    assert result["status"] == "complete"
    pressure = next(item for item in result["expected_values"] if item["target_signal"] == "pressure")
    assert pressure["expected_interval"][0] <= pressure["expected_value"] <= pressure["expected_interval"][1]
    assert pressure["observed_value"] > pressure["expected_value"]
    evidence = next(item for item in result["residual_evidence"] if item["target_signal"] == "pressure")
    assert evidence["diagnosis"] is None
    assert evidence["failure_claim"] is False
    assert pressure["confidence"]["not_probability"] is True


def test_expected_behavior_refuses_unhealthy_signal() -> None:
    models = train_expected_behavior_models(
        rows=_rows(),
        relationship_memory=_relationship_memory(),
        operating_mode="running",
        timestamp_column="timestamp",
        source_run_id="run-1",
        training_time="2026-01-01T01:19:00Z",
    )
    health = _health()
    health["signals"][1]["health"] = "review"
    result = evaluate_expected_behavior(
        active_model={"expected_behavior_models": models},
        rows=_rows(),
        operating_mode="running",
        data_quality={"readiness": "ready", "data_confidence": {"rating": "high"}},
        sensor_health=health,
        source_model_version="v1",
        evaluation_time="2026-01-02T01:19:00Z",
    )
    assert all(item["target_signal"] != "pressure" for item in result["expected_values"])
    assert any("sensor_health_not_acceptable:pressure" in reason for item in result["unavailable_models"] for reason in item["reasons"])


def test_behavioral_graph_reports_competing_structural_views_without_causality() -> None:
    active = {
        "nodes": {"a": {"node_id": "a"}, "b": {"node_id": "b"}, "c": {"node_id": "c"}},
        "edges": {
            "relationship:one": {
                "relationship_id": "relationship:one",
                "source_signal": "a",
                "target_signal": "b",
                "relationship_type": "linear_correlation",
                "operating_mode": "running",
                "current_strength": 0.9,
            },
            "relationship:two": {
                "relationship_id": "relationship:two",
                "source_signal": "b",
                "target_signal": "c",
                "relationship_type": "linear_correlation",
                "operating_mode": "running",
                "current_strength": 0.85,
            },
        },
    }
    current = {
        "nodes": [
            {"id": "metric:a", "type": "metric", "source_column": "a"},
            {"id": "metric:b", "type": "metric", "source_column": "b"},
            {"id": "metric:c", "type": "metric", "source_column": "c"},
        ],
        "eligible_edges": [
            {
                "source": "metric:a",
                "target": "metric:b",
                "columns": ["a", "b"],
                "relationship_type": "linear_correlation",
                "current_strength": 0.3,
            },
            {
                "source": "metric:b",
                "target": "metric:c",
                "columns": ["b", "c"],
                "relationship_type": "linear_correlation",
                "current_strength": 0.2,
            },
        ],
    }
    # Use a stored graph created through the same deterministic id contract.
    stored = update_behavioral_graph(
        active_graph=None,
        current_graph=current,
        signal_memory={
            "a": {"source_column": "a"},
            "b": {"source_column": "b"},
            "c": {"source_column": "c"},
        },
        relationship_memory={},
        event_references=[],
        source_run_id="run-1",
        model_version="v1",
        allow_learning=True,
    )
    current_ids = []
    comparison_seed = compare_behavioral_graph(
        current_graph=current,
        active_graph=None,
        operating_mode="running",
    )
    current_ids = [item["relationship_id"] for item in comparison_seed["edge_emergence"]]
    active["edges"] = {
        current_ids[0]: {**active["edges"]["relationship:one"], "relationship_id": current_ids[0]},
        current_ids[1]: {**active["edges"]["relationship:two"], "relationship_id": current_ids[1]},
    }
    comparison = compare_behavioral_graph(
        current_graph=current,
        active_graph=active,
        previous_snapshot_graph=active,
        long_term_reference_graph=active,
        operating_mode="running",
        change_threshold=0.2,
    )
    assert len(comparison["edge_weakening"]) == 2
    assert comparison["coordinated_edge_weakening"] is True
    assert comparison["changed_edge_clusters"][0]["edge_count"] == 2
    assert all(item["causal_claim"] is False for item in comparison["graph_evidence"])
