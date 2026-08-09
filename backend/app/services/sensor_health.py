from __future__ import annotations

import math
import re
from statistics import median
from typing import Any

from app.services.data_quality import parse_numeric_value
from app.services.telemetry_classification import signal_classification, telemetry_catalog_by_column


_SUSPECT_CONDITIONS = {
    "flatline_or_stuck",
    "possible_drift",
    "timestamp_misalignment",
    "invalid_range",
}


def assess_sensor_health(
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    *,
    timestamp_column: str | None = None,
    numeric_profiles: list[dict[str, Any]] | None = None,
    normalization_report: dict[str, Any] | None = None,
    ingestion_report: dict[str, Any] | None = None,
    timestamp_profile: dict[str, Any] | None = None,
    relationship_model: dict[str, Any] | None = None,
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Extend existing quality evidence into qualitative signal-health conditions."""

    assessment_rows = bounded_assessment_rows(rows)
    numeric_profiles = numeric_profiles or []
    normalization_report = normalization_report or {}
    ingestion_report = ingestion_report or {}
    timestamp_profile = timestamp_profile or {}
    catalog = telemetry_catalog_by_column(telemetry_signal_catalog)
    profile_by_column = {
        str(item.get("column")): item
        for item in numeric_profiles
        if isinstance(item, dict) and item.get("column")
    }
    integrity_by_signal = {
        str(item.get("signal_id")): item
        for item in normalization_report.get("signal_integrity", [])
        if isinstance(item, dict) and item.get("signal_id")
    }
    condition_map: dict[str, list[dict[str, str]]] = {str(column): [] for column in numeric_columns}
    total_checks = len(numeric_columns) + 3
    completed_checks = 0
    if progress_callback:
        progress_callback(completed_checks, total_checks)

    for column in numeric_columns:
        profile = profile_by_column.get(column, {})
        integrity = integrity_by_signal.get(column, {})
        classification = signal_classification(column, catalog)
        values = numeric_series(assessment_rows, column)
        state_signal = bool(classification.get("is_state_signal"))

        if profile.get("constant_or_stuck") and not state_signal:
            add_condition(
                condition_map,
                column,
                "flatline_or_stuck",
                "review",
                "The signal remained at one numeric value across the available analysis rows.",
            )
        if profile.get("non_numeric_count"):
            add_condition(
                condition_map,
                column,
                "invalid_values",
                "limitation",
                f"{profile.get('non_numeric_count')} non-numeric value(s) were excluded from this signal.",
            )
        if profile.get("range_warning"):
            range_evidence = str(profile["range_warning"])
            defensible_range = any(
                token in range_evidence.lower()
                for token in ("humidity values fall outside", "ph values fall outside")
            )
            add_condition(
                condition_map,
                column,
                "invalid_range" if defensible_range else "unusual_range",
                "review" if defensible_range else "limitation",
                range_evidence,
            )

        gap_type = str(integrity.get("gap_type") or "")
        if gap_type == "short_drop":
            add_condition(
                condition_map,
                column,
                "intermittent_dropout",
                "limitation",
                "Short telemetry gaps were filled by the existing normalization layer.",
            )
        elif gap_type in {"sustained", "terminal", "correlated"}:
            add_condition(
                condition_map,
                column,
                "missing_values",
                "review",
                f"The existing integrity profile marked {gap_type} missing telemetry.",
            )
        completeness = number(integrity.get("completeness"))
        if completeness is not None and completeness < 0.8:
            add_condition(
                condition_map,
                column,
                "sparse_baseline_coverage",
                "review",
                "Available samples fell below the existing telemetry completeness floor.",
            )

        repeated = longest_repeated_run(values)
        if not state_signal and len(values) >= 8 and len(set(values)) > 1 and repeated >= max(8, int(len(values) * 0.5)):
            add_condition(
                condition_map,
                column,
                "frozen_precision",
                "limitation",
                f"The same numeric value repeated for {repeated} consecutive readings before changing.",
            )
        if not state_signal and abrupt_step_evidence(values):
            add_condition(
                condition_map,
                column,
                "abrupt_step_change",
                "limitation",
                "An abrupt level step was large relative to this signal's own typical adjacent movement; calibration history should be checked.",
            )
        completed_checks += 1
        if progress_callback:
            progress_callback(completed_checks, total_checks)

    add_peer_drift_conditions(assessment_rows, relationship_model or {}, condition_map)
    completed_checks += 1
    if progress_callback:
        progress_callback(completed_checks, total_checks)
    add_timestamp_alignment_conditions(assessment_rows, relationship_model or {}, condition_map)
    completed_checks += 1
    if progress_callback:
        progress_callback(completed_checks, total_checks)
    source_conditions = source_health_conditions(
        ingestion_report=ingestion_report,
        timestamp_profile=timestamp_profile,
        timestamp_column=timestamp_column,
    )
    completed_checks += 1
    if progress_callback:
        progress_callback(completed_checks, total_checks)
    signals = [
        {
            "signal": column,
            "health": health_from_conditions(condition_map[column]),
            "conditions": condition_map[column],
        }
        for column in numeric_columns
    ]
    return {
        "signals": signals,
        "source_conditions": source_conditions,
        "population_rows": len(rows),
        "assessed_rows": len(assessment_rows),
        "sampled_for_signal_health": len(assessment_rows) < len(rows),
        "assessment_method": "deterministic_signal_health_v1",
    }


def build_data_confidence(
    data_quality: dict[str, Any],
    sensor_health: dict[str, Any],
    *,
    affected_signals: list[str] | None = None,
) -> dict[str, Any]:
    """Apply a qualitative certainty ceiling using existing reliability evidence."""

    profiles = [
        item
        for item in sensor_health.get("signals", [])
        if isinstance(item, dict)
        and (not affected_signals or str(item.get("signal")) in set(affected_signals))
    ]
    source_conditions = [
        item for item in sensor_health.get("source_conditions", []) if isinstance(item, dict)
    ]
    reasons: list[str] = []
    affected: list[str] = []
    rating = "high"
    reliability = str(data_quality.get("reliability_rating") or "").lower()
    quality_metrics = data_quality.get("quality_metrics") if isinstance(data_quality.get("quality_metrics"), dict) else {}
    normalization = data_quality.get("normalization_report") if isinstance(data_quality.get("normalization_report"), dict) else {}

    if (
        data_quality.get("readiness") == "not_ready"
        or reliability == "not_reliable"
        or normalization.get("window_suppressed")
        or quality_metrics.get("baseline_reliable") is False
    ):
        rating = "low"
        reasons.append("Existing data-quality gates do not support a reliable interpretation of this window.")
    elif reliability in {"weak", "usable"}:
        rating = "limited"
        reasons.append(f"The existing telemetry reliability rating is {reliability}.")

    if source_conditions:
        rating = lower_rating(rating, "limited")
        reasons.extend(str(item.get("evidence")) for item in source_conditions if item.get("evidence"))

    for profile in profiles:
        conditions = profile.get("conditions") if isinstance(profile.get("conditions"), list) else []
        if not conditions:
            continue
        signal = str(profile.get("signal") or "")
        if signal:
            affected.append(signal)
        if any(item.get("type") == "sparse_baseline_coverage" for item in conditions if isinstance(item, dict)):
            rating = "low"
        else:
            rating = lower_rating(rating, "limited")
        reasons.extend(
            str(item.get("evidence"))
            for item in conditions
            if isinstance(item, dict) and item.get("evidence")
        )

    if not profiles and affected_signals:
        rating = "low"
        reasons.append("No signal-health profile was available for the signals supporting this finding.")
    if rating == "high":
        summary = "Available telemetry passed the current completeness, timestamp, and signal-health checks."
    elif rating == "limited":
        summary = "The telemetry is usable, but identified signal or source conditions limit finding certainty."
    else:
        summary = "The available telemetry does not support a reliable physical-system interpretation."
    return {
        "rating": rating,
        "summary": summary,
        "reasons": dedupe(reasons),
        "affected_signals": sorted(set(affected)),
    }


def apply_sensor_health_context(
    relationship_model: dict[str, Any],
    *,
    sensor_health: dict[str, Any],
    data_quality: dict[str, Any],
) -> dict[str, Any]:
    """Attach relevant health and confidence while preserving relationship math."""

    model = dict(relationship_model or {})
    model["sensor_health"] = sensor_health
    model["data_confidence"] = build_data_confidence(data_quality, sensor_health)

    def enrich(item: Any) -> Any:
        if not isinstance(item, dict):
            return item
        columns = relationship_columns(item)
        relevant = relevant_signal_health(sensor_health, columns)
        return {
            **item,
            "sensor_health": relevant,
            "data_confidence": build_data_confidence(
                data_quality,
                sensor_health,
                affected_signals=columns,
            ),
        }

    for key in ("top_relationship_changes", "baseline_relationships"):
        if isinstance(model.get(key), list):
            model[key] = [enrich(item) for item in model[key]]
    graph = model.get("relationship_graph")
    if isinstance(graph, dict):
        graph = dict(graph)
        for key in (
            "edges",
            "changed_edges",
            "weakened_relationships",
            "strengthened_relationships",
            "new_relationships",
            "missing_relationships",
            "disrupted_relationships",
        ):
            if isinstance(graph.get(key), list):
                graph[key] = [enrich(item) for item in graph[key]]
        model["relationship_graph"] = graph
    return model


def relevant_signal_health(sensor_health: dict[str, Any], signals: list[str]) -> list[dict[str, Any]]:
    wanted = set(signals)
    return [
        item
        for item in sensor_health.get("signals", [])
        if isinstance(item, dict) and str(item.get("signal")) in wanted
    ]


def bounded_assessment_rows(
    rows: list[dict[str, Any]],
    *,
    baseline_limit: int = 4200,
    recent_limit: int = 1800,
) -> list[dict[str, Any]]:
    """Bound statistical diagnostics while retaining both comparison periods."""

    if len(rows) <= baseline_limit + recent_limit:
        return rows
    split = max(1, min(len(rows) - 1, int(len(rows) * 0.7)))
    baseline = evenly_spaced_rows(rows[:split], baseline_limit)
    recent = evenly_spaced_rows(rows[split:], recent_limit)
    return [*baseline, *recent]


def evenly_spaced_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return rows
    if limit <= 1:
        return rows[-1:]
    last = len(rows) - 1
    indexes = [int(round(index * last / (limit - 1))) for index in range(limit)]
    return [rows[index] for index in indexes]


def add_peer_drift_conditions(
    rows: list[dict[str, Any]],
    relationship_model: dict[str, Any],
    condition_map: dict[str, list[dict[str, str]]],
) -> None:
    split = max(1, min(len(rows) - 1, int(len(rows) * 0.7))) if len(rows) > 1 else 0
    if split < 6 or len(rows) - split < 6:
        return
    for left, right, baseline_correlation in relationship_pairs(relationship_model):
        if abs(baseline_correlation) < 0.8:
            continue
        baseline_pairs = paired_values(rows[:split], left, right)
        recent_pairs = paired_values(rows[split:], left, right)
        if len(baseline_pairs) < 6 or len(recent_pairs) < 6:
            continue
        slope, intercept = linear_fit([pair[0] for pair in baseline_pairs], [pair[1] for pair in baseline_pairs])
        residuals = [right_value - (slope * left_value + intercept) for left_value, right_value in recent_pairs]
        if not gradual_residual_shift(residuals):
            continue
        evidence = (
            f"{left} and {right} gradually diverged from their strong baseline relationship; "
            "an instrumentation offset is one explanation that should be checked."
        )
        if shared_measurement_family(left, right):
            add_condition(condition_map, left, "possible_drift", "review", evidence)
            add_condition(condition_map, right, "possible_drift", "review", evidence)
        else:
            contextual_evidence = (
                f"{left} and {right} gradually diverged from their baseline relationship. "
                "The signals do not appear to be redundant measurements, so this is supporting context rather than sensor-fault evidence."
            )
            add_condition(condition_map, left, "peer_divergence", "limitation", contextual_evidence)
            add_condition(condition_map, right, "peer_divergence", "limitation", contextual_evidence)


def add_timestamp_alignment_conditions(
    rows: list[dict[str, Any]],
    relationship_model: dict[str, Any],
    condition_map: dict[str, list[dict[str, str]]],
) -> None:
    split = max(1, min(len(rows) - 1, int(len(rows) * 0.7))) if len(rows) > 1 else 0
    recent = rows[split:]
    if len(recent) < 10:
        return
    for left, right, baseline_correlation in relationship_pairs(relationship_model):
        if abs(baseline_correlation) < 0.7:
            continue
        pairs = paired_values(recent, left, right)
        if len(pairs) < 10:
            continue
        left_values = [pair[0] for pair in pairs]
        right_values = [pair[1] for pair in pairs]
        zero = abs(correlation(left_values, right_values) or 0.0)
        best_lag = 0
        best = zero
        for lag in (-3, -2, -1, 1, 2, 3):
            lagged = lagged_correlation(left_values, right_values, lag)
            if lagged is not None and abs(lagged) > best:
                best = abs(lagged)
                best_lag = lag
        if best_lag and best >= 0.75 and best - zero >= 0.25:
            evidence = (
                f"{left} and {right} aligned substantially better with a {abs(best_lag)}-sample offset "
                "than at the recorded timestamps."
            )
            add_condition(condition_map, left, "timestamp_misalignment", "review", evidence)
            add_condition(condition_map, right, "timestamp_misalignment", "review", evidence)


def source_health_conditions(
    *,
    ingestion_report: dict[str, Any],
    timestamp_profile: dict[str, Any],
    timestamp_column: str | None,
) -> list[dict[str, str]]:
    conditions: list[dict[str, str]] = []
    counts = ingestion_report.get("quality_counts") if isinstance(ingestion_report.get("quality_counts"), dict) else {}
    duplicate_count = int(counts.get("duplicate_timestamp") or 0)
    if duplicate_count:
        conditions.append(
            {
                "type": "duplicate_timestamps",
                "severity": "limitation",
                "evidence": f"{duplicate_count} duplicate timestamp(s) were reported during ingestion.",
            }
        )
    warnings = " ".join(str(item) for item in timestamp_profile.get("warnings", []))
    if "inconsistent" in warnings.lower():
        conditions.append(
            {
                "type": "irregular_sampling",
                "severity": "limitation",
                "evidence": "Timestamp intervals were inconsistent in the existing timestamp profile.",
            }
        )
    if not timestamp_column:
        conditions.append(
            {
                "type": "timestamp_unavailable",
                "severity": "limitation",
                "evidence": "No timestamp signal was available to validate sampling alignment.",
            }
        )
    return conditions


def relationship_pairs(relationship_model: dict[str, Any]) -> list[tuple[str, str, float]]:
    candidates = relationship_model.get("baseline_relationships")
    if not isinstance(candidates, list) or not candidates:
        graph = relationship_model.get("relationship_graph")
        candidates = graph.get("edges", []) if isinstance(graph, dict) else []
    output: list[tuple[str, str, float]] = []
    seen: set[tuple[str, str]] = set()
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        columns = relationship_columns(item)
        if len(columns) < 2:
            continue
        pair = (columns[0], columns[1])
        if pair in seen:
            continue
        baseline = number(item.get("baseline_correlation"))
        if baseline is None:
            baseline = number(item.get("baseline_strength"))
        if baseline is None:
            continue
        seen.add(pair)
        output.append((pair[0], pair[1], baseline))
    return output


def relationship_columns(item: dict[str, Any]) -> list[str]:
    pairs = item.get("supporting_metric_pairs")
    if isinstance(pairs, list) and pairs and isinstance(pairs[0], dict):
        columns = [pairs[0].get("left"), pairs[0].get("right")]
        return [str(column) for column in columns if column]
    relationship = str(item.get("relationship") or "")
    if "<->" in relationship:
        return [part.strip() for part in relationship.split("<->", 1) if part.strip()]
    source = str(item.get("source") or "").removeprefix("metric:")
    target = str(item.get("target") or "").removeprefix("metric:")
    return [column for column in (source, target) if column]


def shared_measurement_family(left: str, right: str) -> bool:
    families = (
        "pressure",
        "temperature",
        "temp",
        "flow",
        "level",
        "humidity",
        "vibration",
        "current",
        "voltage",
        "power",
        "speed",
        "frequency",
        "conductivity",
        "turbidity",
    )
    left_text = re.sub(r"[^a-z0-9]+", "_", left.lower())
    right_text = re.sub(r"[^a-z0-9]+", "_", right.lower())
    return any(family in left_text and family in right_text for family in families)


def numeric_series(rows: list[dict[str, Any]], column: str) -> list[float]:
    return [
        parsed
        for row in rows
        if (parsed := number(row.get(column))) is not None
    ]


def paired_values(rows: list[dict[str, Any]], left: str, right: str) -> list[tuple[float, float]]:
    pairs = []
    for row in rows:
        left_value = number(row.get(left))
        right_value = number(row.get(right))
        if left_value is not None and right_value is not None:
            pairs.append((left_value, right_value))
    return pairs


def abrupt_step_evidence(values: list[float]) -> bool:
    if len(values) < 10:
        return False
    diffs = [abs(current - previous) for previous, current in zip(values, values[1:])]
    nonzero = [value for value in diffs if value > 0]
    if len(nonzero) < 3:
        return False
    typical = median(nonzero)
    center = median(values)
    spread = median(abs(value - center) for value in values)
    return max(diffs) > max(typical * 10, spread * 4, 1e-9)


def gradual_residual_shift(values: list[float]) -> bool:
    if len(values) < 6:
        return False
    slope, intercept = linear_fit(list(range(len(values))), values)
    predictions = [slope * index + intercept for index in range(len(values))]
    residual_sum = sum((actual - predicted) ** 2 for actual, predicted in zip(values, predictions))
    average = sum(values) / len(values)
    total_sum = sum((value - average) ** 2 for value in values)
    r_squared = 1.0 - (residual_sum / total_sum) if total_sum > 0 else 0.0
    span = abs(predictions[-1] - predictions[0])
    typical_step = median([abs(b - a) for a, b in zip(values, values[1:])]) if len(values) > 1 else 0.0
    return r_squared >= 0.85 and span > max(typical_step * 3, 1e-9)


def longest_repeated_run(values: list[float]) -> int:
    longest = current = 0
    previous: float | None = None
    for value in values:
        if previous is not None and value == previous:
            current += 1
        else:
            current = 1
            previous = value
        longest = max(longest, current)
    return longest


def linear_fit(x_values: list[float], y_values: list[float]) -> tuple[float, float]:
    if not x_values or len(x_values) != len(y_values):
        return 0.0, 0.0
    x_average = sum(x_values) / len(x_values)
    y_average = sum(y_values) / len(y_values)
    denominator = sum((value - x_average) ** 2 for value in x_values)
    if denominator <= 0:
        return 0.0, y_average
    slope = sum((x - x_average) * (y - y_average) for x, y in zip(x_values, y_values)) / denominator
    return slope, y_average - slope * x_average


def correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 3 or len(left) != len(right):
        return None
    left_average = sum(left) / len(left)
    right_average = sum(right) / len(right)
    numerator = sum((a - left_average) * (b - right_average) for a, b in zip(left, right))
    left_spread = math.sqrt(sum((value - left_average) ** 2 for value in left))
    right_spread = math.sqrt(sum((value - right_average) ** 2 for value in right))
    denominator = left_spread * right_spread
    return numerator / denominator if denominator > 0 else None


def lagged_correlation(left: list[float], right: list[float], lag: int) -> float | None:
    if lag > 0:
        return correlation(left[lag:], right[:-lag])
    return correlation(left[:lag], right[-lag:])


def add_condition(
    condition_map: dict[str, list[dict[str, str]]],
    column: str,
    condition_type: str,
    severity: str,
    evidence: str,
) -> None:
    if column not in condition_map:
        return
    if any(item["type"] == condition_type and item["evidence"] == evidence for item in condition_map[column]):
        return
    condition_map[column].append(
        {"type": condition_type, "severity": severity, "evidence": evidence}
    )


def health_from_conditions(conditions: list[dict[str, str]]) -> str:
    if any(item.get("type") in _SUSPECT_CONDITIONS for item in conditions):
        return "suspect"
    if conditions:
        return "limited"
    return "healthy"


def lower_rating(current: str, ceiling: str) -> str:
    order = {"low": 0, "limited": 1, "high": 2}
    return current if order.get(current, 0) <= order.get(ceiling, 0) else ceiling


def number(value: Any) -> float | None:
    if value is None:
        return None
    parsed = parse_numeric_value(str(value))
    return parsed if parsed is not None and math.isfinite(parsed) else None


def dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
