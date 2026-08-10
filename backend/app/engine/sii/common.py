from __future__ import annotations

import math
import time
from datetime import datetime
from statistics import median
from typing import Any, Iterable

from app.services.data_quality import parse_numeric_value, parse_timestamp

EPSILON = 1e-12


class NumericRowCache:
    """Per-analysis cache for deterministic numeric projections of row subsets."""

    def __init__(self) -> None:
        self._datasets: dict[int, tuple[list[dict[str, Any]], dict[str, list[float | None]]]] = {}
        self.hits = 0

    def column(self, rows: list[dict[str, Any]], column: str) -> list[float | None]:
        identity = id(rows)
        cached_dataset = self._datasets.get(identity)
        if cached_dataset is None or cached_dataset[0] is not rows:
            cached_dataset = (rows, {})
            self._datasets[identity] = cached_dataset
        columns = cached_dataset[1]
        values = columns.get(column)
        if values is not None:
            self.hits += 1
            return values
        values = [finite_number(row.get(column)) for row in rows]
        columns[column] = values
        return values


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def finite_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        number = parse_numeric_value(str(value))
    return number if number is not None and math.isfinite(number) else None


def numeric_values(
    rows: list[dict[str, Any]],
    column: str,
    *,
    cache: NumericRowCache | None = None,
) -> list[float]:
    if cache is not None:
        return [number for number in cache.column(rows, column) if number is not None]
    return [number for row in rows if (number := finite_number(row.get(column))) is not None]


def paired_values(
    rows: list[dict[str, Any]],
    left: str,
    right: str,
    *,
    cache: NumericRowCache | None = None,
) -> list[tuple[float, float]]:
    if cache is not None:
        return [
            (left_value, right_value)
            for left_value, right_value in zip(
                cache.column(rows, left),
                cache.column(rows, right),
            )
            if left_value is not None and right_value is not None
        ]
    pairs: list[tuple[float, float]] = []
    for row in rows:
        left_value = finite_number(row.get(left))
        right_value = finite_number(row.get(right))
        if left_value is not None and right_value is not None:
            pairs.append((left_value, right_value))
    return pairs


def pearson(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    left = [pair[0] for pair in pairs]
    right = [pair[1] for pair in pairs]
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    denominator = math.sqrt(sum(value * value for value in left_centered)) * math.sqrt(
        sum(value * value for value in right_centered)
    )
    if denominator <= EPSILON:
        return None
    return clamp(
        sum(left_value * right_value for left_value, right_value in zip(left_centered, right_centered))
        / denominator,
        -1.0,
        1.0,
    )


def median_absolute_deviation(values: list[float]) -> float:
    if not values:
        return 0.0
    center = median(values)
    return float(median(abs(value - center) for value in values))


def quantile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    position = clamp(fraction) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def parse_timestamps(rows: list[dict[str, Any]], timestamp_column: str | None) -> list[datetime | None]:
    if not timestamp_column:
        return [None for _ in rows]
    output: list[datetime | None] = []
    for row in rows:
        raw = row.get(timestamp_column)
        output.append(parse_timestamp(str(raw)) if raw is not None else None)
    return output


def timestamp_statistics(rows: list[dict[str, Any]], timestamp_column: str | None) -> dict[str, Any]:
    parsed = parse_timestamps(rows, timestamp_column)
    valid = [value for value in parsed if value is not None]
    intervals = [
        (current - previous).total_seconds()
        for previous, current in zip(valid, valid[1:])
        if (current - previous).total_seconds() > 0
    ]
    coverage = len(valid) / max(1, len(rows))
    positive_interval_coverage = len(intervals) / max(1, len(valid) - 1)
    median_interval = float(median(intervals)) if intervals else None
    interval_mad = median_absolute_deviation(intervals) if intervals else None
    interval_variability = (
        float(interval_mad) / max(float(median_interval), EPSILON)
        if median_interval is not None and interval_mad is not None
        else None
    )
    regularity = (
        clamp(coverage * positive_interval_coverage * (1.0 - clamp(interval_variability or 0.0)))
        if intervals
        else 0.0
    )
    return {
        "parsed": parsed,
        "coverage": round(coverage, 6),
        "median_interval_seconds": round(median_interval, 6) if median_interval is not None else None,
        "interval_mad_seconds": round(interval_mad, 6) if interval_mad is not None else None,
        "interval_variability": round(interval_variability, 6) if interval_variability is not None else None,
        "regularity": round(regularity, 6),
        "reliable": bool(coverage >= 0.9 and regularity >= 0.8 and median_interval is not None),
    }


def relationship_columns(edge: dict[str, Any]) -> list[str]:
    pairs = edge.get("supporting_metric_pairs")
    if isinstance(pairs, list) and pairs and isinstance(pairs[0], dict):
        columns = [pairs[0].get("left"), pairs[0].get("right")]
        clean = [str(column) for column in columns if column]
        if len(clean) == 2:
            return clean
    explicit_columns = edge.get("columns")
    if isinstance(explicit_columns, list):
        clean = [str(column) for column in explicit_columns if column]
        if len(clean) == 2:
            return clean
    relationship = str(edge.get("relationship") or "")
    if "<->" in relationship:
        return [part.strip() for part in relationship.split("<->", 1) if part.strip()]
    source = str(edge.get("source") or "").removeprefix("metric:")
    target = str(edge.get("target") or "").removeprefix("metric:")
    return [column for column in (source, target) if column]


def confidence_number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"high", "strong"}:
            return 1.0
        if normalized in {"moderate", "usable", "partial"}:
            return 0.7
        if normalized in {"limited", "weak"}:
            return 0.45
        if normalized in {"low", "unavailable", "not_reliable"}:
            return 0.25
    number = finite_number(value)
    if number is None:
        return clamp(default)
    if number > 1.0 and number <= 100.0:
        number /= 100.0
    return clamp(number)


def module_envelope(
    *,
    started: float,
    status: str,
    reason: str | None,
    inputs_used: Iterable[str],
    rows_used: int,
    columns_used: Iterable[str],
    assumptions: Iterable[str],
    output_metrics: dict[str, Any],
    limitations: Iterable[str],
) -> dict[str, Any]:
    result = {
        "status": status,
        "inputs_used": list(dict.fromkeys(str(item) for item in inputs_used if str(item))),
        "rows_used": max(0, int(rows_used)),
        "columns_used": list(dict.fromkeys(str(item) for item in columns_used if str(item))),
        "assumptions": list(dict.fromkeys(str(item) for item in assumptions if str(item))),
        "output_metrics": output_metrics,
        "limitations": list(dict.fromkeys(str(item) for item in limitations if str(item))),
        "runtime_seconds": round(max(0.0, time.perf_counter() - started), 6),
    }
    if reason:
        result["reason"] = str(reason)
    return result


def failed_module_result(
    exc: Exception,
    *,
    inputs_used: Iterable[str],
    rows_used: int,
    columns_used: Iterable[str],
    started: float,
) -> dict[str, Any]:
    reason = f"{type(exc).__name__}: {exc}"
    return module_envelope(
        started=started,
        status="failed",
        reason=reason,
        inputs_used=inputs_used,
        rows_used=rows_used,
        columns_used=columns_used,
        assumptions=[],
        output_metrics={},
        limitations=[reason],
    )
