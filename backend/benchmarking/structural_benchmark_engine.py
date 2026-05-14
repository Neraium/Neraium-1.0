from __future__ import annotations

from typing import Any


class StructuralBenchmarkEngine:
    def benchmark(self, *, intelligence: dict[str, Any], replay_timeline: list[dict[str, Any]]) -> dict[str, Any]:
        frame_count = len(replay_timeline)
        first_fragment_frame = next(
            (index for index, frame in enumerate(replay_timeline) if float(frame.get("topology_state", {}).get("fragmentation_indicator", 0.0)) >= 0.65),
            None,
        )
        first_prop_frame = next(
            (index for index, frame in enumerate(replay_timeline) if float(frame.get("propagation_state", {}).get("activation_intensity", 0.0)) >= 0.55),
            None,
        )
        lead_time = None
        if first_fragment_frame is not None and first_prop_frame is not None:
            lead_time = max(first_fragment_frame - first_prop_frame, 0)
        lineage = intelligence.get("evidence_lineage", {}).get("lineages", [])
        consistency = "high" if len(lineage) >= 3 else "moderate" if len(lineage) >= 1 else "limited"
        return {
            "cognition_quality_metrics": {
                "earliest_structural_divergence_visibility": visibility_label(first_prop_frame),
                "propagation_visibility_lead_time_frames": lead_time,
                "subsystem_fragmentation_timing_frame": first_fragment_frame,
                "replay_fidelity": replay_fidelity(frame_count),
                "evidence_consistency": consistency,
                "topology_evolution_quality": topology_quality(replay_timeline),
                "archetype_emergence_timing": archetype_timing(replay_timeline),
                "continuation_coherence": continuation_coherence(replay_timeline),
                "recovery_convergence_tracking": recovery_tracking(replay_timeline),
            },
            "replay_integrity": "coherent" if frame_count >= 12 else "developing",
            "evidence_consistency": consistency,
            "structural_visibility_timing": {
                "propagation_activation_frame": first_prop_frame,
                "fragmentation_frame": first_fragment_frame,
            },
        }


def visibility_label(index: int | None) -> str:
    if index is None:
        return "not_observed"
    if index <= 3:
        return "early"
    if index <= 7:
        return "moderate"
    return "late"


def replay_fidelity(frame_count: int) -> str:
    if frame_count >= 24:
        return "high"
    if frame_count >= 12:
        return "moderate"
    return "limited"


def topology_quality(timeline: list[dict[str, Any]]) -> str:
    indicators = [float(frame.get("topology_state", {}).get("drift_index", 0.0)) for frame in timeline]
    if not indicators:
        return "limited"
    monotonic = sum(1 for i in range(1, len(indicators)) if indicators[i] >= indicators[i - 1])
    ratio = monotonic / max(len(indicators) - 1, 1)
    if ratio >= 0.7:
        return "high"
    if ratio >= 0.5:
        return "moderate"
    return "low"


def archetype_timing(timeline: list[dict[str, Any]]) -> str:
    emergence = next((index for index, frame in enumerate(timeline) if len(frame.get("active_archetypes", [])) >= 2), None)
    return visibility_label(emergence)


def continuation_coherence(timeline: list[dict[str, Any]]) -> str:
    windows = [frame.get("continuation_window", {}).get("window") for frame in timeline if frame.get("continuation_window", {}).get("window")]
    unique = len(set(windows))
    if unique <= 2:
        return "high"
    if unique <= 4:
        return "moderate"
    return "low"


def recovery_tracking(timeline: list[dict[str, Any]]) -> str:
    states = [frame.get("cognition_state", {}).get("operational_phase") for frame in timeline]
    if "recovery_convergence" in states:
        return "tracked"
    return "developing"

