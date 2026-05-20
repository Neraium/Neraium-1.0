from typing import Any

from fastapi import APIRouter, Depends, Query
from app.core.security import require_api_access
from api.cognition_contracts import build_canonical_cognition_state_response
from app.services.engine_identity import build_engine_identity
from app.services.aquatic_domain import INTEGRATION_STUBS
from app.services.sii_intelligence import REQUIRED_INTELLIGENCE_FIELDS, build_empty_intelligence_status, build_intelligence_status
from app.services.sii_runner import build_runner_status, read_latest_sii_state
from app.services.upload_jobs import read_latest_upload_result

router = APIRouter(tags=["facility"], dependencies=[Depends(require_api_access)])


@router.get("/facility/systems")
def read_facility_systems(include_persisted: bool = Query(True)) -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = resolve_uploaded_intelligence(latest_result, include_persisted=include_persisted)
    adaptive_learning = {}
    if include_persisted and isinstance(latest_result, dict) and isinstance(latest_result.get("adaptive_learning"), dict):
        adaptive_learning = latest_result.get("adaptive_learning", {})
    return {
        "systems": [
            {
                "name": "Circulation",
                "scope": "Hydraulic flow continuity, pump behavior, and pressure response",
            },
            {
                "name": "Filtration",
                "scope": "Filter pressure, flow resistance, and cycle stability",
            },
            {
                "name": "Thermal control",
                "scope": "Pool/spa thermal stability, heater runtime, and heat retention",
            },
            {
                "name": "Water chemistry",
                "scope": "ORP, pH, and sanitizer feed relationship behavior",
            },
            {
                "name": "Hydraulic routing",
                "scope": "Valve state transitions and distribution path consistency",
            },
            {
                "name": "Operational context",
                "scope": "Occupancy load, ambient heat effects, and overnight stabilization",
            },
        ],
        "driver_categories": [
            "circulation_degradation",
            "filter_restriction_buildup",
            "pump_cavitation",
            "abnormal_thermal_drift",
            "heater_efficiency_degradation",
            "orp_instability",
            "chemical_feed_inconsistencies",
            "abnormal_overnight_heat_loss",
            "low_flow_conditions",
            "pressure_instability",
            "dead_zone_circulation_patterns",
            "sensor_disagreement_anomalies",
        ],
        "intelligence": intelligence,
        "adaptive_learning": adaptive_learning,
        "integration_stubs": INTEGRATION_STUBS,
        "intelligence_status": build_intelligence_status(intelligence) if intelligence else build_empty_intelligence_status(),
    }


@router.get("/intelligence/status")
def read_intelligence_status(include_persisted: bool = Query(True)) -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = resolve_uploaded_intelligence(latest_result, include_persisted=include_persisted)
    return build_intelligence_status(intelligence) if intelligence else build_empty_intelligence_status()


@router.get("/facility/cognition-state")
def read_cognition_state(include_persisted: bool = Query(True)) -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = resolve_uploaded_intelligence(latest_result, include_persisted=include_persisted)
    if not intelligence:
        return {
            "cognition_state": "Baseline Pending",
            "structural_stability": "BASELINE_PENDING",
            "active_archetypes": [],
            "propagation_pathways": [],
            "evidence_lineage": {},
            "structural_memory_matches": [],
            "continuation_windows": {"window": "Monitoring", "structural_pathways": [], "uncertainty_range": []},
            "replay_summary": {"frame_count": 0, "canonical_flow": [], "active_frame": {}},
            "recovery_convergence": {},
            "operator_explanation": "No active telemetry session is available yet.",
            "source_mode": "live",
        }
    response = build_canonical_cognition_state_response(intelligence)
    response["source_mode"] = "live"
    return response


def resolve_uploaded_intelligence(latest_result: dict[str, Any] | None, *, include_persisted: bool = False) -> dict[str, Any] | None:
    if not include_persisted:
        return None
    intelligence = read_latest_sii_state()
    if is_valid_persisted_intelligence(intelligence):
        return intelligence
    if latest_result:
        candidate = latest_result.get("sii_intelligence")
        if is_valid_persisted_intelligence(candidate):
            return candidate
    return None


def is_valid_persisted_intelligence(candidate: Any) -> bool:
    if not isinstance(candidate, dict):
        return False
    if not set(REQUIRED_INTELLIGENCE_FIELDS) <= set(candidate):
        return False
    if candidate.get("source") not in {"uploaded", "rest_poll"}:
        return False
    return isinstance(candidate.get("rooms"), list)


@router.get("/intelligence/engine-identity")
def read_engine_identity() -> dict[str, Any]:
    return build_engine_identity()


@router.get("/intelligence/runner-status")
def read_runner_status() -> dict[str, Any]:
    return build_runner_status()
