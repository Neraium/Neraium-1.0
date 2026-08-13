import sqlite3

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
import app.services.auth_store as auth_store


def _production_app(monkeypatch, runtime_dir):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_PASSWORD", "password123")
    auth_store._AUTH_BACKEND = None
    auth_store._AUTH_BACKEND_KEY = None
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=runtime_dir,
    )
    return create_app(settings)


def _login(client: TestClient, email: str, password: str = "password123") -> dict:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _create_account(client: TestClient, email: str, *, role: str = "operator") -> None:
    response = client.post(
        "/api/auth/users",
        json={"email": email, "password": "password123", "name": email.split("@", 1)[0], "role": role},
    )
    assert response.status_code == 201, response.text


def _create_workspace(client: TestClient, name: str = "Central Plant") -> dict:
    response = client.post(
        "/api/workspaces",
        json={"display_name": name, "adopt_current_scope": True},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_workspace_schema_migration_is_idempotent_and_does_not_auto_share(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    auth_store._AUTH_BACKEND = None
    auth_store._AUTH_BACKEND_KEY = None

    assert auth_store.initialize_auth_store() == "sqlite"
    assert auth_store.initialize_auth_store() == "sqlite"

    with sqlite3.connect(tmp_path / "auth_store.db") as connection:
        migration_count = connection.execute(
            "SELECT COUNT(*) FROM auth_schema_migrations WHERE migration_id = '003_workspace_membership'"
        ).fetchone()[0]
        workspace_count = connection.execute("SELECT COUNT(*) FROM auth_workspaces").fetchone()[0]
        member_count = connection.execute("SELECT COUNT(*) FROM auth_workspace_members").fetchone()[0]
    assert migration_count == 1
    assert workspace_count == 0
    assert member_count == 0


def test_create_adopts_personal_scope_and_session_lists_workspace(monkeypatch, tmp_path) -> None:
    app = _production_app(monkeypatch, tmp_path)
    with TestClient(app, base_url="https://testserver") as admin:
        login = _login(admin, "admin@example.com")
        assert login["default_workspace_id"] == "default"
        assert login["workspaces"] == [
            {"workspace_id": "default", "display_name": "Personal workspace", "kind": "personal", "is_active": True}
        ]

        workspace = _create_workspace(admin)
        assert workspace["workspace_id"].startswith("ws-")

        me = admin.get("/api/auth/me")
        assert me.status_code == 200
        assert {item["workspace_id"] for item in me.json()["workspaces"]} == {
            "default",
            workspace["workspace_id"],
        }

        stored = auth_store.get_workspace(workspace["workspace_id"])
        assert stored is not None
        assert stored["scope_tenant_id"] == "admin@example.com"
        assert stored["scope_user_id"] == "admin@example.com"
        assert stored["scope_workspace_id"] == "default"

        empty_response = admin.post(
            "/api/workspaces",
            json={"display_name": "New Facility", "adopt_current_scope": False},
        )
        assert empty_response.status_code == 201
        empty = auth_store.get_workspace(empty_response.json()["workspace_id"])
        assert empty is not None
        assert empty["scope_tenant_id"] == f"workspace:{empty['workspace_id']}"
        assert empty["scope_user_id"] == f"workspace:{empty['workspace_id']}"


def test_personal_workspace_directory_contains_only_its_owner(monkeypatch, tmp_path) -> None:
    app = _production_app(monkeypatch, tmp_path)
    with TestClient(app, base_url="https://testserver") as admin:
        _login(admin, "admin@example.com")
        _create_account(admin, "other@example.com", role="viewer")

        members = admin.get("/api/findings/members")
        assert members.status_code == 200
        assert members.json()["members"] == [
            {
                "member_id": "admin@example.com",
                "display_name": "Admin",
                "role": "admin",
                "is_active": True,
            }
        ]


def test_member_add_disable_and_explicit_workspace_access(monkeypatch, tmp_path) -> None:
    app = _production_app(monkeypatch, tmp_path)
    with TestClient(app, base_url="https://testserver") as admin:
        _login(admin, "admin@example.com")
        _create_account(admin, "tech@example.com")
        _create_account(admin, "outside@example.com")
        workspace = _create_workspace(admin)
        headers = {"X-Neraium-Workspace-Id": workspace["workspace_id"]}

        added = admin.post(
            f"/api/workspaces/{workspace['workspace_id']}/members",
            headers=headers,
            json={"email": "tech@example.com"},
        )
        assert added.status_code == 200, added.text
        assert added.json() == {
            "member_id": "tech@example.com",
            "display_name": "tech",
            "role": "operator",
            "is_active": True,
        }

        with TestClient(app, base_url="https://testserver") as technician:
            _login(technician, "tech@example.com")
            visible = technician.get("/api/workspaces/current/members", headers=headers)
            assert visible.status_code == 200
            assert {item["member_id"] for item in visible.json()["members"]} == {
                "admin@example.com",
                "tech@example.com",
            }

        with TestClient(app, base_url="https://testserver") as outsider:
            _login(outsider, "outside@example.com")
            denied = outsider.get("/api/workspaces/current/members", headers=headers)
            assert denied.status_code == 404
            assert denied.json()["detail"] == "Workspace not found."

        disabled = admin.post(
            f"/api/workspaces/{workspace['workspace_id']}/members/tech@example.com/disable",
            headers=headers,
        )
        assert disabled.status_code == 200
        assert disabled.json()["is_active"] is False
        assert auth_store.workspace_assignment_member(
            workspace["workspace_id"], "tech@example.com", include_inactive=True
        )["is_active"] is False

        with TestClient(app, base_url="https://testserver") as technician:
            relogin = _login(technician, "tech@example.com")
            assert relogin["workspaces"] == [
                {"workspace_id": "default", "display_name": "Personal workspace", "kind": "personal", "is_active": True}
            ]
            assert technician.get("/api/workspaces/current/members", headers=headers).status_code == 404


def test_viewer_cannot_manage_workspace_members(monkeypatch, tmp_path) -> None:
    app = _production_app(monkeypatch, tmp_path)
    with TestClient(app, base_url="https://testserver") as admin:
        _login(admin, "admin@example.com")
        _create_account(admin, "viewer@example.com", role="viewer")
        _create_account(admin, "candidate@example.com")
        workspace = _create_workspace(admin)
        headers = {"X-Neraium-Workspace-Id": workspace["workspace_id"]}
        assert admin.post(
            f"/api/workspaces/{workspace['workspace_id']}/members",
            headers=headers,
            json={"email": "viewer@example.com"},
        ).status_code == 200

    with TestClient(app, base_url="https://testserver") as viewer:
        _login(viewer, "viewer@example.com")
        denied = viewer.post(
            f"/api/workspaces/{workspace['workspace_id']}/members",
            headers=headers,
            json={"email": "candidate@example.com"},
        )
        assert denied.status_code == 403


def test_inactive_account_cannot_be_added_and_self_disable_is_rejected(monkeypatch, tmp_path) -> None:
    app = _production_app(monkeypatch, tmp_path)
    with TestClient(app, base_url="https://testserver") as admin:
        _login(admin, "admin@example.com")
        _create_account(admin, "inactive@example.com")
        assert admin.post("/api/auth/users/inactive@example.com/deactivate").status_code == 200
        workspace = _create_workspace(admin)
        headers = {"X-Neraium-Workspace-Id": workspace["workspace_id"]}

        inactive = admin.post(
            f"/api/workspaces/{workspace['workspace_id']}/members",
            headers=headers,
            json={"email": "inactive@example.com"},
        )
        assert inactive.status_code == 409

        self_disable = admin.post(
            f"/api/workspaces/{workspace['workspace_id']}/members/admin@example.com/disable",
            headers=headers,
        )
        assert self_disable.status_code == 409


def test_service_token_explicit_workspace_requires_exact_allowlist(monkeypatch, tmp_path) -> None:
    app = _production_app(monkeypatch, tmp_path)
    with TestClient(app, base_url="https://testserver") as admin:
        _login(admin, "admin@example.com")
        workspace = _create_workspace(admin)

    monkeypatch.setenv("NERAIUM_API_TOKEN", "test-service-token")
    service_headers = {
        "Authorization": "Bearer test-service-token",
        "X-Neraium-Workspace-Id": workspace["workspace_id"],
    }
    with TestClient(app, base_url="https://testserver") as service:
        assert service.get("/api/workspaces/current/members", headers=service_headers).status_code == 404
        monkeypatch.setenv("NERAIUM_API_TOKEN_WORKSPACE_IDS", workspace["workspace_id"])
        allowed = service.get("/api/workspaces/current/members", headers=service_headers)
        assert allowed.status_code == 200
