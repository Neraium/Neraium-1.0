from __future__ import annotations

import math
from typing import Any

from app.services.data_quality import parse_numeric_value, parse_timestamp


TRAJECTORY_STATES = (
    "Sudden",
    "Gradual",
    "Stable shift",
    "Strengthening",
    "Weakening",
    "Recovering",
    "Recurring",
    "Intermittent",
)


def classify_trajectory(
    *,
    persistence: float | bool = 0.0,
    rate_of_change: float = 0.0,
    corroboration_history: list[int] | None = None,
    confidence_trend: list[float] | None = None,
    evidence_spread: list[float] | None = None,
) -> str:
    """Classify evidence evolution using transparent, deterministic rules."""

    counts = [max(0, int(value)) for value in (corroboration_history or [])]
    confidence = [_bounded(value) for value in (confidence_trend or [])]
    spread = [max(0.0, float(value)) for value in (evidence_spread or [])]
    persistent = bool(persistence) if isinstance(persistence, bool) else float(persistence or 0.0) >= 0.6
    active = [value > 0 for value in counts]

    if len(active) >= 3 and active[-1] and any(not value for value in active[1:-1]) and active[0]:
        return "Recurring"
    if len(active) >= 4 and _transitions(active) >= 2:
        return "Intermittent"

    count_change = _relative_change(counts)
    spread_change = _relative_change(spread)
    confidence_change = _signed_change(confidence)
    combined_change = (count_change * 0.5) + (spread_change * 0.35) + (confidence_change * 0.15)

    if len(spread) >= 3 and spread[-1] < spread[-2] * 0.72 and spread[-2] >= spread[0] * 1.2:
        return "Recovering"
    if len(spread) >= 3:
        early = max(spread[:-1] or [0.0])
        if spread[-1] >= max(0.25, early * 1.8) and not persistent:
            return "Sudden"
        count_growth = counts[-1] - counts[0] if len(counts) >= 2 else 0
        if (
            _monotonic_non_decreasing(spread)
            and spread[-1] - spread[0] >= 0.12
            and count_growth <= 1
            and combined_change < 0.75
        ):
            return "Gradual"
    if combined_change >= 0.18 or (
        len(counts) >= 2 and counts[-1] > counts[0] and spread_change >= 0.05
    ):
        return "Strengthening"
    if combined_change <= -0.18 or (
        len(counts) >= 2 and counts[-1] < counts[0] and spread_change <= -0.05
    ):
        return "Weakening"

    if abs(float(rate_of_change or 0.0)) >= 0.35 and not persistent:
        return "Sudden"
    if persistent:
        return "Stable shift"
    return "Intermittent"


def build_change_trajectory(
    relationships: list[dict[str, Any]],
    *,
    rows: list[dict[str, Any]] | None = None,
    timestamp_column: str | None = None,
    baseline_trajectory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    relationship_history = _relationship_history(relationships, rows or [])
    counts = relationship_history["corroboration_history"]
    spread = relationship_history["evidence_spread"]
    confidence = relationship_history["confidence_trend"]
    persistence_score = _persistence_score(relationships, counts)
    rate = _trajectory_rate(spread)

    if not spread:
        fallback = str((baseline_trajectory or {}).get("trajectory_state") or "").lower()
        if fallback == "accelerating":
            spread = [0.35, 0.55]
            counts = [max(1, len(relationships) - 1), len(relationships)]
        elif fallback == "persistent":
            spread = [0.5, 0.5]
            counts = [len(relationships), len(relationships)]
            persistence_score = max(persistence_score, 0.7)

    state = classify_trajectory(
        persistence=persistence_score,
        rate_of_change=rate,
        corroboration_history=counts,
        confidence_trend=confidence,
        evidence_spread=spread,
    )
    observed = _observed_duration(rows or [], timestamp_column)
    first_count = counts[0] if counts else len(relationships)
    last_count = counts[-1] if counts else len(relationships)
    corroboration_change = (
        f"Corroboration increased from {first_count} to {last_count} relationships"
        if last_count > first_count
        else f"Corroboration decreased from {first_count} to {last_count} relationships"
        if last_count < first_count
        else f"Corroboration remained at {last_count} relationship{'s' if last_count != 1 else ''}"
    )
    evidence = [
        f"Persistence score {persistence_score:.2f}.",
        f"Evidence-spread rate {rate:+.2f} across comparable recent windows.",
        f"{corroboration_change}.",
    ]
    if confidence:
        evidence.append(
            f"Evidence confidence moved from {confidence[0]:.2f} to {confidence[-1]:.2f}."
        )
    return {
        "state": state,
        "label": state,
        "observed_for": observed["label"],
        "observed_for_days": observed["days"],
        "persistence": round(persistence_score, 4),
        "rate_of_change": round(rate, 4),
        "corroboration_history": counts,
        "corroboration_change": corroboration_change,
        "confidence_trend": [round(value, 4) for value in confidence],
        "evidence_spread": [round(value, 4) for value in spread],
        "evidence": evidence,
        "rule_version": "deterministic_condition_trajectory_v1",
    }


def _relationship_history(
    relationships: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, list[Any]]:
    if len(rows) < 18 or not relationships:
        return {
            "corroboration_history": [],
            "confidence_trend": [],
            "evidence_spread": [],
        }

    baseline_end = max(6, min(len(rows) - 9, int(len(rows) * 0.55)))
    recent = rows[baseline_end:]
    window_count = min(4, max(3, len(recent) // 3))
    window_size = len(recent) // window_count
    if window_size < 3:
        return {
            "corroboration_history": [],
            "confidence_trend": [],
            "evidence_spread": [],
        }

    histories: list[tuple[dict[str, Any], list[tuple[float, float]]]] = []
    for relationship in relationships:
        columns = _relationship_columns(relationship)
        if len(columns) < 2:
            continue
        baseline_correlation = _number(relationship.get("baseline_correlation"))
        if baseline_correlation is None:
            baseline_correlation = _correlation(rows[:baseline_end], columns[0], columns[1])
        if baseline_correlation is None:
            continue
        points: list[tuple[float, float]] = []
        for index in range(window_count):
            start = index * window_size
            end = len(recent) if index == window_count - 1 else (index + 1) * window_size
            window = recent[start:end]
            current = _correlation(window, columns[0], columns[1])
            if current is None:
                points.append((0.0, 0.0))
                continue
            delta = abs(current - baseline_correlation)
            confidence = min(1.0, (len(window) / 12.0) * 0.55 + min(1.0, delta) * 0.45)
            points.append((delta, confidence))
        histories.append((relationship, points))

    if not histories:
        return {
            "corroboration_history": [],
            "confidence_trend": [],
            "evidence_spread": [],
        }

    corroboration_history: list[int] = []
    confidence_trend: list[float] = []
    evidence_spread: list[float] = []
    for window_index in range(len(histories[0][1])):
        deltas = [history[window_index][0] for _, history in histories]
        confidences = [history[window_index][1] for _, history in histories]
        active = [
            index
            for index, ((relationship, _), delta) in enumerate(zip(histories, deltas))
            if delta >= _activity_threshold(relationship)
        ]
        corroboration_history.append(len(active))
        evidence_spread.append(sum(deltas) / len(deltas))
        confidence_trend.append(
            sum(confidences[index] for index in active) / len(active) if active else 0.0
        )
    return {
        "corroboration_history": corroboration_history,
        "confidence_trend": confidence_trend,
        "evidence_spread": evidence_spread,
    }


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


def _activity_threshold(relationship: dict[str, Any]) -> float:
    observed = abs(float(relationship.get("correlation_delta") or 0.0))
    return max(0.18, min(0.45, observed * 0.55))


def _persistence_score(relationships: list[dict[str, Any]], counts: list[int]) -> float:
    explicit = [
        _bounded(item.get("persistence_score"))
        for item in relationships
        if item.get("persistence_score") is not None
    ]
    if explicit:
        return sum(explicit) / len(explicit)
    if counts:
        active_windows = sum(1 for value in counts if value > 0)
        return active_windows / len(counts)
    return 0.65 if relationships and all(int(item.get("recent_sample_size") or 0) >= 6 for item in relationships) else 0.35


def _trajectory_rate(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    denominator = max(abs(values[0]), 0.1)
    return max(-2.0, min(2.0, (values[-1] - values[0]) / denominator))


def _observed_duration(rows: list[dict[str, Any]], timestamp_column: str | None) -> dict[str, Any]:
    if not timestamp_column or len(rows) < 2:
        return {"label": "Available comparison window", "days": None}
    start_index = max(0, int(len(rows) * 0.55))
    start_raw = rows[start_index].get(timestamp_column)
    end_raw = rows[-1].get(timestamp_column)
    start = parse_timestamp(str(start_raw)) if start_raw is not None else None
    end = parse_timestamp(str(end_raw)) if end_raw is not None else None
    if not start or not end or end <= start:
        return {"label": "Available comparison window", "days": None}
    seconds = (end - start).total_seconds()
    days = max(1, int(round(seconds / 86400)))
    if seconds < 86400:
        hours = max(1, int(round(seconds / 3600)))
        return {"label": f"Observed for {hours} hour{'s' if hours != 1 else ''}", "days": round(seconds / 86400, 3)}
    return {"label": f"Observed for {days} day{'s' if days != 1 else ''}", "days": days}


def _transitions(values: list[bool]) -> int:
    return sum(1 for left, right in zip(values, values[1:]) if left != right)


def _relative_change(values: list[float | int]) -> float:
    if len(values) < 2:
        return 0.0
    denominator = max(abs(float(values[0])), 1.0 if isinstance(values[0], int) else 0.1)
    return (float(values[-1]) - float(values[0])) / denominator


def _signed_change(values: list[float]) -> float:
    return values[-1] - values[0] if len(values) >= 2 else 0.0


def _monotonic_non_decreasing(values: list[float]) -> bool:
    return all(right >= left - 0.02 for left, right in zip(values, values[1:]))


def _bounded(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if numeric > 1.0 and numeric <= 100.0:
        numeric /= 100.0
    return max(0.0, min(1.0, numeric))


def _number(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None
