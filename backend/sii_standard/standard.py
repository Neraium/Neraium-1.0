from __future__ import annotations

from typing import Any


def build_sii_standard() -> dict[str, Any]:
    return {
        "terminology_registry": [
            "topology drift",
            "propagation pathway",
            "continuation window",
            "subsystem fragmentation",
            "structural compression",
            "archetype emergence",
            "operational timing",
            "topology coherence",
        ],
        "cognition_validation_standards": [
            "earliest divergence visibility",
            "propagation lead-time visibility",
            "fragmentation timing defensibility",
            "replay continuity integrity",
        ],
        "evidence_lineage_specifications": [
            "lineage must include signal, topology, propagation, and historical reference dimensions",
            "lineage must be replay-linked",
        ],
        "replay_integrity_standards": [
            "canonical phase continuity",
            "timestamp reconstruction consistency",
            "frame-level explainability",
        ],
        "topology_cognition_standards": [
            "topology state evolution tracking",
            "subsystem corroboration traceability",
        ],
        "operational_timing_standards": [
            "continuation windows as ranges",
            "convergence timing as ordinal operational windows",
        ],
    }

