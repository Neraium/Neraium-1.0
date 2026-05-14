from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ONTOLOGY_STATES = ("CANDIDATE", "UNDER_REVIEW", "VALIDATED", "REJECTED", "DEPRECATED")


@dataclass(frozen=True)
class OntologyExtensionCandidate:
    candidate_id: str
    name: str
    category: str
    evidence_basis: list[str]
    replay_references: list[str]
    state: str = "CANDIDATE"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OntologyReviewRecord:
    candidate_id: str
    reviewer: str
    state: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OntologyVersion:
    version: str
    active_candidates: list[str]
    validated_extensions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OntologyPromotionDecision:
    candidate_id: str
    approved: bool
    state: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvolvingOntologyEngine:
    def propose_candidates(self, intelligence: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[OntologyExtensionCandidate] = []
        archetypes = intelligence.get("active_archetypes", [])
        for idx, item in enumerate(archetypes[:4]):
            candidates.append(
                OntologyExtensionCandidate(
                    candidate_id=f"candidate-{idx + 1}",
                    name=f"{item.get('name', 'UNKNOWN')}_VARIANT",
                    category="propagation_archetype",
                    evidence_basis=[item.get("evidence_strength", "developing")],
                    replay_references=[f"replay:{idx}"],
                )
            )
        return [item.to_dict() for item in candidates]

    def review_candidate(self, candidate: dict[str, Any], *, reviewer: str, approve: bool) -> dict[str, Any]:
        state = "VALIDATED" if approve else "REJECTED"
        return OntologyReviewRecord(
            candidate_id=str(candidate.get("candidate_id", "unknown")),
            reviewer=reviewer,
            state=state,
            notes="Evidence-backed replay review completed.",
        ).to_dict()

    def version_snapshot(self, candidates: list[dict[str, Any]], *, version: str = "v1.0.0") -> dict[str, Any]:
        validated = [item.get("name", "") for item in candidates if item.get("state") == "VALIDATED"]
        active = [item.get("candidate_id", "") for item in candidates]
        return OntologyVersion(version=version, active_candidates=active, validated_extensions=validated).to_dict()

    def promotion_decision(self, candidate: dict[str, Any]) -> dict[str, Any]:
        evidence_count = len(candidate.get("evidence_basis", []))
        approve = evidence_count >= 1 and len(candidate.get("replay_references", [])) >= 1
        state = "VALIDATED" if approve else "UNDER_REVIEW"
        reason = "Replay-linked evidence threshold satisfied." if approve else "Requires additional replay-backed evidence."
        return OntologyPromotionDecision(
            candidate_id=str(candidate.get("candidate_id", "unknown")),
            approved=approve,
            state=state,
            reason=reason,
        ).to_dict()

