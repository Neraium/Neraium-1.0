from __future__ import annotations

from typing import Any

from app.services.aquatic_domain import INTEGRATION_STUBS as AQUATIC_INTEGRATION_STUBS
from app.services.upload_state_repository import read_current_upload_result

DEFAULT_DOMAIN_MODE = "aquatic"
SUPPORTED_DOMAIN_MODES = {"aquatic", "cultivation"}

AQUATIC_HINTS = (
    "orp",
    "chlorine",
    "ph",
    "pool",
    "spa",
    "resort",
    "aquatic",
    "sanitizer",
    "treatment",
    "turbidity",
    "conductivity",
    "filter",
    "filtration",
    "pump",
    "valve",
    "water_level",
    "makeup_water",
    "heater",
    "circulation",
    "flow",
    "pressure",
    "chilled_water",
    "chw_",
    "chiller",
    "cooling_tower",
    "tower",
    "basin",
    "blowdown",
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
            evidence.append("water infrastructure schema")
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
        "app_subtitle": "Commercial water systems intelligence",
        "app_description": "Neraium helps water infrastructure teams understand changes in system behavior across source, treatment, pumping, distribution, storage, thermal, and process-loop operations.",
        "systems": [
            {"name": "Source / Intake", "scope": "Incoming supply, source availability, inlet pressure, and upstream demand conditions"},
            {"name": "Treatment", "scope": "Treatment performance, chemistry, quality indicators, and process response"},
            {"name": "Pumping", "scope": "Pump load, runtime, flow response, pressure response, and equipment behavior"},
            {"name": "Distribution", "scope": "Distribution pressure, flow balance, downstream demand, and system recovery behavior"},
            {"name": "Storage / Level", "scope": "Tank, reservoir, basin, or vessel level behavior and refill/recovery patterns"},
            {"name": "Chilled water loops", "scope": "Supply/return temperature, delta-T, loop flow, differential pressure, and load response"},
            {"name": "Telemetry Integrity", "scope": "Signal completeness, timestamp quality, source availability, and confidence impact"},
        ],
        "driver_categories": [
            "source_or_intake_instability",
            "treatment_process_instability",
            "pumping_performance_degradation",
            "distribution_pressure_instability",
            "storage_or_level_recovery_shift",
            "abnormal_water_loss_pattern",
            "chilled_water_delta_t_degradation",
            "process_loop_hydraulic_mismatch",
            "cooling_tower_approach_drift",
            "sensor_disagreement_anomalies",
            "telemetry_integrity_degradation",
        ],
        "integration_stubs": AQUATIC_INTEGRATION_STUBS,
        "replay_demo_mode": "aquatic_demo",
    }
