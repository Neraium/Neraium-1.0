from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TopologyTransitionMeasure:
    transition_distance: float
    transition_label: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PropagationEntropy:
    entropy: float
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConvergenceStability:
    stability: float
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SubsystemCoherence:
    coherence: float
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StructuralPersistence:
    persistence: float
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StructuralEvolutionMetrics:
    topology_transition: dict[str, Any]
    propagation_entropy: dict[str, Any]
    convergence_stability: dict[str, Any]
    subsystem_coherence: dict[str, Any]
    structural_persistence: dict[str, Any]
    fragmentation_pressure: float
    compensation_load: float
    coupling_volatility: float
    recovery_gradient: float
    latent_pressure_accumulation: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_structural_evolution_metrics(intelligence: dict[str, Any]) -> dict[str, Any]:
    pathways = intelligence.get("causality_graph", {}).get("dominant_pathways", [])
    path_count = max(1, len(pathways))
    propagation_score = float(intelligence.get("causality_graph", {}).get("propagation_score", 0.0))
    convergence_index = float(intelligence.get("recovery_convergence", {}).get("convergence_index", 0.5))
    fragmentation_pressure = float(intelligence.get("facility_cognition", {}).get("global_structural_pressure_score", 0.4))
    compensation_load = min(1.0, propagation_score * 0.7 + (path_count * 0.05))
    coupling_volatility = min(1.0, abs(propagation_score - convergence_index))
    recovery_gradient = max(0.0, convergence_index - fragmentation_pressure * 0.5)
    latent_pressure_accumulation = min(1.0, fragmentation_pressure * 0.6 + compensation_load * 0.4)
    metrics = StructuralEvolutionMetrics(
        topology_transition=TopologyTransitionMeasure(
            transition_distance=min(1.0, propagation_score + fragmentation_pressure * 0.3),
            transition_label="structural_transition_distance",
        ).to_dict(),
        propagation_entropy=PropagationEntropy(
            entropy=min(1.0, path_count / 10.0 + propagation_score * 0.4),
            interpretation="higher values indicate broader pathway diversification",
        ).to_dict(),
        convergence_stability=ConvergenceStability(
            stability=max(0.0, min(1.0, convergence_index)),
            interpretation="higher values indicate stronger structural reconvergence tendency",
        ).to_dict(),
        subsystem_coherence=SubsystemCoherence(
            coherence=max(0.0, 1.0 - fragmentation_pressure),
            interpretation="higher values indicate tighter subsystem coupling coherence",
        ).to_dict(),
        structural_persistence=StructuralPersistence(
            persistence=min(1.0, 0.3 + path_count * 0.06),
            interpretation="higher values indicate persistent structural pattern recurrence",
        ).to_dict(),
        fragmentation_pressure=fragmentation_pressure,
        compensation_load=compensation_load,
        coupling_volatility=coupling_volatility,
        recovery_gradient=recovery_gradient,
        latent_pressure_accumulation=latent_pressure_accumulation,
    )
    return metrics.to_dict()

