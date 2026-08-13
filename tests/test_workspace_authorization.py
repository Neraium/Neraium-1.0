from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services import auth_store, evidence_store
from app.services.dataset_scope import build_dataset_scope, dataset_scope_context
from app.services.finding_workflow import evidence_finding_id


def _production_app(monkeypatch, runtime_dir):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_EMAIL", "lead@example.com")
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_PASSWORD", "password123")
    auth_store._AUTH_BACKEND = None
    auth_store._AUTH_BACKEND_KEY = None
    return create_app(
        Settings(
            app_env="production",
            backend_host="127.0.0.1",
            backend_port=8010,
            cors_origins=["https://app.neraium.com"],
            runtime_dir=runtime_dir,
        )
    )


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/login", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 200, response.text


def _record(run_id: str, scope) -> dict:
    return {
        "run_id": run_id,
        "source_type": "csv_upload",
        "source_name": "facility.csv",
        "status": "completed",
        "created_at": "2026-08-13T08:00:00+00:00",
        "completed_at": "2026-08-13T08:01:00+00:00",
        "dataset_scope": scope.as_dict(),
        "finding_identity_snapshot": [
            {
                "source_finding_id": "condition-a",
                "finding": {
                    "condition_id": "condition-a",
                    "headline": "Supply temperature changed persistently",
                    "priority": "high",
                    "system_id": "ahu-1",
                },
            }
        ],
    }


def test_workspace_members_share_findings_evidence_and_outsiders_get_opaque_404(
    monkeypatch, tmp_path
) -> None:
    app = _production_app(monkeypatch, tmp_path)
    lead_scope = build_dataset_scope(user_id="lead@example.com")
    run_id = "shared-run"
    finding_id = evidence_finding_id(run_id, "condition-a")

    with TestClient(app, base_url="https://testserver") as lead:
        _login(lead, "lead@example.com")
        for email, role in (
            ("tech@example.com", "viewer"),
            ("engineer@example.com", "viewer"),
            ("outside@example.com", "viewer"),
        ):
            created = lead.post(
                "/api/auth/users",
                json={
                    "email": email,
                    "password": "password123",
                    "name": email.split("@", 1)[0],
                    "role": role,
                },
            )
            assert created.status_code == 201, created.text
        with dataset_scope_context(lead_scope):
            evidence_store.upsert_evidence_run(_record(run_id, lead_scope))
        created_workspace = lead.post(
            "/api/workspaces",
            json={"display_name": "Central Plant", "adopt_current_scope": True},
        )
        assert created_workspace.status_code == 201, created_workspace.text
        workspace_id = created_workspace.json()["workspace_id"]
        headers = {"X-Neraium-Workspace-Id": workspace_id}
        for email in ("tech@example.com", "engineer@example.com"):
            added = lead.post(
                f"/api/workspaces/{workspace_id}/members",
                headers=headers,
                json={"email": email},
            )
            assert added.status_code == 200, added.text

        members = lead.get("/api/findings/members", headers=headers)
        assert {item["member_id"] for item in members.json()["members"]} == {
            "lead@example.com",
            "tech@example.com",
            "engineer@example.com",
        }
        assigned = lead.patch(
            f"/api/findings/{finding_id}/workflow",
            headers=headers,
            json={
                "expected_version": 0,
                "assignment": {
                    "target_type": "person",
                    "label": "ignored",
                    "external_ref": "tech@example.com",
                },
            },
        )
        assert assigned.status_code == 200, assigned.text

        nonmember = lead.patch(
            f"/api/findings/{finding_id}/workflow",
            headers=headers,
            json={
                "expected_version": 1,
                "assignment": {
                    "target_type": "person",
                    "label": "outside",
                    "external_ref": "outside@example.com",
                },
            },
        )
        assert nonmember.status_code == 422
        assert nonmember.json()["detail"] == "unknown_assignment_member"

        with TestClient(app, base_url="https://testserver") as technician:
            _login(technician, "tech@example.com")
            assert technician.get(f"/api/findings/{finding_id}", headers=headers).status_code == 200
            assert technician.get(f"/api/findings/{finding_id}/activity", headers=headers).status_code == 200
            assert technician.get(f"/api/evidence/runs/{run_id}", headers=headers).status_code == 200
            my_work = technician.get("/api/findings?assigned_to_me=true", headers=headers)
            assert [item["finding_id"] for item in my_work.json()["findings"]] == [finding_id]

        with TestClient(app, base_url="https://testserver") as outsider:
            _login(outsider, "outside@example.com")
            for path in (
                f"/api/findings/{finding_id}",
                f"/api/findings/{finding_id}/activity",
                f"/api/evidence/runs/{run_id}",
                f"/api/evidence/runs/{run_id}/integrity",
            ):
                denied = outsider.get(path, headers=headers)
                assert denied.status_code == 404
                assert "scope" not in denied.text.lower()

        disabled = lead.post(
            f"/api/workspaces/{workspace_id}/members/tech@example.com/disable",
            headers=headers,
        )
        assert disabled.status_code == 200
        historical = lead.get(f"/api/findings/{finding_id}", headers=headers)
        assert historical.status_code == 200
        assert historical.json()["workflow"]["assignment"]["external_ref"] == "tech@example.com"
        cannot_reassign = lead.patch(
            f"/api/findings/{finding_id}/workflow",
            headers=headers,
            json={
                "expected_version": 1,
                "assignment": {
                    "target_type": "person",
                    "label": "tech",
                    "external_ref": "tech@example.com",
                },
            },
        )
        assert cannot_reassign.status_code == 422
        assert cannot_reassign.json()["detail"] == "inactive_assignment_member"
        with TestClient(app, base_url="https://testserver") as removed_member:
            _login(removed_member, "tech@example.com")
            assert removed_member.get(
                f"/api/findings/{finding_id}", headers=headers
            ).status_code == 404


def test_scoping_precedes_evidence_pagination_and_null_rows_are_invisible(tmp_path) -> None:
    from app.services import runtime_db

    runtime_db.configure_runtime_dir(tmp_path)
    scope_a = build_dataset_scope(user_id="a@example.com")
    scope_b = build_dataset_scope(user_id="b@example.com")
    with dataset_scope_context(scope_a):
        evidence_store.upsert_evidence_run(_record("a-new", scope_a))
        evidence_store.upsert_evidence_run(_record("a-old", scope_a))
    with dataset_scope_context(scope_b):
        evidence_store.upsert_evidence_run(_record("b-new", scope_b))
    with runtime_db.db_connection() as connection:
        connection.execute(
            """
            INSERT INTO evidence_runs (
                run_id, created_at, completed_at, status, source_name,
                scope_storage_id, payload_json
            ) VALUES ('unscoped', '2099-01-01T00:00:00+00:00', NULL,
                      'completed', NULL, NULL, '{}')
            """
        )

    with dataset_scope_context(scope_a):
        page = evidence_store.list_evidence_runs_page(limit=1, offset=0)
        assert page["runs"][0]["run_id"] in {"a-new", "a-old"}
        assert page["has_more"] is True
        assert evidence_store.read_evidence_run("b-new") is None
        assert evidence_store.read_evidence_run("unscoped") is None
