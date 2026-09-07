"""Pre-merge attack reproductions: assertions must not manufacture eligibility."""
from concurrent.futures import ThreadPoolExecutor
from math import nextafter

import pytest

from app.governance.authority_store import (
    AuthorityRecordConflict, InMemoryAuthorityDecisionStore, RuntimeAuthorityDecisionStore,
    create_policy_decision,
)
from app.governance.context import ContextRegistry
from app.governance.policy import PolicyRegistry
from app.governance.tiers import assess_conditions
from app.governance.trend import trend_usable
from test_governance_phase2 import (
    AT, BEFORE, LATER, AFTER, SCOPE, PROVENANCE, CONDITION_FAMILIES, EvidenceCondition,
    anchor, context, changed, characterized, tier_graph, evidence, observation, graph_for,
    assess, evaluate, policy, phase2_decision, register_basis, trend, classify_tier,
    evaluate_maturity_v2, snapshot, decision_and_basis,
)


@pytest.fixture(params=[InMemoryAuthorityDecisionStore, RuntimeAuthorityDecisionStore])
def storage(request):
    return request.param()


def v2(graph, relevant=None, trajectory=None):
    base = assess(graph, relevant=relevant)
    return evaluate_maturity_v2(finding_id=base.finding_id, relevant_evidence_ids=base.relevant_evidence_ids,
        graph=graph, persistence=base.persistence, evaluated_at=AT, source_run_id="run-1", trajectory=trajectory)


@pytest.mark.parametrize("condition", [item for item in EvidenceCondition if item != EvidenceCondition.LOCATION_SHIFT])
@pytest.mark.parametrize("cross_family,hops,complete", [(False, 1, True), (True, 3, True), (False, 2, False)])
def test_transitive_concerns_dominate_every_gate(condition, cross_family, hops, complete):
    original = tier_graph()
    family = CONDITION_FAMILIES[condition]
    parent = evidence("parent", family, lineage_complete=complete,
        covariance_source_id="observation:parent" if family.value == "covariance_geometry" else None,
        payload={"status": "available", "governance_conditions": {condition.value: "present"}})
    ancestors = [parent]
    for i in range(hops - 1):
        ancestors.append(evidence(f"middle-{i}", "temporal" if cross_family else family,
            derived_from=[{"kind": "evidence", "dependency_id": ancestors[-1].evidence_id}]))
    selected = tuple(changed(item, derived_from=[{"kind": "evidence", "dependency_id": ancestors[-1].evidence_id}])
                     if item.evidence_family == family else item for item in original.evidence)
    graph = graph_for(*selected, *ancestors, observations=(*original.observations, observation("parent")))
    ids = tuple(item.evidence_id for item in selected)
    assessment = next(item for item in assess_conditions(graph, ids) if item.condition == condition)
    assert assessment.status == "present"
    assert parent.evidence_id in assessment.evidence_ids
    assert classify_tier(graph, ids).tier != "tier_a"
    result = evaluate(policy(requested_operation="adapt_state_location", minimum_maturity="L0",
        required_context_types=[], required_evidence_families=[], prohibited_evidence_conditions=[condition]),
        maturity=v2(graph, ids), graph=graph)
    assert result.outcome.value == "blocked"
    assert parent.evidence_id in result.contradicting_evidence


def test_unknown_ancestor_is_not_absence_or_implicit_resolution():
    parent = evidence("parent", "relational", payload={"governance_conditions": {"relationship_change": "unknown"}})
    child = evidence("child", "relational", derived_from=[{"kind": "evidence", "dependency_id": parent.evidence_id}],
        payload={"governance_conditions": {"relationship_change": "absent"}})
    graph = graph_for(parent, child, observations=(observation("parent"),))
    condition = next(item for item in assess_conditions(graph, (child.evidence_id,))
                     if item.condition == EvidenceCondition.RELATIONSHIP_CHANGE)
    assert condition.status == "unknown"
    assert parent.evidence_id in condition.evidence_ids


def decision_with_history(maturity_context, decision_context):
    maturity, graph = characterized(anchors=maturity_context)
    _, old = decision_and_basis()
    return create_policy_decision(scope=SCOPE, graph=graph, maturity=maturity,
        lifecycle=changed(old.lifecycle, evidence_ids=maturity.relevant_evidence_ids), context=decision_context,
        policy=policy(), requested_operation="present_evidence", decision_timestamp=decision_context.evaluated_at,
        source_run_id="run-1", active_model=snapshot("model", payload={"model_ref": "m", "baseline_ref": "b"}))


@pytest.mark.parametrize("at", [BEFORE, AT])
@pytest.mark.parametrize("status", ["invalidated", "partially_verified", "verified"])
def test_known_successor_cannot_be_omitted_from_maturity(at, status):
    first = changed(anchor(), created_at=BEFORE)
    successor = changed(first, version=2, supersedes=first.context_id, created_at=at, verification_status=status)
    new_key = changed(anchor(), context_key="new", created_at=LATER)
    original_context = context(first)
    complete_context = context(first, successor, new_key, at=LATER)
    with pytest.raises(ValueError, match="maturity_context_history_mismatch"):
        decision_with_history(original_context, complete_context)


def test_known_additional_logical_key_cannot_be_omitted():
    first = anchor()
    second = changed(first, context_key="another", verification_status="partially_verified")
    original_context = context(first)
    complete_context = context(second, first, at=LATER)
    with pytest.raises(ValueError, match="maturity_context_history_mismatch"):
        decision_with_history(original_context, complete_context)


def test_later_invalidation_preserves_legitimate_historical_L4(storage):
    first = anchor()
    successor = changed(first, version=2, supersedes=first.context_id, created_at=LATER, verification_status="invalidated")
    new_key = changed(first, context_key="new", created_at=LATER)
    decision, basis = decision_with_history(context(first), context(first, successor, new_key, at=LATER))
    assert decision.maturity_at_decision.value == "L4"
    register_basis(storage, basis)
    storage.append_decision(SCOPE, decision, basis)
    basis.validate_for(decision)


def test_expiry_and_same_timestamp_versions_replay_deterministically():
    first = changed(anchor(), effective_to=AT)
    assert characterized(anchors=context(first))[0].level.value == "L3"
    a = anchor()
    b = changed(a, version=2, supersedes=a.context_id, verification_status="invalidated")
    assert context(a, b) == context(b, a)
    assert characterized(anchors=context(b, a))[0].level.value == "L3"


def admit(storage, decision, basis, **overrides):
    inputs = dict(system_scope=decision.system_scope, policy_id=decision.policy_id,
        graph=basis.graph, maturity=basis.maturity, lifecycle=basis.lifecycle,
        requested_operation=decision.requested_operation, decision_timestamp=decision.decision_timestamp,
        source_run_id=decision.source_run_id,
        active_model=next(item for item in basis.snapshots if item.snapshot_id == decision.active_model_before),
        facts=basis.context.facts, facts_available_at=basis.context.facts_available_at,
        facts_provenance=basis.context.facts_provenance)
    return storage.admit_policy_decision(SCOPE, **{**inputs, **overrides})


def test_scoped_admission_and_original_retry_after_updates(storage):
    first, basis = phase2_decision()
    register_basis(storage, basis)
    actual, frozen = admit(storage, first, basis)
    assert actual == first
    assert frozen == basis
    original = storage.get_record(SCOPE, first.system_scope, first.decision_id)
    successor = changed(anchor(), version=2, supersedes=anchor().context_id, created_at=LATER, verification_status="invalidated")
    ContextRegistry(storage).append(SCOPE, successor)
    p = changed(basis.policy, policy_version=2, supersedes=basis.policy.policy_record_id,
                created_at=LATER, human_review_requirement=True)
    PolicyRegistry(storage).append(SCOPE, p)
    assert storage.append_decision(SCOPE, first, basis) == first
    frozen.validate_for(actual)
    assert storage.get_record(SCOPE, first.system_scope, first.decision_id) == original


@pytest.mark.parametrize("kind", ["context", "policy"])
def test_new_append_rejects_resurrected_registry_versions(storage, kind):
    decision, basis = phase2_decision(at=LATER)
    register_basis(storage, basis)
    if kind == "context":
        first = anchor()
        ContextRegistry(storage).append(SCOPE, changed(first, version=2, supersedes=first.context_id,
            created_at=LATER, verification_status="invalidated"))
    else:
        first = basis.policy
        PolicyRegistry(storage).append(SCOPE, changed(first, policy_version=2, supersedes=first.policy_record_id,
            created_at=LATER, human_review_requirement=True))
    with pytest.raises(AuthorityRecordConflict, match=f"stale_or_unscoped_{kind}_selection"):
        storage.append_decision(SCOPE, decision, basis)
    assert not storage.history(SCOPE, "system-1")


@pytest.mark.parametrize("field", ["tenant_scope_id", "workspace_id"])
def test_serialized_decision_cannot_cross_authenticated_scope(storage, field):
    decision, basis = phase2_decision()
    other = type(SCOPE)(**{**dict(tenant_scope_id=SCOPE.tenant_scope_id, workspace_id=SCOPE.workspace_id), field: "other"})
    with pytest.raises(ValueError, match="authenticated_scope_mismatch"):
        storage.append_decision(other, decision, basis)
    assert not storage.history(other, "system-1")
    other_basis = changed(basis, authenticated_scope=other)
    with pytest.raises(ValueError, match="authenticated_scope_mismatch"):
        other_basis.validate_for(decision)


def test_admission_system_mismatch_and_future_policy(storage):
    decision, basis = phase2_decision()
    with pytest.raises(ValueError, match="system_scope_mismatch"):
        admit(storage, decision, basis, system_scope="other")
    ContextRegistry(storage).append(SCOPE, anchor())
    PolicyRegistry(storage).append(SCOPE, changed(basis.policy, created_at=LATER))
    with pytest.raises(ValueError, match="policy_unavailable_at_decision"):
        admit(storage, decision, basis)


def test_admission_excludes_future_context_without_retroactive_qualification(storage):
    future = changed(anchor(), created_at=LATER, effective_from=BEFORE)
    decision, basis = phase2_decision(records=())
    PolicyRegistry(storage).append(SCOPE, basis.policy)
    ContextRegistry(storage).append(SCOPE, future)
    actual, frozen = admit(storage, decision, basis)
    assert frozen.context.records == ()
    assert actual.maturity_at_decision.value == "L3"
    assert actual.decision_outcome.value == "deferred"


def test_atomic_admission_rejects_registry_change_between_selection_and_append(storage, monkeypatch):
    decision, basis = phase2_decision(at=LATER)
    register_basis(storage, basis)
    transaction = storage._mutate_with_reads
    def intervene(key, read_keys, update):
        first = basis.policy
        PolicyRegistry(storage).append(SCOPE, changed(first, policy_version=2, supersedes=first.policy_record_id,
            created_at=LATER, human_review_requirement=True))
        return transaction(key, read_keys, update)
    monkeypatch.setattr(storage, "_mutate_with_reads", intervene)
    with pytest.raises(AuthorityRecordConflict, match="stale_or_unscoped_policy_selection"):
        admit(storage, decision, basis)
    assert not storage.history(SCOPE, "system-1")


def test_concurrent_admissions_are_idempotent(storage):
    decision, basis = phase2_decision()
    register_basis(storage, basis)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: admit(storage, decision, basis), range(8)))
    assert all(item == (decision, basis) for item in results)
    assert storage.history(SCOPE, "system-1") == [decision]


@pytest.mark.parametrize("changes", [
    {"status": "available"}, {"n": 12, "status": "available", "eligibility_reasons": []},
])
def test_limited_mann_kendall_cannot_be_relabeled_available(changes):
    limited = trend([1, 2, 3])
    forged = changed(limited, payload={**limited.payload, **changes})
    graph = graph_for(forged, evidence("b", "relational"),
        observations=(observation(source_window=forged.source_window.as_dict()), observation("b")))
    assert not trend_usable(forged)
    assert characterized(graph)[0].level.value in {"L0", "L1"}


@pytest.mark.parametrize("changes", [
    {"statistic_s": None}, {"variance_s": None}, {"n": 3}, {"assumptions": {}},
    {"p_value": .5}, {"significant": False}, {"direction": "decreasing"}, {"z": 999.0},
    {"tie_group_sizes": [12]}, {"limitations": []}, {"eligibility_reasons": ["insufficient_samples_minimum_10"]},
])
def test_method_specific_statistical_consistency(changes):
    item = trend(list(range(12)))
    assert trend_usable(item)
    bad = changed(item, payload={**item.payload, **changes})
    assert not trend_usable(bad)


def test_mann_kendall_and_unknown_methods_cannot_establish_rate_absence():
    graph = tier_graph()
    assessment = next(item for item in assess_conditions(graph, tuple(e.evidence_id for e in graph.evidence))
                      if item.condition == EvidenceCondition.EXCESSIVE_EVOLUTION_RATE)
    assert assessment.status == "unknown"
    assert classify_tier(graph, tuple(e.evidence_id for e in graph.evidence)).tier == "unclassified"
    unknown = evidence("a", "trend", payload={"status": "available", "governance_conditions": {"excessive_evolution_rate": "absent"}})
    assert not trend_usable(unknown)


@pytest.mark.parametrize("start,end,expected", [
    ("2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z", "L2"),
    (BEFORE, AT, "L3"), ("2026-09-06T08:00:00Z", "2026-09-06T09:30:00Z", "L3"),
])
def test_trajectory_windows_must_overlap(start, end, expected):
    maturity, graph = characterized()
    trajectory = changed(maturity.trajectory, time_horizon={"window_id": "claimed", "started_at": start, "ended_at": end})
    assert v2(graph, trajectory=trajectory).level.value == expected


def test_archived_historical_windows_and_future_evidence():
    window = {"window_id": "archive-a", "started_at": "2020-01-01T00:00:00Z", "ended_at": "2020-01-02T00:00:00Z"}
    a = evidence(source_window=window, payload=None, result_ref="archive:immutable-a")
    b = evidence("b", "relational", source_window={**window, "window_id": "archive-b"})
    graph = graph_for(a, b, observations=(observation(source_window=window), observation("b", source_window=b.source_window.as_dict())))
    template, _ = characterized()
    trajectory = changed(template.trajectory, evidence_ids=tuple(e.evidence_id for e in graph.evidence),
        dependency_graph_snapshot_id=graph.snapshot_id, time_horizon=window)
    assert v2(graph, trajectory=trajectory).level.value == "L3"
    future = changed(a, created_at=LATER)
    future_graph = graph_for(future, b, observations=graph.observations)
    with pytest.raises(ValueError, match="later_knowledge"):
        v2(future_graph)


def propagation_graph(**changes):
    support = dict(method="timing_graph_propagation_v1", path_signals=["b", "c"],
        observed_at=["2026-09-06T09:10:00Z", "2026-09-06T09:11:00Z"], relationship_refs=["archive:relationship-bc"],
        expected_lag_windows_seconds=[[30.0, 90.0]], alternative_explanations=["common_external_input"],
        limitations=["candidate_path_only"], causal_claim=False)
    b = evidence("b", "multiscale", evidence_method="timing_graph_propagation_v1", source_signals=["b", "c"],
        payload={"status": "available", "propagation_support": {**support, **changes}})
    return graph_for(evidence(), b, observations=(observation(), observation("b", source_signals=["b", "c"])))


def test_propagation_requires_specific_multiscale_support():
    assert characterized(trajectory_name="propagation_candidate")[0].level.value == "L2"
    a = evidence()
    b = evidence("b", "multiscale", payload={"governance_conditions": {"propagation_change": "present"}})
    graph = graph_for(a, b)
    assert characterized(graph, trajectory_name="propagation_candidate")[0].level.value == "L2"
    maturity, _ = characterized(propagation_graph(), trajectory_name="propagation_candidate")
    assert maturity.level.value == "L3"
    assert maturity.trajectory.trajectory == "propagation_candidate"
    assert "declared_adapter_assertion_no_causality" in maturity.trajectory.limitations


@pytest.mark.parametrize("changes", [
    {"alternative_explanations": []}, {"causal_claim": True},
    {"observed_at": [BEFORE, LATER]}, {"expected_lag_windows_seconds": [[100.0, 200.0]]},
    {"relationship_refs": []}, {"path_signals": ["b", "not-in-evidence"]},
])
def test_propagation_support_rejects_missing_alternatives_bad_timing_and_causal_claim(changes):
    assert characterized(propagation_graph(**changes), trajectory_name="propagation_candidate")[0].level.value == "L2"


def test_mann_kendall_hand_calculated_ties_and_unbounded_window():
    from math import sqrt, erfc
    item = trend([1, 1, 2, 2, 3, 3, 4, 4, 5, 5])
    assert item.payload["statistic_s"] == 40
    assert item.payload["variance_s"] == 120.0
    assert item.payload["z"] == pytest.approx(39 / sqrt(120))
    assert item.payload["p_value"] == pytest.approx(erfc(39 / sqrt(240)))
    assert trend_usable(item)
    assert not trend_usable(changed(item, source_window={"window_id": "unknown"}))


@pytest.mark.parametrize("bounds", [
    {"window_id": "missing"},
    {"window_id": "future-of-horizon", "started_at": "2026-09-06T08:00:00Z", "ended_at": "2026-09-06T08:30:00Z"},
])
def test_trajectory_cannot_hide_disjoint_or_unbounded_raw_ancestry(bounds):
    graph = graph_for(evidence(), evidence("b", "relational"),
        observations=(observation(source_window=bounds), observation("b")))
    assert characterized(graph)[0].level.value == "L2"


@pytest.mark.parametrize("threshold", [nextafter(.05, 0.0), nextafter(.05, 1.0), .01, .1])
def test_mann_kendall_threshold_requires_exact_method_parameter(threshold):
    item = trend(list(range(12)))
    assert trend_usable(item)
    forged = changed(item, payload={**item.payload, "significance_threshold": threshold})
    assert not trend_usable(forged)
