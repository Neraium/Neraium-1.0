from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.services.cumulative_counters import (
    counter_delta_series,
    detect_cumulative_counters_from_rows,
)


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


def _source_time_window(source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_window = {
        str(anchor.get("window")): anchor
        for anchor in source_rows
        if isinstance(anchor, dict) and anchor.get("window")
    }
    window = {
        "baseline_start": (by_window.get("baseline_start") or {}).get("timestamp"),
        "baseline_end": (by_window.get("baseline_end") or {}).get("timestamp"),
        "current_start": (by_window.get("recent_start") or {}).get("timestamp"),
        "current_end": (by_window.get("recent_end") or {}).get("timestamp"),
    }
    return {key: value for key, value in window.items() if value}


def _relationship_direction(baseline_corr: float, recent_corr: float) -> str:
    if abs(baseline_corr) >= 0.25 and abs(recent_corr) >= 0.25 and (baseline_corr > 0) != (recent_corr > 0):
        return "inverted"
    if recent_corr >= 0.1:
        return "positive"
    if recent_corr <= -0.1:
        return "negative"
    return "weak_or_flat"


def _relationship_change_type(baseline_corr: float, recent_corr: float) -> str:
    baseline_strength = abs(baseline_corr)
    current_strength = abs(recent_corr)
    sign_flipped = (
        baseline_strength >= 0.35
        and current_strength >= 0.35
        and (baseline_corr > 0) != (recent_corr > 0)
    )
    if sign_flipped:
        return "disrupted"
    if baseline_strength >= 0.65 and current_strength < 0.35:
        return "missing"
    if baseline_strength >= 0.65 and current_strength <= baseline_strength - 0.25:
        return "weakened"
    if current_strength >= 0.65 and baseline_strength < 0.35:
        return "new"
    if current_strength >= baseline_strength + 0.25:
        return "strengthened"
    return "stable"


def _change_percentage(baseline_strength: float, current_strength: float) -> float | None:
    if baseline_strength <= 1e-9:
        return None
    return round(((current_strength - baseline_strength) / baseline_strength) * 100.0, 4)


def _confidence_score(baseline_sample_size: int, recent_sample_size: int, change_magnitude: float) -> float:
    sample_floor = min(baseline_sample_size, recent_sample_size)
    sample_factor = min(1.0, sample_floor / 12.0)
    change_factor = min(1.0, max(0.0, change_magnitude) / 0.75)
    return round(max(0.2, (sample_factor * 0.65) + (change_factor * 0.35)), 4)


def _confidence_level(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "moderate"
    return "limited"


def _system_label_for_columns(left_col: str, right_col: str) -> str:
    text = f"{left_col} {right_col}".lower()
    if any(token in text for token in ("flow", "pressure", "pump", "valve", "air")):
        return "Flow and pressure system"
    if any(token in text for token in ("temp", "heat", "cool", "hvac")):
        return "Thermal response system"
    if any(token in text for token in ("humidity", "moisture", "water")):
        return "Moisture response system"
    if any(token in text for token in ("runtime", "schedule", "energy", "power")):
        return "Schedule and energy system"
    return "Uploaded telemetry"


def _relationship_summary(left_col: str, right_col: str, edge: dict[str, Any]) -> str:
    change_type = str(edge.get("change_type") or "changed").replace("_", " ")
    return (
        f"{left_col} vs {right_col} relationship {change_type}: "
        f"baseline strength={edge['baseline_strength']:.3f}, "
        f"current strength={edge['current_strength']:.3f}, "
        f"correlation delta={edge['correlation_delta']:.3f}."
    )


def _compact(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None and item != "" and item != [] and item != {}
    }


def _relationship_graph(
    *,
    selected_numeric_columns: list[str],
    edges: list[dict[str, Any]],
    sampled_for_baseline: bool,
    column_limited: bool,
) -> dict[str, Any]:
    systems = sorted(
        {
            _system_label_for_columns(
                str(edge.get("supporting_metric_pairs", [{}])[0].get("left", "")),
                str(edge.get("supporting_metric_pairs", [{}])[0].get("right", "")),
            )
            for edge in edges
            if edge.get("supporting_metric_pairs")
        }
    )
    nodes = [
        {"id": f"metric:{column}", "type": "metric", "label": column, "source_column": column}
        for column in selected_numeric_columns
    ]
    nodes.extend(
        {"id": f"system:{system.lower().replace(' ', '_')}", "type": "system", "label": system}
        for system in systems
    )
    changed_edges = [edge for edge in edges if edge.get("change_type") != "stable"]
    return {
        "nodes": nodes,
        "edges": edges,
        "changed_edges": changed_edges,
        "weakened_relationships": [edge for edge in changed_edges if edge.get("change_type") == "weakened"],
        "strengthened_relationships": [edge for edge in changed_edges if edge.get("change_type") == "strengthened"],
        "new_relationships": [edge for edge in changed_edges if edge.get("change_type") == "new"],
        "missing_relationships": [edge for edge in changed_edges if edge.get("change_type") == "missing"],
        "disrupted_relationships": [edge for edge in changed_edges if edge.get("change_type") == "disrupted"],
        "sampled_for_baseline": sampled_for_baseline,
        "relationship_columns_limited": column_limited,
    }

def build_relationship_baseline(
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    *,
    total_row_count: int | None = None,
    baseline_window_limit: int = 12000,
    recent_window_limit: int = 6000,
    max_relationship_columns: int = 32,
) -> dict[str, Any]:
    cumulative_counters = detect_cumulative_counters_from_rows(rows, numeric_columns)
    cumulative_counter_columns = {item["column"] for item in cumulative_counters}
    rows_for_relationships = rows
    relationship_numeric_columns = [column for column in numeric_columns if column not in cumulative_counter_columns]
    if cumulative_counters:
        rows_for_relationships = [dict(row) for row in rows]
        for counter in cumulative_counters:
            column = counter["column"]
            derived = counter["derived_rate_feature"]
            deltas = counter_delta_series([row.get(column) for row in rows])
            usable_delta_count = sum(1 for value in deltas if value is not None)
            if usable_delta_count >= 6:
                relationship_numeric_columns.append(derived)
                counter["derived_rate_feature_analyzed"] = True
                for row, delta in zip(rows_for_relationships, deltas):
                    row[derived] = delta
            else:
                counter["derived_rate_feature_analyzed"] = False
    selected_numeric_columns, column_limited = _select_numeric_columns_for_relationships(
        relationship_numeric_columns,
        max_relationship_columns=max_relationship_columns,
    )
    if len(rows) < 12 or len(selected_numeric_columns) < 2:
        return {
            "top_relationship_changes": [],
            "baseline_relationships": [],
            "relationship_graph": {
                "nodes": [
                    {"id": f"metric:{column}", "type": "metric", "label": column, "source_column": column}
                    for column in selected_numeric_columns
                ],
                "edges": [],
                "changed_edges": [],
                "weakened_relationships": [],
                "strengthened_relationships": [],
                "new_relationships": [],
                "missing_relationships": [],
                "disrupted_relationships": [],
                "sampled_for_baseline": False,
                "relationship_columns_limited": column_limited,
            },
            "sampled_for_baseline": False,
            "relationship_columns_analyzed": len(selected_numeric_columns),
            "relationship_columns_available": len(relationship_numeric_columns),
            "relationship_columns_limited": column_limited,
            "excluded_cumulative_counters": cumulative_counters,
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
    graph_edges: list[dict[str, Any]] = []
    baseline_rows_for_relationships = rows_for_relationships[:baseline_count]
    recent_rows_for_relationships = rows_for_relationships[baseline_count:]
    if len(baseline_rows_for_relationships) > baseline_window_limit:
        baseline_rows_for_relationships = baseline_rows_for_relationships[:baseline_window_limit]
    if len(recent_rows_for_relationships) > recent_window_limit:
        recent_rows_for_relationships = recent_rows_for_relationships[-recent_window_limit:]

    baseline_frame = pd.DataFrame(baseline_rows_for_relationships, columns=selected_numeric_columns).apply(pd.to_numeric, errors="coerce")
    recent_frame = pd.DataFrame(recent_rows_for_relationships, columns=selected_numeric_columns).apply(pd.to_numeric, errors="coerce")
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
            current_strength = abs(float(recent_corr))
            drift = abs(float(recent_corr) - float(baseline_corr))
            change_type = _relationship_change_type(float(baseline_corr), float(recent_corr))
            confidence_score = _confidence_score(baseline_sample_size, recent_sample_size, drift)
            time_window = _source_time_window(source_rows)
            edge = _compact(
                {
                    "id": f"relationship:{left_col}:{right_col}",
                    "source": f"metric:{left_col}",
                    "target": f"metric:{right_col}",
                    "relationship_type": "linear_correlation",
                    "change_type": change_type,
                    "strength": round(float(current_strength), 6),
                    "baseline_strength": round(float(baseline_strength), 6),
                    "current_strength": round(float(current_strength), 6),
                    "direction": _relationship_direction(float(baseline_corr), float(recent_corr)),
                    "confidence": confidence_score,
                    "confidence_level": _confidence_level(confidence_score),
                    "baseline_correlation": round(float(baseline_corr), 6),
                    "recent_correlation": round(float(recent_corr), 6),
                    "correlation_delta": round(float(drift), 6),
                    "signed_correlation_delta": round(float(recent_corr) - float(baseline_corr), 6),
                    "change_percentage": _change_percentage(baseline_strength, current_strength),
                    "supporting_metric_pairs": [
                        {
                            "left": left_col,
                            "right": right_col,
                            "baseline_correlation": round(float(baseline_corr), 6),
                            "recent_correlation": round(float(recent_corr), 6),
                            "baseline_sample_size": baseline_sample_size,
                            "recent_sample_size": recent_sample_size,
                        }
                    ],
                    "time_window": time_window,
                    "source_rows": source_rows,
                }
            )
            graph_edges.append(edge)

            if change_type == "stable" or drift < 0.25:
                continue

            candidates.append(
                {
                    "relationship": f"{left_col} <-> {right_col}",
                    "baseline_correlation": round(float(baseline_corr), 6),
                    "recent_correlation": round(float(recent_corr), 6),
                    "correlation_delta": round(float(drift), 6),
                    "signed_correlation_delta": round(float(recent_corr) - float(baseline_corr), 6),
                    "coupling_strength": round(float(baseline_strength), 6),
                    "relationship_type": "linear_correlation",
                    "change_type": change_type,
                    "strength": round(float(current_strength), 6),
                    "baseline_strength": round(float(baseline_strength), 6),
                    "current_strength": round(float(current_strength), 6),
                    "direction": edge.get("direction"),
                    "confidence_score": confidence_score,
                    "confidence_level": _confidence_level(confidence_score),
                    "change_percentage": edge.get("change_percentage"),
                    "supporting_metric_pairs": edge.get("supporting_metric_pairs"),
                    "time_window": time_window,
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
                    "summary": _relationship_summary(left_col, right_col, edge),
                }
            )

    candidates.sort(key=lambda item: (item["correlation_delta"], item["coupling_strength"]), reverse=True)
    graph_edges.sort(key=lambda item: (abs(float(item.get("correlation_delta") or 0)), float(item.get("baseline_strength") or 0)), reverse=True)
    graph = _relationship_graph(
        selected_numeric_columns=selected_numeric_columns,
        edges=graph_edges,
        sampled_for_baseline=sampled_for_baseline,
        column_limited=column_limited,
    )
    return {
        "top_relationship_changes": candidates[:5],
        "baseline_relationships": candidates,
        "relationship_graph": graph,
        "sampled_for_baseline": sampled_for_baseline,
        "relationship_columns_analyzed": len(selected_numeric_columns),
        "relationship_columns_available": len(relationship_numeric_columns),
        "relationship_columns_limited": column_limited,
        "excluded_cumulative_counters": cumulative_counters,
    }


# Compatibility alias for internal callers migrating from upload_jobs.
_build_relationship_baseline = build_relationship_baseline
