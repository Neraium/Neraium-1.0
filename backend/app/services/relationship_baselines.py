from __future__ import annotations

import math
from typing import Any

import pandas as pd


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


def _select_numeric_columns_for_relationships(
    numeric_columns: list[str],
    *,
    max_relationship_columns: int,
) -> tuple[list[str], bool]:
    """
    Keep pairwise relationship work bounded for large uploads.

    Pairwise correlation scales as O(n^2 * rows). Large telemetry exports can
    include dozens or hundreds of numeric fields, which can hold the worker in
    the first relationship stage long enough to look stuck. Preserve the first
    columns in source order because upstream detection already orders them by
    file/schema appearance, and report when truncation occurred.
    """
    if max_relationship_columns <= 0 or len(numeric_columns) <= max_relationship_columns:
        return numeric_columns, False
    return numeric_columns[:max_relationship_columns], True



def _source_row_anchor(row: dict[str, Any] | None, window: str) -> dict[str, Any]:
    row = row or {}
    return {
        "window": window,
        "source_row": row.get("__source_row_number"),
        "timestamp": row.get("__source_timestamp"),
    }


def _relationship_source_rows(baseline_rows: list[dict[str, Any]], recent_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    anchors = []
    if baseline_rows:
        anchors.append(_source_row_anchor(baseline_rows[0], "baseline_start"))
        anchors.append(_source_row_anchor(baseline_rows[-1], "baseline_end"))
    if recent_rows:
        anchors.append(_source_row_anchor(recent_rows[0], "recent_start"))
        anchors.append(_source_row_anchor(recent_rows[-1], "recent_end"))
    return [anchor for anchor in anchors if anchor.get("source_row") is not None or anchor.get("timestamp")]

def build_relationship_baseline(
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    *,
    total_row_count: int | None = None,
    baseline_window_limit: int = 12000,
    recent_window_limit: int = 6000,
    max_relationship_columns: int = 32,
) -> dict[str, Any]:
    selected_numeric_columns, column_limited = _select_numeric_columns_for_relationships(
        numeric_columns,
        max_relationship_columns=max_relationship_columns,
    )
    if len(rows) < 12 or len(selected_numeric_columns) < 2:
        return {
            "top_relationship_changes": [],
            "baseline_relationships": [],
            "sampled_for_baseline": False,
            "relationship_columns_analyzed": len(selected_numeric_columns),
            "relationship_columns_available": len(numeric_columns),
            "relationship_columns_limited": column_limited,
        }

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
    if column_limited:
        sampled_for_baseline = True
    candidates: list[dict[str, Any]] = []
    baseline_frame = pd.DataFrame(baseline_rows, columns=selected_numeric_columns).apply(pd.to_numeric, errors="coerce")
    recent_frame = pd.DataFrame(recent_rows, columns=selected_numeric_columns).apply(pd.to_numeric, errors="coerce")
    baseline_corr_matrix = baseline_frame.corr(min_periods=3)
    recent_corr_matrix = recent_frame.corr(min_periods=3)
    baseline_counts = baseline_frame.notna().astype(int).T.dot(baseline_frame.notna().astype(int))
    recent_counts = recent_frame.notna().astype(int).T.dot(recent_frame.notna().astype(int))
    source_rows = _relationship_source_rows(baseline_rows, recent_rows)

    for idx, left_col in enumerate(selected_numeric_columns):
        for right_col in selected_numeric_columns[idx + 1 :]:
            baseline_corr = baseline_corr_matrix.at[left_col, right_col] if left_col in baseline_corr_matrix.index and right_col in baseline_corr_matrix.columns else None
            recent_corr = recent_corr_matrix.at[left_col, right_col] if left_col in recent_corr_matrix.index and right_col in recent_corr_matrix.columns else None
            if baseline_corr is None or recent_corr is None or pd.isna(baseline_corr) or pd.isna(recent_corr):
                continue

            baseline_sample_size = int(baseline_counts.at[left_col, right_col]) if left_col in baseline_counts.index and right_col in baseline_counts.columns else 0
            recent_sample_size = int(recent_counts.at[left_col, right_col]) if left_col in recent_counts.index and right_col in recent_counts.columns else 0
            if baseline_sample_size < 3 or recent_sample_size < 3:
                continue

            baseline_strength = abs(float(baseline_corr))
            if baseline_strength < 0.65:
                continue

            drift = abs(float(recent_corr) - float(baseline_corr))
            if drift < 0.25:
                continue

            candidates.append(
                {
                    "relationship": f"{left_col} <-> {right_col}",
                    "baseline_correlation": round(float(baseline_corr), 6),
                    "recent_correlation": round(float(recent_corr), 6),
                    "correlation_delta": round(float(drift), 6),
                    "coupling_strength": round(float(baseline_strength), 6),
                    "baseline_sample_size": baseline_sample_size,
                    "recent_sample_size": recent_sample_size,
                    "sampled_for_baseline": sampled_for_baseline,
                    "evidence_refs": [
                        {
                            "column": left_col,
                            "role": "left_variable",
                            "baseline_window": {"rows": baseline_sample_size, "correlation": round(float(baseline_corr), 6)},
                            "recent_window": {"rows": recent_sample_size, "correlation": round(float(recent_corr), 6)},
                            "source_rows": source_rows,
                        },
                        {
                            "column": right_col,
                            "role": "right_variable",
                            "baseline_window": {"rows": baseline_sample_size, "correlation": round(float(baseline_corr), 6)},
                            "recent_window": {"rows": recent_sample_size, "correlation": round(float(recent_corr), 6)},
                            "source_rows": source_rows,
                        },
                    ],
                    "source_rows": source_rows,
                    "summary": (
                        f"Coupling shift in {left_col} vs {right_col}: "
                        f"baseline={float(baseline_corr):.3f}, recent={float(recent_corr):.3f}, delta={float(drift):.3f}."
                    ),
                }
            )

    candidates.sort(key=lambda item: (item["correlation_delta"], item["coupling_strength"]), reverse=True)
    return {
        "top_relationship_changes": candidates[:5],
        "baseline_relationships": candidates,
        "sampled_for_baseline": sampled_for_baseline,
        "relationship_columns_analyzed": len(selected_numeric_columns),
        "relationship_columns_available": len(numeric_columns),
        "relationship_columns_limited": column_limited,
    }


# Compatibility alias for internal callers migrating from upload_jobs.
_build_relationship_baseline = build_relationship_baseline
