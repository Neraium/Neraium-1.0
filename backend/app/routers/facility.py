from fastapi import APIRouter

router = APIRouter(tags=["facility"])


@router.get("/facility/systems")
def read_facility_systems() -> dict[str, list[dict[str, str]]]:
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
        ]
    }
