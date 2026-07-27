from __future__ import annotations

from copy import deepcopy

from app.engine.sii.baseline_evolution import evaluate_baseline_evolution
from app.engine.sii.behavioral_evolution import evaluate_behavioral_evolution
from app.engine.sii.event_memory import prepare_event_memory
from app.engine.sii.propagation_analysis import PATH_MESSAGE, analyze_propagation


def _learning_inputs() -> dict:
    return {
        "active_model": None,
        "rows_count": 80,
        "numeric_columns": ["a", "b"],
        "operating_mode": {"baseline_mode": "running", "recent_mode": "running", "match": "strong"},
        "data_quality": {"readiness": "ready", "data_confidence": {"rating": "high"}},
        "sensor_health": {"signals": [{"signal": "a", "health": "healthy"}, {"signal": "b", "health": "healthy"}]},
        "temporal_analysis": {"instability_index": {"score": 0.05}, "decision_thresholding": {"state": "Normal"}},
        "multiscale_analysis": {"status": "complete", "cross_scale_classification": "agreement", "scales_used": ["15_minutes"]},
        "physics_reasoning": {"contradictory_priors": []},
        "expected_behavior": {"status": "limited", "models_evaluated": 0, "residual_evidence": []},
        "graph_comparison": {"status": "limited", "changed_edges": []},
        "active_observations": [],
        "source_run_id": "run-1",
        "effective_time": "2026-01-01T00:00:00Z",
        "model_version": "v1",
    }


def test_active_observation_blocks_baseline_learning() -> None:
    inputs = _learning_inputs()
    inputs["active_observations"] = [{"observation_id": "obs-1", "status": "unresolved"}]
    result = evaluate_baseline_evolution(**inputs)
    assert result["decision"] == "blocked_by_active_observation"
    assert result["learning_allowed"] is False
    assert result["candidate_baseline"] is None
    assert result["processing_trace"]["model_update_after_evidence_evaluation"] is True


def test_sensor_and_data_quality_safeguards_prevent_memory_update() -> None:
    sensor_inputs = _learning_inputs()
    sensor_inputs["sensor_health"]["signals"][1]["health"] = "review"
    sensor_result = evaluate_baseline_evolution(**sensor_inputs)
    assert sensor_result["decision"] == "blocked_by_sensor_health"

    quality_inputs = _learning_inputs()
    quality_inputs["data_quality"] = {"readiness": "not_ready", "data_confidence": {"rating": "low"}}
    quality_result = evaluate_baseline_evolution(**quality_inputs)
    assert quality_result["decision"] == "blocked_by_data_quality"


def test_human_validation_creates_candidate_without_activation() -> None:
    result = evaluate_baseline_evolution(
        **_learning_inputs(),
        config={"human_validation_required": True},
    )
    assert result["decision"] == "accepted"
    assert result["status"] == "pending_validation"
    assert result["learning_allowed"] is False
    assert result["candidate_baseline"]["approval_status"] == "pending_validation"
    assert result["candidate_baseline"]["active_version"] is None


def _relationship(
    relationship_id: str,
    source: str,
    target: str,
    *,
    direction: str = "lag_supported_source_to_target",
) -> dict:
    return {
        "relationship_id": relationship_id,
        "source_signal": source,
        "target_signal": target,
        "directionality_status": direction,
        "operating_modes_observed": ["running"],
        "current_strength": 0.9,
        "stability": "stable",
        "persistence": 4,
        "configured_lag_seconds": 60,
        "status": "active",
        "physics_prior_references": [],
        "lag_history": [],
    }


def _propagation_inputs() -> dict:
    relationships = {
        "ab": _relationship("ab", "a", "b"),
        "bc": _relationship("bc", "b", "c"),
    }
    return {
        "graph_comparison": {
            "changed_edges": [
                {"relationship_id": "ab", "source_signal": "a", "target_signal": "b"},
                {"relationship_id": "bc", "source_signal": "b", "target_signal": "c"},
            ]
        },
        "relationship_memory": relationships,
        "signal_drift": {"column_drift": [{"column": "a", "direction": "up"}, {"column": "c", "direction": "up"}]},
        "expected_behavior": {"residual_evidence": [{"target_signal": "c"}]},
        "operating_mode": {"recent_mode": "running"},
        "sensor_health": {"signals": [{"signal": item, "health": "healthy"} for item in "abc"]},
        "data_quality": {"readiness": "ready"},
        "multiscale_analysis": {"status": "complete", "cross_scale_classification": "agreement"},
        "signal_change_times": {
            "a": "2026-01-01T00:00:00Z",
            "b": "2026-01-01T00:01:00Z",
            "c": "2026-01-01T00:02:00Z",
        },
    }


def test_temporally_ordered_changes_create_non_causal_candidate_path() -> None:
    result = analyze_propagation(**_propagation_inputs())
    assert result["status"] == "complete"
    path = next(item for item in result["candidate_paths"] if item["nodes"] == ["a", "b", "c"])
    assert path["statement"] == PATH_MESSAGE
    assert path["causal_claim"] is False
    assert result["reasoning_trace"]["root_cause_selected"] is False
    assert result["propagation_confidence"]["not_probability"] is True


def test_competing_paths_remain_visible_and_no_cause_is_selected() -> None:
    inputs = _propagation_inputs()
    inputs["relationship_memory"]["ad"] = _relationship("ad", "a", "d")
    inputs["relationship_memory"]["dc"] = _relationship("dc", "d", "c")
    inputs["sensor_health"]["signals"].append({"signal": "d", "health": "healthy"})
    inputs["signal_change_times"]["d"] = "2026-01-01T00:01:00Z"
    result = analyze_propagation(**inputs)
    competing = next(item for item in result["competing_paths"] if item["start"] == "a" and item["end"] == "c")
    assert len(competing["candidate_path_ids"]) == 2
    assert competing["cause_selected"] is False
    assert result["uncertainty"]["cause_selected"] is False


def test_ambiguous_direction_is_preserved_as_unsupported_segment() -> None:
    inputs = _propagation_inputs()
    inputs["relationship_memory"]["ab"]["directionality_status"] = "association_only_direction_not_established"
    result = analyze_propagation(**inputs)
    unsupported = next(item for item in result["unsupported_segments"] if item["relationship_id"] == "ab")
    assert "direction_ambiguous" in unsupported["reasons"]
    assert not any(item["nodes"] == ["a", "b", "c"] for item in result["candidate_paths"])


def test_event_memory_keeps_external_and_telemetry_events_distinguishable() -> None:
    result = prepare_event_memory(
        external_events=[
            {
                "event_id": "maintenance-1",
                "event_type": "maintenance_event",
                "timestamp": "2026-01-01T00:00:00Z",
                "source": "operator_log",
                "affected_signals": ["a"],
            }
        ],
        expected_behavior={"residual_evidence": [{"target_signal": "b", "source_relationships": ["ab"]}]},
        graph_comparison={"edge_emergence": []},
        operating_mode={"baseline_mode": "running", "recent_mode": "running"},
        learning_decision={"decision": "blocked_by_active_observation"},
        source_run_id="run-2",
        timestamp="2026-01-02T00:00:00Z",
        model_version_before="v1",
        model_version_after="v1",
        baseline_version_before="baseline-v1",
        baseline_version_after="baseline-v1",
    )
    assert result["externally_supplied_events"][0]["source_origin"] == "externally_supplied"
    assert result["telemetry_derived_events"][0]["source_origin"] == "telemetry_derived"
    assert {item["event_type"] for item in result["events"]} == {"maintenance_event", "significant_behavioral_observation"}


def test_long_term_evolution_never_equates_change_with_degradation() -> None:
    active = {
        "model_version": "v2",
        "signal_memory": {"a": {"historical_center": 10.0, "historical_scale": 1.0, "drift_history": []}},
        "relationship_memory": {},
        "operating_mode_memory": {"running": {}},
        "model_confidence_history": [{"compatibility": 0.5, "factors": {}}],
    }
    result = evaluate_behavioral_evolution(
        active_model=active,
        snapshots=[],
        rows=[{"a": 14.0} for _ in range(10)],
        numeric_columns=["a"],
        relationship_graph_comparison={"changed_edges": [], "graph_fragmentation": {}},
        operating_mode={"recent_mode": "running"},
        expected_behavior={"residual_evidence": []},
        learning_decision={"decision": "blocked_by_instability"},
        current_confidence={"compatibility": 0.4, "factors": {}},
    )
    assert result["signal_changes"][0]["classification"] == "temporary_deviation"
    assert result["processing_trace"]["degradation_claimed"] is False
    assert "not interpreted as degradation" in result["limitations"][0]
