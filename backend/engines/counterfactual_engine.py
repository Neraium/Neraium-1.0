from __future__ import annotations

from typing import Any


class CounterfactualEngine:
    def model(
        self,
        *,
        memory_retrieval: dict[str, Any],
        baseline_analysis: dict[str, Any],
        engine_result: dict[str, Any],
        causality_graph: dict[str, Any],
        urgency: str,
    ) -> dict[str, Any]:
        persistent_count = len(engine_result.get("persistence_assessment", {}).get("persistent_columns", []))
        propagation_score = float(causality_graph.get("propagation_score", 0.0))
        acceleration = abs(float(memory_retrieval.get("active_fingerprint", {}).get("volatility_acceleration", 0.0)))
        base_days = {"unstable": (4, 9), "review": (7, 14), "nominal": (14, 28)}.get(urgency, (8, 16))
        lower = max(1, int(base_days[0] - persistent_count - round(propagation_score * 3)))
        upper = max(lower + 1, int(base_days[1] - persistent_count - round(acceleration * 6)))
        fragmentation_probability = probability_band(propagation_score, persistent_count, acceleration)
        matches = memory_retrieval.get("memory_matches", [])
        leading_match = matches[0]["label"] if matches else "No close progression memory match"
        return {
            "progression_scenarios": [
                {
                    "name": "Continuation without structural relief",
                    "window": f"{lower}-{upper} operational days",
                    "summary": "If the current deterioration path persists, subsystem instability is likely to accelerate within the observed continuation window.",
                    "pathway": causality_graph.get("dominant_pathways", [])[:3],
                },
                {
                    "name": "Topology fragmentation scenario",
                    "window": f"{max(1, lower - 2)}-{max(lower, upper - 1)} operational days",
                    "summary": "Continuation pressure remains concentrated in the current topology and may fragment subsystem coherence rather than produce a single discrete failure.",
                    "pathway": causality_graph.get("dominant_pathways", [])[:2],
                },
            ],
            "uncertainty_ranges": {
                "instability_acceleration_window_days": [lower, upper],
                "structural_fragmentation_probability_band": fragmentation_probability,
            },
            "structural_continuation_pathways": causality_graph.get("dominant_pathways", [])[:4],
            "memory_anchor": leading_match,
        }


def probability_band(propagation_score: float, persistent_count: int, acceleration: float) -> str:
    value = min(max(propagation_score * 0.45 + persistent_count * 0.08 + acceleration * 0.2, 0.12), 0.92)
    lower = max(0.05, round(value - 0.12, 2))
    upper = min(0.98, round(value + 0.12, 2))
    return f"{lower:.2f}-{upper:.2f}"

