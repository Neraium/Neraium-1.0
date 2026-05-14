from __future__ import annotations

from typing import Any


class OperatorExplanationEngine:
    def build(
        self,
        *,
        driver_attribution: dict[str, Any],
        archetypes: list[dict[str, Any]],
        causality_graph: dict[str, Any],
        memory_retrieval: dict[str, Any],
        counterfactuals: dict[str, Any],
        facility_cognition: dict[str, Any],
    ) -> dict[str, Any]:
        dominant_archetype = archetypes[0] if archetypes else None
        leading_match = (memory_retrieval.get("memory_matches") or [{}])[0]
        primary_path = (causality_graph.get("dominant_pathways") or ["Structural propagation pathway not isolated"])[0]
        continuation = (counterfactuals.get("progression_scenarios") or [{}])[0]
        summary = build_summary(driver_attribution, dominant_archetype, primary_path, continuation)
        recovery_indicator = recovery_indicator_from(archetypes, memory_retrieval)
        return {
            "summary": summary,
            "active_archetypes": [
                {
                    "name": item.get("name"),
                    "evidence_strength": item.get("evidence_strength"),
                    "confidence_band": item.get("confidence_band"),
                    "supporting_relationships": item.get("supporting_relationships", []),
                }
                for item in archetypes[:3]
            ],
            "propagation_pathways": causality_graph.get("dominant_pathways", [])[:4],
            "structural_memory_matches": memory_retrieval.get("memory_matches", [])[:3],
            "subsystem_causality_summary": [
                edge.get("explanation")
                for edge in causality_graph.get("edges", [])[:3]
                if edge.get("explanation")
            ],
            "counterfactual_continuation_windows": counterfactuals.get("uncertainty_ranges", {}),
            "recovery_convergence_indicators": recovery_indicator,
            "facility_cognition_state": facility_cognition.get("facility_cognition_state"),
            "operator_language": {
                "leading_memory_match": leading_match.get("label"),
                "counterfactual_window": continuation.get("window"),
            },
        }


def build_summary(
    driver_attribution: dict[str, Any],
    dominant_archetype: dict[str, Any] | None,
    primary_path: str,
    continuation: dict[str, Any],
) -> str:
    archetype_phrase = ""
    if dominant_archetype:
        archetype_phrase = (
            f"Observed instability resembles {dominant_archetype['name'].lower().replace('_', ' ')} "
            "progression behavior. "
        )
    driver = driver_attribution.get("likely_driver") or "Current structure"
    return (
        f"{archetype_phrase}Structural pressure is propagating through {primary_path.replace('_', ' ')}. "
        f"{driver} remains the leading upstream contributor under current evidence. "
        f"Current continuation path suggests {continuation.get('summary', 'structural pressure remains active if deterioration persists unchanged.')}"
    )


def recovery_indicator_from(archetypes: list[dict[str, Any]], memory_retrieval: dict[str, Any]) -> list[str]:
    indicators: list[str] = []
    if any(item.get("name") == "RECOVERY_CONVERGENCE" for item in archetypes):
        indicators.append("Recovery convergence remains visible if cross-system pressure does not widen.")
    for match in memory_retrieval.get("memory_matches", [])[:2]:
        for behavior in match.get("recovery_behaviors", [])[:1]:
            indicators.append(behavior)
    return indicators or ["Recovery convergence has not yet become the dominant structural pattern."]
