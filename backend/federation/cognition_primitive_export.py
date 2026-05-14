from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FederatedCognitionPrimitive:
    primitive_type: str
    signature: str
    evidence_summary: str
    replay_fingerprint: str
    privacy_level: str = "privacy_preserving"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def export_primitives(intelligence: dict[str, Any]) -> list[dict[str, Any]]:
    archetypes = intelligence.get("active_archetypes", [])
    pathways = intelligence.get("causality_graph", {}).get("dominant_pathways", [])
    primitives = [
        FederatedCognitionPrimitive(
            primitive_type="archetype_signature",
            signature=item.get("name", ""),
            evidence_summary=item.get("evidence_strength", "developing"),
            replay_fingerprint=f"arch:{item.get('name', '')}",
        ).to_dict()
        for item in archetypes
    ]
    primitives.extend(
        FederatedCognitionPrimitive(
            primitive_type="propagation_primitive",
            signature=path,
            evidence_summary="pathway corroborated",
            replay_fingerprint=f"path:{idx}",
        ).to_dict()
        for idx, path in enumerate(pathways)
    )
    return primitives

