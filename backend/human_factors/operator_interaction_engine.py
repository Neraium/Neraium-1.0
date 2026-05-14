from __future__ import annotations

from typing import Any


class OperatorInteractionEngine:
    def analyze(self, *, interventions: list[dict[str, Any]], intelligence: dict[str, Any]) -> dict[str, Any]:
        if not interventions:
            return {
                "operational_adaptation_patterns": ["intervention history limited"],
                "intervention_effectiveness_trends": "insufficient_evidence",
                "convergence_influence": "unknown",
                "recovery_interaction_behavior": "not_enough_history",
            }
        avg_latency = sum(float(item.get("response_minutes", 0.0)) for item in interventions) / len(interventions)
        effectiveness = [float(item.get("effectiveness", 0.0)) for item in interventions]
        mean_effectiveness = sum(effectiveness) / len(effectiveness)
        suppression = sum(1 for item in interventions if item.get("propagation_suppressed"))
        return {
            "operational_adaptation_patterns": pattern_labels(avg_latency, suppression, len(interventions)),
            "intervention_effectiveness_trends": trend_label(mean_effectiveness),
            "convergence_influence": convergence_influence(mean_effectiveness, intelligence),
            "recovery_interaction_behavior": recovery_behavior(avg_latency, mean_effectiveness),
            "interaction_summary": {
                "intervention_timing_minutes": round(avg_latency, 2),
                "suppression_events": suppression,
                "intervention_count": len(interventions),
            },
        }


def pattern_labels(avg_latency: float, suppression: int, total: int) -> list[str]:
    patterns = []
    if avg_latency <= 30:
        patterns.append("early_intervention_pattern")
    elif avg_latency <= 90:
        patterns.append("moderate_intervention_pattern")
    else:
        patterns.append("delayed_intervention_pattern")
    if suppression >= max(1, total // 2):
        patterns.append("propagation_suppression_pattern")
    return patterns


def trend_label(effectiveness: float) -> str:
    if effectiveness >= 0.7:
        return "improving"
    if effectiveness >= 0.45:
        return "mixed"
    return "limited"


def convergence_influence(effectiveness: float, intelligence: dict[str, Any]) -> str:
    convergence = str(intelligence.get("recovery_convergence", {}).get("convergence_quality", "LOW_CONVERGENCE"))
    if effectiveness >= 0.7 and "HIGH" in convergence:
        return "strong_positive_influence"
    if effectiveness >= 0.45:
        return "moderate_influence"
    return "low_influence"


def recovery_behavior(latency: float, effectiveness: float) -> str:
    if latency <= 45 and effectiveness >= 0.65:
        return "accelerated_recovery_interaction"
    if effectiveness >= 0.45:
        return "partial_recovery_support"
    return "recovery_support_limited"

