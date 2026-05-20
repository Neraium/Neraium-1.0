from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.aquatic_domain import build_aquatic_replay_dataset


def build_aquatic_demo_replay_payload(intervals: int = 48) -> dict[str, Any]:
    dataset = build_aquatic_replay_dataset(intervals=intervals)
    rows = dataset["rows"]
    timeline: list[dict[str, Any]] = []
    base = datetime.now(UTC) - timedelta(minutes=15 * len(rows))
    for index, row in enumerate(rows):
        state = "Stable"
        if row["flow_rate"] < 500 or row["filter_pressure"] > 19:
            state = "Watch"
        if row["flow_rate"] < 470 and row["filter_pressure"] > 20:
            state = "Admission"
        timeline.append(
            {
                "timestamp": (base + timedelta(minutes=15 * index)).isoformat(),
                "topology_state": {
                    "phase": "relationship_weakening" if state != "Stable" else "stable_topology",
                    "drift_index": round(max(0.05, (20 - row["flow_rate"] / 30) / 10), 3),
                    "stability_state": state,
                    "fragmentation_indicator": "emerging" if state != "Stable" else "limited",
                },
                "subsystem_pressure": {
                    "pressure_score": row["filter_pressure"],
                    "volatility_index": round(abs(row["orp"] - 700) / 120, 3),
                    "compression_intensity": "elevating" if state != "Stable" else "limited",
                },
                "active_archetypes": [
                    {"name": "circulation degradation", "evidence_strength": "moderate" if state == "Watch" else "strong" if state == "Admission" else "low"},
                    {"name": "orp instability", "evidence_strength": "moderate"},
                ],
                "propagation_state": {
                    "dominant_paths": [
                        "occupancy_estimate -> sanitizer_feed_rate -> orp",
                        "pump_amperage -> flow_rate -> filter_pressure",
                    ],
                    "activation_intensity": round(min(0.95, 0.25 + index * 0.01), 3),
                    "propagation_acceleration": "elevating" if state != "Stable" else "contained",
                    "recovery_convergence": "limited" if state == "Admission" else "emerging",
                },
                "cognition_state": {
                    "canonical_phase": "propagation_activation" if state != "Stable" else "stable_topology",
                    "operational_phase": "aquatic_hospitality",
                    "confidence_tier": "RELATIONSHIP_EVIDENCE_PRESENT",
                    "facility_state": state,
                },
                "raw_telemetry": row,
            }
        )
    return {
        "meta": {
            "frame_count": len(timeline),
            "intervals": intervals,
            "replay_compression": 1,
            "canonical_flow": ["stable_topology", "relationship_weakening", "propagation_activation", "recovery_or_escalation"],
            "domain": "commercial_aquatic_hospitality",
        },
        "timeline": timeline,
        "source": "aquatic_demo",
        "facility_state": timeline[-1]["topology_state"]["stability_state"] if timeline else "Stable",
        "dataset": dataset,
    }
