from __future__ import annotations

import math
from typing import Any

from app.services.data_quality import parse_numeric_value, parse_timestamp
from app.services.operating_modes import (
    context_signals,
    describe_mode,
    numeric_band_references,
)
from app.services.telemetry_classification import signal_display_name


class ComparableHistoricalEpisodeService:
    """Retrieve like-for-like historical windows using observed operating context."""

    def retrieve(
        self,
        *,
        rows: list[dict[str, Any]],
        relationship: dict[str, Any],
        timestamp_column: str | None = None,
        telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
        max_periods: int = 48,
    ) -> dict[str, Any]:
        columns = _relationship_columns(relationship)
        if len(rows) < 18 or len(columns) < 2:
            return unavailable_comparison(
                "Comparable operation requires at least 18 rows and a telemetry-supported signal pair."
            )

        period_size = max(6, min(24, len(rows) // 20))
        if len(rows) < period_size * 3:
            return unavailable_comparison(
                "The uploaded history did not contain enough separate windows for like-for-like comparison."
            )

        signals = context_signals(rows, timestamp_column, telemetry_signal_catalog)
        references = numeric_band_references(rows, signals)
        current_rows = rows[-period_size:]
        current_mode = describe_mode(current_rows, signals, references, timestamp_column)
        comparison_dimensions = _comparison_dimensions(current_mode)
        if not comparison_dimensions:
            return unavailable_comparison(
                "No time, staging, pump-count, weather, occupancy, load, or operating-mode evidence was available."
            )

        historical_rows = rows[:-period_size]
        periods: list[dict[str, Any]] = []
        for start in range(0, len(historical_rows) - period_size + 1, period_size):
            window = historical_rows[start : start + period_size]
            mode = describe_mode(window, signals, references, timestamp_column)
            matching, conflicts = _mode_match(current_mode, mode, comparison_dimensions)
            if conflicts or not matching:
                continue
            correlation = _correlation(window, columns[0], columns[1])
            if correlation is None:
                continue
            periods.append(
                {
                    "start": _timestamp(window[0], timestamp_column),
                    "end": _timestamp(window[-1], timestamp_column),
                    "sample_count": len(window),
                    "relationship_strength": round(correlation, 6),
                    "matching_dimensions": matching,
                }
            )
            if len(periods) >= max(1, max_periods):
                break

        current_correlation = _correlation(current_rows, columns[0], columns[1])
        if not periods or current_correlation is None:
            return unavailable_comparison(
                "No historical windows matched the observed operating context with enough paired samples.",
                matching_dimensions=comparison_dimensions,
            )

        correlations = sorted(float(period["relationship_strength"]) for period in periods)
        normal_correlation = _percentile(correlations, 0.5)
        left_label = signal_display_name(columns[0], telemetry_signal_catalog)
        right_label = signal_display_name(columns[1], telemetry_signal_catalog)
        normal_behavior = _behavior_sentence(
            left_label,
            right_label,
            normal_correlation,
            prefix="During comparable operation",
        )
        current_behavior = _current_sentence(
            left_label,
            right_label,
            normal_correlation,
            current_correlation,
        )
        return {
            "status": "supported",
            "period_count": len(periods),
            "comparable_period_count": len(periods),
            "period_size_rows": period_size,
            "matching_dimensions": [
                {"dimension": key, "value": current_mode["features"].get(key)}
                for key in comparison_dimensions
            ],
            "normal_behavior": normal_behavior,
            "current_behavior": current_behavior,
            "normal_relationship_strength": round(normal_correlation, 6),
            "current_relationship_strength": round(current_correlation, 6),
            "relationship": {
                "signals": columns,
                "display_signals": [left_label, right_label],
            },
            "evidence_summary": (
                f"{len(periods)} historical period{'s' if len(periods) != 1 else ''} matched "
                f"{', '.join(_human_dimension(value) for value in comparison_dimensions)}."
            ),
            "periods": periods,
            "supports_existing_baseline": True,
            "rule_version": "deterministic_comparable_operation_v1",
        }


def unavailable_comparison(
    reason: str,
    *,
    matching_dimensions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "period_count": 0,
        "comparable_period_count": 0,
        "matching_dimensions": matching_dimensions or [],
        "normal_behavior": "",
        "current_behavior": "",
        "evidence_summary": reason,
        "periods": [],
        "supports_existing_baseline": True,
        "rule_version": "deterministic_comparable_operation_v1",
    }


def _comparison_dimensions(mode: dict[str, Any]) -> list[str]:
    features = mode.get("features") if isinstance(mode.get("features"), dict) else {}
    preferred = [
        "time_band",
        "week_band",
        "active_unit_count",
        "equipment_state",
        "speed_band",
        "outdoor_air_band",
        "schedule_state",
        "load_band",
        "setpoint",
        "maintenance_state",
        "cleaning_cycle",
        "special_event",
    ]
    return [key for key in preferred if key in features and features.get(key) is not None]


def _mode_match(
    current: dict[str, Any],
    historical: dict[str, Any],
    dimensions: list[str],
) -> tuple[list[str], list[str]]:
    current_features = current.get("features") if isinstance(current.get("features"), dict) else {}
    historical_features = historical.get("features") if isinstance(historical.get("features"), dict) else {}
    matching: list[str] = []
    conflicts: list[str] = []
    for key in dimensions:
        if key not in historical_features:
            conflicts.append(key)
        elif historical_features.get(key) == current_features.get(key):
            matching.append(key)
        else:
            conflicts.append(key)
    return matching, conflicts


def _relationship_columns(item: dict[str, Any]) -> list[str]:
    columns = [str(value) for value in item.get("columns", []) if value]
    if len(columns) >= 2:
        return columns[:2]
    pairs = item.get("supporting_metric_pairs")
    if isinstance(pairs, list) and pairs and isinstance(pairs[0], dict):
        columns = [str(pairs[0].get("left") or ""), str(pairs[0].get("right") or "")]
    if len([value for value in columns if value]) >= 2:
        return [value for value in columns if value][:2]
    source = str(item.get("source") or "").removeprefix("metric:").removeprefix("tag:")
    target = str(item.get("target") or "").removeprefix("metric:").removeprefix("tag:")
    return [value for value in (source, target) if value]


def _correlation(rows: list[dict[str, Any]], left: str, right: str) -> float | None:
    pairs: list[tuple[float, float]] = []
    for row in rows:
        left_value = parse_numeric_value(str(row.get(left))) if row.get(left) is not None else None
        right_value = parse_numeric_value(str(row.get(right))) if row.get(right) is not None else None
        if left_value is not None and right_value is not None:
            pairs.append((left_value, right_value))
    if len(pairs) < 3:
        return None
    left_mean = sum(pair[0] for pair in pairs) / len(pairs)
    right_mean = sum(pair[1] for pair in pairs) / len(pairs)
    numerator = sum((left_value - left_mean) * (right_value - right_mean) for left_value, right_value in pairs)
    left_variance = sum((left_value - left_mean) ** 2 for left_value, _ in pairs)
    right_variance = sum((right_value - right_mean) ** 2 for _, right_value in pairs)
    denominator = math.sqrt(left_variance * right_variance)
    if denominator <= 0:
        return None
    return numerator / denominator


def _timestamp(row: dict[str, Any], timestamp_column: str | None) -> str:
    if not timestamp_column:
        return ""
    raw = row.get(timestamp_column)
    parsed = parse_timestamp(str(raw)) if raw is not None else None
    return parsed.isoformat() if parsed else str(row.get(timestamp_column) or "")


def _behavior_sentence(left: str, right: str, correlation: float, *, prefix: str) -> str:
    if correlation >= 0.45:
        behavior = f"{left} and {right} normally moved together"
    elif correlation <= -0.45:
        behavior = f"{left} and {right} normally moved in opposite directions"
    else:
        behavior = f"{left} and {right} normally had a weak linear relationship"
    return f"{prefix}, {behavior}."


def _current_sentence(left: str, right: str, normal: float, current: float) -> str:
    normal_strength = abs(normal)
    current_strength = abs(current)
    if normal * current < 0:
        return f"Current behavior: the {left} / {right} relationship reversed direction."
    if current_strength < normal_strength - 0.2:
        return f"Current behavior: the {left} / {right} relationship weakened."
    if current_strength > normal_strength + 0.2:
        return f"Current behavior: the {left} / {right} relationship strengthened."
    return f"Current behavior: the {left} / {right} relationship remained near comparable operation."


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(len(values) - 1, lower + 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _human_dimension(value: str) -> str:
    labels = {
        "active_unit_count": "equipment staging",
        "outdoor_air_band": "weather band",
        "schedule_state": "occupancy band",
        "equipment_state": "operating mode",
    }
    return labels.get(value, value.replace("_", " "))
