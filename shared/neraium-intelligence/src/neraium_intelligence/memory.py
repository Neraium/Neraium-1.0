from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Protocol, Sequence

from pydantic import Field, field_validator

from .contracts import SimilarityComponent, StrictModel


class FeatureSpec(StrictModel):
    name: str
    weight: float
    scale: float
    label: str
    required: bool = False

    @field_validator("weight", "scale")
    @classmethod
    def positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("feature weight and scale must be positive")
        return value


class MemoryRecord(StrictModel):
    record_id: str
    subject: str
    observed_at: datetime
    session_key: str | None = None
    features: dict[str, float | None]
    context: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class MemoryQuery(StrictModel):
    subject: str
    observed_at: datetime
    session_key: str | None = None
    features: dict[str, float | None]
    context: dict[str, Any] = Field(default_factory=dict)


class MemoryMatch(StrictModel):
    record: MemoryRecord
    similarity: float | None
    status: str
    supported_weight: float
    components: list[SimilarityComponent]


class SimilarityResult(StrictModel):
    status: str
    matches: list[MemoryMatch]
    eligible_count: int
    limitations: list[str] = Field(default_factory=list)
    algorithm_version: str = "explainable-weighted-distance-v1"


class BehavioralMemoryRepository(Protocol):
    """Persistence boundary. Domain applications decide how records are stored."""

    def append(self, records: Sequence[MemoryRecord]) -> None: ...

    def before(self, observed_at: datetime, *, subject: str | None = None) -> list[MemoryRecord]: ...


class WeightedSimilarityEngine:
    """Transparent weighted distance with strict temporal eligibility.

    Feature scales and weights are domain-owned configuration. Missing dimensions
    are never treated as zero-distance, and candidates with too little supported
    feature weight do not receive a similarity score.
    """

    def __init__(
        self,
        specs: Sequence[FeatureSpec],
        *,
        minimum_supported_weight: float = 0.7,
    ) -> None:
        if not specs:
            raise ValueError("at least one feature specification is required")
        total = sum(spec.weight for spec in specs)
        self.specs = [spec.model_copy(update={"weight": spec.weight / total}) for spec in specs]
        if not 0 < minimum_supported_weight <= 1:
            raise ValueError("minimum_supported_weight must be in (0, 1]")
        self.minimum_supported_weight = minimum_supported_weight

    def compare(self, query: MemoryQuery, candidate: MemoryRecord) -> MemoryMatch:
        components: list[SimilarityComponent] = []
        weighted_score = 0.0
        supported_weight = 0.0
        required_missing: list[str] = []
        for spec in self.specs:
            current = query.features.get(spec.name)
            historical = candidate.features.get(spec.name)
            if not _finite(current) or not _finite(historical):
                if spec.required:
                    required_missing.append(spec.name)
                components.append(
                    SimilarityComponent(
                        feature=spec.name,
                        status="unavailable",
                        weight=spec.weight,
                        current_value=current if _finite(current) else None,
                        historical_value=historical if _finite(historical) else None,
                        explanation=f"{spec.label} was unavailable for one or both states.",
                    )
                )
                continue
            normalized = abs(float(current) - float(historical)) / spec.scale
            score = math.exp(-normalized)
            supported_weight += spec.weight
            weighted_score += score * spec.weight
            components.append(
                SimilarityComponent(
                    feature=spec.name,
                    status="supported",
                    weight=spec.weight,
                    score=round(score, 8),
                    current_value=float(current),
                    historical_value=float(historical),
                    normalized_difference=round(normalized, 8),
                    explanation=(
                        f"{spec.label}: normalized absolute difference {normalized:.3f}; "
                        f"component similarity {score:.3f}."
                    ),
                )
            )
        status = "comparable"
        similarity: float | None = round(weighted_score, 8)
        if required_missing or supported_weight + 1e-12 < self.minimum_supported_weight:
            status = "insufficient_evidence"
            similarity = None
        return MemoryMatch(
            record=candidate,
            similarity=similarity,
            status=status,
            supported_weight=round(supported_weight, 8),
            components=components,
        )

    def retrieve(
        self,
        query: MemoryQuery,
        candidates: Sequence[MemoryRecord],
        *,
        limit: int = 10,
        require_prior_session: bool = True,
    ) -> SimilarityResult:
        eligible = [
            candidate
            for candidate in candidates
            if candidate.observed_at < query.observed_at
            and candidate.subject == query.subject
            and (
                not require_prior_session
                or query.session_key is None
                or candidate.session_key != query.session_key
            )
        ]
        matches = [self.compare(query, candidate) for candidate in eligible]
        comparable = [match for match in matches if match.similarity is not None]
        comparable.sort(key=lambda match: (-float(match.similarity or 0.0), match.record.observed_at))
        status = "matched" if comparable else "insufficient_history"
        limitations = [] if comparable else [
            "No temporally eligible historical state had enough supported comparison dimensions."
        ]
        return SimilarityResult(
            status=status,
            matches=comparable[: max(0, limit)],
            eligible_count=len(eligible),
            limitations=limitations,
        )


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value))

