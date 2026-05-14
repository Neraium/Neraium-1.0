from __future__ import annotations

from typing import Any


def query_recurring_pathways(graph: dict[str, Any]) -> list[str]:
    nodes = graph.get("nodes", [])
    return [node["attributes"]["path"] for node in nodes if node.get("node_type") == "propagation_pathway"]


def query_cross_domain_archetype_matches(graph: dict[str, Any]) -> list[str]:
    nodes = graph.get("nodes", [])
    return [node["node_id"] for node in nodes if node.get("node_type") == "archetype"]

