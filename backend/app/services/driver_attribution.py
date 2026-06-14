from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.cultivation_mapping import category_for_column
from app.services.subsystem_motifs import analyze_subsystem_motifs


DRIVER_LABELS = {
    "moisture_control": "Moisture signal instability",
    "thermal_control": "Thermal signal instability",
    "flow_restriction": "Flow signal restriction",
    "process_timing": "Process timing response",
    "energy_schedule": "Energy/schedule influence",
    "sensor_network": "Sensor/network continuity",
    # legacy aliases kept for compatibility with existing downstream logic
    "humidity_control": "Moisture signal instability",
    "hvac_instability": "Thermal signal instability",
    "airflow_restriction": "Flow signal restriction",
    "irrigation_timing": "Process timing response",
    "lighting_schedule": "Energy/schedule influence",
    "unknown_system_drift": "Unclear system trend",
}

NEXT_MOVES = {
    "moisture_control": "Check moisture control setpoints, environmental coupling, and recovery timing",
    "thermal_control": "Check thermal control setpoints and recovery timing",
    "flow_restriction": "Check circulation/flow paths, filters, and pressure balance",
    "process_timing": "Check timing/scheduling around process transitions",
    "energy_schedule": "Check schedule timing and correlated energy/thermal responses",
    "sensor_network": "Check sensor sync, gateway status, and stale readings",
    "humidity_control": "Check moisture control setpoints, environmental coupling, and recovery timing",
    "hvac_instability": "Check thermal control setpoints and recovery timing",
    "airflow_restriction": "Check circulation/flow paths, filters, and pressure balance",
    "irrigation_timing": "Check timing/scheduling around process transitions",
    "lighting_schedule": "Check schedule timing and correlated energy/thermal responses",
    "unknown_system_drift": "Collect more telemetry coverage before assigning a likely driver",
}

CATEGORY_SIGNALS = {
    "moisture_control": ["moisture", "thermal", "flow"],
    "thermal_control": ["thermal", "energy", "moisture"],
    "flow_restriction": ["flow", "thermal", "moisture"],
    "process_timing": ["timing", "flow", "thermal"],
    "energy_schedule": ["energy", "timing"],
    "sensor_network": ["network", "timestamps", "telemetry"],
    "humidity_control": ["moisture", "thermal", "flow"],
    "hvac_instability": ["thermal", "energy", "moisture"],
    "airflow_restriction": ["flow", "thermal", "moisture"],
    "irrigation_timing": ["timing", "flow", "thermal"],
    "lighting_schedule": ["energy", "timing"],
    "unknown_system_drift": ["telemetry"],
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

    subsystem_override = analyze_subsystem_motifs(
        telemetry_context=telemetry_context,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
    )
    if subsystem_override is not None:
        return {
            "room": room_state.get("room") or room_state.get("label") or "Current room",
            "state": room_state.get("state") or room_state.get("status") or "Needs review",
            **subsystem_override,
        }

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

        if category == "moisture_control" and has_related_column(column_to_category, "thermal"):
            scores["thermal_control"].add(
                0.75,
                "Moisture movement overlaps with thermal context",
                "thermal",
            )
        if category == "thermal_control" and has_related_column(column_to_category, "moisture"):
            scores["moisture_control"].add(
                0.75,
                "Thermal movement overlaps with moisture context",
                "moisture",
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
    if {"moisture_control", "thermal_control"} <= categories:
        scores["moisture_control"].add(2, "Moisture recovery is becoming less stable after environmental transitions", "moisture", relationship_change=True)
        scores["thermal_control"].add(1, evidence, "thermal", relationship_change=True)
    if {"flow_restriction", "thermal_control"} <= categories or {"flow_restriction", "moisture_control"} <= categories:
        scores["flow_restriction"].add(2, "Flow behavior became less consistent during changing conditions", "flow", relationship_change=True)
    if "process_timing" in categories and ("moisture_control" in categories or "thermal_control" in categories):
        scores["process_timing"].add(2, "Recovery behavior is changing around timing-related signals", "timing", relationship_change=True)
    if {"energy_schedule", "thermal_control"} <= categories:
        scores["energy_schedule"].add(2, "Energy/schedule and thermal response became less consistent", "energy", relationship_change=True)


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
            sensor_score.add(1.5, readable_warning(warning), "telemetry")
    for profile in numeric_profiles:
        if profile.get("missing_count", 0) > 0:
            sensor_score.add(
                1.5,
                f"{profile['column']} has missing readings",
                "telemetry",
            )
    if baseline_analysis.get("warnings"):
        for warning in baseline_analysis["warnings"]:
            if mentions_any(warning, ["missing", "not enough", "numeric"]):
                sensor_score.add(1, readable_warning(warning), "telemetry")
    if cultivation_mapping.get("unknown_column_count", 0) > 0:
        sensor_score.add(0.75, "Some source columns are not mapped to generic signal categories", "telemetry")


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
        "humidity": "moisture_control",
        "thermal": "thermal_control",
        "flow": "flow_restriction",
        "chemical": "process_timing",
        "energy": "energy_schedule",
        "timing": "process_timing",
        "location": "sensor_network",
        "temperature": "thermal_control",
        "HVAC": "thermal_control",
        "airflow": "flow_restriction",
        "irrigation": "process_timing",
        "lighting": "energy_schedule",
        "sensor network": "sensor_network",
    }.get(source_category, "unknown_system_drift")


def has_related_column(column_to_category: dict[str, str], source_category: str) -> bool:
    return any(category == source_category for category in column_to_category.values())


def signal_name_for_category(category: str) -> str:
    return {
        "moisture_control": "moisture",
        "thermal_control": "thermal",
        "flow_restriction": "flow",
        "process_timing": "timing",
        "energy_schedule": "energy",
        "sensor_network": "sensor network",
    }.get(category, "telemetry")


def evidence_for_drift(category: str, column: str, persistent: bool) -> str:
    base = {
        "moisture_control": "Moisture behavior moved away from baseline",
        "thermal_control": "Thermal behavior moved away from baseline",
        "flow_restriction": "Flow behavior moved away from baseline",
        "process_timing": "Process timing behavior moved away from baseline",
        "energy_schedule": "Energy/schedule-related readings moved away from baseline",
        "sensor_network": "Sensor readings moved away from expected continuity",
    }.get(category, f"{column} moved away from baseline")
    if persistent:
        return f"{base} and persisted across recent readings"
    return base


def relationship_evidence(columns: list[str]) -> str:
    if len(columns) >= 2:
        return relationship_evidence_sentence(columns[0], columns[1])
    return "Signal coupling is less consistent than the recent baseline"


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
