from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


EVIDENCE_PACKAGE_SCHEMA_VERSION = "neraium-evidence-package-v1"
NON_CAUSAL_NOTE = (
    "Historical similarity is descriptive. It does not establish cause, predict recurrence, "
    "or guarantee a future outcome."
)


class StrictModel(BaseModel):
    """A stable application boundary: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class ConfidenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class EvidenceItem(StrictModel):
    id: str
    kind: str
    label: str
    summary: str
    value: Any = None
    unit: str | None = None
    observed_at: datetime | None = None
    source: str
    quality: str = "usable"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConfidenceDimension(StrictModel):
    """Support for one claim dimension, never a forecast probability."""

    level: ConfidenceLevel = ConfidenceLevel.unknown
    score: float | None = None
    reason: str
    method: str
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("score")
    @classmethod
    def score_is_unit_interval(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("confidence support scores must be between 0 and 1")
        return value


class Limitation(StrictModel):
    category: str
    description: str
    evidence_refs: list[str] = Field(default_factory=list)


class Unknown(StrictModel):
    question: str
    reason: str


class SimilarityComponent(StrictModel):
    feature: str
    status: str
    weight: float
    score: float | None = None
    current_value: float | None = None
    historical_value: float | None = None
    normalized_difference: float | None = None
    explanation: str


class HistoricalComparison(StrictModel):
    reference_id: str
    subject: str
    observed_at: datetime
    similarity: float | None = None
    status: str
    components: list[SimilarityComponent] = Field(default_factory=list)
    matched_relationships: list[str] = Field(default_factory=list)
    important_differences: list[str] = Field(default_factory=list)
    historical_outcomes: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    non_causal_note: str = NON_CAUSAL_NOTE

    @field_validator("similarity")
    @classmethod
    def similarity_is_unit_interval(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("similarity must be between 0 and 1")
        return value


class DataQuality(StrictModel):
    status: str
    completeness: float
    issues: list[str] = Field(default_factory=list)
    is_synthetic: bool = False
    source: str

    @field_validator("completeness")
    @classmethod
    def completeness_is_unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("completeness must be between 0 and 1")
        return value


class PackageProvenance(StrictModel):
    analysis_version: str
    algorithm_version: str
    source_dataset_ids: list[str]
    generated_at: datetime
    replay_as_of: datetime | None = None


class EvidencePackage(StrictModel):
    """Domain-neutral record produced by a Neraium intelligence application."""

    id: str
    schema_version: str = EVIDENCE_PACKAGE_SCHEMA_VERSION
    domain: str
    subject: str
    observed_at: datetime
    title: str
    observed_behavior: list[str]
    persistence: dict[str, Any]
    current_context: dict[str, Any]
    supporting_evidence: list[EvidenceItem]
    contradicting_evidence: list[EvidenceItem]
    historical_comparisons: list[HistoricalComparison]
    confidence: dict[str, ConfidenceDimension]
    important_differences: list[str]
    data_quality: DataQuality
    limitations: list[Limitation]
    unknowns: list[Unknown]
    provenance: PackageProvenance
    decision_boundary: str = (
        "Decision support only. This package is not an instruction to trade, operate, or automate a decision."
    )

