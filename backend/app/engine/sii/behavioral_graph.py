from __future__ import annotations

import math
from collections import defaultdict, deque
from copy import deepcopy
from hashlib import sha256
from statistics import median
from typing import Any

from app.engine.sii.common import clamp, finite_number, relationship_columns


GRAPH_METHOD = "persistent_behavioral_graph_v1"


def relationship_memory_id(
    source_signal: str,
    target_signal: str,
    relationship_type: str,
    operating_mode: str,
) -> str:
    left, right = sorted((str(source_signal), str(target_signal)))
    seed = f"{operating_mode}|{relationship_type}|{left}|{right}"
    return f"relationship:{sha256(seed.encode('utf-8')).hexdigest()[:20]}"


def compare_behavioral_graph(
    *,
    current_graph: dict[str, Any],
    active_graph: dict[str, Any] | None,
    previous_snapshot_graph: dict[str, Any] | None = None,
    long_term_reference_graph: dict[str, Any] | None = None,
    operating_mode: str,
    change_threshold: float = 0.20,
) -> dict[str, Any]:
    """Compare run-level relationships with persistent graph references.

    The comparison is structural association evidence only. It does not infer
    direction, cause, failure, or operational consequence.
    """

    current_nodes, current_edges = _normalized_current(current_graph, operating_mode)
    active_nodes, active_edges = _stored_graph(active_graph)
    _, previous_edges = _stored_graph(previous_snapshot_graph)
    _, reference_edges = _stored_graph(long_term_reference_graph)

    changed: list[dict[str, Any]] = []
    emerged: list[dict[str, Any]] = []
    weakened: list[dict[str, Any]] = []
    strengthened: list[dict[str, Any]] = []
    inactive: list[dict[str, Any]] = []
    all_ids = sorted(set(current_edges) | set(active_edges))
    for edge_id in all_ids:
        current = current_edges.get(edge_id)
        active = active_edges.get(edge_id)
        if current is not None and active is None:
            item = _edge_change(edge_id, None, current, "emerged", previous_edges, reference_edges)
            emerged.append(item)
            changed.append(item)
            continue
        if current is None and active is not None:
            item = _edge_change(edge_id, active, None, "not_observed", previous_edges, reference_edges)
            inactive.append(item)
            changed.append(item)
            continue
        if current is None or active is None:
            continue
        before = finite_number(active.get("current_strength")) or 0.0
        after = finite_number(current.get("current_strength")) or 0.0
        delta = after - before
        if abs(delta) < float(change_threshold):
            continue
        classification = "strengthened" if delta > 0 else "weakened"
        item = _edge_change(edge_id, active, current, classification, previous_edges, reference_edges)
        (strengthened if delta > 0 else weakened).append(item)
        changed.append(item)

    clusters = _changed_edge_clusters(changed)
    active_components = _component_count(active_edges)
    current_components = _component_count(current_edges)
    fragmentation = {
        "active_component_count": active_components,
        "current_component_count": current_components,
        "component_count_delta": current_components - active_components,
        "fragmentation_observed": bool(active_edges and current_components > active_components),
    }
    concentration = _concentration_change(active_edges, current_edges)
    graph_mathematics = _graph_mathematics(
        current_nodes=current_nodes,
        current_edges=current_edges,
        active_nodes=active_nodes,
        active_edges=active_edges,
    )
    topology = _topology_classification(
        current_edges=current_edges,
        active_edges=active_edges,
        changed=changed,
        clusters=clusters,
    )
    limitations = []
    if not active_edges:
        limitations.append("No active persistent graph was available; current edges can only be recorded as initial graph evidence.")
    if not current_edges:
        limitations.append("No eligible current relationship edges were available for graph comparison.")
    evidence = _graph_evidence(
        changed=changed,
        clusters=clusters,
        fragmentation=fragmentation,
        topology=topology,
        graph_mathematics=graph_mathematics,
    )
    status = "complete" if current_edges and active_edges else "limited"
    return {
        "status": status,
        "reason": None if status == "complete" else "persistent_graph_comparison_reference_unavailable",
        "method": GRAPH_METHOD,
        "operating_mode": operating_mode,
        "current_run_graph": {"node_count": len(current_nodes), "edge_count": len(current_edges)},
        "active_model_graph": {"node_count": len(active_nodes), "edge_count": len(active_edges)},
        "previous_snapshot_graph": {"edge_count": len(previous_edges)},
        "long_term_reference_graph": {"edge_count": len(reference_edges)},
        "changed_edges": changed,
        "edge_emergence": emerged,
        "edge_weakening": weakened,
        "edge_strengthening": strengthened,
        "edges_not_observed": inactive,
        "changed_edge_clusters": clusters,
        "neighborhood_disruption": _neighborhood_disruption(changed),
        "graph_fragmentation": fragmentation,
        "concentration_changes": concentration,
        "graph_mathematics": graph_mathematics,
        "coordinated_edge_weakening": len(weakened) >= 2,
        "coordinated_edge_emergence": len(emerged) >= 2,
        "structural_change_scope": topology,
        "persistent_topology_change": _persistent_topology_change(changed),
        "graph_evidence": evidence,
        "limitations": limitations,
        "processing_trace": {
            "current_edge_ids": sorted(current_edges),
            "active_edge_ids": sorted(active_edges),
            "changed_edge_ids": [item["relationship_id"] for item in changed],
            "change_threshold": float(change_threshold),
            "graph_mathematics_method": graph_mathematics["method"],
            "causal_inference_performed": False,
            "diagnosis_performed": False,
        },
    }


def update_behavioral_graph(
    *,
    active_graph: dict[str, Any] | None,
    current_graph: dict[str, Any],
    signal_memory: dict[str, Any],
    relationship_memory: dict[str, Any],
    event_references: list[str],
    source_run_id: str,
    model_version: str,
    allow_learning: bool,
) -> dict[str, Any]:
    """Return a new persistent graph value; never mutate the supplied graph."""

    nodes, edges = _stored_graph(active_graph)
    if not allow_learning:
        return {
            "method": GRAPH_METHOD,
            "nodes": nodes,
            "edges": edges,
            "evolution_history": list((active_graph or {}).get("evolution_history") or []),
            "limitations": list((active_graph or {}).get("limitations") or []),
        }

    for signal_id, memory in sorted(signal_memory.items()):
        prior = nodes.get(signal_id, {})
        nodes[signal_id] = {
            **deepcopy(prior),
            "node_id": signal_id,
            "node_type": "telemetry_signal",
            "signal_id": signal_id,
            "source_column": memory.get("source_column"),
            "signal_behavior_history": deepcopy(memory.get("trend_history", [])),
            "operating_modes": deepcopy(memory.get("operating_modes_observed", [])),
            "signal_confidence": deepcopy(memory.get("confidence", {})),
            "sensor_health_history": deepcopy(memory.get("sensor_health_history", [])),
            "expected_variability": memory.get("historical_variability"),
            "active_observations": deepcopy(memory.get("drift_history", [])[-5:]),
            "event_references": list(event_references),
            "historical_residual_behavior": deepcopy(memory.get("historical_residual_behavior", [])),
            "limitations": deepcopy(memory.get("limitations", [])),
        }

    for relationship_id, memory in sorted(relationship_memory.items()):
        prior = edges.get(relationship_id, {})
        edges[relationship_id] = {
            **deepcopy(prior),
            "relationship_id": relationship_id,
            "source_signal": memory.get("source_signal"),
            "target_signal": memory.get("target_signal"),
            "relationship_type": memory.get("relationship_type"),
            "historical_relationship_strength": memory.get("baseline_strength"),
            "current_strength": memory.get("current_strength"),
            "relationship_confidence": deepcopy(memory.get("confidence", {})),
            "operating_context": deepcopy(memory.get("operating_modes_observed", [])),
            "stability": memory.get("stability"),
            "volatility": memory.get("volatility"),
            "persistence": memory.get("persistence"),
            "lag_behavior": deepcopy(memory.get("lag_history", [])),
            "physics_prior_references": deepcopy(memory.get("physics_prior_references", [])),
            "evolution_history": deepcopy(memory.get("change_history", [])),
            "propagation_participation": deepcopy(memory.get("propagation_participation", [])),
            "limitations": deepcopy(memory.get("limitations", [])),
            "status": memory.get("status"),
        }

    configured_nodes = [
        item
        for item in current_graph.get("nodes", [])
        if isinstance(item, dict) and item.get("type") in {"equipment", "subsystem"}
    ] if isinstance(current_graph, dict) else []
    for item in configured_nodes:
        node_id = str(item.get("id") or "").strip()
        if node_id:
            nodes[node_id] = {**deepcopy(nodes.get(node_id, {})), **deepcopy(item), "node_type": item.get("type")}

    history = list((active_graph or {}).get("evolution_history") or [])
    history.append(
        {
            "source_run_id": source_run_id,
            "model_version": model_version,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }
    )
    return {
        "method": GRAPH_METHOD,
        "nodes": dict(sorted(nodes.items())),
        "edges": dict(sorted(edges.items())),
        "evolution_history": history[-100:],
        "limitations": ["Persistent graph edges are behavioral associations and are not causal claims."],
    }


def _normalized_current(
    graph: dict[str, Any], operating_mode: str
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    for item in graph.get("nodes", []) if isinstance(graph, dict) else []:
        if not isinstance(item, dict):
            continue
        raw_id = str(item.get("source_column") or item.get("id") or "").removeprefix("metric:")
        if raw_id:
            node_id = raw_id if str(item.get("type")) == "metric" else str(item.get("id") or raw_id)
            nodes[node_id] = deepcopy(item)
    edges: dict[str, dict[str, Any]] = {}
    candidates = graph.get("eligible_edges") if isinstance(graph, dict) else None
    if not isinstance(candidates, list) or not candidates:
        candidates = graph.get("edges", []) if isinstance(graph, dict) else []
    for edge in candidates:
        if not isinstance(edge, dict):
            continue
        columns = relationship_columns(edge)
        if len(columns) != 2:
            continue
        relationship_type = str(edge.get("relationship_type") or "linear_correlation")
        edge_id = relationship_memory_id(columns[0], columns[1], relationship_type, operating_mode)
        edges[edge_id] = {
            **deepcopy(edge),
            "relationship_id": edge_id,
            "source_signal": columns[0],
            "target_signal": columns[1],
            "relationship_type": relationship_type,
            "operating_mode": operating_mode,
            "current_strength": _strength(edge),
        }
        nodes.setdefault(columns[0], {"node_id": columns[0], "node_type": "telemetry_signal"})
        nodes.setdefault(columns[1], {"node_id": columns[1], "node_type": "telemetry_signal"})
    return dict(sorted(nodes.items())), dict(sorted(edges.items()))


def _stored_graph(graph: dict[str, Any] | None) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(graph, dict):
        return {}, {}
    raw_nodes = graph.get("nodes", {})
    raw_edges = graph.get("edges", {})
    if isinstance(raw_nodes, list):
        nodes = {
            str(item.get("node_id") or item.get("id")): deepcopy(item)
            for item in raw_nodes
            if isinstance(item, dict) and (item.get("node_id") or item.get("id"))
        }
    else:
        nodes = deepcopy(raw_nodes) if isinstance(raw_nodes, dict) else {}
    if isinstance(raw_edges, list):
        edges = {
            str(item.get("relationship_id") or item.get("id")): deepcopy(item)
            for item in raw_edges
            if isinstance(item, dict) and (item.get("relationship_id") or item.get("id"))
        }
    else:
        edges = deepcopy(raw_edges) if isinstance(raw_edges, dict) else {}
    return nodes, edges


def _strength(edge: dict[str, Any]) -> float:
    for field in ("current_strength", "current_correlation", "recent_correlation", "strength"):
        value = finite_number(edge.get(field))
        if value is not None:
            return round(abs(value), 6)
    return 0.0


def _edge_change(
    edge_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    change_type: str,
    previous_edges: dict[str, dict[str, Any]],
    reference_edges: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source = after or before or {}
    before_strength = _strength(before or {}) if before else None
    after_strength = _strength(after or {}) if after else None
    return {
        "relationship_id": edge_id,
        "source_signal": source.get("source_signal"),
        "target_signal": source.get("target_signal"),
        "operating_mode": source.get("operating_mode"),
        "change_type": change_type,
        "active_strength": before_strength,
        "current_strength": after_strength,
        "strength_delta": round((after_strength or 0.0) - (before_strength or 0.0), 6),
        "previous_snapshot_strength": _strength(previous_edges[edge_id]) if edge_id in previous_edges else None,
        "long_term_reference_strength": _strength(reference_edges[edge_id]) if edge_id in reference_edges else None,
        "persistent_across_references": edge_id in previous_edges and edge_id in reference_edges,
        "source_evidence": deepcopy(after or before or {}),
    }


def _changed_edge_clusters(changed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in changed:
        left = str(edge.get("source_signal") or "")
        right = str(edge.get("target_signal") or "")
        if not left or not right:
            continue
        adjacency[left].add(right)
        adjacency[right].add(left)
        by_node[left].append(edge)
        by_node[right].append(edge)
    visited: set[str] = set()
    output = []
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
        edge_items: dict[str, dict[str, Any]] = {}
        for member in members:
            for edge in by_node[member]:
                edge_items[edge["relationship_id"]] = edge
        output.append(
            {
                "cluster_id": f"graph_change_cluster:{len(output) + 1}",
                "nodes": sorted(members),
                "relationship_ids": sorted(edge_items),
                "edge_count": len(edge_items),
                "change_types": sorted({str(item.get("change_type")) for item in edge_items.values()}),
            }
        )
    return output


def _neighborhood_disruption(changed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    incident: dict[str, list[float]] = defaultdict(list)
    for edge in changed:
        for node in (edge.get("source_signal"), edge.get("target_signal")):
            if node:
                incident[str(node)].append(abs(float(edge.get("strength_delta") or 0.0)))
    return [
        {
            "node": node,
            "changed_incident_edges": len(values),
            "median_strength_displacement": round(float(median(values)), 6),
        }
        for node, values in sorted(incident.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


def _component_count(edges: dict[str, dict[str, Any]]) -> int:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges.values():
        left = str(edge.get("source_signal") or "")
        right = str(edge.get("target_signal") or "")
        if left and right:
            adjacency[left].add(right)
            adjacency[right].add(left)
    visited: set[str] = set()
    count = 0
    for node in sorted(adjacency):
        if node in visited:
            continue
        count += 1
        queue = deque([node])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            queue.extend(sorted(adjacency[current] - visited))
    return count


def _concentration_change(
    active_edges: dict[str, dict[str, Any]], current_edges: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    def concentration(edges: dict[str, dict[str, Any]]) -> float:
        totals: dict[str, float] = defaultdict(float)
        for edge in edges.values():
            strength = _strength(edge)
            for node in (edge.get("source_signal"), edge.get("target_signal")):
                if node:
                    totals[str(node)] += strength
        total = sum(totals.values())
        return max(totals.values(), default=0.0) / total if total else 0.0

    before = concentration(active_edges)
    after = concentration(current_edges)
    return {
        "active_max_node_concentration": round(before, 6),
        "current_max_node_concentration": round(after, 6),
        "concentration_delta": round(after - before, 6),
    }


def _graph_mathematics(
    *,
    current_nodes: dict[str, dict[str, Any]],
    current_edges: dict[str, dict[str, Any]],
    active_nodes: dict[str, dict[str, Any]],
    active_edges: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return inspectable weighted-graph metrics over the graph comparison.

    Node weighted-degree displacement is treated as a graph signal. Its
    Dirichlet energy is x' L x = sum(w_ij * (x_i - x_j)^2), where the
    comparison weight is the larger observed edge weight in either graph.
    This identifies coordinated neighborhood change without embedding nodes
    or assigning causal meaning.
    """

    node_ids = sorted(
        set(current_nodes)
        | set(active_nodes)
        | {
            str(node)
            for edge in [*current_edges.values(), *active_edges.values()]
            for node in (edge.get("source_signal"), edge.get("target_signal"))
            if node
        }
    )
    active_weights = _edge_weights_by_pair(active_edges)
    current_weights = _edge_weights_by_pair(current_edges)
    all_pairs = sorted(set(active_weights) | set(current_weights))
    reference_weights = {
        pair: max(active_weights.get(pair, 0.0), current_weights.get(pair, 0.0))
        for pair in all_pairs
    }
    active_degree = _weighted_degrees(node_ids, active_weights)
    current_degree = _weighted_degrees(node_ids, current_weights)
    displacement = {
        node: current_degree.get(node, 0.0) - active_degree.get(node, 0.0)
        for node in node_ids
    }
    local_energy = {node: 0.0 for node in node_ids}
    dirichlet_energy = 0.0
    total_variation = 0.0
    for (left, right), weight in reference_weights.items():
        difference = displacement[left] - displacement[right]
        edge_energy = weight * difference * difference
        dirichlet_energy += edge_energy
        total_variation += weight * abs(difference)
        local_energy[left] += edge_energy / 2.0
        local_energy[right] += edge_energy / 2.0
    signal_energy = sum(value * value for value in displacement.values())
    normalized_smoothness = (
        dirichlet_energy / signal_energy if signal_energy > 1e-12 else 0.0
    )
    weighted_union = sum(max(active_weights.get(pair, 0.0), current_weights.get(pair, 0.0)) for pair in all_pairs)
    weighted_intersection = sum(min(active_weights.get(pair, 0.0), current_weights.get(pair, 0.0)) for pair in all_pairs)
    weighted_jaccard = weighted_intersection / weighted_union if weighted_union else 1.0
    normalized_l1_change = (
        sum(abs(current_weights.get(pair, 0.0) - active_weights.get(pair, 0.0)) for pair in all_pairs)
        / weighted_union
        if weighted_union
        else 0.0
    )
    neighborhoods = _neighborhood_consistency(
        node_ids=node_ids,
        active_weights=active_weights,
        current_weights=current_weights,
    )
    centrality = _centrality_metrics(node_ids, current_weights)
    active_node_ids = sorted(
        set(active_nodes)
        | {node for pair in active_weights for node in pair}
    )
    current_node_ids = sorted(
        set(current_nodes)
        | {node for pair in current_weights for node in pair}
    )
    active_communities = _component_memberships(
        active_node_ids,
        active_weights,
    )
    current_communities = _component_memberships(
        current_node_ids,
        current_weights,
    )
    community_evolution = _community_evolution(active_communities, current_communities)
    return {
        "method": "weighted_laplacian_structural_comparison_v1",
        "node_signal": {
            "definition": "current_minus_active_weighted_degree",
            "values": [
                {
                    "node": node,
                    "active_weighted_degree": round(active_degree.get(node, 0.0), 6),
                    "current_weighted_degree": round(current_degree.get(node, 0.0), 6),
                    "weighted_degree_displacement": round(displacement[node], 6),
                }
                for node in node_ids
            ],
        },
        "graph_signal_smoothness": {
            "dirichlet_energy": round(dirichlet_energy, 6),
            "normalized_dirichlet_energy": round(normalized_smoothness, 6),
            "weighted_total_variation": round(total_variation, 6),
            "signal_energy": round(signal_energy, 6),
            "formula": "x' L x = sum_{(i,j)} w_ij (x_i - x_j)^2",
            "interpretation": "Lower energy indicates more spatially coordinated weighted-degree displacement on the observed graph.",
        },
        "localized_graph_energy": [
            {
                "node": node,
                "energy": round(local_energy[node], 6),
                "energy_fraction": round(local_energy[node] / dirichlet_energy, 6)
                if dirichlet_energy > 1e-12
                else 0.0,
            }
            for node in sorted(node_ids, key=lambda item: (-local_energy[item], item))
        ],
        "centrality": centrality,
        "neighborhood_consistency": neighborhoods,
        "structural_entropy": {
            "active": round(_degree_entropy(active_degree), 6),
            "current": round(_degree_entropy(current_degree), 6),
            "delta": round(_degree_entropy(current_degree) - _degree_entropy(active_degree), 6),
            "normalization": "shannon_entropy_divided_by_log_node_count",
        },
        "graph_stability": {
            "weighted_jaccard_similarity": round(weighted_jaccard, 6),
            "normalized_weight_l1_change": round(normalized_l1_change, 6),
            "edge_union_count": len(all_pairs),
            "comparable_reference_available": bool(active_edges),
        },
        "community_evolution": community_evolution,
        "limitations": [
            "Graph metrics describe weighted association structure and do not establish direction or cause.",
            "The graph signal is weighted-degree displacement, not a learned embedding.",
        ],
    }


def _edge_weights_by_pair(edges: dict[str, dict[str, Any]]) -> dict[tuple[str, str], float]:
    weights: dict[tuple[str, str], float] = defaultdict(float)
    for edge in edges.values():
        left = str(edge.get("source_signal") or "")
        right = str(edge.get("target_signal") or "")
        if not left or not right or left == right:
            continue
        pair = tuple(sorted((left, right)))
        weights[pair] += _strength(edge)
    return dict(weights)


def _weighted_degrees(
    node_ids: list[str], weights: dict[tuple[str, str], float]
) -> dict[str, float]:
    degrees = {node: 0.0 for node in node_ids}
    for (left, right), weight in weights.items():
        degrees[left] = degrees.get(left, 0.0) + weight
        degrees[right] = degrees.get(right, 0.0) + weight
    return degrees


def _neighborhood_consistency(
    *,
    node_ids: list[str],
    active_weights: dict[tuple[str, str], float],
    current_weights: dict[tuple[str, str], float],
) -> list[dict[str, Any]]:
    incident: dict[str, list[float]] = defaultdict(list)
    for pair in sorted(set(active_weights) | set(current_weights)):
        delta = current_weights.get(pair, 0.0) - active_weights.get(pair, 0.0)
        for node in pair:
            incident[node].append(delta)
    output = []
    for node in node_ids:
        values = incident.get(node, [])
        positive = sum(value > 1e-12 for value in values)
        negative = sum(value < -1e-12 for value in values)
        unchanged = len(values) - positive - negative
        directional = positive + negative
        output.append(
            {
                "node": node,
                "incident_edge_count": len(values),
                "strengthened_incident_edges": positive,
                "weakened_incident_edges": negative,
                "unchanged_incident_edges": unchanged,
                "directional_consistency": round(max(positive, negative) / directional, 6)
                if directional
                else 1.0,
                "median_incident_weight_delta": round(float(median(values)), 6)
                if values
                else 0.0,
            }
        )
    return sorted(
        output,
        key=lambda item: (-int(item["incident_edge_count"]), str(item["node"])),
    )


def _centrality_metrics(
    node_ids: list[str], weights: dict[tuple[str, str], float]
) -> list[dict[str, Any]]:
    adjacency: dict[str, set[str]] = {node: set() for node in node_ids}
    degrees = _weighted_degrees(node_ids, weights)
    for left, right in weights:
        adjacency[left].add(right)
        adjacency[right].add(left)
    betweenness = {node: 0.0 for node in node_ids}
    for source in node_ids:
        stack: list[str] = []
        predecessors = {node: [] for node in node_ids}
        paths = {node: 0.0 for node in node_ids}
        paths[source] = 1.0
        distance = {node: -1 for node in node_ids}
        distance[source] = 0
        queue = deque([source])
        while queue:
            node = queue.popleft()
            stack.append(node)
            for neighbor in sorted(adjacency[node]):
                if distance[neighbor] < 0:
                    queue.append(neighbor)
                    distance[neighbor] = distance[node] + 1
                if distance[neighbor] == distance[node] + 1:
                    paths[neighbor] += paths[node]
                    predecessors[neighbor].append(node)
        dependency = {node: 0.0 for node in node_ids}
        while stack:
            node = stack.pop()
            for predecessor in predecessors[node]:
                if paths[node] > 0:
                    dependency[predecessor] += (
                        paths[predecessor] / paths[node]
                    ) * (1.0 + dependency[node])
            if node != source:
                betweenness[node] += dependency[node]
    normalization = (
        1.0 / ((len(node_ids) - 1) * (len(node_ids) - 2))
        if len(node_ids) > 2
        else 0.0
    )
    return [
        {
            "node": node,
            "degree_centrality": round(
                len(adjacency[node]) / max(1, len(node_ids) - 1), 6
            ),
            "weighted_degree_centrality": round(
                degrees[node] / max(1, len(node_ids) - 1), 6
            ),
            "betweenness_centrality": round(betweenness[node] * normalization, 6),
        }
        for node in sorted(
            node_ids,
            key=lambda item: (-degrees[item], -betweenness[item], item),
        )
    ]


def _degree_entropy(degrees: dict[str, float]) -> float:
    positive = [max(0.0, float(value)) for value in degrees.values()]
    total = sum(positive)
    if total <= 1e-12 or len(positive) <= 1:
        return 0.0
    entropy = -sum(
        (value / total) * math.log(value / total)
        for value in positive
        if value > 0.0
    )
    return entropy / math.log(len(positive))


def _component_memberships(
    node_ids: list[str], weights: dict[tuple[str, str], float]
) -> list[list[str]]:
    adjacency = {node: set() for node in node_ids}
    for (left, right), weight in weights.items():
        if weight <= 0.0:
            continue
        adjacency[left].add(right)
        adjacency[right].add(left)
    visited: set[str] = set()
    output = []
    for start in node_ids:
        if start in visited:
            continue
        queue = deque([start])
        members = []
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            members.append(node)
            queue.extend(sorted(adjacency[node] - visited))
        output.append(sorted(members))
    return output


def _community_evolution(
    active: list[list[str]], current: list[list[str]]
) -> dict[str, Any]:
    active_sets = [set(item) for item in active]
    current_sets = [set(item) for item in current]
    splits = sum(
        sum(bool(group & current_group) for current_group in current_sets) > 1
        for group in active_sets
    )
    merges = sum(
        sum(bool(group & active_group) for active_group in active_sets) > 1
        for group in current_sets
    )
    return {
        "method": "deterministic_connected_component_overlap",
        "active_communities": active,
        "current_communities": current,
        "active_community_count": len(active),
        "current_community_count": len(current),
        "split_count": splits,
        "merge_count": merges,
    }


def _topology_classification(
    *,
    current_edges: dict[str, dict[str, Any]],
    active_edges: dict[str, dict[str, Any]],
    changed: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
) -> str:
    if not changed:
        return "no_material_structural_change"
    fraction = len(changed) / max(1, len(set(current_edges) | set(active_edges)))
    if fraction >= 0.6:
        return "system_wide_structural_change"
    if len(clusters) == 1:
        return "localized_structural_change"
    return "distributed_structural_change"


def _persistent_topology_change(changed: list[dict[str, Any]]) -> bool:
    return any(item.get("persistent_across_references") for item in changed)


def _graph_evidence(
    *,
    changed: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    fragmentation: dict[str, Any],
    topology: str,
    graph_mathematics: dict[str, Any],
) -> list[dict[str, Any]]:
    evidence = []
    for item in changed:
        evidence.append(
            {
                "evidence_id": f"behavioral_graph:{item['relationship_id']}",
                "classification": "Supporting",
                "originating_module": "behavioral_graph",
                "observation": f"Persistent graph edge {item['change_type']} relative to the active behavioral model.",
                "source_relationships": [item["relationship_id"]],
                "source_evidence": deepcopy(item),
                "causal_claim": False,
            }
        )
    if fragmentation.get("fragmentation_observed"):
        evidence.append(
            {
                "evidence_id": "behavioral_graph:fragmentation",
                "classification": "Supporting",
                "originating_module": "behavioral_graph",
                "observation": "The current association graph contains more disconnected components than the active reference graph.",
                "source_relationships": [item["relationship_id"] for item in changed],
                "source_evidence": deepcopy(fragmentation),
                "causal_claim": False,
            }
        )
    if clusters:
        evidence.append(
            {
                "evidence_id": "behavioral_graph:structural_scope",
                "classification": "Supporting" if changed else "Neutral",
                "originating_module": "behavioral_graph",
                "observation": topology,
                "source_relationships": sorted(
                    relationship_id for cluster in clusters for relationship_id in cluster["relationship_ids"]
                ),
                "source_evidence": deepcopy(clusters),
                "causal_claim": False,
            }
        )
    if changed:
        evidence.append(
            {
                "evidence_id": "behavioral_graph:graph_mathematics",
                "classification": "Supporting",
                "originating_module": "behavioral_graph",
                "observation": "Weighted Laplacian, neighborhood, entropy, centrality, and stability metrics characterize the structural scope of the observed graph change.",
                "source_relationships": sorted(
                    item["relationship_id"] for item in changed
                ),
                "source_evidence": deepcopy(graph_mathematics),
                "causal_claim": False,
            }
        )
    return evidence
