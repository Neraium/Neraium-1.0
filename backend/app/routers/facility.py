from typing import Any

from fastapi import APIRouter
from app.services.sii_intelligence import build_intelligence_status, build_sample_intelligence

router = APIRouter(tags=["facility"])


@router.get("/facility/systems")
def read_facility_systems() -> dict[str, Any]:
    intelligence = build_sample_intelligence()
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
    return build_intelligence_status(build_sample_intelligence())
