import json

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.auth_store import create_user, get_session_record
from app.services.rate_limiter import clear_rate_limits


def _production_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    return TestClient(create_app(settings))


def test_auth_store_migrates_legacy_json_to_runtime_db(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    legacy_path = tmp_path / "auth_store.json"
    legacy_payload = {
        "users": [
            {
                "email": "legacy@example.com",
                "name": "Legacy Operator",
                "role": "operator",
                "salt": "abc123",
                "password_hash": "8c9b79e81aa2a6c6adaa39d42a09e695c9636e6d1fe43e34a7af6514b5a2d201",
                "created_at": "2026-06-01T00:00:00+00:00",
            }
        ],
        "sessions": {
            "legacy-session": {
                "email": "legacy@example.com",
                "created_at": "2026-06-10T00:00:00+00:00",
                "expires_at": "2099-06-10T00:00:00+00:00",
            }
        },
    }
    legacy_path.write_text(json.dumps(legacy_payload), encoding="utf-8")
    client = _production_client(monkeypatch, tmp_path)
    migrated_session = get_session_record("legacy-session")

    assert migrated_session is not None
    assert migrated_session["email"] == "legacy@example.com"

    response = client.post("/api/auth/login", json={"email": "legacy@example.com", "password": "password123"})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "legacy@example.com"
    assert (tmp_path / "runtime.db").exists()
    assert (tmp_path / "auth_store.json.migrated").exists()


def test_admin_can_manage_users_and_sessions(monkeypatch, tmp_path) -> None:
    clear_rate_limits()
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_PASSWORD", "password123")
    client = _production_client(monkeypatch, tmp_path)

    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})
    assert login.status_code == 200

    create_response = client.post(
        "/api/auth/users",
        json={"email": "viewer@example.com", "password": "password123", "name": "Viewer", "role": "viewer"},
    )
    assert create_response.status_code == 200
    assert create_response.json()["role"] == "viewer"

    users_response = client.get("/api/auth/users")
    assert users_response.status_code == 200
    assert any(item["email"] == "viewer@example.com" for item in users_response.json()["users"])

    viewer_client = _production_client(monkeypatch, tmp_path)
    viewer_login = viewer_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "password123"})
    assert viewer_login.status_code == 200
    session_id = viewer_login.json()["session"]["session_id"]

    sessions_response = client.get("/api/auth/sessions")
    assert sessions_response.status_code == 200
    assert any(item["session_id"] == session_id for item in sessions_response.json()["sessions"])

    revoke_response = client.post(
        "/api/auth/sessions/revoke",
        json={"session_id": session_id},
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json()["revoked"] == 1

    me_after_revoke = viewer_client.get("/api/auth/me")
    assert me_after_revoke.status_code == 200
    assert me_after_revoke.json()["authenticated"] is False

    deactivate_response = client.post("/api/auth/users/viewer@example.com/deactivate")
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False

    blocked_login = viewer_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "password123"})
    assert blocked_login.status_code == 401

    activate_response = client.post("/api/auth/users/viewer@example.com/activate")
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True

    restored_login = viewer_client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "password123"})
    assert restored_login.status_code == 200


def test_observability_summary_includes_auth_metrics(monkeypatch, tmp_path) -> None:
    clear_rate_limits()
    client = _production_client(monkeypatch, tmp_path)
    create_user("admin2@example.com", "password123", role="admin")
    create_user("operator@example.com", "password123", role="operator")
    login = client.post("/api/auth/login", json={"email": "admin2@example.com", "password": "password123"})
    assert login.status_code == 200

    summary = client.get("/api/observability/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["auth"]["total_users"] >= 2
    assert payload["auth"]["active_users"] >= 2
    assert payload["auth"]["active_sessions"] >= 1

    metrics = client.get("/api/observability/metrics")
    assert metrics.status_code == 200
    assert "neraium_auth_users_active" in metrics.text
    assert "neraium_auth_sessions_active" in metrics.text
