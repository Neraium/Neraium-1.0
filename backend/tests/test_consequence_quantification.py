from __future__ import annotations

import pytest

from neraium_consequence import quantify_consequence


def test_water_quantification_integrates_irregular_cadence() -> None:
    result = quantify_consequence(
        [
            {"timestamp": 0, "observed": 40.0, "expected": 20.0},
            {"timestamp": 60, "observed": 42.0, "expected": 20.0},
            {"timestamp": 180, "observed": 44.0, "expected": 20.0},
        ],
        profile_key="water_gpm",
        source_relationship_ids=["makeup-water:cooling-load"],
        source_tag_ids=["makeup_flow", "cooling_load"],
        support_level="high",
    )

    assert result["status"] == "quantified"
    assert result["resource_type"] == "water"
    assert result["cumulative_unit"] == "gal"
    assert result["cumulative_amount"] == pytest.approx(67.0)
    assert result["duration_seconds"] == 180.0
    assert result["source_relationship_ids"] == ["makeup-water:cooling-load"]
    assert "cause" not in result


def test_electricity_quantification_uses_kwh_time_base() -> None:
    result = quantify_consequence(
        [
            {"timestamp": 0, "observed": 114.2, "expected": 100.0},
            {"timestamp": 3600, "observed": 114.2, "expected": 100.0},
        ],
        profile_key="electricity_kw",
    )

    assert result["status"] == "quantified"
    assert result["cumulative_amount"] == pytest.approx(14.2)
    assert result["cumulative_unit"] == "kWh"


def test_bad_quality_observations_are_gated_not_interpolated() -> None:
    result = quantify_consequence(
        [
            {"timestamp": 0, "observed": 30.0, "expected": 20.0},
            {"timestamp": 60, "observed": 1000.0, "expected": 20.0, "valid": False},
            {"timestamp": 120, "observed": 30.0, "expected": 20.0},
        ],
        profile_key="water_gpm",
        max_gap_seconds=90,
    )

    assert result["status"] == "not_quantifiable"
    assert result["statement"] == "Consequence not quantifiable from available evidence."


def test_unknown_profile_refuses_quantification() -> None:
    result = quantify_consequence(
        [{"timestamp": 0, "observed": 1, "expected": 0}, {"timestamp": 60, "observed": 1, "expected": 0}],
        profile_key="mystery_resource",
    )
    assert result["status"] == "not_quantifiable"


def test_signed_deficit_is_preserved() -> None:
    result = quantify_consequence(
        [
            {"timestamp": 0, "observed": 15.0, "expected": 20.0},
            {"timestamp": 60, "observed": 15.0, "expected": 20.0},
        ],
        profile_key="water_gpm",
    )
    assert result["cumulative_amount"] == pytest.approx(-5.0)
    assert result["direction"] == "below_expected"
