from __future__ import annotations

from typing import Any


class OperationalTimeEngine:
    def model(
        self,
        *,
        causality_graph: dict[str, Any],
        compression: dict[str, Any],
        recovery: dict[str, Any],
        counterfactuals: dict[str, Any],
        persistence: dict[str, Any],
    ) -> dict[str, Any]:
        persistent_count = len(persistence.get("persistent_columns", []))
        pathway_count = len(causality_graph.get("dominant_pathways", []))
        compression_level = compression.get("compression_intensity", "LOW_COMPRESSION")
        recovery_level = recovery.get("convergence_quality", "LOW_CONVERGENCE")
        acceleration_window = counterfactuals.get("uncertainty_ranges", {}).get("instability_acceleration_window_days", [7, 14])
        low, high = parse_window(acceleration_window)
        phase = progression_phase(compression_level, recovery_level, pathway_count)
        return {
            "timing_windows": {
                "propagation_persistence_duration": f"{max(1, low - 1)}-{max(low, high - 2)} operational days",
                "convergence_delay": recovery.get("convergence_timing", "5-8 operational windows"),
                "fragmentation_window": f"{low}-{high} operational days",
                "continuation_acceleration_window": f"{low}-{high} operational days",
                "recovery_stabilization_timing": recovery.get("convergence_timing", "5-8 operational windows"),
            },
            "operational_progression_phase": phase,
            "persistence_duration": persistence_duration_label(persistent_count),
            "convergence_timing": recovery.get("convergence_timing", "5-8 operational windows"),
            "structural_progression_intervals": {
                "phase_1": "stable topology",
                "phase_2": "relationship weakening",
                "phase_3": "pressure migration",
                "phase_4": "archetype emergence",
                "phase_5": "propagation activation",
                "phase_6": "structural fragmentation",
                "phase_7": "continuation pathways",
                "phase_8": "recovery or escalation",
            },
        }


def parse_window(value: list[int] | tuple[int, int] | Any) -> tuple[int, int]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            low = int(value[0])
            high = int(value[1])
            return min(low, high), max(low, high)
        except (TypeError, ValueError):
            return 7, 14
    return 7, 14


def progression_phase(compression_level: str, recovery_level: str, pathway_count: int) -> str:
    if recovery_level == "HIGH_CONVERGENCE":
        return "recovery_convergence"
    if compression_level == "HIGH_COMPRESSION" or pathway_count >= 3:
        return "propagation_acceleration"
    if compression_level == "MODERATE_COMPRESSION":
        return "relationship_weakening"
    return "stable_topology"


def persistence_duration_label(count: int) -> str:
    if count >= 3:
        return "extended_persistence"
    if count >= 1:
        return "moderate_persistence"
    return "limited_persistence"

