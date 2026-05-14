from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


BEHAVIORAL_CLASSES = [
    "COMPENSATORY_SYSTEM",
    "OSCILLATORY_SYSTEM",
    "FRAGMENTATION_PRONE_SYSTEM",
    "DELAYED_RESPONSE_SYSTEM",
    "PROPAGATION_SENSITIVE_SYSTEM",
    "CONVERGENCE_RESISTANT_SYSTEM",
    "COMPRESSION_DOMINATED_SYSTEM",
    "RECOVERY_CAPABLE_SYSTEM",
    "ENVIRONMENTALLY_COUPLED_SYSTEM",
]


@dataclass(frozen=True)
class BehavioralClass:
    name: str
    structural_traits: list[str]
    topology_signatures: list[str]
    propagation_tendencies: list[str]
    recovery_characteristics: list[str]
    evidence_requirements: list[str]
    replay_indicators: list[str]
    domain_examples: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BehavioralClassificationResult:
    primary_class: str
    secondary_classes: list[str]
    evidence_basis: list[str]
    replay_support: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BehavioralTaxonomy:
    classes: list[dict[str, Any]]
    classification_result: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_behavioral_taxonomy(intelligence: dict[str, Any]) -> dict[str, Any]:
    class_defs = [
        BehavioralClass(
            name=name,
            structural_traits=["relationship_drift", "pressure_migration"],
            topology_signatures=["coherence_shift", "pathway_reweighting"],
            propagation_tendencies=["directional_flow", "intermittent_acceleration"],
            recovery_characteristics=["delayed_reconvergence", "partial_stabilization"],
            evidence_requirements=["lineage_corroboration", "replay_support"],
            replay_indicators=["archetype_emergence", "propagation_activation"],
            domain_examples=["cultivation", "data_center", "manufacturing", "water", "energy"],
        ).to_dict()
        for name in BEHAVIORAL_CLASSES
    ]
    active_archetypes = [item.get("name", "") for item in intelligence.get("active_archetypes", [])]
    primary = "RECOVERY_CAPABLE_SYSTEM" if "RECOVERY_RECONVERGENCE" in active_archetypes else "PROPAGATION_SENSITIVE_SYSTEM"
    result = BehavioralClassificationResult(
        primary_class=primary,
        secondary_classes=["COMPENSATORY_SYSTEM", "DELAYED_RESPONSE_SYSTEM"],
        evidence_basis=[item.get("target", "") for item in intelligence.get("evidence_lineage", {}).get("lineages", [])][:5],
        replay_support="strong" if intelligence.get("replay_timeline", {}).get("timeline") else "developing",
    ).to_dict()
    return BehavioralTaxonomy(classes=class_defs, classification_result=result).to_dict()

