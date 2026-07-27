from __future__ import annotations

import time
from statistics import median
from typing import Any

from app.engine.sii.common import finite_number, module_envelope, timestamp_statistics

DEFAULT_CONFIG = {
    "minimum_recent_rows": 3,
    "minimum_timestamp_coverage": 0.90,
    "minimum_regularity": 0.80,
    "support_fraction_threshold": 0.70,
    "duration_fraction_threshold": 0.70,
}


def evaluate_adaptive_persistence(
    *,
    rows: list[dict[str, Any]],
    timestamp_column: str | None,
    baseline_analysis: dict[str, Any],
    fixed_persistence: dict[str, Any] | None = None,
    empirical_thresholds: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate persistence as elapsed-time support when timestamps permit it."""

    started = time.perf_counter()
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    recent_count = max(0, int(baseline_analysis.get("recent_window_rows") or 0))
    recent_rows = rows[-recent_count:] if recent_count else []
    timestamp_profile = timestamp_statistics(recent_rows, timestamp_column)
    parsed = timestamp_profile.pop("parsed")
    valid_timestamps = [value for value in parsed if value is not None]
    monotonic = all(current > previous for previous, current in zip(valid_timestamps, valid_timestamps[1:]))
    sampling_regular = float(timestamp_profile.get("regularity") or 0.0) >= float(cfg["minimum_regularity"])
    reliable = bool(
        timestamp_column
        and len(recent_rows) >= int(cfg["minimum_recent_rows"])
        and float(timestamp_profile.get("coverage") or 0.0) >= float(cfg["minimum_timestamp_coverage"])
        and timestamp_profile.get("median_interval_seconds") is not None
        and monotonic
    )
    assumptions = [
        "Elapsed-time support is calculated only from ordered positive timestamp intervals.",
        "A terminal sample receives one median sampling interval of duration support.",
        "Persistence is observational evidence and does not predict failure time.",
    ]
    if not reliable:
        reason = (
            "insufficient_recent_rows"
            if len(recent_rows) < int(cfg["minimum_recent_rows"])
            else "timestamps_not_strictly_increasing"
            if timestamp_column and not monotonic
            else "timestamp_evidence_not_reliable_for_elapsed_persistence"
        )
        envelope = module_envelope(
            started=started,
            status="limited",
            reason=reason,
            inputs_used=["recent_rows", "timestamp_column", "fixed_row_support"],
            rows_used=len(recent_rows),
            columns_used=[],
            assumptions=assumptions,
            output_metrics={
                "persistent_signal_count": len((fixed_persistence or {}).get("persistent_columns", [])),
                "elapsed_time_available": False,
            },
            limitations=[
                "Elapsed-time persistence was unavailable; the preserved fixed row-support result is exposed as an explicit fallback."
            ],
        )
        return {
            **envelope,
            "method": "elapsed_time_weighted_persistence_v1",
            "elapsed_time_available": False,
            "used_row_fallback": True,
            "timestamp_profile": timestamp_profile,
            "persistent_columns": list((fixed_persistence or {}).get("persistent_columns", [])),
            "details": [],
            "row_fallback": fixed_persistence or {},
        }

    median_interval = float(timestamp_profile["median_interval_seconds"])
    weights = _sample_duration_weights(parsed, median_interval)
    empirical_by_signal = (
        empirical_thresholds.get("signal_thresholds", {})
        if isinstance(empirical_thresholds, dict)
        else {}
    )
    details = []
    persistent_columns = []
    for drift in baseline_analysis.get("column_drift", []):
        if not isinstance(drift, dict) or drift.get("drift_flag") == "normal":
            continue
        column = str(drift.get("column") or "")
        direction = str(drift.get("direction") or "flat")
        baseline_average = finite_number(drift.get("baseline_average"))
        if not column or direction not in {"up", "down"} or baseline_average is None:
            continue
        fixed_threshold = max(0.01 * abs(baseline_average), 0.01)
        empirical = empirical_by_signal.get(column) if isinstance(empirical_by_signal, dict) else None
        learned_threshold = finite_number(empirical.get("threshold")) if isinstance(empirical, dict) else None
        threshold = max(fixed_threshold, learned_threshold or 0.0)
        observations: list[tuple[bool, float]] = []
        for row, duration in zip(recent_rows, weights):
            value = finite_number(row.get(column))
            if value is None or duration <= 0:
                continue
            supported = (
                value > baseline_average + threshold
                if direction == "up"
                else value < baseline_average - threshold
            )
            observations.append((supported, duration))
        if not observations:
            continue
        observed_duration = sum(duration for _supported, duration in observations)
        supporting_duration = sum(duration for supported, duration in observations if supported)
        longest_duration = _longest_supported_duration(observations)
        support_fraction = supporting_duration / max(observed_duration, 1e-12)
        required_duration = max(
            int(cfg["minimum_recent_rows"]) * median_interval,
            float(cfg["duration_fraction_threshold"]) * observed_duration,
        )
        persistent = bool(
            support_fraction >= float(cfg["support_fraction_threshold"])
            and longest_duration >= required_duration
        )
        if persistent:
            persistent_columns.append(column)
        details.append(
            {
                "column": column,
                "direction": direction,
                "baseline_average": round(baseline_average, 6),
                "deviation_threshold": round(threshold, 6),
                "threshold_source": "empirical_with_fixed_floor" if learned_threshold is not None else "fixed_floor",
                "observations": len(observations),
                "observed_duration_seconds": round(observed_duration, 6),
                "supporting_duration_seconds": round(supporting_duration, 6),
                "longest_continuous_support_seconds": round(longest_duration, 6),
                "required_continuous_support_seconds": round(required_duration, 6),
                "support_fraction": round(support_fraction, 6),
                "persistent": persistent,
            }
        )

    observed_duration = sum(weights)
    metrics = {
        "elapsed_time_available": True,
        "recent_rows": len(recent_rows),
        "observed_duration_seconds": round(observed_duration, 6),
        "signals_assessed": len(details),
        "persistent_signal_count": len(persistent_columns),
    }
    duration_limitations = [] if sampling_regular else [
        "Sampling intervals were irregular; actual elapsed intervals were used instead of converting row counts to duration."
    ]
    envelope = module_envelope(
        started=started,
        status="complete",
        reason=None,
        inputs_used=["recent_rows", "timestamp_column", "baseline_signal_drift", "empirical_thresholds"],
        rows_used=len(recent_rows),
        columns_used=[item["column"] for item in details],
        assumptions=assumptions,
        output_metrics=metrics,
        limitations=(
            duration_limitations
            + ([] if details else ["No non-flat watch/review signal was eligible for elapsed-time persistence."])
        ),
    )
    return {
        **envelope,
        "method": "elapsed_time_weighted_persistence_v1",
        "elapsed_time_available": True,
        "sampling_regular": sampling_regular,
        "used_row_fallback": False,
        "timestamp_profile": timestamp_profile,
        "observed_duration_seconds": metrics["observed_duration_seconds"],
        "persistent_columns": persistent_columns,
        "details": details,
        "thresholds": {
            "support_fraction": float(cfg["support_fraction_threshold"]),
            "duration_fraction": float(cfg["duration_fraction_threshold"]),
        },
    }


def _sample_duration_weights(parsed: list[Any], median_interval: float) -> list[float]:
    weights: list[float] = []
    for index, current in enumerate(parsed):
        if current is None:
            weights.append(0.0)
            continue
        next_valid = next((value for value in parsed[index + 1 :] if value is not None), None)
        if next_valid is not None:
            interval = (next_valid - current).total_seconds()
            weights.append(float(interval) if interval > 0 else 0.0)
        else:
            weights.append(max(0.0, median_interval))
    return weights


def _longest_supported_duration(observations: list[tuple[bool, float]]) -> float:
    longest = 0.0
    current = 0.0
    for supported, duration in observations:
        if supported:
            current += duration
            longest = max(longest, current)
        else:
            current = 0.0
    return longest
