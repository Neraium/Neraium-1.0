"""Append-only adaptation planning and human dispositions; no execution adapter.

The host supplies an authenticated scope, a trusted clock and (optionally) a
review authenticator. Never construct that authenticator from request data.
Without one, human review admission is disabled. No record is an execution token.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Literal

from pydantic import model_validator

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.governance.authority_store import AuthorityDecisionV2, DecisionBasisV2, AuthorityRecordConflict
from app.governance.contracts import ContentRecord, Contract, Provenance, Text, Timestamp
from app.governance.policy import ADAPTATION_OPERATIONS, evaluate_policy
from app.governance.registry import time


class AdaptationState(str, Enum):
    PROPOSED = "candidate_proposed"
    DEFERRED = "deferred"
    REVIEW = "human_review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    APPLIED = "applied"  # Vocabulary only; admission is disabled.


class Reviewer(Contract):
    identity: Text
    authenticated_scope: AuthenticatedPhase4Scope
    system_scope: Text
    provenance: Provenance


class TransitionContract(ContentRecord):
    identity_field = "transition_id"
    identity_kind = "inactive-adaptation-transition-v1"
    transition_id: str = ""
    decision: AuthorityDecisionV2
    basis: DecisionBasisV2
    active_before: Text
    candidate: Text
    active_after: Text
    rollback_reference: Text
    execution_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_transition(self):
        self.basis.validate_for(self.decision)
        d = self.decision
        if d.requested_operation not in ADAPTATION_OPERATIONS:
            raise ValueError("adaptation_operation_required")
        if (self.active_before != d.active_model_before or self.candidate != d.candidate_model
                or self.active_after != self.active_before or self.active_after != d.active_model_after):
            raise ValueError("inactive_model_transition_mismatch")
        if self.rollback_reference != self.active_before:
            raise ValueError("rollback_must_reference_exact_active_before")
        candidate = next(item for item in self.basis.snapshots if item.snapshot_id == self.candidate)
        if self.candidate == self.active_before or any(
            not isinstance(candidate.payload.get(key), str) or not candidate.payload[key].strip()
            for key in ("model_ref", "baseline_ref")
        ):
            raise ValueError("distinct_immutable_candidate_required")
        return self


class AdaptationCandidate(ContentRecord):
    identity_field = "candidate_id"
    identity_kind = "adaptation-candidate-v1"
    candidate_id: str = ""
    proposed_at: Timestamp
    provenance: Provenance
    transition: TransitionContract

    @model_validator(mode="after")
    def chronology(self):
        if time(self.proposed_at) < time(self.transition.decision.decision_timestamp):
            raise ValueError("candidate_before_evidence_decision")
        return self


class AdaptationEvent(ContentRecord):
    identity_field = "event_id"
    identity_kind = "adaptation-event-v1"
    event_id: str = ""
    candidate_id: Text
    action: Literal["propose", "evaluate", "request_review", "review", "supersede"] = "propose"
    previous_event_id: Text | None
    recorded_at: Timestamp
    state: AdaptationState
    reasons: tuple[Text, ...]
    review_request_id: Text | None = None
    review_action: Literal["approve", "reject", "defer"] | None = None
    reviewer: Reviewer | None = None
    rationale: Text | None = None
    superseded_by: Text | None = None
    execution_authorized: Literal[False] = False


def _now():
    return datetime.now(timezone.utc).isoformat()


def _gates(candidate, at):
    """Review disposition cannot waive any analytical/policy safety gate."""
    t = candidate.transition
    b, d = t.basis, t.decision
    evaluation = evaluate_policy(policy=b.policy, graph=b.graph, maturity=b.maturity,
        lifecycle_state=b.lifecycle.state, context=b.context,
        requested_operation=d.requested_operation, evaluated_at=at)
    reasons = set(evaluation.failed_rules) - {"human_review_pending", "tier_b_requires_review_no_automatic_authority"}
    classification = evaluation.classification
    for assessment in classification.assessments:
        expected = "present" if assessment.condition.value == "location_shift" else "absent"
        if assessment.status != expected:
            reasons.add(f"safety:{assessment.condition.value}:{assessment.status}")
    if b.lifecycle.state.value in {"new", "persistent", "recovering", "unresolved", "superseded"}:
        reasons.add("finding_lifecycle_unresolved")
    if classification.tier == "unclassified":
        reasons.add("unclassified_candidate")
    return tuple(sorted(reasons))


class AdaptationWorkflow:
    """Atomic scoped ledger using either Phase 2 storage backend.

    Reviewer authentication is a host-side trust boundary, not a signature or
    caller-supplied identity field. authenticate_review(scope, system, credential)
    must verify current authorization and return Reviewer, or raise. It is not
    shipped with a permissive default or exposed via an API.
    """
    def __init__(self, storage, *, authenticate_review: Callable | None = None, clock: Callable = _now):
        self.storage = storage
        self.authenticate_review = authenticate_review
        self.clock = clock

    def _key(self, scope, system):
        return "adaptation-workflow-v1::" + self.storage._key(scope, system)

    def history(self, scope, system):
        ledger = self.storage._ledger(self.storage._read(self._key(scope, system)), scope, system)
        return tuple((AdaptationCandidate.model_validate(row["candidate"]),
                      tuple(AdaptationEvent.model_validate(e) for e in row["events"]))
                     for row in ledger["records"])

    def _current_basis(self, scope, system, candidate, at, raws):
        t = candidate.transition
        d, b = t.decision, t.basis
        if d.authenticated_scope != scope or d.system_scope != system:
            raise ValueError("adaptation_scope_mismatch")
        if time(candidate.proposed_at) > time(at):
            raise ValueError("future_candidate")
        authority = self.storage._ledger(raws[0], scope, system)["records"]
        exact = {"decision": d.as_dict(), "basis": b.as_dict()}
        if exact not in authority:
            raise ValueError("stored_authority_decision_required")
        if any(row["decision"]["supersedes_decision_id"] == d.decision_id for row in authority):
            raise AuthorityRecordConflict("stale_superseded_decision")
        contexts, policy = self.storage._selection(scope, system, at, d.policy_id, raws[1:])
        if contexts != b.context.records or policy != b.policy:
            raise AuthorityRecordConflict("stale_policy_or_context")
        # Re-evaluates expiry and future knowledge even with unchanged versions.
        return _gates(candidate, at)

    def propose(self, scope, system, *, transition, provenance):
        transition = TransitionContract.model_validate(transition.as_dict())
        def append(ledger, raws):
            candidate = AdaptationCandidate(proposed_at=self.clock(), provenance=provenance, transition=transition)
            if any(row["candidate"]["candidate_id"] == candidate.candidate_id for row in ledger["records"]):
                return candidate
            self._current_basis(scope, system, candidate, candidate.proposed_at, raws)
            event = AdaptationEvent(candidate_id=candidate.candidate_id, previous_event_id=None,
                recorded_at=candidate.proposed_at, state="candidate_proposed", reasons=("inactive_candidate_recorded",))
            ledger["records"].append({"candidate": candidate.as_dict(), "events": [event.as_dict()]})
            return candidate
        return self._write(scope, system, append)

    def _write(self, scope, system, callback):
        result = []
        def update(raw, raws):
            ledger = self.storage._ledger(raw, scope, system)
            result.append(callback(ledger, raws))
            return ledger
        keys = (self.storage._key(scope, system), *self.storage._registry_keys(scope, system))
        self.storage._mutate_with_reads(self._key(scope, system), keys, update)
        return type(result[0]).model_validate(result[0].as_dict())

    def advance(self, scope, system, candidate_id, *, expected_event_id,
                action: Literal["evaluate", "request_review", "review", "supersede"],
                credential=None, review_action=None, rationale=None, superseded_by=None):
        """Compare-and-append; duplicate/concurrent submissions conflict.

        Review timestamps come from the trusted host clock. A review applies
        only to its pending request and exact frozen candidate/decision basis.
        """
        def append(ledger, raws):
            at = self.clock()
            row = next((r for r in ledger["records"] if r["candidate"]["candidate_id"] == candidate_id), None)
            if row is None:
                raise ValueError("candidate_not_found_in_scope")
            candidate = AdaptationCandidate.model_validate(row["candidate"])
            prior = AdaptationEvent.model_validate(row["events"][-1])
            if prior.event_id != expected_event_id:
                raise AuthorityRecordConflict("stale_adaptation_event")
            if time(at) < time(prior.recorded_at):
                raise ValueError("workflow_clock_regressed")
            if prior.state in {AdaptationState.REJECTED, AdaptationState.SUPERSEDED, AdaptationState.APPLIED}:
                raise ValueError("terminal_adaptation_state")
            fields = {}
            if action == "supersede":
                replacement = next((r for r in ledger["records"] if r["candidate"]["candidate_id"] == superseded_by), None)
                if replacement is None or superseded_by == candidate_id:
                    raise ValueError("replacement_candidate_required")
                new = AdaptationCandidate.model_validate(replacement["candidate"])
                if (new.transition.decision.finding_id != candidate.transition.decision.finding_id
                        or time(new.proposed_at) < time(candidate.proposed_at)
                        or replacement["events"][-1]["state"] in {"superseded", "rejected"}):
                    raise ValueError("invalid_replacement_candidate")
                state, reasons = "superseded", ("replacement_candidate_recorded",)
                fields["superseded_by"] = superseded_by
            else:
                reasons = self._current_basis(scope, system, candidate, at, raws)
                d = candidate.transition.decision
                required = d.tier_classification == "tier_b" or candidate.transition.basis.policy.human_review_requirement
                if action == "request_review":
                    if prior.state == AdaptationState.REVIEW:
                        raise ValueError("review_already_pending")
                    state = "human_review_required"
                    reasons = reasons or ("explicit_human_review_requested",)
                elif action == "review":
                    if prior.state != AdaptationState.REVIEW:
                        raise ValueError("pending_review_request_required")
                    if self.authenticate_review is None:
                        raise ValueError("review_authentication_unavailable")
                    reviewer = self.authenticate_review(scope, system, credential)
                    if not isinstance(reviewer, Reviewer):
                        raise ValueError("authenticated_reviewer_required")
                    reviewer = Reviewer.model_validate(reviewer.as_dict())
                    if reviewer.authenticated_scope != scope or reviewer.system_scope != system:
                        raise ValueError("reviewer_scope_mismatch")
                    if review_action not in {"approve", "reject", "defer"} or not rationale:
                        raise ValueError("review_disposition_and_rationale_required")
                    state = {"approve": "deferred" if reasons else "approved", "reject": "rejected", "defer": "deferred"}[review_action]
                    fields.update(review_request_id=prior.event_id, review_action=review_action,
                                  reviewer=reviewer, rationale=rationale)
                    reasons = reasons or ("human_review_completed",)
                elif action == "evaluate":
                    if prior.state == AdaptationState.REVIEW:
                        raise ValueError("pending_review_requires_disposition")
                    state = "deferred" if reasons else "human_review_required" if required else "approved"
                    reasons = reasons or (("human_review_required",) if required else ("software_eligible_only",))
                else:
                    raise ValueError("execution_or_unknown_action_disabled")
            event = AdaptationEvent(candidate_id=candidate_id, previous_event_id=prior.event_id,
                recorded_at=at, action=action, state=state, reasons=reasons, **fields)
            row["events"].append(event.as_dict())
            return event
        return self._write(scope, system, append)


def replay_adaptation(candidate, events):
    """Validate a retained history without consulting later registries or auth.

    Authentication is enforced at admission; replay verifies the retained actor
    binding and disposition, not the truth of an external identity assertion.
    """
    candidate = AdaptationCandidate.model_validate(candidate.as_dict())
    events = tuple(AdaptationEvent.model_validate(e.as_dict()) for e in events)
    if not events:
        raise ValueError("adaptation_history_required")
    previous = None
    for event in events:
        if event.candidate_id != candidate.candidate_id or event.previous_event_id != (previous.event_id if previous else None):
            raise ValueError("adaptation_history_chain_mismatch")
        if time(event.recorded_at) < time(previous.recorded_at if previous else candidate.proposed_at):
            raise ValueError("adaptation_history_time_mismatch")
        if previous is None:
            expected, reasons = "candidate_proposed", ("inactive_candidate_recorded",)
            if event.action != "propose" or event.recorded_at != candidate.proposed_at:
                raise ValueError("proposal_time_mismatch")
        elif previous.state in {AdaptationState.REJECTED, AdaptationState.SUPERSEDED, AdaptationState.APPLIED}:
            raise ValueError("terminal_adaptation_state")
        elif event.action == "supersede" and event.superseded_by:
            expected, reasons = "superseded", ("replacement_candidate_recorded",)
            if event.superseded_by == candidate.candidate_id:
                raise ValueError("self_supersession")
        else:
            reasons = _gates(candidate, event.recorded_at)
            if event.action == "review" and event.review_action:
                if previous.state != AdaptationState.REVIEW or event.review_request_id != previous.event_id:
                    raise ValueError("review_request_mismatch")
                actor = event.reviewer
                d = candidate.transition.decision
                if (actor is None or actor.authenticated_scope != d.authenticated_scope
                        or actor.system_scope != d.system_scope or not event.rationale):
                    raise ValueError("review_actor_binding_missing")
                expected = {"approve": "deferred" if reasons else "approved", "reject": "rejected", "defer": "deferred"}[event.review_action]
                reasons = reasons or ("human_review_completed",)
            elif event.action == "request_review":
                if previous.state == AdaptationState.REVIEW:
                    raise ValueError("review_already_pending")
                expected = "human_review_required"
                reasons = reasons or ("explicit_human_review_requested",)
            else:
                if event.action != "evaluate":
                    raise ValueError("adaptation_action_mismatch")
                required = (candidate.transition.decision.tier_classification == "tier_b"
                            or candidate.transition.basis.policy.human_review_requirement)
                if previous.state == AdaptationState.REVIEW:
                    raise ValueError("pending_review_requires_disposition")
                expected = "deferred" if reasons else "human_review_required" if required else "approved"
                reasons = reasons or (("human_review_required",) if required else ("software_eligible_only",))
        if event.action != "supersede" and event.superseded_by:
            raise ValueError("unexpected_supersession")
        if event.action != "review" and event.review_action:
            raise ValueError("unexpected_review")
        if not event.review_action and any((event.reviewer, event.review_request_id, event.rationale)):
            raise ValueError("review_metadata_without_disposition")
        if event.state != expected or event.reasons != reasons:
            raise ValueError("adaptation_replay_mismatch")
        previous = event
    return previous.state
