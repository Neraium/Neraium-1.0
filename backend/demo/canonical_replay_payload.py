from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def build_canonical_demo_replay_payload(intervals: int = 24) -> dict[str, Any]:
    base = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    phases = [
        ("stable_topology", "LOW_EVIDENCE", "Stable"),
        ("relationship_weakening", "MODERATE_EVIDENCE", "Watch"),
        ("pressure_migration", "MODERATE_EVIDENCE", "Watch"),
        ("compensation_masking", "HIGH_EVIDENCE", "Deteriorating"),
        ("propagation_activation", "HIGH_EVIDENCE", "Deteriorating"),
        ("subsystem_fragmentation", "HIGH_EVIDENCE", "Fragmenting"),
        ("continuation_pathway", "STRONG_CONVERGENCE", "Recovering"),
        ("recovery_or_escalation", "STRONG_CONVERGENCE", "Recovering"),
    ]
    frames: list[dict[str, Any]] = []
    for idx in range(max(intervals, len(phases))):
        phase, confidence, stability = phases[min(len(phases) - 1, int(idx / max(1, intervals / len(phases))))]
        ts = base + timedelta(hours=idx * 4)
        frames.append(
            {
                "timestamp": ts.isoformat(),
                "topology_state": {
                    "phase": phase,
                    "drift_index": round(min(0.95, idx * 0.04), 3),
                    "stability_state": stability,
                    "fragmentation_indicator": "emerging" if idx >= intervals // 2 else "limited",
                },
                "subsystem_pressure": {
                    "pressure_score": round(min(0.98, 0.2 + idx * 0.03), 3),
                    "volatility_index": round(min(0.9, 0.15 + idx * 0.025), 3),
                    "compression_intensity": "elevating" if idx > intervals // 3 else "limited",
                },
                "active_archetypes": [
                    {"name": "COMPENSATION_MASKING", "evidence_strength": confidence},
                    {"name": "PROPAGATION_ACCELERATION", "evidence_strength": confidence},
                ],
                "propagation_state": {
                    "dominant_paths": [
                        "airflow imbalance -> thermal lag",
                        "thermal lag -> humidity compensation",
                        "humidity compensation -> VPD instability",
                    ],
                    "activation_intensity": round(min(0.95, 0.12 + idx * 0.03), 3),
                    "propagation_acceleration": "elevating" if idx > intervals // 2 else "developing",
                    "recovery_convergence": "emerging" if idx > (intervals * 3) // 4 else "limited",
                },
                "evidence_state": {
                    "lineage_events": [
                        {
                            "target": "propagation pathway",
                            "evidence_sources": {
                                "supporting_signals": ["airflow_variance", "thermal_response_lag"],
                                "persistence_evidence": ["multi-window persistence"],
                                "topology_evidence": ["cross-subsystem decoupling"],
                                "propagation_evidence": ["directional pathway confirmation"],
                                "historical_memory_references": ["fingerprint:gh-dehum-01"],
                                "subsystem_corroboration": ["HVAC", "Dehumidification", "Airflow"],
                                "replay_support": ["frame_linked progression"],
                            },
                            "confidence_factors": {
                                "confidence_tier": confidence,
                                "corroboration_strength": "strong",
                                "evidence_density": "high",
                            },
                        }
                    ]
                },
                "memory_similarity": [
                    {
                        "fingerprint_id": "gh-dehum-01",
                        "label": "Greenhouse Dehumidification Compensation Progression",
                        "similarity_score": 0.78,
                        "confidence_band": confidence,
                        "archetypes": ["COMPENSATION_MASKING", "PROPAGATION_ACCELERATION"],
                    }
                ],
                "continuation_window": {
                    "window": "7-12 operational days",
                    "timing_window": "near-term continuation",
                },
                "cognition_state": {
                    "canonical_phase": phase,
                    "operational_phase": phase,
                    "confidence_tier": confidence,
                    "facility_state": stability,
                },
            }
        )
    return {
        "meta": {
            "frame_count": len(frames),
            "intervals": intervals,
            "replay_compression": 1,
            "canonical_flow": [p[0] for p in phases],
        },
        "timeline": frames,
        "source": "demo",
        "facility_state": "Demo",
    }

