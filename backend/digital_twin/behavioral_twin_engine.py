from __future__ import annotations

from typing import Any


class BehavioralTwinEngine:
    def build_twin(
        self,
        *,
        intelligence: dict[str, Any],
        replay_timeline: list[dict[str, Any]],
        benchmark: dict[str, Any],
    ) -> dict[str, Any]:
        room = str(intelligence.get("primary_room") or "facility")
        replay_history = replay_timeline[:24]
        continuation_overlays = [
            frame.get("continuation_window", {})
            for frame in replay_history
            if frame.get("continuation_window")
        ]
        return {
            "twin_id": f"behavioral-twin-{room.lower().replace(' ', '-')}",
            "topology_evolution_profile": [frame.get("topology_state", {}) for frame in replay_history],
            "cognition_state_history": [frame.get("cognition_state", {}) for frame in replay_history],
            "replayable_deterioration_behavior": [frame.get("cognition_state", {}).get("canonical_phase") for frame in replay_timeline],
            "subsystem_interaction_patterns": list(intelligence.get("facility_cognition", {}).get("subsystem_pressure", {}).get("subsystems", {}).keys()),
            "propagation_memory_overlay": intelligence.get("structural_memory", {}).get("memory_matches", [])[:3],
            "continuation_pathways": intelligence.get("causality_graph", {}).get("dominant_pathways", [])[:4],
            "convergence_behavior": intelligence.get("recovery_convergence", {}),
            "operational_timing": intelligence.get("operational_time_intelligence", {}),
            "benchmark_overlay": benchmark.get("cognition_quality_metrics", {}),
            "replay_history": replay_history,
            "continuation_overlays": continuation_overlays[:12],
            "propagation_simulation_overlay": intelligence.get("operational_cognition_simulation", {}),
            "convergence_simulation_overlay": intelligence.get("operational_cognition_simulation", {}).get("structural_evolution_scenarios", []),
            "ontology_linked_cognition": intelligence.get("structural_ontology", {}),
            "subsystem_interaction_memory": intelligence.get("facility_cognition", {}).get("subsystem_dependency_map", {}),
            "evidence_replay": intelligence.get("evidence_lineage", {}).get("lineages", []),
            "historical_cognition_comparisons": intelligence.get("deterioration_library_matches", [])[:5],
        }
