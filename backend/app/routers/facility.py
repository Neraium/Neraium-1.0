from typing import Any

from fastapi import APIRouter, Depends
from app.core.security import require_api_access
from api.cognition_contracts import build_canonical_cognition_state_response
from app.services.engine_identity import build_engine_identity
from app.services.sii_intelligence import REQUIRED_INTELLIGENCE_FIELDS, build_empty_intelligence_status, build_intelligence_status
from app.services.sii_intelligence import build_sample_intelligence
from app.services.sii_runner import build_runner_status, read_latest_sii_state
from app.services.upload_jobs import read_latest_upload_result

router = APIRouter(tags=["facility"], dependencies=[Depends(require_api_access)])


@router.get("/facility/systems")
def read_facility_systems() -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = resolve_uploaded_intelligence(latest_result)
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
def read_intelligence_status() -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = resolve_uploaded_intelligence(latest_result)
    return build_intelligence_status(intelligence) if intelligence else build_empty_intelligence_status()


@router.get("/facility/cognition-state")
def read_cognition_state(mode: str = "live") -> dict[str, Any]:
    if mode == "demo":
        intelligence = build_sample_intelligence()
    else:
        latest_result = read_latest_upload_result()
        intelligence = resolve_uploaded_intelligence(latest_result) or build_sample_intelligence()
    response = build_canonical_cognition_state_response(intelligence)
    response["source_mode"] = mode
    return response


def resolve_uploaded_intelligence(latest_result: dict[str, Any] | None) -> dict[str, Any] | None:
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
