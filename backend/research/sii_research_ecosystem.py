from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StructuralPrimitiveDataset:
    primitive_count: int
    primitive_names: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayResearchPacket:
    replay_frame_count: int
    replay_support: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OntologyResearchSnapshot:
    active_archetypes: list[str]
    ontology_coverage: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BehaviorScienceStudy:
    topology_study: str
    propagation_study: str
    convergence_study: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SIIResearchExport:
    primitive_dataset: dict[str, Any]
    replay_packet: dict[str, Any]
    ontology_snapshot: dict[str, Any]
    behavior_study: dict[str, Any]
    evidence_lineage_view: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_sii_research_ecosystem_export(
    *,
    primitives: dict[str, Any],
    metrics: dict[str, Any],
    archive: dict[str, Any],
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    primitive_names = [item.get("name", "") for item in primitives.get("primitives", [])]
    export = SIIResearchExport(
        primitive_dataset=StructuralPrimitiveDataset(
            primitive_count=len(primitive_names),
            primitive_names=primitive_names,
        ).to_dict(),
        replay_packet=ReplayResearchPacket(
            replay_frame_count=len(intelligence.get("replay_timeline", {}).get("timeline", [])),
            replay_support="strong_replay_alignment",
        ).to_dict(),
        ontology_snapshot=OntologyResearchSnapshot(
            active_archetypes=[item.get("name", "") for item in intelligence.get("active_archetypes", [])],
            ontology_coverage="broad_structural_coverage",
        ).to_dict(),
        behavior_study=BehaviorScienceStudy(
            topology_study="topology transition distance tracked across replay archive",
            propagation_study="propagation entropy and recurrence tracked across pathways",
            convergence_study=f"convergence stability tracked with value {metrics.get('convergence_stability', {}).get('stability', 0.0)}",
        ).to_dict(),
        evidence_lineage_view=[item.get("target", "") for item in intelligence.get("evidence_lineage", {}).get("lineages", [])],
    )
    payload = export.to_dict()
    payload["archive_summary"] = {
        "replay_sequences": len(archive.get("replay_sequences", [])),
        "topology_histories": len(archive.get("topology_evolution_histories", [])),
    }
    return payload

