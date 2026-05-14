from __future__ import annotations

from typing import Any


def build_cultivation_pilot_validation_payload(intelligence: dict[str, Any]) -> dict[str, Any]:
    replay = intelligence.get("replay_timeline", {})
    return {
        "weekly_cognition_summary": {
            "cognition_state": intelligence.get("facility_state", "Monitoring"),
            "structural_stability": intelligence.get("structural_stability_index", {}).get("state", "WATCH"),
            "active_archetypes": [item.get("name", "") for item in intelligence.get("active_archetypes", [])],
        },
        "replay_exports": {
            "frame_count": replay.get("meta", {}).get("frame_count", len(replay.get("timeline", []))),
            "canonical_flow": replay.get("meta", {}).get("canonical_flow", []),
        },
        "topology_snapshots": intelligence.get("replay_timeline", {}).get("timeline", [])[-3:],
        "propagation_report": intelligence.get("causality_graph", {}).get("dominant_pathways", []),
        "evidence_summary": [item.get("target", "") for item in intelligence.get("evidence_lineage", {}).get("lineages", [])],
        "convergence_recovery_report": intelligence.get("recovery_convergence", {}),
        "mode": "read_only_pilot_validation",
    }

