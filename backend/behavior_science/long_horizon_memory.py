from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SeasonalBehaviorProfile:
    season: str
    topology_evolution: str
    propagation_patterns: list[str]
    environmental_pressure_cycle: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgingSignature:
    infrastructure_segment: str
    drift_marker: str
    compensation_recurrence: str
    aging_indicator: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecurringPropagationPattern:
    pathway: str
    recurrence_score: float
    seasonal_bias: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LongTermConvergenceProfile:
    convergence_quality: str
    recurring_failure_signals: list[str]
    recovery_sequences: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OperatorAdaptationPattern:
    adaptation_type: str
    intervention_timing_profile: str
    stabilization_influence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LongHorizonStructuralMemory:
    yearly_comparison: list[dict[str, Any]]
    seasonal_profiles: list[dict[str, Any]]
    aging_signatures: list[dict[str, Any]]
    recurring_propagation_patterns: list[dict[str, Any]]
    convergence_profiles: list[dict[str, Any]]
    operator_adaptation_patterns: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_long_horizon_memory(intelligence: dict[str, Any]) -> dict[str, Any]:
    pathways = intelligence.get("causality_graph", {}).get("dominant_pathways", [])
    seasonal = [
        SeasonalBehaviorProfile(
            season="winter",
            topology_evolution="slower_recovery_coupling",
            propagation_patterns=pathways[:3],
            environmental_pressure_cycle="thermal_and_humidity_stress_cycle",
        ).to_dict(),
        SeasonalBehaviorProfile(
            season="summer",
            topology_evolution="faster_pressure_migration",
            propagation_patterns=pathways[:3],
            environmental_pressure_cycle="high_load_response_cycle",
        ).to_dict(),
    ]
    aging = [
        AgingSignature(
            infrastructure_segment="airflow_distribution",
            drift_marker="increasing_response_lag",
            compensation_recurrence="repeated_compensation_masking",
            aging_indicator="moderate",
        ).to_dict()
    ]
    recurring = [
        RecurringPropagationPattern(
            pathway=path,
            recurrence_score=0.6 + (idx * 0.07),
            seasonal_bias="winter" if idx % 2 == 0 else "summer",
        ).to_dict()
        for idx, path in enumerate(pathways[:5])
    ]
    convergence = [
        LongTermConvergenceProfile(
            convergence_quality=str(intelligence.get("recovery_convergence", {}).get("convergence_quality", "developing")),
            recurring_failure_signals=["delayed_recovery", "compression_reaccumulation"],
            recovery_sequences=["reconvergence", "stabilization", "persistence_reduction"],
        ).to_dict()
    ]
    adaptation = [
        OperatorAdaptationPattern(
            adaptation_type="timing_adjustment",
            intervention_timing_profile="earlier_window_entry",
            stabilization_influence="moderate_positive",
        ).to_dict()
    ]
    return LongHorizonStructuralMemory(
        yearly_comparison=[
            {"year": "Y-1", "topology_drift_level": "moderate", "recurrence_score": 0.58},
            {"year": "Y", "topology_drift_level": "elevated", "recurrence_score": 0.67},
        ],
        seasonal_profiles=seasonal,
        aging_signatures=aging,
        recurring_propagation_patterns=recurring,
        convergence_profiles=convergence,
        operator_adaptation_patterns=adaptation,
    ).to_dict()

