from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PrivacyPreservingCognitionSummary:
    facility_hash: str
    archetype_signatures: list[str]
    topology_summary: dict[str, Any]
    propagation_primitives: list[str]
    evidence_summary: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sanitize_for_federation(intelligence: dict[str, Any], *, facility_hash: str) -> PrivacyPreservingCognitionSummary:
    return PrivacyPreservingCognitionSummary(
        facility_hash=facility_hash,
        archetype_signatures=[item.get("name", "") for item in intelligence.get("active_archetypes", [])],
        topology_summary={
            "state": intelligence.get("structural_stability_index", {}).get("state", "WATCH"),
            "coherence": intelligence.get("structural_stability_index", {}).get("coherence_profile", "developing"),
        },
        propagation_primitives=intelligence.get("causality_graph", {}).get("dominant_pathways", []),
        evidence_summary=[item.get("target", "") for item in intelligence.get("evidence_lineage", {}).get("lineages", [])],
    )

