from __future__ import annotations

import re
from typing import Any

from app.services.cumulative_counters import is_cumulative_counter_name


EQUIPMENT_PROCESS = "equipment_process"
CUMULATIVE_COUNTER = "cumulative_counter"
SCHEDULED_LOAD_CONTEXT = "scheduled_load_context"
WEATHER_ENVIRONMENT = "weather_environment"
CONTROL_OUTPUT = "control_output"
SETPOINT = "setpoint"
IDENTIFIER_CONSTANT = "identifier_constant"
COUNTER_DERIVED_RATE = "counter_derived_rate"

SUPPORTING_CONTEXT_CATEGORIES = {
    CUMULATIVE_COUNTER,
    SCHEDULED_LOAD_CONTEXT,
    WEATHER_ENVIRONMENT,
    SETPOINT,
    IDENTIFIER_CONSTANT,
}


def classify_telemetry_signal(column: str, *, metric_type: str | None = None, constant: bool = False) -> dict[str, Any]:
    name = str(column or "")
    text = _normalized_name(name)
    category = EQUIPMENT_PROCESS
    reason = "Default numeric equipment/process telemetry."

    if metric_type == "counter_delta" or text.endswith("_delta"):
        category = COUNTER_DERIVED_RATE
        reason = "Derived rate from a cumulative counter."
    elif metric_type == "cumulative_counter" or is_cumulative_counter_name(name):
        category = CUMULATIVE_COUNTER
        reason = "Cumulative meter/counter values should provide context rather than direct anomaly ranking."
    elif _has_identifier_or_constant_token(text) or constant:
        category = IDENTIFIER_CONSTANT
        reason = "Identifier or constant-like field."
    elif _has_weather_token(text):
        category = WEATHER_ENVIRONMENT
        reason = "Weather/environmental condition that can explain equipment behavior."
    elif _has_setpoint_token(text):
        category = SETPOINT
        reason = "Operator or controller target value."
    elif _has_scheduled_load_token(text):
        category = SCHEDULED_LOAD_CONTEXT
        reason = "Scheduled/load/context driver that can explain equipment behavior."
    elif _has_control_output_token(text):
        category = CONTROL_OUTPUT
        reason = "Controller output or actuator command."

    role = "primary_signal"
    if category in SUPPORTING_CONTEXT_CATEGORIES:
        role = "supporting_context"
    elif category == CONTROL_OUTPUT:
        role = "control_signal"
    elif category == COUNTER_DERIVED_RATE:
        role = "derived_rate_feature"

    return {
        "category": category,
        "analysis_role": role,
        "is_primary_anomaly_candidate": category not in SUPPORTING_CONTEXT_CATEGORIES,
        "is_context_driver": category in {SCHEDULED_LOAD_CONTEXT, WEATHER_ENVIRONMENT, SETPOINT},
        "reason": reason,
    }


def classify_relationship_columns(columns: list[str]) -> dict[str, Any]:
    classifications = [classify_telemetry_signal(column) for column in columns]
    categories = [item["category"] for item in classifications]
    primary_categories = [category for category in categories if category not in SUPPORTING_CONTEXT_CATEGORIES]
    context_categories = [category for category in categories if category in SUPPORTING_CONTEXT_CATEGORIES]
    return {
        "column_classifications": [
            {"column": column, **classification}
            for column, classification in zip(columns, classifications)
        ],
        "categories": categories,
        "context_only": bool(categories) and not primary_categories,
        "equipment_process_involved": EQUIPMENT_PROCESS in categories or CONTROL_OUTPUT in categories or COUNTER_DERIVED_RATE in categories,
        "context_driver_involved": bool(context_categories),
    }


def is_context_or_supporting_column(column: str, *, metric_type: str | None = None) -> bool:
    return classify_telemetry_signal(column, metric_type=metric_type)["analysis_role"] == "supporting_context"


def _normalized_name(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _tokens(text: str) -> set[str]:
    return {token for token in text.split("_") if token}


def _has_scheduled_load_token(text: str) -> bool:
    tokens = _tokens(text)
    if tokens & {"occupancy", "occupied", "occupants", "schedule", "scheduled", "demand", "load", "loading"}:
        return True
    phrases = (
        "production_rate",
        "process_rate",
        "throughput",
        "workload",
        "building_load",
        "cooling_load",
        "heating_load",
        "chiller_load",
        "kw_demand",
        "peak_demand",
    )
    return any(phrase in text for phrase in phrases)


def _has_weather_token(text: str) -> bool:
    tokens = _tokens(text)
    if tokens & {"weather", "outdoor", "outside", "ambient", "oat"}:
        return True
    phrases = (
        "outdoor_air",
        "outside_air",
        "wet_bulb",
        "dry_bulb",
        "dew_point",
        "ambient_temp",
        "oa_temp",
    )
    return any(phrase in text for phrase in phrases)


def _has_control_output_token(text: str) -> bool:
    tokens = _tokens(text)
    if tokens & {"command", "cmd", "output", "position", "actuator", "vfd", "speed"}:
        return True
    phrases = (
        "valve_position",
        "damper_position",
        "pump_speed",
        "fan_speed",
        "control_signal",
        "controller_output",
    )
    return any(phrase in text for phrase in phrases)


def _has_setpoint_token(text: str) -> bool:
    tokens = _tokens(text)
    return "setpoint" in tokens or "set_point" in text or text.endswith("_sp") or "_sp_" in text


def _has_identifier_or_constant_token(text: str) -> bool:
    tokens = _tokens(text)
    if tokens & {"id", "uuid", "serial", "identifier", "asset", "site"}:
        return True
    return text.endswith("_id") or text.endswith("_code")
