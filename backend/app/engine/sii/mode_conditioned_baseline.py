from __future__ import annotations

import time
from itertools import combinations
from typing import Any

from app.engine.sii.common import (
    clamp,
    module_envelope,
    numeric_values,
    paired_values,
    pearson,
    relationship_columns,
)
from app.services.operating_modes import (
    context_signals,
    describe_mode,
    numeric_band_references,
)

DEFAULT_CONFIG = {
    "baseline_fraction": 0.70,
    "minimum_baseline_rows": 12,
    "minimum_recent_rows": 6,
    "minimum_pair_count": 3,
    "maximum_relationship_columns": 32,
    "minimum_recent_mode_purity": 0.70,
}


def analyze_mode_conditioned_baseline(
    *,
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
    relationship_model: dict[str, Any] | None = None,
    operating_mode: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Select historical rows that match the recent explicit operating mode.

    The global Phase 1 comparison remains available as compatibility evidence.
    This module exposes a separate like-for-like relationship comparison and
    never silently falls back while claiming mode conditioning succeeded.
    """

    started = time.perf_counter()
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    split_index = max(1, min(len(rows) - 1, int(len(rows) * float(cfg["baseline_fraction"])))) if len(rows) >= 2 else 0
    historical_rows = rows[:split_index]
    recent_rows = rows[split_index:]
    signals = context_signals(rows, timestamp_column, telemetry_signal_catalog) if rows else []
    references = numeric_band_references(rows, signals)
    recent_descriptor = describe_mode(recent_rows, signals, references, timestamp_column) if recent_rows else {
        "mode_id": "unavailable",
        "mode_label": "Operating context unavailable",
        "features": {},
        "explicit_features": [],
    }
    target_features = {
        feature: recent_descriptor["features"].get(feature)
        for feature in dict.fromkeys(recent_descriptor.get("explicit_features", []))
        if recent_descriptor["features"].get(feature) is not None
    }
    recent_feature_support = _recent_feature_support(
        recent_rows,
        signals=signals,
        references=references,
        timestamp_column=timestamp_column,
        target_features=target_features,
    )
    minimum_feature_support = min(recent_feature_support.values(), default=0.0)
    ambiguous_recent_mode = bool(
        target_features
        and minimum_feature_support < float(cfg["minimum_recent_mode_purity"])
    )
    selected_rows: list[dict[str, Any]] = []
    selected_indices: list[int] = []
    match_scores: list[float] = []
    if target_features:
        for index, row in enumerate(historical_rows):
            descriptor = describe_mode([row], signals, references, timestamp_column)
            features = descriptor.get("features", {})
            comparable = [feature for feature in target_features if feature in features]
            score = (
                sum(features[feature] == target_features[feature] for feature in comparable)
                / max(1, len(target_features))
            )
            if comparable and len(comparable) == len(target_features) and score == 1.0:
                selected_rows.append(row)
                selected_indices.append(index)
                match_scores.append(score)

    minimum_baseline = int(cfg["minimum_baseline_rows"])
    minimum_recent = int(cfg["minimum_recent_rows"])
    if not target_features:
        fallback_reason = "no_explicit_operating_mode_features"
    elif len(recent_rows) < minimum_recent:
        fallback_reason = "insufficient_recent_mode_rows"
    elif ambiguous_recent_mode:
        fallback_reason = "ambiguous_recent_operating_mode"
    elif len(selected_rows) < minimum_baseline:
        fallback_reason = "insufficient_like_mode_historical_rows"
    else:
        fallback_reason = None

    selection_confidence = _selection_confidence(
        target_features=target_features,
        recent_rows=len(recent_rows),
        minimum_recent_rows=minimum_recent,
        minimum_feature_support=minimum_feature_support,
        fallback_reason=fallback_reason,
    )
    selected_operating_mode = {
        "mode_id": recent_descriptor.get("mode_id"),
        "mode_label": recent_descriptor.get("mode_label"),
        "features": target_features,
        "feature_support": recent_feature_support,
        "minimum_feature_support": round(minimum_feature_support, 6),
        "ambiguous": ambiguous_recent_mode,
        "confidence": round(selection_confidence, 6),
        "confidence_level": _confidence_level(selection_confidence),
        "reported_recent_mode": (operating_mode or {}).get("recent_mode"),
    }

    limitations: list[str] = []
    if fallback_reason:
        limitations.append(
            "Mode-conditioned evidence was not substituted for the global comparison; the fallback is explicit."
        )
        metrics = {
            "historical_rows": len(historical_rows),
            "recent_rows": len(recent_rows),
            "selected_baseline_rows": len(selected_rows),
            "selection_fraction": round(len(selected_rows) / max(1, len(historical_rows)), 6),
            "relationship_edge_count": 0,
        }
        envelope = module_envelope(
            started=started,
            status="limited",
            reason=fallback_reason,
            inputs_used=["ordered_rows", "operating_mode_features", "telemetry_signal_catalog"],
            rows_used=len(selected_rows) + len(recent_rows),
            columns_used=numeric_columns,
            assumptions=[
                "Only exact matches across every available explicit recent-mode feature are selected.",
                "Mode labels are deterministic telemetry context, not physical operating-state diagnoses.",
            ],
            output_metrics=metrics,
            limitations=limitations,
        )
        return {
            **envelope,
            "method": "exact_like_mode_historical_selection_v1",
            "used_global_fallback": True,
            "fallback_reason": fallback_reason,
            "selection_confidence": round(selection_confidence, 6),
            "selection_confidence_level": _confidence_level(selection_confidence),
            "selected_operating_mode": selected_operating_mode,
            "global_relationship_model": relationship_model or {},
            "recent_mode": recent_descriptor,
            "target_features": target_features,
            "selection": {
                "historical_start_index": 0,
                "historical_end_index_exclusive": split_index,
                "recent_start_index": split_index,
                "recent_end_index_exclusive": len(rows),
                "selected_historical_indices": selected_indices,
                "selected_baseline_rows": len(selected_rows),
                "recent_rows": len(recent_rows),
                "minimum_baseline_rows": minimum_baseline,
                "minimum_recent_rows": minimum_recent,
                "recent_feature_support": recent_feature_support,
                "minimum_recent_mode_purity": float(cfg["minimum_recent_mode_purity"]),
            },
            "mode_relationships": {"nodes": [], "edges": []},
            "mode_signal_drift": [],
        }

    source_edges = _source_edges(relationship_model)
    pairs = _candidate_pairs(source_edges, numeric_columns, int(cfg["maximum_relationship_columns"]))
    edges = []
    for left, right in pairs:
        baseline_pairs = paired_values(selected_rows, left, right)
        recent_pairs = paired_values(recent_rows, left, right)
        baseline_correlation = pearson(baseline_pairs)
        recent_correlation = pearson(recent_pairs)
        if baseline_correlation is None or recent_correlation is None:
            continue
        if len(baseline_pairs) < int(cfg["minimum_pair_count"]) or len(recent_pairs) < int(cfg["minimum_pair_count"]):
            continue
        raw_edge = _matching_edge(source_edges, left, right)
        edges.append(
            _conditioned_edge(
                raw_edge,
                left=left,
                right=right,
                baseline_correlation=baseline_correlation,
                recent_correlation=recent_correlation,
                baseline_count=len(baseline_pairs),
                recent_count=len(recent_pairs),
                recent_mode=recent_descriptor,
                selected_rows=selected_rows,
                recent_rows=recent_rows,
                timestamp_column=timestamp_column,
            )
        )

    signal_drift = _mode_signal_drift(selected_rows, recent_rows, numeric_columns)
    nodes = [
        {"id": f"metric:{column}", "type": "metric", "label": column, "source_column": column}
        for column in sorted({column for edge in edges for column in relationship_columns(edge)})
    ]
    limitations = [] if edges else ["No numeric relationship pair had enough like-mode values in both windows."]
    status = "complete" if edges or signal_drift else "limited"
    reason = None if status == "complete" else "no_comparable_like_mode_metrics"
    metrics = {
        "historical_rows": len(historical_rows),
        "recent_rows": len(recent_rows),
        "selected_baseline_rows": len(selected_rows),
        "selection_fraction": round(len(selected_rows) / max(1, len(historical_rows)), 6),
        "relationship_edge_count": len(edges),
        "signal_comparison_count": len(signal_drift),
    }
    envelope = module_envelope(
        started=started,
        status=status,
        reason=reason,
        inputs_used=[
            "ordered_rows",
            "recent_explicit_operating_mode",
            "telemetry_signal_catalog",
            "global_relationship_model_edge_set",
        ],
        rows_used=len(selected_rows) + len(recent_rows),
        columns_used=numeric_columns,
        assumptions=[
            "Only exact matches across every available explicit recent-mode feature are selected.",
            "Selected baseline rows precede every recent comparison row.",
            "Relationships remain non-causal Pearson evidence.",
        ],
        output_metrics=metrics,
        limitations=limitations,
    )
    return {
        **envelope,
        "method": "exact_like_mode_historical_selection_v1",
        "used_global_fallback": False,
        "fallback_reason": None,
        "selection_confidence": round(selection_confidence, 6),
        "selection_confidence_level": _confidence_level(selection_confidence),
        "selected_operating_mode": selected_operating_mode,
        "recent_mode": recent_descriptor,
        "target_features": target_features,
        "selection": {
            "historical_start_index": 0,
            "historical_end_index_exclusive": split_index,
            "recent_start_index": split_index,
            "recent_end_index_exclusive": len(rows),
            "selected_historical_indices": selected_indices,
            "selected_baseline_rows": len(selected_rows),
            "recent_rows": len(recent_rows),
            "minimum_baseline_rows": minimum_baseline,
            "minimum_recent_rows": minimum_recent,
            "recent_feature_support": recent_feature_support,
            "minimum_recent_mode_purity": float(cfg["minimum_recent_mode_purity"]),
        },
        "mode_relationships": {
            "nodes": nodes,
            "edges": edges,
            "changed_edges": [edge for edge in edges if edge["change_type"] != "stable"],
            "baseline_mode": recent_descriptor["mode_id"],
            "recent_mode": recent_descriptor["mode_id"],
            "comparison": "like_for_like",
        },
        "mode_signal_drift": signal_drift,
    }


def _recent_feature_support(
    rows: list[dict[str, Any]],
    *,
    signals: list[Any],
    references: dict[str, tuple[float, float]],
    timestamp_column: str | None,
    target_features: dict[str, Any],
) -> dict[str, float]:
    if not rows or not target_features:
        return {}
    matches = {feature: 0 for feature in target_features}
    for row in rows:
        descriptor = describe_mode([row], signals, references, timestamp_column)
        features = descriptor.get("features", {})
        for feature, target in target_features.items():
            if features.get(feature) == target:
                matches[feature] += 1
    return {
        feature: round(count / len(rows), 6)
        for feature, count in matches.items()
    }


def _selection_confidence(
    *,
    target_features: dict[str, Any],
    recent_rows: int,
    minimum_recent_rows: int,
    minimum_feature_support: float,
    fallback_reason: str | None,
) -> float:
    if not target_features or recent_rows <= 0:
        return 0.0
    sample_factor = min(1.0, recent_rows / max(1, minimum_recent_rows * 2))
    feature_factor = min(1.0, 0.70 + 0.15 * len(target_features))
    confidence = clamp(minimum_feature_support * sample_factor * feature_factor)
    if fallback_reason == "ambiguous_recent_operating_mode":
        confidence = min(confidence, 0.25)
    elif fallback_reason:
        confidence = min(confidence, 0.35)
    return confidence


def _confidence_level(confidence: float) -> str:
    return "high" if confidence >= 0.75 else "moderate" if confidence >= 0.45 else "limited"


def _source_edges(relationship_model: dict[str, Any] | None) -> list[dict[str, Any]]:
    graph = relationship_model.get("relationship_graph") if isinstance(relationship_model, dict) else None
    return [edge for edge in graph.get("edges", []) if isinstance(edge, dict)] if isinstance(graph, dict) else []


def _candidate_pairs(
    source_edges: list[dict[str, Any]], numeric_columns: list[str], maximum_columns: int
) -> list[tuple[str, str]]:
    pairs = []
    for edge in source_edges:
        columns = relationship_columns(edge)
        if len(columns) == 2 and tuple(columns) not in pairs:
            pairs.append(tuple(columns))
    if pairs:
        return pairs
    selected = numeric_columns[: max(0, maximum_columns)]
    return list(combinations(selected, 2))


def _matching_edge(source_edges: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    target = {left, right}
    return next((dict(edge) for edge in source_edges if set(relationship_columns(edge)) == target), {})


def _conditioned_edge(
    raw_edge: dict[str, Any],
    *,
    left: str,
    right: str,
    baseline_correlation: float,
    recent_correlation: float,
    baseline_count: int,
    recent_count: int,
    recent_mode: dict[str, Any],
    selected_rows: list[dict[str, Any]],
    recent_rows: list[dict[str, Any]],
    timestamp_column: str | None,
) -> dict[str, Any]:
    delta = abs(recent_correlation - baseline_correlation)
    confidence = max(0.2, 0.65 * min(1.0, min(baseline_count, recent_count) / 12.0) + 0.35 * min(1.0, delta / 0.75))
    baseline_strength = abs(baseline_correlation)
    current_strength = abs(recent_correlation)
    change_type = _change_type(baseline_correlation, recent_correlation)
    source_rows = _conditioned_source_rows(selected_rows, recent_rows, timestamp_column)
    time_window = {
        key: anchor.get("timestamp")
        for key, label in (
            ("baseline_start", "baseline_start"),
            ("baseline_end", "baseline_end"),
            ("current_start", "current_start"),
            ("current_end", "current_end"),
        )
        if (anchor := next((item for item in source_rows if item["window"] == label), {})).get("timestamp")
    }
    return {
        **raw_edge,
        "id": raw_edge.get("id") or f"mode_relationship:{left}:{right}",
        "source": f"metric:{left}",
        "target": f"metric:{right}",
        "columns": [left, right],
        "relationship": f"{left} <-> {right}",
        "relationship_type": "mode_conditioned_linear_correlation",
        "comparison": "like_for_like_operating_mode",
        "change_type": change_type,
        "baseline_correlation": round(baseline_correlation, 6),
        "recent_correlation": round(recent_correlation, 6),
        "current_correlation": round(recent_correlation, 6),
        "baseline_strength": round(baseline_strength, 6),
        "current_strength": round(current_strength, 6),
        "correlation_delta": round(delta, 6),
        "signed_correlation_delta": round(recent_correlation - baseline_correlation, 6),
        "confidence": round(clamp(confidence), 6),
        "confidence_level": "high" if confidence >= 0.75 else "moderate" if confidence >= 0.45 else "limited",
        "baseline_sample_count": baseline_count,
        "current_sample_count": recent_count,
        "baseline_sample_size": baseline_count,
        "recent_sample_size": recent_count,
        "time_window": time_window,
        "source_rows": source_rows,
        "supporting_metric_pairs": [
            {
                "left": left,
                "right": right,
                "baseline_correlation": round(baseline_correlation, 6),
                "recent_correlation": round(recent_correlation, 6),
                "baseline_sample_size": baseline_count,
                "recent_sample_size": recent_count,
            }
        ],
        "mode_conditioning": {
            "mode_id": recent_mode.get("mode_id"),
            "mode_label": recent_mode.get("mode_label"),
            "features": recent_mode.get("features", {}),
        },
    }


def _conditioned_source_rows(
    selected_rows: list[dict[str, Any]],
    recent_rows: list[dict[str, Any]],
    timestamp_column: str | None,
) -> list[dict[str, Any]]:
    anchors = []
    for label, row in (
        ("baseline_start", selected_rows[0] if selected_rows else None),
        ("baseline_end", selected_rows[-1] if selected_rows else None),
        ("current_start", recent_rows[0] if recent_rows else None),
        ("current_end", recent_rows[-1] if recent_rows else None),
    ):
        if row is None:
            continue
        timestamp = row.get("__source_timestamp") or (row.get(timestamp_column) if timestamp_column else None)
        anchors.append(
            {
                "window": label,
                "source_row": row.get("__source_row_number"),
                "timestamp": str(timestamp) if timestamp is not None else None,
            }
        )
    return anchors


def _change_type(baseline: float, recent: float) -> str:
    baseline_strength = abs(baseline)
    current_strength = abs(recent)
    if baseline_strength >= 0.35 and current_strength >= 0.35 and (baseline > 0) != (recent > 0):
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


def _mode_signal_drift(
    baseline_rows: list[dict[str, Any]], recent_rows: list[dict[str, Any]], columns: list[str]
) -> list[dict[str, Any]]:
    output = []
    for column in columns:
        baseline = numeric_values(baseline_rows, column)
        recent = numeric_values(recent_rows, column)
        if len(baseline) < 3 or len(recent) < 3:
            continue
        baseline_mean = sum(baseline) / len(baseline)
        recent_mean = sum(recent) / len(recent)
        absolute_change = recent_mean - baseline_mean
        floor = max(0.05 * abs(baseline_mean), 0.01)
        output.append(
            {
                "column": column,
                "baseline_mean": round(baseline_mean, 6),
                "recent_mean": round(recent_mean, 6),
                "absolute_change": round(absolute_change, 6),
                "normalized_change": round(abs(absolute_change) / floor, 6),
                "direction": "up" if absolute_change > floor else "down" if absolute_change < -floor else "flat",
                "baseline_sample_count": len(baseline),
                "recent_sample_count": len(recent),
            }
        )
    return output
