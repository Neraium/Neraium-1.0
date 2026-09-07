"""Bounded Mann–Kendall evidence; no authority, causality or health interpretation."""
from collections import Counter
from math import erfc, isfinite, sqrt
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt

from app.governance.contracts import Contract, EvidenceObject, ObservationReference, Timestamp, canonical_json
from app.governance.registry import time


class TrendAssumptions(Contract):
    independent_observations: StrictBool
    no_unmodeled_seasonality: StrictBool
    comparable_measurement_regime: StrictBool
    missingness_ignorable: StrictBool


class TrendSample(Contract):
    observed_at: Timestamp
    value: float | None


METHOD = "mann_kendall_tie_corrected_normal_v1"
LIMITATIONS = ["normal_approximation", "assumptions_asserted_by_adapter",
              "no_causal_health_or_authority_interpretation", "not_a_rate_estimate"]


class MannKendallResult(Contract):
    method: Literal["mann_kendall_tie_corrected_normal_v1"]
    status: Literal["limited", "available"]
    n: Annotated[StrictInt, Field(ge=0)]
    missing_count: Annotated[StrictInt, Field(ge=0)]
    tie_group_sizes: tuple[Annotated[StrictInt, Field(ge=2)], ...]
    assumptions: TrendAssumptions
    eligibility_reasons: tuple[str, ...]
    limitations: tuple[str, ...]
    irregular_spacing: StrictBool
    significance_threshold: StrictFloat
    statistic_s: StrictInt | None
    variance_s: StrictFloat | None
    z: StrictFloat | None
    p_value: StrictFloat | None
    significant: StrictBool | None
    direction: Literal["increasing", "decreasing", "none", "unavailable"]
    governance_conditions: dict[str, str] = {}


def _normal_z(s, variance):
    if not s or variance <= 0:
        return 0.0
    correction = 1 if s > 0 else -1
    return (s - correction) / sqrt(variance)


def _direction(s):
    if s > 0:
        return "increasing"
    if s < 0:
        return "decreasing"
    return "none"


def _eligibility_reasons(n, missing, assumptions):
    reasons = [key for key, value in assumptions.as_dict().items() if not value]
    if n < 10:
        reasons.append("insufficient_samples_minimum_10")
    if n + missing > 2048:
        reasons.append("sample_limit_2048")
    if missing and not assumptions.missingness_ignorable:
        reasons.append("missing_data_ineligible")
    return reasons


def _statistics_match(result, n, ties):
    s = result.statistic_s
    pairs = n * (n - 1) // 2 - sum(t * (t - 1) // 2 for t in ties)
    if s is None or abs(s) > pairs or (pairs - s) % 2:
        return False
    variance = (n * (n - 1) * (2 * n + 5) - sum(t * (t - 1) * (2 * t + 5) for t in ties)) / 18
    z = _normal_z(s, variance)
    p = erfc(abs(z) / sqrt(2))
    expected = [variance, z, p, p <= .05, _direction(s)]
    return canonical_json([result.variance_s, result.z, result.p_value, result.significant, result.direction]) == canonical_json(expected)


def trend_usable(evidence: EvidenceObject) -> bool:
    """Validate retained method statistics; raw-artifact truth remains external.

    Unknown methods have no eligibility contract. This method never establishes
    an acceptable evolution rate, even if a caller adds a condition assertion.
    """
    try:
        if (evidence.evidence_method != METHOD or not evidence.source_window.started_at
                or not evidence.source_window.ended_at
                or time(evidence.source_window.ended_at) > time(evidence.created_at)):
            return False
        result = MannKendallResult.model_validate(evidence.payload)
        assumptions = result.assumptions.as_dict()
        if evidence.assumption_set != tuple(sorted(f"{k}={v}" for k, v in assumptions.items())):
            return False
        # The method parameter must match exactly; tolerance would admit another method.
        if list(result.limitations) != LIMITATIONS or canonical_json(result.significance_threshold) != canonical_json(.05):
            return False
        n, ties = result.n, result.tie_group_sizes
        if tuple(sorted(ties)) != ties or sum(ties) > n:
            return False
        reasons = _eligibility_reasons(n, result.missing_count, result.assumptions)
        if list(result.eligibility_reasons) != reasons or result.status != ("limited" if reasons else "available"):
            return False
        if reasons:
            return False
        return _statistics_match(result, n, ties)
    except (ValueError, TypeError):
        return False


def _validate_samples(samples, observation, created_at):
    instants = [time(item.observed_at) for item in samples]
    if any(a >= b for a, b in zip(instants, instants[1:])):
        raise ValueError("trend_times_must_strictly_increase")
    if any(at > time(created_at) for at in instants):
        raise ValueError("future_trend_sample")
    window = observation.source_window
    if not window.started_at or not window.ended_at or time(window.ended_at) > time(created_at):
        raise ValueError("trend_requires_available_bounded_source_window")
    if any(not time(window.started_at) <= at <= time(window.ended_at) for at in instants):
        raise ValueError("trend_sample_outside_source_window")
    if any(item.value is not None and not isfinite(item.value) for item in samples):
        raise ValueError("nonfinite_trend_value_use_null_for_missing")
    return instants, window


def mann_kendall_evidence(*, samples: tuple[TrendSample, ...], observation: ObservationReference,
                          assumptions: TrendAssumptions, created_at: str, source_run_id: str) -> EvidenceObject:
    observation = ObservationReference.model_validate(observation.as_dict())
    assumptions = TrendAssumptions.model_validate(assumptions.as_dict())
    samples = tuple(TrendSample.model_validate(item.as_dict()) for item in samples)
    instants, window = _validate_samples(samples, observation, created_at)
    values = [item.value for item in samples if item.value is not None]
    missing = len(samples) - len(values)
    reasons = _eligibility_reasons(len(values), missing, assumptions)
    payload = {
        "status": "limited" if reasons else "available", "eligibility_reasons": reasons,
        "tie_group_sizes": sorted(t for t in Counter(values).values() if t > 1),
        "n": len(values), "missing_count": missing, "method": METHOD,
        "assumptions": assumptions.as_dict(), "significance_threshold": 0.05,
        "limitations": LIMITATIONS.copy(),
        "irregular_spacing": len({(b - a).total_seconds() for a, b in zip(instants, instants[1:])}) > 1,
        "statistic_s": None, "variance_s": None, "z": None, "p_value": None,
        "significant": None, "direction": "unavailable",
    }
    if not reasons:
        n = len(values)
        s = sum((b > a) - (b < a) for i, a in enumerate(values) for b in values[i + 1:])
        correction = sum(t * (t - 1) * (2 * t + 5) for t in Counter(values).values())
        variance = (n * (n - 1) * (2 * n + 5) - correction) / 18
        z = _normal_z(s, variance)
        p = erfc(abs(z) / sqrt(2))
        payload.update(statistic_s=s, variance_s=variance, z=z, p_value=p, significant=p <= .05,
                       direction=_direction(s))
    return EvidenceObject(evidence_family="trend", evidence_method=METHOD,
        source_module="app.governance.trend", source_run_id=source_run_id, system_scope=observation.system_scope,
        source_signals=observation.source_signals, source_window=window,
        derived_from=({"kind": "observation", "dependency_id": observation.observation_id},),
        assumption_set=tuple(f"{key}={value}" for key, value in assumptions.as_dict().items()), context_refs=(),
        provenance=observation.provenance, created_at=created_at, payload=payload, lineage_complete=True)
