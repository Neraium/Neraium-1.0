from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class BehaviorResearchQuery:
    query_type: str
    prompt: str
    filters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TopologyEvolutionStudy:
    compared_systems: list[str]
    topology_drift_observation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PropagationStudy:
    recurring_pathways: list[str]
    pathway_acceleration_observation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConvergenceStudy:
    convergence_dynamics: str
    recurring_failures: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InterventionEffectStudy:
    adaptation_patterns: list[str]
    stabilization_impact: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BehaviorResearchResult:
    query: dict[str, Any]
    studies: dict[str, Any]
    evidence_summary: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_behavior_research(intelligence: dict[str, Any]) -> dict[str, Any]:
    query = BehaviorResearchQuery(
        query_type="cross_system_topology_and_convergence",
        prompt="compare topology evolution and recurring convergence behavior",
        filters={"include_replay": True, "include_evidence_lineage": True},
    )
    studies = {
        "topology_evolution": TopologyEvolutionStudy(
            compared_systems=["facility-primary", "facility-peer-a"],
            topology_drift_observation="shared drift acceleration during high pressure cycles",
        ).to_dict(),
        "propagation": PropagationStudy(
            recurring_pathways=intelligence.get("causality_graph", {}).get("dominant_pathways", [])[:5],
            pathway_acceleration_observation="repeated pathway acceleration after compensation masking",
        ).to_dict(),
        "convergence": ConvergenceStudy(
            convergence_dynamics=str(intelligence.get("recovery_convergence", {}).get("convergence_quality", "developing")),
            recurring_failures=["delayed_recovery", "partial_reconvergence"],
        ).to_dict(),
        "intervention_effect": InterventionEffectStudy(
            adaptation_patterns=[item.get("adaptation_type", "timing_adjustment") for item in intelligence.get("operator_cognition_training", {}).get("scenarios", [])][:3],
            stabilization_impact="operator timing adjustments correlate with improved reconvergence consistency",
        ).to_dict(),
    }
    result = BehaviorResearchResult(
        query=query.to_dict(),
        studies=studies,
        evidence_summary=[item.get("target", "") for item in intelligence.get("evidence_lineage", {}).get("lineages", [])][:8],
    )
    return result.to_dict()

