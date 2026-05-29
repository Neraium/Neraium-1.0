from __future__ import annotations

import math
from typing import Any


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text == "":
        return None
    low = text.lower()
    if low in {"true", "yes", "on"}:
        return 1.0
    if low in {"false", "no", "off"}:
        return 0.0
    try:
        value = float(text)
        if math.isfinite(value):
            return value
    except ValueError:
        return None
    return None


def _pearson_corr(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    centered_left = [v - mean_left for v in left]
    centered_right = [v - mean_right for v in right]
    denom_left = math.sqrt(sum(v * v for v in centered_left))
    denom_right = math.sqrt(sum(v * v for v in centered_right))
    denom = denom_left * denom_right
    if denom <= 1e-12:
        return None
    return sum(a * b for a, b in zip(centered_left, centered_right)) / denom


def build_relationship_baseline(
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    *,
    total_row_count: int | None = None,
    baseline_window_limit: int = 12000,
    recent_window_limit: int = 6000,
) -> dict[str, Any]:
    if len(rows) < 12 or len(numeric_columns) < 2:
        return {"top_relationship_changes": [], "baseline_relationships": [], "sampled_for_baseline": False}

    baseline_count = max(6, int(len(rows) * 0.7))
    baseline_rows = rows[:baseline_count]
    recent_rows = rows[baseline_count:]

    sampled_for_baseline = False
    if len(baseline_rows) > baseline_window_limit:
        baseline_rows = baseline_rows[:baseline_window_limit]
        sampled_for_baseline = True
    if len(recent_rows) > recent_window_limit:
        recent_rows = recent_rows[-recent_window_limit:]
        sampled_for_baseline = True
    if total_row_count is not None and total_row_count > len(rows):
        sampled_for_baseline = True
    candidates: list[dict[str, Any]] = []

    for idx, left_col in enumerate(numeric_columns):
        for right_col in numeric_columns[idx + 1 :]:
            left_base: list[float] = []
            right_base: list[float] = []
            left_recent: list[float] = []
            right_recent: list[float] = []
            for row in baseline_rows:
                lv = _to_float(row.get(left_col))
                rv = _to_float(row.get(right_col))
                if lv is None or rv is None:
                    continue
                left_base.append(lv)
                right_base.append(rv)
            for row in recent_rows:
                lv = _to_float(row.get(left_col))
                rv = _to_float(row.get(right_col))
                if lv is None or rv is None:
                    continue
                left_recent.append(lv)
                right_recent.append(rv)

            baseline_corr = _pearson_corr(left_base, right_base)
            recent_corr = _pearson_corr(left_recent, right_recent)
            if baseline_corr is None or recent_corr is None:
                continue

            baseline_strength = abs(baseline_corr)
            if baseline_strength < 0.65:
                continue

            drift = abs(recent_corr - baseline_corr)
            if drift < 0.25:
                continue

            candidates.append(
                {
                    "relationship": f"{left_col} <-> {right_col}",
                    "baseline_correlation": round(baseline_corr, 6),
                    "recent_correlation": round(recent_corr, 6),
                    "correlation_delta": round(drift, 6),
                    "coupling_strength": round(baseline_strength, 6),
                    "baseline_sample_size": len(left_base),
                    "recent_sample_size": len(left_recent),
                    "sampled_for_baseline": sampled_for_baseline,
                    "evidence_refs": [
                        {"column": left_col, "role": "left_variable"},
                        {"column": right_col, "role": "right_variable"},
                    ],
                    "summary": (
                        f"Coupling shift in {left_col} vs {right_col}: "
                        f"baseline={baseline_corr:.3f}, recent={recent_corr:.3f}, delta={drift:.3f}."
                    ),
                }
            )

    candidates.sort(key=lambda item: (item["correlation_delta"], item["coupling_strength"]), reverse=True)
    return {
        "top_relationship_changes": candidates[:5],
        "baseline_relationships": candidates,
        "sampled_for_baseline": sampled_for_baseline,
    }


# Compatibility alias for internal callers migrating from upload_jobs.
_build_relationship_baseline = build_relationship_baseline
