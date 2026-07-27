from __future__ import annotations

from copy import deepcopy
from statistics import median
from typing import Any

from app.engine.sii.common import (
    EPSILON,
    finite_number,
    median_absolute_deviation,
    numeric_values,
    parse_timestamps,
    quantile,
)


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
    timestamp_column: str | None = None,
) -> dict[str, Any]:
    if not isinstance(active_model, dict):
        return _limited("active_behavioral_model_unavailable")
    signal_memory = active_model.get("signal_memory") if isinstance(active_model.get("signal_memory"), dict) else {}
    relationship_memory = active_model.get("relationship_memory") if isinstance(active_model.get("relationship_memory"), dict) else {}
    signal_changes = []
    recovery_evidence = []
    unresolved = []
    temporal_characterization = _temporal_characterization(
        rows=rows,
        numeric_columns=numeric_columns,
        timestamp_column=timestamp_column,
        signal_memory=signal_memory,
        snapshots=snapshots,
    )
    temporal_by_signal = {
        str(item["signal_id"]): item
        for item in temporal_characterization["signals"]
    }
    for column in numeric_columns:
        values = numeric_values(rows, column)
        memory = signal_memory.get(column)
        if not values or not isinstance(memory, dict):
            continue
        observed = float(median(values))
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
            "temporal_characterization": deepcopy(
                temporal_by_signal.get(column, {})
            ),
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
        "temporal_characterization": temporal_characterization,
        "behavioral_velocity": [
            {
                "signal_id": item["signal_id"],
                **deepcopy(item["velocity"]),
            }
            for item in temporal_characterization["signals"]
        ],
        "behavioral_acceleration": [
            {
                "signal_id": item["signal_id"],
                **deepcopy(item["acceleration"]),
            }
            for item in temporal_characterization["signals"]
        ],
        "behavioral_curvature": [
            {
                "signal_id": item["signal_id"],
                **deepcopy(item["curvature"]),
            }
            for item in temporal_characterization["signals"]
        ],
        "recovery_trajectories": [
            deepcopy(item)
            for item in temporal_characterization["signals"]
            if item["trajectory"]["classification"] == "recovery_trajectory"
        ],
        "stabilization_detection": [
            {
                "signal_id": item["signal_id"],
                **deepcopy(item["stabilization"]),
            }
            for item in temporal_characterization["signals"]
        ],
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
            "temporal_signals_characterized": len(
                temporal_characterization["signals"]
            ),
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
        "temporal_characterization": {
            "status": "limited",
            "reason": reason,
            "signals": [],
        },
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


def _temporal_characterization(
    *,
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    signal_memory: dict[str, Any],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    parsed = parse_timestamps(rows, timestamp_column)
    valid_time_count = sum(value is not None for value in parsed)
    timestamp_coverage = valid_time_count / max(1, len(rows))
    timestamp_reliable = bool(
        timestamp_column
        and timestamp_coverage >= 0.9
        and all(
            current > previous
            for previous, current in zip(
                [item for item in parsed if item is not None],
                [item for item in parsed if item is not None][1:],
            )
        )
    )
    first_valid_timestamp = next(
        (item for item in parsed if item is not None),
        None,
    )
    output = []
    for column in numeric_columns:
        pairs = []
        for index, row in enumerate(rows):
            value = finite_number(row.get(column))
            if value is None:
                continue
            if timestamp_reliable and parsed[index] is None:
                continue
            coordinate = (
                (parsed[index] - first_valid_timestamp).total_seconds()
                if timestamp_reliable
                and parsed[index] is not None
                and first_valid_timestamp is not None
                else float(index)
            )
            pairs.append((float(coordinate), value))
        if len(pairs) < 5:
            continue
        center = finite_number((signal_memory.get(column) or {}).get("historical_center"))
        scale = finite_number((signal_memory.get(column) or {}).get("historical_scale"))
        velocities = _derivative(pairs)
        accelerations = _derivative(velocities)
        curvatures = _derivative(accelerations)
        value_slope = _theil_sen_slope(pairs)
        normalized_distances = (
            [
                (coordinate, abs((value - center) / max(abs(scale), EPSILON)))
                for coordinate, value in pairs
            ]
            if center is not None and scale is not None
            else []
        )
        distance_slope = _theil_sen_slope(normalized_distances)
        trajectory = _trajectory(normalized_distances, distance_slope)
        stabilization = _stabilization(
            velocities=velocities,
            accelerations=accelerations,
            trajectory=trajectory,
        )
        output.append(
            {
                "signal_id": column,
                "time_basis": "elapsed_seconds"
                if timestamp_reliable
                else "ordered_samples",
                "sample_support": len(pairs),
                "velocity": _derivative_summary(
                    value_slope,
                    velocities,
                    unit="signal_units_per_second"
                    if timestamp_reliable
                    else "signal_units_per_sample",
                    method="theil_sen_slope_with_first_difference_dispersion",
                ),
                "acceleration": _derivative_summary(
                    float(median(value for _time, value in accelerations))
                    if accelerations
                    else None,
                    accelerations,
                    unit="signal_units_per_second_squared"
                    if timestamp_reliable
                    else "signal_units_per_sample_squared",
                    method="median_second_difference_rate",
                ),
                "curvature": _derivative_summary(
                    float(median(value for _time, value in curvatures))
                    if curvatures
                    else None,
                    curvatures,
                    unit="signal_units_per_second_cubed"
                    if timestamp_reliable
                    else "signal_units_per_sample_cubed",
                    method="median_third_difference_rate",
                ),
                "trajectory": trajectory,
                "stabilization": stabilization,
                "snapshot_trajectory": _snapshot_trajectory(
                    signal_id=column,
                    snapshots=snapshots,
                    current_center=float(median(value for _time, value in pairs)),
                ),
            }
        )
    return {
        "status": "complete" if output else "limited",
        "method": "robust_derivative_and_baseline_distance_trajectory_v1",
        "timestamp_coverage": round(timestamp_coverage, 6),
        "time_basis": "elapsed_seconds" if timestamp_reliable else "ordered_samples",
        "signals": output,
        "limitations": []
        if timestamp_reliable
        else [
            "Reliable monotonic timestamps were unavailable; derivatives are reported per ordered sample and are not interpreted as elapsed-time rates."
        ],
        "processing_trace": {
            "opaque_model_used": False,
            "future_state_predicted": False,
            "diagnosis_performed": False,
        },
    }


def _derivative(
    pairs: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    output = []
    for (left_time, left_value), (right_time, right_value) in zip(
        pairs,
        pairs[1:],
    ):
        delta_time = right_time - left_time
        if delta_time > EPSILON:
            output.append(
                (
                    (left_time + right_time) / 2.0,
                    (right_value - left_value) / delta_time,
                )
            )
    return output


def _theil_sen_slope(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    bounded = pairs
    if len(pairs) > 80:
        indices = sorted(
            {
                round(index * (len(pairs) - 1) / 79)
                for index in range(80)
            }
        )
        bounded = [pairs[index] for index in indices]
    slopes = [
        (right_value - left_value) / (right_time - left_time)
        for left_index, (left_time, left_value) in enumerate(bounded)
        for right_time, right_value in bounded[left_index + 1 :]
        if right_time - left_time > EPSILON
    ]
    return float(median(slopes)) if slopes else None


def _derivative_summary(
    center: float | None,
    derivatives: list[tuple[float, float]],
    *,
    unit: str,
    method: str,
) -> dict[str, Any]:
    values = [value for _time, value in derivatives]
    return {
        "value": round(center, 9) if center is not None else None,
        "robust_dispersion": round(
            1.4826 * median_absolute_deviation(values),
            9,
        )
        if values
        else None,
        "empirical_interval": [
            round(quantile(values, 0.10), 9),
            round(quantile(values, 0.90), 9),
        ]
        if values
        else None,
        "sample_support": len(values),
        "unit": unit,
        "method": method,
    }


def _trajectory(
    distances: list[tuple[float, float]],
    slope: float | None,
) -> dict[str, Any]:
    if len(distances) < 5 or slope is None:
        return {
            "classification": "insufficient_evidence",
            "normalized_distance_slope": None,
            "rank_concordance": None,
        }
    split = max(1, len(distances) // 3)
    start = float(median(value for _time, value in distances[:split]))
    end = float(median(value for _time, value in distances[-split:]))
    concordance = _kendall_concordance(distances)
    if slope < -EPSILON and end < start:
        classification = "recovery_trajectory"
    elif slope > EPSILON and end > start:
        classification = "diverging_trajectory"
    else:
        classification = "stable_or_non_monotonic_trajectory"
    return {
        "classification": classification,
        "start_normalized_distance": round(start, 6),
        "end_normalized_distance": round(end, 6),
        "normalized_distance_slope": round(slope, 9),
        "rank_concordance": round(concordance, 6),
        "method": "theil_sen_slope_and_kendall_pair_concordance_of_absolute_baseline_distance",
    }


def _kendall_concordance(pairs: list[tuple[float, float]]) -> float:
    bounded = pairs
    if len(pairs) > 160:
        indices = sorted(
            {
                round(index * (len(pairs) - 1) / 159)
                for index in range(160)
            }
        )
        bounded = [pairs[index] for index in indices]
    concordant = 0
    discordant = 0
    for left_index, (_left_time, left_value) in enumerate(bounded):
        for _right_time, right_value in bounded[left_index + 1 :]:
            difference = right_value - left_value
            concordant += difference > EPSILON
            discordant += difference < -EPSILON
    return (concordant - discordant) / max(1, concordant + discordant)


def _stabilization(
    *,
    velocities: list[tuple[float, float]],
    accelerations: list[tuple[float, float]],
    trajectory: dict[str, Any],
) -> dict[str, Any]:
    if len(velocities) < 6:
        return {
            "detected": False,
            "status": "insufficient_evidence",
            "method": "robust_recent_vs_early_derivative_contraction",
        }
    split = max(2, len(velocities) // 3)
    early = [abs(value) for _time, value in velocities[:split]]
    recent = [abs(value) for _time, value in velocities[-split:]]
    early_center = float(median(early))
    recent_center = float(median(recent))
    early_scale = 1.4826 * median_absolute_deviation(early)
    recent_scale = 1.4826 * median_absolute_deviation(recent)
    acceleration_values = [abs(value) for _time, value in accelerations[-split:]]
    detected = bool(
        recent_center <= early_center
        and recent_scale <= early_scale
        and (recent_center < early_center or recent_scale < early_scale)
        and trajectory.get("classification")
        in {"recovery_trajectory", "stable_or_non_monotonic_trajectory"}
    )
    return {
        "detected": detected,
        "status": "supported" if detected else "not_supported",
        "early_absolute_velocity_median": round(early_center, 9),
        "recent_absolute_velocity_median": round(recent_center, 9),
        "early_velocity_robust_dispersion": round(early_scale, 9),
        "recent_velocity_robust_dispersion": round(recent_scale, 9),
        "recent_absolute_acceleration_median": round(
            float(median(acceleration_values)),
            9,
        )
        if acceleration_values
        else None,
        "method": "robust_recent_vs_early_derivative_contraction",
    }


def _snapshot_trajectory(
    *,
    signal_id: str,
    snapshots: list[dict[str, Any]],
    current_center: float,
) -> dict[str, Any]:
    centers = []
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, dict):
            continue
        memory = snapshot.get("signal_memory")
        item = memory.get(signal_id) if isinstance(memory, dict) else None
        center = finite_number(item.get("historical_center")) if isinstance(item, dict) else None
        if center is not None:
            centers.append((float(index), center))
    centers.append((float(len(snapshots)), current_center))
    return {
        "snapshot_support": len(centers),
        "center_velocity_per_snapshot": round(
            _theil_sen_slope(centers),
            9,
        )
        if len(centers) >= 2
        else None,
        "method": "theil_sen_slope_of_snapshot_centers",
    }
