from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.services import evidence_store, runtime_db
from app.services.dataset_scope import attach_dataset_scope, build_dataset_scope, set_current_dataset_scope
from app.services.finding_workflow import (
    FindingWorkflowConflictError,
    evidence_finding_id,
    materialize_live_finding_cases,
    read_finding_case,
    update_finding_workflow,
)
from app.services.upload_evidence import build_evidence_record_from_result


def _record(run_id: str, finding_ids: tuple[str, ...] = ("condition-a",)) -> dict:
    return {
        "run_id": run_id,
        "source_type": "csv_upload",
        "source_name": "plant.csv",
        "status": "completed",
        "created_at": "2026-08-11T08:00:00+00:00",
        "completed_at": "2026-08-11T08:01:00+00:00",
        "observation_status": "open",
        "operator_feedback_history": [],
        "finding_status_history": [],
        "input_hash": "input-immutable",
        "result_hash": "result-immutable",
        "evidence_hash": "evidence-immutable",
        "finding_identity_snapshot": [
            {
                "source_finding_id": finding_id,
                "finding": {
                    "condition_id": finding_id,
                    "headline": f"Finding {finding_id}",
                    "priority": "high" if index == 0 else "low",
                },
            }
            for index, finding_id in enumerate(finding_ids)
        ],
    }


def test_new_evidence_record_preserves_every_source_finding_identity() -> None:
    conditions = [
        {"condition_id": "condition-a", "headline": "First condition", "priority": "high"},
        {"condition_id": "condition-b", "headline": "Second condition", "priority": "low"},
    ]
    record = build_evidence_record_from_result(
        run_id="snapshot-run",
        filename="plant.csv",
        source_type="csv_upload",
        result={
            "row_count": 20,
            "column_count": 3,
            "analysis_result": {"conditions": conditions},
            "sii_intelligence": {},
            "baseline_analysis": {},
            "data_quality": {},
        },
        created_at="2026-08-11T08:00:00+00:00",
        completed_at="2026-08-11T08:01:00+00:00",
        status="completed",
        initiated_by="operator@example.com",
    )

    assert [
        item["source_finding_id"] for item in record["finding_identity_snapshot"]
    ] == ["condition-a", "condition-b"]
    assert record["finding_identity_snapshot"][0]["finding"]["priority"] == "high"


def test_two_findings_from_one_run_have_isolated_workflows_and_immutable_evidence(client) -> None:
    record = evidence_store.upsert_evidence_run(_record("multi-run", ("condition-a", "condition-b")))
    original = runtime_db.read_evidence_run_db("multi-run")

    listed = client.get("/api/findings?source_kind=evidence_run&source_run_id=multi-run")
    assert listed.status_code == 200
    findings = listed.json()["findings"]
    assert {item["source"]["finding_key"] for item in findings} == {"condition-a", "condition-b"}

    first = next(item for item in findings if item["source"]["finding_key"] == "condition-a")
    second = next(item for item in findings if item["source"]["finding_key"] == "condition-b")
    updated = client.patch(
        f"/api/findings/{first['finding_id']}/workflow",
        json={
            "expected_version": 0,
            "status": "investigating",
            "assignment": {"target_type": "team", "label": "Mechanical"},
            "user_priority": "critical",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["workflow"]["effective_priority"] == "critical"
    assert client.get(f"/api/findings/{second['finding_id']}").json()["workflow"] == second["workflow"]
    assert runtime_db.read_evidence_run_db("multi-run") == original
    assert record["evidence_hash"] == "evidence-immutable"


def test_ambiguous_historical_run_level_assignment_is_not_fanned_out(client) -> None:
    record = _record("historical-multi", ("one", "two"))
    runtime_db.upsert_evidence_run_db(record)
    runtime_db.append_finding_status_event_db(
        "historical-multi",
        {
            "event_id": "legacy-assignment",
            "state": "investigating",
            "assignee": "Legacy Engineer",
            "actor": "legacy@example.com",
            "recorded_at": "2026-08-11T09:00:00+00:00",
        },
    )

    findings = client.get(
        "/api/findings?source_kind=evidence_run&source_run_id=historical-multi"
    ).json()["findings"]
    assert len(findings) == 2
    assert all(item["workflow"]["version"] == 0 for item in findings)
    assert all(item["workflow"]["assignment"] is None for item in findings)
    legacy = client.get("/api/evidence/runs/historical-multi").json()
    assert legacy["finding_assignee"] == "Legacy Engineer"
    assert legacy["observation_status"] == "investigating"


def test_unambiguous_legacy_write_uses_one_event_and_replays_without_duplicates(client) -> None:
    evidence_store.upsert_evidence_run(_record("single-run"))
    payload = {
        "state": "monitoring",
        "assignee": "Alex",
        "work_order_reference": "WO-42",
    }
    headers = {"X-Request-Id": "legacy-status-request-1"}
    first = client.post("/api/evidence/runs/single-run/status", json=payload, headers=headers)
    replay = client.post("/api/evidence/runs/single-run/status", json=payload, headers=headers)

    assert first.status_code == replay.status_code == 200
    finding_id = evidence_finding_id("single-run", "condition-a")
    case = client.get(f"/api/findings/{finding_id}").json()
    assert case["workflow"]["version"] == 1
    assert case["workflow"]["assignment"]["label"] == "Alex"
    activity = client.get(f"/api/findings/{finding_id}/activity").json()
    assert len(activity["events"]) == 1
    with runtime_db.db_connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM finding_status_events WHERE run_id = 'single-run'"
        ).fetchone()[0] == 0


def test_stale_and_concurrent_workflow_edits_conflict(client) -> None:
    evidence_store.upsert_evidence_run(_record("conflict-run"))
    finding_id = evidence_finding_id("conflict-run", "condition-a")
    barrier = Barrier(2)

    def edit(status: str) -> str:
        barrier.wait()
        try:
            update_finding_workflow(
                finding_id,
                changes={"status": status},
                expected_version=0,
                actor=f"{status}@example.com",
            )
            return "updated"
        except FindingWorkflowConflictError as error:
            return f"conflict:{error.current_version}"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(edit, ["investigating", "monitoring"]))
    assert sorted(results) == ["conflict:1", "updated"]

    stale = client.patch(
        f"/api/findings/{finding_id}/workflow",
        json={"expected_version": 0, "status": "acknowledged"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == {"error": "stale_workflow_version", "current_version": 1}


def test_resolution_replay_is_idempotent_and_projects_validation(client) -> None:
    evidence_store.upsert_evidence_run(_record("resolution-run"))
    finding_id = evidence_finding_id("resolution-run", "condition-a")
    payload = {
        "expected_version": 0,
        "idempotency_key": "resolution-request-1",
        "outcome": "maintenance_performed",
        "note": "Cleaned the coil.",
    }
    first = client.post(f"/api/findings/{finding_id}/resolution", json=payload)
    replay = client.post(f"/api/findings/{finding_id}/resolution", json=payload)
    assert first.status_code == replay.status_code == 200
    assert replay.json()["workflow"]["version"] == 1
    assert replay.json()["workflow"]["validation_outcome"] == "maintenance_performed"
    assert replay.json()["workflow"]["validation_note"] == "Cleaned the coil."
    evidence = client.get("/api/evidence/runs/resolution-run").json()
    assert evidence["validation_outcome"] == "maintenance_performed"
    assert len(evidence["operator_feedback_history"]) == 1


def test_scoped_case_is_not_visible_or_mutable_from_another_workspace(client) -> None:
    owner_scope = build_dataset_scope(
        tenant_id="owner@example.com", user_id="owner@example.com", workspace_id="plant-a"
    )
    set_current_dataset_scope(owner_scope)
    scoped_record = attach_dataset_scope(_record("scoped-run"), scope=owner_scope)
    evidence_store.upsert_evidence_run(scoped_record)
    finding_id = evidence_finding_id("scoped-run", "condition-a")

    owner_headers = {
        "X-Neraium-User": "owner@example.com",
        "X-Neraium-Workspace-Id": "plant-a",
    }
    other_headers = {
        "X-Neraium-User": "other@example.com",
        "X-Neraium-Workspace-Id": "plant-b",
    }
    assert client.get(f"/api/findings/{finding_id}", headers=owner_headers).status_code == 200
    assert client.get(f"/api/findings/{finding_id}", headers=other_headers).status_code == 404
    assert client.patch(
        f"/api/findings/{finding_id}/workflow",
        headers=other_headers,
        json={"expected_version": 0, "status": "monitoring"},
    ).status_code == 404
    assert client.post(
        "/api/evidence/runs/scoped-run/status",
        headers=other_headers,
        json={"state": "monitoring"},
    ).status_code == 404


def test_unscoped_live_finding_is_not_claimed_by_first_reader() -> None:
    with runtime_db.db_connection() as connection:
        connection.execute(
            """
            INSERT INTO live_analysis_runs (
                run_id, system_id, baseline_reference, window_start, window_end,
                status, rows_analyzed, signals_analyzed, coverage,
                created_findings_count, updated_findings_count, resolved_findings_count,
                created_at
            ) VALUES ('live-run', 'system', 'baseline', ?, ?, 'completed', 1, 2, 100, 1, 0, 0, ?)
            """,
            ("2026-08-11T08:00:00+00:00", "2026-08-11T09:00:00+00:00", "2026-08-11T09:00:00+00:00"),
        )
        connection.execute(
            """
            INSERT INTO live_findings (
                finding_id, deduplication_key, system_id, relationship_identity,
                finding_classification_json, first_detected_at, last_observed_at,
                current_state, persistence_state_json, latest_evidence_json,
                source_live_analysis_run_id, baseline_reference, created_at, updated_at
            ) VALUES ('live-finding-existing', 'dedupe', 'system', 'flow|pressure', '{}', ?, ?, 'open', '{}', '{}', 'live-run', 'baseline', ?, ?)
            """,
            (
                "2026-08-11T08:00:00+00:00", "2026-08-11T09:00:00+00:00",
                "2026-08-11T09:00:00+00:00", "2026-08-11T09:00:00+00:00",
            ),
        )

    set_current_dataset_scope(build_dataset_scope(user_id="first", workspace_id="first"))
    materialize_live_finding_cases("live-finding-existing")
    set_current_dataset_scope(build_dataset_scope(user_id="second", workspace_id="second"))
    assert read_finding_case("live-finding-existing")["source"]["kind"] == "live_finding"
    with runtime_db.db_connection() as connection:
        row = connection.execute(
            "SELECT scope_storage_id, dataset_scope_json FROM finding_cases WHERE finding_id = 'live-finding-existing'"
        ).fetchone()
    assert tuple(row) == (None, None)


def test_workflow_tables_enforce_append_only_identity_and_survive_evidence_prune() -> None:
    evidence_store.upsert_evidence_run(_record("retained-run"))
    finding_id = evidence_finding_id("retained-run", "condition-a")
    update_finding_workflow(
        finding_id,
        changes={"status": "monitoring"},
        expected_version=0,
        actor="operator@example.com",
    )
    with runtime_db.db_connection() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="finding_case_source_immutable"):
            connection.execute(
                "UPDATE finding_cases SET source_id = 'changed' WHERE finding_id = ?", (finding_id,)
            )
        with pytest.raises(sqlite3.IntegrityError, match="finding_workflow_events_append_only"):
            connection.execute(
                "UPDATE finding_workflow_events SET actor = 'changed' WHERE finding_id = ?", (finding_id,)
            )
        connection.execute("DELETE FROM evidence_runs WHERE run_id = 'retained-run'")
    assert read_finding_case(finding_id)["evidence"]["source_run_id"] == "retained-run"
