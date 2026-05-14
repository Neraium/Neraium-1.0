from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ArchivedReplaySequence:
    replay_id: str
    frame_count: int
    canonical_flow: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArchivedTopologyEvolution:
    topology_state: str
    drift_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArchivedPropagationHistory:
    pathways: list[str]
    recurrence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArchivedConvergenceRecord:
    convergence_quality: str
    recovery_sequence: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArchivedOntologyEvolution:
    ontology_version: str
    extension_summary: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InfrastructureBehaviorArchive:
    replay_sequences: list[dict[str, Any]]
    topology_evolution_histories: list[dict[str, Any]]
    propagation_histories: list[dict[str, Any]]
    convergence_records: list[dict[str, Any]]
    ontology_evolution: list[dict[str, Any]]
    evidence_lineage_histories: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_infrastructure_behavior_archive(intelligence: dict[str, Any]) -> dict[str, Any]:
    timeline = intelligence.get("replay_timeline", {}).get("timeline", [])
    replay = ArchivedReplaySequence(
        replay_id="archive-replay-latest",
        frame_count=len(timeline),
        canonical_flow=intelligence.get("replay_timeline", {}).get("meta", {}).get("canonical_flow", []),
    ).to_dict()
    topology = ArchivedTopologyEvolution(
        topology_state=str(intelligence.get("structural_stability_index", {}).get("state", "WATCH")),
        drift_summary="stored structural drift transition history",
    ).to_dict()
    propagation = ArchivedPropagationHistory(
        pathways=intelligence.get("causality_graph", {}).get("dominant_pathways", []),
        recurrence="tracked for recurring pathway analytics",
    ).to_dict()
    convergence = ArchivedConvergenceRecord(
        convergence_quality=str(intelligence.get("recovery_convergence", {}).get("convergence_quality", "developing")),
        recovery_sequence=["propagation_decay", "reconvergence", "stabilization"],
    ).to_dict()
    ontology = ArchivedOntologyEvolution(
        ontology_version="v1.0.0",
        extension_summary=[item.get("name", "") for item in intelligence.get("ontology_extension_candidates", [])],
    ).to_dict()
    archive = InfrastructureBehaviorArchive(
        replay_sequences=[replay],
        topology_evolution_histories=[topology],
        propagation_histories=[propagation],
        convergence_records=[convergence],
        ontology_evolution=[ontology],
        evidence_lineage_histories=[item.get("target", "") for item in intelligence.get("evidence_lineage", {}).get("lineages", [])],
    )
    return archive.to_dict()

