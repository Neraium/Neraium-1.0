import math

import numpy as np

from app.services.sii_runner import BackendSiiRunner, build_instability_index


def test_backend_sii_runner_single_vector_preserves_public_shape() -> None:
    runner = BackendSiiRunner()

    state = runner.ingest(
        sensor_vector=np.array([1.0, 2.0, 3.0]),
        timestamp=1.0,
        asset_id="asset-1",
        run_id="run-1",
    )

    assert set(state) == {
        "asset_id",
        "run_id",
        "timestamp",
        "regime",
        "urgency",
        "instability_score",
        "instability_components",
        "structural_drift",
        "transition_pressure",
        "confidence",
        "instability_history",
        "velocity_history",
        "regime_history",
    }
    assert "mahalanobis_distance" in state["instability_components"]
    assert "drift_velocity" in state["instability_components"]
    assert "drift_acceleration" in state["instability_components"]


def test_backend_sii_runner_handles_singular_covariance() -> None:
    runner = BackendSiiRunner(baseline_window=4, recent_window=4)
    state = {}
    for index in range(4):
        state = runner.ingest(
            sensor_vector=np.array([5.0, 5.0, 5.0]),
            timestamp=float(index),
            asset_id="asset-1",
            run_id="run-1",
        )

    assert state
    assert math.isfinite(state["instability_score"])
    assert math.isfinite(state["instability_components"]["mahalanobis_distance"])
    assert isinstance(state["instability_components"]["persistence_condition"], bool)
    assert isinstance(state["instability_components"]["accumulation_condition"], bool)


def test_backend_sii_runner_handles_missing_and_nan_values() -> None:
    runner = BackendSiiRunner(baseline_window=3, recent_window=3)
    state = {}
    vectors = [
        np.array([1.0, np.nan, 3.0]),
        np.array([np.nan, 2.0, 3.5]),
        np.array([1.5, 2.5, np.nan]),
        np.array([2.0, 3.0, 4.0]),
    ]

    for index, vector in enumerate(vectors):
        state = runner.ingest(
            sensor_vector=vector,
            timestamp=float(index),
            asset_id="asset-1",
            run_id="run-1",
        )

    assert state
    assert math.isfinite(state["instability_score"])
    assert math.isfinite(state["structural_drift"])
    assert math.isfinite(state["transition_pressure"])
    assert isinstance(state["instability_components"]["persistence_condition"], bool)
    assert isinstance(state["instability_components"]["accumulation_condition"], bool)


def test_backend_sii_runner_exposes_v2_metrics_and_legacy_metrics() -> None:
    runner = BackendSiiRunner(baseline_window=3, recent_window=3)
    state = {}
    vectors = [
        np.array([10.0, 10.0, 10.0]),
        np.array([10.0, 10.0, 10.0]),
        np.array([12.0, 13.0, 11.0]),
        np.array([14.0, 16.0, 13.0]),
    ]

    for index, vector in enumerate(vectors):
        state = runner.ingest(
            sensor_vector=vector,
            timestamp=float(index),
            asset_id="asset-2",
            run_id="run-2",
        )

    components = state["instability_components"]
    assert "drift" in components
    assert "relationship_degradation" in components
    assert "entropy_growth" in components
    assert "fallback_score" in components
    assert "mahalanobis_distance" in components
    assert "drift_velocity" in components
    assert "drift_acceleration" in components
    assert "covariance_shift" in components
    assert "trajectory_curvature" in components
    assert "fallback_transition_pressure" in components
    assert "fallback_variability_pressure" in components


def test_build_instability_index_supports_legacy_and_v2_components() -> None:
    legacy_index = build_instability_index(
        {
            "structural_drift": 0.3,
            "transition_pressure": 0.4,
            "confidence": 0.8,
            "instability_components": {
                "drift": 0.3,
                "relationship_degradation": 0.4,
                "entropy_growth": 0.2,
            },
        }
    )
    technical_index = build_instability_index(
        {
            "structural_drift": 0.1,
            "transition_pressure": 0.6,
            "confidence": 0.7,
            "instability_components": {
                "structural_drift_score": 0.8,
                "covariance_shift": 0.5,
                "trajectory_curvature": 0.25,
                "relationship_degradation": 0.2,
            },
        }
    )

    assert legacy_index["score"] > 0.0
    assert legacy_index["components"]["drift"] == 0.3
    assert legacy_index["components"]["relationship_degradation"] == 0.4
    assert technical_index["score"] > 0.0
    assert technical_index["components"]["drift"] == 0.8
    assert technical_index["components"]["relationship_degradation"] == 0.6
    assert technical_index["components"]["entropy_growth"] == 0.5
    assert technical_index["components"]["topology_propagation"] == 0.425


def test_sii_runner_masks_normalization_sentinel_values():
    from app.services.sii_runner import build_sensor_vectors
    from app.services.telemetry_normalization import SENTINEL

    result = build_sensor_vectors(
        ["timestamp", "flow", "pressure"],
        [
            ["2026-01-01T00:00:00Z", "100", "20"],
            ["2026-01-01T00:01:00Z", str(SENTINEL), "21"],
        ],
        [
            {"column": "flow"},
            {"column": "pressure"},
        ],
    )

    assert len(result["vectors"]) == 2
    assert result["vectors"][1][0] != SENTINEL
    assert result["vectors"][1][0] != result["vectors"][1][0]
    assert result["vectors"][1][1] == 21.0


def test_run_sii_runner_samples_large_vector_sets_while_preserving_recent_tail(monkeypatch) -> None:
    from app.services import sii_runner

    monkeypatch.setattr(sii_runner, "MAX_RUNNER_VECTOR_ROWS", 32)
    monkeypatch.setattr(sii_runner, "RECENT_VECTOR_TAIL", 12)

    columns = ["timestamp", "temp", "pressure"]
    rows = [
        [f"2026-05-01T00:{index:02d}:00Z", f"{70.0 + index * 0.1:.3f}", f"{1.0 + index * 0.01:.3f}"]
        for index in range(200)
    ]
    result = sii_runner.run_sii_runner(
        columns=columns,
        rows=rows,
        numeric_profiles=[{"column": "temp"}, {"column": "pressure"}],
        timestamp_column="timestamp",
        primary_room="Loop A",
        driver_attribution={},
        engine_result={},
        processing_trace={},
    )

    assert result["runner_used"] is True
    assert result["sampling_applied"] is True
    assert result["sensor_vector_source_count"] == 200
    assert result["sensor_vector_count"] <= 32
    assert result["rows_processed"] <= 32
    assert result["processing_trace"]["sii_vector_rows_source_count"] == 200
    assert result["processing_trace"]["sii_sampling_applied"] is True
    assert result["latest_state"]["timestamp"] > 0
