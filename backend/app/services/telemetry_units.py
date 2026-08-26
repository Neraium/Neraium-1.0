from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Callable

from app.water_intelligence.units import (
    UNIT_DEFINITIONS,
    UnitDefinition,
    normalize_dimension,
    normalize_unit_label,
    unit_key,
)


UNIT_NORMALIZATION_VERSION = "neraium.telemetry.units/v1"


@dataclass(frozen=True)
class UnitNormalizationResult:
    """A source-preserving, analysis-ready unit normalization decision."""

    status: str
    quality_state: str
    analysis_eligible: bool
    reason_code: str | None
    original_value: Any
    original_unit: str | None
    canonical_value: float | None
    canonical_unit: str | None
    dimension: str | None
    conversion_id: str | None
    conversion_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _SupportedUnit:
    token: str
    display: str
    definition: UnitDefinition
    from_base: Callable[[float], float]


def _definition(canonical: str) -> UnitDefinition:
    for definition in UNIT_DEFINITIONS:
        if definition.canonical == canonical:
            return definition
    raise RuntimeError(f"Missing water-intelligence unit definition: {canonical}")


_KPA_TO_PSI = _definition("kpa").to_normalized(1.0)
_LPS_TO_GPM = _definition("lps").to_normalized(1.0)


# V1 is intentionally narrow. The definitions and aliases come from the existing
# water-intelligence vocabulary, while the inverse functions make the approved
# mapping target explicit rather than forcing every signal into the older engine's
# preferred unit.
_SUPPORTED_UNITS: tuple[_SupportedUnit, ...] = (
    _SupportedUnit("f", "degF", _definition("f"), lambda value: value),
    _SupportedUnit("c", "degC", _definition("c"), lambda value: (value - 32.0) * 5.0 / 9.0),
    _SupportedUnit("psi", "psi", _definition("psi"), lambda value: value),
    _SupportedUnit("kpa", "kPa", _definition("kpa"), lambda value: value / _KPA_TO_PSI),
    _SupportedUnit("gpm", "gpm", _definition("gpm"), lambda value: value),
    _SupportedUnit("lps", "L/s", _definition("lps"), lambda value: value / _LPS_TO_GPM),
    _SupportedUnit("kw", "kW", _definition("kw"), lambda value: value),
    _SupportedUnit("w", "W", _definition("w"), lambda value: value * 1000.0),
    _SupportedUnit("percent", "%", _definition("percent"), lambda value: value),
    _SupportedUnit("fraction", "fraction", _definition("fraction"), lambda value: value / 100.0),
)


def _supported_lookup() -> dict[str, _SupportedUnit]:
    lookup: dict[str, _SupportedUnit] = {}
    for unit in _SUPPORTED_UNITS:
        for alias in (unit.definition.canonical, *unit.definition.aliases, unit.display):
            lookup[unit_key(alias)] = unit
    return lookup


_SUPPORTED_LOOKUP = _supported_lookup()


def supported_units_for_dimension(dimension: str) -> tuple[str, ...]:
    """Return the deliberate v1 targets for a physical dimension."""

    normalized = normalize_dimension(dimension)
    return tuple(
        unit.display
        for unit in _SUPPORTED_UNITS
        if unit.definition.dimension == normalized
    )


def conversion_contract(
    *,
    source_unit: str | None,
    canonical_unit: str | None,
    expected_dimension: str | None,
) -> dict[str, Any]:
    """Validate an explicit mapping without converting an observation value."""

    result = normalize_telemetry_unit(
        value=0.0,
        source_unit=source_unit,
        canonical_unit=canonical_unit,
        expected_dimension=expected_dimension,
    )
    return {
        "valid": result.analysis_eligible,
        "dimension": result.dimension,
        "source_unit": result.original_unit,
        "canonical_unit": result.canonical_unit,
        "conversion_id": result.conversion_id,
        "conversion_version": result.conversion_version,
        "reason_code": result.reason_code,
    }


def normalize_telemetry_unit(
    *,
    value: Any,
    source_unit: str | None,
    canonical_unit: str | None,
    expected_dimension: str | None,
) -> UnitNormalizationResult:
    """Normalize only an explicitly approved source/target unit pair.

    No signal name or external tag is accepted by this function, so it cannot
    guess units or silently turn a suggested semantic mapping into authority.
    """

    original_unit = str(source_unit) if source_unit is not None else None
    lookup_source_unit = normalize_unit_label(source_unit) or None
    requested_canonical_unit = normalize_unit_label(canonical_unit) or None
    expected = normalize_dimension(expected_dimension)
    source = _SUPPORTED_LOOKUP.get(unit_key(lookup_source_unit)) if lookup_source_unit else None
    target = (
        _SUPPORTED_LOOKUP.get(unit_key(requested_canonical_unit))
        if requested_canonical_unit
        else None
    )

    if source is None or target is None:
        reason = "source_unit_unknown" if source is None else "canonical_unit_unknown"
        return UnitNormalizationResult(
            status="unit_unresolved",
            quality_state="unit_unresolved",
            analysis_eligible=False,
            reason_code=reason,
            original_value=value,
            original_unit=original_unit,
            canonical_value=None,
            canonical_unit=target.display if target else requested_canonical_unit,
            dimension=expected,
            conversion_id=None,
            conversion_version=UNIT_NORMALIZATION_VERSION,
        )

    source_dimension = normalize_dimension(source.definition.dimension)
    target_dimension = normalize_dimension(target.definition.dimension)
    resolved_dimension = expected or target_dimension
    if source_dimension != target_dimension or (
        expected is not None and target_dimension != expected
    ):
        return UnitNormalizationResult(
            status="unit_incompatible",
            quality_state="unit_unresolved",
            analysis_eligible=False,
            reason_code="unit_dimension_incompatible",
            original_value=value,
            original_unit=original_unit,
            canonical_value=None,
            canonical_unit=target.display,
            dimension=resolved_dimension,
            conversion_id=None,
            conversion_version=UNIT_NORMALIZATION_VERSION,
        )

    if isinstance(value, bool):
        numeric = math.nan
    else:
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            numeric = math.nan
    if not math.isfinite(numeric):
        return UnitNormalizationResult(
            status="invalid_value",
            quality_state="invalid_value",
            analysis_eligible=False,
            reason_code="value_nonfinite",
            original_value=value,
            original_unit=original_unit,
            canonical_value=None,
            canonical_unit=target.display,
            dimension=resolved_dimension,
            conversion_id=None,
            conversion_version=UNIT_NORMALIZATION_VERSION,
        )

    conversion_id = f"{source.token}_to_{target.token}"
    try:
        base_value = source.definition.to_normalized(numeric)
        converted = target.from_base(base_value)
    except (ArithmeticError, OverflowError, ValueError):
        converted = math.nan
    if not math.isfinite(converted):
        return UnitNormalizationResult(
            status="invalid_value",
            quality_state="invalid_value",
            analysis_eligible=False,
            reason_code="conversion_nonfinite",
            original_value=value,
            original_unit=original_unit,
            canonical_value=None,
            canonical_unit=target.display,
            dimension=resolved_dimension,
            conversion_id=conversion_id,
            conversion_version=UNIT_NORMALIZATION_VERSION,
        )

    return UnitNormalizationResult(
        status="normalized",
        quality_state="good",
        analysis_eligible=True,
        reason_code=None,
        original_value=value,
        original_unit=original_unit,
        canonical_value=converted,
        canonical_unit=target.display,
        dimension=resolved_dimension,
        conversion_id=conversion_id,
        conversion_version=UNIT_NORMALIZATION_VERSION,
    )


__all__ = [
    "UNIT_NORMALIZATION_VERSION",
    "UnitNormalizationResult",
    "conversion_contract",
    "normalize_telemetry_unit",
    "supported_units_for_dimension",
]
