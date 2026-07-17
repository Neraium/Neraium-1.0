from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.auth_store import create_user
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
    return TestClient(create_app(settings), base_url="https://testserver")


def test_bootstrap_admin_can_log_in(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_PASSWORD", "password123")
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings), base_url="https://testserver")

    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})

    assert login.status_code == 200
    assert login.json()["user"]["role"] == "admin"
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["authenticated"] is True
    assert me.json()["user"]["role"] == "admin"


def test_production_login_rate_limit_returns_429(monkeypatch, tmp_path) -> None:
    clear_rate_limits()
    client = _production_client(monkeypatch, tmp_path)

    response = None
    for _ in range(6):
        response = client.post("/api/auth/login", json={"email": "missing@example.com", "password": "wrongpass123"})

    assert response is not None
    assert response.status_code == 429
    assert response.headers.get("Retry-After")


def test_invalid_login_returns_auth_specific_message(monkeypatch, tmp_path) -> None:
    clear_rate_limits()
    client = _production_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/auth/login",
        json={"email": "missing@example.com", "password": "wrongpass123"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}


def test_operator_cannot_access_admin_audit_route_in_production(monkeypatch, tmp_path) -> None:
    clear_rate_limits()
    create_user_context = _production_client(monkeypatch, tmp_path)
    create_user("operator@example.com", "password123", role="operator")
    login = create_user_context.post("/api/auth/login", json={"email": "operator@example.com", "password": "password123"})
    assert login.status_code == 200

    response = create_user_context.get("/api/audit/session/demo")

    assert response.status_code == 403
    assert response.json()["error_type"] == "auth"


def test_admin_can_access_admin_audit_route_in_production(monkeypatch, tmp_path) -> None:
    clear_rate_limits()
    client = _production_client(monkeypatch, tmp_path)
    create_user("admin2@example.com", "password123", role="admin")
    login = client.post("/api/auth/login", json={"email": "admin2@example.com", "password": "password123"})
    assert login.status_code == 200

    response = client.get("/api/audit/session/demo")

    assert response.status_code == 200
    assert response.json()["audit_record"]["audit_id"] == "audit-demo"


def test_database_connector_endpoints_require_admin_in_production(monkeypatch, tmp_path) -> None:
    clear_rate_limits()
    client = _production_client(monkeypatch, tmp_path)
    request_payload = {
        "database_url": "sqlite:///telemetry.db",
        "query": "SELECT timestamp FROM telemetry",
    }

    for path in ("/api/connectors/database/test", "/api/connectors/database/ingest"):
        response = client.post(path, json=request_payload)
        assert response.status_code == 401
        assert response.json()["error_type"] == "auth"

    create_user("connector-operator@example.com", "password123", role="operator")
    login = client.post(
        "/api/auth/login",
        json={"email": "connector-operator@example.com", "password": "password123"},
    )
    assert login.status_code == 200

    for path in ("/api/connectors/database/test", "/api/connectors/database/ingest"):
        response = client.post(path, json=request_payload)
        assert response.status_code == 403
        assert response.json()["error_type"] == "auth"
