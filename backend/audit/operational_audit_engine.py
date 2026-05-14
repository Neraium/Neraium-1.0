from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class OperationalAuditRecord:
    audit_id: str
    created_at: str
    cognition_state: str
    archetypes: list[str]
    propagation_pathways: list[str]
    continuation_window: str
    evidence_lineage: list[dict[str, Any]]
    replay_reference_count: int
    historical_memory_references: list[str]
    topology_evolution_summary: str
    subsystem_corroboration: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OperationalAuditEngine:
    def build_record(self, *, session_id: str, intelligence: dict[str, Any], replay_timeline: list[dict[str, Any]]) -> dict[str, Any]:
        evidence_lineage = intelligence.get("evidence_lineage", {}).get("lineages", [])
        record = OperationalAuditRecord(
            audit_id=f"audit-{session_id}",
            created_at=datetime.now(UTC).isoformat(),
            cognition_state=str(intelligence.get("facility_state", "Monitoring")),
            archetypes=[item.get("name", "") for item in intelligence.get("active_archetypes", [])],
            propagation_pathways=intelligence.get("causality_graph", {}).get("dominant_pathways", []),
            continuation_window=str(intelligence.get("counterfactuals", {}).get("progression_scenarios", [{}])[0].get("window", "Monitoring")),
            evidence_lineage=evidence_lineage,
            replay_reference_count=len(replay_timeline),
            historical_memory_references=[item.get("fingerprint_id", "") for item in intelligence.get("structural_memory", {}).get("memory_matches", [])],
            topology_evolution_summary=topology_summary(replay_timeline),
            subsystem_corroboration=subsystem_corroboration(intelligence),
        )
        return {
            "audit_record": record.to_dict(),
            "timeline_reconstruction": replay_timeline[:24],
            "propagation_history": propagation_history(replay_timeline),
            "continuation_reasoning": continuation_reasoning(intelligence),
        }


def topology_summary(timeline: list[dict[str, Any]]) -> str:
    if not timeline:
        return "no replay references"
    start = float(timeline[0].get("topology_state", {}).get("drift_index", 0.0))
    end = float(timeline[-1].get("topology_state", {}).get("drift_index", 0.0))
    if end > start:
        return "topology drift intensified across replay horizon"
    if end < start:
        return "topology drift relaxed across replay horizon"
    return "topology drift remained stable across replay horizon"


def subsystem_corroboration(intelligence: dict[str, Any]) -> str:
    count = len(intelligence.get("facility_cognition", {}).get("subsystem_pressure", {}).get("subsystems", {}))
    if count >= 4:
        return "high corroboration"
    if count >= 2:
        return "moderate corroboration"
    return "low corroboration"


def propagation_history(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "frame": idx,
            "paths": frame.get("propagation_state", {}).get("dominant_paths", []),
            "activation": frame.get("propagation_state", {}).get("activation_intensity"),
        }
        for idx, frame in enumerate(timeline[:24])
    ]


def continuation_reasoning(intelligence: dict[str, Any]) -> dict[str, Any]:
    return {
        "window": intelligence.get("counterfactuals", {}).get("progression_scenarios", [{}])[0].get("window"),
        "coherence": intelligence.get("counterfactuals", {}).get("uncertainty_ranges", {}),
        "pathways": intelligence.get("counterfactuals", {}).get("structural_continuation_pathways", []),
    }

