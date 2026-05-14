from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ONTOLOGY_QUEUE_STATUSES = ("PROPOSED", "NEEDS_EVIDENCE", "UNDER_REVIEW", "VALIDATED", "REJECTED", "DEPRECATED")


@dataclass(frozen=True)
class OntologyProposal:
    proposal_id: str
    proposal_type: str
    summary: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OntologyConflict:
    conflict_id: str
    concept_a: str
    concept_b: str
    conflict_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OntologyValidationGap:
    gap_id: str
    missing_requirement: str
    replay_gap: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OntologyGovernanceReview:
    review_id: str
    reviewer_role: str
    decision: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OntologyPromotionQueue:
    items: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_autonomous_ontology_governance(intelligence: dict[str, Any]) -> dict[str, Any]:
    archetypes = [item.get("name", "") for item in intelligence.get("active_archetypes", [])]
    proposals = [
        OntologyProposal(
            proposal_id="proposal-1",
            proposal_type="new_primitive",
            summary="propose SYNCHRONIZATION_VARIANCE primitive for delayed reconvergence behavior",
            status="PROPOSED",
        ).to_dict(),
        OntologyProposal(
            proposal_id="proposal-2",
            proposal_type="deprecate_weak_archetype",
            summary="flag low-evidence archetype for evidence expansion before continued use",
            status="NEEDS_EVIDENCE",
        ).to_dict(),
    ]
    conflicts = [
        OntologyConflict(
            conflict_id="conflict-1",
            concept_a="COMPENSATION_MASKING",
            concept_b="CASCADING_COMPENSATION",
            conflict_reason="overlapping semantics with incomplete disambiguation constraints",
        ).to_dict()
    ]
    gaps = [
        OntologyValidationGap(
            gap_id="gap-1",
            missing_requirement="cross-domain replay corroboration",
            replay_gap="insufficient replay references for universal promotion",
        ).to_dict()
    ]
    reviews = [
        OntologyGovernanceReview(
            review_id="review-1",
            reviewer_role="ontology_custodian",
            decision="UNDER_REVIEW",
            notes="proposal queued for evidence sufficiency validation.",
        ).to_dict()
    ]
    queue = OntologyPromotionQueue(items=proposals).to_dict()
    return {
        "active_archetypes": archetypes,
        "proposals": proposals,
        "conflicts": conflicts,
        "validation_gaps": gaps,
        "reviews": reviews,
        "promotion_queue": queue,
    }

