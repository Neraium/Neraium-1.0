from __future__ import annotations

from statistics import median
from typing import Any

from app.engine.sii.common import EPSILON, median_absolute_deviation, numeric_values, timestamp_statistics


DEFAULT_CONFIG = {"minimum_samples": 40, "baseline_fraction": 0.4, "deviation_threshold": 2.0, "recovery_threshold": 1.0}


def analyze_dynamical_stability(
    *,
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    timestamp = timestamp_statistics(rows, timestamp_column)
    if len(rows) < int(cfg["minimum_samples"]):
        return _limited("insufficient_dynamical_history", timestamp)
    if not timestamp.get("reliable"):
        return _limited("timestamps_inadequate_for_recovery_timing", timestamp)
    split = max(10, min(len(rows) - 5, int(len(rows) * float(cfg["baseline_fraction"]))))
    interval = float(timestamp.get("median_interval_seconds") or 0.0)
    results = []
    for column in numeric_columns:
        values = numeric_values(rows, column)
        if len(values) != len(rows):
            continue
        baseline = values[:split]
        active = values[split:]
        center = float(median(baseline))
        scale = max(1.4826 * median_absolute_deviation(baseline), EPSILON)
        distances = [abs(value - center) / scale for value in active]
        recovery_times = []
        open_index = None
        for index, distance in enumerate(distances):
            if open_index is None and distance >= float(cfg["deviation_threshold"]):
                open_index = index
            elif open_index is not None and distance <= float(cfg["recovery_threshold"]):
                recovery_times.append((index - open_index) * interval)
                open_index = None
        divergence = (distances[-1] - distances[0]) / max(1, len(distances) - 1) if len(distances) >= 2 else 0.0
        transition_persistence = sum(distance >= float(cfg["deviation_threshold"]) for distance in distances) / max(1, len(distances))
        results.append(
            {
                "signal_id": column,
                "recovery_behavior": {
                    "episodes_observed": len(recovery_times),
                    "return_to_baseline_seconds": round(float(median(recovery_times)), 6) if recovery_times else None,
                    "unrecovered_episode_active": open_index is not None,
                },
                "trajectory_divergence_proxy_per_sample": round(divergence, 6),
                "attractor_distance_proxy": round(float(median(distances)), 6) if distances else 0.0,
                "transition_persistence": round(transition_persistence, 6),
                "formal_stability_result": None,
                "limitations": ["These are empirical trajectory proxies; formal dynamical-stability assumptions were not established."],
            }
        )
    return {
        "status": "complete" if results else "limited",
        "reason": None if results else "no_signal_met_dynamical_assumptions",
        "method": "robust_return_to_baseline_trajectory_proxies_v1",
        "signals": results,
        "limitations": [] if results else ["No signal had complete numeric support."],
        "processing_trace": {
            "signals_attempted": len(numeric_columns),
            "signals_completed": len(results),
            "formal_stability_theory_claimed": False,
        },
    }


def _limited(reason: str, timestamp: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "limited",
        "reason": reason,
        "method": "robust_return_to_baseline_trajectory_proxies_v1",
        "signals": [],
        "sampling": timestamp,
        "limitations": [reason],
        "processing_trace": {"signals_completed": 0, "formal_stability_theory_claimed": False},
    }
