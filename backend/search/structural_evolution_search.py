from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StructuralEvolutionQuery:
    text: str
    archetypes: list[str]
    pathways: list[str]
    convergence_terms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StructuralEvolutionSearchResult:
    query: dict[str, Any]
    results: list[dict[str, Any]]
    total_results: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplaySearchIndex:
    frame_count: int
    indexed_archetypes: list[str]
    indexed_paths: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BehavioralSimilaritySearch:
    def build_index(self, intelligence: dict[str, Any]) -> ReplaySearchIndex:
        timeline = intelligence.get("replay_timeline", {}).get("timeline", [])
        archetypes = [item.get("name", "") for item in intelligence.get("active_archetypes", [])]
        paths = intelligence.get("causality_graph", {}).get("dominant_pathways", [])
        return ReplaySearchIndex(frame_count=len(timeline), indexed_archetypes=archetypes, indexed_paths=paths)

    def search(self, query: StructuralEvolutionQuery, intelligence: dict[str, Any]) -> StructuralEvolutionSearchResult:
        matches: list[dict[str, Any]] = []
        for path in intelligence.get("causality_graph", {}).get("dominant_pathways", []):
            if not query.pathways or any(term.lower() in path.lower() for term in query.pathways):
                matches.append(
                    {
                        "match_type": "propagation_pathway",
                        "value": path,
                        "evidence": "replay-backed pathway match",
                    }
                )
        for item in intelligence.get("active_archetypes", []):
            name = item.get("name", "")
            if not query.archetypes or any(term.lower() in name.lower() for term in query.archetypes):
                matches.append(
                    {
                        "match_type": "archetype_emergence",
                        "value": name,
                        "evidence": item.get("evidence_strength", "developing"),
                    }
                )
        result = StructuralEvolutionSearchResult(query=query.to_dict(), results=matches, total_results=len(matches))
        return result

