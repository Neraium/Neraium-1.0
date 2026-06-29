import math
from typing import Any

from app.services.cumulative_counters import (
    counter_delta_series,
    detect_cumulative_counters_from_matrix,
)
from app.services.data_quality import round_number, variability_flag

BASELINE_WINDOW_TARGET = 100
# Backward-compatible export for legacy relationship analysis imports.
BASELINE_WINDOW_FRACTION = 0.2
MIN_BASELINE_ROWS = 5
SPARSE_MISSING_WARNING_THRESHOLD = 0.05


def build_baseline_analysis(
    columns: list[str],
    rows: list[list[str]],
    numeric_profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    warnings: list[str] = []
    if len(rows) < MIN_BASELINE_ROWS:
        return {
            "baseline_window_rows": 0,
            "recent_window_rows": 0,
            "columns_analyzed": 0,
            "column_drift": [],
            "overall_assessment": "needs_review",
            "warnings": ["At least 5 data rows are needed for baseline comparison."],
        }

    baseline_window_size = min(BASELINE_WINDOW_TARGET, max(1, len(rows) // 2))
    recent_window_size = min(BASELINE_WINDOW_TARGET, len(rows) - baseline_window_size)
    if recent_window_size <= 0:
        return {
            "baseline_window_rows": baseline_window_size,
            "recent_window_rows": recent_window_size,
            "columns_analyzed": 0,
            "column_drift": [],
            "overall_assessment": "needs_review",
            "warnings": ["Not enough rows to compare separate baseline and recent windows."],
        }

    numeric_columns = {profile["column"] for profile in numeric_profiles}
    cumulative_counters = detect_cumulative_counters_from_matrix(columns, rows, numeric_columns)
    cumulative_counter_columns = {item["column"] for item in cumulative_counters}
    numeric_indexes = [index for index, column in enumerate(columns) if column in numeric_columns]
    adaptive_baseline = select_adaptive_baseline_window(rows, numeric_indexes, baseline_window_size, recent_window_size)
    baseline_rows = rows[adaptive_baseline["start_index"]:adaptive_baseline["end_index"]]
    recent_rows = rows[-recent_window_size:]
    regime_context = classify_operating_regime(rows, numeric_indexes)
    column_drift: list[dict[str, Any]] = []

    for index, column in enumerate(columns):
        if column not in numeric_columns:
            continue

        baseline_values, baseline_missing = numeric_window_values(baseline_rows, index)
        recent_values, recent_missing = numeric_window_values(recent_rows, index)
        column_warnings: list[str] = []
        informational_warnings: list[str] = []

        if baseline_missing or recent_missing:
            informational_warnings.append(f"{column} had missing samples that were skipped during baseline comparison.")
        if not baseline_values or not recent_values:
            column_warnings.append(f"{column} does not have enough numeric values for baseline comparison.")
            warnings.extend(column_warnings)
            continue

        baseline_average = sum(baseline_values) / len(baseline_values)
        recent_average = sum(recent_values) / len(recent_values)
        absolute_change = recent_average - baseline_average
        percent_change = safe_percent_change(baseline_average, absolute_change)
        direction = drift_direction(absolute_change, baseline_average)
        velocity = drift_velocity(baseline_values, recent_values)
        flag = drift_flag(percent_change, absolute_change, baseline_average)
        metric_type = "cumulative_counter" if column in cumulative_counter_columns else "operational_signal"
        analysis_role = "supporting_context" if metric_type == "cumulative_counter" else "primary_signal"
        if metric_type == "cumulative_counter":
            flag = "context"

        if variability_flag(baseline_values, baseline_average) == "high":
            column_warnings.append(f"{column} baseline window is highly variable.")
        if variability_flag(recent_values, recent_average) == "high":
            column_warnings.append(f"{column} recent window is highly variable.")
        if column_warnings:
            warnings.extend(column_warnings)

        column_drift.append(
            {
                "column": column,
                "baseline_average": round_number(baseline_average),
                "recent_average": round_number(recent_average),
                "absolute_change": round_number(absolute_change),
                "percent_change": round_number(percent_change) if percent_change is not None else None,
                "direction": direction,
                "drift_velocity": velocity["velocity"],
                "drift_acceleration": velocity["acceleration"],
                "persistence_score": persistence_score(baseline_values, recent_values, baseline_average),
                "drift_flag": flag,
                "metric_type": metric_type,
                "analysis_role": analysis_role,
                "warnings": column_warnings + informational_warnings,
            }
        )
        if metric_type == "cumulative_counter":
            delta_drift = cumulative_delta_drift(
                column=column,
                rows=rows,
                column_index=index,
                baseline_start=adaptive_baseline["start_index"],
                baseline_end=adaptive_baseline["end_index"],
                recent_window_size=recent_window_size,
            )
            if delta_drift:
                column_drift.append(delta_drift)

    if not column_drift:
        warnings.append("No numeric columns were available for baseline comparison.")

    overall_assessment = (
        "needs_review"
        if warnings or any(item["drift_flag"] == "review" for item in column_drift)
        else "normal"
    )

    return {
        "baseline_window_rows": baseline_window_size,
        "recent_window_rows": recent_window_size,
        "columns_analyzed": len(column_drift),
        "column_drift": column_drift,
        "cumulative_counters": cumulative_counters,
        "adaptive_baseline": adaptive_baseline,
        "regime_context": regime_context,
        "drift_trajectory": summarize_drift_trajectory(column_drift),
        "overall_assessment": overall_assessment,
        "warnings": warnings,
    }


def cumulative_delta_drift(
    *,
    column: str,
    rows: list[list[str]],
    column_index: int,
    baseline_start: int,
    baseline_end: int,
    recent_window_size: int,
) -> dict[str, Any] | None:
    all_values = [row[column_index] if column_index < len(row) else None for row in rows]
    deltas = counter_delta_series(all_values)
    baseline_values = [value for value in deltas[baseline_start:baseline_end] if value is not None]
    recent_values = [value for value in deltas[-recent_window_size:] if value is not None]
    if len(baseline_values) < 3 or len(recent_values) < 3:
        return None

    baseline_average = sum(baseline_values) / len(baseline_values)
    recent_average = sum(recent_values) / len(recent_values)
    absolute_change = recent_average - baseline_average
    percent_change = safe_percent_change(baseline_average, absolute_change)
    direction = drift_direction(absolute_change, baseline_average)
    velocity = drift_velocity(baseline_values, recent_values)
    return {
        "column": f"{column}_delta",
        "source_counter": column,
        "baseline_average": round_number(baseline_average),
        "recent_average": round_number(recent_average),
        "absolute_change": round_number(absolute_change),
        "percent_change": round_number(percent_change) if percent_change is not None else None,
        "direction": direction,
        "drift_velocity": velocity["velocity"],
        "drift_acceleration": velocity["acceleration"],
        "persistence_score": persistence_score(baseline_values, recent_values, baseline_average),
        "drift_flag": drift_flag(percent_change, absolute_change, baseline_average),
        "metric_type": "counter_delta",
        "analysis_role": "derived_rate_feature",
        "warnings": [f"{column} was treated as a cumulative counter; delta values were analyzed instead of the raw counter."],
    }


def numeric_window_values(rows: list[list[str]], column_index: int) -> tuple[list[float], int]:
    values: list[float] = []
    missing_count = 0
    for row in rows:
        raw_value = row[column_index].strip() if column_index < len(row) else ""
        if raw_value == "":
            missing_count += 1
            continue
        try:
            value = float(raw_value)
        except ValueError:
            missing_count += 1
            continue
        if math.isfinite(value):
            values.append(value)
        else:
            missing_count += 1
    return values, missing_count


def safe_percent_change(baseline_average: float, absolute_change: float) -> float | None:
    if abs(baseline_average) < 0.000001:
        return None
    return absolute_change / abs(baseline_average) * 100


def drift_direction(absolute_change: float, baseline_average: float) -> str:
    threshold = max(abs(baseline_average) * 0.01, 0.01)
    if absolute_change > threshold:
        return "up"
    if absolute_change < -threshold:
        return "down"
    return "flat"


def drift_flag(
    percent_change: float | None,
    absolute_change: float,
    baseline_average: float,
) -> str:
    if percent_change is None:
        return "watch" if abs(absolute_change) > 0.01 else "normal"

    magnitude = abs(percent_change)
    if magnitude >= 20:
        return "review"
    if magnitude >= 10:
        return "watch"
    if drift_direction(absolute_change, baseline_average) == "flat":
        return "normal"
    return "normal"



def select_adaptive_baseline_window(
    rows: list[list[str]],
    numeric_indexes: list[int],
    window_size: int,
    recent_window_size: int,
) -> dict[str, Any]:
    search_limit = max(window_size, len(rows) - max(1, recent_window_size))
    candidates: list[tuple[float, int]] = []
    if not numeric_indexes or window_size <= 0 or len(rows) <= window_size:
        return {
            "strategy": "position_fallback",
            "start_index": 0,
            "end_index": min(window_size, len(rows)),
            "stability_score": 0.0,
            "candidate_windows": 1 if rows else 0,
        }
    for start in range(0, max(1, search_limit - window_size + 1)):
        window = rows[start:start + window_size]
        score = window_stability_score(window, numeric_indexes)
        candidates.append((score, start))
    if not candidates:
        return {
            "strategy": "position_fallback",
            "start_index": 0,
            "end_index": window_size,
            "stability_score": 0.0,
            "candidate_windows": 0,
        }
    score, start = min(candidates, key=lambda item: item[0])
    return {
        "strategy": "lowest_variability_window",
        "start_index": start,
        "end_index": start + window_size,
        "stability_score": round_number(1 / (1 + score)),
        "candidate_windows": len(candidates),
    }


def window_stability_score(rows: list[list[str]], numeric_indexes: list[int]) -> float:
    scores: list[float] = []
    for index in numeric_indexes:
        values, _missing = numeric_window_values(rows, index)
        if len(values) < 2:
            continue
        average = sum(values) / len(values)
        variance = sum((value - average) ** 2 for value in values) / len(values)
        spread = math.sqrt(variance)
        scale = max(abs(average), 1.0)
        scores.append(spread / scale)
    return sum(scores) / len(scores) if scores else 999.0


def drift_velocity(baseline_values: list[float], recent_values: list[float]) -> dict[str, float]:
    baseline_slope = slope_for_values(baseline_values)
    recent_slope = slope_for_values(recent_values)
    return {
        "velocity": round_number(recent_slope),
        "acceleration": round_number(recent_slope - baseline_slope),
    }


def slope_for_values(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_average = (len(values) - 1) / 2
    y_average = sum(values) / len(values)
    denominator = sum((index - x_average) ** 2 for index in range(len(values)))
    if denominator == 0:
        return 0.0
    numerator = sum((index - x_average) * (value - y_average) for index, value in enumerate(values))
    return numerator / denominator


def persistence_score(baseline_values: list[float], recent_values: list[float], baseline_average: float) -> float:
    if not recent_values:
        return 0.0
    tolerance = max(abs(baseline_average) * 0.05, 0.05)
    outside = sum(1 for value in recent_values if abs(value - baseline_average) > tolerance)
    return round_number(outside / len(recent_values))


def summarize_drift_trajectory(column_drift: list[dict[str, Any]]) -> dict[str, Any]:
    active = [item for item in column_drift if item.get("drift_flag") in {"watch", "review"}]
    persistent = [item for item in active if float(item.get("persistence_score") or 0) >= 0.6]
    accelerating = [item for item in active if abs(float(item.get("drift_acceleration") or 0)) > 0.01]
    return {
        "active_columns": len(active),
        "persistent_columns": [item.get("column") for item in persistent[:6]],
        "accelerating_columns": [item.get("column") for item in accelerating[:6]],
        "trajectory_state": "accelerating" if accelerating else "persistent" if persistent else "limited",
    }


def classify_operating_regime(rows: list[list[str]], numeric_indexes: list[int]) -> dict[str, Any]:
    if len(rows) < 8 or not numeric_indexes:
        return {"regime": "unknown", "confidence": "low", "basis": "insufficient numeric history"}
    midpoint = len(rows) // 2
    early_score = window_stability_score(rows[:midpoint], numeric_indexes)
    late_score = window_stability_score(rows[midpoint:], numeric_indexes)
    if late_score > early_score * 1.5:
        return {"regime": "transition_or_recovery", "confidence": "medium", "basis": "recent variability increased versus earlier telemetry"}
    if late_score < early_score * 0.75:
        return {"regime": "stabilizing", "confidence": "medium", "basis": "recent variability compressed versus earlier telemetry"}
    return {"regime": "steady_state", "confidence": "medium", "basis": "recent and baseline variability are similar"}
