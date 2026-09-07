"""Bounded Mann–Kendall evidence; no authority, causality or health interpretation."""
from collections import Counter
from math import erfc, isfinite, sqrt

from pydantic import StrictBool

from app.governance.contracts import Contract, EvidenceObject, ObservationReference, Timestamp
from app.governance.registry import time


class TrendAssumptions(Contract):
    independent_observations: StrictBool
    no_unmodeled_seasonality: StrictBool
    comparable_measurement_regime: StrictBool
    missingness_ignorable: StrictBool


class TrendSample(Contract):
    observed_at: Timestamp
    value: float | None


def mann_kendall_evidence(*, samples: tuple[TrendSample, ...], observation: ObservationReference,
                          assumptions: TrendAssumptions, created_at: str, source_run_id: str) -> EvidenceObject:
    observation = ObservationReference.model_validate(observation.as_dict())
    assumptions = TrendAssumptions.model_validate(assumptions.as_dict())
    samples = tuple(TrendSample.model_validate(item.as_dict()) for item in samples)
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
    values = [item.value for item in samples if item.value is not None]
    missing = len(samples) - len(values)
    reasons = [key for key, value in assumptions.as_dict().items() if not value]
    if len(values) < 10:
        reasons.append("insufficient_samples_minimum_10")
    if len(samples) > 2048:
        reasons.append("sample_limit_2048")
    if missing and not assumptions.missingness_ignorable:
        reasons.append("missing_data_ineligible")
    payload = dict(status="limited" if reasons else "available", eligibility_reasons=reasons,
                   n=len(values), missing_count=missing, method="mann_kendall_tie_corrected_normal_v1",
                   assumptions=assumptions.as_dict(), significance_threshold=0.05,
                   limitations=["normal_approximation", "assumptions_asserted_by_adapter",
                                "no_causal_health_or_authority_interpretation", "not_a_rate_estimate"],
                   irregular_spacing=len({(b - a).total_seconds() for a, b in zip(instants, instants[1:])}) > 1,
                   statistic_s=None, variance_s=None, z=None, p_value=None, significant=None, direction="unavailable")
    if not reasons:
        n = len(values)
        s = sum((b > a) - (b < a) for i, a in enumerate(values) for b in values[i + 1:])
        correction = sum(t * (t - 1) * (2 * t + 5) for t in Counter(values).values())
        variance = (n * (n - 1) * (2 * n + 5) - correction) / 18
        z = (s - (1 if s > 0 else -1)) / sqrt(variance) if s and variance > 0 else 0.0
        p = erfc(abs(z) / sqrt(2))
        payload.update(statistic_s=s, variance_s=variance, z=z, p_value=p, significant=p <= .05,
                       direction="increasing" if s > 0 else "decreasing" if s < 0 else "none")
    return EvidenceObject(evidence_family="trend", evidence_method="mann_kendall_tie_corrected_normal_v1",
        source_module="app.governance.trend", source_run_id=source_run_id, system_scope=observation.system_scope,
        source_signals=observation.source_signals, source_window=window,
        derived_from=({"kind": "observation", "dependency_id": observation.observation_id},),
        assumption_set=tuple(f"{key}={value}" for key, value in assumptions.as_dict().items()), context_refs=(),
        provenance=observation.provenance, created_at=created_at, payload=payload, lineage_complete=True)
