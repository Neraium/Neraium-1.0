from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CognitionValidationReport:
    structural_visibility_timing: dict[str, Any]
    evidence_integrity: str
    replay_consistency: str
    propagation_coherence: str
    subsystem_agreement: str
    cognition_continuity_score: str
    topology_coherence_tracking: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CognitionValidationFramework:
    def validate(
        self,
        *,
        intelligence: dict[str, Any],
        replay_timeline: list[dict[str, Any]],
        evidence_lineage: dict[str, Any],
    ) -> dict[str, Any]:
        first_divergence = locate(replay_timeline, "topology_state", "drift_index", 0.32)
        first_propagation = locate(replay_timeline, "propagation_state", "activation_intensity", 0.45)
        first_fragmentation = locate(replay_timeline, "topology_state", "fragmentation_indicator", 0.6)
        lead_time = None
        if first_divergence is not None and first_propagation is not None:
            lead_time = max(first_propagation - first_divergence, 0)
        propagation_paths = intelligence.get("causality_graph", {}).get("dominant_pathways", [])
        subsystem_count = len(intelligence.get("facility_cognition", {}).get("subsystem_pressure", {}).get("subsystems", {}))
        lineage_count = len(evidence_lineage.get("lineages", []))
        report = CognitionValidationReport(
            structural_visibility_timing={
                "first_topology_divergence_frame": first_divergence,
                "first_propagation_visibility_frame": first_propagation,
                "propagation_visibility_lead_time_frames": lead_time,
                "fragmentation_detection_frame": first_fragmentation,
                "archetype_emergence_frame": locate_archetype_frame(replay_timeline),
            },
            evidence_integrity=level(lineage_count, high=4, moderate=2),
            replay_consistency=replay_consistency(replay_timeline),
            propagation_coherence=level(len(propagation_paths), high=3, moderate=1),
            subsystem_agreement=level(subsystem_count, high=4, moderate=2),
            cognition_continuity_score=continuity(replay_timeline),
            topology_coherence_tracking=topology_tracking(replay_timeline),
        )
        return {
            "validation_report": report.to_dict(),
            "methodology": {
                "validated_dimensions": [
                    "topology divergence visibility",
                    "propagation visibility lead time",
                    "fragmentation detection timing",
                    "replay fidelity",
                    "evidence consistency",
                    "continuation pathway coherence",
                    "convergence tracking quality",
                    "archetype emergence timing",
                ],
                "excluded_metrics": [
                    "prediction accuracy",
                    "remaining useful life",
                    "anomaly classification",
                ],
            },
        }


def locate(timeline: list[dict[str, Any]], section: str, field: str, threshold: float) -> int | None:
    for index, frame in enumerate(timeline):
        value = float(frame.get(section, {}).get(field, 0.0))
        if value >= threshold:
            return index
    return None


def locate_archetype_frame(timeline: list[dict[str, Any]]) -> int | None:
    for index, frame in enumerate(timeline):
        if len(frame.get("active_archetypes", [])) >= 2:
            return index
    return None


def level(value: int, *, high: int, moderate: int) -> str:
    if value >= high:
        return "HIGH"
    if value >= moderate:
        return "MODERATE"
    return "LOW"


def replay_consistency(timeline: list[dict[str, Any]]) -> str:
    phases = [frame.get("cognition_state", {}).get("canonical_phase") for frame in timeline]
    unique = len({phase for phase in phases if phase})
    if unique >= 6:
        return "HIGH"
    if unique >= 4:
        return "MODERATE"
    return "LOW"


def continuity(timeline: list[dict[str, Any]]) -> str:
    confidence = [frame.get("cognition_state", {}).get("confidence_tier") for frame in timeline]
    shifts = sum(1 for idx in range(1, len(confidence)) if confidence[idx] != confidence[idx - 1])
    if shifts <= 4:
        return "STABLE_CONTINUITY"
    if shifts <= 8:
        return "MODERATE_CONTINUITY"
    return "LOW_CONTINUITY"


def topology_tracking(timeline: list[dict[str, Any]]) -> str:
    indicators = [float(frame.get("topology_state", {}).get("drift_index", 0.0)) for frame in timeline]
    if not indicators:
        return "UNAVAILABLE"
    ascending = sum(1 for idx in range(1, len(indicators)) if indicators[idx] >= indicators[idx - 1])
    ratio = ascending / max(len(indicators) - 1, 1)
    if ratio >= 0.75:
        return "COHERENT_TRACKING"
    if ratio >= 0.5:
        return "PARTIAL_TRACKING"
    return "INCONSISTENT_TRACKING"

