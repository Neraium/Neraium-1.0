from __future__ import annotations

import math

from app.engine.sii.bayesian_evidence import DEFERRED_REASON, BayesianEvidenceRegistry, evaluate_bayesian_evidence
from app.engine.sii.dynamical_stability import analyze_dynamical_stability
from app.engine.sii.network_stability import analyze_network_stability
from app.engine.sii.spectral_analysis import analyze_spectral_behavior


def test_bayesian_posterior_remains_null_without_validated_calibration() -> None:
    result = evaluate_bayesian_evidence()
    assert result["status"] == "deferred"
    assert result["active"] is False
    assert result["reason"] == DEFERRED_REASON
    assert result["posterior"] is None
    assert result["safeguards"]["heuristic_confidence_converted_to_probability"] is False


def test_even_complete_configuration_cannot_bypass_unimplemented_posterior_engine() -> None:
    registry = BayesianEvidenceRegistry()
    registry.register_evidence_likelihood(
        "residual",
        versioned_parameters={"version": "v1"},
        calibration_dataset_references=["dataset-1"],
        calibration_metrics={"metric": 1.0},
        reliability_metrics={"reliability": 1.0},
        validation_metrics={"validation": 1.0},
        acceptance_criteria={"approved": True},
    )
    registry.register_posterior_updater("future", lambda *_args, **_kwargs: 0.9)
    result = evaluate_bayesian_evidence(
        {
            "enabled": True,
            "validated_likelihood_models": {"residual": "v1"},
            "calibration_dataset_identifiers": ["dataset-1"],
            "calibration_metrics": {"metric": 1.0},
            "reliability_analysis": {"passed": True},
            "versioned_model_parameters": {"version": "v1"},
            "acceptance_test_approval": {"approved": True},
        },
        registry=registry,
    )
    assert all(result["requirements"].values())
    assert result["reason"] == "posterior_update_engine_not_implemented"
    assert result["posterior"] is None
    assert result["active"] is False


def test_advanced_modules_return_limited_when_assumptions_fail() -> None:
    rows = [{"timestamp": f"2026-01-01T00:0{index}:00Z", "value": index} for index in range(5)]
    spectral = analyze_spectral_behavior(rows=rows, numeric_columns=["value"], timestamp_column="timestamp")
    dynamics = analyze_dynamical_stability(rows=rows, numeric_columns=["value"], timestamp_column="timestamp")
    network = analyze_network_stability(current_graph={"edges": []}, active_graph=None, graph_comparison={})
    assert spectral["status"] == "limited"
    assert dynamics["status"] == "limited"
    assert network["status"] == "limited"
    assert network["processing_trace"]["network_risk_score_generated"] is False
    assert dynamics["processing_trace"]["formal_stability_theory_claimed"] is False


def test_spectral_analysis_runs_with_regular_sampling_and_nyquist_safeguards() -> None:
    rows = []
    for index in range(128):
        rows.append(
            {
                "timestamp": f"2026-01-01T{index // 60:02d}:{index % 60:02d}:00Z",
                "value": math.sin(2.0 * math.pi * index / 16.0),
            }
        )
    result = analyze_spectral_behavior(rows=rows, numeric_columns=["value"], timestamp_column="timestamp")
    assert result["status"] == "complete"
    signal = result["dominant_frequencies"][0]
    assert abs(signal["dominant_period_seconds"] - 960.0) < 1.0
    assert signal["nyquist_frequency_hz"] > signal["dominant_frequency_hz"]
    assert result["processing_trace"]["aliasing_safeguard_applied"] is True
