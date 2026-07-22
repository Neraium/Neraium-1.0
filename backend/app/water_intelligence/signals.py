from __future__ import annotations

import re
from typing import Any

from app.water_intelligence.models import SignalMatch
from app.water_intelligence.units import infer_unit_from_header, normalize_unit


SIGNAL_MEANING: dict[str, dict[str, Any]] = {
    "flow": {"dimension": "flow", "meaning": "Water flow rate through the relevant loop or asset."},
    "differential_pressure": {"dimension": "pressure", "meaning": "Pressure gain or pressure drop across a pump, coil, filter, or loop section."},
    "pump_power": {"dimension": "power", "meaning": "Electrical input to a pump, motor, or drive; not hydraulic output."},
    "pump_current": {"dimension": None, "meaning": "Pump motor current; supporting electrical input context."},
    "pump_speed": {"dimension": "frequency", "meaning": "Pump or VFD speed/frequency context."},
    "valve_position": {"dimension": "fraction", "meaning": "Valve command or position that can alter hydraulic resistance."},
    "bypass_state": {"dimension": None, "meaning": "Bypass or recirculation state."},
    "pump_stage": {"dimension": None, "meaning": "Pump staging or count of active pumps."},
    "operating_mode": {"dimension": None, "meaning": "Water-system operating mode or control state."},
    "supply_temperature": {"dimension": "temperature", "meaning": "Chilled-water supply temperature at the relevant location."},
    "return_temperature": {"dimension": "temperature", "meaning": "Chilled-water return temperature at the relevant location."},
    "delta_t": {"dimension": "temperature_difference", "meaning": "Temperature difference between return and supply water."},
    "thermal_load": {"dimension": "power", "meaning": "Thermal load or heat transfer rate."},
    "chiller_power": {"dimension": "power", "meaning": "Chiller electrical or compressor power input."},
    "filter_differential_pressure": {"dimension": "pressure", "meaning": "Differential pressure across a filter or strainer."},
    "filter_mode": {"dimension": None, "meaning": "Filter operating mode such as filtering, bypass, backwash, or maintenance."},
    "backwash_event": {"dimension": None, "meaning": "Backwash or maintenance event affecting filter state."},
    "makeup_flow": {"dimension": "flow", "meaning": "Cooling tower makeup water flow."},
    "evaporation_flow": {"dimension": "flow", "meaning": "Measured evaporation flow or loss term."},
    "blowdown_flow": {"dimension": "flow", "meaning": "Measured tower blowdown or bleed flow."},
    "drift_flow": {"dimension": "flow", "meaning": "Measured drift loss."},
    "leak_flow": {"dimension": "flow", "meaning": "Measured leakage or abnormal loss."},
    "overflow_flow": {"dimension": "flow", "meaning": "Measured overflow loss."},
    "storage_change": {"dimension": "flow", "meaning": "Rate-equivalent tower basin or system storage change."},
    "basin_level": {"dimension": "level", "meaning": "Cooling tower basin level."},
    "makeup_conductivity": {"dimension": "conductivity", "meaning": "Conductivity of makeup water used as tracer context."},
    "circulating_conductivity": {"dimension": "conductivity", "meaning": "Conductivity of circulating tower water."},
    "chemical_feed_pump": {"dimension": None, "meaning": "Chemical feed pump state; context for conductivity tracer validity."},
}


PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("filter_differential_pressure", (r"filter.*(dp|differential.*pressure|delta.*p)", r"(dp|differential.*pressure|delta.*p).*filter", r"strainer.*(dp|differential.*pressure)")),
    ("differential_pressure", (r"(differential.*pressure|delta.*p|dp|head).*pump", r"pump.*(differential.*pressure|delta.*p|dp|head)", r"pressure.*rise", r"discharge.*pressure", r"loop.*dp", r"chw.*dp")),
    ("makeup_flow", (r"makeup.*(flow|rate|gpm)", r"make_up.*(flow|rate|gpm)", r"fill.*(flow|rate)", r"tower.*makeup.*(flow|rate|gpm)")),
    ("blowdown_flow", (r"blowdown.*(flow|rate|gpm)", r"bleed.*(flow|rate|gpm)")),
    ("evaporation_flow", (r"evap.*(flow|rate|loss)",)),
    ("drift_flow", (r"drift.*(flow|rate|loss)",)),
    ("leak_flow", (r"leak.*(flow|rate|loss)",)),
    ("overflow_flow", (r"overflow.*(flow|rate|loss)",)),
    ("storage_change", (r"storage.*(change|rate)", r"basin.*level.*rate", r"level.*change")),
    ("makeup_conductivity", (r"makeup.*conduct", r"make_up.*conduct", r"source.*conduct")),
    ("circulating_conductivity", (r"circulat.*conduct", r"tower.*conduct", r"basin.*conduct", r"cw.*conduct")),
    ("chemical_feed_pump", (r"chemical.*feed.*(pump|status|run)", r"feed.*pump", r"treatment.*feed")),
    ("supply_temperature", (r"(chw|chilled.*water).*supply.*temp", r"supply.*temp.*(chw|chilled.*water)", r"chws")),
    ("return_temperature", (r"(chw|chilled.*water).*return.*temp", r"return.*temp.*(chw|chilled.*water)", r"chwr")),
    ("delta_t", (r"(delta|delt|dt).*t", r"delta_t", r"chw.*delt", r"temperature.*difference")),
    ("thermal_load", (r"thermal.*load", r"cooling.*load", r"tons", r"btu", r"load.*kw")),
    ("chiller_power", (r"chiller.*(power|kw|load)", r"compressor.*(power|kw)", r"chiller.*ton")),
    ("pump_power", (r"pump.*(power|kw|kilowatt|hp)", r"(power|kw|kilowatt|hp).*pump")),
    ("pump_current", (r"pump.*(amp|amps|current)", r"(amp|amps|current).*pump")),
    ("pump_speed", (r"pump.*(speed|vfd|frequency|hz|rpm)", r"(speed|vfd|frequency|hz|rpm).*pump")),
    ("pump_stage", (r"pump.*(stage|staging|count|lead|lag)", r"active.*pump")),
    ("valve_position", (r"valve.*(position|pct|percent|command|cmd|open)", r"(position|command).*valve")),
    ("bypass_state", (r"bypass", r"recirc", r"recirculation")),
    ("filter_mode", (r"filter.*mode", r"backwash.*mode", r"maintenance.*mode")),
    ("backwash_event", (r"backwash", r"filter.*maintenance", r"media.*wash")),
    ("basin_level", (r"basin.*level", r"tower.*level", r"sump.*level")),
    ("operating_mode", (r"operating.*mode", r"mode$", r"state$", r"status$")),
    ("flow", (r"(flow|flow_rate|gpm|lpm)",)),
)


def normalize_name(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def signal_for_column(column: str, metadata: dict[str, Any] | None = None) -> str | None:
    metadata = metadata if isinstance(metadata, dict) else {}
    candidates = " ".join(
        str(metadata.get(key) or "")
        for key in ("source_column", "original_header", "normalized_name", "display_name", "tag_name")
    )
    text = f"{column} {candidates}"
    normalized = normalize_name(text)
    for canonical, patterns in PATTERNS:
        if any(re.search(pattern, normalized) for pattern in patterns):
            return canonical
    return None


def match_water_signals(
    *,
    columns: list[str],
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
    required_dimensions: dict[str, str | None] | None = None,
) -> dict[str, list[SignalMatch]]:
    catalog = _catalog_by_column(telemetry_signal_catalog)
    required_dimensions = required_dimensions or {}
    matches: dict[str, list[SignalMatch]] = {}
    for column in columns:
        metadata = catalog.get(str(column), {})
        canonical = signal_for_column(column, metadata)
        if not canonical:
            continue
        meaning = SIGNAL_MEANING.get(canonical, {}).get("meaning", f"{canonical} signal")
        expected_dimension = required_dimensions.get(canonical, SIGNAL_MEANING.get(canonical, {}).get("dimension"))
        source_unit = (
            metadata.get("engineering_units")
            or metadata.get("unit")
            or infer_unit_from_header(metadata.get("original_header") or column)
        )
        unit_status = normalize_unit(source_unit=source_unit, expected_dimension=expected_dimension)
        display_name = str(metadata.get("display_name") or metadata.get("original_header") or column)
        match = SignalMatch(
            canonical=canonical,
            source_column=str(column),
            display_name=display_name,
            source_unit=unit_status.get("source_unit"),
            normalized_unit=unit_status.get("normalized_unit"),
            unit_dimension=expected_dimension,
            conversion_applied=unit_status.get("conversion_applied"),
            unit_status=unit_status.get("status", "unknown"),
            meaning=meaning,
            metadata=dict(metadata),
        )
        matches.setdefault(canonical, []).append(match)
    return matches


def best_signal(matches: dict[str, list[SignalMatch]], canonical: str) -> SignalMatch | None:
    options = matches.get(canonical) or []
    if not options:
        return None
    return sorted(options, key=lambda item: (item.unit_status != "ok", len(item.source_column)))[0]


def columns_for_signals(matches: dict[str, list[SignalMatch]], signals: set[str]) -> set[str]:
    return {
        match.source_column
        for signal in signals
        for match in matches.get(signal, [])
    }


def _catalog_by_column(telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    if isinstance(telemetry_signal_catalog, dict):
        return {str(key): value for key, value in telemetry_signal_catalog.items() if isinstance(value, dict)}
    if isinstance(telemetry_signal_catalog, list):
        return {
            str(item.get("source_column") or item.get("column") or item.get("tag_name")): item
            for item in telemetry_signal_catalog
            if isinstance(item, dict) and (item.get("source_column") or item.get("column") or item.get("tag_name"))
        }
    return {}
