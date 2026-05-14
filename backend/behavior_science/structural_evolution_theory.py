from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StructuralEvolutionRule:
    rule_id: str
    title: str
    conditions: list[str]
    evidence_requirements: list[str]
    expected_structural_behavior: str
    continuation_implications: str
    recovery_implications: str
    replay_references: list[str]
    confidence_basis: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionRuleEvaluation:
    rule_id: str
    matched: bool
    evidence_basis: list[str]
    uncertainty_disclosure: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvolutionTheoryEngine:
    def rules(self) -> list[dict[str, Any]]:
        return [
            StructuralEvolutionRule(
                rule_id="rule-topology-destabilization",
                title="Topology destabilization precedes visible fragmentation.",
                conditions=["relationship_decay", "pressure_migration", "persistence_increase"],
                evidence_requirements=["lineage_corroboration", "replay_phase_progression"],
                expected_structural_behavior="coherence_degradation_with_pathway_activation",
                continuation_implications="elevated_fragmentation_tendency",
                recovery_implications="requires reconvergence support",
                replay_references=["stable_topology", "relationship_weakening", "propagation_activation"],
                confidence_basis="evidence_density_and_replay_consistency",
            ).to_dict(),
            StructuralEvolutionRule(
                rule_id="rule-compression-release",
                title="Structural compression tends to release through delayed divergence.",
                conditions=["compression_accumulation", "compensation_masking", "latent_pressure"],
                evidence_requirements=["compression_lineage", "delayed_divergence_replay_pattern"],
                expected_structural_behavior="sudden_pathway_acceleration_after_hidden_accumulation",
                continuation_implications="narrower_continuation_window",
                recovery_implications="requires compensation_unwinding",
                replay_references=["structural_compression", "delayed_divergence"],
                confidence_basis="cross_run_recurrence_and_topology_support",
            ).to_dict(),
        ]

    def evaluate(self, intelligence: dict[str, Any]) -> list[dict[str, Any]]:
        active = {item.get("name", "") for item in intelligence.get("active_archetypes", [])}
        evidence_targets = [item.get("target", "") for item in intelligence.get("evidence_lineage", {}).get("lineages", [])]
        evaluations = [
            EvolutionRuleEvaluation(
                rule_id="rule-topology-destabilization",
                matched=bool(active),
                evidence_basis=evidence_targets[:4],
                uncertainty_disclosure="non_deterministic_structural_tendency",
            ).to_dict(),
            EvolutionRuleEvaluation(
                rule_id="rule-compression-release",
                matched="STRUCTURAL_COMPRESSION" in active,
                evidence_basis=evidence_targets[:4],
                uncertainty_disclosure="requires additional seasonal corroboration",
            ).to_dict(),
        ]
        return evaluations

