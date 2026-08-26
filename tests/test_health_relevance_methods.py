from __future__ import annotations

import copy

import pytest

from app.services.health_relevance_methods import (
    BAYESIAN_METHOD_ID,
    INFORMATION_METHOD_ID,
    METHOD_REGISTRY,
    BayesianShrinkageMethod,
    OutcomeConditionedInformationMethod,
    evaluate_health_relevance_method,
)


MANIFEST_HASH = "sha256:frozen-health-relevance-manifest"


def _manifest(contributions: list[dict[str, object]]) -> dict[str, object]:
    return {
        "input_manifest_hash": MANIFEST_HASH,
        "input_snapshot_id": "snapshot-001",
        "contributions": contributions,
    }


def _directional(
    contribution_id: str,
    treatment: str,
    authority_tier: str,
) -> dict[str, object]:
    return {
        "contribution_id": contribution_id,
        "eligible": True,
        "evidence_treatment": treatment,
        "authority_tier": authority_tier,
        "provenance_categories": [
            "independently_documented_outcome"
            if authority_tier in {"A", "B"}
            else "operator_confirmed_after_neraium_review"
        ],
    }


def _cell(contribution_id: str, cell: str, authority_tier: str = "A") -> dict[str, object]:
    return {
        "contribution_id": contribution_id,
        "eligible": True,
        "information_cell": cell,
        "authority_tier": authority_tier,
        "provenance_categories": ["independently_documented_outcome"],
    }


def test_registry_contains_exactly_the_two_approved_methods() -> None:
    assert set(METHOD_REGISTRY) == {
        "bayesian_shrinkage_v1",
        "outcome_conditioned_information_v1",
    }
    assert len(METHOD_REGISTRY) == 2
    assert METHOD_REGISTRY[BAYESIAN_METHOD_ID].method_id == BAYESIAN_METHOD_ID
    assert METHOD_REGISTRY[INFORMATION_METHOD_ID].method_id == INFORMATION_METHOD_ID

    with pytest.raises(KeyError, match="unsupported Health Relevance method"):
        evaluate_health_relevance_method("third_method", _manifest([]))


def test_bayesian_sparse_event_is_shrunk_and_uncertainty_remains_wide() -> None:
    result = BayesianShrinkageMethod().evaluate(
        _manifest([_directional("outcome-1", "positive", "A")])
    )
    primary = result["components"]["primary_view"]

    assert primary["counts"] == {"positive": 1, "negative": 0, "directional": 1}
    assert primary["prior"] == {"alpha": 2.0, "beta": 2.0}
    assert primary["posterior"]["alpha"] == 3.0
    assert primary["posterior"]["beta"] == 2.0
    assert primary["posterior"]["mean"] == pytest.approx(0.6)
    assert 0.5 < primary["posterior"]["median"] < 0.7
    interval = primary["posterior"]["credible_interval_90"]
    assert interval["lower"] < 0.3
    assert interval["upper"] > 0.85
    assert result["uncertainty"]["sparse_data_shrinkage_target"] == 0.5


def test_bayesian_keeps_primary_and_neraium_influenced_evidence_separate() -> None:
    manifest = _manifest(
        [
            _directional("independent-positive", "positive", "A"),
            _directional("independent-negative", "negative", "B"),
            _directional("influenced-positive-1", "positive", "D"),
            _directional("influenced-positive-2", "positive", "D"),
        ]
    )
    result = BayesianShrinkageMethod().evaluate(manifest)
    primary = result["components"]["primary_view"]
    supplemental = result["components"]["supplemental_view"]

    assert primary["counts"] == {"positive": 1, "negative": 1, "directional": 2}
    assert primary["posterior"]["mean"] == pytest.approx(0.5)
    assert supplemental["counts"] == {"positive": 3, "negative": 1, "directional": 4}
    assert supplemental["posterior"]["mean"] == pytest.approx(0.625)
    assert result["components"]["authority_tier_counts"] == {"A": 1, "B": 1, "C": 0, "D": 2}
    tier_d = [item for item in result["contributions"] if item["authority_tier"] == "D"]
    assert tier_d
    assert all(not item["included_in_primary"] for item in tier_d)
    assert all(item["included_in_supplemental"] for item in tier_d)


def test_bayesian_contradictory_directional_input_remains_centered() -> None:
    contributions = [
        _directional("positive-1", "positive", "A"),
        _directional("positive-2", "positive", "B"),
        _directional("negative-1", "negative", "A"),
        _directional("negative-2", "negative", "B"),
    ]
    result = BayesianShrinkageMethod().evaluate(_manifest(contributions))
    primary = result["components"]["primary_view"]

    assert primary["counts"] == {"positive": 2, "negative": 2, "directional": 4}
    assert primary["posterior"]["mean"] == pytest.approx(0.5)
    assert primary["posterior"]["median"] == pytest.approx(0.5)
    interval = primary["posterior"]["credible_interval_90"]
    assert interval["lower"] < 0.3
    assert interval["upper"] > 0.7


def test_information_method_exposes_2x2_jeffreys_and_deterministic_reference() -> None:
    contributions = []
    for cell in ("a", "d"):
        contributions.extend(_cell(f"{cell}-{index}", cell) for index in range(8))
    manifest = _manifest(contributions)
    original = copy.deepcopy(manifest)
    method = OutcomeConditionedInformationMethod()

    first = method.evaluate(manifest, {"permutation_iterations": 300})
    second = method.evaluate(manifest, {"permutation_iterations": 300})
    primary = first["components"]["primary_view"]

    assert first == second
    assert manifest == original
    assert primary["contingency_table"] == {"a": 8, "b": 0, "c": 0, "d": 8}
    assert primary["smoothed_table"] == {"a": 8.5, "b": 0.5, "c": 0.5, "d": 8.5}
    assert primary["jeffreys_smoothing_per_cell"] == 0.5
    assert primary["effective_sample_size"] == 16
    assert primary["adjusted_normalized_information"] > 0.1
    reference = primary["permutation_reference"]
    assert reference["seed"] == method.default_permutation_seed
    assert reference["iterations"] == 300
    assert reference["algorithm"] == "fixed_seed_outcome_label_permutation_v1"


def test_information_method_resists_frequent_but_uninformative_subject() -> None:
    contributions = []
    for cell in ("a", "b", "c", "d"):
        contributions.extend(_cell(f"{cell}-{index}", cell) for index in range(20))
    result = OutcomeConditionedInformationMethod().evaluate(
        _manifest(contributions), {"permutation_iterations": 300}
    )
    primary = result["components"]["primary_view"]

    assert primary["contingency_table"] == {"a": 20, "b": 20, "c": 20, "d": 20}
    assert primary["raw_mutual_information_bits"] == pytest.approx(0.0, abs=1e-15)
    assert primary["observed_normalized_information"] == pytest.approx(0.0, abs=1e-15)
    assert primary["adjusted_normalized_information"] == pytest.approx(0.0, abs=1e-15)


def test_information_authority_views_keep_influenced_confirmations_supplemental() -> None:
    manifest = _manifest(
        [
            _cell("independent-a", "a", "A"),
            _cell("independent-d", "d", "B"),
            _cell("influenced-a", "a", "D"),
            _cell("influenced-b", "b", "D"),
        ]
    )
    result = OutcomeConditionedInformationMethod().evaluate(
        manifest, {"permutation_iterations": 100}
    )

    assert result["components"]["primary_view"]["contingency_table"] == {
        "a": 1,
        "b": 0,
        "c": 0,
        "d": 1,
    }
    assert result["components"]["supplemental_view"]["contingency_table"] == {
        "a": 2,
        "b": 1,
        "c": 0,
        "d": 1,
    }
    influenced = next(
        item for item in result["contributions"] if item["contribution_id"] == "influenced-a"
    )
    assert influenced["included_in_primary"] is False
    assert influenced["included_in_supplemental"] is True


@pytest.mark.parametrize("method_id", [BAYESIAN_METHOD_ID, INFORMATION_METHOD_ID])
def test_both_methods_preserve_the_identical_frozen_manifest_identity(method_id: str) -> None:
    contribution = {
        **_directional("shared-1", "positive", "A"),
        "information_cell": "a",
    }
    manifest = _manifest([contribution])
    config = {"permutation_iterations": 100} if method_id == INFORMATION_METHOD_ID else None

    result = evaluate_health_relevance_method(method_id, manifest, config)

    assert result["input_manifest_hash"] == MANIFEST_HASH
    assert result["input_snapshot_id"] == "snapshot-001"
    assert result["contributions"][0]["contribution_id"] == "shared-1"
