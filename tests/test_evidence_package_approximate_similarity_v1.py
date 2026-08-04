from __future__ import annotations

from copy import deepcopy

from app.services import baseline_analysis_repository as repository
from app.services.dataset_scope import current_dataset_scope
from app.services.evidence_package_fingerprint import (
    ApproximateSimilarityResult,
    SIMILARITY_WEIGHTS,
    SimilarityStatus,
    aggregate_similarity_status,
    build_fingerprint,
    compare_fingerprints,
)
EXPECTED_DIMENSIONS = list(SIMILARITY_WEIGHTS)


def _package(package_id: str) -> dict:
    return {
        "id": package_id, "schema_version": "evidence-package-v1", "revision": 1,
        "organization_id": "tenant-a", "portfolio_id": "workspace-a", "system_id": "system-a",
        "condition_type": "persistent_relationship_change",
        "primary_relationship": {
            "left_variable": "signal-z", "right_variable": "signal-a", "relationship_type": "correlation",
            "baseline_strength": 0.125, "comparison_strength": 0.25,
            "signed_change": 0.125, "absolute_change": 0.125, "persistence_score": None,
        },
        "operating_context": None,
        "supporting_evidence": [
            {"id": f"ev-{name}", "quality_status": "recorded", "calculation_version": "calc-v1"}
            for name in ("baseline-strength", "comparison-strength", "absolute-change")
        ],
    }


def _fingerprint(package_id: str, **relationship_changes):
    package = _package(package_id)
    package["primary_relationship"].update(relationship_changes)
    return build_fingerprint(package)


def test_scoring_is_deterministic_ordered_and_reconstructable_without_renormalization() -> None:
    evaluated = _fingerprint("evaluated")
    candidate = _fingerprint("candidate", comparison_strength=0.5, signed_change=-0.2, absolute_change=0.2)
    first = compare_fingerprints(evaluated, candidate)
    second = compare_fingerprints(evaluated, candidate)

    assert first == second
    assert [item.name for item in first.dimensions] == EXPECTED_DIMENSIONS
    assert sum(item.weight for item in first.dimensions) == 1.0
    reconstructed = round(sum(item.score * item.weight for item in first.dimensions if item.score is not None), 8)
    assert first.overall_similarity == reconstructed
    assert first.supported_weight == 0.80
    assert first.required_supported_weight == 0.80
    assert first.unavailable_dimensions == [
        "relationship_direction", "persistence_similarity", "operating_context_compatibility"
    ]
    assert first.overall_status.value in {"supported_similarity", "no_supported_similarity"}


def test_optional_dimensions_are_used_only_when_available_for_both() -> None:
    evaluated_package = _package("evaluated")
    candidate_package = deepcopy(evaluated_package)
    candidate_package["id"] = "candidate"
    evaluated_package["primary_relationship"]["persistence_score"] = 0.75
    candidate_package["primary_relationship"]["persistence_score"] = 0.5
    for package in (evaluated_package, candidate_package):
        package["supporting_evidence"].append({"id": "ev-persistence", "quality_status": "recorded", "calculation_version": "calc-v1"})
    result = compare_fingerprints(build_fingerprint(evaluated_package), build_fingerprint(candidate_package))
    persistence = next(item for item in result.dimensions if item.name == "persistence_similarity")
    context = next(item for item in result.dimensions if item.name == "operating_context_compatibility")
    assert persistence.status.value == "supported"
    assert persistence.score == 0.75
    assert context.status.value == "unavailable"
    assert context.score is None


def test_different_system_is_excluded_instead_of_scored() -> None:
    evaluated = _fingerprint("evaluated")
    candidate_package = _package("candidate")
    candidate_package["system_id"] = "system-b"
    result = compare_fingerprints(evaluated, build_fingerprint(candidate_package))
    assert result.overall_status.value == "excluded"
    assert result.overall_similarity is None
    assert result.supported_dimensions == []
    assert result.excluded_dimensions == EXPECTED_DIMENSIONS


def test_valid_eligible_comparison_with_too_little_weight_has_first_class_status() -> None:
    evaluated = _fingerprint("evaluated")
    candidate = _fingerprint("candidate")
    for fingerprint in (evaluated, candidate):
        fingerprint.features["relationship"].pop("comparison_strength")
        fingerprint.features["relationship"].pop("absolute_change")
        fingerprint.features["relationship"].pop("signed_change")
    result = compare_fingerprints(evaluated, candidate)
    assert result.overall_status == SimilarityStatus.insufficient_similarity_evidence
    assert result.overall_similarity is None
    assert result.supported_weight == 0.50
    assert result.required_supported_weight == 0.80
    assert "Supported dimension weight 0.50 did not meet required minimum 0.80." in result.limitations


def test_status_precedence_is_deterministic() -> None:
    template = compare_fingerprints(_fingerprint("evaluated"), _fingerprint("candidate"))

    def with_status(status: SimilarityStatus) -> ApproximateSimilarityResult:
        return template.model_copy(update={"overall_status": status})

    insufficient = with_status(SimilarityStatus.insufficient_similarity_evidence)
    excluded = with_status(SimilarityStatus.excluded)
    unsupported = with_status(SimilarityStatus.no_supported_similarity)
    supported = with_status(SimilarityStatus.supported_similarity)
    assert aggregate_similarity_status([excluded, insufficient]) == SimilarityStatus.insufficient_similarity_evidence
    assert aggregate_similarity_status([insufficient, unsupported]) == SimilarityStatus.no_supported_similarity
    assert aggregate_similarity_status([unsupported, supported, insufficient]) == SimilarityStatus.supported_similarity
    assert aggregate_similarity_status([insufficient, insufficient]) == SimilarityStatus.insufficient_similarity_evidence


def test_different_primary_pair_is_excluded_without_partial_score() -> None:
    evaluated = _fingerprint("evaluated")
    candidate_package = _package("candidate")
    candidate_package["primary_relationship"].update({"left_variable": "signal-b", "right_variable": "signal-c"})
    candidate_package["relationship_label"] = "signal-z / signal-a"
    result = compare_fingerprints(evaluated, build_fingerprint(candidate_package))
    assert result.overall_status == SimilarityStatus.excluded
    assert result.overall_similarity is None
    assert all(item.status.value == "excluded" for item in result.dimensions)
    pair = next(item for item in result.dimensions if item.name == "primary_signal_pair")
    assert pair.exclusion_reason == "same_primary_signal_pair_required_v1"


def test_symmetric_reversal_is_eligible_but_directed_reversal_is_excluded() -> None:
    symmetric = _package("evaluated")
    reversed_symmetric = deepcopy(symmetric)
    reversed_symmetric["id"] = "candidate"
    reversed_symmetric["primary_relationship"].update({"left_variable": "signal-a", "right_variable": "signal-z"})
    assert compare_fingerprints(build_fingerprint(symmetric), build_fingerprint(reversed_symmetric)).overall_status == SimilarityStatus.supported_similarity

    directed = _package("evaluated-directed")
    directed["primary_relationship"]["relationship_type"] = "model_edge"
    reversed_directed = deepcopy(directed)
    reversed_directed["id"] = "candidate-directed"
    reversed_directed["primary_relationship"].update({"left_variable": "signal-a", "right_variable": "signal-z"})
    directed_result = compare_fingerprints(build_fingerprint(directed), build_fingerprint(reversed_directed))
    assert directed_result.overall_status == SimilarityStatus.excluded
    assert directed_result.overall_similarity is None


def test_dimension_evidence_refs_are_narrow_and_never_fabricated() -> None:
    result = compare_fingerprints(_fingerprint("evaluated"), _fingerprint("candidate"))
    refs = {item.name: item.evidence_refs for item in result.dimensions}
    assert refs["relationship_strength_similarity"] == ["ev-baseline-strength", "ev-comparison-strength"]
    assert refs["relationship_change_magnitude"] == ["ev-absolute-change"]
    assert refs["relationship_change_direction"] == ["ev-baseline-strength", "ev-comparison-strength"]
    assert refs["system_identity"] == []
    assert len({tuple(value) for value in refs.values()}) > 2
    assert any("no typed supporting-evidence reference for system identity" in item for item in result.limitations)


def test_history_response_preserves_all_insufficient_status_and_repeat_read_equality(monkeypatch) -> None:
    scope = current_dataset_scope()
    evaluated_package = _package("evaluated")
    evaluated_package.update({
        "organization_id": scope.tenant_id, "portfolio_id": scope.workspace_id,
        "latest_evaluated_at": "2026-08-04T12:00:00Z",
    })
    candidate_package = deepcopy(evaluated_package)
    candidate_package.update({"id": "candidate", "latest_evaluated_at": "2026-08-03T12:00:00Z"})
    evaluated = build_fingerprint(evaluated_package)
    candidate = build_fingerprint(candidate_package)
    for fingerprint in (evaluated, candidate):
        for name in ("comparison_strength", "absolute_change", "signed_change"):
            fingerprint.features["relationship"].pop(name)

    packages = {"evaluated": evaluated_package, "candidate": candidate_package}
    monkeypatch.setattr(repository, "read_evidence_package_by_id", packages.get)
    monkeypatch.setattr(repository, "read_evidence_package_fingerprint", lambda package_id: evaluated if package_id == "evaluated" else candidate)
    monkeypatch.setattr(repository, "list_shared_state_prefix", lambda *args, **kwargs: [{
        **scope.as_dict(), "dataset_scope": scope.as_dict(),
        "organization_id": scope.tenant_id, "portfolio_id": scope.workspace_id,
        "system_id": "system-a", "algorithm_version": evaluated.algorithm_version,
        "package_id": "candidate", "evaluated_at": "2026-08-03T12:00:00Z",
        "fingerprint_id": candidate.fingerprint_id, "canonical_digest": candidate.canonical_digest,
    }])
    monkeypatch.setattr(repository, "_read", lambda *args, **kwargs: {
        "dataset_scope": scope.as_dict(), "fingerprint": candidate.model_dump(mode="json")
    })

    first = repository.read_approximate_fingerprint_similarity("evaluated")
    second = repository.read_approximate_fingerprint_similarity("evaluated")
    assert first == second
    assert first is not None
    assert first.overall_status == SimilarityStatus.insufficient_similarity_evidence
    assert first.results[0].overall_status == SimilarityStatus.insufficient_similarity_evidence
