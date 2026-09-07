"""Adaptation classification from explicit, frozen analytical condition assertions.

Adapters supply payload.governance_conditions, never permission. Missing checks
are unknown. Any contradictory observation takes precedence over intact checks.
"""
from enum import Enum
from typing import Literal

from pydantic import StrictBool

from app.governance.contracts import Contract, EvidenceFamily, Text
from app.governance.dependencies import DependencyGraph


class EvidenceCondition(str, Enum):
    LOCATION_SHIFT = "location_shift"
    RELATIONSHIP_CHANGE = "relationship_change"
    COVARIANCE_CHANGE = "covariance_change"
    RESPONSE_BREAKDOWN = "response_breakdown"
    PROPAGATION_CHANGE = "propagation_change"
    PHYSICS_CONTRADICTION = "physics_contradiction"
    INSTRUMENTATION_CONCERN = "instrumentation_concern"
    EXCESSIVE_EVOLUTION_RATE = "excessive_evolution_rate"


CONDITION_FAMILIES = {
    EvidenceCondition.LOCATION_SHIFT: EvidenceFamily.SIGNAL_LOCATION,
    EvidenceCondition.RELATIONSHIP_CHANGE: EvidenceFamily.RELATIONAL,
    EvidenceCondition.COVARIANCE_CHANGE: EvidenceFamily.COVARIANCE_GEOMETRY,
    EvidenceCondition.RESPONSE_BREAKDOWN: EvidenceFamily.EXPECTED_RESPONSE,
    EvidenceCondition.PROPAGATION_CHANGE: EvidenceFamily.MULTISCALE,
    EvidenceCondition.PHYSICS_CONTRADICTION: EvidenceFamily.PHYSICS_EXTERNAL,
    EvidenceCondition.INSTRUMENTATION_CONCERN: EvidenceFamily.INSTRUMENTATION,
    EvidenceCondition.EXCESSIVE_EVOLUTION_RATE: EvidenceFamily.TREND,
}
STRUCTURAL = frozenset({EvidenceCondition.RELATIONSHIP_CHANGE, EvidenceCondition.COVARIANCE_CHANGE,
    EvidenceCondition.RESPONSE_BREAKDOWN, EvidenceCondition.PROPAGATION_CHANGE, EvidenceCondition.PHYSICS_CONTRADICTION})


class ConditionAssessment(Contract):
    condition: EvidenceCondition
    status: Literal["present", "absent", "unknown"]
    evidence_ids: tuple[Text, ...]


class TierClassification(Contract):
    tier: Literal["tier_a", "tier_b", "unclassified"]
    eligible_candidate: StrictBool
    reasons: tuple[Text, ...]
    assessments: tuple[ConditionAssessment, ...]
    limiting_evidence: tuple[Text, ...]
    # This contract cannot represent execution permission.
    execution_authorized: Literal[False] = False


def usable_lineage(graph: DependencyGraph, identifier: str) -> bool:
    nodes = {item.evidence_id: item for item in graph.evidence}
    for ancestor in {identifier, *graph.lineage(identifier)}:
        if ancestor not in nodes:
            continue
        item = nodes[ancestor]
        if not item.lineage_complete or not item.derived_from:
            return False
        if (item.evidence_family == EvidenceFamily.COVARIANCE_GEOMETRY or item.covariance_source_id) and (
            item.covariance_source_id not in graph.lineage(ancestor)
        ):
            return False
        if (item.payload or {}).get("status", "available") != "available":
            return False
    return True


def assess_conditions(graph: DependencyGraph, relevant_ids: tuple[str, ...]) -> tuple[ConditionAssessment, ...]:
    graph = DependencyGraph.model_validate(graph.as_dict())
    nodes = {item.evidence_id: item for item in graph.evidence}
    if not set(relevant_ids) <= nodes.keys():
        raise ValueError("condition_evidence_outside_graph")
    results = []
    for condition, family in CONDITION_FAMILIES.items():
        present, absent, unknown = [], [], []
        for identifier in sorted(set(relevant_ids)):
            item = nodes[identifier]
            if item.evidence_family != family:
                continue
            payload = item.payload or {}
            assertions = payload.get("governance_conditions", {})
            if not isinstance(assertions, dict):
                raise ValueError("invalid_governance_conditions")
            status = assertions.get(condition.value, "unknown")
            if not isinstance(status, str) or status not in {"present", "absent", "unknown"}:
                raise ValueError("invalid_governance_condition_status")
            if status == "present":
                if condition == EvidenceCondition.LOCATION_SHIFT and not usable_lineage(graph, identifier):
                    unknown.append(identifier)
                else:
                    present.append(identifier)
            elif status == "absent" and usable_lineage(graph, identifier) and (
                family != EvidenceFamily.TREND or payload.get("status") == "available"
            ):
                absent.append(identifier)
            else:
                unknown.append(identifier)
        results.append(ConditionAssessment(condition=condition, status="present" if present else "absent" if absent and not unknown else "unknown",
                                           evidence_ids=tuple(sorted(set(present + absent + unknown)))))
    return tuple(results)


def classify_tier(graph: DependencyGraph, relevant_ids: tuple[str, ...]) -> TierClassification:
    assessments = assess_conditions(graph, relevant_ids)
    structural = [item for item in assessments if item.condition in STRUCTURAL and item.status == "present"]
    failed = [item for item in assessments if item.status != (
        "present" if item.condition == EvidenceCondition.LOCATION_SHIFT else "absent")]
    if structural:
        tier, reasons = "tier_b", tuple(f"structural:{item.condition.value}" for item in structural)
    elif not failed:
        tier, reasons = "tier_a", ("location_shift_with_all_structural_and_safety_checks_intact",)
    else:
        tier, reasons = "unclassified", tuple(f"{item.condition.value}:{item.status}" for item in failed)
    return TierClassification(tier=tier, eligible_candidate=tier in {"tier_a", "tier_b"}, reasons=reasons,
        assessments=assessments, limiting_evidence=tuple(sorted({identifier for item in failed for identifier in item.evidence_ids})))
