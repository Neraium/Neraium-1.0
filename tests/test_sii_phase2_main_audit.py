from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.engine.sii.adaptive_persistence import evaluate_adaptive_persistence
from app.engine.sii.mode_conditioned_baseline import analyze_mode_conditioned_baseline
from app.engine.sii.multiscale_analysis import analyze_multiscale
from app.engine.sii.relationship_graph import analyze_relationship_graph
from app.engine.sii_engine import evaluate_sii
from app.services.upload_evidence import build_evidence_record_from_result


def _profiles(*columns: str) -> list[dict[str, object]]:
    return [
        {
            "column": column,
            "constant_or_stuck": False,
            "missing_count": 0,
            "non_numeric_count": 0,
        }
        for column in columns
    ]


def _edge(
    left: str,
    right: str,
    *,
    baseline: float = 0.9,
    current: float = 0.1,
    change_type: str = "missing",
    confidence: float = 1.0,
    primary: bool = True,
) -> dict[str, object]:
    return {
        "id": f"relationship:{left}:{right}",
        "source": f"metric:{left}",
        "target": f"metric:{right}",
        "relationship": f"{left} <-> {right}",
        "change_type": change_type,
        "baseline_correlation": baseline,
        "recent_correlation": current,
        "confidence": confidence,
        "baseline_sample_count": 24,
        "current_sample_count": 12,
        "relationship_context": {
            "operator_primary_eligible": primary,
            "context_only": not primary,
        },
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


def _graph(edges: list[dict[str, object]], **kwargs: object) -> dict[str, object]:
    return analyze_relationship_graph(
        relationship_model={"relationship_graph": {"edges": edges}},
        data_quality={"data_confidence": {"rating": "high"}},
        **kwargs,
    )


def _mode_rows(
    *,
    recent_modes: list[str] | None = None,
    sparse_history: bool = False,
    drift_recent: bool = False,
) -> list[dict[str, object]]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    recent_modes = recent_modes or ["B"] * 30
    for index in range(100):
        if index < 35:
            stage = "A"
        elif index < 70:
            stage = "A" if sparse_history and index < 65 else "B"
        else:
            stage = recent_modes[index - 70]
        within_mode = index if stage == "A" else index - 35
        x = float(within_mode)
        y = float(2 * within_mode + 5)
        if drift_recent and index >= 70:
            y = float(((index - 70) % 5) - 2)
        rows.append(
            {
                "timestamp": (start + timedelta(minutes=index)).isoformat(),
                "stage": stage,
                "flow": x,
                "pressure": y,
            }
        )
    return rows


def _conditioned(rows: list[dict[str, object]]) -> dict[str, object]:
    return analyze_mode_conditioned_baseline(
        rows=rows,
        numeric_columns=["flow", "pressure"],
        timestamp_column="timestamp",
        relationship_model={"relationship_graph": {"edges": [_edge("flow", "pressure")]}},
    )


def _persistence_rows(values: list[float], *, irregular: bool = False) -> list[dict[str, object]]:
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, value in enumerate(values):
        rows.append({"timestamp": current.isoformat(), "temperature": value})
        current += timedelta(minutes=1 if not irregular or index % 2 == 0 else 2)
    return rows


def _persistence_baseline(recent_rows: int) -> dict[str, object]:
    return {
        "recent_window_rows": recent_rows,
        "column_drift": [
            {
                "column": "temperature",
                "baseline_average": 10.0,
                "direction": "up",
                "drift_flag": "review",
                "warnings": [],
            }
        ],
    }


# Dynamic graph numerical and safety audit.

def test_graph_stable_edges_have_zero_disruption() -> None:
    result = _graph([_edge("flow", "pressure", baseline=0.9, current=0.88, change_type="stable")])
    assert result["status"] == "complete"
    assert result["changed_edge_fraction"] == 0.0
    assert result["weighted_edge_displacement"] == pytest.approx(0.014)
    assert result["connected_changed_components"] == []
    assert result["node_disruption_scores"] == [
        {"node": "pressure", "node_id": "metric:pressure", "changed_incident_edges": 0, "node_disruption_score": 0.0},
        {"node": "flow", "node_id": "metric:flow", "changed_incident_edges": 0, "node_disruption_score": 0.0},
    ]


def test_graph_isolated_changed_edge_is_not_a_coherent_component() -> None:
    result = _graph([_edge("flow", "pressure")])
    assert result["changed_edge_fraction"] == 1.0
    assert len(result["changed_edges"]) == 1
    component = result["connected_changed_components"][0]
    assert component["edge_count"] == 1
    assert component["coherent"] is False
    assert set(component["edge_ids"]) == {"relationship:flow:pressure"}


def test_graph_three_connected_changes_form_one_component() -> None:
    edges = [
        _edge("flow", "pressure"),
        _edge("pressure", "power", baseline=0.85, current=0.1),
        _edge("power", "temperature", baseline=0.8, current=0.05),
    ]
    result = _graph(
        edges,
        telemetry_signal_catalog={
            column: {"subsystem": "primary_loop"}
            for column in ("flow", "pressure", "power", "temperature")
        },
    )
    assert result["component_count"] == 1
    component = result["connected_changed_components"][0]
    assert component["node_count"] == 4
    assert component["edge_count"] == 3
    assert component["systems_involved"] == ["primary_loop"]
    assert component["coherent"] is True


def test_graph_excludes_context_only_component_from_eligible_math() -> None:
    result = _graph([_edge("outdoor_temperature", "schedule", primary=False)])
    assert result["status"] == "limited"
    assert result["eligible_edges"] == []
    assert result["changed_edges"] == []
    assert result["changed_edge_fraction"] == 0.0


def test_graph_low_confidence_component_is_not_promoted() -> None:
    result = _graph([_edge("flow", "pressure", confidence=0.2)])
    assert result["status"] == "complete"
    assert result["eligible_edges"][0]["edge_confidence"] < result["thresholds"]["minimum_edge_confidence"]
    assert result["changed_edges"] == []


def test_graph_unhealthy_sensor_component_is_down_ranked_without_root_cause() -> None:
    result = _graph(
        [_edge("flow", "pressure")],
        sensor_health={
            "signals": [
                {"signal": "flow", "health": "suspect", "conditions": [{"type": "flatline_or_stuck"}]},
                {"signal": "pressure", "health": "healthy", "conditions": []},
            ]
        },
    )
    edge = result["eligible_edges"][0]
    assert edge["data_quality_factor"] == 0.25
    assert edge["promoted_changed_edge"] is False
    assert result["changed_edges"] == []
    assert "root" not in json.dumps(result).lower()
    assert "non-causal" in json.dumps(result["assumptions"]).lower()


# Exact mode-conditioned baseline audit.

def test_normal_mode_transition_uses_like_mode_rows_without_false_graph_change() -> None:
    conditioned = _conditioned(_mode_rows())
    assert conditioned["status"] == "complete"
    assert conditioned["used_global_fallback"] is False
    assert conditioned["selected_operating_mode"]["features"] == {"equipment_state": "b"}
    assert conditioned["selected_operating_mode"]["ambiguous"] is False
    edge = conditioned["mode_relationships"]["edges"][0]
    assert edge["change_type"] == "stable"
    graph = analyze_relationship_graph(
        relationship_model={"relationship_graph": {"edges": [_edge("flow", "pressure")]}},
        mode_conditioned_analysis=conditioned,
        data_quality={"data_confidence": {"rating": "high"}},
    )
    assert graph["edge_basis"] == "mode_conditioned_relationships"
    assert graph["changed_edges"] == []


def test_true_drift_within_same_mode_remains_detectable() -> None:
    conditioned = _conditioned(_mode_rows(drift_recent=True))
    assert conditioned["used_global_fallback"] is False
    edge = conditioned["mode_relationships"]["changed_edges"][0]
    assert edge["baseline_correlation"] == pytest.approx(1.0)
    assert edge["correlation_delta"] >= 0.25
    graph = analyze_relationship_graph(
        relationship_model={"relationship_graph": {"edges": [_edge("flow", "pressure")]}},
        mode_conditioned_analysis=conditioned,
        data_quality={"data_confidence": {"rating": "high"}},
    )
    assert graph["changed_edges"]


def test_sparse_mode_uses_explicit_global_fallback_with_reduced_confidence() -> None:
    conditioned = _conditioned(_mode_rows(sparse_history=True))
    assert conditioned["status"] == "limited"
    assert conditioned["used_global_fallback"] is True
    assert conditioned["fallback_reason"] == "insufficient_like_mode_historical_rows"
    assert conditioned["selection_confidence_level"] == "limited"
    assert conditioned["selection_confidence"] <= 0.35
    assert conditioned["selection"]["selected_baseline_rows"] == 5


def test_ambiguous_recent_mode_never_makes_confident_conditioned_claim() -> None:
    conditioned = _conditioned(_mode_rows(recent_modes=["B", "C"] * 15))
    assert conditioned["status"] == "limited"
    assert conditioned["used_global_fallback"] is True
    assert conditioned["fallback_reason"] == "ambiguous_recent_operating_mode"
    assert conditioned["selected_operating_mode"]["ambiguous"] is True
    assert conditioned["selected_operating_mode"]["minimum_feature_support"] == 0.5
    assert conditioned["selection_confidence_level"] == "limited"
    assert conditioned["mode_relationships"]["edges"] == []


# Elapsed-time adaptive persistence audit.

def test_adaptive_persistence_regular_timestamps_expose_required_and_actual_support() -> None:
    values = [10.0] * 36 + [12.0] * 12
    result = evaluate_adaptive_persistence(
        rows=_persistence_rows(values),
        timestamp_column="timestamp",
        baseline_analysis=_persistence_baseline(12),
    )
    detail = result["details"][0]
    assert result["persistence_basis"] == "elapsed_time"
    assert result["sampling_regular"] is True
    assert detail["required_observations"] >= 3
    assert detail["actual_persistence"]["supporting_observations"] == 12
    assert detail["actual_persistence"]["satisfied"] is True


def test_adaptive_persistence_irregular_timestamps_use_actual_intervals_and_raise_requirement() -> None:
    values = [10.0] * 7 + [12.0] * 13
    result = evaluate_adaptive_persistence(
        rows=_persistence_rows(values, irregular=True),
        timestamp_column="timestamp",
        baseline_analysis=_persistence_baseline(13),
    )
    detail = result["details"][0]
    assert result["sampling_regular"] is False
    assert result["observed_duration_seconds"] == 1170.0
    assert detail["requirement_adjustments"]["irregular_sampling"] >= 1
    assert detail["required_observations"] >= 4


def test_adaptive_persistence_without_timestamps_is_row_only_and_has_no_duration_fields() -> None:
    result = evaluate_adaptive_persistence(
        rows=[{"temperature": 12.0} for _ in range(8)],
        timestamp_column=None,
        baseline_analysis=_persistence_baseline(4),
        fixed_persistence={"status": "complete", "persistent_columns": ["temperature"]},
    )
    assert result["used_row_fallback"] is True
    assert result["persistence_basis"] == "row_count"
    assert "observed_duration_seconds" not in result
    assert "required_continuous_support_seconds" not in result
    assert result["details"] == []


def test_noisy_system_requires_more_observations_than_stable_system() -> None:
    values = [10.0] * 12
    stable = evaluate_adaptive_persistence(
        rows=_persistence_rows(values),
        timestamp_column="timestamp",
        baseline_analysis=_persistence_baseline(12),
        empirical_thresholds={"signal_thresholds": {"temperature": {"threshold": 0.05, "robust_sigma": 0.04, "fixed_floor": 0.05}}},
    )
    noisy = evaluate_adaptive_persistence(
        rows=_persistence_rows(values),
        timestamp_column="timestamp",
        baseline_analysis=_persistence_baseline(12),
        empirical_thresholds={"signal_thresholds": {"temperature": {"threshold": 0.4, "robust_sigma": 0.4, "fixed_floor": 0.05}}},
    )
    assert noisy["details"][0]["required_observations"] > stable["details"][0]["required_observations"]
    assert noisy["details"][0]["requirement_adjustments"]["volatility"] > 0


def test_isolated_spike_does_not_satisfy_persistence() -> None:
    values = [10.0] * 11 + [12.0]
    result = evaluate_adaptive_persistence(
        rows=_persistence_rows(values),
        timestamp_column="timestamp",
        baseline_analysis=_persistence_baseline(12),
    )
    detail = result["details"][0]
    assert detail["supporting_observations"] == 1
    assert detail["persistent"] is False


def test_sustained_small_change_satisfies_bounded_persistence() -> None:
    values = [10.2] * 12
    result = evaluate_adaptive_persistence(
        rows=_persistence_rows(values),
        timestamp_column="timestamp",
        baseline_analysis=_persistence_baseline(12),
    )
    detail = result["details"][0]
    assert detail["required_observation_bounds"] == {"minimum": 3, "maximum": 12}
    assert detail["persistent"] is True


def test_poor_quality_health_and_mode_never_reduce_persistence_requirement() -> None:
    values = [12.0] * 12
    healthy = evaluate_adaptive_persistence(
        rows=_persistence_rows(values),
        timestamp_column="timestamp",
        baseline_analysis=_persistence_baseline(12),
        data_quality={"readiness": "ready", "data_confidence": {"rating": "high"}},
        sensor_health={"signals": [{"signal": "temperature", "health": "healthy", "conditions": []}]},
        operating_mode={"match": "strong", "confidence": "high"},
    )
    unhealthy = evaluate_adaptive_persistence(
        rows=_persistence_rows(values),
        timestamp_column="timestamp",
        baseline_analysis=_persistence_baseline(12),
        data_quality={"readiness": "not_ready", "data_confidence": {"rating": "low"}},
        sensor_health={"signals": [{"signal": "temperature", "health": "suspect", "conditions": [{"type": "flatline_or_stuck"}]}]},
        operating_mode={"match": "weak", "confidence": "low"},
    )
    healthy_detail = healthy["details"][0]
    unhealthy_detail = unhealthy["details"][0]
    assert unhealthy_detail["required_observations"] >= healthy_detail["required_observations"]
    assert unhealthy_detail["requirement_adjustments"]["data_quality"] > 0
    assert unhealthy_detail["requirement_adjustments"]["sensor_health"] > 0
    assert unhealthy_detail["requirement_adjustments"]["operating_mode"] > 0


# Timestamp and row-fallback multiscale audit.

def _multiscale_rows(values: list[float], *, irregular: bool = False) -> list[dict[str, object]]:
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index, value in enumerate(values):
        rows.append({"timestamp": current.isoformat(), "temperature": value})
        current += timedelta(minutes=1 if not irregular or index % 2 == 0 else 2)
    return rows


def _time_scales() -> list[dict[str, object]]:
    return [
        {"name": "15m", "seconds": 15 * 60},
        {"name": "30m", "seconds": 30 * 60},
        {"name": "60m", "seconds": 60 * 60},
    ]


def test_short_transient_is_scale_specific_not_sustained() -> None:
    result = analyze_multiscale(
        rows=_multiscale_rows([10.0] * 172 + [20.0] * 8),
        numeric_columns=["temperature"],
        timestamp_column="timestamp",
        config={"scales": _time_scales()},
    )
    assert result["cross_scale_interpretation"]["classification"] == "transient_or_scale_specific"
    assert result["agreement"]["sustained_change_observed"] is False


def test_medium_duration_change_agrees_on_supported_medium_scales() -> None:
    result = analyze_multiscale(
        rows=_multiscale_rows([10.0] * 160 + [20.0] * 20),
        numeric_columns=["temperature"],
        timestamp_column="timestamp",
        config={"scales": _time_scales(), "agreement_fraction": 0.6},
    )
    assert result["cross_scale_interpretation"]["classification"] == "sustained_across_elapsed_scales"
    agreeing = result["agreement"]["agreeing_signals"][0]
    assert agreeing["direction"] == "up"
    assert agreeing["active_scale_count"] >= 2


def test_slow_long_term_change_agrees_across_elapsed_scales() -> None:
    result = analyze_multiscale(
        rows=_multiscale_rows([10.0] * 120 + [20.0] * 60),
        numeric_columns=["temperature"],
        timestamp_column="timestamp",
        config={"scales": _time_scales()},
    )
    assert result["cross_scale_interpretation"]["classification"] == "sustained_across_elapsed_scales"
    assert result["agreement"]["agreement_score"] == 1.0


def test_opposing_directions_across_scales_are_classified_as_conflicting() -> None:
    values = [10.0] * 120 + [0.0] * 45 + [20.0] * 15
    result = analyze_multiscale(
        rows=_multiscale_rows(values),
        numeric_columns=["temperature"],
        timestamp_column="timestamp",
        config={"scales": _time_scales()},
    )
    assert result["cross_scale_interpretation"]["classification"] == "conflicting_scales"
    assert result["agreement"]["conflicting_signals"][0]["column"] == "temperature"


def test_undercovered_elapsed_horizon_is_skipped() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        {"timestamp": (start + timedelta(minutes=index)).isoformat(), "temperature": 10.0}
        for index in range(12)
    ]
    rows.extend(
        {"timestamp": (start + timedelta(hours=2, minutes=index)).isoformat(), "temperature": 20.0}
        for index in range(6)
    )
    result = analyze_multiscale(
        rows=rows,
        numeric_columns=["temperature"],
        timestamp_column="timestamp",
        config={"scales": [{"name": "15m", "seconds": 900}]},
    )
    scale = result["scales"][0]
    assert scale["status"] == "limited"
    assert scale["reason"] == "insufficient_active_time_coverage"
    assert scale["active_time_coverage_fraction"] < 0.8
    assert result["cross_scale_interpretation"]["classification"] == "insufficient_coverage"


def test_irregular_monotonic_timestamps_remain_elapsed_time_based() -> None:
    result = analyze_multiscale(
        rows=_multiscale_rows([10.0] * 100 + [20.0] * 40, irregular=True),
        numeric_columns=["temperature"],
        timestamp_column="timestamp",
        config={"scales": _time_scales()},
    )
    assert result["analysis_basis"] == "elapsed_time"
    assert result["used_row_fallback"] is False
    assert any(scale["status"] == "complete" for scale in result["scales"])


def test_no_timestamp_uses_row_scales_without_duration_claim() -> None:
    result = analyze_multiscale(
        rows=[{"temperature": 10.0 if index < 36 else 20.0} for index in range(60)],
        numeric_columns=["temperature"],
        timestamp_column=None,
    )
    assert result["status"] == "limited"
    assert result["reason"] == "timestamp_column_unavailable"
    assert result["analysis_basis"] == "row_count"
    assert result["used_row_fallback"] is True
    assert result["cross_scale_interpretation"]["elapsed_time_basis"] is False
    assert result["agreement"]["sustained_change_observed"] is False
    assert all("horizon_seconds" not in scale and "actual_active_span_seconds" not in scale for scale in result["scales"])


# Canonical output, failure-state, compatibility, and evidence persistence audit.

def test_canonical_phase2_outputs_are_populated_and_marked_supporting_only() -> None:
    rows = _mode_rows()
    result = evaluate_sii(
        columns=["timestamp", "stage", "flow", "pressure"],
        rows=rows,
        numeric_profiles=_profiles("flow", "pressure"),
        timestamp_column="timestamp",
        config={
            "numeric_columns": ["flow", "pressure"],
            "multiscale_config": {"scales": [{"name": "15m", "seconds": 900}, {"name": "30m", "seconds": 1800}]},
        },
    )
    graph = result["relationship_graph"]
    conditioned = result["operating_modes"]["mode_conditioned_baseline"]
    adaptive = result["persistence_analysis"]["adaptive_persistence"]
    multiscale = result["multiscale_analysis"]
    assert "connected_changed_components" in graph
    assert "node_disruption_scores" in graph
    assert conditioned["selected_operating_mode"]["mode_id"]
    assert "fallback_reason" in conditioned
    assert "required_observations" in adaptive
    assert "actual_persistence" in adaptive
    assert multiscale["cross_scale_interpretation"]["classification"]
    assert result["processing_trace"]["phase_2_authoritative"] is False
    assert result["processing_trace"]["phase_2_effect"] == "supporting_evidence_only"
    assert result["findings"] == []
    assert result["compatibility"]["relationship_model"]["relationship_graph"] != graph


def test_insufficient_telemetry_returns_structured_limited_phase2_outputs() -> None:
    result = evaluate_sii(
        columns=["flow", "pressure"],
        rows=[{"flow": float(index), "pressure": float(index * 2)} for index in range(4)],
        numeric_profiles=_profiles("flow", "pressure"),
        timestamp_column=None,
        config={"numeric_columns": ["flow", "pressure"]},
    )
    assert result["relationship_graph"]["status"] == "limited"
    assert result["operating_modes"]["mode_conditioned_baseline"]["status"] == "limited"
    assert result["persistence_analysis"]["adaptive_persistence"]["status"] == "limited"
    assert result["multiscale_analysis"]["status"] == "limited"
    statuses = result["processing_trace"]["module_statuses"]
    for module in (
        "mode_conditioned_baseline",
        "relationship_graph_analysis",
        "adaptive_persistence",
        "multiscale_analysis",
    ):
        assert statuses[module]["status"] == "limited"
        assert statuses[module].get("reason")


def test_phase2_supporting_evidence_is_available_to_evidence_persistence() -> None:
    rows = _mode_rows()
    sii = evaluate_sii(
        columns=["timestamp", "stage", "flow", "pressure"],
        rows=rows,
        numeric_profiles=_profiles("flow", "pressure"),
        timestamp_column="timestamp",
        config={"numeric_columns": ["flow", "pressure"]},
    )
    upload_result = {
        "sii_result": sii,
        "columns": ["timestamp", "stage", "flow", "pressure"],
        "column_count": 4,
        "row_count": len(rows),
        "operating_state": "Baseline-aligned",
        "drift_status": "info",
        "sii_intelligence": {},
        "baseline_analysis": sii["compatibility"]["baseline_analysis"],
        "timestamp_profile": sii["compatibility"]["timestamp_profile"],
        "data_quality": sii["compatibility"]["data_quality"],
        "processing_trace": sii["processing_trace"],
        "completed_at": "2026-01-01T02:00:00+00:00",
        "last_processed_at": "2026-01-01T02:00:00+00:00",
    }
    record = build_evidence_record_from_result(
        run_id="phase2-audit",
        filename="phase2-audit.csv",
        source_type="csv_upload",
        result=upload_result,
        created_at="2026-01-01T02:00:00+00:00",
        completed_at="2026-01-01T02:00:00+00:00",
        status="completed",
        initiated_by="audit",
    )
    phase2 = record["phase_2_supporting_evidence"]
    assert phase2["authoritative"] is False
    assert "connected_changed_components" in phase2["relationship_graph"]
    assert phase2["mode_conditioned_baseline"]["selected_operating_mode"]
    assert phase2["adaptive_persistence"]["actual_persistence"]
    assert phase2["multiscale_analysis"]["cross_scale_interpretation"]
    assert phase2["processing_trace"]["module_statuses"]
