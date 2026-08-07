from datetime import UTC, datetime, timedelta

import pytest

from neraium_intelligence import (
    ConfidenceDimension,
    ConfidenceLevel,
    DataQuality,
    EvidenceItem,
    EvidencePackageAssembler,
    FeatureSpec,
    MemoryQuery,
    MemoryRecord,
    PackageProvenance,
    Unknown,
    WeightedSimilarityEngine,
    assess_evidence_support,
)


NOW = datetime(2024, 3, 20, 15, 0, tzinfo=UTC)


def record(record_id: str, when: datetime, value: float, session: str) -> MemoryRecord:
    return MemoryRecord(
        record_id=record_id,
        subject="subject-a",
        observed_at=when,
        session_key=session,
        features={"movement": value, "context": 0.5},
    )


def test_similarity_is_explainable_and_excludes_future_and_same_session() -> None:
    engine = WeightedSimilarityEngine(
        [
            FeatureSpec(name="movement", weight=0.7, scale=0.02, label="Movement", required=True),
            FeatureSpec(name="context", weight=0.3, scale=0.5, label="Context"),
        ]
    )
    query = MemoryQuery(
        subject="subject-a",
        observed_at=NOW,
        session_key="2024-03-20",
        features={"movement": 0.01, "context": 0.5},
    )
    result = engine.retrieve(
        query,
        [
            record("prior", NOW - timedelta(days=1), 0.011, "2024-03-19"),
            record("same-session", NOW - timedelta(minutes=5), 0.01, "2024-03-20"),
            record("future", NOW + timedelta(minutes=1), 0.01, "2024-03-21"),
        ],
    )
    assert [match.record.record_id for match in result.matches] == ["prior"]
    assert result.matches[0].components[0].normalized_difference == pytest.approx(0.05)


def test_missing_required_feature_does_not_create_similarity() -> None:
    engine = WeightedSimilarityEngine(
        [FeatureSpec(name="movement", weight=1.0, scale=0.02, label="Movement", required=True)]
    )
    match = engine.compare(
        MemoryQuery(subject="subject-a", observed_at=NOW, features={"movement": None}),
        record("prior", NOW - timedelta(days=1), 0.01, "prior"),
    )
    assert match.status == "insufficient_evidence"
    assert match.similarity is None


def test_support_is_not_reported_as_probability() -> None:
    support = assess_evidence_support(
        comparable_count=8,
        similarities=[0.8, 0.7, 0.75],
        data_completeness=0.95,
    )
    assert support.level in {ConfidenceLevel.medium, ConfidenceLevel.high}
    assert "not an outcome probability" in support.reason


def test_evidence_package_is_deterministic_and_rejects_dangling_refs() -> None:
    evidence = EvidenceItem(
        id="ev-1",
        kind="observation",
        label="Observed change",
        summary="A supported change was observed.",
        source="test",
    )
    provenance = PackageProvenance(
        analysis_version="test-v1",
        algorithm_version="test-algorithm-v1",
        source_dataset_ids=["dataset-a"],
        generated_at=NOW,
    )
    assembler = EvidencePackageAssembler()
    kwargs = dict(
        domain="test",
        subject="subject-a",
        observed_at=NOW,
        title="Evidence-backed observation",
        observed_behavior=["A change occurred."],
        persistence={"status": "unknown"},
        current_context={},
        supporting_evidence=[evidence],
        contradicting_evidence=[],
        historical_comparisons=[],
        confidence={
            "support": ConfidenceDimension(
                level="unknown", reason="Not enough history.", method="test", evidence_refs=["ev-1"]
            )
        },
        important_differences=[],
        data_quality=DataQuality(status="usable", completeness=1.0, source="test"),
        limitations=[],
        unknowns=[Unknown(question="Will it persist?", reason="Future evidence is unavailable.")],
        provenance=provenance,
    )
    first = assembler.assemble(**kwargs)
    second = assembler.assemble(**kwargs)
    assert first.id == second.id
    kwargs["confidence"] = {
        "support": ConfidenceDimension(
            level="unknown", reason="No evidence.", method="test", evidence_refs=["missing"]
        )
    }
    with pytest.raises(ValueError, match="not present"):
        assembler.assemble(**kwargs)
