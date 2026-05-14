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
        return {
            "twin_id": f"behavioral-twin-{room.lower().replace(' ', '-')}",
            "topology_evolution_profile": [frame.get("topology_state", {}) for frame in replay_timeline[:12]],
            "cognition_state_history": [frame.get("cognition_state", {}) for frame in replay_timeline[:12]],
            "replayable_deterioration_behavior": [frame.get("cognition_state", {}).get("canonical_phase") for frame in replay_timeline],
            "subsystem_interaction_patterns": list(intelligence.get("facility_cognition", {}).get("subsystem_pressure", {}).get("subsystems", {}).keys()),
            "propagation_memory_overlay": intelligence.get("structural_memory", {}).get("memory_matches", [])[:3],
            "continuation_pathways": intelligence.get("causality_graph", {}).get("dominant_pathways", [])[:4],
            "convergence_behavior": intelligence.get("recovery_convergence", {}),
            "operational_timing": intelligence.get("operational_time_intelligence", {}),
            "benchmark_overlay": benchmark.get("cognition_quality_metrics", {}),
        }
