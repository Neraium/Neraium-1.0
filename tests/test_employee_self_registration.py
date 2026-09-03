import sqlite3

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.auth_store import create_user, create_workspace, list_authorized_workspaces, list_users
from app.services.rate_limiter import clear_rate_limits

ACCESS_CODE = "employer-issued-secret"


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


def _configure_workspace(monkeypatch) -> dict:
    create_user("admin@example.com", "admin-password-123", name="Admin", role="admin")
    workspace = create_workspace("PPC Facility", created_by="admin@example.com")
    monkeypatch.setenv("NERAIUM_EMPLOYEE_ONBOARDING_CODE", ACCESS_CODE)
    monkeypatch.setenv("NERAIUM_EMPLOYEE_ONBOARDING_WORKSPACE_ID", workspace["workspace_id"])
    return workspace


def _payload(**overrides) -> dict:
    payload = {
        "first_name": "Taylor",
        "last_name": "Employee",
        "email": "taylor.personal@example.net",
        "password": "safe-password-123",
        "password_confirmation": "safe-password-123",
        "employee_access_code": ACCESS_CODE,
    }
    payload.update(overrides)
    return payload


def test_valid_code_registers_personal_email_as_viewer_in_only_configured_workspace(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    workspace = _configure_workspace(monkeypatch)

    response = client.post("/api/auth/register", json=_payload(email=" Personal.User@Example.net "))

    assert response.status_code == 201
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["user"] == {
        "email": "personal.user@example.net",
        "name": "Taylor Employee",
        "role": "viewer",
        "created_at": payload["user"]["created_at"],
        "last_login_at": None,
        "is_active": True,
        "deactivated_at": None,
        "bootstrap_managed": False,
    }
    assert [item["workspace_id"] for item in list_authorized_workspaces("personal.user@example.net")] == [workspace["workspace_id"]]
    assert {item["workspace_id"] for item in payload["workspaces"]} == {"default", workspace["workspace_id"]}
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert client.get("/api/auth/me").json()["authenticated"] is True


def test_wrong_or_missing_code_creates_nothing_and_issues_no_session(monkeypatch, tmp_path, caplog) -> None:
    client = _client(monkeypatch, tmp_path)
    _configure_workspace(monkeypatch)

    wrong = client.post(
        "/api/auth/register",
        json=_payload(employee_access_code="wrong-secret-value"),
    )
    missing = client.post(
        "/api/auth/register",
        json={key: value for key, value in _payload(email="second@example.net").items() if key != "employee_access_code"},
    )

    assert wrong.status_code == 403
    assert wrong.json()["detail"] == "Invalid employee access code."
    assert "neraium_session" not in wrong.cookies
    assert missing.status_code == 422
    assert all(user["role"] == "admin" for user in list_users())
    assert ACCESS_CODE not in wrong.text
    assert ACCESS_CODE not in caplog.text


def test_missing_code_configuration_fails_closed(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    workspace = _configure_workspace(monkeypatch)
    monkeypatch.delenv("NERAIUM_EMPLOYEE_ONBOARDING_CODE")
    monkeypatch.setenv("NERAIUM_EMPLOYEE_ONBOARDING_WORKSPACE_ID", workspace["workspace_id"])

    response = client.post("/api/auth/register", json=_payload())

    assert response.status_code == 503
    assert response.json()["detail"] == "Employee registration is unavailable."
    assert "neraium_session" not in response.cookies


def test_missing_or_invalid_workspace_configuration_fails_closed(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setenv("NERAIUM_EMPLOYEE_ONBOARDING_CODE", ACCESS_CODE)
    monkeypatch.delenv("NERAIUM_EMPLOYEE_ONBOARDING_WORKSPACE_ID", raising=False)
    missing = client.post("/api/auth/register", json=_payload())
    assert missing.status_code == 503

    monkeypatch.setenv(
        "NERAIUM_EMPLOYEE_ONBOARDING_WORKSPACE_ID",
        "ws-00000000-0000-0000-0000-000000000000",
    )
    invalid = client.post("/api/auth/register", json=_payload(email="other@example.net"))
    assert invalid.status_code == 503
    assert "neraium_session" not in invalid.cookies
    assert list_users() == []


def test_duplicate_email_and_malformed_input_fail_safely(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    _configure_workspace(monkeypatch)
    assert client.post("/api/auth/register", json=_payload()).status_code == 201
    client.post("/api/auth/logout")

    duplicate = client.post("/api/auth/register", json=_payload())
    mismatch = client.post(
        "/api/auth/register",
        json=_payload(email="other@example.net", password_confirmation="different-password"),
    )
    malformed = client.post("/api/auth/register", json=_payload(email="not-an-email"))

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "An account with this email already exists."
    assert mismatch.status_code == 422
    assert malformed.status_code == 422
    assert "neraium_session" not in duplicate.cookies


def test_password_is_hashed_and_access_code_is_not_stored_or_returned(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    _configure_workspace(monkeypatch)

    response = client.post("/api/auth/register", json=_payload())

    assert response.status_code == 201
    assert ACCESS_CODE not in response.text
    assert "password" not in response.text
    assert "salt" not in response.text
    with sqlite3.connect(tmp_path / "auth_store.db") as connection:
        user = connection.execute(
            "SELECT password_hash, salt, role FROM auth_users WHERE email = ?",
            ("taylor.personal@example.net",),
        ).fetchone()
        assert user is not None
        assert user[0] != _payload()["password"]
        assert user[1] != _payload()["password"]
        assert user[2] == "viewer"
        schema = " ".join(
            row[0] or "" for row in connection.execute("SELECT sql FROM sqlite_master")
        )
        assert "onboarding_code" not in schema.lower()


def test_role_and_workspace_injection_are_rejected(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    _configure_workspace(monkeypatch)

    for field, value in (
        ("role", "admin"),
        ("workspace_id", "ws-00000000-0000-0000-0000-000000000000"),
    ):
        response = client.post("/api/auth/register", json=_payload(**{field: value}))
        assert response.status_code == 422
        assert "neraium_session" not in response.cookies
    assert all(user["role"] == "admin" for user in list_users())


def test_registration_preserves_login_logout_and_admin_user_management(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    workspace = _configure_workspace(monkeypatch)
    registration = client.post("/api/auth/register", json=_payload())
    assert registration.status_code == 201
    assert client.post("/api/auth/logout").json()["authenticated"] is False
    assert client.get("/api/auth/me").json()["authenticated"] is False
    login = client.post(
        "/api/auth/login",
        json={"email": "taylor.personal@example.net", "password": "safe-password-123"},
    )
    assert login.status_code == 200
    assert client.get("/api/auth/me").json()["authenticated"] is True

    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-password-123"},
    )
    created = client.post(
        "/api/auth/users",
        json={"email": "managed@example.net", "password": "managed-password", "role": "operator"},
        headers={"X-Neraium-Workspace-Id": workspace["workspace_id"]},
    )
    assert created.status_code == 201
    assert created.json()["role"] == "operator"
