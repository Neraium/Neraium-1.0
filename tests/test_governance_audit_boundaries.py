"""Audit reconstruction and upgrades retain the originally recorded basis."""
import sqlite3

import pytest

from app.governance.authority_store import AuthorityRecordConflict, DecisionBasis, InMemoryAuthorityDecisionStore, RuntimeAuthorityDecisionStore
from app.governance.contracts import AuthorityDecision, FindingLifecycleEvent
from app.governance.maturity import MaturityEvaluation
from app.services import finding_workflow as workflow, runtime_db
from test_evidence_governance import (
    AT, LATER, SCOPE, assess, decision_and_basis, graph_for, lifecycle_change,
    materialize_finding, observation, evidence,
)


def test_existing_observation_identity_cannot_be_rebound_by_later_decision():
    first, basis = decision_and_basis()
    store = InMemoryAuthorityDecisionStore()
    store.append_decision(SCOPE, first, basis)
    changed_graph = graph_for(*basis.graph.evidence, observations=(
        observation("a", source_id="different-acquisition"), observation("b"),
    ))
    changed_maturity = assess(changed_graph)
    changed_basis = DecisionBasis(**{**basis.as_dict(), "graph": changed_graph, "maturity": changed_maturity})
    successor = AuthorityDecision.model_validate({
        **first.as_dict(), "decision_id": "", "supersedes_decision_id": first.decision_id,
        "dependency_graph_snapshot_id": changed_graph.snapshot_id,
        "maturity_snapshot_id": changed_maturity.evaluation_id,
    })
    with pytest.raises(AuthorityRecordConflict, match="immutable_basis_identity_conflict:observation:a"):
        store.append_decision(SCOPE, successor, changed_basis)
    assert store.get_record(SCOPE, "system-1", first.decision_id)["basis"] == basis.as_dict()
    assert store.history(SCOPE, "system-1") == [first]


def test_decision_cannot_claim_knowledge_recorded_later():
    decision, basis = decision_and_basis()
    later_event = FindingLifecycleEvent(**{**basis.lifecycle.as_dict(), "recorded_at": LATER})
    basis = DecisionBasis(**{**basis.as_dict(), "lifecycle": later_event})
    with pytest.raises(ValueError, match="decision_basis_contains_later_knowledge"):
        InMemoryAuthorityDecisionStore().append_decision(SCOPE, decision, basis)


@pytest.mark.parametrize("future_node", ["evidence", "observation"])
def test_decision_rejects_source_windows_after_decision_time(future_node):
    decision, basis = decision_and_basis()
    window = {"window_id": "window:a", "started_at": AT, "ended_at": LATER}
    a = evidence(source_window=window) if future_node == "evidence" else evidence()
    raw = observation(source_window=window) if future_node == "observation" else observation()
    graph = graph_for(a, evidence("b", "instrumentation"), observations=(raw, observation("b")))
    maturity = assess(graph, evaluated_at=LATER)
    lifecycle = FindingLifecycleEvent(**{
        **basis.lifecycle.as_dict(), "evidence_ids": maturity.relevant_evidence_ids,
    })
    basis = DecisionBasis(**{
        **basis.as_dict(), "graph": graph, "maturity": maturity, "lifecycle": lifecycle,
    })
    decision = AuthorityDecision.model_validate({
        **decision.as_dict(), "decision_id": "",
        "evidence_snapshot_ids": maturity.relevant_evidence_ids,
        "dependency_graph_snapshot_id": graph.snapshot_id,
        "maturity_snapshot_id": maturity.evaluation_id,
    })
    store = InMemoryAuthorityDecisionStore()
    with pytest.raises(ValueError, match="decision_basis_contains_later_knowledge"):
        store.append_decision(SCOPE, decision, basis)
    assert store.history(SCOPE, "system-1") == []


def test_lifecycle_schema_upgrade_preserves_existing_events_and_append_only_triggers():
    finding_id = materialize_finding()
    workflow.update_finding_workflow(
        finding_id, changes={"status": "investigating"}, actor="operator",
        expected_version=0, idempotency_key="original-event", recorded_at=AT,
    )
    before = workflow.read_finding_case(finding_id)
    original_event = workflow._events(finding_id)[0]
    # Recreate the previous CHECK vocabulary in this isolated test database,
    # keeping the original event row byte-for-byte, then perform the upgrade.
    with runtime_db.db_connection() as connection:
        ddl = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'finding_workflow_events'").fetchone()[0]
        old_ddl = ddl.replace(", 'governance_lifecycle_recorded'", "")
        assert old_ddl != ddl
        rows = connection.execute("SELECT * FROM finding_workflow_events").fetchall()
        connection.execute("DROP TABLE finding_workflow_events")
        connection.execute(old_ddl)
        connection.executemany("INSERT INTO finding_workflow_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [tuple(row) for row in rows])
        connection.execute("DELETE FROM runtime_schema_migrations WHERE migration_id = '014_governance_lifecycle_events'")
    runtime_db.init_runtime_db()
    runtime_db.init_runtime_db()  # Upgrade is idempotent.
    assert workflow.read_finding_case(finding_id) == before
    assert workflow._events(finding_id) == [original_event]
    lifecycle = workflow.record_governance_lifecycle(
        finding_id, change=lifecycle_change(), actor="adapter", expected_version=1,
        idempotency_key="new-lifecycle", recorded_at=LATER,
    )
    assert lifecycle["version"] == 2
    assert workflow._events(finding_id)[0] == original_event
    assert workflow.read_finding_case(finding_id)["workflow"]["status"] == "investigating"
    for statement in (
        "UPDATE finding_workflow_events SET actor = 'changed'",
        "DELETE FROM finding_workflow_events",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="finding_workflow_events_append_only"):
            with runtime_db.db_connection() as connection:
                connection.execute(statement)
    with runtime_db.db_connection() as connection:
        indexes = {row["name"] for row in connection.execute("PRAGMA index_list(finding_workflow_events)")}
        assert "idx_finding_workflow_events_finding_version" in indexes


@pytest.fixture(params=[InMemoryAuthorityDecisionStore, RuntimeAuthorityDecisionStore])
def temporal_store(request):
    return request.param()


def test_supersession_chronology_rejects_atomically_and_allows_retroactive_effect(temporal_store):
    first, basis = decision_and_basis(decision_timestamp=LATER)
    temporal_store.append_decision(SCOPE, first, basis)
    original = temporal_store.get_record(SCOPE, "system-1", first.decision_id)
    earlier, earlier_basis = decision_and_basis(supersedes_decision_id=first.decision_id)
    with pytest.raises(AuthorityRecordConflict, match="supersession_precedes_predecessor_decision"):
        temporal_store.append_decision(SCOPE, earlier, earlier_basis)
    assert temporal_store.history(SCOPE, "system-1") == [first]
    assert temporal_store.get_record(SCOPE, "system-1", first.decision_id) == original
    # Equality is allowed, including equivalent timezone representations. The
    # failed append must not consume the predecessor's single successor slot.
    successor, successor_basis = decision_and_basis(
        supersedes_decision_id=first.decision_id,
        decision_timestamp="2026-09-06T13:00:00+02:00", effective_timestamp=AT,
    )
    temporal_store.append_decision(SCOPE, successor, successor_basis)
    assert temporal_store.history(SCOPE, "system-1") == [first, successor]
    assert successor.effective_timestamp == AT
    assert temporal_store.get_record(SCOPE, "system-1", first.decision_id) == original


def test_future_effective_lifecycle_cannot_supply_decision_time_state(temporal_store):
    decision, basis = decision_and_basis(effective_timestamp=AT)
    future = FindingLifecycleEvent(**{**basis.lifecycle.as_dict(), "effective_at": LATER})
    basis = DecisionBasis(**{**basis.as_dict(), "lifecycle": future})
    with pytest.raises(ValueError, match="decision_lifecycle_not_yet_effective"):
        temporal_store.append_decision(SCOPE, decision, basis)
    assert temporal_store.history(SCOPE, "system-1") == []
    applicable = AuthorityDecision.model_validate({
        **decision.as_dict(), "decision_id": "", "decision_timestamp": LATER,
    })
    temporal_store.append_decision(SCOPE, applicable, basis)
    assert temporal_store.history(SCOPE, "system-1") == [applicable]


def test_future_effective_lifecycle_remains_recordable():
    finding = materialize_finding()
    change = {**lifecycle_change(), "effective_at": LATER}
    event = workflow.record_governance_lifecycle(
        finding, change=change, actor="adapter", expected_version=0,
        idempotency_key="scheduled", recorded_at=AT,
    )
    assert event["recorded_at"] == AT and event["effective_at"] == LATER
    assert workflow.governance_lifecycle_history(finding) == [event]
    assert workflow.read_finding_case(finding)["workflow"]["status"] == "open"


TEMPORAL_CASES = (
    "evidence_created", "evidence_effective", "evidence_window",
    "upstream_created", "upstream_effective", "upstream_window",
    "observation_window", "unrelated_evidence",
)


def graph_with_later_knowledge(case):
    window = {"window_id": "window:a", "started_at": AT, "ended_at": LATER}
    changes = {}
    if case.endswith("created"):
        changes["created_at"] = LATER
    elif case.endswith("effective"):
        changes["effective_at"] = LATER
    elif case.endswith("window") and case != "observation_window":
        changes["source_window"] = window
    a, b = evidence(**changes), evidence("b", "instrumentation")
    nodes = [a, b]
    relevant = (a.evidence_id, b.evidence_id)
    if case.startswith("upstream"):
        child = evidence("c", "trend", derived_from=[{"kind": "evidence", "dependency_id": a.evidence_id}])
        nodes.append(child)
        relevant = (child.evidence_id, b.evidence_id)
    if case == "unrelated_evidence":
        nodes.append(evidence("unused", created_at=LATER, derived_from=[]))
    raw = observation(source_window=window) if case == "observation_window" else observation()
    return graph_for(*nodes, observations=(raw, observation("b"))), relevant


@pytest.mark.parametrize("case", TEMPORAL_CASES)
def test_maturity_rejects_future_knowledge_in_retained_graph(case):
    graph, relevant = graph_with_later_knowledge(case)
    with pytest.raises(ValueError, match="graph_contains_later_knowledge"):
        assess(graph, relevant=relevant, evaluated_at=AT)
    # Exact boundary and equivalent UTC offsets are admissible.
    evaluated = assess(graph, relevant=relevant, evaluated_at="2026-09-06T13:00:00+02:00")
    assert evaluated.evaluated_at == LATER


@pytest.mark.parametrize("case", TEMPORAL_CASES)
def test_storage_independently_rejects_backdated_maturity(temporal_store, monkeypatch, case):
    graph, relevant = graph_with_later_knowledge(case)
    valid = assess(graph, relevant=relevant, evaluated_at=LATER)
    # Simulate an imported historical evaluation with a valid content ID, not
    # an object produced by the corrected evaluator.
    backdated = MaturityEvaluation.model_validate({
        **valid.as_dict(), "evaluation_id": "", "evaluated_at": AT,
    })
    decision, basis = decision_and_basis(decision_timestamp=LATER)
    lifecycle = FindingLifecycleEvent(**{
        **basis.lifecycle.as_dict(), "evidence_ids": relevant, "recorded_at": LATER,
    })
    basis = DecisionBasis(**{
        **basis.as_dict(), "graph": graph, "maturity": backdated, "lifecycle": lifecycle,
    })
    decision = AuthorityDecision.model_validate({
        **decision.as_dict(), "decision_id": "", "evidence_snapshot_ids": relevant,
        "dependency_graph_snapshot_id": graph.snapshot_id,
        "maturity_snapshot_id": backdated.evaluation_id, "maturity_at_decision": backdated.level,
    })
    # Even a replay implementation returning the claimed result cannot bypass
    # the separate storage-side temporal validation.
    monkeypatch.setattr("app.governance.authority_store.evaluate_maturity", lambda **kwargs: backdated)
    with pytest.raises(ValueError, match="graph_contains_later_knowledge"):
        temporal_store.append_decision(SCOPE, decision, basis)
    assert temporal_store.history(SCOPE, "system-1") == []
