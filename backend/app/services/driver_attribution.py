from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.cultivation_mapping import category_for_column


DRIVER_LABELS = {
    "humidity_control": "Humidity control instability",
    "hvac_instability": "Room temperature control instability",
    "airflow_restriction": "Airflow restriction",
    "irrigation_timing": "Irrigation timing response",
    "lighting_schedule": "Lighting schedule influence",
    "sensor_network": "Sensor network continuity",
    "unknown_system_drift": "Unclear room system trend",
}

NEXT_MOVES = {
    "humidity_control": "Check dehumidification, airflow, and room sealing",
    "hvac_instability": "Check room temperature setpoints, HVAC activity, and recovery timing",
    "airflow_restriction": "Check fans, filters, vents, and room pressure balance",
    "irrigation_timing": "Check feed timing, runoff response, and post-feed room conditions",
    "lighting_schedule": "Check photoperiod schedule, fixture timing, and heat response",
    "sensor_network": "Check sensor sync, gateway status, and stale room readings",
    "unknown_system_drift": "Collect more room telemetry before assigning a likely driver",
}

CATEGORY_SIGNALS = {
    "humidity_control": ["humidity", "HVAC", "airflow"],
    "hvac_instability": ["temperature", "HVAC", "humidity"],
    "airflow_restriction": ["airflow", "HVAC", "humidity"],
    "irrigation_timing": ["irrigation", "humidity", "temperature"],
    "lighting_schedule": ["lighting", "temperature"],
    "sensor_network": ["sensor network", "timestamps", "room data"],
    "unknown_system_drift": ["room telemetry"],
}


@dataclass
class DriverScore:
    category: str
    score: float = 0
    evidence: list[str] = field(default_factory=list)
    signals: set[str] = field(default_factory=set)
    persistent: bool = False
    relationship_change: bool = False

    def add(
        self,
        points: float,
        evidence: str,
        signal: str | None = None,
        *,
        persistent: bool = False,
        relationship_change: bool = False,
    ) -> None:
        self.score += points
        if evidence not in self.evidence:
            self.evidence.append(evidence)
        if signal:
            self.signals.add(signal)
        self.persistent = self.persistent or persistent
        self.relationship_change = self.relationship_change or relationship_change


def build_driver_attribution(
    room_state: dict[str, Any] | None,
    telemetry_context: dict[str, Any] | None,
    baseline_context: dict[str, Any] | None,
    engine_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a deterministic, evidence-ranked driver attribution.

    The output is intentionally causal-safe: it ranks likely contributors using
    telemetry evidence but does not claim an exact root cause.
    """

    room_state = room_state or {}
    telemetry_context = telemetry_context or {}
    baseline_context = baseline_context or {}
    engine_result = engine_result or {}

    scores = {
        category: DriverScore(category)
        for category in DRIVER_LABELS
        if category != "unknown_system_drift"
    }

    baseline_analysis = baseline_context.get("baseline_analysis", baseline_context)
    cultivation_mapping = baseline_context.get("cultivation_mapping") or telemetry_context.get("cultivation_mapping") or {}
    column_to_category = build_column_category_lookup(cultivation_mapping)
    persistent_columns = set(
        engine_result.get("persistence_assessment", {}).get("persistent_columns", [])
    )

    score_baseline_drift(scores, baseline_analysis, column_to_category, persistent_columns)
    score_relationships(scores, engine_result, column_to_category)
    score_sensor_network(scores, telemetry_context, baseline_analysis, cultivation_mapping)

    ranked = sorted(scores.values(), key=lambda item: item.score, reverse=True)
    top = ranked[0] if ranked else DriverScore("unknown_system_drift")
    evidence_strength = len(top.evidence)
    has_corrob = top.persistent or top.relationship_change or len(top.signals) >= 2

    if top.score < 3 or evidence_strength < 2 or not has_corrob:
        return unknown_attribution(room_state, telemetry_context, top)

    return {
        "room": room_state.get("room") or room_state.get("label") or "Current room",
        "state": room_state.get("state") or room_state.get("status") or "Needs review",
        "likely_driver": DRIVER_LABELS[top.category],
        "driver_category": top.category,
        "contributing_signals": sorted(top.signals) or CATEGORY_SIGNALS[top.category],
        "supporting_evidence": top.evidence[:4],
        "confidence_basis": confidence_basis(top),
        "next_operator_move": NEXT_MOVES[top.category],
        "severity": severity_from_score(top.score, room_state),
        "attribution_confidence": confidence_from_score(top),
    }


def score_baseline_drift(
    scores: dict[str, DriverScore],
    baseline_analysis: dict[str, Any],
    column_to_category: dict[str, str],
    persistent_columns: set[str],
) -> None:
    for item in baseline_analysis.get("column_drift", []):
        flag = item.get("drift_flag")
        if flag not in {"watch", "review"}:
            continue
        column = item.get("column", "")
        category = driver_category_for_column(column, column_to_category)
        if category not in scores:
            continue
        points = 3 if flag == "review" else 1.5
        persistent = column in persistent_columns
        if persistent:
            points += 2
        signal = signal_name_for_category(category)
        scores[category].add(
            points,
            evidence_for_drift(category, column, persistent),
            signal,
            persistent=persistent,
        )

        if category == "humidity_control" and has_related_column(column_to_category, "HVAC"):
            scores["hvac_instability"].add(
                0.75,
                "Humidity movement overlaps with HVAC context",
                "HVAC",
            )
        if category == "hvac_instability" and has_related_column(column_to_category, "humidity"):
            scores["humidity_control"].add(
                0.75,
                "Room temperature movement overlaps with humidity context",
                "humidity",
            )


def score_relationships(
    scores: dict[str, DriverScore],
    engine_result: dict[str, Any],
    column_to_category: dict[str, str],
) -> None:
    for item in engine_result.get("evidence", []):
        if item.get("type") != "relationship_change" or abs(item.get("change", 0)) < 0.5:
            continue
        columns = item.get("columns", [])
        categories = {driver_category_for_column(column, column_to_category) for column in columns}
        categories.discard("unknown_system_drift")
        evidence = relationship_evidence(columns)
        for category in categories:
            if category in scores:
                scores[category].add(
                    1.5,
                    evidence,
                    signal_name_for_category(category),
                    relationship_change=True,
                )
        score_relationship_pair(scores, categories, evidence)


def score_relationship_pair(
    scores: dict[str, DriverScore],
    categories: set[str],
    evidence: str,
) -> None:
    if {"humidity_control", "hvac_instability"} <= categories:
        scores["humidity_control"].add(2, "Humidity recovery is becoming less stable after environmental transitions", "humidity", relationship_change=True)
        scores["hvac_instability"].add(1, evidence, "HVAC", relationship_change=True)
    if {"airflow_restriction", "hvac_instability"} <= categories or {"airflow_restriction", "humidity_control"} <= categories:
        scores["airflow_restriction"].add(2, "Air movement behavior became less consistent during changing room conditions", "airflow", relationship_change=True)
    if "irrigation_timing" in categories and ("humidity_control" in categories or "hvac_instability" in categories):
        scores["irrigation_timing"].add(2, "Room recovery behavior is changing around irrigation-related signals", "irrigation", relationship_change=True)
    if {"lighting_schedule", "hvac_instability"} <= categories:
        scores["lighting_schedule"].add(2, "Lighting and room temperature response became less consistent", "lighting", relationship_change=True)


def score_sensor_network(
    scores: dict[str, DriverScore],
    telemetry_context: dict[str, Any],
    baseline_analysis: dict[str, Any],
    cultivation_mapping: dict[str, Any],
) -> None:
    sensor_score = scores["sensor_network"]
    timestamp_profile = telemetry_context.get("timestamp_profile", {})
    data_quality = telemetry_context.get("data_quality", {})
    numeric_profiles = telemetry_context.get("numeric_profiles", [])

    if not timestamp_profile.get("detected_timestamp_column"):
        sensor_score.add(2, "Timestamp coverage is missing or unclear", "timestamps")
    for warning in timestamp_profile.get("warnings", []):
        sensor_score.add(2, readable_warning(warning), "timestamps")
    for warning in data_quality.get("warnings", []):
        if mentions_any(warning, ["missing", "timestamp", "stale", "parse", "sensor"]):
            sensor_score.add(1.5, readable_warning(warning), "room data")
    for profile in numeric_profiles:
        if profile.get("missing_count", 0) > 0:
            sensor_score.add(
                1.5,
                f"{profile['column']} has missing room readings",
                "room data",
            )
    if baseline_analysis.get("warnings"):
        for warning in baseline_analysis["warnings"]:
            if mentions_any(warning, ["missing", "not enough", "numeric"]):
                sensor_score.add(1, readable_warning(warning), "room data")
    if cultivation_mapping.get("unknown_column_count", 0) > 0:
        sensor_score.add(0.75, "Some source columns are not mapped to cultivation systems", "room data")


def unknown_attribution(
    room_state: dict[str, Any],
    telemetry_context: dict[str, Any],
    top: DriverScore,
) -> dict[str, Any]:
    evidence = top.evidence[:2]
    readiness = telemetry_context.get("data_quality", {}).get("readiness")
    has_directional_evidence = top.category != "unknown_system_drift" and top.score >= 1.5 and bool(evidence)
    driver_category = top.category if has_directional_evidence else "unknown_system_drift"
    if not evidence:
        evidence = ["Available telemetry does not provide enough corroborating evidence"]
    return {
        "room": room_state.get("room") or room_state.get("label") or "Current room",
        "state": room_state.get("state") or room_state.get("status") or "Needs review",
        "likely_driver": DRIVER_LABELS[driver_category],
        "driver_category": driver_category,
        "contributing_signals": sorted(top.signals) or CATEGORY_SIGNALS[driver_category],
        "supporting_evidence": evidence,
        "confidence_basis": (
            "Single-signal drift is present, but corroboration is still limited."
            if has_directional_evidence
            else "Evidence is limited or based on a single weak signal."
        ),
        "next_operator_move": NEXT_MOVES[driver_category],
        "severity": "review" if readiness != "ready" or has_directional_evidence else "info",
        "attribution_confidence": "low",
    }


def build_column_category_lookup(cultivation_mapping: dict[str, Any]) -> dict[str, str]:
    categories = cultivation_mapping.get("categories", {})
    return {
        column: category
        for category, columns in categories.items()
        for column in columns
    }


def driver_category_for_column(column: str, column_to_category: dict[str, str]) -> str:
    source_category = column_to_category.get(column) or category_for_column(column)
    return {
        "humidity": "humidity_control",
        "temperature": "hvac_instability",
        "HVAC": "hvac_instability",
        "airflow": "airflow_restriction",
        "irrigation": "irrigation_timing",
        "lighting": "lighting_schedule",
        "sensor network": "sensor_network",
    }.get(source_category, "unknown_system_drift")


def has_related_column(column_to_category: dict[str, str], source_category: str) -> bool:
    return any(category == source_category for category in column_to_category.values())


def signal_name_for_category(category: str) -> str:
    return {
        "humidity_control": "humidity",
        "hvac_instability": "HVAC",
        "airflow_restriction": "airflow",
        "irrigation_timing": "irrigation",
        "lighting_schedule": "lighting",
        "sensor_network": "sensor network",
    }.get(category, "room telemetry")


def evidence_for_drift(category: str, column: str, persistent: bool) -> str:
    base = {
        "humidity_control": "Humidity behavior moved away from baseline",
        "hvac_instability": "Room temperature behavior moved away from baseline",
        "airflow_restriction": "Air movement behavior moved away from baseline",
        "irrigation_timing": "Irrigation response moved away from baseline",
        "lighting_schedule": "Lighting-related readings moved away from baseline",
        "sensor_network": "Sensor readings moved away from expected continuity",
    }.get(category, f"{column} moved away from baseline")
    if persistent:
        return f"{base} and persisted across recent readings"
    return base


def relationship_evidence(columns: list[str]) -> str:
    if len(columns) >= 2:
        return relationship_evidence_sentence(columns[0], columns[1])
    return "Environmental coupling is less consistent than the room's recent baseline"


def relationship_evidence_sentence(first_column: str, second_column: str) -> str:
    first = display_column(first_column)
    second = display_column(second_column)
    normalized = f"{first} {second}".lower()
    if "intervention window" in normalized:
        return "Intervention windows are shortening as environmental recovery slows"
    if "humidity" in normalized and ("airflow" in normalized or "air movement" in normalized):
        return "Airflow response consistency weakened during active climate periods"
    if "humidity" in normalized:
        return "Humidity recovery is becoming less stable after environmental transitions"
    if "airflow" in normalized or "air movement" in normalized:
        return "Air movement behavior is diverging from this room's recent operating pattern"
    return "Environmental coupling is less consistent than the room's recent baseline"


def display_column(column: str) -> str:
    normalized = str(column).lower().replace("_", " ")
    aliases = {
        "intervention window hours": "intervention window",
        "hvac runtime": "HVAC runtime",
        "co2": "CO2",
    }
    return aliases.get(normalized, normalized)


def confidence_basis(score: DriverScore) -> str:
    if score.persistent and score.relationship_change:
        return "Persistent multi-signal drift with relationship-change support"
    if score.persistent and len(score.signals) >= 2:
        return "Persistent multi-signal drift, not a single sensor spike"
    if score.relationship_change and len(score.signals) >= 2:
        return "Multiple contributing signals with relationship-change support"
    return "Multiple supporting signals from the uploaded telemetry"


def severity_from_score(score: float, room_state: dict[str, Any]) -> str:
    existing = (room_state.get("severity") or room_state.get("tone") or "").lower()
    if existing in {"unstable", "action"} or score >= 8:
        return "action"
    if existing in {"review", "elevated"} or score >= 3:
        return "review"
    return "info"


def confidence_from_score(score: DriverScore) -> str:
    if score.score >= 8 and score.persistent and score.relationship_change:
        return "high"
    if score.score >= 4.5:
        return "medium"
    return "low"


def readable_warning(warning: str) -> str:
    if not warning:
        return "Telemetry warning present"
    return warning.rstrip(".")


def mentions_any(value: str, needles: list[str]) -> bool:
    normalized = value.lower()
    return any(needle in normalized for needle in needles)
