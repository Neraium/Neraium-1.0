"""Phase 2 temporal integrity, eligibility and inert decision replay."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.governance.authority_store import (
    AuthorityRecordConflict, AuthorityDecisionV2, DecisionBasisV2,
    InMemoryAuthorityDecisionStore, RuntimeAuthorityDecisionStore, create_policy_decision,
)
from app.governance.characterization import TrajectoryCharacterization
from app.governance.context import ContextObject, ContextBasis, ContextRegistry, qualify_context
from app.governance.contracts import EvidenceObject, MaturityLevel
from app.governance.maturity import evaluate_maturity_v2
from app.governance.policy import AuthorityPolicy, PolicyRegistry, evaluate_policy
from app.governance.tiers import CONDITION_FAMILIES, EvidenceCondition, classify_tier
from app.governance.trend import TrendAssumptions, TrendSample, mann_kendall_evidence
from test_evidence_governance import (
    AT, LATER, PROVENANCE, SCOPE, assess, decision_and_basis, evidence, graph_for, observation, snapshot,
)

BEFORE = "2026-09-06T09:00:00Z"
AFTER = "2026-09-06T12:00:00Z"


def changed(record, **fields):
    raw = record.as_dict()
    if hasattr(record, "identity_field"):
        raw[record.identity_field] = ""
    return type(record).model_validate({**raw, **fields})


def anchor(**fields):
    return ContextObject.model_validate(dict(context_key="calibration-1", context_type="calibration_event",
        system_scope="system-1", source_type="operator_record", source_reference="record:calibration-1",
        provenance=PROVENANCE, verification_status="verified", effective_from=BEFORE, created_at=AT,
        payload={"event": "calibration"}, **fields))


def context(*records, at=AT, **fields):
    return ContextBasis.model_validate({**dict(system_scope="system-1", evaluated_at=at, relevant_at=at,
        records=records, facts={}, facts_available_at=AT, facts_provenance=PROVENANCE), **fields})


def characterized(graph=None, *, trajectory_name="gradual_drift", anchors=None, at=AT):
    graph = graph or graph_for(evidence(), evidence("b", "relational"))
    base = assess(graph, evaluated_at=at)
    trajectory = TrajectoryCharacterization(finding_id=base.finding_id, system_scope=graph.system_scope,
        trajectory=trajectory_name, evaluated_at=at, evidence_ids=base.relevant_evidence_ids,
        evidence_families=tuple(sorted({item.evidence_family for item in graph.evidence})),
        dependency_graph_snapshot_id=graph.snapshot_id,
        time_horizon={"window_id": "trajectory-window", "started_at": BEFORE, "ended_at": at},
        method="reviewed_multifamily_trajectory_v1", assumptions=("comparable_operating_regime",),
        limitations=("declared_adapter_assertion_no_causality",))
    return evaluate_maturity_v2(finding_id=base.finding_id, relevant_evidence_ids=base.relevant_evidence_ids,
        graph=graph, persistence=base.persistence, evaluated_at=at, source_run_id="run-1",
        trajectory=trajectory, context_basis=anchors), graph


def policy(**fields):
    raw = dict(policy_id="presentation", policy_version=1, applicable_system_scope="system-1",
        requested_operation="present_evidence", minimum_maturity="L4", allowed_lifecycle_states=["new"],
        required_evidence_families=["signal_location", "relational"], prohibited_evidence_conditions=[],
        required_context_types=["calibration_event"], human_review_requirement=False,
        effective_from=BEFORE, created_at=AT, provenance=PROVENANCE)
    return AuthorityPolicy.model_validate({**raw, **fields})


def evaluate(p=None, *, maturity=None, graph=None, ctx=None, at=AT, **fields):
    ctx = ctx or context(anchor(), at=at)
    if maturity is None:
        maturity, graph = characterized(anchors=ctx, at=at)
    return evaluate_policy(policy=p or policy(), graph=graph, maturity=maturity, lifecycle_state="new",
        context=ctx, requested_operation=(p or policy()).requested_operation, evaluated_at=at, **fields)


@pytest.fixture(params=[InMemoryAuthorityDecisionStore, RuntimeAuthorityDecisionStore])
def storage(request):
    return request.param()


def test_context_registry_identity_history_supersession_and_scope(storage):
    registry = ContextRegistry(storage)
    first = anchor()
    assert anchor() == first
    assert ContextObject.model_validate_json(first.model_dump_json()) == first
    assert registry.append(SCOPE, first) == first
    registry.append(SCOPE, first)
    second = changed(first, version=2, supersedes=first.context_id, verification_status="invalidated", created_at=LATER)
    registry.append(SCOPE, second)
    assert registry.history(SCOPE, "system-1") == (first, second)
    assert registry.as_of(SCOPE, "system-1", AT) == (first,)
    assert qualify_context(context(*registry.as_of(SCOPE, "system-1", AT))).applicable_context_ids == (first.context_id,)
    assert not qualify_context(context(first, second, at=LATER)).applicable_context_ids
    assert registry.history(SCOPE, "other-system") == ()
    other_scope = type(SCOPE)(tenant_scope_id="other", workspace_id="workspace-1")
    assert registry.history(other_scope, "system-1") == ()
    registry.history(SCOPE, "system-1")[0].payload["changed"] = True
    assert "changed" not in registry.history(SCOPE, "system-1")[0].payload
    with pytest.raises(AuthorityRecordConflict):
        registry.append(SCOPE, changed(first, payload={"rebind": True}))
    with pytest.raises(AuthorityRecordConflict):
        registry.append(SCOPE, changed(second, payload={"branch": True}))


@pytest.mark.parametrize("changes,reason", [
    ({"system_scope": "other-system"}, "scope_mismatch"),
    ({"effective_from": LATER}, "outside_effective_interval"),
    ({"effective_to": AT}, "outside_effective_interval"),
    ({"verification_status": "invalidated"}, "invalidated"),
    ({"verification_status": "partially_verified"}, "verification_limited"),
    ({"verification_status": "unverified"}, "verification_limited"),
    ({"context_type": "operating_context"}, "not_external_qualification"),
    ({"validity_conditions": {"mode": "cooling"}}, "validity_conditions_unsatisfied"),
])
def test_context_qualification_limits(changes, reason):
    item = changed(anchor(), **changes)
    result = qualify_context(context(item))
    assert result.rejected_context_ids == result.limiting_context == (item.context_id,)
    assert result.qualification_reasons == (f"{item.context_id}:{reason}",)
    assert not result.applicable_context_ids
    maturity, _ = characterized(anchors=context(item))
    assert maturity.level == MaturityLevel.L3


def test_context_validity_facts_and_temporal_boundary():
    item = changed(anchor(), validity_conditions={"mode": "cooling"})
    assert qualify_context(context(item, facts={"mode": "cooling"})).applicable_context_ids
    with pytest.raises(ValueError, match="future_context_knowledge"):
        context(changed(item, created_at=LATER, effective_from=BEFORE))
    with pytest.raises(ValueError, match="future_context_facts"):
        context(item, facts_available_at=LATER)
    with pytest.raises(ValueError, match="incomplete_or_ambiguous"):
        context(changed(item, version=2, supersedes=item.context_id))
    with pytest.raises(ValueError, match="empty_or_reversed"):
        changed(item, effective_to=BEFORE)


@pytest.mark.parametrize("name", ["step_change", "gradual_drift", "oscillation", "recovery", "sustained_shift", "propagation_candidate"])
def test_L3_and_L4_trajectory_vocabulary_and_replay(name):
    l3, graph = characterized(trajectory_name=name)
    assert l3.level == MaturityLevel.L3
    l4, _ = characterized(graph, trajectory_name=name, anchors=context(anchor()))
    assert l4.level == MaturityLevel.L4
    assert l4.context_qualification.applicable_context_ids == (anchor().context_id,)
    assert not {"confidence", "probability", "health", "cause"} & type(l4).model_fields.keys()
    assert characterized(graph, trajectory_name=name, anchors=context(anchor()))[0] == l4
    assert characterized(graph, trajectory_name="indeterminate")[0].level == MaturityLevel.L2
    base = assess(graph)
    assert evaluate_maturity_v2(finding_id=base.finding_id, relevant_evidence_ids=base.relevant_evidence_ids,
        graph=graph, persistence=base.persistence, evaluated_at=AT, source_run_id="run-1").level == MaturityLevel.L2


def test_no_false_trajectory_corroboration_or_future_characterization():
    l3, graph = characterized()
    dependent = graph_for(evidence(), evidence("b", "relational", source_signals=["a"]))
    assert characterized(dependent)[0].level == MaturityLevel.L1
    for changes in ({"evaluated_at": LATER}, {"evidence_families": ["signal_location", "trend"]},
                    {"finding_id": "other-finding"}):
        with pytest.raises(ValueError):
            evaluate_maturity_v2(finding_id=l3.finding_id, relevant_evidence_ids=l3.relevant_evidence_ids,
                graph=graph, persistence=l3.persistence, evaluated_at=AT, source_run_id="run-1",
                trajectory=changed(l3.trajectory, **changes))


def trend(values, **assumption_changes):
    samples = tuple(TrendSample(observed_at=f"2026-09-06T09:{i:02d}:00Z", value=value) for i, value in enumerate(values))
    raw = observation(source_window={"window_id": "trend", "started_at": BEFORE, "ended_at": AT})
    assumptions = TrendAssumptions(**{**dict(independent_observations=True, no_unmodeled_seasonality=True,
        comparable_measurement_regime=True, missingness_ignorable=True), **assumption_changes})
    return mann_kendall_evidence(samples=samples, observation=raw, assumptions=assumptions, created_at=AT, source_run_id="run-1")


@pytest.mark.parametrize("values,direction,s", [(list(range(12)), "increasing", 66),
    (list(range(12))[::-1], "decreasing", -66), ([3] * 12, "none", 0)])
def test_mann_kendall_direction_statistic_significance_and_replay(values, direction, s):
    item = trend(values)
    assert item.evidence_family.value == "trend"
    assert item.payload["statistic_s"] == s
    assert item.payload["direction"] == direction
    assert item.payload["significant"] == (s != 0)
    assert trend(values) == item
    assert EvidenceObject.model_validate_json(item.model_dump_json()) == item


@pytest.mark.parametrize("values,assumptions", [([1, 2, 3], {}), (list(range(12)), {"independent_observations": False}),
    (list(range(12)), {"no_unmodeled_seasonality": False}), ([None] * 12, {}),
    ([None, *range(12)], {"missingness_ignorable": False})])
def test_trend_limited_not_fabricated(values, assumptions):
    result = trend(values, **assumptions).payload
    assert result["status"] == "limited"
    assert result["statistic_s"] is None and result["significant"] is None
    assert result["eligibility_reasons"]


def test_trend_missing_ties_and_nonfinite():
    result = trend([1, 1, 2, None, 3, 4, 4, 5, 6, 7, 8, 9]).payload
    assert result["missing_count"] == 1 and result["status"] == "available"
    assert result["variance_s"] > 0
    with pytest.raises(ValueError, match="nonfinite"):
        trend([float("nan")] * 12)


@pytest.mark.parametrize("fields,outcome,rule", [
    ({}, "permitted", "all_policy_rules_satisfied"),
    ({"human_review_requirement": True}, "human_review_required", "human_review_pending"),
    ({"allowed_lifecycle_states": ["persistent"]}, "deferred", "allowed_lifecycle_state"),
    ({"required_evidence_families": ["trend"]}, "deferred", "evidence_family:trend"),
    ({"required_context_types": ["maintenance_event"]}, "deferred", "context_type:maintenance_event"),
    ({"effective_to": AT}, "blocked", "policy_effective_interval"),
    ({"effective_from": LATER}, "blocked", "policy_effective_interval"),
    ({"applicable_system_scope": "other"}, "blocked", "policy_scope"),
    ({"decision_outcome_rules": {"satisfied": "released"}}, "released", "all_policy_rules_satisfied"),
    ({"decision_outcome_rules": {"satisfied": "escalated"}}, "escalated", "all_policy_rules_satisfied"),
    ({"required_context_types": ["maintenance_event"], "decision_outcome_rules": {"insufficient": "blocked"}}, "blocked", "context_type:maintenance_event"),
])
def test_policy_outcome_rules_and_reasons(fields, outcome, rule):
    result = evaluate(policy(**fields))
    assert result.outcome.value == outcome
    assert rule in result.reasons
    assert result.satisfied_rules
    assert result.execution_authorized is False
    assert evaluate(policy(**fields)) == result


def test_future_policy_and_expired_L4_cannot_authorize():
    with pytest.raises(ValueError, match="future_knowledge"):
        evaluate(policy(created_at=LATER, effective_from=BEFORE))
    ctx = context(changed(anchor(), effective_to=LATER))
    maturity, graph = characterized(anchors=ctx)
    assert maturity.level == MaturityLevel.L4
    result = evaluate(maturity=maturity, graph=graph, ctx=context(*ctx.records, at=LATER), at=LATER)
    assert result.outcome.value == "deferred"
    assert "current_L4_context" in result.failed_rules


def test_policy_registry_version_resolution_and_no_history_rewrite(storage):
    registry = PolicyRegistry(storage)
    first = policy()
    registry.append(SCOPE, first)
    second = changed(first, policy_version=2, supersedes=first.policy_record_id, created_at=LATER,
                     effective_from=BEFORE, effective_to=AFTER, human_review_requirement=True)
    registry.append(SCOPE, second)
    assert registry.resolve(SCOPE, "system-1", first.policy_id, AT) == first
    assert registry.resolve(SCOPE, "system-1", first.policy_id, LATER) == second
    assert evaluate(registry.resolve(SCOPE, "system-1", first.policy_id, AT)).outcome.value == "permitted"
    with pytest.raises(ValueError, match="expired"):
        registry.resolve(SCOPE, "system-1", first.policy_id, AFTER)
    assert registry.history(SCOPE, "system-1") == (first, second)
    with pytest.raises(AuthorityRecordConflict):
        registry.append(SCOPE, changed(second, human_review_requirement=False))


def tier_graph(**statuses):
    items, raw = [], []
    for i, (condition, family) in enumerate(CONDITION_FAMILIES.items()):
        name = f"input-{i}"
        raw.append(observation(name))
        item = evidence(name, family, covariance_source_id=f"observation:{name}" if family.value == "covariance_geometry" else None,
            payload={"status": "available", "governance_conditions": {
                condition.value: statuses.get(condition.value, "present" if condition == EvidenceCondition.LOCATION_SHIFT else "absent")}})
        items.append(item)
    return graph_for(*items, observations=tuple(raw))


@pytest.mark.parametrize("condition", ["relationship_change", "covariance_change", "response_breakdown", "propagation_change", "physics_contradiction"])
def test_structural_change_forces_Tier_B_human_review(condition):
    graph = tier_graph(**{condition: "present"})
    maturity = assess(graph)
    classification = classify_tier(graph, maturity.relevant_evidence_ids)
    assert classification.tier == "tier_b" and not classification.execution_authorized
    p = policy(requested_operation="evaluate_adaptation", minimum_maturity="L2", required_evidence_families=[], required_context_types=[])
    result = evaluate(p, maturity=maturity, graph=graph)
    assert result.outcome.value == "human_review_required"
    assert "tier_b_requires_review_no_automatic_authority" in result.failed_rules
    blocked = changed(p, prohibited_evidence_conditions=[condition])
    assert evaluate(blocked, maturity=maturity, graph=graph).outcome.value == "blocked"


def test_Tier_A_requires_all_intact_checks_and_never_executes():
    graph = tier_graph()
    maturity = assess(graph)
    assert classify_tier(graph, maturity.relevant_evidence_ids).tier == "tier_a"
    p = policy(requested_operation="adapt_state_location", minimum_maturity="L2", required_evidence_families=[], required_context_types=[])
    result = evaluate(p, maturity=maturity, graph=graph)
    assert result.outcome.value == "permitted" and not result.execution_authorized
    for condition in ("relationship_change", "instrumentation_concern", "excessive_evolution_rate"):
        graph = tier_graph(**{condition: "unknown"})
        assert classify_tier(graph, assess(graph).relevant_evidence_ids).tier == "unclassified"


def phase2_decision(at=AT, records=None, p=None):
    ctx = context(*(records if records is not None else (anchor(),)), at=at)
    maturity, graph = characterized(anchors=ctx, at=at)
    _, old_basis = decision_and_basis()
    lifecycle = changed(old_basis.lifecycle, evidence_ids=maturity.relevant_evidence_ids)
    return create_policy_decision(graph=graph, maturity=maturity, lifecycle=lifecycle, context=ctx,
        policy=p or policy(), requested_operation="present_evidence", decision_timestamp=at, source_run_id="run-1",
        active_model=snapshot("model", payload={"model_ref": "model:snapshot-1", "baseline_ref": "baseline:snapshot-1"}))


def test_frozen_phase2_decision_replay_and_later_invalidation(storage):
    first, basis = phase2_decision()
    assert first.decision_outcome.value == "permitted"
    assert first.active_model_before == first.active_model_after
    storage.append_decision(SCOPE, first, basis)
    original = storage.get_record(SCOPE, "system-1", first.decision_id)
    second_anchor = changed(anchor(), version=2, supersedes=anchor().context_id, verification_status="invalidated", created_at=LATER)
    second, later_basis = phase2_decision(at=LATER, records=(anchor(), second_anchor))
    assert second.decision_outcome.value == "deferred"
    storage.append_decision(SCOPE, changed(second, supersedes_decision_id=first.decision_id), later_basis)
    assert storage.get_record(SCOPE, "system-1", first.decision_id) == original
    restored = DecisionBasisV2.model_validate(original["basis"])
    restored.validate_for(AuthorityDecisionV2.model_validate(original["decision"]))
    basis.context.records[0].payload["tampered"] = True
    assert storage.get_record(SCOPE, "system-1", first.decision_id) == original
    with pytest.raises(ValueError, match="content_identity_mismatch"):
        storage.append_decision(SCOPE, first, basis)


@pytest.mark.parametrize("field,value,reason", [
    ("decision_reasons", ["invented"], "decision_policy_result_mismatch"),
    ("decision_outcome", "blocked", "decision_policy_result_mismatch"),
    ("policy_evaluation_id", "invented", "policy_replay_mismatch"),
    ("active_model_after", None, "phase2_model_transition_inactive"),
])
def test_decision_cannot_override_policy_or_mutate_model(field, value, reason):
    decision, basis = phase2_decision()
    with pytest.raises(ValueError, match=reason):
        InMemoryAuthorityDecisionStore().append_decision(SCOPE, changed(decision, **{field: value}), basis)


def test_registry_concurrent_append_is_atomic_and_failure_propagates(monkeypatch):
    storage = RuntimeAuthorityDecisionStore()
    registry = ContextRegistry(storage)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: registry.append(SCOPE, anchor()), range(8)))
    assert registry.history(SCOPE, "system-1") == (anchor(),)
    def fail(*args): raise OSError("offline")
    monkeypatch.setattr(storage, "_mutate", fail)
    with pytest.raises(OSError, match="offline"):
        registry.append(SCOPE, anchor())


def test_irregular_trend_duplicate_times_and_future_samples():
    assumptions = TrendAssumptions(independent_observations=True, no_unmodeled_seasonality=True,
        comparable_measurement_regime=True, missingness_ignorable=True)
    raw = observation(source_window={"window_id": "trend", "started_at": BEFORE, "ended_at": AT})
    samples = tuple(TrendSample(observed_at=f"2026-09-06T09:{minute:02d}:00Z", value=i)
                    for i, minute in enumerate([0, 1, 3, 6, 10, 15, 21, 28, 36, 45]))
    def compute(items):
        return mann_kendall_evidence(samples=items, observation=raw, assumptions=assumptions,
                                    created_at=AT, source_run_id="run-1")
    result = compute(samples)
    assert result.payload["irregular_spacing"] and result.payload["significant"]
    with pytest.raises(ValueError, match="strictly_increase"):
        compute((samples[0], *samples))
    with pytest.raises(ValueError, match="future_trend_sample"):
        compute((*samples, TrendSample(observed_at=LATER, value=11)))
    assert trend([1, 5, 2, 4, 3, 3, 4, 2, 5, 1]).payload["significant"] is False


def test_limited_trend_cannot_corroborate_or_characterize():
    a, b = evidence(), evidence("b", "trend", payload={"status": "limited"})
    graph = graph_for(a, b)
    base = assess(graph, relevant=(a.evidence_id, b.evidence_id))
    assert base.level == MaturityLevel.L2  # Historical v1 rules are unchanged.
    result = evaluate_maturity_v2(finding_id=base.finding_id, relevant_evidence_ids=base.relevant_evidence_ids,
        graph=graph, persistence=base.persistence, evaluated_at=AT, source_run_id="run-1")
    assert result.level == MaturityLevel.L1
    assert "corroborating_support_unavailable" in result.reasons
    assert characterized(graph)[0].level in {MaturityLevel.L0, MaturityLevel.L1}


def test_incomplete_or_contradictory_structure_never_passes_Tier_A():
    graph = tier_graph()
    covariance = next(item for item in graph.evidence if item.evidence_family.value == "covariance_geometry")
    bad = changed(covariance, covariance_source_id="undeclared")
    graph = graph_for(*(bad if item == covariance else item for item in graph.evidence), observations=graph.observations)
    assert classify_tier(graph, assess(graph).relevant_evidence_ids).tier == "unclassified"
    concern = evidence("concern", "instrumentation", lineage_complete=False,
        payload={"governance_conditions": {"instrumentation_concern": "present"}})
    graph = graph_for(*tier_graph().evidence, concern, observations=(*tier_graph().observations, observation("concern")))
    classification = classify_tier(graph, assess(graph).relevant_evidence_ids)
    assert classification.tier == "unclassified"
    assert "instrumentation_concern:present" in classification.reasons


def test_Tier_B_policy_cannot_configure_permitting_outcome():
    with pytest.raises(ValueError):
        policy(decision_outcome_rules={"tier_b": "permitted"})
    for outcome in ("blocked", "deferred"):
        graph = tier_graph(relationship_change="present")
        p = policy(requested_operation="evaluate_adaptation", minimum_maturity="L2",
            required_evidence_families=[], required_context_types=[], decision_outcome_rules={"tier_b": outcome})
        assert evaluate(p, maturity=assess(graph), graph=graph).outcome.value == outcome


def test_partial_context_preserves_limitation_alongside_qualifying_anchor():
    partial = changed(anchor(), context_key="maintenance-1", context_type="maintenance_event", verification_status="partially_verified")
    result, _ = characterized(anchors=context(anchor(), partial))
    assert result.level == MaturityLevel.L4
    assert result.context_qualification.limiting_context == (partial.context_id,)
    assert result.context_qualification.verification_statuses[partial.context_id].value == "partially_verified"


def test_policy_can_require_non_external_context_without_using_it_for_L4():
    identity = changed(anchor(), context_key="identity-1", context_type="infrastructure_identity")
    ctx = context(anchor(), identity)
    assert evaluate(policy(required_context_types=["infrastructure_identity"]), ctx=ctx).outcome.value == "permitted"
    assert characterized(anchors=context(identity))[0].level == MaturityLevel.L3


def test_v2_cannot_be_stored_under_legacy_basis_or_forged_policy_result():
    decision, basis = phase2_decision()
    from app.governance.authority_store import DecisionBasis
    with pytest.raises(ValueError, match="phase2_basis_schema_required"):
        InMemoryAuthorityDecisionStore().append_decision(SCOPE, decision,
            DecisionBasis(graph=basis.graph, maturity=basis.maturity, lifecycle=basis.lifecycle, snapshots=basis.snapshots))
    forged = changed(basis.policy_evaluation, outcome="blocked", reasons=["invented"])
    with pytest.raises(ValueError, match="policy_replay_mismatch"):
        InMemoryAuthorityDecisionStore().append_decision(SCOPE, decision, changed(basis, policy_evaluation=forged))


def test_governance_evaluation_has_no_runtime_write_or_physical_handler(monkeypatch):
    from app.services import runtime_db
    def forbidden(*args, **kwargs):
        pytest.fail("governance evaluation attempted a runtime mutation")
    monkeypatch.setattr(runtime_db, "mutate_latest_payload", forbidden)
    decision, basis = phase2_decision()
    basis.validate_for(decision)
    assert decision.execution_authorized is False
    assert decision.active_model_before == decision.active_model_after
    from app.governance.contracts import RequestedOperation
    with pytest.raises(ValueError):
        RequestedOperation("physical_control")


def test_evaluated_governance_preserves_SII_outputs():
    from app.engine.sii_engine import evaluate_sii
    from test_governance_compatibility import stable_result
    from test_sii_engine_v2 import _profiles, _stable_rows
    columns, rows = _stable_rows()
    def run():
        return stable_result(evaluate_sii(columns=columns, rows=rows, numeric_profiles=_profiles(columns),
            timestamp_column="timestamp", config={"numeric_columns": columns[1:]}))
    before = run()
    decision, basis = phase2_decision()
    InMemoryAuthorityDecisionStore().append_decision(SCOPE, decision, basis)
    assert run() == before


def test_context_and_policy_set_order_does_not_change_identity():
    a = anchor()
    b = changed(a, context_key="second")
    assert context(a, b) == context(b, a)
    assert policy(required_evidence_families=["trend", "relational", "trend"]) == policy(required_evidence_families=["relational", "trend"])


def test_unsupported_location_assertion_cannot_establish_Tier_A():
    graph = tier_graph()
    location = next(item for item in graph.evidence if item.evidence_family.value == "signal_location")
    graph = graph_for(*(changed(item, lineage_complete=False) if item == location else item for item in graph.evidence),
                      observations=graph.observations)
    assert classify_tier(graph, assess(graph).relevant_evidence_ids).tier == "unclassified"


def test_context_predicates_do_not_coerce_nested_boolean_and_number():
    item = changed(anchor(), validity_conditions={"reading": {"enabled": True}})
    assert not qualify_context(context(item, facts={"reading": {"enabled": 1}})).applicable_context_ids


def test_policy_supersession_preserves_frozen_v2_decision(storage):
    first, basis = phase2_decision()
    storage.append_decision(SCOPE, first, basis)
    original = storage.get_record(SCOPE, "system-1", first.decision_id)
    registry = PolicyRegistry(storage)
    registry.append(SCOPE, basis.policy)
    successor = changed(basis.policy, policy_version=2, supersedes=basis.policy.policy_record_id,
                        created_at=LATER, effective_from=BEFORE, human_review_requirement=True)
    registry.append(SCOPE, successor)
    second, new_basis = phase2_decision(at=LATER, p=registry.resolve(SCOPE, "system-1", successor.policy_id, LATER))
    assert second.decision_outcome.value == "human_review_required"
    storage.append_decision(SCOPE, changed(second, supersedes_decision_id=first.decision_id), new_basis)
    assert storage.get_record(SCOPE, "system-1", first.decision_id) == original
    basis.validate_for(first)


@pytest.mark.parametrize("structural,outcome,tier", [(False, "permitted", "tier_a"), (True, "human_review_required", "tier_b")])
def test_Tier_decision_serialization_and_pending_review(structural, outcome, tier):
    graph = tier_graph(relationship_change="present" if structural else "absent")
    maturity, _ = characterized(graph, anchors=context(anchor()))
    _, old_basis = decision_and_basis()
    lifecycle = changed(old_basis.lifecycle, evidence_ids=maturity.relevant_evidence_ids)
    p = policy(requested_operation="evaluate_adaptation")
    decision, basis = create_policy_decision(graph=graph, maturity=maturity, lifecycle=lifecycle,
        context=context(anchor()), policy=p, requested_operation=p.requested_operation, decision_timestamp=AT,
        source_run_id="run-1", active_model=snapshot("model", payload={"model_ref": "immutable-model", "baseline_ref": "immutable-baseline"}))
    assert decision.decision_outcome.value == outcome and decision.tier_classification == tier
    assert decision.human_review.required == structural
    assert decision.human_review.status == ("pending" if structural else "not_required")
    assert bool(decision.contradicting_evidence) == structural
    assert not decision.execution_authorized and decision.active_model_before == decision.active_model_after
    store = InMemoryAuthorityDecisionStore()
    store.append_decision(SCOPE, decision, basis)
    assert store.history(SCOPE, "system-1") == [decision]
