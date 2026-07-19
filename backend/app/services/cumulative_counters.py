from __future__ import annotations

import math
import re
from typing import Any


CUMULATIVE_COUNTER_PATTERN = re.compile(
    r"(^|[_\s-])(cumulative|totalizer|totalized|total|counter|meter|odometer|accum|accumulated|usage|consumption)([_\s-]|$)"
)


def is_cumulative_counter_name(column: str) -> bool:
    text = str(column or "").strip().lower()
    if not text:
        return False
    if "rate" in text or text.endswith(("_delta", "_diff", "_change", "_per_min", "_per_hour")):
        return False
    return bool(CUMULATIVE_COUNTER_PATTERN.search(text))


def numeric_series(values: list[Any]) -> list[float]:
    parsed: list[float] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip().replace(",", "").replace("%", "")
        if text == "":
            continue
        try:
            number = float(text)
        except ValueError:
            continue
        if math.isfinite(number):
            parsed.append(number)
    return parsed


def is_monotonic_counter_series(values: list[Any], *, min_samples: int = 8) -> bool:
    series = numeric_series(values)
    if len(series) < min_samples:
        return False
    deltas = [right - left for left, right in zip(series, series[1:])]
    if not deltas:
        return False
    positive_or_flat = sum(1 for delta in deltas if delta >= -1e-9)
    positive = sum(1 for delta in deltas if delta > 1e-9)
    net_change = series[-1] - series[0]
    return (
        net_change > 0
        and positive > 0
        and positive_or_flat / len(deltas) >= 0.98
        and len(set(round(value, 9) for value in series)) > 1
    )


def is_cumulative_counter(column: str, values: list[Any]) -> bool:
    return is_cumulative_counter_name(column) and is_monotonic_counter_series(values)


def counter_delta_series(values: list[Any]) -> list[float | None]:
    series = [None if value is None or str(value).strip() == "" else _to_float(value) for value in values]
    deltas: list[float | None] = [None]
    for previous, current in zip(series, series[1:]):
        if previous is None or current is None:
            deltas.append(None)
            continue
        delta = current - previous
        deltas.append(delta if delta >= 0 else None)
    return deltas


def detect_cumulative_counters_from_matrix(columns: list[str], rows: list[list[Any]], numeric_columns: set[str]) -> list[dict[str, Any]]:
    detected: list[dict[str, Any]] = []
    for index, column in enumerate(columns):
        if column not in numeric_columns:
            continue
        values = [row[index] if index < len(row) else None for row in rows]
        if is_cumulative_counter(column, values):
            deltas = [value for value in counter_delta_series(values) if value is not None]
            detected.append(
                {
                    "column": column,
                    "reason": "name_and_monotonic_increase",
                    "derived_rate_feature": f"{column}_delta",
                    "samples": len(numeric_series(values)),
                    "delta_samples": len(deltas),
                }
            )
    return detected


def detect_cumulative_counters_from_rows(rows: list[dict[str, Any]], numeric_columns: list[str]) -> list[dict[str, Any]]:
    detected: list[dict[str, Any]] = []
    for column in numeric_columns:
        values = [row.get(column) for row in rows]
        if is_cumulative_counter(column, values):
            deltas = [value for value in counter_delta_series(values) if value is not None]
            detected.append(
                {
                    "column": column,
                    "reason": "name_and_monotonic_increase",
                    "derived_rate_feature": f"{column}_delta",
                    "samples": len(numeric_series(values)),
                    "delta_samples": len(deltas),
                }
            )
    return detected


def _to_float(value: Any) -> float | None:
    try:
        number = float(str(value).strip().replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
