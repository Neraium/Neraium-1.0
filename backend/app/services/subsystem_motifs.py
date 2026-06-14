from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.aquatic_domain import normalize_signal_name


@dataclass(frozen=True)
class SubsystemMotif:
    profile: str
    driver_category: str
    title: str
    primary_phrase: str
    primary_signals: tuple[str, ...]
    secondary_families: tuple[tuple[str, str, tuple[str, ...]], ...]
    next_operator_move: str
    confidence_basis: str
    base_evidence: tuple[str, ...]


MOTIFS: tuple[SubsystemMotif, ...] = (
    SubsystemMotif(
        profile="pool_hottub_systems",
        driver_category="aquatic_circulation_infrastructure",
        title="Pool circulation system drift",
        primary_phrase="circulation system drift",
        primary_signals=("flow_rate", "filter_pressure", "pump_runtime", "pump_amperage", "circulation_pump_runtime", "pressure", "water_pressure"),
        secondary_families=(
            ("makeup", "makeup-water demand increase", ("water_level", "makeup_water", "makeup_water_flow", "fill_valve", "tank_level", "level")),
            ("thermal", "heater runtime divergence", ("heater_runtime", "pool_temperature", "spa_temperature", "pool_water_temp", "spa_water_temp")),
        ),
        next_operator_move="Inspect circulation hydraulics, confirm makeup-water demand, and compare heater runtime against turnover recovery.",
        confidence_basis="Multi-family pool infrastructure evidence aligned across circulation, persistence, and corroborating relationship changes.",
        base_evidence=(
            "Circulation-side signals are moving together rather than as an isolated sensor excursion.",
        ),
    ),
    SubsystemMotif(
        profile="hvac_systems",
        driver_category="hvac_air_distribution_infrastructure",
        title="Air distribution system drift",
        primary_phrase="air-distribution system drift",
        primary_signals=("supply_temp", "return_temp", "static_pressure", "compressor_runtime", "air_handler_status", "compressor", "pressure"),
        secondary_families=(
            ("thermal", "supply-return thermal split divergence", ("supply_temp", "return_temp", "temp_air", "temperature")),
            ("runtime", "compressor runtime divergence", ("compressor_runtime", "hvac_runtime", "dehu_runtime", "cycle", "runtime")),
        ),
        next_operator_move="Inspect air-handler delivery, compare supply-return split, and review compressor/runtime loading against static-pressure response.",
        confidence_basis="Multi-family HVAC evidence aligned across air delivery, thermal split, and runtime corroboration.",
        base_evidence=(
            "Air-distribution signals are drifting together rather than as a single-point sensor change.",
        ),
    ),
    SubsystemMotif(
        profile="utility_infrastructure",
        driver_category="utility_distribution_infrastructure",
        title="Utility distribution system drift",
        primary_phrase="utility-distribution system drift",
        primary_signals=("distribution_pressure", "pump_station_output", "water_pressure", "flow_rate", "pump_amperage"),
        secondary_families=(
            ("storage", "reservoir refill divergence", ("reservoir_refill_rate", "tank_level", "reservoir", "level")),
            ("loss", "leak or downstream demand divergence", ("leak_detection_indicator", "leak_detection", "sewer_flow", "treatment_plant_flow")),
        ),
        next_operator_move="Inspect distribution pressure, compare reservoir refill behavior, and confirm whether leak or downstream demand signals are widening.",
        confidence_basis="Multi-family utility evidence aligned across distribution pressure, storage response, and downstream-demand corroboration.",
        base_evidence=(
            "Distribution-side signals are moving together rather than as an isolated sensor excursion.",
        ),
    ),
)


def analyze_subsystem_motifs(
    *,
    telemetry_context: dict[str, Any],
    baseline_analysis: dict[str, Any],
    engine_result: dict[str, Any],
) -> dict[str, Any] | None:
    profile = resolved_profile(telemetry_context)
    if not profile:
        return None

    motif = next((item for item in MOTIFS if item.profile == profile), None)
    if motif is None:
        return None

    active_columns = active_columns_from_evidence(baseline_analysis=baseline_analysis, engine_result=engine_result)
    primary_hits = active_columns & set(motif.primary_signals)
    if not primary_hits:
        return None

    corroboration_level = str((engine_result.get("system_evidence") or {}).get("corroboration_level") or "limited").lower()
    relationship_count = len([item for item in (engine_result.get("evidence") or []) if item.get("type") == "relationship_change"])
    persistent_columns = {
        normalize_signal_name(column)
        for column in (engine_result.get("persistence_assessment", {}) or {}).get("persistent_columns", [])
        if column
    }

    matched_secondaries: list[tuple[str, str, set[str]]] = []
    for family_name, phrase, signals in motif.secondary_families:
        family_hits = active_columns & set(signals)
        if family_hits:
            matched_secondaries.append((family_name, phrase, family_hits))

    persistent_family_count = int(bool(primary_hits & persistent_columns)) + sum(
        1 for _family, _phrase, hits in matched_secondaries if hits & persistent_columns
    )
    if len(matched_secondaries) == 0:
        return None
    if corroboration_level not in {"moderate", "strong"} and relationship_count == 0:
        return None
    if persistent_family_count == 0 and corroboration_level != "strong":
        return None

    likely_driver = motif.title
    secondary_phrases = [phrase for _family, phrase, _hits in matched_secondaries[:2]]
    if secondary_phrases:
        likely_driver = f"{likely_driver} coincides with {' and '.join(secondary_phrases)}."
    else:
        likely_driver = f"{likely_driver} is showing multi-signal infrastructure divergence."

    supporting_evidence = list(motif.base_evidence)
    for family_name, _phrase, _hits in matched_secondaries:
        if family_name == "makeup":
            supporting_evidence.append("Water-level related behavior suggests rising makeup-water demand alongside the circulation change.")
        elif family_name == "thermal":
            supporting_evidence.append("Heater runtime is diverging from expected pool/spa thermal response.")
        elif family_name == "runtime":
            supporting_evidence.append("Runtime behavior is diverging from expected thermal and pressure recovery.")
        elif family_name == "storage":
            supporting_evidence.append("Storage-side behavior is diverging from expected distribution recovery.")
        elif family_name == "loss":
            supporting_evidence.append("Leak or downstream-demand indicators are widening alongside the distribution shift.")
    if relationship_count > 0:
        supporting_evidence.append("Relationship-change evidence links the affected signals into one infrastructure pattern.")

    confidence = "high" if corroboration_level == "strong" and persistent_family_count >= 2 else "medium"
    severity = "action" if corroboration_level == "strong" and persistent_family_count >= 2 else "review"
    return {
        "driver_category": motif.driver_category,
        "likely_driver": likely_driver,
        "contributing_signals": sorted(primary_hits | set().union(*(hits for _family, _phrase, hits in matched_secondaries))),
        "supporting_evidence": supporting_evidence[:4],
        "confidence_basis": motif.confidence_basis,
        "next_operator_move": motif.next_operator_move,
        "severity": severity,
        "attribution_confidence": confidence,
    }


def active_columns_from_evidence(*, baseline_analysis: dict[str, Any], engine_result: dict[str, Any]) -> set[str]:
    persistent_columns = {
        normalize_signal_name(column)
        for column in (engine_result.get("persistence_assessment", {}) or {}).get("persistent_columns", [])
        if column
    }
    relationship_columns = {
        normalize_signal_name(column)
        for item in (engine_result.get("evidence") or [])
        if item.get("type") == "relationship_change"
        for column in (item.get("columns") or [])
    }
    drift_columns = {
        normalize_signal_name(item.get("column"))
        for item in (baseline_analysis.get("column_drift") or [])
        if item.get("drift_flag") in {"watch", "review"} and item.get("column")
    }
    return persistent_columns | relationship_columns | drift_columns


def resolved_profile(telemetry_context: dict[str, Any]) -> str:
    telemetry_profile = str(telemetry_context.get("telemetry_profile") or "").lower()
    operational_profile = str(telemetry_context.get("operational_signal_profile") or "").lower()
    if telemetry_profile in {"pool_hottub_systems", "hvac_systems"}:
        return telemetry_profile
    if operational_profile == "utility_infrastructure":
        return operational_profile
    return ""
