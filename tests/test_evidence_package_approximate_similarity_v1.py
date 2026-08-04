from __future__ import annotations

from copy import deepcopy

from app.services.evidence_package_fingerprint import (
    SIMILARITY_WEIGHTS,
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


def test_minimum_evidence_does_not_manufacture_a_score() -> None:
    package = _package("evaluated")
    package["primary_relationship"]["comparison_strength"] = None
    fingerprint = build_fingerprint(package)
    assert fingerprint.status.value == "unavailable"
    assert fingerprint.features == {}
    assert fingerprint.canonical_digest is None
