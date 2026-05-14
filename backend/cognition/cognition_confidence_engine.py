from __future__ import annotations

from typing import Any


CONFIDENCE_TIERS = (
    "LOW_EVIDENCE",
    "MODERATE_EVIDENCE",
    "HIGH_EVIDENCE",
    "STRONG_CONVERGENCE",
)


class CognitionConfidenceEngine:
    def calibrate(
        self,
        *,
        intelligence: dict[str, Any],
        evidence_lineage: dict[str, Any],
        engine_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        engine_result = engine_result or {}
        corroboration = evidence_lineage.get("corroboration_model", {}).get("corroboration_quality", "DEVELOPING")
        persistence = len(engine_result.get("persistence_assessment", {}).get("persistent_columns", []))
        subsystems = len(intelligence.get("facility_cognition", {}).get("subsystem_pressure", {}).get("subsystems", {}))
        paths = len(intelligence.get("causality_graph", {}).get("dominant_pathways", []))
        memory_score = float((intelligence.get("structural_memory", {}).get("memory_matches", [{}])[0]).get("similarity_score", 0.0))
        archetype_count = len(intelligence.get("active_archetypes", []))
        ordinal = score(
            corroboration=corroboration,
            persistence=persistence,
            subsystems=subsystems,
            pathways=paths,
            memory_score=memory_score,
            archetype_count=archetype_count,
        )
        tier = tier_for_score(ordinal)
        return {
            "confidence_tier": tier,
            "ordinal_score": ordinal,
            "corroboration_strength": corroboration,
            "factors": {
                "persistence_consistency": "HIGH" if persistence >= 2 else "MODERATE" if persistence == 1 else "LOW",
                "subsystem_agreement": "HIGH" if subsystems >= 3 else "MODERATE" if subsystems >= 1 else "LOW",
                "topology_consistency": "HIGH" if paths >= 3 else "MODERATE" if paths >= 1 else "LOW",
                "propagation_consistency": "HIGH" if paths >= 2 else "LOW",
                "historical_memory_similarity": "HIGH" if memory_score >= 0.7 else "MODERATE" if memory_score >= 0.5 else "LOW",
                "archetype_agreement": "HIGH" if archetype_count >= 3 else "MODERATE" if archetype_count >= 1 else "LOW",
            },
            "descriptor": descriptor_for_tier(tier),
        }


def score(
    *,
    corroboration: str,
    persistence: int,
    subsystems: int,
    pathways: int,
    memory_score: float,
    archetype_count: int,
) -> int:
    total = 0
    total += {"DEVELOPING": 1, "MODERATE": 2, "STRONG": 3}.get(corroboration, 1)
    total += 2 if persistence >= 2 else 1 if persistence == 1 else 0
    total += 2 if subsystems >= 3 else 1 if subsystems >= 1 else 0
    total += 2 if pathways >= 3 else 1 if pathways >= 1 else 0
    total += 2 if memory_score >= 0.7 else 1 if memory_score >= 0.5 else 0
    total += 2 if archetype_count >= 3 else 1 if archetype_count >= 1 else 0
    return total


def tier_for_score(total: int) -> str:
    if total >= 11:
        return "STRONG_CONVERGENCE"
    if total >= 8:
        return "HIGH_EVIDENCE"
    if total >= 5:
        return "MODERATE_EVIDENCE"
    return "LOW_EVIDENCE"


def descriptor_for_tier(tier: str) -> str:
    return {
        "LOW_EVIDENCE": "Evidence is present but remains sparse across corroboration dimensions.",
        "MODERATE_EVIDENCE": "Evidence lines are partially convergent and operationally useful for review.",
        "HIGH_EVIDENCE": "Evidence is dense and corroborated across subsystem, topology, and propagation dimensions.",
        "STRONG_CONVERGENCE": "Evidence strongly converges across structural memory, topology, persistence, and propagation lineage.",
    }[tier]
