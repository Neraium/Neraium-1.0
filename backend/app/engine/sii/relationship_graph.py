from __future__ import annotations

import time
from collections import Counter, defaultdict, deque
from typing import Any

from app.engine.sii.common import (
    EPSILON,
    clamp,
    confidence_number,
    module_envelope,
    relationship_columns,
)
from app.services.telemetry_classification import telemetry_catalog_by_column

DEFAULT_CONFIG = {
    "change_inclusion_threshold": 0.25,
    "density_inclusion_threshold": 0.10,
    "minimum_edge_confidence": 0.45,
    "minimum_data_quality_factor": 0.35,
    "minimum_component_coherence": 0.62,
    "minimum_component_edges": 2,
    "minimum_persistence_observations": 6,
}


def analyze_relationship_graph(
    *,
    relationship_model: dict[str, Any],
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
    sensor_health: dict[str, Any] | None = None,
    data_quality: dict[str, Any] | None = None,
    operating_mode: dict[str, Any] | None = None,
    mode_conditioned_analysis: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Build non-causal graph evidence from existing Pearson relationship edges."""

    started = time.perf_counter()
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    limitations: list[str] = []
    catalog = telemetry_catalog_by_column(telemetry_signal_catalog)
    source_graph = relationship_model.get("relationship_graph") if isinstance(relationship_model, dict) else None
    source_edges = source_graph.get("edges", []) if isinstance(source_graph, dict) else []
    mode_relationships = (
        mode_conditioned_analysis.get("mode_relationships")
        if isinstance(mode_conditioned_analysis, dict)
        else None
    )
    if (
        isinstance(mode_conditioned_analysis, dict)
        and not mode_conditioned_analysis.get("used_global_fallback")
        and isinstance(mode_relationships, dict)
        and isinstance(mode_relationships.get("edges"), list)
        and bool(mode_relationships.get("edges"))
    ):
        source_edges = mode_relationships.get("edges", [])
        edge_basis = "mode_conditioned_relationships"
    else:
        edge_basis = "global_relationship_model"
        if isinstance(mode_conditioned_analysis, dict) and mode_conditioned_analysis.get("used_global_fallback"):
            limitations.append(
                f"Mode-conditioned relationships unavailable: {mode_conditioned_analysis.get('fallback_reason') or 'global fallback used'}."
            )
        elif isinstance(mode_conditioned_analysis, dict) and not mode_conditioned_analysis.get("used_global_fallback"):
            limitations.append("Mode-conditioned selection produced no eligible relationship edges; global relationship edges were retained.")

    health_by_signal = _health_by_signal(sensor_health)
    global_quality = _global_quality_factor(data_quality)
    enriched_edges: list[dict[str, Any]] = []
    eligible_edges: list[dict[str, Any]] = []
    promoted_edges: list[dict[str, Any]] = []
    edge_candidates = source_edges if isinstance(source_edges, list) else []
    if progress_callback:
        progress_callback(0, len(edge_candidates))
    for edge_index, raw_edge in enumerate(edge_candidates, start=1):
        if not isinstance(raw_edge, dict):
            if progress_callback:
                progress_callback(edge_index, len(edge_candidates))
            continue
        edge = _enrich_edge(
            raw_edge,
            catalog=catalog,
            health_by_signal=health_by_signal,
            global_quality=global_quality,
            operating_mode=operating_mode or {},
            minimum_persistence_observations=int(cfg["minimum_persistence_observations"]),
        )
        enriched_edges.append(edge)
        if not edge["eligible"]:
            if progress_callback:
                progress_callback(edge_index, len(edge_candidates))
            continue
        eligible_edges.append(edge)
        if _promoted(edge, cfg):
            edge["promoted_changed_edge"] = True
            promoted_edges.append(edge)
        if progress_callback:
            progress_callback(edge_index, len(edge_candidates))

    metric_nodes = sorted({column for edge in eligible_edges for column in edge["columns"]})
    subsystem_by_metric = {
        column: subsystem
        for column in metric_nodes
        if (subsystem := _catalog_subsystem(catalog.get(column, {})))
    }
    nodes = [_metric_node(column, catalog.get(column, {}), subsystem_by_metric.get(column)) for column in metric_nodes]
    nodes.extend(
        {
            "id": f"subsystem:{_safe_id(subsystem)}",
            "type": "subsystem",
            "label": subsystem,
            "classification_source": "telemetry_catalog",
        }
        for subsystem in sorted(set(subsystem_by_metric.values()))
    )

    total_eligible = len(eligible_edges)
    changed_edge_fraction = len(promoted_edges) / max(total_eligible, 1)
    confidence_sum = sum(edge["edge_confidence"] for edge in eligible_edges)
    weighted_edge_displacement = sum(edge["edge_displacement"] for edge in eligible_edges) / max(
        confidence_sum, EPSILON
    )
    node_scores = _node_disruption(metric_nodes, promoted_edges)
    components = _changed_components(
        promoted_edges,
        subsystem_by_metric=subsystem_by_metric,
        minimum_coherence=float(cfg["minimum_component_coherence"]),
        minimum_edges=int(cfg["minimum_component_edges"]),
    )
    weighted_degree = _weighted_degree(metric_nodes, eligible_edges)
    density = _density_change(
        metric_nodes,
        eligible_edges,
        inclusion_threshold=float(cfg["density_inclusion_threshold"]),
    )
    subsystem_concentration = _subsystem_concentration(promoted_edges, subsystem_by_metric)
    if subsystem_concentration["status"] == "limited":
        limitations.append(subsystem_concentration["reason"])

    metrics = {
        "changed_edge_fraction": round(changed_edge_fraction, 6),
        "changed_eligible_edges": len(promoted_edges),
        "total_eligible_edges": total_eligible,
        "weighted_edge_displacement": round(weighted_edge_displacement, 6),
        "most_disrupted_nodes": node_scores[:10],
        "component_count": len(components),
        "coherent_component_count": sum(1 for component in components if component["coherent"]),
        "component_sizes": [component["edge_count"] for component in components],
        "weighted_degree_change": weighted_degree,
        "graph_density_change": density,
        "subsystem_concentration": subsystem_concentration,
    }
    status = "complete" if eligible_edges else "limited"
    reason = None if eligible_edges else "no_eligible_relationship_edges"
    envelope = module_envelope(
        started=started,
        status=status,
        reason=reason,
        inputs_used=[
            "relationship_model.relationship_graph.edges",
            edge_basis,
            "telemetry_signal_catalog",
            "sensor_health",
            "data_quality",
            "operating_mode",
        ],
        rows_used=max(
            [
                int(edge.get("baseline_sample_count") or 0) + int(edge.get("current_sample_count") or 0)
                for edge in eligible_edges
            ]
            or [0]
        ),
        columns_used=metric_nodes,
        assumptions=[
            "Edges are non-causal association evidence; no graph metric establishes causality.",
            "Only telemetry-catalog subsystem metadata is used; subsystem labels are never inferred from signal names.",
            "Promoted edges meet deterministic change, confidence, and data-quality floors.",
        ],
        output_metrics=metrics,
        limitations=limitations,
    )
    return {
        **envelope,
        "method": "deterministic_dynamic_relationship_graph_v1",
        "edge_basis": edge_basis,
        "nodes": nodes,
        "edges": enriched_edges,
        "eligible_edges": eligible_edges,
        "changed_edges": promoted_edges,
        "changed_edge_fraction": metrics["changed_edge_fraction"],
        "weighted_edge_displacement": metrics["weighted_edge_displacement"],
        "node_disruption_scores": node_scores,
        "most_disrupted_nodes": node_scores[:10],
        "connected_changed_components": components,
        "component_count": metrics["component_count"],
        "component_sizes": metrics["component_sizes"],
        "weighted_degree_change": weighted_degree,
        "graph_density_change": density,
        "subsystem_concentration": subsystem_concentration,
        "thresholds": {
            "change_inclusion_threshold": float(cfg["change_inclusion_threshold"]),
            "density_inclusion_threshold": float(cfg["density_inclusion_threshold"]),
            "minimum_edge_confidence": float(cfg["minimum_edge_confidence"]),
            "minimum_data_quality_factor": float(cfg["minimum_data_quality_factor"]),
            "minimum_component_coherence": float(cfg["minimum_component_coherence"]),
            "minimum_component_edges": int(cfg["minimum_component_edges"]),
        },
        "formulas": {
            "changed_edge_fraction": "changed_eligible_edges / max(total_eligible_edges, 1)",
            "edge_displacement": "abs(current_correlation - baseline_correlation) * edge_confidence * data_quality_factor",
            "weighted_edge_displacement": "sum(edge_displacement) / max(sum(edge_confidence), epsilon)",
            "node_disruption": "sum(incident_edge_displacement) / max(sum(incident_edge_confidence * incident_data_quality_factor), epsilon)",
            "component_coherence": "0.20*shared_node + 0.20*direction + 0.15*time_alignment + 0.15*confidence + 0.15*persistence + 0.15*sensor_health",
        },
    }


def _enrich_edge(
    raw_edge: dict[str, Any],
    *,
    catalog: dict[str, dict[str, Any]],
    health_by_signal: dict[str, dict[str, Any]],
    global_quality: float,
    operating_mode: dict[str, Any],
    minimum_persistence_observations: int,
) -> dict[str, Any]:
    columns = relationship_columns(raw_edge)
    baseline = _edge_number(raw_edge, "baseline_correlation")
    current = _edge_number(raw_edge, "current_correlation", "recent_correlation")
    baseline_count = _edge_count(raw_edge, "baseline_sample_count", "baseline_sample_size")
    current_count = _edge_count(raw_edge, "current_sample_count", "recent_sample_size")
    raw_confidence = confidence_number(raw_edge.get("confidence", raw_edge.get("confidence_score")), 0.0)
    sensor_factor, health_context = _sensor_health_factor(columns, health_by_signal)
    data_quality_factor = clamp(global_quality * sensor_factor)
    edge_confidence = clamp(raw_confidence * sensor_factor)
    absolute_delta = abs(float(current or 0.0) - float(baseline or 0.0))
    signed_delta = float(current or 0.0) - float(baseline or 0.0)
    displacement = absolute_delta * edge_confidence * data_quality_factor
    context = raw_edge.get("relationship_context") if isinstance(raw_edge.get("relationship_context"), dict) else {}
    eligible = bool(
        len(columns) == 2
        and baseline is not None
        and current is not None
        and baseline_count >= 3
        and current_count >= 3
        and context.get("operator_primary_eligible", True)
    )
    persistence_factor = clamp(current_count / max(1, minimum_persistence_observations))
    return {
        **raw_edge,
        "columns": columns,
        "baseline_correlation": round(float(baseline), 6) if baseline is not None else None,
        "current_correlation": round(float(current), 6) if current is not None else None,
        "recent_correlation": round(float(current), 6) if current is not None else None,
        "signed_correlation_delta": round(signed_delta, 6),
        "absolute_correlation_delta": round(absolute_delta, 6),
        "correlation_delta": round(absolute_delta, 6),
        "baseline_strength": round(abs(float(baseline)), 6) if baseline is not None else None,
        "current_strength": round(abs(float(current)), 6) if current is not None else None,
        "raw_confidence": round(raw_confidence, 6),
        "edge_confidence": round(edge_confidence, 6),
        "confidence": round(edge_confidence, 6),
        "data_quality_factor": round(data_quality_factor, 6),
        "edge_displacement": round(displacement, 6),
        "baseline_sample_count": baseline_count,
        "current_sample_count": current_count,
        "persistence_factor": round(persistence_factor, 6),
        "sensor_health_context": health_context,
        "telemetry_classification": [
            catalog.get(column, {}).get("telemetry_classification")
            or {
                "category": catalog.get(column, {}).get("telemetry_category"),
                "analysis_role": catalog.get(column, {}).get("analysis_role"),
            }
            for column in columns
        ],
        "operating_mode_context": operating_mode,
        "eligible": eligible,
        "promoted_changed_edge": False,
    }


def _promoted(edge: dict[str, Any], config: dict[str, Any]) -> bool:
    change_type = str(edge.get("change_type") or "stable")
    baseline_strength = float(edge.get("baseline_strength") or 0.0)
    current_strength = float(edge.get("current_strength") or 0.0)
    if change_type in {"disrupted", "missing", "weakened"}:
        strength_gate = baseline_strength >= 0.65
    elif change_type == "strengthened":
        strength_gate = baseline_strength >= 0.50 and current_strength >= 0.65
    elif change_type == "new":
        strength_gate = current_strength >= 0.75
    else:
        strength_gate = False
    return bool(
        edge["eligible"]
        and strength_gate
        and float(edge["absolute_correlation_delta"]) >= float(config["change_inclusion_threshold"])
        and float(edge["edge_confidence"]) >= float(config["minimum_edge_confidence"])
        and float(edge["data_quality_factor"]) >= float(config["minimum_data_quality_factor"])
    )


def _node_disruption(nodes: list[str], changed_edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    incident: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in changed_edges:
        for column in edge["columns"]:
            incident[column].append(edge)
    scores = []
    for node in nodes:
        edges = incident.get(node, [])
        numerator = sum(float(edge["edge_displacement"]) for edge in edges)
        denominator = sum(
            float(edge["edge_confidence"]) * float(edge["data_quality_factor"]) for edge in edges
        )
        scores.append(
            {
                "node": node,
                "node_id": f"metric:{node}",
                "changed_incident_edges": len(edges),
                "node_disruption_score": round(numerator / max(denominator, EPSILON), 6) if edges else 0.0,
            }
        )
    return sorted(scores, key=lambda item: (item["node_disruption_score"], item["changed_incident_edges"], item["node"]), reverse=True)


def _changed_components(
    changed_edges: list[dict[str, Any]],
    *,
    subsystem_by_metric: dict[str, str],
    minimum_coherence: float,
    minimum_edges: int,
) -> list[dict[str, Any]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    edges_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in changed_edges:
        left, right = edge["columns"]
        adjacency[left].add(right)
        adjacency[right].add(left)
        edges_by_node[left].append(edge)
        edges_by_node[right].append(edge)
    visited: set[str] = set()
    components = []
    for start in sorted(adjacency):
        if start in visited:
            continue
        queue = deque([start])
        members: set[str] = set()
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            members.add(node)
            queue.extend(sorted(adjacency[node] - visited))
        component_edges = []
        seen_edges: set[str] = set()
        for node in sorted(members):
            for edge in edges_by_node[node]:
                edge_id = str(edge.get("id") or "|".join(edge["columns"]))
                if edge_id not in seen_edges:
                    seen_edges.add(edge_id)
                    component_edges.append(edge)
        coherence, factors = _component_coherence(members, component_edges)
        disruption = sum(float(edge["edge_displacement"]) for edge in component_edges) / max(
            sum(float(edge["edge_confidence"]) for edge in component_edges), EPSILON
        )
        systems = sorted(
            {
                subsystem_by_metric[column]
                for column in members
                if column in subsystem_by_metric
            }
        )
        components.append(
            {
                "component_id": f"changed_component_{len(components) + 1}",
                "node_count": len(members),
                "edge_count": len(component_edges),
                "component_size": len(members),
                "metrics_involved": sorted(members),
                "systems_involved": systems,
                "edge_ids": [str(edge.get("id") or "|".join(edge["columns"])) for edge in component_edges],
                "component_disruption_score": round(disruption, 6),
                "coherence": round(coherence, 6),
                "coherence_factors": factors,
                "coherent": bool(len(component_edges) >= minimum_edges and coherence >= minimum_coherence),
                "limitations": [] if systems else ["No explicit subsystem metadata was available for this component."],
            }
        )
    return sorted(components, key=lambda item: (item["coherent"], item["coherence"], item["component_disruption_score"]), reverse=True)


def _component_coherence(nodes: set[str], edges: list[dict[str, Any]]) -> tuple[float, dict[str, float]]:
    edge_count = len(edges)
    if not edges:
        return 0.0, {}
    average_degree = (2.0 * edge_count) / max(1, len(nodes))
    shared_node = clamp((average_degree - 1.0) / 1.5)
    direction_values = []
    for edge in edges:
        strength_delta = float(edge.get("current_strength") or 0.0) - float(edge.get("baseline_strength") or 0.0)
        direction_values.append(1 if strength_delta > 1e-12 else -1 if strength_delta < -1e-12 else 0)
    nonzero_directions = [value for value in direction_values if value]
    direction = (
        abs(sum(nonzero_directions)) / max(1, len(nonzero_directions))
        if nonzero_directions
        else 0.0
    )
    windows = [
        str(edge.get("time_window") or "unavailable")
        for edge in edges
    ]
    time_alignment = max(Counter(windows).values()) / edge_count
    confidence = sum(float(edge["edge_confidence"]) for edge in edges) / edge_count
    persistence = sum(float(edge["persistence_factor"]) for edge in edges) / edge_count
    sensor_health = sum(float(edge["data_quality_factor"]) for edge in edges) / edge_count
    factors = {
        "shared_node_factor": round(shared_node, 6),
        "compatible_direction_factor": round(direction, 6),
        "time_window_alignment_factor": round(time_alignment, 6),
        "confidence_factor": round(confidence, 6),
        "persistence_factor": round(persistence, 6),
        "sensor_health_factor": round(sensor_health, 6),
    }
    coherence = (
        0.20 * shared_node
        + 0.20 * direction
        + 0.15 * time_alignment
        + 0.15 * confidence
        + 0.15 * persistence
        + 0.15 * sensor_health
    )
    return clamp(coherence), factors


def _weighted_degree(nodes: list[str], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for node in nodes:
        incident = [edge for edge in edges if node in edge["columns"]]
        baseline = sum(abs(float(edge["baseline_correlation"])) * float(edge["edge_confidence"]) for edge in incident)
        current = sum(abs(float(edge["current_correlation"])) * float(edge["edge_confidence"]) for edge in incident)
        output.append(
            {
                "node": node,
                "baseline_weighted_degree": round(baseline, 6),
                "current_weighted_degree": round(current, 6),
                "weighted_degree_delta": round(current - baseline, 6),
            }
        )
    return sorted(output, key=lambda item: abs(item["weighted_degree_delta"]), reverse=True)


def _density_change(nodes: list[str], edges: list[dict[str, Any]], *, inclusion_threshold: float) -> dict[str, Any]:
    possible = len(nodes) * (len(nodes) - 1) / 2
    baseline_count = sum(abs(float(edge["baseline_correlation"])) >= inclusion_threshold for edge in edges)
    current_count = sum(abs(float(edge["current_correlation"])) >= inclusion_threshold for edge in edges)
    baseline_density = baseline_count / max(possible, 1.0)
    current_density = current_count / max(possible, 1.0)
    return {
        "inclusion_threshold": inclusion_threshold,
        "possible_edges": int(possible),
        "baseline_included_edges": baseline_count,
        "current_included_edges": current_count,
        "baseline_density": round(baseline_density, 6),
        "current_density": round(current_density, 6),
        "density_delta": round(current_density - baseline_density, 6),
    }


def _subsystem_concentration(
    changed_edges: list[dict[str, Any]], subsystem_by_metric: dict[str, str]
) -> dict[str, Any]:
    if not subsystem_by_metric:
        return {
            "status": "limited",
            "reason": "telemetry_classification_did_not_supply_subsystem_labels",
            "classification": "unavailable",
            "concentration": None,
            "subsystems": [],
        }
    weights: dict[str, float] = defaultdict(float)
    cross_subsystem_weight = 0.0
    total_weight = 0.0
    for edge in changed_edges:
        systems = {subsystem_by_metric[column] for column in edge["columns"] if column in subsystem_by_metric}
        weight = max(float(edge["edge_displacement"]), EPSILON)
        total_weight += weight
        if len(systems) == 1:
            weights[next(iter(systems))] += weight
        elif len(systems) > 1:
            cross_subsystem_weight += weight
    concentration = max(weights.values(), default=0.0) / max(total_weight, EPSILON) if changed_edges else 0.0
    if not changed_edges:
        classification = "no_changed_relationships"
    elif concentration >= 0.75:
        classification = "concentrated"
    elif cross_subsystem_weight / max(total_weight, EPSILON) >= 0.4 or len(weights) >= 3:
        classification = "distributed"
    else:
        classification = "mixed"
    return {
        "status": "complete",
        "classification": classification,
        "concentration": round(concentration, 6),
        "cross_subsystem_fraction": round(cross_subsystem_weight / max(total_weight, EPSILON), 6) if total_weight else 0.0,
        "subsystems": [
            {"subsystem": name, "changed_edge_weight": round(weight, 6)}
            for name, weight in sorted(weights.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def _health_by_signal(sensor_health: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("signal")): item
        for item in (sensor_health or {}).get("signals", [])
        if isinstance(item, dict) and item.get("signal")
    }


def _sensor_health_factor(
    columns: list[str], health_by_signal: dict[str, dict[str, Any]]
) -> tuple[float, list[dict[str, Any]]]:
    if not columns:
        return 0.25, []
    factors = []
    contexts = []
    for column in columns:
        profile = health_by_signal.get(column)
        if not profile:
            factors.append(0.7)
            contexts.append({"signal": column, "health": "unavailable", "factor": 0.7})
            continue
        health = str(profile.get("health") or "healthy").lower()
        conditions = [item for item in profile.get("conditions", []) if isinstance(item, dict)]
        condition_types = {str(item.get("type") or "") for item in conditions}
        if condition_types & {
            "flatline_or_stuck",
            "frozen_precision",
            "sparse_baseline_coverage",
            "possible_drift",
            "timestamp_misalignment",
        }:
            factor = 0.25
        elif health in {"suspect", "review", "unhealthy", "failed"}:
            factor = 0.4
        elif conditions or health in {"limited", "watch"}:
            factor = 0.65
        else:
            factor = 1.0
        factors.append(factor)
        contexts.append({**profile, "factor": factor})
    return min(factors), contexts


def _global_quality_factor(data_quality: dict[str, Any] | None) -> float:
    confidence = (data_quality or {}).get("data_confidence")
    rating = confidence.get("rating") if isinstance(confidence, dict) else (data_quality or {}).get("reliability_rating")
    return confidence_number(rating, 0.8)


def _catalog_subsystem(metadata: dict[str, Any]) -> str | None:
    for key in ("subsystem", "subsystem_name", "system", "system_name", "asset_group"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    classification = metadata.get("telemetry_classification")
    if isinstance(classification, dict):
        for key in ("subsystem", "subsystem_name", "system", "system_name", "asset_group"):
            value = str(classification.get(key) or "").strip()
            if value:
                return value
    return None


def _metric_node(column: str, metadata: dict[str, Any], subsystem: str | None) -> dict[str, Any]:
    node = {
        "id": f"metric:{column}",
        "type": "metric",
        "label": str(metadata.get("display_name") or column),
        "source_column": column,
        "telemetry_classification": metadata.get("telemetry_classification")
        or {
            "category": metadata.get("telemetry_category"),
            "analysis_role": metadata.get("analysis_role"),
        },
    }
    if subsystem:
        node["subsystem"] = subsystem
        node["subsystem_node_id"] = f"subsystem:{_safe_id(subsystem)}"
    return node


def _edge_number(edge: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        try:
            value = float(edge.get(key))
        except (TypeError, ValueError):
            continue
        return value
    return None


def _edge_count(edge: dict[str, Any], *keys: str) -> int:
    for key in keys:
        try:
            return max(0, int(edge.get(key)))
        except (TypeError, ValueError):
            continue
    pairs = edge.get("supporting_metric_pairs")
    if isinstance(pairs, list) and pairs and isinstance(pairs[0], dict):
        for key in keys:
            try:
                return max(0, int(pairs[0].get(key)))
            except (TypeError, ValueError):
                continue
    return 0


def _safe_id(value: str) -> str:
    return "_".join(part for part in value.lower().replace("/", " ").split() if part)
