from __future__ import annotations

import math

from app.engine.sii.baseline_evolution import evaluate_baseline_evolution
from app.engine.sii.behavioral_evolution import evaluate_behavioral_evolution
from app.engine.sii.behavioral_graph import (
    compare_behavioral_graph,
    relationship_memory_id,
)
from app.engine.sii.expected_behavior import train_expected_behavior_models
from app.engine.sii.multiscale_analysis import _scale_behavior_patterns
from app.engine.sii.physics_reasoning import evaluate_physics_reasoning
from app.engine.sii.propagation_analysis import analyze_propagation
from app.engine.sii_contract import uncertainty_section


def test_graph_laplacian_metrics_identify_coordinated_structural_change() -> None:
    pairs = (("a", "b"), ("b", "c"), ("a", "c"))
    active_edges = {}
    current_edges = []
    for left, right in pairs:
        relationship_id = relationship_memory_id(
            left,
            right,
            "linear_correlation",
            "running",
        )
        active_edges[relationship_id] = {
            "relationship_id": relationship_id,
            "source_signal": left,
            "target_signal": right,
            "current_strength": 0.8,
        }
        current_edges.append(
            {
                "columns": [left, right],
                "relationship_type": "linear_correlation",
                "current_strength": 0.4,
            }
        )
    result = compare_behavioral_graph(
        current_graph={"eligible_edges": current_edges},
        active_graph={"nodes": {}, "edges": active_edges},
        operating_mode="running",
        change_threshold=0.2,
    )
    mathematics = result["graph_mathematics"]
    assert mathematics["graph_signal_smoothness"]["dirichlet_energy"] == 0.0
    assert mathematics["graph_stability"]["weighted_jaccard_similarity"] == 0.5
    assert mathematics["structural_entropy"]["delta"] == 0.0
    assert mathematics["community_evolution"]["split_count"] == 0
    assert mathematics["centrality"][0]["betweenness_centrality"] == 0.0
    assert mathematics["limitations"][1].endswith("not a learned embedding.")


def test_expected_behavior_selects_transparent_time_ordered_lag() -> None:
    rows = []
    predictor_values = [math.sin(index / 5.0) + index * 0.01 for index in range(80)]
    for index, predictor in enumerate(predictor_values):
        delayed = predictor_values[max(0, index - 2)]
        rows.append(
            {
                "timestamp": f"2026-01-01T{index // 60:02d}:{index % 60:02d}:00Z",
                "input": predictor,
                "response": 3.0 + 2.0 * delayed,
            }
        )
    models = train_expected_behavior_models(
        rows=rows,
        relationship_memory={
            "input-response": {
                "source_signal": "input",
                "target_signal": "response",
                "status": "active",
                "operating_modes_observed": ["running"],
                "current_strength": 0.95,
            }
        },
        operating_mode="running",
        timestamp_column="timestamp",
        source_run_id="lag-run",
        training_time="2026-01-01T01:19:00Z",
    )
    model = next(
        item for item in models.values() if item["target_signal"] == "response"
    )
    assert model["model_version"] == "v2"
    assert model["model_parameters"]["lag_samples"] == 2
    assert model["model_parameters"]["lag_seconds"] == 120.0
    assert model["model_parameters"]["slope"] == 2.0
    assert model["validation"]["validation_sample_count"] >= 5
    assert model["validation"]["passed"] is True


def test_physics_prior_configures_delay_variability_and_mode_sensitivity() -> None:
    prior = {
        "id": "configured_response",
        "name": "Configured response",
        "description": "A test-only configured response.",
        "domain": "generic",
        "equipment_types": [],
        "required_signals": [],
        "required_relationships": [],
        "required_operating_modes": ["running"],
        "prerequisites": [],
        "expected_behavior": {
            "source": "measurements",
            "path": "state",
            "operator": "eq",
            "value": "responding",
        },
        "response_delay": {
            "source": "measurements",
            "path": "delay_seconds",
            "minimum_seconds": 30,
            "maximum_seconds": 120,
        },
        "allowable_physical_variability": {
            "source": "measurements",
            "path": "response",
            "expected": 10.0,
            "absolute_tolerance": 1.0,
        },
        "operating_mode_sensitivity": {
            "running": {
                "response_delay": {
                    "source": "measurements",
                    "path": "delay_seconds",
                    "minimum_seconds": 60,
                    "maximum_seconds": 90,
                }
            }
        },
        "validity_conditions": [],
        "confidence_modifier": "unchanged",
        "limitations": [],
        "reasoning_template": "{prior_name}: {status}",
    }
    result = evaluate_physics_reasoning(
        priors=[prior],
        analytical_evidence={
            "operating_modes": {
                "baseline_mode": "running",
                "recent_mode": "running",
                "match": "strong",
            },
            "measurements": {
                "state": "responding",
                "delay_seconds": 75.0,
                "response": 10.5,
            },
        },
    )
    evaluated = result["evaluated_priors"][0]
    assert evaluated["status"] == "supported"
    response_trace = evaluated["reasoning_trace"]["response_characteristics"]
    assert response_trace["operating_mode_override_applied"] is True
    assert [item["group"] for item in response_trace["groups_evaluated"]] == [
        "expectation",
        "response_delay",
        "allowable_physical_variability",
    ]
    assert evaluated["statistical_evidence_overridden"] is False


def test_propagation_reports_lag_consistency_and_independent_simultaneity() -> None:
    def relationship(identifier: str, source: str, target: str) -> dict:
        return {
            "relationship_id": identifier,
            "source_signal": source,
            "target_signal": target,
            "directionality_status": "lag_supported_source_to_target",
            "operating_modes_observed": ["running"],
            "current_strength": 0.9,
            "stability": "stable",
            "configured_lag_seconds": 60,
            "configured_response_window_seconds": [50, 70],
            "status": "active",
            "lag_history": [],
        }

    result = analyze_propagation(
        graph_comparison={
            "changed_edges": [
                {"relationship_id": "ab", "source_signal": "a", "target_signal": "b"},
                {"relationship_id": "bc", "source_signal": "b", "target_signal": "c"},
            ]
        },
        relationship_memory={
            "ab": relationship("ab", "a", "b"),
            "bc": relationship("bc", "b", "c"),
        },
        signal_drift={
            "column_drift": [
                {"column": item, "direction": "up"}
                for item in ("a", "c", "x", "y")
            ]
        },
        expected_behavior={"residual_evidence": []},
        operating_mode={"recent_mode": "running"},
        sensor_health={
            "signals": [
                {"signal": item, "health": "healthy"}
                for item in ("a", "b", "c", "x", "y")
            ]
        },
        data_quality={"readiness": "ready"},
        multiscale_analysis={
            "status": "complete",
            "cross_scale_classification": "agreement",
        },
        signal_change_times={
            "a": "2026-01-01T00:00:00Z",
            "b": "2026-01-01T00:01:00Z",
            "c": "2026-01-01T00:02:00Z",
            "x": "2026-01-01T00:03:00Z",
            "y": "2026-01-01T00:03:03Z",
        },
    )
    path = next(
        item for item in result["candidate_paths"] if item["nodes"] == ["a", "b", "c"]
    )
    assert path["lag_consistency"]["end_to_end_fit_score"] == 1.0
    assert result["primary_behavioral_change_candidates"][0]["signal"] == "a"
    assert any(
        item["signal"] == "c"
        for item in result["downstream_behavioral_responses"]
    )
    assert result["independent_simultaneous_changes"][0]["signals"] == ["x", "y"]
    assert result["uncertainty"]["cause_selected"] is False


def test_temporal_characterization_reports_recovery_and_stabilization_inputs() -> None:
    rows = [
        {
            "timestamp": f"2026-01-01T00:{index:02d}:00Z",
            "signal": 10.0 / (index + 1),
        }
        for index in range(12)
    ]
    result = evaluate_behavioral_evolution(
        active_model={
            "model_version": "v1",
            "signal_memory": {
                "signal": {
                    "historical_center": 0.0,
                    "historical_scale": 1.0,
                    "drift_history": [],
                    "historical_residual_behavior": [],
                }
            },
            "relationship_memory": {},
            "operating_mode_memory": {"running": {}},
            "model_confidence_history": [],
        },
        snapshots=[],
        rows=rows,
        numeric_columns=["signal"],
        relationship_graph_comparison={"changed_edges": []},
        operating_mode={"recent_mode": "running"},
        expected_behavior={"residual_evidence": []},
        learning_decision={"decision": "blocked_by_instability"},
        timestamp_column="timestamp",
    )
    temporal = result["temporal_characterization"]
    signal = temporal["signals"][0]
    assert temporal["time_basis"] == "elapsed_seconds"
    assert signal["velocity"]["value"] < 0.0
    assert signal["trajectory"]["classification"] == "recovery_trajectory"
    assert signal["trajectory"]["rank_concordance"] < 0.0
    assert signal["stabilization"]["method"] == (
        "robust_recent_vs_early_derivative_contraction"
    )


def test_multiscale_profile_math_distinguishes_transient_gradual_and_recurring() -> None:
    def scale(name: str, values: dict[str, tuple[str, float]]) -> dict:
        return {
            "name": name,
            "signal_metrics": [
                {
                    "column": column,
                    "active": True,
                    "direction": direction,
                    "normalized_change": magnitude,
                }
                for column, (direction, magnitude) in values.items()
            ],
        }

    patterns = _scale_behavior_patterns(
        [
            scale(
                "short",
                {
                    "transient": ("up", 5.0),
                    "gradual": ("up", 1.0),
                    "recurring": ("up", 2.0),
                },
            ),
            scale(
                "medium",
                {
                    "transient": ("up", 3.0),
                    "gradual": ("up", 3.0),
                    "recurring": ("down", 2.0),
                },
            ),
            scale(
                "long",
                {
                    "transient": ("up", 1.0),
                    "gradual": ("up", 5.0),
                    "recurring": ("up", 2.0),
                },
            ),
        ],
        elapsed_time=True,
    )
    by_signal = {item["column"]: item for item in patterns["signals"]}
    assert by_signal["transient"]["classification"] == "transient_event"
    assert by_signal["gradual"]["classification"] == "gradual_evolution"
    assert (
        by_signal["recurring"]["classification"]
        == "recurring_or_oscillatory_scale_pattern"
    )


def test_uncertainty_components_remain_individually_traceable() -> None:
    result = uncertainty_section(
        data_quality={
            "readiness": "ready",
            "warnings": [],
            "data_confidence": {"rating": "high"},
        },
        sensor_health={
            "signals": [{"signal": "a", "health": "healthy"}]
        },
        temporal_analysis={"uncertainty_summary": {"coverage": 0.9}},
        module_failures=[],
        relationship_analysis={"status": "complete"},
        relationship_graph={
            "edges": [
                {
                    "source_signal": "a",
                    "target_signal": "b",
                    "baseline_sample_count": 30,
                    "current_sample_count": 20,
                    "directionality_status": "association_only_direction_not_established",
                }
            ]
        },
        operating_modes={
            "baseline_mode": "running",
            "recent_mode": "running",
            "match": "strong",
        },
        expected_behavior={"status": "complete", "models_evaluated": 1, "expected_values": []},
        covariance_analysis={"status": "complete"},
        multiscale_analysis={
            "status": "complete",
            "cross_scale_interpretation": {
                "classification": "stable_across_scales"
            },
        },
        propagation_analysis={
            "status": "limited",
            "reason": "no_fully_supported_candidate_propagation_path",
            "candidate_paths": [],
            "competing_paths": [],
            "unsupported_segments": [],
            "limitations": [],
        },
    )
    assert list(result["components"]) == [
        "data_uncertainty",
        "model_uncertainty",
        "relationship_uncertainty",
        "operating_context_uncertainty",
        "propagation_uncertainty",
    ]
    assert result["data_uncertainty"]["status"] == "complete"
    assert result["relationship_uncertainty"]["status"] == "limited"
    assert result["propagation_uncertainty"]["status"] == "limited"
    assert all(
        component["not_probability"]
        for component in result["components"].values()
    )
    assert result["processing_trace"]["component_weighting_performed"] is False


def test_stable_baseline_evolution_requires_repeated_confirmation() -> None:
    common = {
        "active_model": {
            "baseline_versions": ["baseline-v1"],
            "learning_decisions": [],
        },
        "rows_count": 80,
        "numeric_columns": ["a"],
        "operating_mode": {
            "baseline_mode": "running",
            "recent_mode": "running",
            "match": "strong",
        },
        "data_quality": {
            "readiness": "ready",
            "data_confidence": {"rating": "high"},
        },
        "sensor_health": {
            "signals": [{"signal": "a", "health": "healthy"}]
        },
        "temporal_analysis": {
            "instability_index": {"score": 0.05},
            "decision_thresholding": {"state": "Normal"},
        },
        "multiscale_analysis": {
            "status": "complete",
            "cross_scale_interpretation": {
                "classification": "sustained_across_elapsed_scales"
            },
            "behavior_patterns": {
                "signals": [
                    {"column": "a", "classification": "gradual_evolution"}
                ]
            },
            "scales_used": ["short", "medium", "long"],
        },
        "physics_reasoning": {
            "contradictory_priors": [],
            "supporting_priors": [],
        },
        "expected_behavior": {
            "status": "complete",
            "models_evaluated": 1,
            "residual_evidence": [],
        },
        "graph_comparison": {"status": "complete", "changed_edges": []},
        "active_observations": [],
        "effective_time": "2026-01-01T00:00:00Z",
        "model_version": "v1",
    }
    first = evaluate_baseline_evolution(
        **common,
        source_run_id="stable-evolution-1",
    )
    assert first["decision"] == "deferred"
    assert (
        first["baseline_evolution_assessment"]["classification"]
        == "stable_evolution_candidate"
    )
    second = evaluate_baseline_evolution(
        **common,
        source_run_id="stable-evolution-2",
        prior_learning_decisions=[first],
    )
    assert second["decision"] == "accepted"
    assert second["learning_allowed"] is True
    assert second["processing_trace"]["active_instability_learned"] is False
