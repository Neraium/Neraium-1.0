import sqlite3

import pytest

from app.governance.contracts import FindingLifecycleEvent, LifecycleState
from app.services import evidence_store, finding_workflow, runtime_db
from app.services.dataset_scope import build_dataset_scope, dataset_scope_context
from test_evidence_governance import AT as TIME, LATER, PROVENANCE, evidence, graph_for as graph, assess as maturity
from test_finding_workflow import _record


def change(state="new", previous=None):
    return {"state": state, "previous_event_id": previous, "effective_at": TIME,
            "evidence_ids": [evidence().evidence_id], "reasons": ["observed_change"],
            "source_run_id": "run-1", "provenance": PROVENANCE}


def create_finding():
    evidence_store.upsert_evidence_run(_record("governance-run"))
    return finding_workflow.evidence_finding_id("governance-run", "condition-a")


def record(finding_id, payload, version=0, key="first"):
    return finding_workflow.record_governance_lifecycle(
        finding_id, change=payload, actor="reviewer-a", expected_version=version,
        idempotency_key=key, recorded_at=LATER,
    )


def test_lifecycle_reuses_append_only_finding_events_and_version_order():
    finding = create_finding()
    before = finding_workflow.read_finding_case(finding)
    first = record(finding, change())
    assert record(finding, change()) == first
    assert first["version"] == 1
    finding_workflow.update_finding_workflow(
        finding, changes={"status": "investigating"}, actor="reviewer-a",
        expected_version=1, idempotency_key="operator-status",
    )
    second = record(finding, change("recovering", first["event_id"]), version=2, key="second")
    history = finding_workflow.governance_lifecycle_history(finding)
    assert history == [first, second]
    assert [item["version"] for item in history] == [1, 3]
    assert FindingLifecycleEvent.model_validate(second).state == LifecycleState.RECOVERING
    history[0]["state"] = "closed"
    assert finding_workflow.governance_lifecycle_history(finding)[0] == first
    after = finding_workflow.read_finding_case(finding)
    assert after["evidence"] == before["evidence"]
    assert after["workflow"]["status"] == "investigating"
    assert "maturity" not in first
    assert first["effective_at"] == TIME and first["recorded_at"] == LATER


def test_maturity_regression_does_not_change_lifecycle_or_operator_status():
    finding = create_finding()
    first = record(finding, change("persistent"))
    a, b = evidence(), evidence("b", "instrumentation")
    assert maturity(graph(a, b)).level.value == "L2"
    assert maturity(graph(a), persistent=False).level.value == "L0"
    assert finding_workflow.governance_lifecycle_history(finding) == [first]
    assert finding_workflow.read_finding_case(finding)["workflow"]["status"] == "open"


def test_lifecycle_conflicts_and_scope_fail_closed():
    finding = create_finding()
    first = record(finding, change())
    with pytest.raises(finding_workflow.FindingWorkflowConflictError, match="idempotency_key_reused"):
        record(finding, change("closed"))
    with pytest.raises(finding_workflow.FindingWorkflowConflictError, match="stale_workflow_version"):
        record(finding, change("persistent", first["event_id"]), key="stale")
    with pytest.raises(finding_workflow.FindingWorkflowConflictError, match="stale_lifecycle_predecessor"):
        record(finding, change("persistent"), version=1, key="bad-parent")
    with dataset_scope_context(build_dataset_scope(user_id="other-user")):
        with pytest.raises(finding_workflow.FindingNotFoundError):
            record(finding, change())
        with pytest.raises(finding_workflow.FindingNotFoundError):
            finding_workflow.governance_lifecycle_history(finding)
    with pytest.raises(finding_workflow.FindingNotFoundError):
        record("unknown", change())
    assert finding_workflow.governance_lifecycle_history(finding) == [first]


@pytest.mark.parametrize("state", list(LifecycleState))
def test_future_lifecycle_vocabulary_is_representable_without_maturity(state):
    result = record(create_finding(), change(state.value))
    assert result["state"] == state.value
    assert "maturity" not in result


def test_lifecycle_migration_preserves_existing_rows_and_database_constraints():
    with runtime_db.db_connection() as current:
        schema = runtime_db._table_sql(current, "finding_workflow_events")
    old_schema = schema.replace(", 'governance_lifecycle_recorded'", "")
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("CREATE TABLE finding_cases (finding_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO finding_cases VALUES ('finding-old')")
        connection.execute(old_schema)
        connection.execute("CREATE TABLE runtime_schema_migrations (migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        for migration in runtime_db.RUNTIME_SCHEMA_MIGRATIONS:
            if migration != "014_governance_lifecycle_events":
                connection.execute("INSERT INTO runtime_schema_migrations VALUES (?, ?)", (migration, TIME))
        original = ("event-old", "finding-old", 1, "workflow_updated", TIME, "operator", "retry-old", '{"original": true}')
        connection.execute("INSERT INTO finding_workflow_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)", original)
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        runtime_db._apply_runtime_migrations(connection)
        connection.commit()
        assert tuple(connection.execute("SELECT * FROM finding_workflow_events").fetchone()) == original
        assert "governance_lifecycle_recorded" in runtime_db._table_sql(connection, "finding_workflow_events")
        for sql in ("UPDATE finding_workflow_events SET actor = 'rewrite'", "DELETE FROM finding_workflow_events"):
            with pytest.raises(sqlite3.IntegrityError, match="append_only"):
                connection.execute(sql)
        # The migration is idempotent and retains FK and uniqueness enforcement.
        runtime_db._apply_runtime_migrations(connection)
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            connection.execute("INSERT INTO finding_workflow_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               ("different", *original[1:]))
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            connection.execute("INSERT INTO finding_workflow_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               ("missing-parent", "missing-finding", 1, "governance_lifecycle_recorded", TIME, "actor", "new", "{}"))
