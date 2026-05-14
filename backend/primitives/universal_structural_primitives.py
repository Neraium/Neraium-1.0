from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


PRIMITIVE_NAMES = [
    "PROPAGATION",
    "CONVERGENCE",
    "COMPENSATION",
    "FRAGMENTATION",
    "STABILIZATION",
    "SYNCHRONIZATION",
    "LATENT_PRESSURE",
    "OSCILLATION",
    "COMPRESSION",
    "RELEASE",
    "PERSISTENCE",
    "RECOVERY",
    "DIVERGENCE",
    "COUPLING",
    "DECOUPLING",
]


@dataclass(frozen=True)
class PrimitiveEvidenceRequirement:
    requirement: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PrimitiveReplaySignature:
    canonical_phases: list[str]
    progression_marker: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PrimitiveOntologyMapping:
    compatible_archetypes: list[str]
    ontology_targets: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UniversalStructuralPrimitive:
    name: str
    structural_meaning: str
    topology_signature: str
    temporal_behavior: str
    evidence_requirements: list[dict[str, Any]]
    replay_signature: dict[str, Any]
    ontology_mapping: dict[str, Any]
    domain_agnostic_examples: list[str]
    operator_explanation_language: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_universal_structural_primitives() -> dict[str, Any]:
    primitives = []
    for name in PRIMITIVE_NAMES:
        primitive = UniversalStructuralPrimitive(
            name=name,
            structural_meaning=f"{name.lower().replace('_', ' ')} as a foundational infrastructure behavior primitive",
            topology_signature="coherence reweighting across subsystem relationships",
            temporal_behavior="emerges through staged structural progression rather than abrupt deterministic transition",
            evidence_requirements=[
                PrimitiveEvidenceRequirement(
                    requirement="corroborating_relationship_evidence",
                    rationale="ensures primitive interpretation is supported across subsystem relationships",
                ).to_dict(),
                PrimitiveEvidenceRequirement(
                    requirement="replay_phase_alignment",
                    rationale="ensures primitive is replay-grounded in observed timeline phases",
                ).to_dict(),
            ],
            replay_signature=PrimitiveReplaySignature(
                canonical_phases=["relationship_weakening", "pressure_migration", "propagation_activation"],
                progression_marker="evidence-backed phase transition",
            ).to_dict(),
            ontology_mapping=PrimitiveOntologyMapping(
                compatible_archetypes=["PROPAGATION_ACCELERATION", "COMPENSATION_MASKING", "RECOVERY_RECONVERGENCE"],
                ontology_targets=["structural_ontology", "ontology_corpus"],
            ).to_dict(),
            domain_agnostic_examples=[
                "airflow-thermal coupling transition",
                "load-response synchronization drift",
                "pressure-mediated propagation pathway",
            ],
            operator_explanation_language=f"{name.lower().replace('_', ' ')} is present as an evidence-backed structural tendency.",
        )
        primitives.append(primitive.to_dict())
    return {"primitives": primitives, "primitive_count": len(primitives)}

