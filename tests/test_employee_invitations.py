import hashlib
import sqlite3

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.auth_store import create_user, create_workspace, list_authorized_workspaces, list_users
from app.services.rate_limiter import clear_rate_limits


def _client(monkeypatch, tmp_path) -> TestClient:
    clear_rate_limits()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    return TestClient(create_app(Settings(
        app_env="production", backend_host="127.0.0.1", backend_port=8010,
        cors_origins=["https://app.neraium.com"], runtime_dir=tmp_path,
    )), base_url="https://testserver")


def _company_invite(client: TestClient):
    create_user("admin@example.com", "admin-password-123", name="Admin", role="admin")
    assert client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-password-123"}).status_code == 200
    invitation = client.post("/api/auth/invitations")
    assert invitation.status_code == 201
    client.post("/api/auth/logout")
    return invitation.json()


def _payload(token: str, **overrides):
    payload = {
        "first_name": "Taylor", "last_name": "Employee",
        "email": "taylor.personal@example.net", "password": "safe-password-123",
        "password_confirmation": "safe-password-123", "invite_token": token,
    }
    payload.update(overrides)
    return payload


def test_company_link_registers_multiple_cpos_with_personal_workspaces_and_sessions(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    invitation = _company_invite(client)
    token = invitation["invite_token"]

    response = client.post("/api/auth/register", json=_payload(token, email=" Personal.User@Example.net "))

    assert response.status_code == 201
    assert response.json()["authenticated"] is True
    assert response.json()["user"]["role"] == "operator"
    assert response.json()["user"]["email"] == "personal.user@example.net"
    assert [row["workspace_id"] for row in response.json()["workspaces"]] == ["default"]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "secure" in response.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json()["authenticated"] is True
    client.post("/api/auth/logout")
    second = client.post("/api/auth/register", json=_payload(token, email="second@example.net"))
    assert second.status_code == 201
    assert [row["workspace_id"] for row in second.json()["workspaces"]] == ["default"]
    with sqlite3.connect(tmp_path / "auth_store.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM auth_workspace_members WHERE email IN (?, ?)",
                                  ("personal.user@example.net", "second@example.net")).fetchone()[0] == 0


def test_invite_token_is_returned_once_but_only_hash_is_stored(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    invitation = _company_invite(client)
    token = invitation["invite_token"]
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-password-123"})
    listed = client.get("/api/auth/invitations")
    assert listed.status_code == 200
    assert listed.json()["invitations"][0]["invite_token"] is None
    assert token not in listed.text
    with sqlite3.connect(tmp_path / "auth_store.db") as connection:
        stored_hash = connection.execute("SELECT token_hash FROM auth_company_signup_links").fetchone()[0]
        assert stored_hash == hashlib.sha256(token.encode()).hexdigest()
        assert stored_hash != token


def test_creating_replacement_link_revokes_previous_company_link(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    first = _company_invite(client)
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-password-123"})
    second = client.post("/api/auth/invitations")
    assert second.status_code == 201
    client.post("/api/auth/logout")

    replaced = client.post("/api/auth/register", json=_payload(first["invite_token"]))
    current = client.post("/api/auth/register", json=_payload(second.json()["invite_token"]))
    assert replaced.status_code == 403
    assert current.status_code == 201


def test_invalid_missing_and_revoked_links_never_create_session(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    invitation = _company_invite(client)
    invalid = client.post("/api/auth/register", json=_payload("x" * 43))
    missing = client.post("/api/auth/register", json={key: value for key, value in _payload(invitation["invite_token"]).items() if key != "invite_token"})
    assert invalid.status_code == 403 and "neraium_session" not in invalid.cookies
    assert missing.status_code == 422

    assert client.post("/api/auth/register", json=_payload(invitation["invite_token"])).status_code == 201
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-password-123"})
    assert client.post(f"/api/auth/invitations/{invitation['invite_id']}/revoke").status_code == 200
    client.post("/api/auth/logout")
    revoked = client.post("/api/auth/register", json=_payload(invitation["invite_token"], email="revoked@example.net"))
    assert revoked.status_code == 403
    assert [user["email"] for user in list_users()].count("revoked@example.net") == 0


def test_expired_invite_cannot_create_an_account(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    invitation = _company_invite(client)
    with sqlite3.connect(tmp_path / "auth_store.db") as connection:
        connection.execute(
            "UPDATE auth_company_signup_links SET expires_at = ? WHERE invite_id = ?",
            ("2020-01-01T00:00:00+00:00", invitation["invite_id"]),
        )

    response = client.post("/api/auth/register", json=_payload(invitation["invite_token"]))
    assert response.status_code == 403
    assert "neraium_session" not in response.cookies
    assert all(user["email"] != "taylor.personal@example.net" for user in list_users())


def test_non_admin_cannot_create_or_list_invitations(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    create_user("cpo@example.net", "cpo-password", role="operator")
    client.post("/api/auth/login", json={"email": "cpo@example.net", "password": "cpo-password"})
    assert client.get("/api/auth/invitations").status_code == 403
    assert client.post("/api/auth/invitations").status_code == 403


def test_registration_rejects_duplicate_malformed_and_authority_fields(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    first = _company_invite(client)
    assert client.post("/api/auth/register", json=_payload(first["invite_token"])).status_code == 201
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-password-123"})
    second = client.post("/api/auth/invitations").json()
    client.post("/api/auth/logout")
    assert client.post("/api/auth/register", json=_payload(second["invite_token"])).status_code == 409
    assert client.post("/api/auth/register", json=_payload(second["invite_token"], email="bad-email")).status_code == 422
    assert client.post("/api/auth/register", json=_payload(second["invite_token"], email="other@example.net", password_confirmation="different")).status_code == 422
    for field, value in (("role", "admin"), ("workspace_id", "ws-00000000-0000-0000-0000-000000000000")):
        assert client.post("/api/auth/register", json=_payload(second["invite_token"], email=f"{field}@example.net", **{field: value})).status_code == 422


def test_existing_login_logout_and_admin_user_management_remain_available(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    invitation = _company_invite(client)
    assert client.post("/api/auth/register", json=_payload(invitation["invite_token"])).status_code == 201
    assert client.post("/api/auth/logout").json()["authenticated"] is False
    assert client.post("/api/auth/login", json={"email": "taylor.personal@example.net", "password": "safe-password-123"}).status_code == 200
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin-password-123"})
    workspace = create_workspace("PPC Facility", created_by="admin@example.com")
    created = client.post("/api/auth/users", json={"email": "managed@example.net", "password": "managed-password", "role": "operator"})
    assert created.status_code == 201
    assert workspace["workspace_id"] in [row["workspace_id"] for row in list_authorized_workspaces("admin@example.com")]
