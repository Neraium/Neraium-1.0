from __future__ import annotations

from typing import Any


class RecoveryConvergenceEngine:
    def model(
        self,
        *,
        facility_cognition: dict[str, Any],
        causality_graph: dict[str, Any],
        memory_retrieval: dict[str, Any],
        persistence: dict[str, Any],
    ) -> dict[str, Any]:
        subsystem_pressure = facility_cognition.get("subsystem_pressure", {}).get("subsystems", {})
        pressure_values = list(subsystem_pressure.values()) or [0.35]
        spread = max(pressure_values) - min(pressure_values)
        persistent_count = len(persistence.get("persistent_columns", []))
        pathway_count = len(causality_graph.get("dominant_pathways", []))
        memory = memory_retrieval.get("memory_matches", [])
        recovery_anchor = next(
            (item for item in memory if "recovery" in str(item.get("label", "")).lower()),
            memory[0] if memory else None,
        )
        convergence_quality = max(0.0, min(1.0, (1.0 - spread) * 0.5 + max(0, 2 - persistent_count) * 0.12 + max(0, 3 - pathway_count) * 0.08))
        return {
            "convergence_quality": quality_label(convergence_quality),
            "stabilization_progression": progression_label(convergence_quality, persistent_count),
            "subsystem_recovery_consistency": consistency_label(spread),
            "recovery_pathways": build_recovery_pathways(causality_graph),
            "convergence_timing": convergence_timing(convergence_quality, persistent_count),
            "reference_memory": recovery_anchor.get("label") if isinstance(recovery_anchor, dict) else "No recovery memory anchor available",
            "convergence_index": round(convergence_quality, 4),
        }


def quality_label(score: float) -> str:
    if score >= 0.72:
        return "HIGH_CONVERGENCE"
    if score >= 0.5:
        return "MODERATE_CONVERGENCE"
    return "LOW_CONVERGENCE"


def progression_label(score: float, persistent_count: int) -> str:
    if score >= 0.72:
        return "stabilization_progressing"
    if persistent_count > 1:
        return "stabilization_delayed_by_persistence"
    return "stabilization_emerging"


def consistency_label(spread: float) -> str:
    if spread <= 0.2:
        return "CONSISTENT_RECOVERY"
    if spread <= 0.4:
        return "PARTIAL_RECOVERY_CONSISTENCY"
    return "RECOVERY_DIVERGENT"


def build_recovery_pathways(causality_graph: dict[str, Any]) -> list[str]:
    pathways = causality_graph.get("dominant_pathways", [])
    if not pathways:
        return ["Recovery pathway still forming"]
    return [f"decay:{path}" for path in pathways[:3]]


def convergence_timing(score: float, persistent_count: int) -> str:
    if score >= 0.72:
        return "2-4 operational windows"
    if score >= 0.5:
        return "4-7 operational windows"
    if persistent_count > 1:
        return "7+ operational windows"
    return "5-8 operational windows"

