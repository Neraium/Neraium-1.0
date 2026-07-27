from __future__ import annotations

import time
from statistics import median
from typing import Any

from app.engine.sii.common import finite_number, module_envelope, timestamp_statistics

DEFAULT_CONFIG = {
    "minimum_recent_rows": 3,
    "phase2_active_fraction": 0.30,
    "align_to_phase2_active_window": False,
    "minimum_timestamp_coverage": 0.90,
    "minimum_regularity": 0.80,
    "support_fraction_threshold": 0.70,
    "duration_fraction_threshold": 0.70,
    "minimum_required_observations": 3,
    "maximum_required_observations": 12,
    "irregular_sampling_increment": 1,
    "limited_data_quality_increment": 1,
    "poor_data_quality_increment": 2,
    "limited_sensor_health_increment": 1,
    "poor_sensor_health_increment": 2,
    "ambiguous_mode_increment": 1,
    "unavailable_mode_increment": 2,
    "moderate_volatility_increment": 1,
    "high_volatility_increment": 2,
}


def evaluate_adaptive_persistence(
    *,
    rows: list[dict[str, Any]],
    timestamp_column: str | None,
    baseline_analysis: dict[str, Any],
    fixed_persistence: dict[str, Any] | None = None,
    empirical_thresholds: dict[str, Any] | None = None,
    data_quality: dict[str, Any] | None = None,
    sensor_health: dict[str, Any] | None = None,
    operating_mode: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate elapsed-time support with conservative adaptive requirements."""

    started = time.perf_counter()
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    phase1_recent_count = max(0, int(baseline_analysis.get("recent_window_rows") or 0))
    phase2_active_count = max(0, len(rows) - int(len(rows) * (1.0 - float(cfg["phase2_active_fraction"]))))
    recent_count = (
        min(phase1_recent_count, phase2_active_count)
        if phase1_recent_count and bool(cfg["align_to_phase2_active_window"])
        else phase1_recent_count
    )
    recent_rows = rows[-recent_count:] if recent_count else []
    timestamp_profile = timestamp_statistics(recent_rows, timestamp_column)
    parsed = timestamp_profile.pop("parsed")
    valid_timestamps = [value for value in parsed if value is not None]
    monotonic = all(current > previous for previous, current in zip(valid_timestamps, valid_timestamps[1:]))
    adaptive_regularity = _interval_regularity(parsed)
    timestamp_profile["adaptive_interval_regularity"] = round(adaptive_regularity, 6)
    sampling_regular = adaptive_regularity >= float(cfg["minimum_regularity"])
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
        "Quality, health, volatility, sampling, and mode adjustments can only retain or increase persistence requirements.",
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
            assumptions=[
                "The fallback counts supporting observations only.",
                "No elapsed-time claim is made from row counts.",
                "Persistence is observational evidence and does not predict failure time.",
            ],
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
            "method": "elapsed_time_weighted_adaptive_persistence_v2",
            "persistence_basis": "row_count",
            "elapsed_time_available": False,
            "used_row_fallback": True,
            "timestamp_profile": timestamp_profile,
            "persistent_columns": list((fixed_persistence or {}).get("persistent_columns", [])),
            "details": [],
            "row_fallback": fixed_persistence or {},
            "actual_persistence": {
                "persistent_columns": list((fixed_persistence or {}).get("persistent_columns", [])),
                "source": "fixed_row_support",
            },
        }

    median_interval = float(timestamp_profile["median_interval_seconds"])
    weights = _sample_duration_weights(parsed, median_interval)
    empirical_by_signal = (
        empirical_thresholds.get("signal_thresholds", {})
        if isinstance(empirical_thresholds, dict)
        else {}
    )
    health_by_signal = _health_by_signal(sensor_health)
    minimum_required = max(
        int(cfg["minimum_recent_rows"]),
        int(cfg["minimum_required_observations"]),
    )
    maximum_required = max(minimum_required, int(cfg["maximum_required_observations"]))
    common_adjustments = {
        "irregular_sampling": 0 if sampling_regular else max(0, int(cfg["irregular_sampling_increment"])),
        "data_quality": _data_quality_increment(data_quality, cfg),
        "operating_mode": _operating_mode_increment(operating_mode, cfg),
    }
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

        adjustments = {
            **common_adjustments,
            "volatility": _volatility_increment(drift, empirical, cfg),
            "sensor_health": _sensor_health_increment(health_by_signal.get(column), cfg),
        }
        required_observations = max(
            minimum_required,
            min(maximum_required, minimum_required + sum(max(0, int(value)) for value in adjustments.values())),
        )
        observed_duration = sum(duration for _supported, duration in observations)
        supporting_duration = sum(duration for supported, duration in observations if supported)
        supporting_observations = sum(1 for supported, _duration in observations if supported)
        longest_duration, longest_observations = _longest_supported_run(observations)
        support_fraction = supporting_duration / max(observed_duration, 1e-12)
        required_duration = max(
            required_observations * median_interval,
            float(cfg["duration_fraction_threshold"]) * observed_duration,
        )
        persistent = bool(
            supporting_observations >= required_observations
            and support_fraction >= float(cfg["support_fraction_threshold"])
            and longest_observations >= required_observations
            and longest_duration >= required_duration
        )
        if persistent:
            persistent_columns.append(column)
        actual = {
            "observations": len(observations),
            "supporting_observations": supporting_observations,
            "longest_continuous_support_observations": longest_observations,
            "observed_duration_seconds": round(observed_duration, 6),
            "supporting_duration_seconds": round(supporting_duration, 6),
            "longest_continuous_support_seconds": round(longest_duration, 6),
            "support_fraction": round(support_fraction, 6),
            "satisfied": persistent,
        }
        details.append(
            {
                "column": column,
                "direction": direction,
                "baseline_average": round(baseline_average, 6),
                "deviation_threshold": round(threshold, 6),
                "threshold_source": "empirical_with_fixed_floor" if learned_threshold is not None else "fixed_floor",
                "observations": len(observations),
                "supporting_observations": supporting_observations,
                "longest_continuous_support_observations": longest_observations,
                "required_observations": required_observations,
                "required_observation_bounds": {"minimum": minimum_required, "maximum": maximum_required},
                "requirement_adjustments": adjustments,
                "observed_duration_seconds": actual["observed_duration_seconds"],
                "supporting_duration_seconds": actual["supporting_duration_seconds"],
                "longest_continuous_support_seconds": actual["longest_continuous_support_seconds"],
                "required_continuous_support_seconds": round(required_duration, 6),
                "support_fraction": actual["support_fraction"],
                "actual_persistence": actual,
                "persistent": persistent,
            }
        )

    observed_duration = sum(weights)
    required_observations = max((item["required_observations"] for item in details), default=minimum_required)
    metrics = {
        "elapsed_time_available": True,
        "recent_rows": len(recent_rows),
        "observed_duration_seconds": round(observed_duration, 6),
        "signals_assessed": len(details),
        "persistent_signal_count": len(persistent_columns),
        "maximum_required_observations": required_observations,
    }
    duration_limitations = [] if sampling_regular else [
        "Sampling intervals were irregular; actual elapsed intervals were used and the observation requirement was not reduced."
    ]
    envelope = module_envelope(
        started=started,
        status="complete",
        reason=None,
        inputs_used=[
            "recent_rows",
            "timestamp_column",
            "baseline_signal_drift",
            "empirical_thresholds",
            "data_quality",
            "sensor_health",
            "operating_mode",
        ],
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
        "method": "elapsed_time_weighted_adaptive_persistence_v2",
        "persistence_basis": "elapsed_time",
        "elapsed_time_available": True,
        "sampling_regular": sampling_regular,
        "used_row_fallback": False,
        "timestamp_profile": timestamp_profile,
        "observed_duration_seconds": metrics["observed_duration_seconds"],
        "recent_window": {
            "rows": recent_count,
            "phase1_recent_rows": phase1_recent_count,
            "phase2_active_rows": phase2_active_count,
            "selection": (
                "minimum_of_phase1_recent_and_phase2_30_percent_active_window"
                if bool(cfg["align_to_phase2_active_window"])
                else "phase1_recent_window"
            ),
        },
        "required_observations": required_observations,
        "required_observation_bounds": {"minimum": minimum_required, "maximum": maximum_required},
        "persistent_columns": persistent_columns,
        "actual_persistence": {
            "persistent_columns": persistent_columns,
            "persistent_signal_count": len(persistent_columns),
            "signals_assessed": len(details),
            "source": "elapsed_time_support",
        },
        "details": details,
        "thresholds": {
            "support_fraction": float(cfg["support_fraction_threshold"]),
            "duration_fraction": float(cfg["duration_fraction_threshold"]),
        },
    }


def _interval_regularity(parsed: list[Any]) -> float:
    valid = [value for value in parsed if value is not None]
    intervals = [
        (current - previous).total_seconds()
        for previous, current in zip(valid, valid[1:])
        if (current - previous).total_seconds() > 0
    ]
    if not intervals:
        return 0.0
    center = float(median(intervals))
    tolerance = max(1e-12, 0.20 * center)
    return sum(abs(value - center) <= tolerance for value in intervals) / len(intervals)


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


def _longest_supported_run(observations: list[tuple[bool, float]]) -> tuple[float, int]:
    longest_duration = 0.0
    current_duration = 0.0
    longest_observations = 0
    current_observations = 0
    for supported, duration in observations:
        if supported:
            current_duration += duration
            current_observations += 1
            longest_duration = max(longest_duration, current_duration)
            longest_observations = max(longest_observations, current_observations)
        else:
            current_duration = 0.0
            current_observations = 0
    return longest_duration, longest_observations


def _data_quality_increment(data_quality: dict[str, Any] | None, config: dict[str, Any]) -> int:
    quality = data_quality or {}
    confidence = quality.get("data_confidence") if isinstance(quality.get("data_confidence"), dict) else {}
    rating = str(confidence.get("rating") or quality.get("reliability_rating") or "").strip().lower()
    readiness = str(quality.get("readiness") or "").strip().lower()
    if rating in {"low", "weak", "not_reliable"} or readiness == "not_ready":
        return max(0, int(config["poor_data_quality_increment"]))
    if rating in {"limited", "usable"} or readiness == "needs_review" or quality.get("warnings"):
        return max(0, int(config["limited_data_quality_increment"]))
    return 0


def _operating_mode_increment(operating_mode: dict[str, Any] | None, config: dict[str, Any]) -> int:
    if not isinstance(operating_mode, dict):
        return 0
    match = str(operating_mode.get("match") or "unavailable").strip().lower()
    if match in {"weak", "unavailable"}:
        return max(0, int(config["unavailable_mode_increment"]))
    if match == "partial" or str(operating_mode.get("confidence") or "").lower() in {"low", "limited"}:
        return max(0, int(config["ambiguous_mode_increment"]))
    return 0


def _volatility_increment(
    drift: dict[str, Any], empirical: dict[str, Any] | None, config: dict[str, Any]
) -> int:
    if any("highly variable" in str(item).lower() for item in drift.get("warnings", [])):
        return max(0, int(config["high_volatility_increment"]))
    if not isinstance(empirical, dict):
        return 0
    robust_sigma = finite_number(empirical.get("robust_sigma"))
    fixed_floor = finite_number(empirical.get("fixed_floor"))
    if robust_sigma is None or fixed_floor is None or fixed_floor <= 0:
        return 0
    ratio = robust_sigma / fixed_floor
    if ratio >= 3.0:
        return max(0, int(config["high_volatility_increment"]))
    if ratio >= 1.5:
        return max(0, int(config["moderate_volatility_increment"]))
    return 0


def _health_by_signal(sensor_health: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("signal")): item
        for item in (sensor_health or {}).get("signals", [])
        if isinstance(item, dict) and item.get("signal")
    }


def _sensor_health_increment(profile: dict[str, Any] | None, config: dict[str, Any]) -> int:
    if not isinstance(profile, dict):
        return 0
    health = str(profile.get("health") or "healthy").strip().lower()
    conditions = [item for item in profile.get("conditions", []) if isinstance(item, dict)]
    severe_types = {
        "flatline_or_stuck",
        "frozen_precision",
        "sparse_baseline_coverage",
        "possible_drift",
        "timestamp_misalignment",
    }
    if health in {"suspect", "unhealthy", "failed"} or any(
        str(item.get("type") or "") in severe_types for item in conditions
    ):
        return max(0, int(config["poor_sensor_health_increment"]))
    if health in {"review", "watch", "limited"} or conditions:
        return max(0, int(config["limited_sensor_health_increment"]))
    return 0
