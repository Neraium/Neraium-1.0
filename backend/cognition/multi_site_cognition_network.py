from __future__ import annotations

from typing import Any


def build_multi_site_cognition_network(facilities: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = [facility_node(item) for item in facilities]
    edges = []
    for idx, src in enumerate(nodes):
        for tgt in nodes[idx + 1 :]:
            shared = sorted(set(src["active_archetypes"]) & set(tgt["active_archetypes"]))
            if shared:
                edges.append(
                    {
                        "source": src["id"],
                        "target": tgt["id"],
                        "shared_archetypes": shared,
                        "cross_site_similarity": round(len(shared) / max(len(set(src["active_archetypes"]) | set(tgt["active_archetypes"])), 1), 4),
                    }
                )
    return {
        "facility_nodes": nodes,
        "cognition_network": {"nodes": nodes, "edges": edges},
        "cross_site_patterns": [
            {"pattern": "recurring_archetype_cluster", "members": edge["shared_archetypes"]}
            for edge in edges
        ],
        "fleet_structural_state": {
            "network_cognition_state": "clustered_pressure" if edges else "distributed_state",
            "fleet_wide_structural_pressure": "elevated" if len(edges) >= 2 else "localized",
            "cross_facility_evidence_summaries": [f"{edge['source']} <-> {edge['target']}" for edge in edges],
        },
    }


def facility_node(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("facility_id")),
        "name": item.get("facility_name"),
        "active_archetypes": item.get("active_archetypes", []),
        "dominant_paths": item.get("dominant_paths", []),
        "topology_state": item.get("topology_state", "unknown"),
    }

