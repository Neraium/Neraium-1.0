from __future__ import annotations

import time
from collections import defaultdict
from statistics import median
from typing import Any

from app.engine.sii.common import (
    clamp,
    finite_number,
    median_absolute_deviation,
    module_envelope,
    parse_timestamps,
    paired_values,
    pearson,
)

DEFAULT_SCALES = (
    {"name": "15_minutes", "seconds": 15 * 60},
    {"name": "1_hour", "seconds": 60 * 60},
    {"name": "6_hours", "seconds": 6 * 60 * 60},
    {"name": "24_hours", "seconds": 24 * 60 * 60},
)
DEFAULT_ROW_SCALES = (
    {"name": "short_rows", "rows": 6},
    {"name": "medium_rows", "rows": 12},
    {"name": "long_rows", "rows": 24},
)
DEFAULT_CONFIG = {
    "minimum_timestamp_coverage": 0.90,
    "minimum_horizon_coverage": 0.80,
    "minimum_baseline_rows": 12,
    "minimum_active_rows": 6,
    "signal_activation_ratio": 1.0,
    "agreement_fraction": 0.67,
    "minimum_agreeing_scales": 2,
    "maximum_scales": 8,
    "maximum_signal_columns": 64,
    "maximum_relationship_columns": 16,
}


def analyze_multiscale(
    *,
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    empirical_thresholds: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare recent elapsed-time horizons with strictly earlier telemetry."""

    started = time.perf_counter()
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    maximum_scales = max(1, int(cfg["maximum_scales"]))
    scale_specs = _scale_specs(cfg.get("scales"), maximum_scales=maximum_scales)
    selected_columns = list(dict.fromkeys(numeric_columns))[: max(1, int(cfg["maximum_signal_columns"]))]
    parsed = parse_timestamps(rows, timestamp_column)
    timestamp_coverage = sum(value is not None for value in parsed) / max(1, len(rows))
    valid_pairs = [(index, value) for index, value in enumerate(parsed) if value is not None]
    monotonic = all(current > previous for (_pi, previous), (_ci, current) in zip(valid_pairs, valid_pairs[1:]))

    if not timestamp_column:
        return _row_fallback(
            rows=rows,
            numeric_columns=selected_columns,
            empirical_thresholds=empirical_thresholds,
            config=cfg,
            started=started,
            fallback_reason="timestamp_column_unavailable",
            timestamp_coverage=timestamp_coverage,
        )

    if timestamp_coverage < float(cfg["minimum_timestamp_coverage"]) or not monotonic:
        reason = (
            "insufficient_timestamp_coverage"
            if timestamp_coverage < float(cfg["minimum_timestamp_coverage"])
            else "timestamps_not_strictly_increasing"
        )
        envelope = module_envelope(
            started=started,
            status="limited",
            reason=reason,
            inputs_used=["ordered_rows", "timestamp_column", "numeric_columns"],
            rows_used=len(valid_pairs),
            columns_used=selected_columns,
            assumptions=["Elapsed-time horizons require reliable chronological timestamps; unreliable timestamps are not relabeled as durations."],
            output_metrics={"eligible_scale_count": 0, "configured_scale_count": len(scale_specs)},
            limitations=["Elapsed-time scales could not be constructed safely from the supplied timestamps."],
        )
        return {
            **envelope,
            "method": "chronological_elapsed_horizon_comparison_v2",
            "analysis_basis": "unavailable",
            "timestamp_coverage": round(timestamp_coverage, 6),
            "used_row_fallback": False,
            "scales": [_unsupported_scale(spec, reason) for spec in scale_specs],
            "scales_used": [],
            "agreement": _empty_agreement(int(cfg["minimum_agreeing_scales"])),
            "cross_scale_interpretation": _cross_scale_interpretation([], _empty_agreement(int(cfg["minimum_agreeing_scales"])), minimum_scales=int(cfg["minimum_agreeing_scales"]), elapsed_time=True),
            "behavior_patterns": {
                "status": "limited",
                "elapsed_time_basis": True,
                "signals": [],
                "classification_counts": {},
                "limitations": [
                    "Reliable chronological scale profiles were unavailable."
                ],
            },
        }

    latest = valid_pairs[-1][1]
    learned = (
        empirical_thresholds.get("signal_thresholds", {})
        if isinstance(empirical_thresholds, dict)
        else {}
    )
    scales = []
    activation: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    relationship_columns = selected_columns[: max(1, int(cfg["maximum_relationship_columns"]))]
    limitations: list[str] = []
    if len(selected_columns) < len(list(dict.fromkeys(numeric_columns))):
        limitations.append("Signal columns were bounded by the configured multiscale runtime limit.")

    for spec in scale_specs:
        cutoff = latest.timestamp() - float(spec["seconds"])
        current_indices = [
            index
            for index, timestamp in valid_pairs
            if cutoff < timestamp.timestamp() <= latest.timestamp()
        ]
        baseline_indices = [
            index
            for index, timestamp in valid_pairs
            if timestamp.timestamp() <= cutoff
        ]
        start_time = parsed[current_indices[0]] if current_indices else None
        end_time = parsed[current_indices[-1]] if current_indices else None
        actual_span = (end_time - start_time).total_seconds() if start_time and end_time else 0.0
        coverage_fraction = actual_span / max(float(spec["seconds"]), 1e-12)
        if len(current_indices) < int(cfg["minimum_active_rows"]):
            scales.append(
                _unsupported_scale(
                    spec,
                    "insufficient_active_rows",
                    len(baseline_indices),
                    len(current_indices),
                    actual_span=actual_span,
                    coverage_fraction=coverage_fraction,
                )
            )
            continue
        if len(baseline_indices) < int(cfg["minimum_baseline_rows"]):
            scales.append(
                _unsupported_scale(
                    spec,
                    "insufficient_pre_window_baseline_rows",
                    len(baseline_indices),
                    len(current_indices),
                    actual_span=actual_span,
                    coverage_fraction=coverage_fraction,
                )
            )
            continue
        if coverage_fraction < float(cfg["minimum_horizon_coverage"]):
            scales.append(
                _unsupported_scale(
                    spec,
                    "insufficient_active_time_coverage",
                    len(baseline_indices),
                    len(current_indices),
                    actual_span=actual_span,
                    coverage_fraction=coverage_fraction,
                )
            )
            continue
        baseline_rows = [rows[index] for index in baseline_indices]
        current_rows = [rows[index] for index in current_indices]
        signal_metrics = _signal_metrics(
            baseline_rows,
            current_rows,
            selected_columns,
            learned=learned,
            config=cfg,
        )
        for item in signal_metrics:
            if item["active"]:
                activation[item["column"]][item["direction"]].append(str(spec["name"]))
        relationship_metrics = _relationship_metrics(baseline_rows, current_rows, relationship_columns)
        scale_score = (
            sum(float(item["score"]) for item in signal_metrics) / len(signal_metrics)
            if signal_metrics
            else 0.0
        )
        scales.append(
            {
                "name": spec["name"],
                "analysis_basis": "elapsed_time",
                "horizon_seconds": float(spec["seconds"]),
                "status": "complete",
                "baseline_rows": len(baseline_indices),
                "active_rows": len(current_indices),
                "baseline_end_index": baseline_indices[-1],
                "active_start_index": current_indices[0],
                "active_end_index": current_indices[-1],
                "actual_active_span_seconds": round(actual_span, 6),
                "active_time_coverage_fraction": round(coverage_fraction, 6),
                "window_start": start_time.isoformat() if start_time else None,
                "window_end": end_time.isoformat() if end_time else None,
                "signal_metrics": signal_metrics,
                "relationship_metrics": relationship_metrics,
                "active_signal_count": sum(item["active"] for item in signal_metrics),
                "score": round(scale_score, 6),
            }
        )

    eligible = [item for item in scales if item["status"] == "complete"]
    minimum_scales = int(cfg["minimum_agreeing_scales"])
    if len(eligible) < minimum_scales:
        limitations.append("Fewer than two elapsed-time horizons had enough non-overlapping historical and active-time coverage.")
    agreement = _agreement(
        eligible,
        activation,
        minimum_scales=minimum_scales,
        fraction=float(cfg["agreement_fraction"]),
    )
    interpretation = _cross_scale_interpretation(
        eligible,
        agreement,
        minimum_scales=minimum_scales,
        elapsed_time=True,
    )
    behavior_patterns = _scale_behavior_patterns(
        eligible,
        elapsed_time=True,
    )
    status = "complete" if eligible else "limited"
    reason = None if eligible else "no_supported_elapsed_time_scales"
    metrics = {
        "configured_scale_count": len(scale_specs),
        "eligible_scale_count": len(eligible),
        "unsupported_scale_count": len(scales) - len(eligible),
        "agreeing_signal_count": len(agreement["agreeing_signals"]),
        "agreement_score": agreement["agreement_score"],
        "cross_scale_classification": interpretation["classification"],
    }
    envelope = module_envelope(
        started=started,
        status=status,
        reason=reason,
        inputs_used=["chronological_timestamped_rows", "numeric_columns", "empirical_thresholds"],
        rows_used=len(valid_pairs),
        columns_used=selected_columns,
        assumptions=[
            "Each active horizon is compared only with rows at or before its cutoff.",
            "Window boundaries are lower-exclusive and upper-inclusive.",
            "An elapsed horizon must cover the configured fraction of its duration before it can support cross-scale persistence.",
            "Cross-scale agreement is behavioral consistency, not a causal or failure-time claim.",
        ],
        output_metrics=metrics,
        limitations=limitations,
    )
    return {
        **envelope,
        "method": "chronological_elapsed_horizon_comparison_v2",
        "analysis_basis": "elapsed_time",
        "timestamp_coverage": round(timestamp_coverage, 6),
        "latest_timestamp": latest.isoformat(),
        "used_row_fallback": False,
        "scales": scales,
        "scales_used": [item["name"] for item in eligible],
        "agreement": agreement,
        "cross_scale_interpretation": interpretation,
        "behavior_patterns": behavior_patterns,
        "thresholds": {
            "signal_activation_ratio": float(cfg["signal_activation_ratio"]),
            "agreement_fraction": float(cfg["agreement_fraction"]),
            "minimum_agreeing_scales": minimum_scales,
            "minimum_horizon_coverage": float(cfg["minimum_horizon_coverage"]),
        },
        "runtime_limits": {
            "maximum_scales": maximum_scales,
            "maximum_signal_columns": int(cfg["maximum_signal_columns"]),
            "maximum_relationship_columns": int(cfg["maximum_relationship_columns"]),
        },
    }


def _row_fallback(
    *,
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    empirical_thresholds: dict[str, Any] | None,
    config: dict[str, Any],
    started: float,
    fallback_reason: str,
    timestamp_coverage: float,
) -> dict[str, Any]:
    learned = empirical_thresholds.get("signal_thresholds", {}) if isinstance(empirical_thresholds, dict) else {}
    specs = _row_scale_specs(
        config.get("row_scales"),
        maximum_scales=max(1, int(config["maximum_scales"])),
    )
    scales = []
    activation: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    relationship_columns = numeric_columns[: max(1, int(config["maximum_relationship_columns"]))]
    for spec in specs:
        active_count = int(spec["rows"])
        active_rows = rows[-active_count:] if active_count <= len(rows) else list(rows)
        baseline_rows = rows[: max(0, len(rows) - len(active_rows))]
        if len(active_rows) < max(int(config["minimum_active_rows"]), active_count):
            scales.append(_unsupported_row_scale(spec, "insufficient_active_rows", len(baseline_rows), len(active_rows)))
            continue
        if len(baseline_rows) < int(config["minimum_baseline_rows"]):
            scales.append(_unsupported_row_scale(spec, "insufficient_pre_window_baseline_rows", len(baseline_rows), len(active_rows)))
            continue
        signal_metrics = _signal_metrics(
            baseline_rows,
            active_rows,
            numeric_columns,
            learned=learned,
            config=config,
        )
        for item in signal_metrics:
            if item["active"]:
                activation[item["column"]][item["direction"]].append(str(spec["name"]))
        scales.append(
            {
                "name": spec["name"],
                "analysis_basis": "row_count",
                "window_rows": active_count,
                "status": "complete",
                "baseline_rows": len(baseline_rows),
                "active_rows": len(active_rows),
                "baseline_end_index": len(baseline_rows) - 1,
                "active_start_index": len(baseline_rows),
                "active_end_index": len(rows) - 1,
                "signal_metrics": signal_metrics,
                "relationship_metrics": _relationship_metrics(baseline_rows, active_rows, relationship_columns),
                "active_signal_count": sum(item["active"] for item in signal_metrics),
                "score": round(
                    sum(float(item["score"]) for item in signal_metrics) / len(signal_metrics)
                    if signal_metrics
                    else 0.0,
                    6,
                ),
            }
        )
    eligible = [item for item in scales if item["status"] == "complete"]
    minimum_scales = int(config["minimum_agreeing_scales"])
    agreement = _agreement(
        eligible,
        activation,
        minimum_scales=minimum_scales,
        fraction=float(config["agreement_fraction"]),
    )
    agreement["row_scale_consistency_observed"] = bool(agreement["agreeing_signals"])
    agreement["sustained_change_observed"] = False
    interpretation = _cross_scale_interpretation(
        eligible,
        agreement,
        minimum_scales=minimum_scales,
        elapsed_time=False,
    )
    behavior_patterns = _scale_behavior_patterns(
        eligible,
        elapsed_time=False,
    )
    status = "limited"
    reason = fallback_reason if eligible else "no_supported_row_fallback_scales"
    envelope = module_envelope(
        started=started,
        status=status,
        reason=reason,
        inputs_used=["ordered_rows", "numeric_columns", "empirical_thresholds"],
        rows_used=len(rows),
        columns_used=numeric_columns,
        assumptions=[
            "Row-count fallback does not map rows to minutes or any other elapsed duration.",
            "Row-scale consistency cannot establish elapsed-time persistence.",
        ],
        output_metrics={
            "configured_scale_count": len(specs),
            "eligible_scale_count": len(eligible),
            "unsupported_scale_count": len(scales) - len(eligible),
            "cross_scale_classification": interpretation["classification"],
        },
        limitations=["Reliable timestamps were unavailable; only row-count scale consistency is reported."],
    )
    return {
        **envelope,
        "method": "row_count_multiscale_fallback_v1",
        "analysis_basis": "row_count",
        "timestamp_coverage": round(timestamp_coverage, 6),
        "used_row_fallback": True,
        "fallback_reason": fallback_reason,
        "scales": scales,
        "scales_used": [item["name"] for item in eligible],
        "agreement": agreement,
        "cross_scale_interpretation": interpretation,
        "behavior_patterns": behavior_patterns,
        "thresholds": {
            "signal_activation_ratio": float(config["signal_activation_ratio"]),
            "agreement_fraction": float(config["agreement_fraction"]),
            "minimum_agreeing_scales": minimum_scales,
        },
    }


def _signal_metrics(
    baseline_rows: list[dict[str, Any]],
    current_rows: list[dict[str, Any]],
    columns: list[str],
    *,
    learned: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    output = []
    for column in columns:
        baseline_values = [
            value for row in baseline_rows if (value := finite_number(row.get(column))) is not None
        ]
        current_values = [
            value for row in current_rows if (value := finite_number(row.get(column))) is not None
        ]
        if len(baseline_values) < int(config["minimum_baseline_rows"]) or len(current_values) < int(config["minimum_active_rows"]):
            continue
        baseline_center = float(median(baseline_values))
        current_center = float(median(current_values))
        absolute_change = current_center - baseline_center
        robust_sigma = 1.4826 * median_absolute_deviation(baseline_values)
        fixed_floor = max(0.05 * abs(baseline_center), 0.01)
        learned_item = learned.get(column) if isinstance(learned, dict) else None
        learned_threshold = finite_number(learned_item.get("threshold")) if isinstance(learned_item, dict) else None
        threshold = max(robust_sigma, fixed_floor, learned_threshold or 0.0)
        ratio = abs(absolute_change) / max(threshold, 1e-12)
        active = ratio >= float(config["signal_activation_ratio"])
        direction = "up" if active and absolute_change > 0 else "down" if active and absolute_change < 0 else "flat"
        output.append(
            {
                "column": column,
                "baseline_median": round(baseline_center, 6),
                "current_median": round(current_center, 6),
                "absolute_change": round(absolute_change, 6),
                "deviation_threshold": round(threshold, 6),
                "threshold_source": "empirical_with_robust_floor" if learned_threshold is not None else "robust_fixed_floor",
                "normalized_change": round(ratio, 6),
                "score": round(clamp(ratio / 4.0), 6),
                "direction": direction,
                "active": active,
                "baseline_sample_count": len(baseline_values),
                "current_sample_count": len(current_values),
            }
        )
    return output


def _scale_specs(raw: Any, *, maximum_scales: int) -> list[dict[str, Any]]:
    candidates = raw if isinstance(raw, (list, tuple)) else DEFAULT_SCALES
    output = []
    for index, item in enumerate(candidates[:maximum_scales]):
        if isinstance(item, (int, float)):
            seconds = float(item)
            name = f"{int(seconds)}_seconds"
        elif isinstance(item, dict):
            try:
                seconds = float(item.get("seconds"))
            except (TypeError, ValueError):
                continue
            name = str(item.get("name") or f"scale_{index + 1}")
        else:
            continue
        if seconds > 0:
            output.append({"name": name, "seconds": seconds})
    return output


def _row_scale_specs(raw: Any, *, maximum_scales: int) -> list[dict[str, Any]]:
    candidates = raw if isinstance(raw, (list, tuple)) else DEFAULT_ROW_SCALES
    output = []
    for index, item in enumerate(candidates[:maximum_scales]):
        if isinstance(item, (int, float)):
            rows = int(item)
            name = f"{rows}_rows"
        elif isinstance(item, dict):
            try:
                rows = int(item.get("rows"))
            except (TypeError, ValueError):
                continue
            name = str(item.get("name") or f"row_scale_{index + 1}")
        else:
            continue
        if rows > 0:
            output.append({"name": name, "rows": rows})
    return output


def _unsupported_scale(
    spec: dict[str, Any],
    reason: str,
    baseline_rows: int = 0,
    active_rows: int = 0,
    *,
    actual_span: float = 0.0,
    coverage_fraction: float = 0.0,
) -> dict[str, Any]:
    return {
        "name": spec["name"],
        "analysis_basis": "elapsed_time",
        "horizon_seconds": float(spec["seconds"]),
        "status": "limited",
        "reason": reason,
        "baseline_rows": baseline_rows,
        "active_rows": active_rows,
        "actual_active_span_seconds": round(actual_span, 6),
        "active_time_coverage_fraction": round(coverage_fraction, 6),
        "signal_metrics": [],
        "relationship_metrics": [],
        "score": 0.0,
    }


def _unsupported_row_scale(
    spec: dict[str, Any], reason: str, baseline_rows: int, active_rows: int
) -> dict[str, Any]:
    return {
        "name": spec["name"],
        "analysis_basis": "row_count",
        "window_rows": int(spec["rows"]),
        "status": "limited",
        "reason": reason,
        "baseline_rows": baseline_rows,
        "active_rows": active_rows,
        "signal_metrics": [],
        "relationship_metrics": [],
        "score": 0.0,
    }


def _relationship_metrics(
    baseline_rows: list[dict[str, Any]], current_rows: list[dict[str, Any]], columns: list[str]
) -> list[dict[str, Any]]:
    output = []
    for index, left in enumerate(columns):
        for right in columns[index + 1 :]:
            baseline_pairs = paired_values(baseline_rows, left, right)
            current_pairs = paired_values(current_rows, left, right)
            baseline = pearson(baseline_pairs)
            current = pearson(current_pairs)
            if baseline is None or current is None:
                continue
            output.append(
                {
                    "left": left,
                    "right": right,
                    "baseline_correlation": round(baseline, 6),
                    "current_correlation": round(current, 6),
                    "correlation_delta": round(abs(current - baseline), 6),
                    "baseline_sample_count": len(baseline_pairs),
                    "current_sample_count": len(current_pairs),
                }
            )
    return output


def _agreement(
    eligible: list[dict[str, Any]],
    activation: dict[str, dict[str, list[str]]],
    *,
    minimum_scales: int,
    fraction: float,
) -> dict[str, Any]:
    eligible_count = len(eligible)
    required = max(minimum_scales, int(eligible_count * fraction + 0.999999)) if eligible_count else minimum_scales
    agreeing = []
    best_count = 0
    conflicting = []
    for column, by_direction in sorted(activation.items()):
        nonempty = {direction: names for direction, names in by_direction.items() if names}
        if len(nonempty) > 1:
            conflicting.append(
                {
                    "column": column,
                    "directions": {direction: names for direction, names in sorted(nonempty.items())},
                }
            )
        for direction, names in sorted(nonempty.items()):
            best_count = max(best_count, len(names))
            if len(names) >= required:
                agreeing.append(
                    {
                        "column": column,
                        "direction": direction,
                        "active_scales": names,
                        "active_scale_count": len(names),
                        "eligible_scale_count": eligible_count,
                        "agreement_fraction": round(len(names) / max(1, eligible_count), 6),
                    }
                )
    return {
        "status": "complete" if eligible_count >= minimum_scales else "limited",
        "eligible_scale_count": eligible_count,
        "required_agreeing_scale_count": required,
        "agreeing_signals": agreeing,
        "conflicting_signals": conflicting,
        "agreement_score": round(best_count / max(1, eligible_count), 6),
        "sustained_change_observed": bool(agreeing),
    }


def _cross_scale_interpretation(
    eligible: list[dict[str, Any]],
    agreement: dict[str, Any],
    *,
    minimum_scales: int,
    elapsed_time: bool,
) -> dict[str, Any]:
    active_count = sum(int(item.get("active_signal_count") or 0) for item in eligible)
    conflicting = list(agreement.get("conflicting_signals") or [])
    agreeing = list(agreement.get("agreeing_signals") or [])
    if len(eligible) < minimum_scales:
        classification = "insufficient_coverage"
        summary = "Too few scales had sufficient support for a cross-scale claim."
    elif conflicting:
        classification = "conflicting_scales"
        summary = "At least one signal changed in opposing directions across eligible scales."
    elif agreeing and elapsed_time:
        classification = "sustained_across_elapsed_scales"
        summary = "A directionally consistent change met the elapsed-time agreement rule across scales."
    elif agreeing:
        classification = "consistent_across_row_scales"
        summary = "A directionally consistent change appeared across row-count scales; elapsed persistence remains unavailable."
    elif active_count:
        classification = "transient_or_scale_specific"
        summary = "Change was active on one or more scales but did not meet the cross-scale agreement rule."
    else:
        classification = "stable_across_scales"
        summary = "No eligible scale crossed the signal activation threshold."
    return {
        "status": "complete" if len(eligible) >= minimum_scales else "limited",
        "classification": classification,
        "summary": summary,
        "elapsed_time_basis": elapsed_time,
        "eligible_scale_count": len(eligible),
        "agreeing_signal_count": len(agreeing),
        "conflicting_signal_count": len(conflicting),
    }


def _scale_behavior_patterns(
    eligible: list[dict[str, Any]],
    *,
    elapsed_time: bool,
) -> dict[str, Any]:
    by_signal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for scale_index, scale in enumerate(eligible):
        for metric in scale.get("signal_metrics", []):
            if not isinstance(metric, dict) or not metric.get("column"):
                continue
            direction = str(metric.get("direction") or "flat")
            sign = 1.0 if direction == "up" else -1.0 if direction == "down" else 0.0
            by_signal[str(metric["column"])].append(
                {
                    "scale_index": scale_index,
                    "scale": scale.get("name"),
                    "horizon_seconds": scale.get("horizon_seconds"),
                    "window_rows": scale.get("window_rows"),
                    "active": bool(metric.get("active")),
                    "direction": direction,
                    "normalized_change": float(metric.get("normalized_change") or 0.0),
                    "signed_normalized_change": round(
                        sign * float(metric.get("normalized_change") or 0.0),
                        6,
                    ),
                }
            )
    signals = []
    for signal, profile in sorted(by_signal.items()):
        ordered = sorted(profile, key=lambda item: int(item["scale_index"]))
        active = [item for item in ordered if item["active"]]
        directions = [item["direction"] for item in active if item["direction"] != "flat"]
        reversals = sum(
            current != previous
            for previous, current in zip(directions, directions[1:])
        )
        magnitudes = [
            (float(index), float(item["normalized_change"]))
            for index, item in enumerate(ordered)
        ]
        magnitude_slope = _median_pairwise_slope(magnitudes)
        if not active:
            classification = "stable_across_scales"
        elif reversals >= 2:
            classification = "recurring_or_oscillatory_scale_pattern"
        elif len(active) == 1:
            classification = (
                "transient_event"
                if active[0]["scale_index"] == 0 and elapsed_time
                else "scale_specific_change"
            )
        elif not elapsed_time:
            classification = "consistent_across_row_scales"
        elif (
            magnitude_slope is not None
            and magnitude_slope > 1e-12
            and magnitudes[-1][1] > magnitudes[0][1]
        ):
            classification = "gradual_evolution"
        elif (
            magnitude_slope is not None
            and magnitude_slope < -1e-12
            and magnitudes[-1][1] < magnitudes[0][1]
        ):
            classification = "transient_event"
        else:
            classification = "persistent_instability"
        signals.append(
            {
                "column": signal,
                "classification": classification,
                "scale_profile": ordered,
                "active_scale_count": len(active),
                "eligible_scale_count": len(ordered),
                "direction_reversal_count": reversals,
                "normalized_magnitude_slope_per_scale": round(
                    magnitude_slope,
                    6,
                )
                if magnitude_slope is not None
                else None,
                "method": "direction_reversals_and_theil_sen_scale_profile_slope",
            }
        )
    counts: dict[str, int] = defaultdict(int)
    for item in signals:
        counts[str(item["classification"])] += 1
    return {
        "status": "complete" if signals else "limited",
        "elapsed_time_basis": elapsed_time,
        "signals": signals,
        "classification_counts": dict(sorted(counts.items())),
        "limitations": []
        if elapsed_time
        else [
            "Row-scale patterns cannot establish elapsed-time persistence or evolution."
        ],
    }


def _median_pairwise_slope(
    pairs: list[tuple[float, float]],
) -> float | None:
    slopes = [
        (right_value - left_value) / (right_position - left_position)
        for left_index, (left_position, left_value) in enumerate(pairs)
        for right_position, right_value in pairs[left_index + 1 :]
        if right_position > left_position
    ]
    return float(median(slopes)) if slopes else None


def _empty_agreement(minimum_scales: int = 2) -> dict[str, Any]:
    return {
        "status": "limited",
        "eligible_scale_count": 0,
        "required_agreeing_scale_count": minimum_scales,
        "agreeing_signals": [],
        "conflicting_signals": [],
        "agreement_score": 0.0,
        "sustained_change_observed": False,
    }
