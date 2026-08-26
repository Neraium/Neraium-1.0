from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.health_relevance import (
    DEFAULT_THRESHOLDS,
    evaluate_evidence_state,
    freshness_status,
)
from app.services.health_relevance_methods import (
    BAYESIAN_METHOD_ID,
    INFORMATION_METHOD_ID,
)


def _summary(**overrides):
    value = {
        "eligible_outcome_count": 8,
        "canonical_incident_count": 6,
        "positive_count": 6,
        "negative_count": 2,
        "primary_positive_count": 6,
        "primary_negative_count": 2,
        "positive_balance_all": 0.75,
        "positive_balance_primary": 0.75,
        "context_metadata_completeness": 0.80,
        "context_episode_count": 2,
        "protocol_completion": 0.80,
        "comparison_window_count": 2,
        "positive_family_count": 2,
        "independent_count": 2,
        "tier_a_count": 1,
        "hard_eligibility_failure": False,
        "limited_link_count": 0,
    }
    value.update(overrides)
    return value


def _bayesian(lower=0.60):
    return {
        "components": {
            "primary_view": {
                "posterior": {"credible_interval_90": {"lower": lower, "upper": 0.9}}
            }
        }
    }


def _information(adjusted=0.10, observed=0.20, null_95=0.19):
    return {
        "components": {
            "primary_view": {
                "adjusted_normalized_information": adjusted,
                "observed_normalized_information": observed,
                "permutation_reference": {"null_percentile_95": null_95},
            }
        }
    }


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"eligible_outcome_count": 2}, "insufficient_outcome_evidence"),
        (
            {
                "eligible_outcome_count": 3,
                "canonical_incident_count": 2,
                "positive_count": 3,
                "negative_count": 0,
                "primary_positive_count": 3,
                "primary_negative_count": 0,
                "positive_balance_all": 1.0,
                "positive_balance_primary": 1.0,
            },
            "emerging_relevance",
        ),
        ({"canonical_incident_count": 1}, "insufficient_outcome_evidence"),
        (
            {
                "eligible_outcome_count": 4,
                "canonical_incident_count": 3,
            },
            "emerging_relevance",
        ),
        ({}, "supported_relevance"),
    ],
)
def test_minimum_outcome_and_recurrence_boundaries(overrides, expected):
    result = evaluate_evidence_state(
        _summary(**overrides), BAYESIAN_METHOD_ID, _bayesian()
    )
    assert result["evidence_state"] == expected


@pytest.mark.parametrize(
    ("balance", "expected"),
    [
        (0.3999, "emerging_relevance"),
        (0.4000, "contradictory_evidence"),
        (0.6000, "contradictory_evidence"),
        (0.6001, "emerging_relevance"),
    ],
)
def test_contradictory_band_is_inclusive(balance, expected):
    result = evaluate_evidence_state(
        _summary(
            positive_count=3,
            negative_count=2,
            primary_positive_count=3,
            primary_negative_count=2,
            positive_balance_all=balance,
            positive_balance_primary=balance,
        ),
        BAYESIAN_METHOD_ID,
        _bayesian(),
    )
    assert result["evidence_state"] == expected


def test_contradiction_requires_both_sides_and_five_directional_units():
    result = evaluate_evidence_state(
        _summary(
            positive_count=2,
            negative_count=2,
            primary_positive_count=2,
            primary_negative_count=2,
            positive_balance_all=0.5,
            positive_balance_primary=0.5,
        ),
        BAYESIAN_METHOD_ID,
        _bayesian(),
    )
    assert result["evidence_state"] == "emerging_relevance"


@pytest.mark.parametrize(
    ("balance", "negative", "expected"),
    [
        (0.2501, 4, "emerging_relevance"),
        (0.2500, 4, "not_supported_by_outcomes"),
        (0.0000, 3, "emerging_relevance"),
        (0.0000, 4, "not_supported_by_outcomes"),
    ],
)
def test_negative_dominant_boundary(balance, negative, expected):
    result = evaluate_evidence_state(
        _summary(
            positive_count=1 if balance else 0,
            negative_count=negative,
            primary_positive_count=1 if balance else 0,
            primary_negative_count=negative,
            positive_balance_all=balance,
            positive_balance_primary=balance,
        ),
        BAYESIAN_METHOD_ID,
        _bayesian(),
    )
    assert result["evidence_state"] == expected


@pytest.mark.parametrize(
    ("field", "below", "at", "reason"),
    [
        ("context_metadata_completeness", 0.7999, 0.8000, "context_completeness_not_met"),
        ("context_episode_count", 1, 2, "context_episode_coverage_not_met"),
        ("protocol_completion", 0.7999, 0.8000, "stable_protocol_completion_not_met"),
        ("comparison_window_count", 1, 2, "explicit_comparison_denominator_not_met"),
        ("positive_family_count", 1, 2, "outcome_diversity_not_met"),
        ("independent_count", 1, 2, "independent_evidence_not_met"),
        ("tier_a_count", 0, 1, "tier_a_evidence_not_met"),
    ],
)
def test_supported_gate_boundaries(field, below, at, reason):
    below_state = evaluate_evidence_state(
        _summary(**{field: below}), BAYESIAN_METHOD_ID, _bayesian()
    )
    at_state = evaluate_evidence_state(
        _summary(**{field: at}), BAYESIAN_METHOD_ID, _bayesian()
    )
    assert below_state["evidence_state"] == "emerging_relevance"
    assert reason in below_state["state_reason_codes"]
    assert at_state["evidence_state"] == "supported_relevance"


def test_primary_and_all_authority_balances_must_both_pass():
    all_fails = evaluate_evidence_state(
        _summary(positive_balance_all=0.7499), BAYESIAN_METHOD_ID, _bayesian()
    )
    primary_fails = evaluate_evidence_state(
        _summary(positive_balance_primary=0.7499), BAYESIAN_METHOD_ID, _bayesian()
    )
    assert all_fails["evidence_state"] == "emerging_relevance"
    assert "all_positive_balance_not_met" in all_fails["state_reason_codes"]
    assert primary_fails["evidence_state"] == "emerging_relevance"
    assert "primary_positive_balance_not_met" in primary_fails["state_reason_codes"]


def test_bayesian_lower_bound_is_inclusive():
    below = evaluate_evidence_state(
        _summary(), BAYESIAN_METHOD_ID, _bayesian(0.5999)
    )
    at = evaluate_evidence_state(_summary(), BAYESIAN_METHOD_ID, _bayesian(0.6000))
    assert below["evidence_state"] == "emerging_relevance"
    assert at["evidence_state"] == "supported_relevance"


def test_information_floor_is_inclusive_but_permutation_must_be_strict():
    below = evaluate_evidence_state(
        _summary(), INFORMATION_METHOD_ID, _information(adjusted=0.0999)
    )
    equal_null = evaluate_evidence_state(
        _summary(), INFORMATION_METHOD_ID, _information(observed=0.19, null_95=0.19)
    )
    at = evaluate_evidence_state(
        _summary(), INFORMATION_METHOD_ID, _information(adjusted=0.10, observed=0.20)
    )
    assert below["evidence_state"] == "emerging_relevance"
    assert equal_null["evidence_state"] == "emerging_relevance"
    assert at["evidence_state"] == "supported_relevance"


def test_hard_reference_or_context_failure_is_fail_closed():
    result = evaluate_evidence_state(
        _summary(hard_eligibility_failure=True), BAYESIAN_METHOD_ID, _bayesian()
    )
    assert result["evidence_state"] == "insufficient_outcome_evidence"
    assert "identity_context_or_provenance_incomplete" in result["state_reason_codes"]


def test_staleness_has_no_numeric_decay_and_changes_after_boundary():
    last = datetime(2026, 1, 1, tzinfo=UTC)
    assert freshness_status(last, as_of=last + timedelta(days=180)) == "current"
    assert (
        freshness_status(last, as_of=last + timedelta(days=180, microseconds=1))
        == "stale"
    )
    assert DEFAULT_THRESHOLDS.stale_after_days == 180
