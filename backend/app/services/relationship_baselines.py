from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.services.cumulative_counters import (
    counter_delta_series,
    detect_cumulative_counters_from_rows,
)
from app.services.telemetry_classification import (
    NON_OPERATOR_RELATIONSHIP_CATEGORIES,
    classify_relationship_columns,
    signal_classification,
    signal_display_name,
    signal_metadata,
    telemetry_catalog_by_column,
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
    pair = f"{left_col} and {right_col}"
    if change_type == "missing":
        return f"The historical relationship between {pair} no longer follows its established operating pattern."
    if change_type == "weakened":
        return f"The historical relationship between {pair} weakened substantially during the analysis window."
    if change_type in {"disrupted", "inverted"}:
        return f"The historical relationship between {pair} shifted from its established operating pattern."
    if change_type == "new":
        return f"A new operating relationship between {pair} emerged during the analysis window and should be checked against operating changes."
    if change_type == "strengthened":
        return f"{pair} became more tightly coupled than their historical operating pattern."
    return f"The relationship between {pair} changed significantly from baseline operation."


def _baseline_drift_lookup(baseline_analysis: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(baseline_analysis, dict):
        return {}
    return {
        str(item.get("column")): item
        for item in baseline_analysis.get("column_drift", [])
        if isinstance(item, dict) and item.get("column")
    }


def _score_number(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback
    if number > 1.0 and number <= 100.0:
        number = number / 100.0
    return max(0.0, min(1.0, number))


def _severity_factor_for_columns(columns: list[str], baseline_drift_by_column: dict[str, dict[str, Any]]) -> float:
    factors: list[float] = []
    for column in columns:
        drift = baseline_drift_by_column.get(column, {})
        flag = str(drift.get("drift_flag") or "").lower()
        if flag == "review":
            factors.append(1.0)
        elif flag == "watch":
            factors.append(0.65)
        elif flag == "context":
            factors.append(0.25)
        text = column.lower()
        if "vibration" in text:
            factors.append(1.0)
        elif any(token in text for token in ("power", "kw", "amp", "current")):
            factors.append(0.85)
        elif any(token in text for token in ("pressure", "flow", "temp", "thermal", "fouling")):
            factors.append(0.7)
    return max(factors) if factors else 0.35


def _system_factor_for_columns(columns: list[str]) -> float:
    systems = {_system_label_for_columns(column, "") for column in columns}
    return min(1.0, (len(systems) * 0.35) + (len(set(columns)) * 0.15))


def _novelty_factor(change_type: Any) -> float:
    normalized = str(change_type or "").lower()
    if normalized in {"disrupted", "missing", "new"}:
        return 1.0
    if normalized in {"weakened", "strengthened"}:
        return 0.8
    if normalized == "stable":
        return 0.2
    return 0.55


def score_relationship_importance(
    columns: list[str],
    edge: dict[str, Any],
    baseline_drift_by_column: dict[str, dict[str, Any]] | None = None,
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    clean_columns = [str(column) for column in columns if str(column or "").strip()]
    baseline_drift_by_column = baseline_drift_by_column or {}
    classification = classify_relationship_columns(clean_columns, telemetry_signal_catalog=telemetry_signal_catalog)
    delta_factor = min(1.0, abs(float(edge.get("correlation_delta") or 0.0)))
    confidence_factor = _score_number(edge.get("confidence_score", edge.get("confidence")), 0.5)
    try:
        minimum_samples = min(int(edge.get("baseline_sample_size") or 0), int(edge.get("recent_sample_size") or 0))
    except (TypeError, ValueError):
        minimum_samples = 0
    persistence_factor = min(1.0, minimum_samples / 24.0)
    downstream_factor = _system_factor_for_columns(clean_columns)
    severity_factor = _severity_factor_for_columns(clean_columns, baseline_drift_by_column)
    novelty_factor = _novelty_factor(edge.get("change_type"))
    data_quality_factor = min(confidence_factor, max(0.2, persistence_factor))
    equipment_factor = 1.0 if classification["equipment_process_involved"] else 0.25

    weighted = (
        delta_factor * 0.22
        + confidence_factor * 0.16
        + persistence_factor * 0.12
        + downstream_factor * 0.10
        + severity_factor * 0.16
        + novelty_factor * 0.09
        + data_quality_factor * 0.08
        + equipment_factor * 0.07
    )
    context_explanation_factor = 1.0
    if classification["context_only"]:
        context_explanation_factor = 0.35
    elif classification["context_driver_involved"]:
        context_explanation_factor = 0.82

    score = max(0.0, min(100.0, weighted * 100.0 * context_explanation_factor))
    if classification["context_only"]:
        score = min(score, 34.0)

    factors = {
        "magnitude": round(delta_factor, 4),
        "confidence": round(confidence_factor, 4),
        "persistence": round(persistence_factor, 4),
        "downstream_scope": round(downstream_factor, 4),
        "affected_metric_severity": round(severity_factor, 4),
        "novelty": round(novelty_factor, 4),
        "data_quality": round(data_quality_factor, 4),
        "equipment_process_involvement": round(equipment_factor, 4),
        "context_explanation_factor": round(context_explanation_factor, 4),
    }
    rationale = _relationship_importance_rationale(clean_columns, classification, edge, factors)
    return {
        "relationship_importance_score": round(score, 4),
        "relationship_importance_rationale": rationale,
        "ranking_factors": factors,
        "column_classifications": classification["column_classifications"],
        "relationship_context": {
            "context_only": classification["context_only"],
            "equipment_process_involved": classification["equipment_process_involved"],
            "context_driver_involved": classification["context_driver_involved"],
            "state_signal_involved": classification.get("state_signal_involved", False),
            "operator_primary_eligible": classification.get("operator_primary_eligible", True),
            "blocked_operator_categories": classification.get("blocked_operator_categories", []),
        },
    }


def _relationship_importance_rationale(
    columns: list[str],
    classification: dict[str, Any],
    edge: dict[str, Any],
    factors: dict[str, float],
) -> str:
    label = " / ".join(columns) if columns else "This relationship"
    change_type = str(edge.get("change_type") or "changed").replace("_", " ")
    if classification["context_only"]:
        return (
            f"Down-ranked because {label} is made up of scheduled/load/context or environmental drivers. "
            "Detailed relationship statistics are retained in evidence, but this is less likely to indicate equipment health by itself."
        )
    if classification["context_driver_involved"]:
        return (
            f"This relationship is useful because {label} {change_type} while equipment/process telemetry is involved. "
            "Context/load movement may explain part of the change, so Neraium treats it as supporting subsystem evidence."
        )
    return (
        f"This relationship is important because {label} {change_type} while equipment/process signals changed together, "
        "which can indicate subsystem behavior changing before a single sensor explains it."
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
    telemetry_signal_catalog: dict[str, dict[str, Any]] | None = None,
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
        {
            "id": f"metric:{column}",
            "type": "metric",
            "label": signal_display_name(column, telemetry_signal_catalog),
            "source_column": column,
            "display_name": signal_display_name(column, telemetry_signal_catalog),
            "telemetry_metadata": signal_metadata(column, telemetry_signal_catalog),
        }
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
    baseline_analysis: dict[str, Any] | None = None,
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    signal_catalog = telemetry_catalog_by_column(telemetry_signal_catalog)
    cumulative_counters = detect_cumulative_counters_from_rows(rows, numeric_columns)
    cumulative_counter_columns = {item["column"] for item in cumulative_counters}
    rows_for_relationships = rows
    excluded_structural_columns: list[dict[str, Any]] = []
    relationship_numeric_columns = []
    for column in numeric_columns:
        classification = signal_classification(column, signal_catalog)
        if column in cumulative_counter_columns or classification.get("category") in NON_OPERATOR_RELATIONSHIP_CATEGORIES or classification.get("is_ignored"):
            excluded_structural_columns.append(
                {
                    "column": column,
                    "display_name": signal_display_name(column, signal_catalog),
                    "telemetry_category": classification.get("category"),
                    "structural_class": classification.get("structural_class"),
                    "reason": classification.get("reason"),
                }
            )
            continue
        relationship_numeric_columns.append(column)
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
            "excluded_structural_columns": excluded_structural_columns,
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
    baseline_drift_by_column = _baseline_drift_lookup(baseline_analysis)
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
                            "left_display_name": signal_display_name(left_col, signal_catalog),
                            "right_display_name": signal_display_name(right_col, signal_catalog),
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
            display_columns = [signal_display_name(left_col, signal_catalog), signal_display_name(right_col, signal_catalog)]
            importance = score_relationship_importance([left_col, right_col], edge, baseline_drift_by_column, signal_catalog)
            edge.update(importance)
            edge["display_columns"] = display_columns
            edge["source_column_metadata"] = [signal_metadata(left_col, signal_catalog), signal_metadata(right_col, signal_catalog)]
            graph_edges.append(edge)

            relationship_context = edge.get("relationship_context") if isinstance(edge.get("relationship_context"), dict) else {}
            if change_type == "stable" or drift < 0.25 or relationship_context.get("operator_primary_eligible") is False:
                continue

            candidates.append(
                {
                    "relationship": f"{left_col} <-> {right_col}",
                    "display_relationship": f"{display_columns[0]} <-> {display_columns[1]}",
                    "display_columns": display_columns,
                    "source_column_metadata": edge.get("source_column_metadata"),
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
                    "relationship_importance_score": edge.get("relationship_importance_score"),
                    "relationship_importance_rationale": edge.get("relationship_importance_rationale"),
                    "ranking_factors": edge.get("ranking_factors"),
                    "column_classifications": edge.get("column_classifications"),
                    "relationship_context": edge.get("relationship_context"),
                    "evidence_refs": [
                        {
                            "column": left_col,
                            "display_name": signal_display_name(left_col, signal_catalog),
                            "role": "left_variable",
                            "baseline_window": {"rows": baseline_sample_size, "correlation": round(float(baseline_corr), 6)},
                            "recent_window": {"rows": recent_sample_size, "correlation": round(float(recent_corr), 6)},
                            "source_rows": source_rows,
                        },
                        {
                            "column": right_col,
                            "display_name": signal_display_name(right_col, signal_catalog),
                            "role": "right_variable",
                            "baseline_window": {"rows": baseline_sample_size, "correlation": round(float(baseline_corr), 6)},
                            "recent_window": {"rows": recent_sample_size, "correlation": round(float(recent_corr), 6)},
                            "source_rows": source_rows,
                        },
                    ],
                    "source_rows": source_rows,
                    "summary": _relationship_summary(display_columns[0], display_columns[1], edge),
                }
            )

    candidates.sort(key=lambda item: (float(item.get("relationship_importance_score") or 0), item["correlation_delta"], item["coupling_strength"]), reverse=True)
    graph_edges.sort(key=lambda item: (float(item.get("relationship_importance_score") or 0), abs(float(item.get("correlation_delta") or 0)), float(item.get("baseline_strength") or 0)), reverse=True)
    graph = _relationship_graph(
        selected_numeric_columns=selected_numeric_columns,
        edges=graph_edges,
        sampled_for_baseline=sampled_for_baseline,
        column_limited=column_limited,
        telemetry_signal_catalog=signal_catalog,
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
        "excluded_structural_columns": excluded_structural_columns,
    }


# Compatibility alias for internal callers migrating from upload_jobs.
_build_relationship_baseline = build_relationship_baseline
