from typing import Any

from fastapi import APIRouter, Depends
from app.core.security import require_api_access
from app.services.engine_identity import build_engine_identity
from app.services.sii_intelligence import REQUIRED_INTELLIGENCE_FIELDS, build_intelligence_status, build_sample_intelligence
from app.services.sii_runner import build_runner_status, read_latest_sii_state
from app.services.upload_jobs import read_latest_upload_result

router = APIRouter(tags=["facility"], dependencies=[Depends(require_api_access)])


@router.get("/facility/systems")
def read_facility_systems() -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = read_latest_sii_state()
    if intelligence is None and latest_result:
        candidate = latest_result.get("sii_intelligence")
        if is_valid_persisted_intelligence(candidate):
            intelligence = candidate
    intelligence = intelligence or build_sample_intelligence()
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
        "intelligence_status": build_intelligence_status(intelligence),
    }


@router.get("/intelligence/status")
def read_intelligence_status() -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = read_latest_sii_state()
    if intelligence is None and latest_result:
        candidate = latest_result.get("sii_intelligence")
        if is_valid_persisted_intelligence(candidate):
            intelligence = candidate
    return build_intelligence_status(intelligence or build_sample_intelligence())


def is_valid_persisted_intelligence(candidate: Any) -> bool:
    if not isinstance(candidate, dict):
        return False
    if not set(REQUIRED_INTELLIGENCE_FIELDS) <= set(candidate):
        return False
    if candidate.get("source") != "uploaded":
        return False
    return isinstance(candidate.get("rooms"), list)


@router.get("/intelligence/engine-identity")
def read_engine_identity() -> dict[str, Any]:
    return build_engine_identity()


@router.get("/intelligence/runner-status")
def read_runner_status() -> dict[str, Any]:
    return build_runner_status()
