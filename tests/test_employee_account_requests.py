import sqlite3

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.auth_store import (
    create_user,
    create_workspace,
    deactivate_user,
    list_authorized_workspaces,
    list_users,
)
from app.services.rate_limiter import clear_rate_limits


def _client(monkeypatch, tmp_path) -> TestClient:
    clear_rate_limits()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    return TestClient(create_app(settings), base_url="https://testserver")


def _submit(client: TestClient, email: str = "employee@example.com", password: str = "safe-password-123"):
    return client.post(
        "/api/auth/account-requests",
        json={
            "first_name": "Taylor",
            "last_name": "Employee",
            "email": email,
            "password": password,
            "password_confirmation": password,
        },
    )


def _admin_workspace(client: TestClient):
    create_user("admin@example.com", "admin-password-123", name="Admin", role="admin")
    workspace = create_workspace("Plant A", created_by="admin@example.com")
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-password-123"},
    )
    assert login.status_code == 200
    return workspace


def test_request_is_pending_without_user_membership_session_or_hash(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)

    response = _submit(client, email=" Employee@Example.com ")

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "employee@example.com"
    assert payload["status"] == "pending"
    assert "password" not in response.text
    assert "salt" not in response.text
    assert list_users() == []
    assert list_authorized_workspaces("employee@example.com") == []
    assert "neraium_session" not in response.cookies
    with sqlite3.connect(tmp_path / "auth_store.db") as connection:
        stored = connection.execute(
            "SELECT password_hash, salt, status FROM auth_account_requests WHERE email = ?",
            ("employee@example.com",),
        ).fetchone()
        assert stored is not None
        assert stored[0] != "safe-password-123"
        assert stored[1] != "safe-password-123"
        assert stored[2] == "pending"
        assert connection.execute(
            "SELECT COUNT(*) FROM auth_schema_migrations WHERE migration_id = ?",
            ("004_employee_account_requests",),
        ).fetchone()[0] == 1
    me = client.get("/api/auth/me")
    assert me.json()["authenticated"] is False


def test_duplicate_and_invalid_requests_are_rejected_safely(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    assert _submit(client).status_code == 201
    duplicate = _submit(client)
    assert duplicate.status_code == 409
    assert "pending request" in duplicate.json()["detail"].lower()

    mismatch = client.post(
        "/api/auth/account-requests",
        json={
            "first_name": "Taylor", "last_name": "Employee",
            "email": "other@example.com", "password": "safe-password-123",
            "password_confirmation": "different-password",
        },
    )
    assert mismatch.status_code == 422

    invalid = client.post(
        "/api/auth/account-requests",
        json={
            "first_name": "", "last_name": "Employee", "email": "not-an-email",
            "password": "short", "password_confirmation": "short",
        },
    )
    assert invalid.status_code == 422


def test_active_account_email_request_is_rejected(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    create_user("employee@example.com", "safe-password-123")
    response = _submit(client)
    assert response.status_code == 409
    assert response.json()["detail"] == "An account or pending request already exists for this email."


def test_pending_login_requires_matching_password_and_never_authenticates(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    assert _submit(client).status_code == 201

    pending = client.post(
        "/api/auth/login",
        json={"email": "employee@example.com", "password": "safe-password-123"},
    )
    assert pending.status_code == 403
    assert pending.json()["detail"] == "Your account is awaiting administrator approval."
    assert "neraium_session" not in pending.cookies

    wrong = client.post(
        "/api/auth/login",
        json={"email": "employee@example.com", "password": "wrong-password"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "Invalid email or password."


def test_only_admin_can_list_and_approve_requests(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    request_id = _submit(client).json()["request_id"]
    create_user("operator@example.com", "operator-password", role="operator")
    client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "operator-password"},
    )

    assert client.get("/api/auth/account-requests").status_code == 403
    assert client.post(
        f"/api/auth/account-requests/{request_id}/approve",
        json={"role": "viewer", "workspace_id": "ws-00000000-0000-0000-0000-000000000000"},
    ).status_code == 403


def test_admin_approval_assigns_explicit_role_and_workspace_then_login_works(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    request_id = _submit(client).json()["request_id"]
    workspace = _admin_workspace(client)
    headers = {"X-Neraium-Workspace-Id": workspace["workspace_id"]}

    pending = client.get("/api/auth/account-requests", headers=headers)
    assert pending.status_code == 200
    assert [item["request_id"] for item in pending.json()["requests"]] == [request_id]
    assert "password" not in pending.text
    assert "salt" not in pending.text

    approval = client.post(
        f"/api/auth/account-requests/{request_id}/approve",
        json={"role": "viewer", "workspace_id": workspace["workspace_id"]},
        headers=headers,
    )
    assert approval.status_code == 200
    assert approval.json()["approved_role"] == "viewer"
    assert approval.json()["approved_workspace_id"] == workspace["workspace_id"]
    account = next(user for user in list_users() if user["email"] == "employee@example.com")
    assert account["name"] == "Taylor Employee"
    assert account["role"] == "viewer"
    assert [item["workspace_id"] for item in list_authorized_workspaces(account["email"])] == [workspace["workspace_id"]]

    client.post("/api/auth/logout")
    login = client.post(
        "/api/auth/login",
        json={"email": "employee@example.com", "password": "safe-password-123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "viewer"
    assert "password" not in login.text


def test_rejected_request_never_creates_an_account(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    request_id = _submit(client).json()["request_id"]
    workspace = _admin_workspace(client)
    headers = {"X-Neraium-Workspace-Id": workspace["workspace_id"]}

    rejection = client.post(f"/api/auth/account-requests/{request_id}/reject", headers=headers)
    assert rejection.status_code == 200
    assert rejection.json()["status"] == "rejected"
    assert all(user["email"] != "employee@example.com" for user in list_users())

    client.post("/api/auth/logout")
    login = client.post(
        "/api/auth/login",
        json={"email": "employee@example.com", "password": "safe-password-123"},
    )
    assert login.status_code == 401


def test_approval_reactivates_an_inactive_account_with_requested_credentials(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    create_user("returning@example.com", "old-password", role="operator")
    deactivate_user("returning@example.com")
    request_id = _submit(
        client, email="returning@example.com", password="new-safe-password"
    ).json()["request_id"]
    workspace = _admin_workspace(client)
    headers = {"X-Neraium-Workspace-Id": workspace["workspace_id"]}

    approval = client.post(
        f"/api/auth/account-requests/{request_id}/approve",
        json={"role": "viewer", "workspace_id": workspace["workspace_id"]},
        headers=headers,
    )
    assert approval.status_code == 200
    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"email": "returning@example.com", "password": "old-password"},
    ).status_code == 401
    assert client.post(
        "/api/auth/login",
        json={"email": "returning@example.com", "password": "new-safe-password"},
    ).status_code == 200
