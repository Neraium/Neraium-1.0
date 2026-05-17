from typing import Any

from fastapi import APIRouter, Depends, Query
from app.core.security import require_api_access
from api.cognition_contracts import build_canonical_cognition_state_response
from app.services.engine_identity import build_engine_identity
from app.services.sii_intelligence import REQUIRED_INTELLIGENCE_FIELDS, build_empty_intelligence_status, build_intelligence_status
from app.services.sii_runner import build_runner_status, read_latest_sii_state
from app.services.upload_jobs import read_latest_upload_result

router = APIRouter(tags=["facility"], dependencies=[Depends(require_api_access)])


@router.get("/facility/systems")
def read_facility_systems(include_persisted: bool = Query(False)) -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = resolve_uploaded_intelligence(latest_result, include_persisted=include_persisted)
    return {
        "systems": [
            {
                "name": "HVAC",
                "scope": "Temperature conditioning and equipment runtime behavior",
            },
            {
                "name": "Humidity control",
                "scope": "Dehumidification, humidification, and room moisture balance",
            },
            {
                "name": "Airflow",
                "scope": "Air movement patterns, circulation, and room exchange signals",
            },
            {
                "name": "Irrigation",
                "scope": "Irrigation events, timing, and environmental response context",
            },
            {
                "name": "Lighting",
                "scope": "Lighting schedules and environmental response windows",
            },
            {
                "name": "Sensor network",
                "scope": "Room sensors, facility exports, and historical readings",
            },
        ],
        "driver_categories": [
            "humidity_control",
            "hvac_instability",
            "airflow_restriction",
            "irrigation_timing",
            "lighting_schedule",
            "sensor_network",
            "unknown_system_drift",
        ],
        "intelligence": intelligence,
        "intelligence_status": build_intelligence_status(intelligence) if intelligence else build_empty_intelligence_status(),
    }


@router.get("/intelligence/status")
def read_intelligence_status(include_persisted: bool = Query(False)) -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = resolve_uploaded_intelligence(latest_result, include_persisted=include_persisted)
    return build_intelligence_status(intelligence) if intelligence else build_empty_intelligence_status()


@router.get("/facility/cognition-state")
def read_cognition_state(include_persisted: bool = Query(False)) -> dict[str, Any]:
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
