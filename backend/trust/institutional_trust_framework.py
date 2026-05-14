from __future__ import annotations

from typing import Any


TRUST_LEVELS = ("OBSERVATIONAL", "CORROBORATED", "STRONG_CONVERGENCE", "HIGH_STRUCTURAL_CONFIDENCE")


class InstitutionalTrustFramework:
    def assess(
        self,
        *,
        intelligence: dict[str, Any],
        validation: dict[str, Any],
        audit: dict[str, Any],
    ) -> dict[str, Any]:
        lineage_count = len(intelligence.get("evidence_lineage", {}).get("lineages", []))
        replay_count = len(audit.get("timeline_reconstruction", []))
        continuity = validation.get("validation_report", {}).get("cognition_continuity_score", "LOW_CONTINUITY")
        topology = validation.get("validation_report", {}).get("topology_coherence_tracking", "INCONSISTENT_TRACKING")
        level = trust_level(lineage_count, replay_count, continuity, topology)
        return {
            "trust_level": level,
            "trust_factors": {
                "evidence_integrity": validation.get("validation_report", {}).get("evidence_integrity"),
                "replay_consistency": validation.get("validation_report", {}).get("replay_consistency"),
                "topology_coherence": topology,
                "cognition_continuity": continuity,
                "subsystem_corroboration": validation.get("validation_report", {}).get("subsystem_agreement"),
                "auditability": "HIGH" if replay_count >= 12 else "MODERATE" if replay_count >= 6 else "LOW",
                "replay_traceability": "HIGH" if replay_count >= 12 else "MODERATE",
                "explanation_consistency": explanation_consistency(intelligence),
            },
        }


def trust_level(lineage_count: int, replay_count: int, continuity: str, topology: str) -> str:
    if lineage_count >= 4 and replay_count >= 16 and continuity == "STABLE_CONTINUITY" and topology == "COHERENT_TRACKING":
        return "HIGH_STRUCTURAL_CONFIDENCE"
    if lineage_count >= 3 and replay_count >= 12:
        return "STRONG_CONVERGENCE"
    if lineage_count >= 2 and replay_count >= 8:
        return "CORROBORATED"
    return "OBSERVATIONAL"


def explanation_consistency(intelligence: dict[str, Any]) -> str:
    summary = intelligence.get("operator_explanation_v2", {}).get("summary", "")
    if len(summary) > 40:
        return "HIGH"
    if len(summary) > 10:
        return "MODERATE"
    return "LOW"

