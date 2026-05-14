from __future__ import annotations

from typing import Any


class MultiFacilityCognitionEngine:
    def build_graph(self, *, facilities: list[dict[str, Any]]) -> dict[str, Any]:
        nodes = []
        edges = []
        for facility in facilities:
            fid = str(facility.get("facility_id"))
            nodes.append(
                {
                    "id": fid,
                    "label": facility.get("facility_name", fid),
                    "active_archetypes": facility.get("active_archetypes", []),
                    "topology_state": facility.get("topology_state", "unknown"),
                }
            )
        for idx, source in enumerate(facilities):
            for target in facilities[idx + 1 :]:
                similarity = similarity_score(source, target)
                if similarity >= 0.32:
                    edges.append(
                        {
                            "source": str(source.get("facility_id")),
                            "target": str(target.get("facility_id")),
                            "structural_similarity": round(similarity, 4),
                            "shared_archetypes": shared_archetypes(source, target),
                        }
                    )
        return {
            "facility_cognition_graph": {"nodes": nodes, "edges": edges},
            "recurring_deterioration_pathways": recurring_pathways(facilities),
            "shared_archetype_emergence": recurring_archetypes(facilities),
            "fleet_topology_shift_state": fleet_shift_state(facilities),
        }


def shared_archetypes(source: dict[str, Any], target: dict[str, Any]) -> list[str]:
    src = {str(item) for item in source.get("active_archetypes", [])}
    tgt = {str(item) for item in target.get("active_archetypes", [])}
    return sorted(src & tgt)


def similarity_score(source: dict[str, Any], target: dict[str, Any]) -> float:
    shared = shared_archetypes(source, target)
    total = len(set(source.get("active_archetypes", [])) | set(target.get("active_archetypes", [])))
    if total == 0:
        return 0.0
    return len(shared) / total


def recurring_pathways(facilities: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for facility in facilities:
        for path in facility.get("dominant_paths", []):
            counts[path] = counts.get(path, 0) + 1
    return [path for path, count in counts.items() if count >= 2]


def recurring_archetypes(facilities: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for facility in facilities:
        for archetype in facility.get("active_archetypes", []):
            counts[archetype] = counts.get(archetype, 0) + 1
    return [name for name, count in counts.items() if count >= 2]


def fleet_shift_state(facilities: list[dict[str, Any]]) -> str:
    fragmenting = sum(1 for facility in facilities if "FRAGMENT" in str(facility.get("topology_state", "")).upper())
    if fragmenting >= max(2, len(facilities) // 2):
        return "fleet_fragmentation_pressure"
    if fragmenting >= 1:
        return "localized_shift"
    return "fleet_coherent"

