from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


GOVERNANCE_STATUSES = ("OBSERVED", "PROPOSED", "REVIEWED", "VALIDATED", "LIMITED_USE", "DEPRECATED", "REJECTED")


@dataclass(frozen=True)
class EvidenceSufficiencyReview:
    sufficiency: str
    replay_available: bool
    lineage_complete: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FederationReview:
    privacy_constraints_met: bool
    raw_telemetry_absent: bool
    control_payloads_absent: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OntologyGovernanceDecision:
    candidate_id: str
    status: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CognitionGovernanceRecord:
    record_id: str
    provenance: str
    validation_status: str
    domain_applicability: list[str]
    evidence_review: EvidenceSufficiencyReview
    federation_review: FederationReview
    ontology_decision: OntologyGovernanceDecision

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence_review"] = self.evidence_review.to_dict()
        payload["federation_review"] = self.federation_review.to_dict()
        payload["ontology_decision"] = self.ontology_decision.to_dict()
        return payload


def build_governance_record(intelligence: dict[str, Any]) -> dict[str, Any]:
    evidence_review = EvidenceSufficiencyReview(
        sufficiency="CORROBORATED" if intelligence.get("evidence_lineage", {}).get("lineages") else "OBSERVATIONAL",
        replay_available=bool(intelligence.get("replay_timeline", {}).get("timeline")),
        lineage_complete=bool(intelligence.get("evidence_lineage")),
    )
    federation_review = FederationReview(
        privacy_constraints_met=True,
        raw_telemetry_absent=True,
        control_payloads_absent=True,
    )
    decision = OntologyGovernanceDecision(
        candidate_id="candidate-1",
        status="REVIEWED",
        rationale="Replay-linked evidence present; broader domain review pending.",
    )
    record = CognitionGovernanceRecord(
        record_id="governance-latest",
        provenance="distributed_structural_cognition_network",
        validation_status="REVIEWED",
        domain_applicability=["cultivation", "data_center", "manufacturing", "water", "energy"],
        evidence_review=evidence_review,
        federation_review=federation_review,
        ontology_decision=decision,
    )
    return record.to_dict()

