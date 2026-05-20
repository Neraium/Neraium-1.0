from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["facility-compatibility"])


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _compatibility_cognition_payload(mode: str = "live") -> dict[str, Any]:
    return {
        "cognition_state": "Drift observed",
        "structural_stability": "WATCH",
        "active_archetypes": ["CIRCULATION_DEGRADATION", "THERMAL_RESPONSE_LAG"],
        "propagation_pathways": ["flow_rate_to_filter_pressure_instability"],
        "evidence_lineage": {
            "integrity": "MODERATE",
            "sources": ["sample_aquatic_cognition"],
            "confidence_basis": "Compatibility payload available while live cognition initializes.",
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
        "degraded_mode": True,
        "last_updated": _now_iso(),
    }


@router.get("/facility/cognition-state")
@router.get("/facility/cognition-state/")
@router.get("/cognition-state")
@router.get("/cognition-state/")
def facility_state_compat(mode: str = "live") -> dict[str, Any]:
    return _compatibility_cognition_payload(mode)


@router.get("/facility/systems")
@router.get("/facility/systems/")
def facility_systems_compat() -> dict[str, Any]:
    cognition = _compatibility_cognition_payload("live")
    return {
        "systems": [
            {"name": "Circulation", "scope": "Hydraulic flow continuity and pump behavior"},
            {"name": "Filtration", "scope": "Filter pressure and resistance behavior"},
            {"name": "Thermal control", "scope": "Pool/spa temperature and heater response"},
            {"name": "Water chemistry", "scope": "ORP, pH, and sanitizer feed behavior"},
            {"name": "Hydraulic routing", "scope": "Valve path transitions and distribution consistency"},
            {"name": "Sensor network", "scope": "Telemetry continuity and agreement checks"},
        ],
        "driver_categories": [
            "circulation_degradation",
            "filter_restriction_buildup",
            "abnormal_thermal_drift",
            "orp_instability",
            "dead_zone_circulation_patterns",
            "sensor_disagreement_anomalies",
        ],
        "intelligence": cognition,
        "intelligence_status": {
            "engine_loaded": True,
            "source": "compatibility_endpoint",
            "last_processed_at": cognition["last_updated"],
            "active_rooms_count": 0,
            "evidence_fields_present": [
                "cognition_state",
                "structural_stability",
                "active_archetypes",
                "propagation_pathways",
                "evidence_lineage",
            ],
            "mode": "degraded",
            "status": "compatibility_fallback",
        },
    }


@router.get("/data/latest-upload")
@router.get("/data/latest-upload/")
def latest_upload_compat() -> dict[str, Any]:
    return {
        "status": "empty",
        "processing_state": "idle",
        "latest_upload": None,
        "latest_result": None,
        "snapshot": {
            "status": "empty",
            "processing_state": "idle",
            "message": "No latest upload is available from compatibility mode.",
            "updated_at": _now_iso(),
        },
        "source": "compatibility_endpoint",
        "degraded_mode": True,
    }
