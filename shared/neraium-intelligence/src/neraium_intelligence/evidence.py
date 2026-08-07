from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence
from uuid import UUID, uuid5

from .contracts import (
    ConfidenceDimension,
    ConfidenceLevel,
    DataQuality,
    EvidenceItem,
    EvidencePackage,
    HistoricalComparison,
    Limitation,
    PackageProvenance,
    Unknown,
)


PACKAGE_NAMESPACE = UUID("e26499d9-7bd8-423e-8b67-e61e482848d1")


def assess_evidence_support(
    *,
    comparable_count: int,
    similarities: Sequence[float],
    data_completeness: float,
    contradiction_count: int = 0,
    evidence_refs: Sequence[str] = (),
) -> ConfidenceDimension:
    """Assess retrieval support, not the likelihood of a future outcome."""

    usable = [value for value in similarities if 0.0 <= value <= 1.0]
    if comparable_count < 3 or not usable:
        return ConfidenceDimension(
            level=ConfidenceLevel.unknown,
            score=None,
            reason="Too few comparable historical states support a retrieval assessment.",
            method="retrieval_support_rules_v1",
            evidence_refs=list(evidence_refs),
        )
    mean_similarity = sum(usable) / len(usable)
    count_support = min(comparable_count / 12.0, 1.0)
    contradiction_factor = max(0.0, 1.0 - min(contradiction_count / 5.0, 0.5))
    score = mean_similarity * 0.55 + count_support * 0.25 + data_completeness * 0.20
    score *= contradiction_factor
    score = round(max(0.0, min(score, 1.0)), 6)
    level = ConfidenceLevel.high if score >= 0.75 else ConfidenceLevel.medium if score >= 0.55 else ConfidenceLevel.low
    return ConfidenceDimension(
        level=level,
        score=score,
        reason=(
            f"Support reflects {comparable_count} historical states, their descriptive similarity, "
            "data completeness, and contradicting evidence. It is not an outcome probability."
        ),
        method="retrieval_support_rules_v1",
        evidence_refs=list(evidence_refs),
    )


class EvidencePackageAssembler:
    """Build deterministic, evidence-referenced records for any Neraium domain."""

    def assemble(
        self,
        *,
        domain: str,
        subject: str,
        observed_at: datetime,
        title: str,
        observed_behavior: Sequence[str],
        persistence: dict[str, Any],
        current_context: dict[str, Any],
        supporting_evidence: Sequence[EvidenceItem],
        contradicting_evidence: Sequence[EvidenceItem],
        historical_comparisons: Sequence[HistoricalComparison],
        confidence: dict[str, ConfidenceDimension],
        important_differences: Sequence[str],
        data_quality: DataQuality,
        limitations: Sequence[Limitation],
        unknowns: Sequence[Unknown],
        provenance: PackageProvenance,
    ) -> EvidencePackage:
        all_evidence = [*supporting_evidence, *contradicting_evidence]
        evidence_ids = [item.id for item in all_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique within a package")
        known_refs = set(evidence_ids)
        referenced = {
            ref
            for dimension in confidence.values()
            for ref in dimension.evidence_refs
        } | {
            ref
            for comparison in historical_comparisons
            for ref in comparison.evidence_refs
        } | {
            ref
            for limitation in limitations
            for ref in limitation.evidence_refs
        }
        missing = sorted(referenced - known_refs)
        if missing:
            raise ValueError(f"evidence references are not present in package: {', '.join(missing)}")
        identity = "|".join(
            [domain, subject, observed_at.isoformat(), provenance.analysis_version, provenance.algorithm_version]
        )
        return EvidencePackage(
            id=f"evp-{uuid5(PACKAGE_NAMESPACE, identity)}",
            domain=domain,
            subject=subject,
            observed_at=observed_at,
            title=title,
            observed_behavior=list(observed_behavior),
            persistence=persistence,
            current_context=current_context,
            supporting_evidence=list(supporting_evidence),
            contradicting_evidence=list(contradicting_evidence),
            historical_comparisons=list(historical_comparisons),
            confidence=confidence,
            important_differences=list(important_differences),
            data_quality=data_quality,
            limitations=list(limitations),
            unknowns=list(unknowns),
            provenance=provenance,
        )

