from __future__ import annotations

import math

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.engine.sii.behavioral_model_store import InMemoryBehavioralModelStore
from app.engine.sii.evidence_fusion import PHASE_4_SOURCE_MODULE_ORDER
from app.engine.sii_engine import evaluate_sii


def _rows(*, violation: float = 0.0) -> tuple[list[str], list[dict[str, str]]]:
    columns = ["timestamp", "flow", "pressure"]
    rows = []
    for index in range(240):
        wave = math.sin(index / 8.0)
        flow = 100.0 + wave * 2.0
        pressure = 20.0 + flow * 0.5
        if index >= 168:
            pressure += violation
        rows.append(
            {
                "timestamp": f"2026-01-01T{index // 60:02d}:{index % 60:02d}:00Z",
                "flow": f"{flow:.8f}",
                "pressure": f"{pressure:.8f}",
            }
        )
    return columns, rows


def _profiles() -> list[dict]:
    return [
        {"column": column, "constant_or_stuck": False, "missing_count": 0, "non_numeric_count": 0}
        for column in ("flow", "pressure")
    ]


def _mode() -> dict:
    return {
        "baseline_mode": "running",
        "recent_mode": "running",
        "match": "strong",
        "confidence": "high",
        "features": {"baseline": {"state": "running"}, "recent": {"state": "running"}},
        "reasons": [],
    }


def _health() -> dict:
    return {
        "signals": [
            {"signal": "flow", "health": "healthy", "conditions": []},
            {"signal": "pressure", "health": "healthy", "conditions": []},
        ],
        "source_conditions": [],
    }


def _evaluate(
    store,
    run_id: str,
    *,
    violation: float = 0.0,
    phase4_config: dict | None = None,
    phase4_scope: AuthenticatedPhase4Scope | None | bool = True,
) -> dict:
    columns, rows = _rows(violation=violation)
    return evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=_profiles(),
        timestamp_column="timestamp",
        operating_mode=_mode(),
        sensor_health=_health(),
        data_quality={"readiness": "ready", "warnings": [], "data_confidence": {"rating": "high"}},
        phase4_scope=(
            AuthenticatedPhase4Scope(
                tenant_scope_id="org-1",
                workspace_id="ws-1",
            )
            if phase4_scope is True
            else phase4_scope
        ),
        config={
            "numeric_columns": ["flow", "pressure"],
            "source_run_id": run_id,
            "infrastructure_identity": {"organization_id": "org-1", "facility_id": "facility-1", "system_id": "system-1"},
            "behavioral_model_store": store,
            "phase_4_config": phase4_config or {},
        },
    )


def test_unified_engine_activates_phase4_after_phase3_and_extends_fusion() -> None:
    store = InMemoryBehavioralModelStore()
    result = _evaluate(store, "phase4-run-1")

    assert result["engine"] == {"name": "neraium_sii", "version": "v2"}
    assert result["signal_drift"]["status"] == "complete"
    assert result["relationship_analysis"]["status"] == "complete"
    assert result["covariance_analysis"]["status"] == "complete"
    assert result["behavioral_model"]["status"] == "complete"
    assert result["behavioral_model"]["active"] is True
    assert result["behavioral_snapshots"]["current_snapshot_id"]
    assert result["event_memory"]["events_recorded"] >= 1
    assert result["bayesian_evidence"]["active"] is False
    assert result["bayesian_evidence"]["posterior"] is None

    trace = result["processing_trace"]
    assert trace["modules_attempted"].index("physics_reasoning") < trace["modules_attempted"].index("phase_4")
    assert trace["modules_attempted"].index("phase_4") < trace["modules_attempted"].index("evidence_fusion")
    assert trace["phase_4_active"] is True
    assert trace["current_evidence_evaluated_before_model_update"] is True
    assert trace["model_version_after"] == "v1"
    assert trace["storage_writes"]

    inventory = {item["evidence_id"]: item for item in result["evidence_fusion"]["evidence_inventory"]}
    for module in PHASE_4_SOURCE_MODULE_ORDER:
        assert f"module:{module}" in inventory
        assert inventory[f"module:{module}"]["originating_module"] == module
    assert inventory["module:bayesian_evidence"]["classification"] == "Limiting"


def test_second_unified_run_uses_expected_models_and_residual_blocks_update() -> None:
    store = InMemoryBehavioralModelStore()
    first = _evaluate(store, "phase4-baseline")
    result = _evaluate(store, "phase4-violation", violation=30.0)

    assert first["behavioral_model"]["model_version"] == "v1"
    assert result["expected_behavior"]["models_evaluated"] >= 1
    assert result["expected_behavior"]["residual_evidence"]
    assert result["behavioral_model"]["learning_decision"]["decision"] == "blocked_by_active_observation"
    assert result["behavioral_model"]["model_version"] == "v1"
    assert result["findings"] == []
    assert result["expected_behavior"]["residual_evidence"][0]["diagnosis"] is None


class _UnavailableStore:
    def load_model(self, _model_id):
        raise RuntimeError("synthetic storage outage")

    def list_snapshots(self, _model_id):
        raise RuntimeError("synthetic storage outage")


def test_storage_outage_preserves_phase1_through_phase3_analysis() -> None:
    result = _evaluate(_UnavailableStore(), "phase4-storage-outage")
    assert result["signal_drift"]["status"] == "complete"
    assert result["relationship_analysis"]["status"] == "complete"
    assert result["covariance_analysis"]["status"] == "complete"
    assert result["physics_reasoning"]["active"] is True
    assert result["evidence_fusion"]["active"] is True
    assert result["behavioral_model"]["status"] == "limited"
    assert result["behavioral_model"]["active"] is False
    assert result["processing_trace"]["storage_failures"]
    assert result["findings"] == []


def test_human_validation_keeps_candidate_baseline_inactive() -> None:
    store = InMemoryBehavioralModelStore()
    result = _evaluate(
        store,
        "phase4-pending-human",
        phase4_config={"baseline_evolution_config": {"human_validation_required": True}},
    )
    learning = result["behavioral_model"]["learning_decision"]
    assert learning["status"] == "pending_validation"
    assert learning["learning_allowed"] is False
    assert learning["candidate_baseline"]["approval_status"] == "pending_validation"
    assert result["behavioral_model"]["baseline_state"]["active_version"] is None
    assert result["behavioral_snapshots"]["current_snapshot_id"] is None


def test_missing_phase4_scope_preserves_phase1_through_phase3_and_writes_nothing() -> None:
    store = InMemoryBehavioralModelStore()
    result = _evaluate(store, "phase4-no-auth-scope", phase4_scope=None)

    assert result["signal_drift"]["status"] == "complete"
    assert result["relationship_analysis"]["status"] == "complete"
    assert result["covariance_analysis"]["status"] == "complete"
    assert result["physics_reasoning"]["active"] is True
    assert result["behavioral_model"]["status"] == "limited"
    assert result["behavioral_model"]["limitations"] == ["authenticated_scope_unavailable"]
    assert result["behavioral_model"]["identity"] == {
        "identity_status": "limited",
        "identity_limitations": ["authenticated_scope_unavailable"],
        "memory_update_allowed": False,
    }
    assert result["processing_trace"]["storage_writes"] == []
