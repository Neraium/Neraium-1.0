from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
import app.routers.auth as auth_router
from app.services.auth_store import create_user
from app.services.rate_limiter import clear_rate_limits


def _production_client(monkeypatch, tmp_path) -> TestClient:
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


def test_bootstrap_admin_can_log_in(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
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
    assert response.json() == {
        "detail": "Invalid email or password.",
        "message": "Invalid email or password.",
        "error_type": "auth",
    }


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


def test_no_active_session_does_not_touch_unavailable_auth_store(monkeypatch, tmp_path) -> None:
    client = _production_client(monkeypatch, tmp_path)

    def fail_if_called(_session_id):
        raise RuntimeError("auth database should not be queried")

    monkeypatch.setattr(auth_router, "get_user_by_session", fail_if_called)
    monkeypatch.setattr(auth_router, "get_session_record", fail_if_called)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user": None, "session": None}


def test_auth_database_failure_returns_service_unavailable_and_logs_cause(monkeypatch, tmp_path, caplog) -> None:
    clear_rate_limits()
    client = _production_client(monkeypatch, tmp_path)

    def fail_authentication(_email, _password):
        raise RuntimeError("production auth database offline")

    monkeypatch.setattr(auth_router, "authenticate_user", fail_authentication)
    with caplog.at_level("ERROR", logger="app.routers.auth"):
        response = client.post(
            "/api/auth/login",
            json={"email": "craig@neraium.com", "password": "password123"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Authentication service temporarily unavailable.",
        "message": "Authentication service temporarily unavailable.",
        "error_type": "http_503",
    }
    assert "Invalid email or password" not in response.text
    assert "auth_store_request_failed" in caplog.text
    assert "production auth database offline" in caplog.text


def test_production_session_cookie_is_secure_http_only_and_host_scoped(monkeypatch, tmp_path) -> None:
    clear_rate_limits()
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_EMAIL", "cookie-admin@example.com")
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_PASSWORD", "password123")
    client = _production_client(monkeypatch, tmp_path)

    response = client.post(
        "/api/auth/login",
        json={"email": "cookie-admin@example.com", "password": "password123"},
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    attributes = {part.strip().lower() for part in cookie.split(";")[1:]}
    assert "secure" in attributes
    assert "httponly" in attributes
    assert "path=/" in attributes
    assert "samesite=lax" in attributes
    assert not any(attribute.startswith("domain=") for attribute in attributes)

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["authenticated"] is True
