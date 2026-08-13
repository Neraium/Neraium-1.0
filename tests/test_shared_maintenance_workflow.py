from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services import evidence_store
from app.services.auth_store import (
    add_workspace_member,
    create_user,
    create_workspace,
    deactivate_user,
)
from app.services.dataset_scope import build_dataset_scope, dataset_scope_context
from app.services.finding_workflow import evidence_finding_id


def _record(run_id: str, *, system_id: str = "ahu-1") -> dict:
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
        "finding_identity_snapshot": [{
            "source_finding_id": "condition-a",
            "finding": {
                "condition_id": "condition-a",
                "headline": "Supply temperature changed persistently",
                "priority": "high",
                "system_id": system_id,
            },
        }],
    }


def _materialize(run_id: str, *, system_id: str = "ahu-1") -> str:
    evidence_store.upsert_evidence_run(_record(run_id, system_id=system_id))
    return evidence_finding_id(run_id, "condition-a")


def test_active_member_directory_assignment_reassignment_and_legacy_reference(client) -> None:
    create_user("tech@example.com", "password123", name="Taylor Tech", role="viewer")
    create_user("lead@example.com", "password123", name="Morgan Lead", role="operator")
    create_user("inactive@example.com", "password123", name="Inactive Tech", role="viewer")
    workspace = create_workspace(
        "Central Plant",
        created_by="lead@example.com",
        scope_tenant_id="lead@example.com",
        scope_user_id="lead@example.com",
        scope_workspace_id="default",
    )
    add_workspace_member(workspace["workspace_id"], "tech@example.com", added_by="lead@example.com")
    add_workspace_member(workspace["workspace_id"], "inactive@example.com", added_by="lead@example.com")
    deactivate_user("inactive@example.com")
    headers = {
        "X-Neraium-User": "lead@example.com",
        "X-Neraium-Workspace-Id": workspace["workspace_id"],
    }

    members = client.get("/api/findings/members", headers=headers)
    assert members.status_code == 200
    assert sorted(members.json()["members"], key=lambda item: item["member_id"]) == [
        {"member_id": "lead@example.com", "display_name": "Morgan Lead", "role": "operator", "is_active": True},
        {"member_id": "tech@example.com", "display_name": "Taylor Tech", "role": "viewer", "is_active": True},
    ]

    with dataset_scope_context(build_dataset_scope(user_id="lead@example.com")):
        finding_id = _materialize("member-assignment")
    assigned = client.patch(
        f"/api/findings/{finding_id}/workflow",
        headers=headers,
        json={
            "expected_version": 0,
            "assignment": {"target_type": "person", "label": "stale label", "external_ref": "TECH@example.com"},
            "user_priority": "critical",
            "due_at": "2026-08-13T08:00:00Z",
        },
    )
    assert assigned.status_code == 200
    workflow = assigned.json()["workflow"]
    assert workflow["assignment"] == {
        "target_type": "person", "label": "Taylor Tech", "external_ref": "tech@example.com",
    }
    assert workflow["assigned_by"] == "lead@example.com"
    assert workflow["effective_priority"] == "critical"
    assert workflow["due_at"] == "2026-08-13T08:00:00+00:00"

    reassigned = client.patch(
        f"/api/findings/{finding_id}/workflow",
        headers=headers,
        json={
            "expected_version": 1,
            "assignment": {"target_type": "person", "label": "Morgan", "external_ref": "lead@example.com"},
        },
    )
    assert reassigned.status_code == 200
    history = reassigned.json()["workflow"]["assignment_history"]
    assert [item["action"] for item in history] == ["assigned", "reassigned"]

    with dataset_scope_context(build_dataset_scope(user_id="lead@example.com")):
        legacy_id = _materialize("legacy-label-assignment")
    legacy = client.patch(
        f"/api/findings/{legacy_id}/workflow",
        headers=headers,
        json={
            "expected_version": 0,
            "assignment": {"target_type": "person", "label": "Historical technician"},
        },
    )
    assert legacy.status_code == 422
    assert legacy.json()["detail"] == "assignment_member_required"

    for member_id, expected_detail in (
        ("missing@example.com", "unknown_assignment_member"),
        ("inactive@example.com", "inactive_assignment_member"),
    ):
        with dataset_scope_context(build_dataset_scope(user_id="lead@example.com")):
            invalid_id = _materialize(f"invalid-{member_id.split('@')[0]}")
        invalid = client.patch(
            f"/api/findings/{invalid_id}/workflow",
            headers=headers,
            json={
                "expected_version": 0,
                "assignment": {"target_type": "person", "label": "Invalid", "external_ref": member_id},
            },
        )
        assert invalid.status_code == 422
        assert invalid.json()["detail"] == expected_detail


def test_field_reports_escalation_review_resolution_and_human_activity(client) -> None:
    finding_id = _materialize("field-report")
    started = client.patch(
        f"/api/findings/{finding_id}/workflow",
        json={"expected_version": 0, "status": "investigating"},
    )
    assert started.status_code == 200

    report = client.post(
        f"/api/findings/{finding_id}/field-reports",
        json={
            "expected_version": 1,
            "problem_found": "yes",
            "inspected": "Supply fan belt and bearings",
            "found": "Belt was visibly loose",
            "action_taken": "Adjusted belt tension",
            "note": "Fan vibration reduced after adjustment.",
            "investigation_complete": True,
        },
    )
    assert report.status_code == 200
    workflow = report.json()["workflow"]
    assert workflow["status"] == "awaiting_review"
    assert workflow["latest_field_report"]["problem_found"] == "yes"
    assert len(workflow["field_reports"]) == 1

    resolved = client.post(
        f"/api/findings/{finding_id}/resolution",
        json={
            "expected_version": 2,
            "outcome": "maintenance_performed",
            "note": "Lead reviewed the belt adjustment.",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["workflow"]["status"] == "resolved"

    terminal_report = client.post(
        f"/api/findings/{finding_id}/field-reports",
        json={
            "expected_version": 3,
            "problem_found": "uncertain",
            "found": "Late report must not reopen the finding",
            "needs_escalation": True,
        },
    )
    assert terminal_report.status_code == 422
    assert terminal_report.json()["detail"] == "field_report_not_allowed_for_terminal_finding"
    assert client.get(f"/api/findings/{finding_id}").json()["workflow"]["status"] == "resolved"

    activity = client.get(f"/api/findings/{finding_id}/activity").json()
    assert [item["label"] for item in activity["activity"]] == [
        "Finding resolved", "Investigation completed", "Investigation started", "Finding detected",
    ]
    assert [event["event_type"] for event in activity["events"]] == [
        "resolution_recorded", "field_report_recorded", "workflow_updated",
    ]

    escalation_id = _materialize("field-escalation")
    escalation = client.post(
        f"/api/findings/{escalation_id}/field-reports",
        json={
            "expected_version": 0,
            "problem_found": "uncertain",
            "found": "Intermittent noise could not be isolated",
            "needs_escalation": True,
        },
    )
    assert escalation.status_code == 200
    assert escalation.json()["workflow"]["status"] == "escalated"


def test_human_activity_expands_bundled_assignment_priority_due_and_guidance(client) -> None:
    create_user("lead@example.com", "password123", name="Lead", role="operator")
    create_user("first@example.com", "password123", name="First Tech", role="viewer")
    create_user("second@example.com", "password123", name="Second Tech", role="viewer")
    workspace = create_workspace(
        "Activity Plant",
        created_by="lead@example.com",
        scope_tenant_id="lead@example.com",
        scope_user_id="lead@example.com",
        scope_workspace_id="default",
    )
    for email in ("first@example.com", "second@example.com"):
        add_workspace_member(workspace["workspace_id"], email, added_by="lead@example.com")
    headers = {
        "X-Neraium-User": "lead@example.com",
        "X-Neraium-Workspace-Id": workspace["workspace_id"],
    }
    with dataset_scope_context(build_dataset_scope(user_id="lead@example.com")):
        finding_id = _materialize("activity-bundled-changes")
    first = client.patch(
        f"/api/findings/{finding_id}/workflow",
        headers=headers,
        json={
            "expected_version": 0,
            "assignment": {"target_type": "person", "label": "First", "external_ref": "first@example.com"},
            "user_priority": "critical",
            "due_at": "2026-08-14T23:59:59Z",
            "manager_note": "Inspect the drive first.",
        },
    )
    assert first.status_code == 200
    second = client.patch(
        f"/api/findings/{finding_id}/workflow",
        headers=headers,
        json={
            "expected_version": 1,
            "assignment": {"target_type": "person", "label": "Second", "external_ref": "second@example.com"},
        },
    )
    assert second.status_code == 200

    labels = [
        item["label"]
        for item in client.get(f"/api/findings/{finding_id}/activity", headers=headers).json()["activity"]
    ]
    assert labels == [
        "Finding reassigned", "Finding assigned", "Priority changed",
        "Due date changed", "Guidance updated", "Finding detected",
    ]


def test_work_queue_filters_are_applied_before_pagination(client) -> None:
    create_user("tech@example.com", "password123", name="Taylor Tech", role="viewer")
    headers = {"X-Neraium-User": "tech@example.com"}
    with dataset_scope_context(build_dataset_scope(user_id="tech@example.com")):
        my_id = _materialize("queue-my-work", system_id="ahu-1")
        unassigned_id = _materialize("queue-unassigned", system_id="boiler-1")
        review_id = _materialize("queue-review", system_id="ahu-2")
        resolved_id = _materialize("queue-resolved", system_id="pump-1")

    client.patch(
        f"/api/findings/{my_id}/workflow",
        headers=headers,
        json={
            "expected_version": 0,
            "status": "investigating",
            "assignment": {"target_type": "person", "label": "Taylor", "external_ref": "tech@example.com"},
            "due_at": "2020-01-01T00:00:00Z",
        },
    )
    client.patch(
        f"/api/findings/{review_id}/workflow",
        headers=headers,
        json={"expected_version": 0, "status": "awaiting_review"},
    )
    client.post(
        f"/api/findings/{resolved_id}/resolution",
        headers=headers,
        json={"expected_version": 0, "outcome": "no_issue_found"},
    )

    my_work = client.get(
        "/api/findings?assigned_to_me=true&limit=1",
        headers=headers,
    ).json()
    assert [item["finding_id"] for item in my_work["findings"]] == [my_id]
    assert my_work["has_more"] is False
    assert {item["finding_id"] for item in client.get("/api/findings?unassigned=true", headers=headers).json()["findings"]} == {
        unassigned_id, review_id, resolved_id,
    }
    assert [item["finding_id"] for item in client.get("/api/findings?overdue=true", headers=headers).json()["findings"]] == [my_id]
    assert [item["finding_id"] for item in client.get("/api/findings?awaiting_review=true", headers=headers).json()["findings"]] == [review_id]
    assert [item["finding_id"] for item in client.get("/api/findings?recently_resolved=true", headers=headers).json()["findings"]] == [resolved_id]
    assert [item["finding_id"] for item in client.get("/api/findings?system=boiler-1", headers=headers).json()["findings"]] == [unassigned_id]


def test_production_viewer_can_only_mutate_exact_own_validated_assignment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path / "runtime"))
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path / "runtime",
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        create_user("lead@example.com", "password123", name="Morgan Lead", role="operator")
        create_user("tech@example.com", "password123", name="Taylor Tech", role="viewer")
        create_user("other@example.com", "password123", name="Other Tech", role="viewer")
        workspace = create_workspace(
            "Production Plant",
            created_by="lead@example.com",
            scope_tenant_id="lead@example.com",
            scope_user_id="lead@example.com",
            scope_workspace_id="default",
        )
        for member in ("tech@example.com", "other@example.com"):
            add_workspace_member(workspace["workspace_id"], member, added_by="lead@example.com")
        workspace_headers = {"X-Neraium-Workspace-Id": workspace["workspace_id"]}
        with dataset_scope_context(build_dataset_scope(user_id="lead@example.com")):
            finding_id = _materialize("production-policy")

        assert client.post(
            "/api/auth/login", json={"email": "lead@example.com", "password": "password123"},
        ).status_code == 200
        assigned = client.patch(
            f"/api/findings/{finding_id}/workflow",
            headers=workspace_headers,
            json={
                "expected_version": 0,
                "assignment": {"target_type": "person", "label": "Taylor", "external_ref": "tech@example.com"},
            },
        )
        assert assigned.status_code == 200
        client.post("/api/auth/logout")

        assert client.post(
            "/api/auth/login", json={"email": "tech@example.com", "password": "password123"},
        ).status_code == 200
        accepted = client.patch(
            f"/api/findings/{finding_id}/workflow",
            headers=workspace_headers,
            json={"expected_version": 1, "status": "acknowledged"},
        )
        assert accepted.status_code == 200
        forbidden_priority = client.patch(
            f"/api/findings/{finding_id}/workflow",
            headers=workspace_headers,
            json={"expected_version": 2, "user_priority": "critical"},
        )
        assert forbidden_priority.status_code == 403
        assert client.post(
            f"/api/findings/{finding_id}/resolution",
            headers=workspace_headers,
            json={"expected_version": 2, "outcome": "issue_found"},
        ).status_code == 403
        client.post("/api/auth/logout")

        assert client.post(
            "/api/auth/login", json={"email": "other@example.com", "password": "password123"},
        ).status_code == 200
        not_mine = client.patch(
            f"/api/findings/{finding_id}/workflow",
            headers=workspace_headers,
            json={"expected_version": 2, "status": "investigating"},
        )
        assert not_mine.status_code == 403
