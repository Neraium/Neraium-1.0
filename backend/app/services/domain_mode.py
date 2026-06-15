from __future__ import annotations

from typing import Any

from app.services.aquatic_domain import INTEGRATION_STUBS as AQUATIC_INTEGRATION_STUBS
from app.services.upload_state_repository import read_current_upload_result

DEFAULT_DOMAIN_MODE = "cultivation" 
SUPPORTED_DOMAIN_MODES = {"aquatic", "cultivation"}

AQUATIC_HINTS = (
    "orp",
    "chlorine",
    "ph",
    "pool",
    "spa",
    "sanitizer",
    "filter",
    "pump",
    "valve",
    "water_level",
    "heater",
    "circulation",
    "pressure",
)

CULTIVATION_HINTS = (
    "hvac",
    "humidity",
    "dehumid",
    "airflow",
    "irrigation",
    "lighting",
    "co2",
    "vpd",
    "flower",
    "veg",
    "mother",
    "clone",
    "grow",
    "canopy",
    "exhaust",
    "fan",
)


def normalize_domain_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in SUPPORTED_DOMAIN_MODES:
        return normalized
    return DEFAULT_DOMAIN_MODE


def read_domain_mode() -> str:
    return detect_domain_mode()["mode"]


def detect_domain_mode() -> dict[str, Any]:
    latest_result = read_current_upload_result()
    if not isinstance(latest_result, dict):
        return {
            "mode": DEFAULT_DOMAIN_MODE,
            "source": "unclassified",
            "confidence": 0.0,
            "evidence": [],
        }

    columns = _domain_detection_inputs(latest_result)
    aquatic_score, aquatic_evidence = _score_domain(columns, AQUATIC_HINTS, latest_result.get("aquatic_schema"))
    cultivation_score, cultivation_evidence = _score_domain(columns, CULTIVATION_HINTS)

    if aquatic_score == 0 and cultivation_score == 0:
        return {
            "mode": DEFAULT_DOMAIN_MODE,
            "source": "unclassified",
            "confidence": 0.0,
            "evidence": [],
        }

    if aquatic_score > cultivation_score:
        mode = "aquatic"
        score = aquatic_score
        runner_up = cultivation_score
        evidence = aquatic_evidence
    elif cultivation_score > aquatic_score:
        mode = "cultivation"
        score = cultivation_score
        runner_up = aquatic_score
        evidence = cultivation_evidence
    else:
        mode = DEFAULT_DOMAIN_MODE
        score = cultivation_score
        runner_up = aquatic_score
        evidence = cultivation_evidence if mode == "cultivation" else aquatic_evidence

    confidence = _confidence_from_scores(score, runner_up)
    return {
        "mode": mode,
        "source": "upload_shape",
        "confidence": confidence,
        "evidence": evidence,
    }


def _domain_detection_inputs(latest_result: dict[str, Any]) -> list[str]:
    columns = [str(column) for column in latest_result.get("columns", []) if str(column).strip()]
    room_summary = latest_result.get("room_summary")
    if isinstance(room_summary, dict):
        rooms = room_summary.get("rooms")
        if isinstance(rooms, list):
            for room in rooms:
                if isinstance(room, dict):
                    room_name = room.get("room")
                    if room_name:
                        columns.append(str(room_name))
    return columns


def _score_domain(items: list[str], hints: tuple[str, ...], extra: Any = None) -> tuple[int, list[str]]:
    evidence: list[str] = []
    lowered_items = [str(item).lower() for item in items]
    for item, lowered in zip(items, lowered_items):
        if any(hint in lowered for hint in hints):
            evidence.append(str(item))

    if isinstance(extra, dict):
        mapped_count = extra.get("mapped_column_count")
        if isinstance(mapped_count, int) and mapped_count > 0:
            evidence.append("aquatic schema")
            evidence.append(f"mapped_columns:{min(mapped_count, 5)}")

    unique_evidence = list(dict.fromkeys(evidence))
    return len(unique_evidence), unique_evidence


def _confidence_from_scores(winner: int, runner_up: int) -> float:
    total = winner + runner_up
    if total <= 0:
        return 0.0
    spread = (winner - runner_up) / total
    return round(0.55 + max(0.0, spread) * 0.4, 3)


def domain_profile(mode: str) -> dict[str, Any]:
    selected = normalize_domain_mode(mode)
    if selected == "cultivation":
        return {
            "mode": "cultivation",
            "app_subtitle": "Environmental drift intelligence for cannabis grow facilities",
            "app_description": "Neraium helps cultivation teams detect persistent relationship instability before operational degradation compounds.",
            "systems": [
                {"name": "HVAC", "scope": "Temperature conditioning and equipment runtime behavior"},
                {"name": "Humidity control", "scope": "Dehumidification, humidification, and moisture balance"},
                {"name": "Airflow", "scope": "Air movement patterns, circulation, and room exchange signals"},
                {"name": "Irrigation", "scope": "Irrigation events, timing, and environmental response context"},
                {"name": "Lighting", "scope": "Lighting schedules and environmental response windows"},
                {"name": "Sensor network", "scope": "Room sensors, facility exports, and historical readings"},
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
            "integration_stubs": [
                {"name": "CSV", "connector_type": "csv", "mode": "active", "read_only": True},
                {"name": "REST ingestion", "connector_type": "rest", "mode": "active", "read_only": True},
                {"name": "MQTT", "connector_type": "mqtt", "mode": "adapter_stub", "read_only": True},
                {"name": "BACnet / BMS", "connector_type": "bacnet", "mode": "adapter_stub", "read_only": True},
                {"name": "OPC UA", "connector_type": "opcua", "mode": "adapter_stub", "read_only": True},
            ],
            "replay_demo_mode": "demo",
        }
    return {
        "mode": "aquatic",
        "app_subtitle": "Operational relationship intelligence for hospitality aquatic infrastructure",
        "app_description": "Neraium helps resort pool and spa operations teams detect and explain persistent relationship instability across telemetry domains.",
        "systems": [
            {"name": "Circulation", "scope": "Hydraulic flow continuity, pump behavior, and pressure response"},
            {"name": "Filtration", "scope": "Filter pressure, flow resistance, and cycle stability"},
            {"name": "Thermal control", "scope": "Pool/spa thermal stability, heater runtime, and heat retention"},
            {"name": "Water chemistry", "scope": "ORP, pH, and sanitizer feed relationship behavior"},
            {"name": "Hydraulic routing", "scope": "Valve state transitions and distribution path consistency"},
            {"name": "Operational context", "scope": "Occupancy load, ambient heat effects, and overnight stabilization"},
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
        "integration_stubs": AQUATIC_INTEGRATION_STUBS,
        "replay_demo_mode": "aquatic_demo",
    }
