from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DomainCognitionPack:
    domain: str
    subsystem_types: list[str]
    propagation_pathways: list[str]
    structural_relationships: list[str]
    domain_archetype_mappings: list[str]
    subsystem_dependency_graph: list[str]
    environmental_context: list[str]
    operational_timing_patterns: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DOMAIN_PACKS: dict[str, DomainCognitionPack] = {
    "cultivation": DomainCognitionPack(
        domain="cultivation",
        subsystem_types=["HVAC", "dehumidification", "airflow", "irrigation", "lighting", "sensor network"],
        propagation_pathways=["airflow -> thermal", "thermal -> humidity", "irrigation timing -> moisture response"],
        structural_relationships=["temperature-humidity coupling", "airflow-pressure balance"],
        domain_archetype_mappings=["THERMAL_PROPAGATION", "STRUCTURAL_COMPRESSION", "COMPENSATION_MASKING"],
        subsystem_dependency_graph=["airflow=>thermal", "thermal=>humidity", "timing=>moisture"],
        environmental_context=["ambient weather", "crop phase", "room moisture load"],
        operational_timing_patterns=["transition windows", "feed cycles", "light schedule boundaries"],
    ),
    "data_centers": DomainCognitionPack(
        domain="data_centers",
        subsystem_types=["cooling loops", "air handling", "power distribution", "workload clusters", "network fabric"],
        propagation_pathways=["workload surge -> thermal load", "thermal load -> cooling compensation", "power imbalance -> thermal divergence"],
        structural_relationships=["load-response coherence", "cooling-power interaction"],
        domain_archetype_mappings=["LOAD_RESPONSE_MISMATCH", "PROPAGATION_ACCELERATION", "RESPONSE_LAG"],
        subsystem_dependency_graph=["workload=>thermal", "thermal=>cooling", "power=>thermal"],
        environmental_context=["external temperature", "rack density", "power quality"],
        operational_timing_patterns=["batch workload windows", "peak demand periods"],
    ),
    "aerospace_manufacturing": DomainCognitionPack(
        domain="aerospace_manufacturing",
        subsystem_types=["assembly cells", "thermal treatment", "airflow systems", "power systems", "quality stations"],
        propagation_pathways=["line load -> thermal variation", "thermal variation -> tolerance drift"],
        structural_relationships=["line cadence-response synchronization", "thermal-quality coupling"],
        domain_archetype_mappings=["SUBSYSTEM_DESYNCHRONIZATION", "DELAYED_DIVERGENCE", "OSCILLATORY_INSTABILITY"],
        subsystem_dependency_graph=["line_load=>thermal", "thermal=>quality"],
        environmental_context=["shift changes", "ambient variability", "material batch variation"],
        operational_timing_patterns=["shift transitions", "batch-to-batch windows"],
    ),
    "water_infrastructure": DomainCognitionPack(
        domain="water_infrastructure",
        subsystem_types=["pumping", "distribution pressure", "treatment", "storage", "sensor network"],
        propagation_pathways=["pressure imbalance -> flow redistribution", "flow redistribution -> treatment lag"],
        structural_relationships=["pressure-flow coupling", "storage-treatment coherence"],
        domain_archetype_mappings=["TOPOLOGY_FRAGMENTATION", "LATENT_PRESSURE_ACCUMULATION", "RECOVERY_RECONVERGENCE"],
        subsystem_dependency_graph=["pressure=>flow", "flow=>treatment", "storage=>distribution"],
        environmental_context=["demand spikes", "source variability", "weather events"],
        operational_timing_patterns=["daily demand cycle", "storm-driven load windows"],
    ),
    "energy_systems": DomainCognitionPack(
        domain="energy_systems",
        subsystem_types=["generation", "storage", "distribution", "load balancing", "control telemetry"],
        propagation_pathways=["load variability -> balancing pressure", "balancing pressure -> storage compensation"],
        structural_relationships=["generation-load synchronization", "storage-compensation coupling"],
        domain_archetype_mappings=["CASCADING_COMPENSATION", "PROPAGATION_ACCELERATION", "STRUCTURAL_COMPRESSION"],
        subsystem_dependency_graph=["load=>balancing", "balancing=>storage", "generation=>distribution"],
        environmental_context=["market demand", "weather-dependent generation", "grid events"],
        operational_timing_patterns=["peak/off-peak cycles", "dispatch windows"],
    ),
}


def resolve_domain_pack(domain: str) -> dict[str, Any]:
    key = (domain or "cultivation").strip().lower().replace(" ", "_")
    if key in {"aerospace", "manufacturing", "aerospace/manufacturing"}:
        key = "aerospace_manufacturing"
    pack = DOMAIN_PACKS.get(key) or DOMAIN_PACKS["cultivation"]
    return pack.to_dict()

