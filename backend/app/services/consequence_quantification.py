from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Iterable, Literal


QuantificationStatus = Literal["quantified", "not_quantifiable"]


@dataclass(frozen=True)
class ResourceProfile:
    resource_type: str
    rate_unit: str
    cumulative_unit: str
    rate_period_seconds: float


RESOURCE_PROFILES: dict[str, ResourceProfile] = {
    "water_gpm": ResourceProfile("water", "gpm", "gal", 60.0),
    "electricity_kw": ResourceProfile("electricity", "kW", "kWh", 3600.0),
    "steam_lb_hr": ResourceProfile("steam", "lb/hr", "lb", 3600.0),
    "chemical_gal_hr": ResourceProfile("chemical", "gal/hr", "gal", 3600.0),
    "compressed_air_scfm": ResourceProfile("compressed_air", "scfm", "scf", 60.0),
}


def _timestamp_seconds(value: Any) -> float:
    if isinstance(value, (int, float)) and isfinite(float(value)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        raise ValueError("missing timestamp")
    normalized = text.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).timestamp()


def _finite_number(value: Any) -> float:
    number = float(value)
    if not isfinite(number):
        raise ValueError("non-finite value")
    return number


def _not_quantifiable(reason: str, *, resource_type: str | None = None) -> dict[str, Any]:
    return {
        "status": "not_quantifiable",
        "resource_type": resource_type,
        "reason": reason,
        "statement": "Consequence not quantifiable from available evidence.",
    }


def quantify_consequence(
    observations: Iterable[dict[str, Any]],
    *,
    profile_key: str,
    max_gap_seconds: float | None = None,
    source_relationship_ids: list[str] | None = None,
    source_tag_ids: list[str] | None = None,
    support_level: str | None = None,
) -> dict[str, Any]:
    """Quantify a measurable consequence from observed-vs-expected rate evidence.

    Each observation requires ``timestamp``, ``observed``, and ``expected``. Optional
    ``valid`` can explicitly gate an observation. Invalid observations and intervals
    are excluded; the function never interpolates over missing evidence.

    The result is deliberately non-causal. It measures only the signed deviation
    associated with the supplied evidence window.
    """

    profile = RESOURCE_PROFILES.get(profile_key)
    if profile is None:
        return _not_quantifiable(f"Unknown resource profile: {profile_key}")

    prepared: list[dict[str, float]] = []
    rejected_observations = 0
    for item in observations:
        if item.get("valid", True) is False:
            rejected_observations += 1
            continue
        try:
            prepared.append(
                {
                    "timestamp": _timestamp_seconds(item.get("timestamp")),
                    "observed": _finite_number(item.get("observed")),
                    "expected": _finite_number(item.get("expected")),
                }
            )
        except (TypeError, ValueError, OverflowError):
            rejected_observations += 1

    prepared.sort(key=lambda row: row["timestamp"])
    if len(prepared) < 2:
        return _not_quantifiable("At least two valid aligned observations are required.", resource_type=profile.resource_type)

    intervals: list[dict[str, Any]] = []
    cumulative = 0.0
    absolute_cumulative = 0.0
    duration_seconds = 0.0
    excluded_intervals = 0

    for left, right in zip(prepared, prepared[1:]):
        dt = right["timestamp"] - left["timestamp"]
        if dt <= 0:
            excluded_intervals += 1
            continue
        if max_gap_seconds is not None and dt > float(max_gap_seconds):
            excluded_intervals += 1
            continue

        left_residual = left["observed"] - left["expected"]
        right_residual = right["observed"] - right["expected"]
        mean_residual = (left_residual + right_residual) / 2.0
        amount = mean_residual * dt / profile.rate_period_seconds
        absolute_amount = (abs(left_residual) + abs(right_residual)) / 2.0 * dt / profile.rate_period_seconds

        cumulative += amount
        absolute_cumulative += absolute_amount
        duration_seconds += dt
        intervals.append(
            {
                "start_timestamp": left["timestamp"],
                "end_timestamp": right["timestamp"],
                "duration_seconds": dt,
                "start_deviation_rate": left_residual,
                "end_deviation_rate": right_residual,
                "integrated_amount": amount,
            }
        )

    if not intervals or duration_seconds <= 0:
        return _not_quantifiable("No valid contiguous intervals support accumulation.", resource_type=profile.resource_type)

    observed_values = [row["observed"] for row in prepared]
    expected_values = [row["expected"] for row in prepared]
    observed_rate = sum(observed_values) / len(observed_values)
    expected_rate = sum(expected_values) / len(expected_values)
    deviation_rate = observed_rate - expected_rate
    relative_deviation = (deviation_rate / abs(expected_rate)) if expected_rate != 0 else None

    direction = "above_expected" if cumulative > 0 else "below_expected" if cumulative < 0 else "aligned"
    return {
        "status": "quantified",
        "resource_type": profile.resource_type,
        "rate_unit": profile.rate_unit,
        "cumulative_unit": profile.cumulative_unit,
        "observed_rate": observed_rate,
        "expected_rate": expected_rate,
        "deviation_rate": deviation_rate,
        "relative_deviation": relative_deviation,
        "cumulative_amount": cumulative,
        "absolute_cumulative_amount": absolute_cumulative,
        "direction": direction,
        "duration_seconds": duration_seconds,
        "calculation_method": "timestamp-aware trapezoidal integration of observed-minus-expected rate",
        "support_level": support_level,
        "contributing_intervals": intervals,
        "valid_observation_count": len(prepared),
        "rejected_observation_count": rejected_observations,
        "excluded_interval_count": excluded_intervals,
        "source_relationship_ids": list(source_relationship_ids or []),
        "source_tag_ids": list(source_tag_ids or []),
        "evidence_boundary": "Associated measurable deviation only; no cause attribution is performed.",
    }
