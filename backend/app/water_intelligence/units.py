from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class UnitDefinition:
    canonical: str
    dimension: str
    normalized_unit: str
    to_normalized: Callable[[float], float]
    conversion: str
    aliases: tuple[str, ...]


def _same(value: float) -> float:
    return value


UNIT_DEFINITIONS: tuple[UnitDefinition, ...] = (
    UnitDefinition("gpm", "flow", "gpm", _same, "identity", ("gpm", "gal/min", "gallon/min", "gallons/minute")),
    UnitDefinition("lpm", "flow", "gpm", lambda v: v * 0.264172052, "lpm_to_gpm", ("lpm", "l/min", "liter/min", "liters/minute")),
    UnitDefinition("lps", "flow", "gpm", lambda v: v * 15.850323141, "lps_to_gpm", ("l/s", "lps", "liter/s", "liters/second")),
    UnitDefinition("m3h", "flow", "gpm", lambda v: v * 4.402867539, "m3h_to_gpm", ("m3/h", "m^3/h", "m3hr", "m3_per_hr", "m3_per_hour")),
    UnitDefinition("cfs", "flow", "gpm", lambda v: v * 448.8311688, "cfs_to_gpm", ("cfs", "ft3/s", "ft^3/s")),
    UnitDefinition("psi", "pressure", "psi", _same, "identity", ("psi", "psig")),
    UnitDefinition("kpa", "pressure", "psi", lambda v: v * 0.145037738, "kpa_to_psi", ("kpa", "kilopascal", "kilopascals")),
    UnitDefinition("pa", "pressure", "psi", lambda v: v * 0.000145037738, "pa_to_psi", ("pa", "pascal", "pascals")),
    UnitDefinition("bar", "pressure", "psi", lambda v: v * 14.5037738, "bar_to_psi", ("bar",)),
    UnitDefinition("inh2o", "pressure", "psi", lambda v: v * 0.0360912, "inh2o_to_psi", ("in_h2o", "inh2o", "inwc", "in.wc")),
    UnitDefinition("ft_h2o", "pressure", "psi", lambda v: v * 0.4335275, "ft_h2o_to_psi", ("ft_h2o", "ftwc", "feet_water")),
    UnitDefinition("f", "temperature", "degF", _same, "identity", ("f", "degf", "degree_f", "degrees_f", "fahrenheit")),
    UnitDefinition("c", "temperature", "degF", lambda v: (v * 9.0 / 5.0) + 32.0, "c_to_f", ("c", "degc", "degree_c", "degrees_c", "celsius")),
    UnitDefinition("k", "temperature", "degF", lambda v: ((v - 273.15) * 9.0 / 5.0) + 32.0, "k_to_f", ("k", "kelvin")),
    UnitDefinition("delta_f", "temperature_difference", "degF", _same, "identity", ("delta_f", "delt_f", "degf_delta", "f_delta")),
    UnitDefinition("delta_c", "temperature_difference", "degF", lambda v: v * 9.0 / 5.0, "delta_c_to_delta_f", ("delta_c", "delt_c", "degc_delta", "c_delta")),
    UnitDefinition("kw", "power", "kW", _same, "identity", ("kw", "kilowatt", "kilowatts")),
    UnitDefinition("w", "power", "kW", lambda v: v / 1000.0, "w_to_kw", ("w", "watt", "watts")),
    UnitDefinition("hp", "power", "kW", lambda v: v * 0.745699872, "hp_to_kw", ("hp", "horsepower")),
    UnitDefinition("kwh", "energy", "kWh", _same, "identity", ("kwh", "kilowatt_hour", "kilowatt-hours")),
    UnitDefinition("wh", "energy", "kWh", lambda v: v / 1000.0, "wh_to_kwh", ("wh", "watt_hour", "watt-hours")),
    UnitDefinition("us_cm", "conductivity", "uS/cm", _same, "identity", ("us/cm", "µs/cm", "uS/cm", "microsiemens/cm", "umho/cm")),
    UnitDefinition("ms_cm", "conductivity", "uS/cm", lambda v: v * 1000.0, "ms_cm_to_us_cm", ("ms/cm", "mS/cm", "millisiemens/cm")),
    UnitDefinition("percent", "fraction", "%", _same, "identity", ("%", "pct", "percent", "percentage")),
    UnitDefinition("fraction", "fraction", "%", lambda v: v * 100.0, "fraction_to_percent", ("fraction", "ratio")),
    UnitDefinition("ft", "level", "ft", _same, "identity", ("ft", "feet", "foot")),
    UnitDefinition("in", "level", "ft", lambda v: v / 12.0, "inch_to_ft", ("in", "inch", "inches")),
    UnitDefinition("m", "level", "ft", lambda v: v * 3.280839895, "m_to_ft", ("m", "meter", "meters")),
    UnitDefinition("gal", "volume", "gal", _same, "identity", ("gal", "gallon", "gallons")),
    UnitDefinition("l", "volume", "gal", lambda v: v * 0.264172052, "l_to_gal", ("l", "liter", "liters")),
    UnitDefinition("m3", "volume", "gal", lambda v: v * 264.172052, "m3_to_gal", ("m3", "m^3", "cubic_meter", "cubic_meters")),
    UnitDefinition("rpm", "speed", "rpm", _same, "identity", ("rpm", "rev/min")),
    UnitDefinition("hz", "frequency", "Hz", _same, "identity", ("hz", "hertz")),
)

UNIT_LOOKUP = {
    alias.lower().replace(" ", "").replace("_", ""): definition
    for definition in UNIT_DEFINITIONS
    for alias in (definition.canonical, *definition.aliases)
}

DIMENSION_COMPATIBILITY = {
    "differential_pressure": "pressure",
    "temperature_delta": "temperature_difference",
    "valve_position": "fraction",
}


def normalize_dimension(dimension: str | None) -> str | None:
    if not dimension:
        return None
    normalized = str(dimension).strip().lower()
    return DIMENSION_COMPATIBILITY.get(normalized, normalized)


def normalize_unit_label(unit: str | None) -> str:
    text = str(unit or "").strip()
    text = text.replace("°", "deg")
    text = text.replace("Δ", "delta_")
    return text


def unit_key(unit: str | None) -> str:
    return normalize_unit_label(unit).lower().replace(" ", "").replace("_", "")


def infer_unit_from_header(column: str) -> str | None:
    text = str(column or "")
    paren = re.search(r"\(([^)]+)\)", text)
    if paren:
        return paren.group(1).strip()
    normalized = re.sub(r"[^a-zA-Z0-9%]+", "_", text).strip("_").lower()
    suffixes = (
        "gpm",
        "lpm",
        "lps",
        "psi",
        "psig",
        "kpa",
        "pa",
        "bar",
        "f",
        "c",
        "kw",
        "w",
        "hp",
        "kwh",
        "wh",
        "us_cm",
        "ms_cm",
        "pct",
        "percent",
        "ft",
        "in",
        "m",
        "gal",
        "l",
        "rpm",
        "hz",
    )
    parts = normalized.split("_")
    for width in (2, 1):
        suffix = "_".join(parts[-width:])
        if suffix in suffixes:
            return suffix
    return None


def normalize_unit(
    *,
    value: float | None = None,
    source_unit: str | None,
    expected_dimension: str | None,
) -> dict[str, Any]:
    dimension = normalize_dimension(expected_dimension)
    clean_unit = normalize_unit_label(source_unit)
    if not dimension:
        return {
            "status": "not_required",
            "source_unit": clean_unit or None,
            "normalized_unit": None,
            "normalized_value": value,
            "conversion_applied": None,
            "reason": "No unit dimension is required for this signal.",
        }
    if not clean_unit:
        return {
            "status": "unknown",
            "source_unit": None,
            "normalized_unit": None,
            "normalized_value": value,
            "conversion_applied": None,
            "reason": f"No source unit was supplied for expected {dimension} signal.",
        }
    definition = UNIT_LOOKUP.get(unit_key(clean_unit))
    if definition is None:
        return {
            "status": "unknown",
            "source_unit": clean_unit,
            "normalized_unit": None,
            "normalized_value": value,
            "conversion_applied": None,
            "reason": f"Unit {clean_unit} is not registered in the centralized water unit system.",
        }
    if definition.dimension != dimension:
        return {
            "status": "incompatible",
            "source_unit": clean_unit,
            "normalized_unit": definition.normalized_unit,
            "normalized_value": None,
            "conversion_applied": None,
            "reason": f"Unit {clean_unit} has dimension {definition.dimension}, expected {dimension}.",
        }
    normalized_value = None
    if value is not None:
        try:
            numeric = float(value)
            normalized_value = definition.to_normalized(numeric) if math.isfinite(numeric) else None
        except (TypeError, ValueError, OverflowError):
            normalized_value = None
    return {
        "status": "ok",
        "source_unit": clean_unit,
        "normalized_unit": definition.normalized_unit,
        "normalized_value": normalized_value,
        "conversion_applied": definition.conversion,
        "reason": "Unit is compatible and normalized.",
    }


def accepted_units_for_dimension(dimension: str) -> tuple[str, ...]:
    normalized = normalize_dimension(dimension)
    units = [
        definition.canonical
        for definition in UNIT_DEFINITIONS
        if definition.dimension == normalized
    ]
    return tuple(dict.fromkeys(units))
