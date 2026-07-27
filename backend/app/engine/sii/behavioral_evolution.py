from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.engine.sii.common import EPSILON, finite_number, numeric_values


EVOLUTION_STATES = {
    "temporary_deviation",
    "persistent_behavioral_change",
    "validated_adaptation",
    "behavioral_recovery",
    "unresolved_instability",
    "insufficient_evidence",
}


def evaluate_behavioral_evolution(
    *,
    active_model: dict[str, Any] | None,
    snapshots: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    relationship_graph_comparison: dict[str, Any],
    operating_mode: dict[str, Any],
    expected_behavior: dict[str, Any],
    learning_decision: dict[str, Any],
    current_confidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(active_model, dict):
        return _limited("active_behavioral_model_unavailable")
    signal_memory = active_model.get("signal_memory") if isinstance(active_model.get("signal_memory"), dict) else {}
    relationship_memory = active_model.get("relationship_memory") if isinstance(active_model.get("relationship_memory"), dict) else {}
    signal_changes = []
    recovery_evidence = []
    unresolved = []
    for column in numeric_columns:
        values = numeric_values(rows, column)
        memory = signal_memory.get(column)
        if not values or not isinstance(memory, dict):
            continue
        observed = sum(values) / len(values)
        center = finite_number(memory.get("historical_center"))
        scale = finite_number(memory.get("historical_scale"))
        if center is None or scale is None:
            continue
        normalized = (observed - center) / max(abs(scale), EPSILON)
        history = [
            item for item in memory.get("drift_history", []) if isinstance(item, dict)
        ]
        same_direction_history = sum(
            1
            for item in history[-3:]
            if str(item.get("direction") or "").lower()
            == ("up" if normalized > 0 else "down" if normalized < 0 else "flat")
        )
        if abs(normalized) < 1.5:
            state = "behavioral_recovery" if any(
                abs(float(item.get("normalized_residual") or 0.0)) >= 3.0
                for item in memory.get("historical_residual_behavior", [])[-3:]
                if isinstance(item, dict)
            ) else "temporary_deviation"
        elif same_direction_history >= 2:
            state = "persistent_behavioral_change"
        else:
            state = "temporary_deviation"
        item = {
            "signal_id": column,
            "historical_center": center,
            "current_center": round(observed, 6),
            "historical_scale": scale,
            "normalized_change": round(normalized, 6),
            "classification": state,
            "history_support": same_direction_history,
            "source_model_version": active_model.get("model_version"),
        }
        signal_changes.append(item)
        if state == "behavioral_recovery":
            recovery_evidence.append(item)

    relationship_changes = [
        {
            **deepcopy(item),
            "classification": (
                "persistent_behavioral_change"
                if item.get("persistent_across_references")
                else "temporary_deviation"
            ),
        }
        for item in relationship_graph_comparison.get("changed_edges", [])
        if isinstance(item, dict)
    ]
    unresolved.extend(
        {
            "type": "expected_behavior_residual",
            "classification": "unresolved_instability",
            "source_evidence": deepcopy(item),
        }
        for item in expected_behavior.get("residual_evidence", [])
        if isinstance(item, dict)
    )
    mode_id = operating_mode.get("recent_mode")
    known_modes = active_model.get("operating_mode_memory") if isinstance(active_model.get("operating_mode_memory"), dict) else {}
    operating_mode_changes = []
    if mode_id and mode_id != "unavailable" and mode_id not in known_modes:
        operating_mode_changes.append(
            {
                "operating_mode": mode_id,
                "classification": "persistent_behavioral_change" if learning_decision.get("decision") == "accepted" else "insufficient_evidence",
                "source_evidence": deepcopy(operating_mode),
            }
        )
    adaptation = []
    if learning_decision.get("decision") == "accepted":
        adaptation.append(
            {
                "classification": "validated_adaptation",
                "decision_id": learning_decision.get("decision_id"),
                "baseline_version": (learning_decision.get("candidate_baseline") or {}).get("candidate_version"),
                "human_validation_required": learning_decision.get("human_validation_required"),
            }
        )
    confidence_changes = _confidence_changes(active_model, current_confidence)
    recurring_cycles = _recurring_cycles(snapshots)
    return {
        "status": "complete",
        "signal_changes": signal_changes,
        "relationship_changes": relationship_changes,
        "graph_changes": {
            "structural_change_scope": relationship_graph_comparison.get("structural_change_scope"),
            "persistent_topology_change": relationship_graph_comparison.get("persistent_topology_change"),
            "fragmentation": deepcopy(relationship_graph_comparison.get("graph_fragmentation", {})),
        },
        "operating_mode_changes": operating_mode_changes,
        "recovery_evidence": recovery_evidence,
        "adaptation_evidence": adaptation,
        "unresolved_changes": unresolved,
        "slow_signal_drift": [item for item in signal_changes if item["classification"] == "persistent_behavioral_change"],
        "relationship_weakening": [item for item in relationship_changes if item.get("change_type") == "weakened"],
        "relationship_strengthening": [item for item in relationship_changes if item.get("change_type") in {"strengthened", "emerged"}],
        "changing_variability": _variability_changes(signal_memory, snapshots),
        "changing_response_timing": _response_timing_changes(relationship_memory),
        "recurring_behavioral_cycles": recurring_cycles,
        "model_confidence_changes": confidence_changes,
        "seasonal_change": {
            "status": "limited" if recurring_cycles.get("status") != "supported" else "complete",
            "evidence": deepcopy(recurring_cycles),
            "limitations": [] if recurring_cycles.get("status") == "supported" else ["At least three time-separated snapshots are required before recurring behavior can be described."],
        },
        "relationship_lifecycle": {
            "emerged": [key for key, item in relationship_memory.items() if item.get("status") == "emerged"],
            "inactive": [key for key, item in relationship_memory.items() if item.get("status") == "inactive"],
            "retired": [key for key, item in relationship_memory.items() if item.get("status") == "retired"],
        },
        "limitations": [
            "Long-term behavioral change is not interpreted as degradation without separate engineering interpretation.",
            "Evolution classifications describe evidence persistence and validation state, not future failure.",
        ],
        "processing_trace": {
            "snapshots_compared": len(snapshots),
            "signals_compared": len(signal_changes),
            "relationships_compared": len(relationship_changes),
            "allowed_classifications": sorted(EVOLUTION_STATES),
            "degradation_claimed": False,
        },
    }


def _limited(reason: str) -> dict[str, Any]:
    return {
        "status": "limited",
        "reason": reason,
        "signal_changes": [],
        "relationship_changes": [],
        "graph_changes": {},
        "operating_mode_changes": [],
        "recovery_evidence": [],
        "adaptation_evidence": [],
        "unresolved_changes": [],
        "limitations": [reason],
        "processing_trace": {"snapshots_compared": 0, "degradation_claimed": False},
    }


def _confidence_changes(active_model: dict[str, Any], current: dict[str, Any] | None) -> dict[str, Any]:
    history = active_model.get("model_confidence_history") or []
    before = history[-1] if history else {}
    before_value = finite_number(before.get("compatibility"))
    after_value = finite_number((current or {}).get("compatibility"))
    return {
        "before": before_value,
        "after": after_value,
        "delta": round(after_value - before_value, 6) if before_value is not None and after_value is not None else None,
        "not_probability": True,
        "before_factors": deepcopy(before.get("factors", {})),
        "after_factors": deepcopy((current or {}).get("factors", {})),
    }


def _recurring_cycles(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    if len(snapshots) < 3:
        return {"status": "insufficient_evidence", "snapshot_support": len(snapshots), "cycles": []}
    mode_sequences = [
        sorted((snapshot.get("operating_mode_memory") or {}).keys())
        for snapshot in snapshots
        if isinstance(snapshot, dict)
    ]
    repeated = mode_sequences and all(sequence == mode_sequences[0] for sequence in mode_sequences[1:])
    return {
        "status": "supported" if repeated else "insufficient_evidence",
        "snapshot_support": len(snapshots),
        "cycles": [{"type": "recurring_mode_set", "modes": mode_sequences[0]}] if repeated else [],
        "method": "deterministic_repeated_snapshot_mode_set_comparison",
    }


def _variability_changes(signal_memory: dict[str, Any], snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not snapshots:
        return []
    prior_memory = snapshots[-1].get("signal_memory") if isinstance(snapshots[-1], dict) else {}
    output = []
    for signal_id, current in signal_memory.items():
        previous = prior_memory.get(signal_id) if isinstance(prior_memory, dict) else None
        if not isinstance(previous, dict):
            continue
        before = finite_number(previous.get("historical_scale"))
        after = finite_number(current.get("historical_scale"))
        if before is not None and after is not None and abs(after - before) > max(abs(before) * 0.2, EPSILON):
            output.append({"signal_id": signal_id, "before": before, "after": after, "delta": round(after - before, 6)})
    return output


def _response_timing_changes(relationship_memory: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for relationship_id, memory in relationship_memory.items():
        histories = memory.get("lag_history", [])
        values = []
        for item in histories:
            lag = ((item.get("global_temporal_lag_evidence") or {}).get("dominant_lag_shift")) if isinstance(item, dict) else None
            if isinstance(lag, (int, float)):
                values.append(float(lag))
        if len(values) >= 2 and values[-1] != values[-2]:
            output.append({"relationship_id": relationship_id, "previous_lag": values[-2], "current_lag": values[-1], "lag_delta": values[-1] - values[-2]})
    return output
