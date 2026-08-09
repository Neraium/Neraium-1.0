from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services.data_quality import parse_numeric_value, parse_timestamp
from app.services.telemetry_classification import signal_classification, telemetry_catalog_by_column


# These are telemetry-role hints, not physical thresholds. Numeric bands are learned
# from the uploaded dataset so the assessor remains portable across domains.
_ROLE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("maintenance_state", ("maintenance", "service_mode", "service_state", "repair")),
    ("cleaning_cycle", ("backwash", "cleaning", "clean_cycle", "flush_cycle", "regeneration")),
    ("setpoint", ("setpoint", "set_point", "_sp")),
    ("active_unit_count", ("active_unit_count", "running_unit_count", "units_active", "active_count")),
    ("equipment_state", ("status", "state", "enabled", "enable", "stage", "mode", "phase", "on_off")),
    ("valve_state", ("valve_state", "valve_status", "valve_position", "damper_position")),
    ("speed_band", ("vfd", "speed", "frequency", "hz")),
    ("load_band", ("load", "demand", "occupancy", "production_rate", "throughput", "workload")),
    ("outdoor_air_band", ("outdoor", "outside_air", "ambient", "weather", "oat", "wet_bulb")),
    ("schedule_state", ("schedule", "occupied", "unoccupied")),
    ("special_event", ("override", "intervention", "special_event", "alarm_state")),
)

_STATE_ROLES = {
    "maintenance_state",
    "cleaning_cycle",
    "setpoint",
    "active_unit_count",
    "equipment_state",
    "valve_state",
    "schedule_state",
    "special_event",
}
_BAND_ROLES = {"speed_band", "load_band", "outdoor_air_band"}
_KNOWN_CHANGE_ROLES = _STATE_ROLES | _BAND_ROLES


@dataclass(frozen=True)
class ContextSignal:
    column: str
    role: str


def assess_operating_modes(
    rows: list[dict[str, Any]],
    *,
    timestamp_column: str | None = None,
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
    baseline_fraction: float = 0.7,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Compare baseline and recent operating context with deterministic rules."""

    if len(rows) < 2:
        if progress_callback:
            progress_callback(0, 0)
        return unavailable_operating_mode("Not enough rows were available to compare operating conditions.")

    if progress_callback:
        progress_callback(0, 2)

    split_index = max(1, min(len(rows) - 1, int(len(rows) * baseline_fraction)))
    baseline_population = rows[:split_index]
    recent_population = rows[split_index:]
    baseline_rows = baseline_population[:12000]
    recent_rows = recent_population[-6000:]
    context_rows = [*baseline_rows, *recent_rows]
    signals = context_signals(context_rows, timestamp_column, telemetry_signal_catalog)
    references = numeric_band_references(context_rows, signals)
    baseline = describe_mode(baseline_rows, signals, references, timestamp_column)
    if progress_callback:
        progress_callback(1, 2)
    recent = describe_mode(recent_rows, signals, references, timestamp_column)
    if progress_callback:
        progress_callback(2, 2)
    explicit_features = sorted(set(baseline["explicit_features"]) & set(recent["explicit_features"]))

    if not explicit_features:
        result = unavailable_operating_mode(
            "No usable equipment-state, staging, load, schedule, weather, setpoint, or event signals were available."
        )
        result.update(
            {
                "baseline_mode": baseline["mode_id"],
                "baseline_mode_label": baseline["mode_label"],
                "recent_mode": recent["mode_id"],
                "recent_mode_label": recent["mode_label"],
                "features": {"baseline": baseline["features"], "recent": recent["features"]},
            }
        )
        return result

    differences = compare_features(baseline["features"], recent["features"], explicit_features)
    material = [item for item in differences if item["feature"] in _KNOWN_CHANGE_ROLES]
    if not differences:
        match = "strong"
    elif any(item["feature"] in _STATE_ROLES for item in differences):
        match = "weak"
    elif len(differences) < len(explicit_features):
        match = "partial"
    else:
        match = "weak"

    confidence = "high" if len(explicit_features) >= 2 else "limited"
    reasons = mode_match_reasons(match, explicit_features, differences)
    return {
        "baseline_mode": baseline["mode_id"],
        "baseline_mode_label": baseline["mode_label"],
        "recent_mode": recent["mode_id"],
        "recent_mode_label": recent["mode_label"],
        "match": match,
        "confidence": confidence,
        "features": {"baseline": baseline["features"], "recent": recent["features"]},
        "differences": differences,
        "reasons": reasons,
        "known_operational_change": bool(material),
        "sampled_context": len(context_rows) < len(rows),
        "population_rows": len(rows),
        "assessed_rows": len(context_rows),
        "assessment_method": "deterministic_telemetry_context_v1",
    }


def apply_operating_mode_context(
    relationship_model: dict[str, Any],
    operating_mode: dict[str, Any],
) -> dict[str, Any]:
    """Attach mode context without changing relationship scores or ordering."""

    model = dict(relationship_model or {})
    model["operating_mode"] = operating_mode
    for key in ("top_relationship_changes", "baseline_relationships"):
        items = model.get(key)
        if isinstance(items, list):
            model[key] = [
                {**item, "operating_mode": operating_mode} if isinstance(item, dict) else item
                for item in items
            ]
    graph = model.get("relationship_graph")
    if isinstance(graph, dict):
        graph = dict(graph)
        for key in (
            "edges",
            "changed_edges",
            "weakened_relationships",
            "strengthened_relationships",
            "new_relationships",
            "missing_relationships",
            "disrupted_relationships",
        ):
            items = graph.get(key)
            if isinstance(items, list):
                graph[key] = [
                    {**item, "operating_mode": operating_mode} if isinstance(item, dict) else item
                    for item in items
                ]
        model["relationship_graph"] = graph
    return model


def context_signals(
    rows: list[dict[str, Any]],
    timestamp_column: str | None,
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None,
) -> list[ContextSignal]:
    catalog = telemetry_catalog_by_column(telemetry_signal_catalog)
    schema_rows = [*rows[:10], *rows[-10:]]
    columns = list(
        dict.fromkeys(
            str(column)
            for row in schema_rows
            for column in row
            if not str(column).startswith("__")
        )
    )
    signals: list[ContextSignal] = []
    for column in columns:
        if column == timestamp_column:
            continue
        role = context_role(column, signal_classification(column, catalog))
        if role:
            signals.append(ContextSignal(column=column, role=role))
    return signals


def context_role(column: str, classification: dict[str, Any]) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(column).lower()).strip("_")
    category = str(classification.get("category") or "")
    if category == "setpoint":
        return "setpoint"
    if category == "weather_environment":
        return "outdoor_air_band"
    if category == "scheduled_load_context":
        return "load_band"
    for role, hints in _ROLE_HINTS:
        if any(hint in normalized for hint in hints):
            return role
    if category in {"binary_status", "equipment_state"}:
        return "equipment_state"
    return None


def numeric_band_references(
    rows: list[dict[str, Any]],
    signals: list[ContextSignal],
) -> dict[str, tuple[float, float]]:
    references: dict[str, tuple[float, float]] = {}
    for signal in signals:
        if signal.role not in _BAND_ROLES:
            continue
        values = sorted(
            value
            for row in rows
            if (value := numeric_value(row.get(signal.column))) is not None
        )
        if not values:
            continue
        references[signal.column] = (
            percentile(values, 1 / 3),
            percentile(values, 2 / 3),
        )
    return references


def describe_mode(
    rows: list[dict[str, Any]],
    signals: list[ContextSignal],
    references: dict[str, tuple[float, float]],
    timestamp_column: str | None,
) -> dict[str, Any]:
    features: dict[str, Any] = {}
    explicit: list[str] = []
    equipment_signals = [signal for signal in signals if signal.role == "equipment_state"]
    if len(equipment_signals) >= 2:
        active_counts = [
            sum(
                1
                for signal in equipment_signals
                if row.get(signal.column) is not None and is_active_value(row.get(signal.column))
            )
            for row in rows
        ]
        if active_counts:
            features["active_unit_count"] = majority(active_counts)
            explicit.append("active_unit_count")
    for signal in signals:
        if signal.role == "equipment_state" and len(equipment_signals) >= 2:
            continue
        feature = summarize_signal(rows, signal, references.get(signal.column))
        if feature is None:
            continue
        features[signal.role] = feature
        explicit.append(signal.role)

    timestamps = [
        parsed
        for row in rows
        if (parsed := timestamp_value(row.get(timestamp_column) if timestamp_column else None)) is not None
    ]
    if timestamps:
        features["time_band"] = majority("day" if 6 <= item.hour < 18 else "night" for item in timestamps)
        features["week_band"] = majority("weekday" if item.weekday() < 5 else "weekend" for item in timestamps)

    label_parts = [
        human_feature(features.get("load_band")),
        human_feature(features.get("time_band")),
        human_feature(features.get("equipment_state")),
    ]
    label = " ".join(part for part in label_parts if part and part != "Typical").strip()
    if not explicit:
        label = "Operating context unavailable"
    elif not label:
        label = "Observed operating context"
    return {
        "mode_id": mode_id(features, explicit),
        "mode_label": label,
        "features": features,
        "explicit_features": explicit,
    }


def summarize_signal(
    rows: list[dict[str, Any]],
    signal: ContextSignal,
    band_reference: tuple[float, float] | None,
) -> Any:
    raw_values = [row.get(signal.column) for row in rows]
    clean_values = [value for value in raw_values if value is not None and str(value).strip()]
    if not clean_values:
        return None

    if signal.role in _BAND_ROLES:
        numeric = [value for value in (numeric_value(item) for item in clean_values) if value is not None]
        if not numeric or band_reference is None:
            return None
        median = percentile(sorted(numeric), 0.5)
        low, high = band_reference
        if low == high:
            return "typical"
        if median < low:
            return "low"
        if median > high:
            return "high"
        return "typical"

    if signal.role in {"maintenance_state", "cleaning_cycle", "special_event"}:
        return "present" if any(is_active_value(value) for value in clean_values) else "not_observed"

    numeric = [value for value in (numeric_value(item) for item in clean_values) if value is not None]
    if signal.role == "active_unit_count" and numeric:
        return round(percentile(sorted(numeric), 0.5), 3)
    if numeric and len(set(numeric)) <= 12:
        selected = majority(round(value, 3) for value in numeric)
        if set(numeric).issubset({0.0, 1.0}):
            return "enabled" if float(selected) == 1.0 else "disabled"
        return selected
    return majority(normalize_state(value) for value in clean_values)


def compare_features(
    baseline: dict[str, Any],
    recent: dict[str, Any],
    explicit_features: list[str],
) -> list[dict[str, Any]]:
    differences = []
    for feature in sorted(explicit_features):
        left = baseline.get(feature)
        right = recent.get(feature)
        if left == right:
            continue
        differences.append(
            {
                "feature": feature,
                "baseline": left,
                "recent": right,
                "reason": f"{feature.replace('_', ' ').capitalize()} differed between the baseline and recent periods.",
            }
        )
    for feature in ("time_band", "week_band"):
        left = baseline.get(feature)
        right = recent.get(feature)
        if left and right and left != right:
            differences.append(
                {
                    "feature": feature,
                    "baseline": left,
                    "recent": right,
                    "reason": f"{feature.replace('_', ' ').capitalize()} differed between the comparison periods.",
                }
            )
    return differences


def mode_match_reasons(
    match: str,
    explicit_features: list[str],
    differences: list[dict[str, Any]],
) -> list[str]:
    if match == "strong":
        return [
            f"Baseline and recent periods matched across {len(explicit_features)} available operating-context feature(s)."
        ]
    reasons = [item["reason"] for item in differences[:4]]
    if match == "partial":
        reasons.append("Some operating conditions matched, but the comparison is not fully like-for-like.")
    else:
        reasons.append("Material operating-context differences prevent a like-for-like relationship comparison.")
    return reasons


def unavailable_operating_mode(reason: str) -> dict[str, Any]:
    return {
        "baseline_mode": "unavailable",
        "baseline_mode_label": "Operating context unavailable",
        "recent_mode": "unavailable",
        "recent_mode_label": "Operating context unavailable",
        "match": "unavailable",
        "confidence": "low",
        "features": {"baseline": {}, "recent": {}},
        "differences": [],
        "reasons": [reason],
        "known_operational_change": False,
        "assessment_method": "deterministic_telemetry_context_v1",
    }


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, int(round((len(values) - 1) * fraction))))
    return float(values[index])


def majority(values: Any) -> Any:
    counts = Counter(values)
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))[0][0]


def numeric_value(value: Any) -> float | None:
    return parse_numeric_value(str(value)) if value is not None else None


def timestamp_value(value: Any) -> datetime | None:
    return parse_timestamp(str(value)) if value is not None else None


def is_active_value(value: Any) -> bool:
    numeric = numeric_value(value)
    if numeric is not None:
        return numeric > 0
    return normalize_state(value) in {"active", "enabled", "on", "true", "yes", "present", "maintenance", "cleaning"}


def normalize_state(value: Any) -> str:
    return re.sub(r"\s+", "_", str(value).strip().lower())


def human_feature(value: Any) -> str:
    return str(value or "").replace("_", " ").title()


def mode_id(features: dict[str, Any], explicit_features: list[str]) -> str:
    if not explicit_features:
        return "unavailable"
    keys = [
        key
        for key in ("load_band", "time_band", "active_unit_count", "equipment_state", "schedule_state")
        if key in features
    ]
    if not keys:
        keys = sorted(explicit_features)[:3]
    value = "_".join(f"{key}_{features[key]}" for key in keys)
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "observed_mode"
