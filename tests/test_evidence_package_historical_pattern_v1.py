from __future__ import annotations

from app.services import baseline_analysis_repository as repository
from app.services.evidence_package_fingerprint import (
    ALGORITHM_VERSION,
    ApproximateSimilarityResponse,
    ApproximateSimilarityResult,
    ExactMatchObservation,
    ExactMatchResult,
    ExactMatchStatus,
    HistoricalPatternClassification,
    SimilarityProvenance,
    SimilarityStatus,
)


def _package(package_id: str, timestamp: str) -> dict:
    return {"id": package_id, "latest_evaluated_at": timestamp, "revision": 1}


def _exact(*candidate_ids: str, eligible: int | None = None) -> ExactMatchResult:
    matches = [ExactMatchObservation(
        observation_id=f"observation-{candidate}", evaluated_package_id="evaluated",
        evaluated_fingerprint_id="fp-evaluated", prior_package_id=candidate,
        prior_fingerprint_id=f"fp-{candidate}", canonical_digest="digest",
        algorithm_version=ALGORITHM_VERSION, eligibility_basis="governed",
        scope_basis="governed", temporal_basis="governed", evidence_refs=[f"ev-{candidate}"], limitations=[],
    ) for candidate in candidate_ids]
    count = len(candidate_ids) if eligible is None else eligible
    status = ExactMatchStatus.exact_match if matches else (ExactMatchStatus.no_exact_match if count else ExactMatchStatus.insufficient_history)
    return ExactMatchResult(status=status, evaluated_package_id="evaluated", evaluated_fingerprint_id="fp-evaluated", matches=matches, eligible_history_count=count)


def _similar(candidate: str, score: float | None, status: SimilarityStatus = SimilarityStatus.supported_similarity) -> ApproximateSimilarityResult:
    return ApproximateSimilarityResult(
        evaluated_package_id="evaluated", evaluated_fingerprint_id="fp-evaluated",
        candidate_package_id=candidate, candidate_fingerprint_id=f"fp-{candidate}",
        overall_similarity=score, overall_status=status, supported_weight=.8,
        dimensions=[], supported_dimensions=["system_identity"], unavailable_dimensions=["persistence_similarity"],
        excluded_dimensions=[], limitations=[], provenance=SimilarityProvenance(
            eligibility_basis="governed", scope_basis="governed", temporal_basis="governed", score_formula="governed"
        ),
    )


def _install(monkeypatch, exact, results=(), approximate_status=None):
    packages = {
        "evaluated": _package("evaluated", "2026-08-04T12:00:00Z"),
        "early": _package("early", "2026-08-01T12:00:00Z"),
        "middle": _package("middle", "2026-08-02T12:00:00Z"),
        "late": _package("late", "2026-08-03T12:00:00Z"),
        "latest": _package("latest", "2026-08-03T18:00:00Z"),
    }
    monkeypatch.setattr(repository, "read_evidence_package_by_id", packages.get)
    monkeypatch.setattr(repository, "read_exact_fingerprint_matches", lambda _: exact)
    status = approximate_status or repository.aggregate_similarity_status(list(results))
    approximate = ApproximateSimilarityResponse(
        evaluated_package_id="evaluated", evaluated_fingerprint_id="fp-evaluated",
        overall_status=status, eligible_history_count=exact.eligible_history_count, results=list(results),
    )
    monkeypatch.setattr(repository, "read_approximate_fingerprint_similarity", lambda _: approximate)


def test_insufficient_history_and_no_supported_history_are_distinct(monkeypatch) -> None:
    _install(monkeypatch, _exact())
    assert repository.read_historical_pattern_classification("evaluated").classification == HistoricalPatternClassification.insufficient_history

    unsupported = _similar("early", .4, SimilarityStatus.no_supported_similarity)
    _install(monkeypatch, _exact(eligible=1), [unsupported])
    result = repository.read_historical_pattern_classification("evaluated")
    assert result.classification == HistoricalPatternClassification.no_supported_historical_pattern
    assert result.no_supported_similarity_candidate_count == 1


def test_exact_precedes_approximate_and_preserves_separate_evidence(monkeypatch) -> None:
    _install(monkeypatch, _exact("early", eligible=2), [_similar("late", .99)])
    result = repository.read_historical_pattern_classification("evaluated")
    assert result.classification == HistoricalPatternClassification.exact_historical_match
    assert [item.match_type for item in result.supporting_matches] == ["exact", "approximate"]
    assert result.strongest_supported_match.candidate_package_id == "early"
    assert result.evidence_refs == ["ev-early"]


def test_approximate_ranking_uses_score_then_earliest_time(monkeypatch) -> None:
    _install(monkeypatch, _exact(eligible=2), [_similar("late", .9), _similar("early", .9)])
    result = repository.read_historical_pattern_classification("evaluated")
    assert result.classification == HistoricalPatternClassification.similar_historical_pattern
    assert [item.candidate_package_id for item in result.supporting_matches] == ["early", "late"]
    match = result.strongest_supported_match
    assert match.supported_dimensions == ["system_identity"]
    assert match.unavailable_dimensions == ["persistence_similarity"]
    assert match.supported_weight == .8


def test_excluded_only_history_is_unavailable_with_preserved_counts(monkeypatch) -> None:
    _install(monkeypatch, _exact(eligible=1), [_similar("early", None, SimilarityStatus.excluded)])
    result = repository.read_historical_pattern_classification("evaluated")
    assert result.classification == HistoricalPatternClassification.unavailable
    assert result.excluded_candidate_count == 1
    assert result.insufficient_evidence_candidate_count == 0
    assert result.no_supported_similarity_candidate_count == 0
    assert result.eligible_history_count == 1
    assert result.strongest_supported_match is None
    assert result.supporting_matches == []
    assert result.evidence_refs == []
    assert result.limitations == ["Eligible history exists, but no candidate had sufficient comparable evidence for historical pattern classification."]


def test_insufficient_only_history_is_unavailable(monkeypatch) -> None:
    _install(monkeypatch, _exact(eligible=1), [_similar("early", None, SimilarityStatus.insufficient_similarity_evidence)])
    result = repository.read_historical_pattern_classification("evaluated")
    assert result.classification == HistoricalPatternClassification.unavailable
    assert result.excluded_candidate_count == 0
    assert result.insufficient_evidence_candidate_count == 1


def test_excluded_and_insufficient_only_history_is_unavailable(monkeypatch) -> None:
    results = [
        _similar("early", None, SimilarityStatus.excluded),
        _similar("late", None, SimilarityStatus.insufficient_similarity_evidence),
    ]
    _install(monkeypatch, _exact(eligible=2), results)
    result = repository.read_historical_pattern_classification("evaluated")
    assert result.classification == HistoricalPatternClassification.unavailable
    assert result.excluded_candidate_count == 1
    assert result.insufficient_evidence_candidate_count == 1
    assert result.eligible_history_count == 2


def test_valid_negative_with_excluded_or_insufficient_history_is_no_supported_pattern(monkeypatch) -> None:
    for limited_status in (SimilarityStatus.excluded, SimilarityStatus.insufficient_similarity_evidence):
        results = [
            _similar("early", .4, SimilarityStatus.no_supported_similarity),
            _similar("late", None, limited_status),
        ]
        _install(monkeypatch, _exact(eligible=2), results)
        result = repository.read_historical_pattern_classification("evaluated")
        assert result.classification == HistoricalPatternClassification.no_supported_historical_pattern
        assert result.no_supported_similarity_candidate_count == 1
        assert result.excluded_candidate_count == int(limited_status == SimilarityStatus.excluded)
        assert result.insufficient_evidence_candidate_count == int(limited_status == SimilarityStatus.insufficient_similarity_evidence)


def test_positive_precedence_over_all_other_candidate_statuses(monkeypatch) -> None:
    results = [
        _similar("early", .4, SimilarityStatus.no_supported_similarity),
        _similar("middle", None, SimilarityStatus.excluded),
        _similar("late", .9, SimilarityStatus.supported_similarity),
        _similar("latest", None, SimilarityStatus.insufficient_similarity_evidence),
    ]
    _install(monkeypatch, _exact(eligible=4), results)
    similar = repository.read_historical_pattern_classification("evaluated")
    assert similar.classification == HistoricalPatternClassification.similar_historical_pattern
    assert (similar.no_supported_similarity_candidate_count, similar.excluded_candidate_count, similar.insufficient_evidence_candidate_count) == (1, 1, 1)

    _install(monkeypatch, _exact("early", eligible=4), results)
    assert repository.read_historical_pattern_classification("evaluated").classification == HistoricalPatternClassification.exact_historical_match


def test_source_unavailability_fails_closed(monkeypatch) -> None:
    _install(monkeypatch, ExactMatchResult(status="unavailable", evaluated_package_id="evaluated"), approximate_status=SimilarityStatus.unavailable)
    result = repository.read_historical_pattern_classification("evaluated")
    assert result.classification == HistoricalPatternClassification.unavailable
    assert result.supporting_matches == []


def test_human_readable_output_uses_only_evidence_bounded_language(monkeypatch) -> None:
    _install(monkeypatch, _exact("early"), [_similar("early", 1.0)])
    text = repository.read_historical_pattern_classification("evaluated").model_dump_json().lower()
    for prohibited in ("root cause", "diagnosis", "topology", "propagat", "same fault", "duplicate incident", "happened before", "recurr"):
        assert prohibited not in text


def test_repeat_reads_are_equal_and_package_revision_is_unchanged(monkeypatch) -> None:
    _install(monkeypatch, _exact("early"), [_similar("early", 1.0)])
    assert repository.read_historical_pattern_classification("evaluated") == repository.read_historical_pattern_classification("evaluated")
    assert repository.read_evidence_package_by_id("evaluated")["revision"] == 1


def test_prior_lifecycle_state_does_not_change_classification(monkeypatch) -> None:
    outputs = []
    for lifecycle_status in ("OPEN", "ACKNOWLEDGED", "RESOLVED"):
        _install(monkeypatch, _exact("early"), [_similar("early", 1.0)])
        original_read = repository.read_evidence_package_by_id

        def read(package_id, original_read=original_read, lifecycle_status=lifecycle_status):
            package = original_read(package_id)
            return {**package, "lifecycle": {"status": lifecycle_status}} if package else None

        monkeypatch.setattr(repository, "read_evidence_package_by_id", read)
        outputs.append(repository.read_historical_pattern_classification("evaluated").model_dump())
    assert outputs[0] == outputs[1] == outputs[2]
