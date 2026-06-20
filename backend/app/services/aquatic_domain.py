from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
import random
from typing import Any


AQUATIC_TELEMETRY_SIGNALS = [
    "orp",
    "ph",
    "pool_temperature",
    "spa_temperature",
    "flow_rate",
    "filter_pressure",
    "pump_amperage",
    "pump_runtime",
    "heater_runtime",
    "sanitizer_feed_rate",
    "water_level",
    "valve_states",
    "occupancy_estimate",
    "ambient_temperature",
    "turbidity",
    "conductivity",
    "free_chlorine",
    "makeup_water_flow",
    "differential_pressure",
    "supply_temperature",
    "return_temperature",
    "loop_delta_t",
    "chiller_load",
    "tower_fan_speed",
    "basin_temperature",
    "blowdown_rate",
]

AQUATIC_SIGNAL_ALIASES = {
    "orp": ("orp", "oxidation_reduction", "oxidation-reduction", "sanitizer_potential"),
    "ph": ("ph", "acidity"),
    "pool_temperature": ("pool_temp", "pool_temperature", "pool water temp"),
    "spa_temperature": ("spa_temp", "spa_temperature", "spa water temp", "hot_tub_temp"),
    "flow_rate": ("flow", "flow_rate", "flow rate", "gpm", "lpm"),
    "filter_pressure": ("filter_pressure", "pressure_filter", "delta_p"),
    "pump_amperage": ("pump_amp", "pump_amperage", "motor_current", "amps"),
    "pump_runtime": ("pump_runtime", "runtime_pump", "pump_hours"),
    "heater_runtime": ("heater_runtime", "runtime_heater", "heater_hours"),
    "sanitizer_feed_rate": ("sanitizer_feed", "chlorine_feed", "feed_rate"),
    "water_level": ("water_level", "level", "sump_level"),
    "valve_states": ("valve_state", "valve_position", "valve_states"),
    "occupancy_estimate": ("occupancy", "bather_load", "occupancy_estimate"),
    "ambient_temperature": ("ambient_temp", "ambient_temperature", "outside_temp"),
    "turbidity": ("turbidity", "ntu", "clarity"),
    "conductivity": ("conductivity", "tds", "specific_conductance"),
    "free_chlorine": ("free_chlorine", "chlorine", "chlorine_ppm", "fac"),
    "makeup_water_flow": ("makeup_water", "makeup_water_flow", "fill_flow", "refill_rate"),
    "differential_pressure": ("differential_pressure", "differential_pressure_psi", "dp", "delta_pressure"),
    "supply_temperature": ("supply_temp", "supply_temperature", "chilled_water_supply_temp", "chw_supply_temp"),
    "return_temperature": ("return_temp", "return_temperature", "chilled_water_return_temp", "chw_return_temp"),
    "loop_delta_t": ("delta_t", "loop_delta_t", "chw_delta_t", "approach_temp"),
    "chiller_load": ("chiller_load", "chiller_load_pct", "compressor_power", "compressor_power_kw"),
    "tower_fan_speed": ("tower_fan_speed", "fan_speed", "fan_vfd", "fan_vfd_frequency"),
    "basin_temperature": ("basin_temp", "basin_temperature", "condenser_water_temp", "tower_basin_temp"),
    "blowdown_rate": ("blowdown", "blowdown_rate", "bleed_rate", "cycles_of_concentration"),
}

INTEGRATION_STUBS = [
    {"name": "Pentair", "connector_type": "pentair", "mode": "adapter_stub", "read_only": True},
    {"name": "Hayward", "connector_type": "hayward", "mode": "adapter_stub", "read_only": True},
    {"name": "MQTT", "connector_type": "mqtt", "mode": "adapter_stub", "read_only": True},
    {"name": "Modbus", "connector_type": "modbus", "mode": "adapter_stub", "read_only": True},
    {"name": "Node-RED", "connector_type": "nodered", "mode": "adapter_stub", "read_only": True},
    {"name": "REST ingestion", "connector_type": "rest", "mode": "active", "read_only": True},
    {"name": "BAS/BMS", "connector_type": "bas_bms", "mode": "adapter_stub", "read_only": True},
]


@dataclass
class _Rule:
    archetype: str
    subsystem: str
    signals: tuple[str, ...]
    summary: str


RULES = [
    _Rule("circulation degradation", "circulation loop", ("flow_rate", "pump_amperage", "filter_pressure"), "Flow response is decoupling from pump electrical load and pressure pattern."),
    _Rule("filter restriction buildup", "filtration", ("filter_pressure", "flow_rate"), "Filter pressure trend is rising while effective flow trend softens."),
    _Rule("pump cavitation", "pump train", ("pump_amperage", "flow_rate", "water_level"), "Pump electrical behavior diverges from delivered flow with unstable level support."),
    _Rule("abnormal thermal drift", "thermal control", ("pool_temperature", "spa_temperature", "ambient_temperature"), "Water temperature response diverges from ambient and reciprocal basin behavior."),
    _Rule("heater efficiency degradation", "heating subsystem", ("heater_runtime", "pool_temperature", "spa_temperature"), "Heater runtime is rising without proportional water temperature response."),
    _Rule("orp instability", "water chemistry", ("orp", "ph", "sanitizer_feed_rate"), "ORP relationship with pH and feed response is unstable."),
    _Rule("chemical feed inconsistencies", "chemical dosing", ("sanitizer_feed_rate", "orp", "ph"), "Feed activity and chemistry response are intermittently decoupled."),
    _Rule("water treatment instability", "water treatment", ("orp", "ph", "free_chlorine", "turbidity", "conductivity"), "Treatment response is drifting across sanitizer, clarity, and dissolved solids signals."),
    _Rule("abnormal overnight heat loss", "thermal envelope", ("pool_temperature", "ambient_temperature", "heater_runtime"), "Overnight cooling exceeds expected ambient-coupled profile."),
    _Rule("low-flow conditions", "circulation loop", ("flow_rate", "filter_pressure", "valve_states"), "Observed flow is structurally low relative to pressure/valve relation."),
    _Rule("pressure instability", "filtration", ("filter_pressure", "flow_rate", "pump_runtime"), "Pressure regime is oscillatory relative to steady runtime conditions."),
    _Rule("dead-zone circulation patterns", "hydraulic distribution", ("flow_rate", "valve_states", "occupancy_estimate"), "Circulation signatures imply uneven distribution under load."),
    _Rule("makeup water abnormality", "resort water system", ("makeup_water_flow", "water_level", "flow_rate"), "Makeup-water behavior is no longer aligned with level recovery and circulation demand."),
    _Rule("chilled water delta-t degradation", "chilled water loop", ("supply_temperature", "return_temperature", "loop_delta_t", "flow_rate"), "Chilled-water temperature split is degrading relative to loop flow."),
    _Rule("chiller hydraulic mismatch", "chilled water loop", ("chiller_load", "flow_rate", "differential_pressure", "loop_delta_t"), "Chiller load, pump hydraulics, and thermal pickup are no longer moving together."),
    _Rule("cooling tower approach drift", "cooling tower", ("basin_temperature", "tower_fan_speed", "ambient_temperature", "blowdown_rate"), "Tower heat rejection response is drifting against fan effort, ambient load, and water management."),
    _Rule("sensor disagreement anomalies", "sensor network", ("orp", "ph", "flow_rate", "pump_runtime"), "Independent sensors disagree in a persistent way."),
]


def normalize_signal_name(column: str) -> str:
    raw = str(column or "").strip().lower().replace("-", "_").replace(" ", "_")
    for canonical, aliases in AQUATIC_SIGNAL_ALIASES.items():
        if raw == canonical or raw in aliases:
            return canonical
    return raw


def map_aquatic_schema(columns: list[str]) -> dict[str, Any]:
    mapped: dict[str, list[str]] = {signal: [] for signal in AQUATIC_TELEMETRY_SIGNALS}
    unknown: list[str] = []
    for column in columns:
        normalized = normalize_signal_name(column)
        if normalized in mapped:
            mapped[normalized].append(column)
        else:
            unknown.append(column)
    mapped_count = sum(len(items) for items in mapped.values())
    return {
        "schema_type": "commercial_aquatic_v1",
        "required_signals": AQUATIC_TELEMETRY_SIGNALS,
        "mapped_signals": mapped,
        "mapped_column_count": mapped_count,
        "coverage_ratio": round(mapped_count / max(1, len(columns)), 4),
        "unknown_columns": unknown,
    }


def generate_aquatic_simulated_telemetry(*, intervals: int = 96, seed: int = 7) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    base_time = datetime.now(UTC) - timedelta(minutes=15 * intervals)
    rows: list[dict[str, Any]] = []
    for i in range(intervals):
        hour = (i * 0.25) % 24
        daytime = max(0.0, math.sin((hour - 6) / 24 * math.pi * 2))
        overnight = 1.0 - daytime
        occupancy = max(2.0, 15 + 120 * daytime + rng.uniform(-8, 8))
        vegas_heat = 0.8 + 0.45 * daytime
        drift = i / max(1, intervals)
        rows.append(
            {
                "timestamp": (base_time + timedelta(minutes=i * 15)).isoformat(),
                "orp": round(700 + 45 * daytime - 35 * drift + rng.uniform(-18, 18), 2),
                "ph": round(7.4 + 0.08 * overnight + 0.05 * drift + rng.uniform(-0.04, 0.04), 3),
                "pool_temperature": round(82 + 1.8 * daytime * vegas_heat - 1.4 * overnight + rng.uniform(-0.3, 0.3), 2),
                "spa_temperature": round(100 + 1.1 * daytime - 0.5 * overnight + rng.uniform(-0.25, 0.25), 2),
                "flow_rate": round(530 + 90 * daytime - 50 * drift + rng.uniform(-14, 14), 2),
                "filter_pressure": round(16 + 0.7 * daytime + 3.6 * drift + rng.uniform(-0.4, 0.5), 2),
                "pump_amperage": round(23 + 3.1 * daytime + 0.9 * drift + rng.uniform(-0.5, 0.5), 2),
                "pump_runtime": round(8 + 3.5 * daytime, 2),
                "heater_runtime": round(3 + 1.6 * overnight + 1.2 * drift + rng.uniform(-0.2, 0.2), 2),
                "sanitizer_feed_rate": round(1.4 + 0.55 * daytime + rng.uniform(-0.08, 0.08), 3),
                "water_level": round(61.5 - 0.8 * daytime + rng.uniform(-0.12, 0.12), 2),
                "valve_states": "recirc" if i % 10 else "backwash",
                "occupancy_estimate": round(occupancy, 1),
                "ambient_temperature": round(84 + 14 * daytime * vegas_heat - 5 * overnight + rng.uniform(-1.0, 1.0), 2),
            }
        )
    return rows


def build_aquatic_replay_dataset(*, intervals: int = 96) -> dict[str, Any]:
    rows = generate_aquatic_simulated_telemetry(intervals=intervals)
    return {
        "meta": {
            "domain": "commercial_aquatic_hospitality",
            "intervals": intervals,
            "cadence": "15m",
            "read_only": True,
            "actuation": False,
        },
        "rows": rows,
        "relationship_map": relationship_map(),
    }


def relationship_map() -> list[dict[str, Any]]:
    return [
        {"source": "occupancy_estimate", "target": "sanitizer_feed_rate", "relationship": "load_response"},
        {"source": "sanitizer_feed_rate", "target": "orp", "relationship": "chemistry_response"},
        {"source": "ph", "target": "orp", "relationship": "chemical_coupling"},
        {"source": "pump_amperage", "target": "flow_rate", "relationship": "electro_hydraulic"},
        {"source": "flow_rate", "target": "filter_pressure", "relationship": "hydraulic_resistance"},
        {"source": "heater_runtime", "target": "pool_temperature", "relationship": "thermal_response"},
        {"source": "ambient_temperature", "target": "pool_temperature", "relationship": "environmental_load"},
        {"source": "makeup_water_flow", "target": "water_level", "relationship": "makeup_recovery"},
        {"source": "supply_temperature", "target": "return_temperature", "relationship": "chilled_water_delta_t"},
        {"source": "chiller_load", "target": "loop_delta_t", "relationship": "thermal_load_response"},
        {"source": "tower_fan_speed", "target": "basin_temperature", "relationship": "heat_rejection_response"},
    ]


def analyze_aquatic_instability(
    *,
    columns: list[str],
    baseline_analysis: dict[str, Any],
    engine_result: dict[str, Any],
) -> dict[str, Any]:
    normalized_columns = {normalize_signal_name(c) for c in columns}
    drift_by_signal = {normalize_signal_name(item.get("column")): item for item in baseline_analysis.get("column_drift", []) if isinstance(item, dict)}
    persistent = {normalize_signal_name(c) for c in (engine_result.get("persistence_assessment", {}) or {}).get("persistent_columns", [])}
    relationship_count = len([e for e in engine_result.get("evidence", []) if isinstance(e, dict) and e.get("type") == "relationship_change"])
    corroboration = (engine_result.get("system_evidence", {}) or {}).get("corroboration_level", "limited")

    candidates: list[dict[str, Any]] = []
    for rule in RULES:
        available = [s for s in rule.signals if s in normalized_columns]
        if len(available) < 2:
            continue
        drift_hits = [s for s in available if s in drift_by_signal and drift_by_signal[s].get("drift_flag") in {"watch", "review"}]
        persistence_hits = [s for s in available if s in persistent]
        support_score = len(drift_hits) * 0.5 + len(persistence_hits) * 0.4 + (0.25 if relationship_count > 0 else 0.0) + (0.25 if corroboration in {"moderate", "strong"} else 0.0)
        if support_score < 1.4:
            continue
        confidence = min(0.94, 0.42 + support_score * 0.17)
        contributing_signals = sorted(set(drift_hits + persistence_hits))
        if len(contributing_signals) < 2 and len(available) >= 2 and (relationship_count > 0 or corroboration in {"moderate", "strong"}):
            for signal in available:
                if signal not in contributing_signals:
                    contributing_signals.append(signal)
                if len(contributing_signals) >= 2:
                    break
        candidates.append(
            {
                "archetype": rule.archetype,
                "subsystem": rule.subsystem,
                "contributing_signals": contributing_signals,
                "relationship_explanation": rule.summary,
                "confidence_persistence_score": round(confidence, 3),
                "severity_trajectory": "escalating" if len(persistence_hits) >= 2 else "monitoring",
                "timeline": "persistent multi-window relationship drift",
            }
        )

    admitted = [c for c in candidates if c["confidence_persistence_score"] >= 0.62 and len(c["contributing_signals"]) >= 2]
    signals = [
        {
            "type": "aquatic_relationship_instability",
            "level": "review" if item["confidence_persistence_score"] < 0.76 else "elevated",
            "columns": item["contributing_signals"],
            "message": f"{item['archetype']} pattern is persistent with multi-signal corroboration.",
        }
        for item in admitted[:4]
    ]
    evidence = [
        {
            "type": "aquatic_instability_archetype",
            "archetype": item["archetype"],
            "subsystem": item["subsystem"],
            "contributing_signals": item["contributing_signals"],
            "confidence_persistence_score": item["confidence_persistence_score"],
            "severity_trajectory": item["severity_trajectory"],
            "relationship_explanation": item["relationship_explanation"],
            "timeline": item["timeline"],
            "evidence_graph": relationship_map(),
        }
        for item in admitted[:4]
    ]
    return {
        "domain": "commercial_aquatic_hospitality",
        "schema": map_aquatic_schema(columns),
        "relationship_map": relationship_map(),
        "admitted_candidates": admitted[:4],
        "signals": signals,
        "evidence": evidence,
        "recommended_checks": [
            "Confirm persistent relationship drift across pool, spa, chilled-water, and circulation windows.",
            "Validate treatment, hydraulic, and thermal coupling during high-load operating periods.",
        ] if admitted else [],
        "integration_stubs": INTEGRATION_STUBS,
        "governance_boundary": {
            "read_only": True,
            "autonomous_control": False,
            "operator_authority_preserved": True,
        },
    }
