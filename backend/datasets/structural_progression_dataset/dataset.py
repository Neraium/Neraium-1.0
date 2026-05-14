from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StructuralProgressionDataset:
    dataset_id: str
    topology_evolution: list[dict[str, Any]]
    propagation_chains: list[str]
    archetype_emergence: list[str]
    subsystem_fragmentation: list[str]
    continuation_pathways: list[str]
    convergence_behavior: list[str]
    replay_sequences: list[str]
    operational_timing: dict[str, Any]
    evidence_structures: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_structural_progression_dataset(*, intelligence: dict[str, Any], replay_timeline: list[dict[str, Any]]) -> dict[str, Any]:
    dataset = StructuralProgressionDataset(
        dataset_id=f"spd-{str(intelligence.get('primary_room', 'facility')).lower().replace(' ', '-')}",
        topology_evolution=[frame.get("topology_state", {}) for frame in replay_timeline[:24]],
        propagation_chains=intelligence.get("causality_graph", {}).get("dominant_pathways", []),
        archetype_emergence=[item.get("name", "") for item in intelligence.get("active_archetypes", [])],
        subsystem_fragmentation=[intelligence.get("structural_stability_index", {}).get("state", "WATCH")],
        continuation_pathways=intelligence.get("counterfactuals", {}).get("structural_continuation_pathways", []),
        convergence_behavior=[intelligence.get("recovery_convergence", {}).get("convergence_quality", "LOW_CONVERGENCE")],
        replay_sequences=[frame.get("cognition_state", {}).get("canonical_phase") for frame in replay_timeline],
        operational_timing=intelligence.get("operational_time_intelligence", {}),
        evidence_structures=["signal_lineage", "topology_lineage", "propagation_lineage", "memory_lineage"],
    )
    return dataset.to_dict()

