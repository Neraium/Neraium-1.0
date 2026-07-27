from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import app.engine.sii_engine as sii_engine_module
from app.engine.sii.adaptive_persistence import evaluate_adaptive_persistence
from app.engine.sii.empirical_thresholds import estimate_empirical_thresholds
from app.engine.sii.mode_conditioned_baseline import analyze_mode_conditioned_baseline
from app.engine.sii.multiscale_analysis import analyze_multiscale
from app.engine.sii.relationship_graph import analyze_relationship_graph
from app.engine.sii_engine import evaluate_sii


def _edge(
    left: str,
    right: str,
    baseline: float,
    current: float,
    change_type: str,
) -> dict[str, object]:
    return {
        "id": f"relationship:{left}:{right}",
        "source": f"metric:{left}",
        "target": f"metric:{right}",
        "change_type": change_type,
        "baseline_correlation": baseline,
        "recent_correlation": current,
        "confidence": 1.0,
        "baseline_sample_count": 24,
        "current_sample_count": 12,
        "relationship_context": {"operator_primary_eligible": True},
        "time_window": {"baseline_end": "2026-01-01", "current_end": "2026-01-02"},
        "supporting_metric_pairs": [
            {
                "left": left,
                "right": right,
                "baseline_sample_size": 24,
                "recent_sample_size": 12,
            }
        ],
    }


def test_graph_wide_change_metrics_are_exact_and_non_causal() -> None:
    edges = [
        _edge("flow", "pressure", 0.90, 0.20, "missing"),
        _edge("pressure", "power", 0.85, 0.10, "missing"),
        _edge("flow", "power", 0.80, 0.82, "stable"),
    ]
    result = analyze_relationship_graph(
        relationship_model={"relationship_graph": {"edges": edges}},
        telemetry_signal_catalog={
            name: {"subsystem": "primary_loop"} for name in ("flow", "pressure", "power")
        },
        sensor_health={
            "signals": [
                {"signal": name, "health": "healthy", "conditions": []}
                for name in ("flow", "pressure", "power")
            ]
        },
        data_quality={"data_confidence": {"rating": "high"}},
    )

    assert result["status"] == "complete"
    assert result["changed_edge_fraction"] == pytest.approx(2 / 3, abs=1e-6)
    assert result["weighted_edge_displacement"] == pytest.approx(0.49, abs=1e-6)
    assert result["component_count"] == 1
    component = result["connected_changed_components"][0]
    assert component["node_count"] == 3
    assert component["edge_count"] == 2
    assert component["coherent"] is True
    assert component["systems_involved"] == ["primary_loop"]
    scores = {item["node"]: item["node_disruption_score"] for item in result["node_disruption_scores"]}
    assert scores == pytest.approx({"flow": 0.70, "pressure": 0.725, "power": 0.75})
    assert result["subsystem_concentration"]["classification"] == "concentrated"
    assert result["subsystem_concentration"]["concentration"] == 1.0
    assert "non-causal" in result["assumptions"][0].lower()


def test_graph_change_is_suppressed_by_signal_health_and_quality_floors() -> None:
    result = analyze_relationship_graph(
        relationship_model={
            "relationship_graph": {
                "edges": [_edge("flow", "pressure", 0.95, 0.10, "missing")]
            }
        },
        sensor_health={
            "signals": [
                {
                    "signal": "flow",
                    "health": "suspect",
                    "conditions": [{"type": "flatline_or_stuck"}],
                },
                {"signal": "pressure", "health": "healthy", "conditions": []},
            ]
        },
        data_quality={"data_confidence": {"rating": "high"}},
    )

    assert result["status"] == "complete"
    assert result["changed_edge_fraction"] == 0.0
    edge = result["eligible_edges"][0]
    assert edge["edge_confidence"] == 0.25
    assert edge["data_quality_factor"] == 0.25
    assert edge["promoted_changed_edge"] is False


def test_mode_conditioning_selects_only_prior_rows_matching_recent_mode() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(100):
        stage = "A" if index < 40 else "B"
        within_mode = index if stage == "A" else index - 40
        rows.append(
            {
                "timestamp": (start + timedelta(minutes=index)).isoformat(),
                "stage": stage,
                "flow": float(within_mode),
                "pressure": float(2 * within_mode + 5),
            }
        )
    source_edge = _edge("flow", "pressure", 1.0, 1.0, "stable")
    result = analyze_mode_conditioned_baseline(
        rows=rows,
        numeric_columns=["flow", "pressure"],
        timestamp_column="timestamp",
        relationship_model={"relationship_graph": {"edges": [source_edge]}},
    )

    assert result["status"] == "complete"
    assert result["used_global_fallback"] is False
    assert result["target_features"] == {"equipment_state": "b"}
    selection = result["selection"]
    assert selection["selected_historical_indices"] == list(range(40, 70))
    assert selection["selected_baseline_rows"] == 30
    assert selection["recent_rows"] == 30
    edge = result["mode_relationships"]["edges"][0]
    assert edge["baseline_sample_count"] == 30
    assert edge["current_sample_count"] == 30
    assert edge["baseline_correlation"] == pytest.approx(1.0)
    assert edge["current_correlation"] == pytest.approx(1.0)
    assert edge["comparison"] == "like_for_like_operating_mode"


def test_adaptive_persistence_uses_exact_elapsed_support() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "temperature": 10.0 if index < 36 else 12.0,
        }
        for index in range(48)
    ]
    baseline = {
        "recent_window_rows": 12,
        "column_drift": [
            {
                "column": "temperature",
                "baseline_average": 10.0,
                "direction": "up",
                "drift_flag": "review",
            }
        ],
    }
    result = evaluate_adaptive_persistence(
        rows=rows,
        timestamp_column="timestamp",
        baseline_analysis=baseline,
        fixed_persistence={"persistent_columns": ["temperature"]},
    )

    assert result["status"] == "complete"
    assert result["elapsed_time_available"] is True
    assert result["observed_duration_seconds"] == 720.0
    detail = result["details"][0]
    assert detail["supporting_duration_seconds"] == 720.0
    assert detail["longest_continuous_support_seconds"] == 720.0
    assert detail["support_fraction"] == 1.0
    assert detail["persistent"] is True


def test_adaptive_persistence_uses_actual_irregular_intervals() -> None:
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(20):
        rows.append({"timestamp": current.isoformat(), "temperature": 12.0})
        current += timedelta(minutes=1 if index % 2 == 0 else 2)
    result = evaluate_adaptive_persistence(
        rows=rows,
        timestamp_column="timestamp",
        baseline_analysis={
            "recent_window_rows": 13,
            "column_drift": [
                {
                    "column": "temperature",
                    "baseline_average": 10.0,
                    "direction": "up",
                    "drift_flag": "review",
                }
            ],
        },
    )

    assert result["status"] == "complete"
    assert result["sampling_regular"] is False
    assert result["observed_duration_seconds"] == 1170.0
    assert result["details"][0]["supporting_duration_seconds"] == 1170.0
    assert "actual elapsed intervals" in result["limitations"][0]


def test_adaptive_persistence_falls_back_explicitly_without_timestamps() -> None:
    result = evaluate_adaptive_persistence(
        rows=[{"temperature": 10.0 + index} for index in range(8)],
        timestamp_column=None,
        baseline_analysis={"recent_window_rows": 4, "column_drift": []},
        fixed_persistence={"status": "persistent", "persistent_columns": ["temperature"]},
    )

    assert result["status"] == "limited"
    assert result["used_row_fallback"] is True
    assert result["reason"] == "timestamp_evidence_not_reliable_for_elapsed_persistence"
    assert result["persistent_columns"] == ["temperature"]


def test_multiscale_windows_have_exact_counts_and_sustained_agreement() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "temperature": 10.0 if index < 120 else 20.0,
        }
        for index in range(180)
    ]
    result = analyze_multiscale(
        rows=rows,
        numeric_columns=["temperature"],
        timestamp_column="timestamp",
        config={
            "scales": [
                {"name": "15m", "seconds": 900},
                {"name": "30m", "seconds": 1800},
                {"name": "60m", "seconds": 3600},
                {"name": "24h", "seconds": 86400},
            ]
        },
    )

    assert result["status"] == "complete"
    scales = {item["name"]: item for item in result["scales"] if item["status"] == "complete"}
    unsupported = next(item for item in result["scales"] if item["name"] == "24h")
    assert unsupported["status"] == "limited"
    assert unsupported["reason"] == "insufficient_pre_window_baseline_rows"
    assert {name: item["active_rows"] for name, item in scales.items()} == {
        "15m": 15,
        "30m": 30,
        "60m": 60,
    }
    assert {name: item["actual_active_span_seconds"] for name, item in scales.items()} == {
        "15m": 840.0,
        "30m": 1740.0,
        "60m": 3540.0,
    }
    assert all(item["baseline_end_index"] < item["active_start_index"] for item in scales.values())
    assert result["agreement"]["sustained_change_observed"] is True
    signal = result["agreement"]["agreeing_signals"][0]
    assert signal["column"] == "temperature"
    assert signal["active_scale_count"] == 3
    assert signal["agreement_fraction"] == 1.0


def test_empirical_thresholds_fit_baseline_only_and_preserve_fixed_fallback() -> None:
    rows = [
        {
            "x": float(index) + (0.1 if index % 2 else -0.1),
            "y": float(index) * 2.0 + (0.2 if index % 3 else -0.2),
        }
        for index in range(80)
    ]
    learned = estimate_empirical_thresholds(rows=rows, numeric_columns=["x", "y"])
    assert learned["status"] == "complete"
    assert learned["fit_window"] == {
        "start_index": 0,
        "end_index_exclusive": 56,
        "rows": 56,
        "active_rows_excluded": 24,
    }
    assert learned["signal_thresholds"]["x"]["status"] == "learned"
    assert learned["relationship_change"]["status"] == "learned"
    assert learned["relationship_change"]["threshold"] >= 0.25

    changed_active = [dict(row) for row in rows]
    for row in changed_active[56:]:
        row["x"] += 1_000_000.0
        row["y"] -= 1_000_000.0
    refit = estimate_empirical_thresholds(rows=changed_active, numeric_columns=["x", "y"])
    assert refit["signal_thresholds"] == learned["signal_thresholds"]
    assert refit["relationship_change"] == learned["relationship_change"]

    fallback = estimate_empirical_thresholds(rows=rows[:30], numeric_columns=["x", "y"])
    assert fallback["status"] == "limited"
    assert fallback["relationship_change"] == {
        "status": "fallback",
        "threshold": 0.25,
        "fixed_floor": 0.25,
        "fallback_reason": "insufficient_baseline_rows",
        "delta_sample_count": 0,
        "maximum_pair_window_count": 1,
        "columns_used": ["x", "y"],
    }


def test_phase_2_modules_are_orchestrated_once_without_replacing_compatibility() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    columns = ["timestamp", "stage", "flow", "pressure"]
    rows = []
    for index in range(180):
        stage = "A" if index < 60 else "B"
        flow = float(index % 31)
        pressure = 2.0 * flow + 5.0
        rows.append(
            {
                "timestamp": (start + timedelta(minutes=index)).isoformat(),
                "stage": stage,
                "flow": flow,
                "pressure": pressure,
            }
        )
    profiles = [
        {"column": column, "constant_or_stuck": False, "missing_count": 0, "non_numeric_count": 0}
        for column in ("flow", "pressure")
    ]
    result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=profiles,
        timestamp_column="timestamp",
        config={"numeric_columns": ["flow", "pressure"]},
    )

    trace = result["processing_trace"]
    for module in (
        "empirical_thresholds",
        "mode_conditioned_baseline",
        "relationship_graph_analysis",
        "adaptive_persistence",
        "multiscale_analysis",
    ):
        assert trace["modules_attempted"].count(module) == 1
    assert result["relationship_graph"]["method"] == "deterministic_dynamic_relationship_graph_v1"
    assert result["operating_modes"]["mode_conditioned_baseline"]["used_global_fallback"] is False
    assert result["persistence_analysis"]["adaptive_persistence"]["elapsed_time_available"] is True
    assert result["multiscale_analysis"]["status"] == "complete"
    assert trace["scales_used"] == result["multiscale_analysis"]["scales_used"]
    compatibility = result["compatibility"]
    assert "mode_conditioned_baseline" not in compatibility["relationship_model"]
    assert compatibility["relationship_model"]["relationship_graph"]["edges"]


def test_phase_2_optional_failure_is_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    columns = ["timestamp", "flow", "pressure"]
    rows = [
        {
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "flow": float(index % 17),
            "pressure": float((index % 17) * 2 + 1),
        }
        for index in range(120)
    ]

    def fail_multiscale(**_kwargs: object) -> dict[str, object]:
        raise RuntimeError("synthetic phase 2 failure")

    monkeypatch.setattr(sii_engine_module, "analyze_multiscale", fail_multiscale)
    result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=[
            {"column": column, "constant_or_stuck": False, "missing_count": 0, "non_numeric_count": 0}
            for column in ("flow", "pressure")
        ],
        timestamp_column="timestamp",
        config={"numeric_columns": ["flow", "pressure"]},
    )

    assert result["status"] == "limited"
    assert result["multiscale_analysis"]["status"] == "failed"
    assert result["relationship_graph"]["status"] == "complete"
    assert result["processing_trace"]["modules_failed"] == ["multiscale_analysis"]
    assert result["uncertainty"]["module_failures"] == [
        {
            "module": "multiscale_analysis",
            "reason": "RuntimeError: synthetic phase 2 failure",
        }
    ]
