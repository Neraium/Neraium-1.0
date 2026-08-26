from __future__ import annotations

import math

import pytest

from app.services.telemetry_units import (
    UNIT_NORMALIZATION_VERSION,
    conversion_contract,
    normalize_telemetry_unit,
    supported_units_for_dimension,
)


@pytest.mark.parametrize(
    ("source_unit", "target_unit", "dimension", "value", "expected"),
    [
        ("degF", "degC", "temperature", 32.0, 0.0),
        ("°C", "degF", "temperature", 100.0, 212.0),
        ("psi", "kPa", "pressure", 1.0, 6.89475728),
        ("kPa", "psi", "differential_pressure", 6.89475728, 1.0),
        ("GPM", "L/s", "flow", 1.0, 0.0630901964),
        ("L/s", "gpm", "flow", 1.0, 15.850323141),
        ("kW", "W", "power", 1.25, 1250.0),
        ("watts", "kW", "power", 2500.0, 2.5),
        ("%", "fraction", "fraction", 25.0, 0.25),
        ("ratio", "%", "valve_position", 0.25, 25.0),
    ],
)
def test_required_inverse_conversions_are_explicit_and_precise(
    source_unit: str,
    target_unit: str,
    dimension: str,
    value: float,
    expected: float,
) -> None:
    result = normalize_telemetry_unit(
        value=value,
        source_unit=source_unit,
        canonical_unit=target_unit,
        expected_dimension=dimension,
    )

    assert result.status == "normalized"
    assert result.quality_state == "good"
    assert result.analysis_eligible is True
    assert result.canonical_value == pytest.approx(expected, rel=1e-8, abs=1e-10)
    assert result.conversion_id is not None
    assert result.conversion_version == UNIT_NORMALIZATION_VERSION


@pytest.mark.parametrize(
    ("unit", "dimension"),
    [
        ("degF", "temperature"),
        ("degC", "temperature"),
        ("psi", "pressure"),
        ("kPa", "pressure"),
        ("gpm", "flow"),
        ("L/s", "flow"),
        ("kW", "power"),
        ("W", "power"),
        ("%", "fraction"),
        ("fraction", "fraction"),
    ],
)
def test_identity_conversions_are_versioned(unit: str, dimension: str) -> None:
    result = normalize_telemetry_unit(
        value=12.5,
        source_unit=unit,
        canonical_unit=unit,
        expected_dimension=dimension,
    )

    assert result.canonical_value == pytest.approx(12.5)
    assert result.conversion_id is not None
    assert result.conversion_id.endswith(f"_to_{result.conversion_id.split('_to_')[0]}")
    assert result.conversion_version == UNIT_NORMALIZATION_VERSION


def test_normalization_preserves_original_value_and_unit_exactly() -> None:
    result = normalize_telemetry_unit(
        value="72.500",
        source_unit=" °F ",
        canonical_unit="degC",
        expected_dimension="temperature",
    )

    assert result.original_value == "72.500"
    assert result.original_unit == " °F "
    assert result.canonical_value == pytest.approx(22.5)
    assert result.canonical_unit == "degC"
    assert result.dimension == "temperature"
    assert result.to_dict()["conversion_version"] == UNIT_NORMALIZATION_VERSION


@pytest.mark.parametrize(
    ("source", "target", "dimension", "reason"),
    [
        (None, "kW", "power", "source_unit_unknown"),
        ("mystery", "kW", "power", "source_unit_unknown"),
        ("kW", "horsepower", "power", "canonical_unit_unknown"),
        ("kW", "psi", "pressure", "unit_dimension_incompatible"),
        ("psi", "kPa", "temperature", "unit_dimension_incompatible"),
    ],
)
def test_unknown_and_incompatible_units_are_analysis_ineligible(
    source: str | None,
    target: str,
    dimension: str,
    reason: str,
) -> None:
    result = normalize_telemetry_unit(
        value=12.0,
        source_unit=source,
        canonical_unit=target,
        expected_dimension=dimension,
    )

    assert result.analysis_eligible is False
    assert result.canonical_value is None
    assert result.quality_state == "unit_unresolved"
    assert result.reason_code == reason


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "nan", True, None])
def test_nonfinite_or_nonnumeric_values_are_analysis_ineligible(value: object) -> None:
    result = normalize_telemetry_unit(
        value=value,
        source_unit="kW",
        canonical_unit="W",
        expected_dimension="power",
    )

    assert result.original_value is value or (
        isinstance(value, float) and math.isnan(value) and math.isnan(result.original_value)
    )
    assert result.status == "invalid_value"
    assert result.quality_state == "invalid_value"
    assert result.analysis_eligible is False
    assert result.reason_code == "value_nonfinite"


def test_mapping_contract_requires_explicit_units_and_exposes_provenance() -> None:
    contract = conversion_contract(
        source_unit="CentralPlant.Pump01.Power",
        canonical_unit="kW",
        expected_dimension="power",
    )

    assert contract == {
        "valid": False,
        "dimension": "power",
        "source_unit": "CentralPlant.Pump01.Power",
        "canonical_unit": "kW",
        "conversion_id": None,
        "conversion_version": UNIT_NORMALIZATION_VERSION,
        "reason_code": "source_unit_unknown",
    }


def test_supported_v1_targets_reuse_existing_dimension_aliases() -> None:
    assert supported_units_for_dimension("differential_pressure") == ("psi", "kPa")
    assert supported_units_for_dimension("valve_position") == ("%", "fraction")
