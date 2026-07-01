from __future__ import annotations

import re
from typing import Any

from app.services.cumulative_counters import is_cumulative_counter_name


EQUIPMENT_PROCESS = "equipment_process"
EQUIPMENT_STATE = "equipment_state"
BINARY_STATUS = "binary_status"
CUMULATIVE_COUNTER = "cumulative_counter"
COUNTER = "counter"
SCHEDULED_LOAD_CONTEXT = "scheduled_load_context"
WEATHER_ENVIRONMENT = "weather_environment"
CONTROL_OUTPUT = "control_output"
SETPOINT = "setpoint"
IDENTIFIER_CONSTANT = "identifier_constant"
IDENTIFIER = "identifier"
CONSTANT = "constant"
GROUND_TRUTH_LABEL = "ground_truth_label"
SYNTHETIC_FEATURE = "synthetic_feature"
TIMESTAMP = "timestamp"
UNKNOWN = "unknown"
COUNTER_DERIVED_RATE = "counter_derived_rate"

STRUCTURAL_CLASS_LABELS = {
    EQUIPMENT_PROCESS: "Equipment Process Variable",
    EQUIPMENT_STATE: "Equipment State",
    BINARY_STATUS: "Binary Status",
    CONTROL_OUTPUT: "Control Output",
    SETPOINT: "Setpoint",
    SCHEDULED_LOAD_CONTEXT: "Context / Demand Driver",
    WEATHER_ENVIRONMENT: "Weather / Environmental",
    COUNTER: "Counter",
    CUMULATIVE_COUNTER: "Cumulative Counter",
    GROUND_TRUTH_LABEL: "Ground Truth Label",
    SYNTHETIC_FEATURE: "Synthetic Feature",
    TIMESTAMP: "Timestamp",
    IDENTIFIER: "Identifier",
    IDENTIFIER_CONSTANT: "Identifier",
    CONSTANT: "Constant",
    COUNTER_DERIVED_RATE: "Counter",
    UNKNOWN: "Unknown",
}

SUPPORTING_CONTEXT_CATEGORIES = {
    CUMULATIVE_COUNTER,
    COUNTER,
    SCHEDULED_LOAD_CONTEXT,
    WEATHER_ENVIRONMENT,
    SETPOINT,
    IDENTIFIER_CONSTANT,
    IDENTIFIER,
    CONSTANT,
    GROUND_TRUTH_LABEL,
    SYNTHETIC_FEATURE,
    TIMESTAMP,
    BINARY_STATUS,
    EQUIPMENT_STATE,
    UNKNOWN,
}

IGNORED_CATEGORIES = {
    IDENTIFIER_CONSTANT,
    IDENTIFIER,
    CONSTANT,
    TIMESTAMP,
}

NON_OPERATOR_RELATIONSHIP_CATEGORIES = {
    CUMULATIVE_COUNTER,
    COUNTER,
    GROUND_TRUTH_LABEL,
    SYNTHETIC_FEATURE,
    TIMESTAMP,
    IDENTIFIER_CONSTANT,
    IDENTIFIER,
    CONSTANT,
}

PRIMARY_METRIC_CATEGORIES = {
    EQUIPMENT_PROCESS,
    COUNTER_DERIVED_RATE,
}

EQUIPMENT_RELATIONSHIP_CATEGORIES = {
    EQUIPMENT_PROCESS,
    CONTROL_OUTPUT,
    COUNTER_DERIVED_RATE,
}


def classify_telemetry_signal(
    column: str,
    *,
    metric_type: str | None = None,
    constant: bool = False,
    numeric_profile: dict[str, Any] | None = None,
    timestamp: bool = False,
) -> dict[str, Any]:
    name = str(column or "")
    text = _normalized_name(name)
    category = EQUIPMENT_PROCESS
    reason = "Default numeric equipment/process telemetry."
    numeric_profile = numeric_profile if isinstance(numeric_profile, dict) else {}
    constant = constant or bool(numeric_profile.get("constant_or_stuck"))

    if timestamp or metric_type == "timestamp" or _has_timestamp_token(text):
        category = TIMESTAMP
        reason = "Timestamp/context column."
    elif metric_type == "counter_delta" or text.endswith("_delta"):
        category = COUNTER_DERIVED_RATE
        reason = "Derived rate from a cumulative counter."
    elif metric_type == "cumulative_counter" or is_cumulative_counter_name(name):
        category = CUMULATIVE_COUNTER
        reason = "Cumulative meter/counter values should provide context rather than direct anomaly ranking."
    elif _has_ground_truth_token(text):
        category = GROUND_TRUTH_LABEL
        reason = "Ground-truth or validation label; reserved for validation/developer context."
    elif _has_synthetic_feature_token(text):
        category = SYNTHETIC_FEATURE
        reason = "Derived or synthetic feature rather than source equipment telemetry."
    elif _has_identifier_token(text):
        category = IDENTIFIER
        reason = "Identifier field."
    elif constant:
        category = CONSTANT
        reason = "Constant or stuck field."
    elif _is_binary_status(text, numeric_profile):
        category = BINARY_STATUS
        reason = "Binary status/state signal; transition and dwell behavior should be reviewed separately."
    elif _has_equipment_state_token(text):
        category = EQUIPMENT_STATE
        reason = "Equipment state or mode signal."
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
    elif _has_counter_token(text):
        category = COUNTER
        reason = "Event/count field; analyze a rate or delta instead of raw count drift."

    role = "primary_signal"
    if category in {IDENTIFIER_CONSTANT, IDENTIFIER, CONSTANT}:
        role = "ignored"
    elif category == TIMESTAMP:
        role = "timestamp"
    elif category == GROUND_TRUTH_LABEL:
        role = "validation_label"
    elif category == SYNTHETIC_FEATURE:
        role = "synthetic_feature"
    elif category in {BINARY_STATUS, EQUIPMENT_STATE}:
        role = "state_signal"
    elif category in SUPPORTING_CONTEXT_CATEGORIES:
        role = "supporting_context"
    elif category == CONTROL_OUTPUT:
        role = "control_signal"
    elif category == COUNTER_DERIVED_RATE:
        role = "derived_rate_feature"

    return {
        "category": category,
        "structural_class": STRUCTURAL_CLASS_LABELS.get(category, "Unknown"),
        "structural_class_key": category,
        "analysis_role": role,
        "is_primary_anomaly_candidate": category in PRIMARY_METRIC_CATEGORIES,
        "operator_primary_eligible": category in PRIMARY_METRIC_CATEGORIES,
        "is_context_driver": category in {SCHEDULED_LOAD_CONTEXT, WEATHER_ENVIRONMENT, SETPOINT},
        "is_state_signal": category in {BINARY_STATUS, EQUIPMENT_STATE},
        "is_ignored": category in IGNORED_CATEGORIES,
        "requires_derived_rate": category in {COUNTER, CUMULATIVE_COUNTER},
        "reason": reason,
    }


def classify_relationship_columns(
    columns: list[str],
    *,
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    catalog = telemetry_catalog_by_column(telemetry_signal_catalog)
    classifications = [signal_classification(column, catalog) for column in columns]
    categories = [item["category"] for item in classifications]
    primary_categories = [category for category in categories if category not in SUPPORTING_CONTEXT_CATEGORIES]
    context_categories = [category for category in categories if category in SUPPORTING_CONTEXT_CATEGORIES]
    blocked_categories = [category for category in categories if category in NON_OPERATOR_RELATIONSHIP_CATEGORIES]
    state_categories = [category for category in categories if category in {BINARY_STATUS, EQUIPMENT_STATE}]
    operator_primary_eligible = bool(categories) and not blocked_categories and not state_categories and any(
        classification.get("operator_primary_eligible") for classification in classifications
    )
    return {
        "column_classifications": [
            {"column": column, **classification}
            for column, classification in zip(columns, classifications)
        ],
        "categories": categories,
        "context_only": bool(categories) and not primary_categories,
        "equipment_process_involved": any(category in EQUIPMENT_RELATIONSHIP_CATEGORIES for category in categories),
        "context_driver_involved": bool(context_categories),
        "state_signal_involved": bool(state_categories),
        "operator_primary_eligible": operator_primary_eligible,
        "blocked_operator_categories": blocked_categories,
    }


def is_context_or_supporting_column(
    column: str,
    *,
    metric_type: str | None = None,
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
) -> bool:
    catalog = telemetry_catalog_by_column(telemetry_signal_catalog)
    classification = signal_classification(column, catalog, metric_type=metric_type)
    return classification["analysis_role"] in {
        "supporting_context",
        "ignored",
        "validation_label",
        "state_signal",
        "timestamp",
        "synthetic_feature",
    }


def build_telemetry_signal_catalog(
    columns: list[str],
    *,
    numeric_profiles: list[dict[str, Any]] | None = None,
    timestamp_column: str | None = None,
    header_present: bool = True,
) -> dict[str, dict[str, Any]]:
    profiles = {
        str(profile.get("column")): profile
        for profile in (numeric_profiles or [])
        if isinstance(profile, dict) and profile.get("column")
    }
    catalog: dict[str, dict[str, Any]] = {}
    for index, column in enumerate(columns):
        column_name = str(column)
        profile = profiles.get(column_name, {})
        classification = classify_telemetry_signal(
            column_name,
            numeric_profile=profile,
            timestamp=bool(timestamp_column and column_name == str(timestamp_column)),
        )
        original_header = column_name.strip() if header_present and not _is_generated_column_name(column_name) else ""
        normalized_name = _normalized_name(original_header or column_name)
        display_name = _display_name(original_header)
        units = _engineering_units(original_header or column_name)
        catalog[column_name] = {
            "source_column": column_name,
            "original_header": original_header,
            "normalized_name": normalized_name if original_header else "",
            "display_name": display_name,
            "engineering_units": units,
            "inferred_telemetry_type": classification["structural_class"],
            "source_column_index": index,
            "telemetry_category": classification["category"],
            "analysis_role": classification["analysis_role"],
            "telemetry_classification": classification,
            **classification,
        }
    return catalog


def update_catalog_from_baseline(
    catalog: dict[str, dict[str, Any]],
    baseline_analysis: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    updated = {key: dict(value) for key, value in (catalog or {}).items()}
    for item in baseline_analysis.get("column_drift", []) if isinstance(baseline_analysis, dict) else []:
        if not isinstance(item, dict):
            continue
        column = str(item.get("column") or "")
        if not column or column not in updated:
            continue
        classification = item.get("telemetry_classification")
        if isinstance(classification, dict):
            updated[column].update(
                {
                    "inferred_telemetry_type": classification.get("structural_class", updated[column].get("inferred_telemetry_type")),
                    "telemetry_category": classification.get("category", updated[column].get("telemetry_category")),
                    "analysis_role": classification.get("analysis_role", updated[column].get("analysis_role")),
                    "telemetry_classification": classification,
                    **classification,
                }
            )
    return updated


def telemetry_catalog_by_column(
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    if isinstance(telemetry_signal_catalog, dict):
        return {
            str(key): value
            for key, value in telemetry_signal_catalog.items()
            if isinstance(value, dict)
        }
    if isinstance(telemetry_signal_catalog, list):
        return {
            str(item.get("source_column") or item.get("column") or item.get("tag_name")): item
            for item in telemetry_signal_catalog
            if isinstance(item, dict) and (item.get("source_column") or item.get("column") or item.get("tag_name"))
        }
    return {}


def signal_classification(
    column: str,
    catalog: dict[str, dict[str, Any]] | None = None,
    *,
    metric_type: str | None = None,
) -> dict[str, Any]:
    metadata = (catalog or {}).get(str(column), {})
    classification = metadata.get("telemetry_classification") if isinstance(metadata, dict) else None
    if isinstance(classification, dict):
        return classification
    return classify_telemetry_signal(column, metric_type=metric_type)


def signal_display_name(
    column: str,
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
) -> str:
    catalog = telemetry_catalog_by_column(telemetry_signal_catalog)
    metadata = catalog.get(str(column), {})
    for key in ("display_name", "normalized_name", "original_header"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    index = metadata.get("source_column_index")
    if index is not None:
        try:
            return f"Column {int(index) + 1}"
        except (TypeError, ValueError):
            pass
    return str(column or "").strip() or "Signal"


def signal_metadata(
    column: str,
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return dict(telemetry_catalog_by_column(telemetry_signal_catalog).get(str(column), {}))


def _normalized_name(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _tokens(text: str) -> set[str]:
    return {token for token in text.split("_") if token}


def _has_timestamp_token(text: str) -> bool:
    return text in {"timestamp", "time", "datetime", "date", "recorded_at", "created_at"} or "timestamp" in text


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


def _has_identifier_token(text: str) -> bool:
    tokens = _tokens(text)
    if tokens & {"id", "uuid", "serial", "identifier", "asset", "site", "facility", "room", "zone", "location", "area"}:
        return True
    return text.endswith("_id") or text.endswith("_code")


def _has_ground_truth_token(text: str) -> bool:
    tokens = _tokens(text)
    if text.startswith("gt_") or text.startswith("truth_") or "ground_truth" in text:
        return True
    return bool(tokens & {"label", "labels", "target", "truth", "outcome"})


def _has_synthetic_feature_token(text: str) -> bool:
    tokens = _tokens(text)
    return bool(tokens & {"synthetic", "derived", "feature"}) or text.endswith("_score")


def _has_equipment_state_token(text: str) -> bool:
    tokens = _tokens(text)
    return bool(tokens & {"state", "mode", "stage", "phase", "cycle"})


def _has_counter_token(text: str) -> bool:
    tokens = _tokens(text)
    return bool(tokens & {"count", "counts", "counter", "events", "starts", "cycles"}) or text.endswith("_count")


def _has_binary_status_token(text: str) -> bool:
    tokens = _tokens(text)
    return bool(tokens & {"status", "flag", "enabled", "active", "inactive", "on", "off", "open", "closed", "occupied", "occupancy", "alarm", "fault", "trip"})


def _is_binary_status(text: str, numeric_profile: dict[str, Any]) -> bool:
    values = numeric_profile.get("unique_values")
    if not isinstance(values, list):
        values = []
    numeric_values = set()
    for value in values:
        try:
            numeric_values.add(float(value))
        except (TypeError, ValueError):
            continue
    if numeric_values and numeric_values.issubset({0.0, 1.0}):
        return True
    return _has_binary_status_token(text) and numeric_profile.get("min") in {0, 0.0} and numeric_profile.get("max") in {1, 1.0}


def _engineering_units(value: str) -> str:
    text = str(value or "").strip()
    match = re.search(r"\(([^)]+)\)", text)
    if match:
        return match.group(1).strip()
    normalized = _normalized_name(text)
    suffixes = {
        "deg_f": "F",
        "temp_f": "F",
        "f": "F",
        "deg_c": "C",
        "temp_c": "C",
        "c": "C",
        "psi": "psi",
        "kpa": "kPa",
        "gpm": "gpm",
        "lpm": "lpm",
        "ppm": "ppm",
        "pct": "%",
        "percent": "%",
        "kw": "kW",
        "kwh": "kWh",
        "ips": "ips",
    }
    parts = normalized.split("_")
    for width in (2, 1):
        suffix = "_".join(parts[-width:])
        if suffix in suffixes:
            return suffixes[suffix]
    return ""


def _display_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\([^)]*\)", "", text)
    parts = [part for part in _normalized_name(text).split("_") if part]
    unit_tokens = {"f", "c", "pct", "percent", "psi", "kpa", "gpm", "lpm", "ppm", "kw", "kwh", "ips"}
    if len(parts) > 1 and parts[-1] in unit_tokens:
        parts = parts[:-1]
    acronyms = {"hvac", "co2", "ph", "vfd", "ct", "chw", "kw", "kwh", "psi", "gpm", "ppm"}
    words = [part.upper() if part in acronyms else part for part in parts]
    return " ".join(words).capitalize() if words else ""


def _is_generated_column_name(value: str) -> bool:
    return bool(re.fullmatch(r"column_\d+", str(value or "").strip().lower()))
