"""Adversarial admission tests for the non-executing Phase 3 workflow."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.governance.adaptation import AdaptationWorkflow, Reviewer, TransitionContract
from app.governance.authority_store import InMemoryAuthorityDecisionStore, RuntimeAuthorityDecisionStore, create_policy_decision
from app.governance.context import ContextRegistry
from app.governance.policy import PolicyRegistry
from test_governance_phase2 import (
    AT, AFTER, BEFORE, SCOPE, PROVENANCE, anchor, changed, characterized,
    context, decision_and_basis, policy, register_basis, snapshot, tier_graph,
)


@pytest.fixture(params=["memory", "runtime"])
def storage(request):
    if request.param == "runtime":
        return RuntimeAuthorityDecisionStore()
    return InMemoryAuthorityDecisionStore()


def setup(storage, *, structural=False, authenticate=True, graph=None, **conditions):
    graph = graph or tier_graph(relationship_change="present" if structural else "absent", **conditions)
    ctx = context(anchor())
    maturity, _ = characterized(graph, anchors=ctx)
    _, old = decision_and_basis()
    lifecycle = changed(old.lifecycle, evidence_ids=maturity.relevant_evidence_ids)
    p = policy(requested_operation="evaluate_adaptation")
    d, b = create_policy_decision(scope=SCOPE, graph=graph, maturity=maturity, lifecycle=lifecycle,
        context=ctx, policy=p, requested_operation=p.requested_operation, decision_timestamp=AT,
        source_run_id="run-1", active_model=snapshot("model", payload={"model_ref": "model:active", "baseline_ref": "baseline:active"}),
        candidate_model=snapshot("model", version="2", payload={"model_ref": "model:candidate", "baseline_ref": "baseline:candidate"}))
    register_basis(storage, b)
    storage.append_decision(SCOPE, d, b)
    t = TransitionContract(decision=d, basis=b, active_before=d.active_model_before,
        candidate=d.candidate_model, active_after=d.active_model_after, rollback_reference=d.active_model_before)
    now = [AT]
    def auth(scope, system, credential):
        if credential != "verified-session":
            raise ValueError("invalid_session")
        return Reviewer(identity="reviewer-1", authenticated_scope=scope, system_scope=system, provenance=PROVENANCE)
    w = AdaptationWorkflow(storage, clock=lambda: now[0], authenticate_review=auth if authenticate else None)
    c = w.propose(SCOPE, "system-1", transition=t, provenance=PROVENANCE)
    return w, c, now


def advance(w, c, action, **kwargs):
    prior = next(events[-1] for candidate, events in w.history(SCOPE, "system-1") if candidate == c)
    return w.advance(SCOPE, "system-1", c.candidate_id, expected_event_id=prior.event_id, action=action, **kwargs)


def test_unknown_rate_defers_and_transition_never_executes(storage):
    w, c, _ = setup(storage)
    e = advance(w, c, "evaluate")
    assert e.state == "deferred"
    assert "safety:excessive_evolution_rate:unknown" in e.reasons
    assert c.transition.active_before == c.transition.active_after == c.transition.rollback_reference
    assert not e.execution_authorized
    with pytest.raises(ValueError, match="disabled"):
        advance(w, c, "applied")


@pytest.mark.parametrize("structural", [False, True])
def test_approval_is_immutable_disposition_not_safety_waiver(storage, structural):
    w, c, _ = setup(storage, structural=structural)
    original = storage.get_record(SCOPE, "system-1", c.transition.decision.decision_id)
    request = advance(w, c, "request_review")
    e = advance(w, c, "review", credential="verified-session", review_action="approve", rationale="Reviewed retained basis")
    assert e.state == "deferred"
    assert e.review_action == "approve"
    assert e.review_request_id == request.event_id
    assert e.reviewer.identity == "reviewer-1"
    assert storage.get_record(SCOPE, "system-1", c.transition.decision.decision_id) == original
    assert not e.execution_authorized


@pytest.mark.parametrize("action,state", [("reject", "rejected"), ("defer", "deferred")])
def test_review_dispositions(storage, action, state):
    w, c, _ = setup(storage)
    advance(w, c, "request_review")
    assert advance(w, c, "review", credential="verified-session", review_action=action, rationale="Reviewed").state == state


@pytest.mark.parametrize("authenticate,credential", [(False, "verified-session"), (True, "reviewer-1"), (True, {"identity": "admin"})])
def test_fake_review_fails_closed(storage, authenticate, credential):
    w, c, _ = setup(storage, authenticate=authenticate)
    advance(w, c, "request_review")
    before = w.history(SCOPE, "system-1")
    with pytest.raises(ValueError):
        advance(w, c, "review", credential=credential, review_action="approve", rationale="Forged")
    assert w.history(SCOPE, "system-1") == before


def test_review_before_evidence_or_request(storage):
    w, c, now = setup(storage)
    with pytest.raises(ValueError, match="pending_review"):
        advance(w, c, "review", credential="verified-session", review_action="approve", rationale="Early")
    advance(w, c, "request_review")
    now[0] = BEFORE
    with pytest.raises(ValueError, match="clock_regressed"):
        advance(w, c, "review", credential="verified-session", review_action="approve", rationale="Early")


@pytest.mark.parametrize("field", ["active_before", "active_after", "candidate", "rollback_reference"])
def test_transition_reference_tampering(storage, field):
    _, c, _ = setup(storage)
    with pytest.raises(ValueError):
        changed(c.transition, **{field: "forged-reference"})


@pytest.mark.parametrize("kind", ["policy", "context"])
def test_stale_review_policy_context(storage, kind):
    w, c, now = setup(storage)
    advance(w, c, "request_review")
    now[0] = AFTER
    b = c.transition.basis
    if kind == "policy":
        PolicyRegistry(storage).append(SCOPE, changed(b.policy, policy_version=2,
            supersedes=b.policy.policy_record_id, created_at=AFTER, effective_from=AFTER))
    else:
        a = b.context.records[0]
        ContextRegistry(storage).append(SCOPE, changed(a, version=2, supersedes=a.context_id,
            created_at=AFTER, verification_status="invalidated"))
    before = w.history(SCOPE, "system-1")
    with pytest.raises(ValueError, match="stale_policy_or_context"):
        advance(w, c, "review", credential="verified-session", review_action="approve", rationale="Stale")
    assert w.history(SCOPE, "system-1") == before


@pytest.mark.parametrize("tenant,workspace", [("tenant-2", "workspace-1"), ("tenant-1", "workspace-2")])
def test_cross_scope_reuse(storage, tenant, workspace):
    w, c, _ = setup(storage)
    foreign = AuthenticatedPhase4Scope(tenant_scope_id=tenant, workspace_id=workspace)
    with pytest.raises(ValueError, match="scope_mismatch"):
        w.propose(foreign, "system-1", transition=c.transition, provenance=PROVENANCE)
    assert w.history(foreign, "system-1") == ()


def test_tier_b_auto_approval_attempt(storage):
    w, c, _ = setup(storage, structural=True)
    assert c.transition.decision.tier_classification == "tier_b"
    assert advance(w, c, "evaluate").state != "approved"


def test_duplicate_concurrent_review(storage):
    w, c, _ = setup(storage)
    request = advance(w, c, "request_review")
    def submit(_):
        try:
            return w.advance(SCOPE, "system-1", c.candidate_id, expected_event_id=request.event_id,
                action="review", credential="verified-session", review_action="approve", rationale="Reviewed")
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sum(result is not None for result in results) == 1
    assert len(w.history(SCOPE, "system-1")[0][1]) == 3


def test_later_supersession_preserves_history(storage):
    w, c, now = setup(storage)
    advance(w, c, "request_review")
    earlier = w.history(SCOPE, "system-1")[0]
    now[0] = AFTER
    replacement = w.propose(SCOPE, "system-1", transition=c.transition, provenance=PROVENANCE)
    advance(w, c, "supersede", superseded_by=replacement.candidate_id)
    current = w.history(SCOPE, "system-1")[0]
    assert current[0] == earlier[0]
    assert current[1][:-1] == earlier[1]
    c.transition.basis.validate_for(c.transition.decision)
    with pytest.raises(ValueError, match="terminal"):
        advance(w, c, "request_review")


@pytest.mark.parametrize("condition", ["instrumentation_concern", "covariance_change", "response_breakdown", "propagation_change", "physics_contradiction"])
def test_unresolved_concerns_cannot_be_approved(storage, condition):
    w, c, _ = setup(storage, **{condition: "present"})
    advance(w, c, "request_review")
    event = advance(w, c, "review", credential="verified-session", review_action="approve", rationale="Cannot waive")
    assert event.state == "deferred"
    assert f"safety:{condition}:present" in event.reasons


def test_replay_ignores_later_registry_and_rejects_forged_events(storage):
    from app.governance.adaptation import replay_adaptation
    w, c, now = setup(storage)
    advance(w, c, "request_review")
    advance(w, c, "review", credential="verified-session", review_action="approve", rationale="Reviewed")
    candidate, events = w.history(SCOPE, "system-1")[0]
    assert replay_adaptation(candidate, events) == "deferred"
    a = c.transition.basis.context.records[0]
    ContextRegistry(storage).append(SCOPE, changed(a, version=2, supersedes=a.context_id,
        created_at=AFTER, verification_status="invalidated"))
    assert replay_adaptation(candidate, events) == "deferred"
    with pytest.raises(ValueError, match="replay_mismatch"):
        replay_adaptation(candidate, (*events[:-1], changed(events[-1], state="approved")))
    with pytest.raises(ValueError, match="chain_mismatch"):
        replay_adaptation(candidate, (events[0], events[-1]))


def test_stored_decision_supersession_invalidates_pending_review(storage):
    w, c, now = setup(storage)
    advance(w, c, "request_review")
    t = c.transition
    d = changed(t.decision, supersedes_decision_id=t.decision.decision_id, source_run_id="later-run")
    storage.append_decision(SCOPE, d, t.basis)
    with pytest.raises(ValueError, match="stale_superseded_decision"):
        advance(w, c, "review", credential="verified-session", review_action="approve", rationale="Old decision")


def test_reviewer_wrong_scope_and_expired_credentials(storage):
    w, c, _ = setup(storage)
    advance(w, c, "request_review")
    w.authenticate_review = lambda *_: Reviewer(identity="admin", authenticated_scope=SCOPE,
        system_scope="different-system", provenance=PROVENANCE)
    with pytest.raises(ValueError, match="reviewer_scope_mismatch"):
        advance(w, c, "review", review_action="approve", rationale="Wrong scope")
    w.authenticate_review = lambda *_: {"identity": "admin"}
    with pytest.raises(ValueError, match="authenticated_reviewer_required"):
        advance(w, c, "review", review_action="approve", rationale="Forged identity")


def test_conflicting_ancestry_survives_human_approval(storage):
    from test_governance_phase2 import evidence, observation, graph_for
    base = tier_graph()
    parent = evidence("parent", "relational", payload={"governance_conditions": {"relationship_change": "present"}})
    selected = tuple(changed(item, derived_from=[{"kind": "evidence", "dependency_id": parent.evidence_id}])
                     if item.evidence_family == "relational" else item for item in base.evidence)
    graph = graph_for(*selected, parent, observations=(*base.observations, observation("parent")))
    w, c, _ = setup(storage, graph=graph)
    advance(w, c, "request_review")
    e = advance(w, c, "review", credential="verified-session", review_action="approve", rationale="Intact child cannot erase parent")
    assert e.state == "deferred"
    assert "safety:relationship_change:present" in e.reasons
    assert parent.evidence_id in c.transition.decision.contradicting_evidence


def test_proposal_uses_clock_inside_writer_transaction(storage, monkeypatch):
    w, c, now = setup(storage)
    original = storage._mutate_with_reads
    def delayed(key, keys, callback):
        now[0] = AFTER
        return original(key, keys, callback)
    monkeypatch.setattr(storage, "_mutate_with_reads", delayed)
    candidate = w.propose(SCOPE, "system-1", transition=c.transition, provenance=PROVENANCE)
    assert candidate.proposed_at == AFTER
