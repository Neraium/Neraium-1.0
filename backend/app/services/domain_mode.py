from __future__ import annotations

from typing import Any

from app.services.aquatic_domain import INTEGRATION_STUBS as AQUATIC_INTEGRATION_STUBS
from app.services.runtime_db import now_iso, read_latest_payload, upsert_latest_payload

DEFAULT_DOMAIN_MODE = "aquatic"
SUPPORTED_DOMAIN_MODES = {"aquatic", "cultivation"}
DOMAIN_MODE_KEY = "neraium_domain_mode"


def normalize_domain_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in SUPPORTED_DOMAIN_MODES:
        return normalized
    return DEFAULT_DOMAIN_MODE


def read_domain_mode() -> str:
    payload = read_latest_payload(DOMAIN_MODE_KEY)
    if isinstance(payload, dict):
        return normalize_domain_mode(payload.get("mode"))
    if isinstance(payload, str):
        return normalize_domain_mode(payload)
    return DEFAULT_DOMAIN_MODE


def write_domain_mode(mode: str, actor: str = "operator") -> dict[str, Any]:
    normalized = normalize_domain_mode(mode)
    payload = {
        "mode": normalized,
        "updated_at": now_iso(),
        "actor": actor,
    }
    upsert_latest_payload(DOMAIN_MODE_KEY, payload)
    return payload


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
