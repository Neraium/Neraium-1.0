import math
from typing import Any

from app.services.data_quality import round_number, variability_flag

BASELINE_WINDOW_FRACTION = 0.2
MIN_BASELINE_ROWS = 5


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

    window_size = max(1, math.ceil(len(rows) * BASELINE_WINDOW_FRACTION))
    if window_size * 2 > len(rows):
        return {
            "baseline_window_rows": window_size,
            "recent_window_rows": window_size,
            "columns_analyzed": 0,
            "column_drift": [],
            "overall_assessment": "needs_review",
            "warnings": ["Not enough rows to compare separate baseline and recent windows."],
        }

    baseline_rows = rows[:window_size]
    recent_rows = rows[-window_size:]
    numeric_columns = {profile["column"] for profile in numeric_profiles}
    column_drift: list[dict[str, Any]] = []

    for index, column in enumerate(columns):
        if column not in numeric_columns:
            continue

        baseline_values, baseline_missing = numeric_window_values(baseline_rows, index)
        recent_values, recent_missing = numeric_window_values(recent_rows, index)
        column_warnings: list[str] = []

        if baseline_missing or recent_missing:
            column_warnings.append(f"{column} has missing values in baseline or recent windows.")
        if not baseline_values or not recent_values:
            column_warnings.append(f"{column} does not have enough numeric values for baseline comparison.")
            warnings.extend(column_warnings)
            continue

        baseline_average = sum(baseline_values) / len(baseline_values)
        recent_average = sum(recent_values) / len(recent_values)
        absolute_change = recent_average - baseline_average
        percent_change = safe_percent_change(baseline_average, absolute_change)
        direction = drift_direction(absolute_change, baseline_average)
        flag = drift_flag(percent_change, absolute_change, baseline_average)

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
                "drift_flag": flag,
                "warnings": column_warnings,
            }
        )

    if not column_drift:
        warnings.append("No numeric columns were available for baseline comparison.")

    overall_assessment = (
        "needs_review"
        if warnings or any(item["drift_flag"] == "review" for item in column_drift)
        else "normal"
    )

    return {
        "baseline_window_rows": window_size,
        "recent_window_rows": window_size,
        "columns_analyzed": len(column_drift),
        "column_drift": column_drift,
        "overall_assessment": overall_assessment,
        "warnings": warnings,
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
