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
DEFAULT_CONFIG = {
    "minimum_timestamp_coverage": 0.90,
    "minimum_baseline_rows": 12,
    "minimum_active_rows": 6,
    "signal_activation_ratio": 1.0,
    "agreement_fraction": 0.67,
    "minimum_agreeing_scales": 2,
}


def analyze_multiscale(
    *,
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    empirical_thresholds: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare recent timestamp horizons with strictly earlier telemetry."""

    started = time.perf_counter()
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    scale_specs = _scale_specs(cfg.get("scales"))
    parsed = parse_timestamps(rows, timestamp_column)
    timestamp_coverage = sum(value is not None for value in parsed) / max(1, len(rows))
    valid_pairs = [(index, value) for index, value in enumerate(parsed) if value is not None]
    monotonic = all(current > previous for (_pi, previous), (_ci, current) in zip(valid_pairs, valid_pairs[1:]))
    limitations: list[str] = []
    if not timestamp_column or timestamp_coverage < float(cfg["minimum_timestamp_coverage"]) or not monotonic:
        reason = (
            "timestamp_column_unavailable"
            if not timestamp_column
            else "insufficient_timestamp_coverage"
            if timestamp_coverage < float(cfg["minimum_timestamp_coverage"])
            else "timestamps_not_strictly_increasing"
        )
        envelope = module_envelope(
            started=started,
            status="limited",
            reason=reason,
            inputs_used=["ordered_rows", "timestamp_column", "numeric_columns"],
            rows_used=len(valid_pairs),
            columns_used=numeric_columns,
            assumptions=["Scale windows require chronological timestamps and never substitute row counts for elapsed time."],
            output_metrics={"eligible_scale_count": 0, "configured_scale_count": len(scale_specs)},
            limitations=["Elapsed-time scales could not be constructed from the supplied timestamps."],
        )
        return {
            **envelope,
            "method": "chronological_elapsed_horizon_comparison_v1",
            "timestamp_coverage": round(timestamp_coverage, 6),
            "scales": [_unsupported_scale(spec, reason) for spec in scale_specs],
            "scales_used": [],
            "agreement": _empty_agreement(),
        }

    latest = valid_pairs[-1][1]
    learned = (
        empirical_thresholds.get("signal_thresholds", {})
        if isinstance(empirical_thresholds, dict)
        else {}
    )
    scales = []
    signal_activation: dict[str, list[str]] = defaultdict(list)
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
        if len(current_indices) < int(cfg["minimum_active_rows"]):
            scales.append(_unsupported_scale(spec, "insufficient_active_rows", len(baseline_indices), len(current_indices)))
            continue
        if len(baseline_indices) < int(cfg["minimum_baseline_rows"]):
            scales.append(_unsupported_scale(spec, "insufficient_pre_window_baseline_rows", len(baseline_indices), len(current_indices)))
            continue
        baseline_rows = [rows[index] for index in baseline_indices]
        current_rows = [rows[index] for index in current_indices]
        signal_metrics = []
        for column in numeric_columns:
            baseline_values = [
                value
                for row in baseline_rows
                if (value := finite_number(row.get(column))) is not None
            ]
            current_values = [
                value
                for row in current_rows
                if (value := finite_number(row.get(column))) is not None
            ]
            if len(baseline_values) < int(cfg["minimum_baseline_rows"]) or len(current_values) < int(cfg["minimum_active_rows"]):
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
            active = ratio >= float(cfg["signal_activation_ratio"])
            if active:
                signal_activation[column].append(str(spec["name"]))
            signal_metrics.append(
                {
                    "column": column,
                    "baseline_median": round(baseline_center, 6),
                    "current_median": round(current_center, 6),
                    "absolute_change": round(absolute_change, 6),
                    "deviation_threshold": round(threshold, 6),
                    "threshold_source": "empirical_with_robust_floor" if learned_threshold is not None else "robust_fixed_floor",
                    "normalized_change": round(ratio, 6),
                    "score": round(clamp(ratio / 4.0), 6),
                    "direction": "up" if absolute_change > threshold else "down" if absolute_change < -threshold else "flat",
                    "active": active,
                    "baseline_sample_count": len(baseline_values),
                    "current_sample_count": len(current_values),
                }
            )
        relationship_metrics = _relationship_metrics(baseline_rows, current_rows, numeric_columns)
        scale_score = (
            sum(float(item["score"]) for item in signal_metrics) / len(signal_metrics)
            if signal_metrics
            else 0.0
        )
        start_time = parsed[current_indices[0]]
        end_time = parsed[current_indices[-1]]
        actual_span = (end_time - start_time).total_seconds() if start_time and end_time else 0.0
        scales.append(
            {
                "name": spec["name"],
                "horizon_seconds": float(spec["seconds"]),
                "status": "complete",
                "baseline_rows": len(baseline_indices),
                "active_rows": len(current_indices),
                "baseline_end_index": baseline_indices[-1],
                "active_start_index": current_indices[0],
                "active_end_index": current_indices[-1],
                "actual_active_span_seconds": round(actual_span, 6),
                "window_start": start_time.isoformat() if start_time else None,
                "window_end": end_time.isoformat() if end_time else None,
                "signal_metrics": signal_metrics,
                "relationship_metrics": relationship_metrics,
                "active_signal_count": sum(item["active"] for item in signal_metrics),
                "score": round(scale_score, 6),
            }
        )

    eligible = [item for item in scales if item["status"] == "complete"]
    if len(eligible) < int(cfg["minimum_agreeing_scales"]):
        limitations.append("Fewer than two elapsed-time horizons had enough non-overlapping historical support.")
    agreement = _agreement(
        eligible,
        signal_activation,
        minimum_scales=int(cfg["minimum_agreeing_scales"]),
        fraction=float(cfg["agreement_fraction"]),
    )
    status = "complete" if eligible else "limited"
    reason = None if eligible else "no_supported_elapsed_time_scales"
    metrics = {
        "configured_scale_count": len(scale_specs),
        "eligible_scale_count": len(eligible),
        "unsupported_scale_count": len(scales) - len(eligible),
        "agreeing_signal_count": len(agreement["agreeing_signals"]),
        "agreement_score": agreement["agreement_score"],
    }
    envelope = module_envelope(
        started=started,
        status=status,
        reason=reason,
        inputs_used=["chronological_timestamped_rows", "numeric_columns", "empirical_thresholds"],
        rows_used=len(valid_pairs),
        columns_used=numeric_columns,
        assumptions=[
            "Each active horizon is compared only with rows at or before its cutoff.",
            "Window boundaries are lower-exclusive and upper-inclusive.",
            "Multi-scale agreement is behavioral consistency, not a causal or failure-time claim.",
        ],
        output_metrics=metrics,
        limitations=limitations,
    )
    return {
        **envelope,
        "method": "chronological_elapsed_horizon_comparison_v1",
        "timestamp_coverage": round(timestamp_coverage, 6),
        "latest_timestamp": latest.isoformat(),
        "scales": scales,
        "scales_used": [item["name"] for item in eligible],
        "agreement": agreement,
        "thresholds": {
            "signal_activation_ratio": float(cfg["signal_activation_ratio"]),
            "agreement_fraction": float(cfg["agreement_fraction"]),
            "minimum_agreeing_scales": int(cfg["minimum_agreeing_scales"]),
        },
    }


def _scale_specs(raw: Any) -> list[dict[str, Any]]:
    candidates = raw if isinstance(raw, (list, tuple)) else DEFAULT_SCALES
    output = []
    for index, item in enumerate(candidates):
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


def _unsupported_scale(
    spec: dict[str, Any], reason: str, baseline_rows: int = 0, active_rows: int = 0
) -> dict[str, Any]:
    return {
        "name": spec["name"],
        "horizon_seconds": float(spec["seconds"]),
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
    selected = columns[:16]
    for index, left in enumerate(selected):
        for right in selected[index + 1 :]:
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
    activation: dict[str, list[str]],
    *,
    minimum_scales: int,
    fraction: float,
) -> dict[str, Any]:
    eligible_count = len(eligible)
    required = max(minimum_scales, int(eligible_count * fraction + 0.999999)) if eligible_count else minimum_scales
    agreeing = [
        {
            "column": column,
            "active_scales": names,
            "active_scale_count": len(names),
            "eligible_scale_count": eligible_count,
            "agreement_fraction": round(len(names) / max(1, eligible_count), 6),
        }
        for column, names in sorted(activation.items())
        if len(names) >= required
    ]
    best_fraction = max((len(names) / max(1, eligible_count) for names in activation.values()), default=0.0)
    return {
        "status": "complete" if eligible_count >= minimum_scales else "limited",
        "eligible_scale_count": eligible_count,
        "required_agreeing_scale_count": required,
        "agreeing_signals": agreeing,
        "agreement_score": round(best_fraction, 6),
        "sustained_change_observed": bool(agreeing),
    }


def _empty_agreement() -> dict[str, Any]:
    return {
        "status": "limited",
        "eligible_scale_count": 0,
        "required_agreeing_scale_count": 2,
        "agreeing_signals": [],
        "agreement_score": 0.0,
        "sustained_change_observed": False,
    }
