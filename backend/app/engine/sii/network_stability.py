from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from typing import Any

import numpy as np

from app.engine.sii.common import finite_number, relationship_columns


DEFAULT_CONFIG = {"minimum_nodes": 3, "minimum_edges": 2, "eigenvalue_indicators_enabled": False}


def analyze_network_stability(
    *,
    current_graph: dict[str, Any],
    active_graph: dict[str, Any] | None,
    graph_comparison: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    current_edges = _current_edges(current_graph)
    active_edges = _active_edges(active_graph)
    nodes = sorted({node for edge in current_edges.values() for node in edge["nodes"]})
    if len(nodes) < int(cfg["minimum_nodes"]) or len(current_edges) < int(cfg["minimum_edges"]):
        return _limited("network_structure_insufficient", len(nodes), len(current_edges))
    deltas = []
    for edge_id, edge in current_edges.items():
        before = active_edges.get(edge_id)
        if before:
            deltas.append(abs(edge["weight"] - before["weight"]))
    connectivity = {
        "current_components": _components(current_edges),
        "active_components": _components(active_edges) if active_edges else None,
    }
    connectivity["component_delta"] = (
        connectivity["current_components"] - connectivity["active_components"]
        if connectivity["active_components"] is not None
        else None
    )
    eigenvalues = None
    if bool(cfg["eigenvalue_indicators_enabled"]):
        matrix = np.zeros((len(nodes), len(nodes)), dtype=float)
        index = {node: position for position, node in enumerate(nodes)}
        for edge in current_edges.values():
            left, right = edge["nodes"]
            matrix[index[left], index[right]] = edge["weight"]
            matrix[index[right], index[left]] = edge["weight"]
        values = sorted((float(value.real) for value in np.linalg.eigvals(matrix)), reverse=True)
        eigenvalues = {
            "adjacency_eigenvalues": [round(value, 6) for value in values],
            "indicator_only": True,
            "risk_interpretation": None,
        }
    return {
        "status": "complete",
        "method": "deterministic_edge_sensitivity_and_connectivity_v1",
        "graph_structural_stability": graph_comparison.get("structural_change_scope"),
        "edge_weight_sensitivity": {
            "comparable_edges": len(deltas),
            "median_absolute_weight_change": round(float(np.median(deltas)), 6) if deltas else None,
            "maximum_absolute_weight_change": round(max(deltas), 6) if deltas else None,
        },
        "neighborhood_disruption": deepcopy(graph_comparison.get("neighborhood_disruption", [])),
        "connectivity_changes": connectivity,
        "eigenvalue_indicators": eigenvalues,
        "limitations": [
            "Network indicators describe association-graph structure and are not network-risk scores.",
            "Eigenvalue indicators are omitted unless explicitly configured and sufficiently supported.",
        ],
        "processing_trace": {
            "nodes_evaluated": len(nodes),
            "edges_evaluated": len(current_edges),
            "eigenvalues_attempted": bool(cfg["eigenvalue_indicators_enabled"]),
            "network_risk_score_generated": False,
        },
    }


def _current_edges(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates = graph.get("eligible_edges") if isinstance(graph, dict) else None
    if not isinstance(candidates, list) or not candidates:
        candidates = graph.get("edges", []) if isinstance(graph, dict) else []
    output = {}
    for index, edge in enumerate(candidates):
        if not isinstance(edge, dict):
            continue
        columns = relationship_columns(edge)
        if len(columns) != 2:
            continue
        edge_id = str(edge.get("relationship_id") or edge.get("id") or "|".join(sorted(columns)))
        output[edge_id] = {"nodes": columns, "weight": _weight(edge)}
    return output


def _active_edges(graph: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    raw = graph.get("edges", {}) if isinstance(graph, dict) else {}
    items = raw.items() if isinstance(raw, dict) else enumerate(raw) if isinstance(raw, list) else []
    output = {}
    for key, edge in items:
        if not isinstance(edge, dict):
            continue
        columns = [str(edge.get("source_signal") or ""), str(edge.get("target_signal") or "")]
        if not all(columns):
            columns = relationship_columns(edge)
        if len(columns) == 2:
            output[str(edge.get("relationship_id") or key)] = {"nodes": columns, "weight": _weight(edge)}
    return output


def _weight(edge: dict[str, Any]) -> float:
    for field in ("current_strength", "current_correlation", "recent_correlation", "strength"):
        value = finite_number(edge.get(field))
        if value is not None:
            return abs(float(value))
    return 0.0


def _components(edges: dict[str, dict[str, Any]]) -> int:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges.values():
        left, right = edge["nodes"]
        adjacency[left].add(right)
        adjacency[right].add(left)
    visited = set()
    count = 0
    for start in sorted(adjacency):
        if start in visited:
            continue
        count += 1
        queue = deque([start])
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            queue.extend(sorted(adjacency[node] - visited))
    return count


def _limited(reason: str, nodes: int, edges: int) -> dict[str, Any]:
    return {
        "status": "limited",
        "reason": reason,
        "method": "deterministic_edge_sensitivity_and_connectivity_v1",
        "graph_structural_stability": None,
        "edge_weight_sensitivity": {},
        "neighborhood_disruption": [],
        "connectivity_changes": {},
        "eigenvalue_indicators": None,
        "limitations": [reason],
        "processing_trace": {
            "nodes_evaluated": nodes,
            "edges_evaluated": edges,
            "network_risk_score_generated": False,
        },
    }
