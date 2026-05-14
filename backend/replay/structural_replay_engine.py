from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class ReplayFrame:
    timestamp: str
    topology_state: dict[str, Any]
    subsystem_pressure: dict[str, Any]
    active_archetypes: list[dict[str, Any]]
    propagation_state: dict[str, Any]
    evidence_state: dict[str, Any]
    cognition_state: dict[str, Any]
    memory_similarity: list[dict[str, Any]]
    continuation_window: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "topology_state": self.topology_state,
            "subsystem_pressure": self.subsystem_pressure,
            "active_archetypes": self.active_archetypes,
            "propagation_state": self.propagation_state,
            "evidence_state": self.evidence_state,
            "cognition_state": self.cognition_state,
            "memory_similarity": self.memory_similarity,
            "continuation_window": self.continuation_window,
        }


class StructuralReplayEngine:
    def build_timeline(
        self,
        *,
        intelligence: dict[str, Any],
        intervals: int = 16,
        replay_compression: int = 1,
    ) -> dict[str, Any]:
        safe_intervals = max(6, min(intervals, 80))
        compression = max(1, replay_compression)
        frames = self._frames_from_intelligence(
            intelligence=intelligence,
            intervals=safe_intervals,
            replay_compression=compression,
        )
        return {
            "meta": {
                "frame_count": len(frames),
                "intervals": safe_intervals,
                "replay_compression": compression,
                "playback_speeds": [0.5, 1.0, 1.5, 2.0, 4.0],
                "supported_intervals": ["30s", "1m", "5m", "15m", "1h"],
                "canonical_flow": canonical_flow(),
            },
            "timeline": [frame.to_dict() for frame in frames],
        }

    def frame_at_timestamp(
        self,
        *,
        intelligence: dict[str, Any],
        timestamp: str,
        intervals: int = 24,
    ) -> dict[str, Any]:
        frames = self._frames_from_intelligence(intelligence=intelligence, intervals=intervals, replay_compression=1)
        if not frames:
            raise ValueError("No replay frames available.")
        match = min(frames, key=lambda item: abs(parse_ts(item.timestamp) - parse_ts(timestamp)))
        return match.to_dict()

    def frame_range(
        self,
        *,
        intelligence: dict[str, Any],
        start_timestamp: str,
        end_timestamp: str,
        intervals: int = 24,
    ) -> dict[str, Any]:
        frames = self._frames_from_intelligence(intelligence=intelligence, intervals=intervals, replay_compression=1)
        start = parse_ts(start_timestamp)
        end = parse_ts(end_timestamp)
        if end < start:
            start, end = end, start
        selected = [frame for frame in frames if start <= parse_ts(frame.timestamp) <= end]
        return {
            "start_timestamp": ts_iso(start),
            "end_timestamp": ts_iso(end),
            "frame_count": len(selected),
            "frames": [frame.to_dict() for frame in selected],
        }

    def _frames_from_intelligence(
        self,
        *,
        intelligence: dict[str, Any],
        intervals: int,
        replay_compression: int,
    ) -> list[ReplayFrame]:
        archetypes = intelligence.get("active_archetypes", [])
        causality = intelligence.get("causality_graph", {})
        facility = intelligence.get("facility_cognition", {})
        memory = intelligence.get("structural_memory", {})
        counterfactuals = intelligence.get("counterfactuals", {})
        confidence = intelligence.get("cognition_confidence", {})
        lineage = intelligence.get("evidence_lineage", {})
        stability = intelligence.get("structural_stability_index", {})
        recovery = intelligence.get("recovery_convergence", {})
        compression = intelligence.get("structural_compression", {})
        time_intel = intelligence.get("operational_time_intelligence", {})
        base_time = parse_dt(intelligence.get("last_updated"))
        pressure = facility.get("subsystem_pressure", {})
        pressure_score = float(pressure.get("pressure_score", 0.22))
        volatility = float(pressure.get("volatility_index", 0.18))
        dominant_paths = causality.get("dominant_pathways", [])
        memory_matches = memory.get("memory_matches", [])
        progression = counterfactuals.get("progression_scenarios", [])
        evidence_lineage = lineage.get("lineages", [])
        frames: list[ReplayFrame] = []
        for index in range(intervals):
            t = index / max(intervals - 1, 1)
            ts = base_time - timedelta(minutes=(intervals - index) * replay_compression * 4)
            phase = phase_for_t(t)
            frame_pressure = round(min(max(pressure_score * (0.6 + t * 0.7), 0.0), 1.0), 4)
            frame_volatility = round(min(max(volatility * (0.5 + t * 0.9), 0.0), 1.0), 4)
            active_slice = max(1, min(len(archetypes), int(round((t * len(archetypes)) + 0.2)))) if archetypes else 0
            frames.append(
                ReplayFrame(
                    timestamp=ts.isoformat(),
                    topology_state={
                        "phase": phase,
                        "drift_index": round(min(0.12 + (t * 0.88), 1.0), 4),
                        "fragmentation_indicator": round(
                            min(frame_pressure * 0.92 + (0.08 if phase in {"structural_fragmentation", "continuation_pathways"} else 0.0), 1.0),
                            4,
                        ),
                        "stability_state": stability.get("state", "WATCH"),
                    },
                    subsystem_pressure={
                        "pressure_score": frame_pressure,
                        "volatility_index": frame_volatility,
                        "subsystems": pressure.get("subsystems", {}),
                        "compression_intensity": compression.get("compression_intensity", "LOW_COMPRESSION"),
                    },
                    active_archetypes=archetypes[:active_slice],
                    propagation_state={
                        "dominant_paths": dominant_paths[: max(1, min(len(dominant_paths), 1 + int(t * 3)))],
                        "activation_intensity": round(min(0.18 + (t * 0.82), 1.0), 4),
                        "propagation_acceleration": round(min(0.1 + t * 0.9, 1.0), 4),
                        "recovery_convergence": recovery.get("convergence_quality", "LOW_CONVERGENCE"),
                    },
                    evidence_state={
                        "corroboration_strength": confidence.get("corroboration_strength", "MODERATE"),
                        "lineage_events": evidence_lineage[: max(1, min(len(evidence_lineage), 1 + int(t * 2)))],
                    },
                    cognition_state={
                        "facility_state": facility.get("facility_cognition_state", intelligence.get("facility_state", "Monitoring")),
                        "confidence_tier": confidence.get("confidence_tier", "MODERATE_EVIDENCE"),
                        "state_evolution": f"frame_{index + 1}_of_{intervals}",
                        "canonical_phase": phase,
                        "operational_phase": time_intel.get("operational_progression_phase", "stable_topology"),
                    },
                    memory_similarity=memory_matches[: max(1, min(len(memory_matches), 1 + int(t * 2)))],
                    continuation_window={
                        "active_scenario": progression[0]["name"] if progression else "Continuation tracking",
                        "window": progression[0]["window"] if progression else intelligence.get("intervention_window", "Monitoring"),
                        "timing_window": time_intel.get("timing_windows", {}).get("continuation_acceleration_window", "n/a"),
                    },
                )
            )
        return frames


def parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        normalized = value.strip().replace(" ", "+").replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(UTC)
    except ValueError:
        return datetime.now(UTC)


def parse_ts(value: str) -> float:
    return parse_dt(value).timestamp()


def ts_iso(value: float) -> str:
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def canonical_flow() -> list[str]:
    return [
        "stable_topology",
        "relationship_weakening",
        "pressure_migration",
        "archetype_emergence",
        "propagation_activation",
        "structural_fragmentation",
        "continuation_pathways",
        "recovery_or_escalation",
    ]


def phase_for_t(t: float) -> str:
    phases = canonical_flow()
    idx = min(len(phases) - 1, int(t * len(phases)))
    return phases[idx]
