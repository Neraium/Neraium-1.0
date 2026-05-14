from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class CognitionGraphNode:
    node_id: str
    node_type: str
    attributes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CognitionGraphEdge:
    source: str
    target: str
    edge_type: str
    attributes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CognitionGraphSnapshot:
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_structural_cognition_graph(intelligence: dict[str, Any]) -> dict[str, Any]:
    archetypes = intelligence.get("active_archetypes", [])
    paths = intelligence.get("causality_graph", {}).get("dominant_pathways", [])
    nodes = [
        CognitionGraphNode(node_id=f"arch:{item.get('name')}", node_type="archetype", attributes={"evidence_strength": item.get("evidence_strength")}).to_dict()
        for item in archetypes
    ]
    for idx, path in enumerate(paths):
        nodes.append(CognitionGraphNode(node_id=f"path:{idx}", node_type="propagation_pathway", attributes={"path": path}).to_dict())
    edges = []
    for idx, item in enumerate(archetypes[: len(paths)]):
        edges.append(
            CognitionGraphEdge(
                source=f"arch:{item.get('name')}",
                target=f"path:{idx}",
                edge_type="influences_pathway",
                attributes={"confidence_band": item.get("confidence_band")},
            ).to_dict()
        )
    return {
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
        "snapshot": CognitionGraphSnapshot(nodes=nodes, edges=edges, timestamp=intelligence.get("last_updated", "")).to_dict(),
    }

