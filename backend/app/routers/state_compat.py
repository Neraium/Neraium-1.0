from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["facility"])


@router.get("/facility/cognition-state")
@router.get("/facility/cognition-state/")
def facility_state_compat(mode: str = "live") -> dict[str, Any]:
    return {
        "cognition_state": "Drift observed",
        "structural_stability": "WATCH",
        "active_archetypes": ["COMPENSATION_MASKING", "THERMAL_LAG_PROPAGATION"],
        "propagation_pathways": ["humidity_control_to_thermal_response"],
        "evidence_lineage": {
            "integrity": "MODERATE",
            "sources": ["sample_cultivation_cognition"],
        },
        "structural_memory_matches": [],
        "continuation_windows": {
            "window": "Monitoring",
            "structural_pathways": [],
        },
        "replay_summary": {
            "frame_count": 0,
            "canonical_flow": [],
        },
        "recovery_convergence": {},
        "operator_explanation": "Sample structural cognition payload available for operator review.",
        "source_mode": mode,
        "source": "compatibility_endpoint",
    }
