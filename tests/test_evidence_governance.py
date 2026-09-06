"""Inactive governance contracts: no analytical or operational authority."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.governance.authority_store import (
    AuthorityRecordConflict, AuthorityStorageUnavailable, DecisionBasis,
    InMemoryAuthorityDecisionStore, RuntimeAuthorityDecisionStore,
)
from app.governance.contracts import (
    AuditSnapshot, AuthorityDecision, AuthorityOutcome, DependencyRef,
    EvidenceFamily, EvidenceObject, FindingLifecycleEvent, HumanReview,
    LifecycleChange, LifecycleState, MaturityLevel, ObservationReference,
    Provenance, RequestedOperation, SourceWindow,
)
from app.governance.dependencies import DependencyGraph, evaluate_independence, topological_order
from app.governance.maturity import (
    MaturityEvaluation, PersistenceAssessment, PersistenceGate, evaluate_maturity,
)
from app.services import finding_workflow as workflow, runtime_db
from app.services.dataset_scope import attach_dataset_scope, build_dataset_scope, dataset_scope_context


AT = "2026-09-06T10:00:00Z"
LATER = "2026-09-06T11:00:00Z"
PROVENANCE = Provenance(source="test-adapter", source_version="1", reference_ids=("run-1",))
SCOPE = AuthenticatedPhase4Scope(tenant_scope_id="tenant-1", workspace_id="workspace-1")


def observation(name="a", **changes):
    return ObservationReference.model_validate({
        "observation_id": f"observation:{name}", "source_id": f"source:{name}",
        "system_scope": "system-1", "source_signals": [name],
        "source_window": {"window_id": f"window:{name}"},
        "provenance": PROVENANCE.as_dict(), **changes,
    })


def evidence(name="a", family="signal_location", **changes):
    raw = observation(name)
    return EvidenceObject.model_validate({
        "evidence_family": family, "evidence_method": "measured_deviation",
        "source_module": "test-adapter", "source_run_id": "run-1",
        "system_scope": "system-1", "source_signals": [name],
        "source_window": raw.source_window.as_dict(),
        "derived_from": [{"kind": "observation", "dependency_id": raw.observation_id}],
        "assumption_set": [], "context_refs": [], "provenance": PROVENANCE.as_dict(),
        "created_at": AT, "payload": {"deviation": 2}, "lineage_complete": True, **changes,
    })


def graph_for(*items, observations=None):
    return DependencyGraph(
        system_scope="system-1", evidence=items,
        observations=observations if observations is not None else (observation("a"), observation("b")),
    )


def assess(graph, *, persistent=True, relevant=None, finding_id="finding-1", **changes):
    ids = relevant if relevant is not None else tuple(item.evidence_id for item in graph.evidence)
    persistence = PersistenceAssessment(finding_id=finding_id, gates=(PersistenceGate(
        requirement_id="fixed-gate", requirement_version="1", basis="fixed_observations",
        satisfied=persistent, evidence_ids=(ids[0] if ids else "absent",),
        reasons=("three_consecutive_observations" if persistent else "insufficient_observations",),
    ),) if ids else ())
    return evaluate_maturity(**{
        "finding_id": finding_id, "relevant_evidence_ids": ids, "graph": graph,
        "persistence": persistence, "evaluated_at": AT, "source_run_id": "run-1", **changes,
    })


def snapshot(kind, version="1", **changes):
    return AuditSnapshot.model_validate({
        "kind": kind, "object_id": f"{kind}-1", "version": version,
        "system_scope": "system-1", "created_at": AT,
        "provenance": PROVENANCE.as_dict(), "payload": {"version_basis": version}, **changes,
    })


def decision_and_basis(*, policy_version="1", **changes):
    graph = graph_for(evidence(), evidence("b", "instrumentation"))
    maturity = assess(graph)
    lifecycle = FindingLifecycleEvent(
        event_id="lifecycle-1", finding_id="finding-1", version=1, recorded_at=AT,
        actor="reviewer", state="new", effective_at=AT,
        evidence_ids=maturity.relevant_evidence_ids, reasons=("observation_recorded",),
        source_run_id="run-1", provenance=PROVENANCE,
    )
    context, policy, model = snapshot("context"), snapshot("policy", policy_version), snapshot("model")
    decision = AuthorityDecision.model_validate({
        "finding_id": "finding-1", "system_scope": "system-1",
        "decision_timestamp": AT, "effective_timestamp": LATER,
        "policy_id": policy.object_id, "policy_version": policy.version,
        "policy_snapshot_id": policy.snapshot_id,
        "evidence_snapshot_ids": maturity.relevant_evidence_ids,
        "context_snapshot_id": context.snapshot_id, "dependency_graph_snapshot_id": graph.snapshot_id,
        "maturity_at_decision": maturity.level, "maturity_snapshot_id": maturity.evaluation_id,
        "lifecycle_state_at_decision": lifecycle.state, "lifecycle_event_id": lifecycle.event_id,
        "requested_operation": "evaluate_adaptation", "decision_outcome": "deferred",
        "decision_reasons": ["foundation_only"], "limiting_evidence": [], "contradicting_evidence": [],
        "active_model_before": model.snapshot_id, "candidate_model": None,
        "active_model_after": model.snapshot_id,
        "human_review": {"required": False, "status": "not_required"},
        "source_run_id": "run-1", **changes,
    })
    return decision, DecisionBasis(graph=graph, maturity=maturity, lifecycle=lifecycle, snapshots=(context, policy, model))


def test_evidence_round_trip_and_deterministic_normalization():
    first = evidence(source_signals=["b", "a", "a"], assumption_set=["y", "x"],
                     created_at="2026-09-06T12:00:00+02:00", payload={"b": [2], "a": 1})
    second = evidence(source_signals=["a", "b"], assumption_set=["x", "y"], payload={"a": 1, "b": [2]})
    assert first == second
    assert first.evidence_id == second.evidence_id
    assert EvidenceObject.model_validate_json(first.model_dump_json()) == first
    assert first.derived_from == (DependencyRef(kind="observation", dependency_id="observation:a"),)
    assert first.provenance == PROVENANCE
    assert evidence(source_run_id="run-2").evidence_id != evidence().evidence_id
    assert evidence(payload={"deviation": 3}).evidence_id != evidence().evidence_id
    with pytest.raises(ValidationError, match="content_identity_mismatch"):
        EvidenceObject.model_validate({**first.as_dict(), "payload": {"changed": True}})


@pytest.mark.parametrize("family", list(EvidenceFamily))
def test_canonical_families(family):
    assert evidence(family=family.value).evidence_family == family


@pytest.mark.parametrize("changes", [
    {"evidence_family": "mahalanobis"}, {"evidence_family": "unknown"},
    {"confidence": 0.9}, {"probability": 0.9}, {"version": True},
    {"created_at": "2026-09-06T10:00:00"}, {"payload": {"x": float("nan")}},
    {"payload": {"x": "a" * 65536}}, {"payload": None}, {"schema_version": "future"},
    {"version": 2}, {"supersedes": "prior"},
])
def test_invalid_evidence_rejected(changes):
    with pytest.raises(ValidationError):
        evidence(**changes)


def test_evidence_versions_and_external_result_reference():
    first = evidence()
    second = evidence(version=2, supersedes=first.evidence_id, effective_at=LATER,
                      payload=None, result_ref="immutable-results:run-2")
    assert second.supersedes == first.evidence_id
    assert second.effective_at == LATER
    with pytest.raises(ValidationError):
        first.version = 2
    with pytest.raises(ValidationError, match="reversed_window"):
        SourceWindow(window_id="w", started_at=LATER, ended_at=AT)


def test_dag_serialization_order_lineage_and_shared_dependencies():
    first = evidence()
    child = evidence("b", "trend", derived_from=[{"kind": "evidence", "dependency_id": first.evidence_id}])
    graph = graph_for(first, child)
    assert graph == graph_for(child, first, observations=(observation("b"), observation("a")))
    assert DependencyGraph.model_validate_json(graph.model_dump_json()) == graph
    assert graph.upstream(child.evidence_id) == (first.evidence_id,)
    assert graph.lineage(child.evidence_id) == tuple(sorted((first.evidence_id, "observation:a")))
    assert graph.shared_upstream(first.evidence_id, child.evidence_id) == tuple(sorted((first.evidence_id, "observation:a")))
    order = topological_order(graph.edges())
    assert order.index("observation:a") < order.index(first.evidence_id) < order.index(child.evidence_id)
    assert not evaluate_independence(graph, first.evidence_id, child.evidence_id).independent


@pytest.mark.parametrize("edges", [{"a": ("b",), "b": ("a",)}, {"a": ("a",)}])
def test_cycles_rejected(edges):
    # Content-addressed evidence cannot naturally encode a cycle. Exercise the
    # exact graph validator used during construction with explicit cyclic IDs.
    with pytest.raises(ValueError, match="dependency_cycle"):
        topological_order(edges)


def test_graph_rejects_missing_wrong_kind_duplicate_and_cross_system_nodes():
    with pytest.raises(ValueError, match="missing_dependency_ids"):
        topological_order({"a": ("missing",)})
    with pytest.raises(ValueError, match="missing_or_wrong_kind_dependency"):
        graph_for(evidence(derived_from=[{"kind": "evidence", "dependency_id": "observation:a"}]))
    with pytest.raises(ValueError, match="duplicate_graph_node_id"):
        graph_for(evidence(), evidence())
    with pytest.raises(ValueError, match="graph_system_scope_mismatch"):
        graph_for(evidence(system_scope="other-system"))


def test_independent_families_require_disjoint_complete_lineage():
    a, b = evidence(), evidence("b", "instrumentation")
    result = evaluate_independence(graph_for(a, b), a.evidence_id, b.evidence_id)
    assert result.independent
    assert result.reasons == ("distinct_families_with_complete_disjoint_declared_inputs",)
    assert not result.shared_dependency_ids


@pytest.mark.parametrize("changes,reason", [
    ({"evidence_family": "signal_location"}, "same_evidence_family"),
    ({"lineage_complete": False}, "incomplete_declared_lineage"),
    ({"derived_from": []}, "incomplete_declared_lineage"),
    ({"covariance_source_id": "undeclared-covariance"}, "incomplete_declared_lineage"),
    ({"source_signals": ["a"]}, "shared_source_signals"),
    ({"source_window": {"window_id": "window:a"}}, "shared_source_window"),
    ({"derived_from": [{"kind": "observation", "dependency_id": "observation:a"}]}, "shared_upstream_dependencies"),
])
def test_conservative_non_corroboration(changes, reason):
    a, b = evidence(), evidence("b", "instrumentation", **changes)
    graph = graph_for(a, b)
    result = evaluate_independence(graph, a.evidence_id, b.evidence_id)
    assert not result.independent
    assert reason in result.reasons
    assert assess(graph).level == MaturityLevel.L1


def test_shared_source_aliases_context_and_assumptions_are_visible():
    a = evidence(context_refs=["context:shared"], assumption_set=["common-calibration"])
    b = evidence("b", "instrumentation", context_refs=a.context_refs, assumption_set=a.assumption_set)
    graph = graph_for(a, b, observations=(observation(), observation("b", source_id="source:a")))
    result = evaluate_independence(graph, a.evidence_id, b.evidence_id)
    assert not result.independent
    assert result.shared_source_ids == ("source:a",)
    assert result.shared_context_ids == ("context:shared",)
    assert result.shared_assumptions == ("common-calibration",)


def test_covariance_and_mahalanobis_do_not_double_count():
    a = evidence(family="covariance_geometry", evidence_method="covariance_divergence", covariance_source_id="observation:a")
    b = evidence("b", "covariance_geometry", evidence_method="mahalanobis_distance", covariance_source_id="observation:a",
                 derived_from=[{"kind": "observation", "dependency_id": "observation:a"}])
    graph = graph_for(a, b)
    pair = evaluate_independence(graph, a.evidence_id, b.evidence_id)
    assert {"same_evidence_family", "shared_covariance_source", "shared_upstream_dependencies"} <= set(pair.reasons)
    assert "observation:a" in pair.shared_dependency_ids
    assert assess(graph).level == MaturityLevel.L1
    # Relabeling a downstream metric still retains its covariance lineage.
    child = evidence("b", "trend", derived_from=[{"kind": "evidence", "dependency_id": b.evidence_id}])
    pair = evaluate_independence(graph_for(a, b, child), a.evidence_id, child.evidence_id)
    assert "shared_covariance_source" in pair.reasons
    missing = evidence(family="covariance_geometry", covariance_source_id="undeclared-covariance")
    other = evidence("b", "instrumentation")
    pair = evaluate_independence(graph_for(missing, other), missing.evidence_id, other.evidence_id)
    assert "incomplete_declared_lineage" in pair.reasons


def test_maturity_progression_and_regression_are_finding_specific():
    a, b = evidence(), evidence("b", "instrumentation")
    graph = graph_for(a, b)
    l0 = assess(graph, persistent=False)
    l1 = assess(graph, relevant=(a.evidence_id,))
    l2 = assess(graph)
    assert (l0.level, l1.level, l2.level) == (MaturityLevel.L0, MaturityLevel.L1, MaturityLevel.L2)
    regressed = assess(graph, relevant=(a.evidence_id,), evaluated_at=LATER)
    assert regressed.level == MaturityLevel.L1
    assert assess(graph, persistent=False, evaluated_at=LATER).level == MaturityLevel.L0
    assert assess(graph, finding_id="finding-2", persistent=False).level == MaturityLevel.L0
    assert l2.level == MaturityLevel.L2
    assert MaturityEvaluation.model_validate_json(l2.model_dump_json()) == l2
    assert l2.supporting_evidence_ids == l2.relevant_evidence_ids
    assert l0.persistence.gates[0].reasons == ("insufficient_observations",)


def test_unknown_persistence_is_L0_and_all_applicable_gates_must_pass():
    graph = graph_for(evidence(), evidence("b", "instrumentation"))
    empty = PersistenceAssessment(finding_id="finding-1", gates=())
    assert assess(graph, persistence=empty).level == MaturityLevel.L0
    passed = assess(graph).persistence.gates[0]
    elapsed = PersistenceGate(**{**passed.as_dict(), "requirement_id": "elapsed-gate", "basis": "elapsed_time", "satisfied": False})
    assert assess(graph, persistence=PersistenceAssessment(finding_id="finding-1", gates=(passed, elapsed))).level == MaturityLevel.L0
    with pytest.raises(ValueError, match="persistence_finding_mismatch"):
        assess(graph, persistence=PersistenceAssessment(finding_id="wrong", gates=()))
    with pytest.raises(ValueError, match="duplicate_persistence_requirement"):
        assess(graph, persistence=PersistenceAssessment(finding_id="finding-1", gates=(passed, passed)))
    with pytest.raises(ValueError, match="relevant_evidence_required"):
        assess(graph, relevant=(), persistence=empty)


def test_independent_extras_cannot_corroborate_unrelated_persistent_evidence():
    a = evidence(lineage_complete=False)
    b, c = evidence("b", "instrumentation"), evidence("c", "relational")
    graph = graph_for(a, b, c, observations=(observation(), observation("b"), observation("c")))
    assert assess(graph, relevant=(a.evidence_id, b.evidence_id, c.evidence_id)).level == MaturityLevel.L1


def test_no_maturity_probability_confidence_or_lifecycle_semantics():
    for contract in (MaturityEvaluation, PersistenceAssessment, PersistenceGate, EvidenceObject, FindingLifecycleEvent):
        assert not {"probability", "confidence"} & contract.model_fields.keys()
    assert "level" not in FindingLifecycleEvent.model_fields
    assert "state" not in MaturityEvaluation.model_fields
    assert "maturity" not in LifecycleChange.model_fields


@pytest.fixture(params=[InMemoryAuthorityDecisionStore, RuntimeAuthorityDecisionStore])
def store(request):
    return request.param()


def test_authority_serialization_append_supersession_and_historical_basis(store):
    first, basis = decision_and_basis()
    assert AuthorityDecision.model_validate_json(first.model_dump_json()) == first
    assert store.append_decision(SCOPE, first, basis) == first
    original = store.get_record(SCOPE, "system-1", first.decision_id)
    assert original == {"decision": first.as_dict(), "basis": basis.as_dict()}
    # Idempotent replay does not add another record.
    store.append_decision(SCOPE, first, basis)
    second, later_basis = decision_and_basis(policy_version="2", supersedes_decision_id=first.decision_id,
                                            decision_timestamp=LATER, effective_timestamp=AT)
    store.append_decision(SCOPE, second, later_basis)
    third, third_basis = decision_and_basis(policy_version="3", supersedes_decision_id=second.decision_id)
    store.append_decision(SCOPE, third, third_basis)
    assert store.history(SCOPE, "system-1", finding_id="finding-1") == [first, second, third]
    assert store.get_record(SCOPE, "system-1", first.decision_id) == original
    assert original["decision"]["policy_version"] == "1"
    assert original["decision"]["decision_timestamp"] == AT
    assert original["decision"]["effective_timestamp"] == LATER
    # Mutating returned or caller-owned JSON cannot rewrite stored history.
    original["basis"]["snapshots"][0]["payload"]["changed"] = True
    basis.snapshots[0].payload["changed"] = True
    assert "changed" not in store.get_record(SCOPE, "system-1", first.decision_id)["basis"]["snapshots"][0]["payload"]
    with pytest.raises(ValidationError, match="content_identity_mismatch"):
        store.append_decision(SCOPE, first, basis)


def test_authority_conflicts_and_scope_isolation(store):
    first, basis = decision_and_basis()
    store.append_decision(SCOPE, first, basis)
    assert store.history(AuthenticatedPhase4Scope(tenant_scope_id="tenant-2", workspace_id="workspace-1"), "system-1") == []
    assert store.history(AuthenticatedPhase4Scope(tenant_scope_id="tenant-1", workspace_id="workspace-2"), "system-1") == []
    assert store.history(SCOPE, "other-system") == []
    assert store.history(SCOPE, "system-1", finding_id="other-finding") == []
    assert store.get_record(SCOPE, "system-1", "absent") is None
    with pytest.raises(ValueError, match="authenticated_scope_required"):
        store.history(None, "system-1")
    for changes, reason in [
        ({"supersedes_decision_id": "missing"}, "superseded_decision_missing"),
        ({"supersedes_decision_id": first.decision_id, "requested_operation": "close_finding"}, "supersession_finding_or_operation_mismatch"),
    ]:
        changed, changed_basis = decision_and_basis(**changes)
        with pytest.raises(AuthorityRecordConflict, match=reason):
            store.append_decision(SCOPE, changed, changed_basis)
    successor, successor_basis = decision_and_basis(supersedes_decision_id=first.decision_id)
    store.append_decision(SCOPE, successor, successor_basis)
    fork, fork_basis = decision_and_basis(supersedes_decision_id=first.decision_id, source_run_id="fork")
    with pytest.raises(AuthorityRecordConflict, match="already_has_successor"):
        store.append_decision(SCOPE, fork, fork_basis)
    assert len(store.history(SCOPE, "system-1")) == 2


@pytest.mark.parametrize("changes,reason", [
    ({"policy_version": "wrong"}, "decision_policy_version_mismatch"),
    ({"dependency_graph_snapshot_id": "missing"}, "decision_graph_snapshot_mismatch"),
    ({"context_snapshot_id": "missing"}, "decision_context_snapshot_missing"),
    ({"active_model_before": "active-pointer"}, "decision_model_snapshot_missing"),
    ({"maturity_at_decision": "L0"}, "decision_maturity_evidence_mismatch"),
    ({"lifecycle_state_at_decision": "closed"}, "decision_lifecycle_snapshot_mismatch"),
    ({"limiting_evidence": ["missing"]}, "decision_evidence_snapshot_missing"),
    ({"contradicting_evidence": ["missing"]}, "decision_evidence_snapshot_missing"),
])
def test_authority_basis_requires_exact_snapshots(changes, reason):
    first, basis = decision_and_basis()
    changed = AuthorityDecision.model_validate({**first.as_dict(), "decision_id": "", **changes})
    store = InMemoryAuthorityDecisionStore()
    with pytest.raises(ValueError, match=reason):
        store.append_decision(SCOPE, changed, basis)
    assert store.history(SCOPE, "system-1") == []


def test_authority_replays_maturity_instead_of_trusting_claimed_level():
    decision, basis = decision_and_basis()
    maturity = MaturityEvaluation.model_validate({**basis.maturity.as_dict(), "evaluation_id": "", "level": "L0"})
    basis = DecisionBasis(**{**basis.as_dict(), "maturity": maturity})
    decision = AuthorityDecision.model_validate({**decision.as_dict(), "decision_id": "", "maturity_snapshot_id": maturity.evaluation_id, "maturity_at_decision": "L0"})
    with pytest.raises(ValueError, match="maturity_replay_mismatch"):
        InMemoryAuthorityDecisionStore().append_decision(SCOPE, decision, basis)


def test_runtime_store_reopens_and_serializes_concurrent_writers():
    def append(index):
        decision, basis = decision_and_basis(source_run_id=f"run-{index}")
        RuntimeAuthorityDecisionStore().append_decision(SCOPE, decision, basis)
        return decision.decision_id

    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = set(executor.map(append, range(8)))
    reopened = RuntimeAuthorityDecisionStore()
    assert {item.decision_id for item in reopened.history(SCOPE, "system-1")} == ids
    assert all(reopened.get_record(SCOPE, "system-1", item) for item in ids)


def test_runtime_store_fails_closed_without_fallback(monkeypatch):
    def fail(*args):
        raise OSError("unavailable")
    monkeypatch.setattr(runtime_db, "mutate_latest_payload", fail)
    decision, basis = decision_and_basis()
    with pytest.raises(AuthorityStorageUnavailable, match="append_failed"):
        RuntimeAuthorityDecisionStore().append_decision(SCOPE, decision, basis)
    monkeypatch.setattr(runtime_db, "read_latest_payload", fail)
    with pytest.raises(AuthorityStorageUnavailable, match="read_failed"):
        RuntimeAuthorityDecisionStore().history(SCOPE, "system-1")


@pytest.mark.parametrize("outcome", list(AuthorityOutcome))
def test_outcomes_are_records_and_operations_have_no_handlers(outcome):
    review = {"required": True, "status": "pending"} if outcome == AuthorityOutcome.HUMAN_REVIEW_REQUIRED else {"required": False, "status": "not_required"}
    decision, basis = decision_and_basis(decision_outcome=outcome, human_review=review)
    assert InMemoryAuthorityDecisionStore().append_decision(SCOPE, decision, basis) == decision
    assert not hasattr(RuntimeAuthorityDecisionStore, "activate_baseline")
    assert "physical_control" not in {item.value for item in RequestedOperation}


def test_human_review_consistency():
    with pytest.raises(ValidationError):
        HumanReview(required=True, status="approved")
    with pytest.raises(ValidationError):
        HumanReview(required=True, status="not_required")
    with pytest.raises(ValidationError):
        decision_and_basis(decision_outcome="permitted", human_review={"required": True, "status": "pending"})
    decision, _ = decision_and_basis(decision_outcome="permitted", human_review={
        "required": True, "status": "approved", "reviewer_identity": "operator-1", "reviewed_at": AT, "rationale": "Reviewed software evidence presentation",
    })
    assert decision.human_review.reviewer_identity == "operator-1"


def test_authority_rejects_later_knowledge_and_rebound_event_identity():
    store = InMemoryAuthorityDecisionStore()
    first, basis = decision_and_basis()
    store.append_decision(SCOPE, first, basis)
    changed_event = FindingLifecycleEvent.model_validate({**basis.lifecycle.as_dict(), "reasons": ["later interpretation"]})
    changed_basis = DecisionBasis.model_validate({**basis.as_dict(), "lifecycle": changed_event})
    second, _ = decision_and_basis(source_run_id="run-2")
    with pytest.raises(AuthorityRecordConflict, match="immutable_basis_identity_conflict"):
        store.append_decision(SCOPE, second, changed_basis)
    future_context = snapshot("context", version="2", created_at=LATER)
    future_basis = DecisionBasis.model_validate({**basis.as_dict(), "snapshots": [
        future_context, *[item for item in basis.snapshots if item.kind != "context"],
    ]})
    future_decision, _ = decision_and_basis(context_snapshot_id=future_context.snapshot_id)
    with pytest.raises(ValueError, match="later_knowledge"):
        store.append_decision(SCOPE, future_decision, future_basis)
    assert store.history(SCOPE, "system-1") == [first]


def materialize_finding():
    record = {
        "run_id": "run-lifecycle", "created_at": AT, "completed_at": AT,
        "finding_identity_snapshot": [{"source_finding_id": "one", "finding": {"condition_id": "one", "headline": "Observed deviation"}}],
    }
    workflow.materialize_evidence_finding_cases(attach_dataset_scope(record))
    return workflow.evidence_finding_id("run-lifecycle", "one")


def lifecycle_change(state="new", previous=None):
    return LifecycleChange(state=state, previous_event_id=previous, effective_at=AT,
                           evidence_ids=(evidence().evidence_id,), reasons=("explicit_event",),
                           source_run_id="run-1", provenance=PROVENANCE).as_dict()


def test_lifecycle_reuses_existing_append_only_event_log_with_independent_state():
    finding_id = materialize_finding()
    original = workflow.read_finding_case(finding_id)
    first = workflow.record_governance_lifecycle(finding_id, change=lifecycle_change(), actor="adapter",
                                               expected_version=0, idempotency_key="event-1", recorded_at=AT)
    replay = workflow.record_governance_lifecycle(finding_id, change=lifecycle_change(), actor="adapter",
                                                expected_version=0, idempotency_key="event-1", recorded_at=LATER)
    assert replay == first
    workflow.update_finding_workflow(finding_id, changes={"status": "investigating"}, actor="operator", expected_version=1)
    second = workflow.record_governance_lifecycle(finding_id, change=lifecycle_change("recovering", first["event_id"]), actor="adapter",
                                                expected_version=2, idempotency_key="event-2", recorded_at=LATER)
    assert [item["version"] for item in workflow.governance_lifecycle_history(finding_id)] == [1, 3]
    assert workflow.governance_lifecycle_history(finding_id) == [first, second]
    assert first["state"] == "new" and second["state"] == "recovering"
    assert second["previous_event_id"] == first["event_id"]
    assert second["effective_at"] == AT and second["recorded_at"] == LATER
    case = workflow.read_finding_case(finding_id)
    assert case["evidence"] == original["evidence"]
    assert case["workflow"]["status"] == "investigating"
    assert FindingLifecycleEvent.model_validate_json(FindingLifecycleEvent.model_validate(first).model_dump_json()).as_dict() == first
    first["reasons"].append("changed")
    assert workflow.governance_lifecycle_history(finding_id)[0]["reasons"] == ["explicit_event"]


def test_lifecycle_stale_predecessor_and_cross_scope_rejected():
    finding_id = materialize_finding()
    workflow.record_governance_lifecycle(finding_id, change=lifecycle_change(), actor="adapter",
                                        expected_version=0, idempotency_key="event-1", recorded_at=AT)
    for version, reason in [(0, "stale_workflow_version"), (1, "stale_lifecycle_predecessor")]:
        with pytest.raises(workflow.FindingWorkflowConflictError, match=reason):
            workflow.record_governance_lifecycle(finding_id, change=lifecycle_change("persistent"), actor="adapter",
                                                expected_version=version, idempotency_key="event-2", recorded_at=LATER)
    assert len(workflow.governance_lifecycle_history(finding_id)) == 1
    with dataset_scope_context(build_dataset_scope(user_id="other-user")):
        with pytest.raises(workflow.FindingNotFoundError):
            workflow.governance_lifecycle_history(finding_id)
        with pytest.raises(workflow.FindingNotFoundError):
            workflow.record_governance_lifecycle(finding_id, change=lifecycle_change(), actor="adapter",
                                                expected_version=1, idempotency_key="other", recorded_at=AT)


@pytest.mark.parametrize("state", list(LifecycleState))
def test_future_lifecycle_states_representable_without_transition_rules(state):
    assert LifecycleChange.model_validate(lifecycle_change(state)).state == state
