from __future__ import annotations

from typing import Any

from ontology.archetypes import ARCHETYPES


CANONICAL_VOCABULARY = [
    "topology drift",
    "propagation pathway",
    "continuation window",
    "subsystem fragmentation",
    "convergence",
    "structural compression",
    "archetype emergence",
    "cognition state",
    "structural memory",
    "operational timing",
    "topology coherence",
]


def build_structural_ontology() -> dict[str, Any]:
    nodes = [item.to_dict() for item in ARCHETYPES]
    relationships = []
    for item in nodes:
        name = item["name"]
        relationships.append(
            {
                "source": name,
                "targets": infer_targets(name),
                "interaction_pattern": infer_pattern(name),
                "topology_signature": infer_topology_signature(name),
            }
        )
    return {
        "vocabulary": CANONICAL_VOCABULARY,
        "archetype_nodes": nodes,
        "archetype_relationships": relationships,
        "ontology_primitives": {
            "instability_lifecycle": [
                "stable_topology",
                "relationship_weakening",
                "pressure_migration",
                "archetype_emergence",
                "propagation_activation",
                "subsystem_fragmentation",
                "continuation_pathway",
                "recovery_or_escalation",
            ],
            "evidence_requirements": [
                "corroborating_signals",
                "relationship_evolution",
                "topology_support",
                "propagation_confirmation",
                "historical_similarity",
            ],
        },
    }


def infer_targets(name: str) -> list[str]:
    if name in {"RELATIONSHIP_DECAY", "SUBSYSTEM_DESYNCHRONIZATION"}:
        return ["PROPAGATION_ACCELERATION", "TOPOLOGY_FRAGMENTATION"]
    if name in {"STRUCTURAL_COMPRESSION", "LATENT_PRESSURE_ACCUMULATION"}:
        return ["DELAYED_DIVERGENCE", "TOPOLOGY_FRAGMENTATION"]
    if name in {"RECOVERY_RECONVERGENCE", "RECOVERY_CONVERGENCE"}:
        return ["STABLE_TOPOLOGY"]
    return ["CONTINUATION_PATHWAY"]


def infer_pattern(name: str) -> str:
    if "RECOVERY" in name:
        return "convergent"
    if "COMPRESSION" in name or "LATENT" in name:
        return "subtle-accumulative"
    if "PROPAGATION" in name or "CASCADING" in name:
        return "accelerative"
    return "degradation-linked"


def infer_topology_signature(name: str) -> str:
    if name in {"TOPOLOGY_FRAGMENTATION", "SUBSYSTEM_FRAGMENTATION"}:
        return "cross-subsystem decoupling"
    if name in {"RECOVERY_RECONVERGENCE", "RECOVERY_CONVERGENCE"}:
        return "pathway collapse and recoupling"
    if name in {"STRUCTURAL_COMPRESSION", "LATENT_PRESSURE_ACCUMULATION"}:
        return "hidden pressure concentration"
    return "relationship drift concentration"

