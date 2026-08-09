from __future__ import annotations

import math
import time
from itertools import combinations
from typing import Any

from app.engine.sii.common import (
    median_absolute_deviation,
    module_envelope,
    numeric_values,
    paired_values,
    pearson,
    quantile,
)

DEFAULT_CONFIG = {
    "baseline_fraction": 0.70,
    "minimum_baseline_rows": 48,
    "minimum_signal_values": 24,
    "minimum_relationship_windows": 4,
    "relationship_window_rows": 12,
    "fixed_relationship_change_threshold": 0.25,
    "minimum_absolute_signal_threshold": 0.01,
    "signal_relative_floor": 0.05,
}


def estimate_empirical_thresholds(
    *,
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    relationship_columns: list[str] | None = None,
    config: dict[str, Any] | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Fit deterministic, conservative thresholds on historical rows only.

    Learned thresholds may make a fixed Phase 1 threshold stricter, never more
    permissive. Active/recent rows are not used while fitting the thresholds.
    """

    started = time.perf_counter()
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    split_index = max(0, min(len(rows), int(len(rows) * float(cfg["baseline_fraction"]))))
    baseline_rows = rows[:split_index]
    minimum_rows = int(cfg["minimum_baseline_rows"])
    fixed_relationship = float(cfg["fixed_relationship_change_threshold"])
    limitations: list[str] = []
    relationship_fit_columns = numeric_columns if relationship_columns is None else relationship_columns
    total_candidates = len(numeric_columns) + (
        len(relationship_fit_columns) * max(0, len(relationship_fit_columns) - 1) // 2
    )
    if progress_callback:
        progress_callback(0, total_candidates)

    signal_thresholds: dict[str, dict[str, Any]] = {}
    for signal_index, column in enumerate(numeric_columns, start=1):
        values = numeric_values(baseline_rows, column)
        if len(values) < int(cfg["minimum_signal_values"]):
            signal_thresholds[column] = {
                "status": "fallback",
                "threshold": None,
                "fallback_reason": "insufficient_baseline_signal_values",
                "sample_count": len(values),
            }
            if progress_callback:
                progress_callback(signal_index, total_candidates)
            continue
        center = quantile(values, 0.5)
        deviations = [abs(value - center) for value in values]
        empirical = quantile(deviations, 0.95)
        robust_sigma = 1.4826 * median_absolute_deviation(values)
        fixed_floor = max(
            float(cfg["minimum_absolute_signal_threshold"]),
            float(cfg["signal_relative_floor"]) * abs(center),
        )
        threshold = max(empirical, robust_sigma, fixed_floor)
        signal_thresholds[column] = {
            "status": "learned",
            "threshold": round(threshold, 6),
            "baseline_center": round(center, 6),
            "empirical_absolute_deviation_q95": round(empirical, 6),
            "robust_sigma": round(robust_sigma, 6),
            "fixed_floor": round(fixed_floor, 6),
            "sample_count": len(values),
        }
        if progress_callback:
            progress_callback(signal_index, total_candidates)

    relationship_deltas: list[float] = []
    relationship_windows = _relationship_window_correlations(
        baseline_rows,
        relationship_fit_columns,
        window_rows=max(3, int(cfg["relationship_window_rows"])),
        progress_callback=(
            (
                lambda completed, total: progress_callback(
                    len(numeric_columns) + completed,
                    len(numeric_columns) + total,
                )
            )
            if progress_callback
            else None
        ),
    )
    for pair_windows in relationship_windows.values():
        for left, right in zip(pair_windows, pair_windows[1:]):
            relationship_deltas.append(abs(right - left))

    minimum_relationship_windows = int(cfg["minimum_relationship_windows"])
    eligible_window_count = max((len(values) for values in relationship_windows.values()), default=0)
    baseline_sufficient = len(baseline_rows) >= minimum_rows
    relationship_sufficient = eligible_window_count >= minimum_relationship_windows and bool(relationship_deltas)
    if baseline_sufficient and relationship_sufficient:
        empirical_relationship = quantile(relationship_deltas, 0.95)
        relationship_threshold = max(fixed_relationship, empirical_relationship)
        relationship = {
            "status": "learned",
            "threshold": round(relationship_threshold, 6),
            "fixed_floor": round(fixed_relationship, 6),
            "empirical_delta_q95": round(empirical_relationship, 6),
            "delta_sample_count": len(relationship_deltas),
            "maximum_pair_window_count": eligible_window_count,
        }
    else:
        fallback_reason = (
            "insufficient_baseline_rows"
            if not baseline_sufficient
            else "insufficient_baseline_relationship_windows"
        )
        relationship = {
            "status": "fallback",
            "threshold": round(fixed_relationship, 6),
            "fixed_floor": round(fixed_relationship, 6),
            "fallback_reason": fallback_reason,
            "delta_sample_count": len(relationship_deltas),
            "maximum_pair_window_count": eligible_window_count,
        }
        limitations.append(
            "The fixed relationship-change threshold was retained because the historical baseline was insufficient for empirical fitting."
        )

    learned_signal_count = sum(item["status"] == "learned" for item in signal_thresholds.values())
    fallback_signal_count = len(signal_thresholds) - learned_signal_count
    if fallback_signal_count:
        limitations.append(
            f"{fallback_signal_count} signal threshold(s) retained an explicit fallback because baseline values were insufficient."
        )
    status = "complete" if baseline_sufficient and (learned_signal_count or relationship_sufficient) else "limited"
    reason = None if status == "complete" else "insufficient_baseline_for_empirical_thresholds"
    metrics = {
        "fit_rows": len(baseline_rows),
        "fit_end_index_exclusive": split_index,
        "active_rows_excluded_from_fit": len(rows) - split_index,
        "learned_signal_threshold_count": learned_signal_count,
        "fallback_signal_threshold_count": fallback_signal_count,
        "relationship_change_threshold": relationship["threshold"],
        "relationship_threshold_status": relationship["status"],
        "relationship_fit_columns": list(relationship_fit_columns),
    }
    envelope = module_envelope(
        started=started,
        status=status,
        reason=reason,
        inputs_used=["historical_baseline_rows", "numeric_columns", "eligible_relationship_columns"],
        rows_used=len(baseline_rows),
        columns_used=numeric_columns,
        assumptions=[
            "Only rows before the chronological 70 percent split are used for fitting.",
            "Empirical thresholds may raise fixed evidence floors but never lower them.",
            "Thresholds describe observed baseline variability, not physical alarm limits.",
        ],
        output_metrics=metrics,
        limitations=limitations,
    )
    return {
        **envelope,
        "method": "baseline_only_robust_empirical_thresholds_v1",
        "fit_window": {
            "start_index": 0,
            "end_index_exclusive": split_index,
            "rows": len(baseline_rows),
            "active_rows_excluded": len(rows) - split_index,
        },
        "signal_thresholds": signal_thresholds,
        "relationship_change": {**relationship, "columns_used": list(relationship_fit_columns)},
        "fallback_policy": "retain_fixed_phase_1_threshold",
        "minimums": {
            "baseline_rows": minimum_rows,
            "signal_values": int(cfg["minimum_signal_values"]),
            "relationship_windows": minimum_relationship_windows,
        },
    }


def _relationship_window_correlations(
    rows: list[dict[str, Any]],
    columns: list[str],
    *,
    window_rows: int,
    progress_callback: Any | None = None,
) -> dict[tuple[str, str], list[float]]:
    output: dict[tuple[str, str], list[float]] = {}
    if window_rows < 3:
        return output
    full_window_count = len(rows) // window_rows
    windows = [
        rows[index * window_rows : (index + 1) * window_rows]
        for index in range(full_window_count)
    ]
    pairs = list(combinations(columns, 2))
    if progress_callback:
        progress_callback(0, len(pairs))
    for pair_index, (left, right) in enumerate(pairs, start=1):
        correlations = [
            correlation
            for window in windows
            if (correlation := pearson(paired_values(window, left, right))) is not None
            and math.isfinite(correlation)
        ]
        if correlations:
            output[(left, right)] = correlations
        if progress_callback:
            progress_callback(pair_index, len(pairs))
    return output
