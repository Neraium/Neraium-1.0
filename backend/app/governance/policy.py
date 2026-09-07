"""Versioned software authority eligibility. Outcomes have no execution handlers."""
from typing import Literal, Self

from pydantic import StrictBool, field_validator, model_validator

from app.governance.context import ContextBasis, ContextType, QUALIFYING_TYPES, qualify_context
from app.governance.contracts import (ContentRecord, Contract, AuthorityOutcome, EvidenceFamily, LifecycleState,
    MaturityLevel, Provenance, RequestedOperation, Text, Timestamp, Version, _timestamp, content_id)
from app.governance.dependencies import DependencyGraph
from app.governance.maturity import MaturityEvaluation, MaturityEvaluationV2, replay_maturity
from app.governance.registry import VersionRegistry, covers, time
from app.governance.tiers import EvidenceCondition, TierClassification, assess_conditions, classify_tier, usable_lineage


class DecisionOutcomeRules(Contract):
    satisfied: Literal["permitted", "released", "escalated"] = "permitted"
    insufficient: Literal["deferred", "blocked"] = "deferred"
    prohibited: Literal["blocked", "human_review_required"] = "blocked"
    tier_b: Literal["human_review_required", "blocked", "deferred"] = "human_review_required"


class AuthorityPolicy(ContentRecord):
    identity_field = "policy_record_id"
    identity_kind = "authority-policy"
    schema_version: Literal["authority-policy-v1"] = "authority-policy-v1"
    policy_record_id: str = ""
    policy_id: Text
    policy_version: Version
    applicable_system_scope: Text
    requested_operation: RequestedOperation
    minimum_maturity: MaturityLevel
    allowed_lifecycle_states: tuple[LifecycleState, ...]
    required_evidence_families: tuple[EvidenceFamily, ...]
    prohibited_evidence_conditions: tuple[EvidenceCondition, ...]
    required_context_types: tuple[ContextType, ...]
    human_review_requirement: StrictBool
    decision_outcome_rules: DecisionOutcomeRules = DecisionOutcomeRules()
    effective_from: Timestamp
    effective_to: Timestamp | None = None
    created_at: Timestamp
    supersedes: Text | None = None
    provenance: Provenance

    @field_validator("allowed_lifecycle_states", "required_evidence_families", "prohibited_evidence_conditions", "required_context_types")
    @classmethod
    def ordered_set(cls, value):
        return tuple(sorted(set(value)))

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.effective_to and time(self.effective_to) <= time(self.effective_from):
            raise ValueError("empty_or_reversed_policy_interval")
        if (self.policy_version == 1) != (self.supersedes is None):
            raise ValueError("policy_version_requires_predecessor")
        return self

    @property
    def registry_scope(self): return self.applicable_system_scope
    @property
    def registry_identity(self): return self.policy_id
    @property
    def registry_version(self): return self.policy_version
    @property
    def record_id(self): return self.policy_record_id


class PolicyRegistry(VersionRegistry):
    def __init__(self, storage):
        super().__init__(storage, AuthorityPolicy, "authority-policy-registry-v1")

    def resolve(self, scope, system_scope: str, policy_id: str, evaluated_at: str) -> AuthorityPolicy:
        known = [item for item in self.as_of(scope, system_scope, evaluated_at) if item.policy_id == policy_id
                 and time(item.effective_from) <= time(evaluated_at)]
        if not known:
            raise ValueError("policy_unavailable_at_decision")
        policy = max(known, key=lambda item: item.policy_version)
        # Never fall back to a superseded permissive policy after a successor expires.
        if not covers(policy.effective_from, policy.effective_to, evaluated_at):
            raise ValueError("policy_expired_at_decision")
        return policy


class PolicyEvaluation(ContentRecord):
    identity_field = "evaluation_id"
    identity_kind = "authority-policy-evaluation"
    evaluation_id: str = ""
    evaluator_version: Literal["authority-evaluator-v1"] = "authority-evaluator-v1"
    policy_id: Text
    policy_version: Version
    policy_record_id: Text
    evaluated_at: Timestamp
    requested_operation: RequestedOperation
    dependency_graph_snapshot_id: Text
    maturity_snapshot_id: Text
    context_basis_id: Text
    lifecycle_state: LifecycleState
    outcome: AuthorityOutcome
    reasons: tuple[Text, ...]
    satisfied_rules: tuple[Text, ...]
    failed_rules: tuple[Text, ...]
    limiting_evidence: tuple[Text, ...]
    contradicting_evidence: tuple[Text, ...]
    limiting_context: tuple[Text, ...]
    classification: TierClassification | None
    execution_authorized: Literal[False] = False


ADAPTATION_OPERATIONS = frozenset({RequestedOperation.EVALUATE_ADAPTATION, RequestedOperation.ADAPT_STATE_LOCATION,
                                  RequestedOperation.ADAPT_STRUCTURE})


def evaluate_policy(*, policy: AuthorityPolicy, graph: DependencyGraph,
                    maturity: MaturityEvaluation | MaturityEvaluationV2, lifecycle_state: LifecycleState,
                    context: ContextBasis, requested_operation: RequestedOperation, evaluated_at: str) -> PolicyEvaluation:
    policy = AuthorityPolicy.model_validate(policy.as_dict())
    graph = DependencyGraph.model_validate(graph.as_dict())
    context = ContextBasis.model_validate(context.as_dict())
    requested_operation = RequestedOperation(requested_operation)
    lifecycle_state = LifecycleState(lifecycle_state)
    evaluated_at = _timestamp(evaluated_at)
    if replay_maturity(maturity, graph) != maturity:
        raise ValueError("policy_maturity_replay_mismatch")
    if (time(policy.created_at) > time(evaluated_at) or time(maturity.evaluated_at) > time(evaluated_at)
            or time(context.evaluated_at) > time(evaluated_at)):
        raise ValueError("policy_basis_contains_future_knowledge")
    graph.validate_available_at(evaluated_at)
    if graph.system_scope != maturity.system_scope or graph.system_scope != context.system_scope:
        raise ValueError("policy_basis_scope_mismatch")
    if isinstance(maturity, MaturityEvaluationV2) and maturity.context_basis:
        context.validate_historical_basis(maturity.context_basis)
    # Re-evaluate context at decision time; old L4 cannot carry expired anchors forward.
    current_context = ContextBasis.model_validate({**context.as_dict(), "evaluated_at": evaluated_at, "relevant_at": evaluated_at})
    qualification = qualify_context(current_context, external_only=False)
    satisfied, failed = [], []
    def check(rule, passed):
        (satisfied if passed else failed).append(rule)
    check("policy_scope", policy.applicable_system_scope == graph.system_scope)
    check("requested_operation", policy.requested_operation == requested_operation)
    check("policy_effective_interval", covers(policy.effective_from, policy.effective_to, evaluated_at))
    check("minimum_maturity", int(maturity.level.value[1:]) >= int(policy.minimum_maturity.value[1:]))
    check("allowed_lifecycle_state", lifecycle_state in policy.allowed_lifecycle_states)
    if policy.minimum_maturity == MaturityLevel.L4:
        check("current_L4_context", any(item.context_type in QUALIFYING_TYPES and item.context_id in qualification.applicable_context_ids
            for item in current_context.records))
    relevant = [item for item in graph.evidence if item.evidence_id in maturity.relevant_evidence_ids]
    usable = [item for item in relevant if usable_lineage(graph, item.evidence_id)
              and (item.payload or {}).get("status", "available") == "available"]
    check("maturity_support_available", set(maturity.supporting_evidence_ids) <= {item.evidence_id for item in usable})
    for family in sorted(set(policy.required_evidence_families)):
        check(f"evidence_family:{family.value}", any(item.evidence_family == family for item in usable))
    conditions = {item.condition: item for item in assess_conditions(graph, maturity.relevant_evidence_ids)}
    prohibited = False
    limiting = set(maturity.supporting_evidence_ids) - {item.evidence_id for item in usable}
    for condition in sorted(set(policy.prohibited_evidence_conditions)):
        item = conditions[condition]
        check(f"prohibited_condition_absent:{condition.value}", item.status == "absent")
        if item.status == "present":
            prohibited = True
        if item.status != "absent": limiting.update(item.evidence_ids)
    types = {item.context_type for item in current_context.records if item.context_id in qualification.applicable_context_ids}
    for kind in sorted(set(policy.required_context_types)):
        check(f"context_type:{kind.value}", kind in types)
    classification = classify_tier(graph, maturity.relevant_evidence_ids) if requested_operation in ADAPTATION_OPERATIONS else None
    if classification:
        limiting.update(classification.limiting_evidence)
        check("adaptation_candidate_classified", classification.eligible_candidate)
        if requested_operation == RequestedOperation.ADAPT_STATE_LOCATION:
            check("tier_a_operation_match", classification.tier == "tier_a")
        if requested_operation == RequestedOperation.ADAPT_STRUCTURE:
            check("tier_b_operation_match", classification.tier == "tier_b")
    rules = policy.decision_outcome_rules
    if any(rule in failed for rule in ("policy_scope", "requested_operation", "policy_effective_interval")):
        outcome = "blocked"
    elif prohibited:
        outcome = rules.prohibited
    elif failed:
        outcome = rules.insufficient
    elif classification and classification.tier == "tier_b":
        outcome = rules.tier_b
        failed.append("tier_b_requires_review_no_automatic_authority")
    elif policy.human_review_requirement:
        outcome = "human_review_required"
        failed.append("human_review_pending")
    else:
        outcome = rules.satisfied
    return PolicyEvaluation(policy_id=policy.policy_id, policy_version=policy.policy_version,
        policy_record_id=policy.policy_record_id, evaluated_at=evaluated_at, requested_operation=requested_operation,
        dependency_graph_snapshot_id=graph.snapshot_id, maturity_snapshot_id=maturity.evaluation_id,
        context_basis_id=content_id("policy-context-basis", current_context.as_dict()), lifecycle_state=lifecycle_state,
        outcome=outcome, reasons=tuple(failed or ["all_policy_rules_satisfied"]), satisfied_rules=tuple(satisfied),
        failed_rules=tuple(failed), limiting_evidence=tuple(sorted(limiting)),
        contradicting_evidence=tuple(sorted({identifier for item in conditions.values()
            if item.status == "present" and item.condition != EvidenceCondition.LOCATION_SHIFT for identifier in item.evidence_ids})),
        limiting_context=tuple(sorted(set((*qualification.limiting_context, *qualification.unavailable_context,
            *(rule for rule in failed if rule.startswith("context_type:")))))), classification=classification)
