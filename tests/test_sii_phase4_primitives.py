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

from app.engine.sii.behavioral_model import (
    behavioral_model_section,
    build_behavioral_snapshot,
    build_candidate_model,
    resolve_infrastructure_identity,
    validate_model_compatibility,
)


def _identity_config(facility: str, system: str) -> dict:
    return {
        "infrastructure_identity": {
            "organization_id": "org-1",
            "facility_id": facility,
            "system_id": system,
        }
    }


def test_behavioral_identity_is_stable_and_unknown_identity_cannot_learn() -> None:
    columns = ["timestamp", "flow", "pressure"]
    first = resolve_infrastructure_identity(columns=columns, telemetry_signal_catalog={}, config=_identity_config("facility-a", "pump-a"))
    repeated = resolve_infrastructure_identity(columns=columns, telemetry_signal_catalog={}, config=_identity_config("facility-a", "pump-a"))
    unrelated = resolve_infrastructure_identity(columns=columns, telemetry_signal_catalog={}, config=_identity_config("facility-b", "pump-a"))
    unknown = resolve_infrastructure_identity(columns=columns, telemetry_signal_catalog={}, config={})

    assert first == repeated
    assert first["model_id"] != unrelated["model_id"]
    assert first["identity_status"] == "adequate"
    assert unknown["identity_status"] == "limited"
    assert unknown["model_id"] is None
    assert unknown["memory_update_allowed"] is False


def test_conflicting_identity_and_schema_compatibility_remain_visible() -> None:
    identity = resolve_infrastructure_identity(
        columns=["timestamp", "flow"],
        telemetry_signal_catalog={},
        config={
            "facility_id": "facility-a",
            "system_id": "system-a",
            "infrastructure_identity": {"facility_id": "facility-b", "system_id": "system-a"},
        },
    )
    assert identity["identity_status"] == "conflicting"
    assert "conflicting_facility_id" in identity["identity_limitations"]

    active = {
        "model_id": "different",
        "infrastructure_identity": {"facility_id": "facility-a", "schema_fingerprint": "old"},
    }
    compatibility = validate_model_compatibility(active, {**identity, "model_id": "expected"})
    assert compatibility["compatible"] is False
    assert compatibility["status"] == "conflicting"


def test_candidate_model_persists_inspectable_signal_and_mode_separated_relationship_memory() -> None:
    identity = resolve_infrastructure_identity(
        columns=["timestamp", "flow", "pressure"],
        telemetry_signal_catalog={},
        config=_identity_config("facility-a", "system-a"),
    )
    graph = {
        "nodes": [
            {"id": "metric:flow", "type": "metric", "source_column": "flow"},
            {"id": "metric:pressure", "type": "metric", "source_column": "pressure"},
        ],
        "eligible_edges": [
            {
                "columns": ["flow", "pressure"],
                "relationship_type": "linear_correlation",
                "baseline_strength": 0.99,
                "current_strength": 0.99,
                "baseline_sample_count": 50,
                "current_sample_count": 30,
            }
        ],
    }
    common = {
        "identity": identity,
        "rows": _rows(),
        "numeric_columns": ["flow", "pressure"],
        "timestamp_column": "timestamp",
        "telemetry_signal_catalog": {},
        "signal_drift": {"column_drift": [{"column": "flow", "direction": "flat"}]},
        "relationship_graph": graph,
        "sensor_health": _health(),
        "data_quality": {"readiness": "ready", "data_confidence": {"rating": "high"}},
        "temporal_analysis": {"mutual_information_drift": {"score": 0.0}, "lagged_relationships": {"dominant_lag_shift": 0}},
        "multiscale_analysis": {"status": "complete", "cross_scale_classification": "agreement", "scales_used": ["15_minutes"]},
        "physics_reasoning": {"applicable_priors": []},
        "expected_behavior": {"expected_values": []},
        "trained_expected_models": {},
        "baseline_record": None,
        "event_references": [],
        "source_run_id": "run-1",
        "observed_at": "2026-01-01T01:19:00+00:00",
        "allow_learning": True,
    }
    running_model, changes = build_candidate_model(
        active_model=None,
        operating_mode={"recent_mode": "running", "baseline_mode": "running", "confidence": "high"},
        **common,
    )
    assert changes["signals_added"] == 2
    assert changes["relationships_added"] == 1
    assert running_model["behavioral_identity"]["inspectable"] is True
    assert running_model["behavioral_identity"]["opaque_vector_used"] is False
    relationship = next(iter(running_model["relationship_memory"].values()))
    assert relationship["operating_modes_observed"] == ["running"]
    assert relationship["method_metadata"]["mode_conditioned"] is True

    idle_model, idle_changes = build_candidate_model(
        active_model=running_model,
        operating_mode={"recent_mode": "idle", "baseline_mode": "idle", "confidence": "high"},
        **{**common, "source_run_id": "run-2", "observed_at": "2026-01-02T01:19:00+00:00"},
    )
    assert idle_changes["relationships_added"] == 1
    assert len(idle_model["relationship_memory"]) == 2
    assert {tuple(item["operating_modes_observed"]) for item in idle_model["relationship_memory"].values()} == {("running",), ("idle",)}

    snapshot = build_behavioral_snapshot(
        model=idle_model,
        source_run_id="run-2",
        created_at="2026-01-02T01:19:00+00:00",
        previous_snapshot_id=None,
        changes=idle_changes,
    )
    section = behavioral_model_section(
        model=idle_model,
        identity=identity,
        snapshot_id=snapshot["snapshot_id"],
        baseline_state={},
        learning_decision={"decision": "accepted"},
        processing_trace={},
    )
    assert section["active"] is True
    assert section["signal_memory_summary"]["signals_tracked"] == 2
    assert section["relationship_memory_summary"]["relationships_tracked"] == 2
    assert section["confidence"]["not_probability"] is True


def test_unhealthy_sensor_is_excluded_from_candidate_memory() -> None:
    identity = resolve_infrastructure_identity(
        columns=["timestamp", "flow", "pressure"],
        telemetry_signal_catalog={},
        config=_identity_config("facility-a", "system-a"),
    )
    health = _health()
    health["signals"][1]["health"] = "review"
    model, changes = build_candidate_model(
        active_model=None,
        identity=identity,
        rows=_rows(),
        numeric_columns=["flow", "pressure"],
        timestamp_column="timestamp",
        telemetry_signal_catalog={},
        signal_drift={"column_drift": []},
        relationship_graph={"eligible_edges": [{"columns": ["flow", "pressure"], "current_strength": 0.9}]},
        operating_mode={"recent_mode": "running", "baseline_mode": "running"},
        sensor_health=health,
        data_quality={"readiness": "ready", "data_confidence": {"rating": "high"}},
        temporal_analysis={},
        multiscale_analysis={"status": "complete"},
        physics_reasoning={},
        expected_behavior={"expected_values": []},
        trained_expected_models={},
        baseline_record=None,
        event_references=[],
        source_run_id="run-unhealthy",
        observed_at="2026-01-01T01:19:00+00:00",
        allow_learning=True,
    )
    assert set(model["signal_memory"]) == {"flow"}
    assert model["relationship_memory"] == {}
    assert changes["relationships_added"] == 0
    assert any("sensor_health_not_acceptable" in item["reason"] for item in changes["learning_exclusions"])


def test_relationship_lifecycle_preserves_history_through_weakening_inactive_and_retired() -> None:
    identity = resolve_infrastructure_identity(
        columns=["timestamp", "flow", "pressure"],
        telemetry_signal_catalog={},
        config=_identity_config("facility-lifecycle", "system-lifecycle"),
    )

    def build(active_model, run_id: str, strength: float | None):
        edges = [] if strength is None else [
            {
                "columns": ["flow", "pressure"],
                "relationship_type": "linear_correlation",
                "baseline_strength": 0.95,
                "current_strength": strength,
                "baseline_sample_count": 50,
                "current_sample_count": 30,
            }
        ]
        return build_candidate_model(
            active_model=active_model,
            identity=identity,
            rows=_rows(),
            numeric_columns=["flow", "pressure"],
            timestamp_column="timestamp",
            telemetry_signal_catalog={},
            signal_drift={"column_drift": []},
            relationship_graph={"eligible_edges": edges, "nodes": []},
            operating_mode={"recent_mode": "running", "baseline_mode": "running"},
            sensor_health=_health(),
            data_quality={"readiness": "ready", "data_confidence": {"rating": "high"}},
            temporal_analysis={},
            multiscale_analysis={"status": "complete", "cross_scale_classification": "stable"},
            physics_reasoning={},
            expected_behavior={"expected_values": []},
            trained_expected_models={},
            baseline_record=None,
            event_references=[],
            source_run_id=run_id,
            observed_at=f"2026-01-0{run_id[-1]}T01:19:00+00:00",
            allow_learning=True,
        )

    model, _ = build(None, "run-1", 0.95)
    relationship_id = next(iter(model["relationship_memory"]))
    assert model["relationship_memory"][relationship_id]["status"] == "emerged"

    model, _ = build(model, "run-2", 0.50)
    assert model["relationship_memory"][relationship_id]["status"] == "weakened"
    assert model["relationship_memory"][relationship_id]["stability"] == "volatile"

    model, _ = build(model, "run-3", None)
    model, _ = build(model, "run-4", None)
    assert model["relationship_memory"][relationship_id]["status"] == "inactive"
    model, changes = build(model, "run-5", None)
    relationship = model["relationship_memory"][relationship_id]
    assert relationship["status"] == "retired"
    assert changes["relationships_retired"] == 1
    assert len(relationship["strength_history"]) == 2
    assert {item["status"] for item in relationship["change_history"]} >= {"emerged", "weakened", "inactive", "retired"}
