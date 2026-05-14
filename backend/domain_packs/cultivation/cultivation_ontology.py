from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ARCHETYPES = [
    "DEHUMIDIFICATION_COMPENSATION",
    "THERMAL_LAG_PROPAGATION",
    "VPD_DECOUPLING",
    "CANOPY_STRESS_EMERGENCE",
    "ROOM_SYNCHRONIZATION_DRIFT",
    "LATENT_HUMIDITY_ACCUMULATION",
    "HVAC_LOAD_RESPONSE_MISMATCH",
    "TRANSIPRATION_IMBALANCE",
    "NIGHT_RECOVERY_FAILURE",
    "ENVIRONMENTAL_FRAGMENTATION",
    "AIRFLOW_PROPAGATION_DELAY",
    "COMPENSATION_MASKING",
    "MULTI_ROOM_PRESSURE_PROPAGATION",
]


@dataclass(frozen=True)
class CultivationEvidencePattern:
    required_signals: list[str]
    corroboration_targets: list[str]
    replay_requirements: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CultivationStructuralPrimitive:
    name: str
    structural_indicators: list[str]
    subsystem_relationships: list[str]
    topology_signature: str
    propagation_behavior: str
    replay_indicators: list[str]
    recovery_patterns: list[str]
    evidence_pattern: dict[str, Any]
    cultivation_explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CultivationArchetype:
    name: str
    primitive: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_cultivation_ontology() -> dict[str, Any]:
    archetypes = []
    for name in ARCHETYPES:
        primitive = CultivationStructuralPrimitive(
            name=name,
            structural_indicators=["temperature-humidity drift", "VPD coupling shift", "multi-room pressure divergence"],
            subsystem_relationships=["HVAC <-> dehumidification", "airflow <-> canopy", "room loop <-> facility loop"],
            topology_signature="cultivation environmental topology fragmentation tendency",
            propagation_behavior="directional pressure migration across coupled room loops",
            replay_indicators=["relationship_weakening", "propagation_activation", "continuation_window_compression"],
            recovery_patterns=["night reconvergence", "dehumidification unwind", "room synchronization restoration"],
            evidence_pattern=CultivationEvidencePattern(
                required_signals=["temperature", "humidity", "VPD", "airflow", "dehumidification runtime"],
                corroboration_targets=["subsystem coherence", "room synchronization", "replay continuity"],
                replay_requirements=["frame-linked phase progression", "propagation path continuity"],
            ).to_dict(),
            cultivation_explanation=f"{name.lower().replace('_', ' ')} indicates structural environmental change before obvious room deterioration.",
        ).to_dict()
        archetypes.append(CultivationArchetype(name=name, primitive=primitive).to_dict())
    return {"domain": "cultivation", "archetypes": archetypes, "count": len(archetypes)}

