from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.auth_store import create_user
from app.services.rate_limiter import clear_rate_limits


def production_client(monkeypatch, tmp_path: Path) -> TestClient:
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
    return TestClient(create_app(settings))


def test_unknown_body_and_query_fields_are_rejected(client: TestClient) -> None:
    body_response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "password123", "is_admin": True},
    )
    assert body_response.status_code == 422
    assert body_response.json()["error_type"] == "validation_error"
    assert body_response.json()["errors"][0]["type"] == "extra_forbidden"

    query_response = client.get("/api/evidence/runs?limit=10&sort=password_hash")
    assert query_response.status_code == 422
    assert query_response.json()["error_type"] == "http_422"
    assert query_response.json()["detail"]["fields"] == ["sort"]


def test_boundary_and_malformed_requests_use_consistent_errors(client: TestClient) -> None:
    cases = [
        client.get("/api/evidence/runs?limit=101"),
        client.get("/api/evidence/runs?offset=1000001"),
        client.get("/api/replay/timeline?intervals=1001"),
        client.get("/api/replay/timeline?mode=unapproved"),
        client.get("/api/evidence/export/missing?format=xml"),
        client.get(
            "/api/replay/range?start_timestamp=2026-01-02T00:00:00Z"
            "&end_timestamp=2026-01-01T00:00:00Z"
        ),
    ]
    for response in cases:
        assert response.status_code == 422
        payload = response.json()
        assert payload["error_type"] in {"validation_error", "http_422"}
        assert payload["detail"]
        assert payload["message"]

    malformed = client.post(
        "/api/auth/login",
        content=b'{"email":',
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["error_type"] == "validation_error"


def test_payload_header_path_and_filename_limits(client: TestClient) -> None:
    oversized = client.post(
        "/api/auth/login",
        content=b"x" * (1_048_576 + 1),
        headers={"content-type": "application/json"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error_type"] == "payload_too_large"

    oversized_header = client.get("/api/health", headers={"X-Request-Id": "x" * 129})
    assert oversized_header.status_code == 400
    assert oversized_header.json()["error_type"] == "invalid_header"

    invalid_path = client.get(f"/api/evidence/runs/{'x' * 129}")
    assert invalid_path.status_code == 422

    invalid_filename = client.post(
        "/api/connectors/csv/upload",
        files={"file": ("x" * 252 + ".csv", "timestamp,value\n2026-01-01T00:00:00Z,1", "text/csv")},
    )
    assert invalid_filename.status_code == 400


def test_unauthorized_forbidden_not_found_and_conflict_contracts(monkeypatch, tmp_path: Path) -> None:
    clear_rate_limits()
    client = production_client(monkeypatch, tmp_path)

    unauthorized = client.get("/api/observability/summary")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error_type"] == "auth"
    assert unauthorized.json()["detail"]

    create_user("operator@example.com", "password123", role="operator")
    login = client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    forbidden = client.get("/api/observability/summary")
    assert forbidden.status_code == 403
    assert forbidden.json()["error_type"] == "auth"

    assert client.get("/api/evidence/runs/missing-run").status_code == 404
    assert client.get("/api/replay/missing-run").status_code == 404
    assert client.get("/api/data/intake/missing-run/result").status_code == 404
    assert client.get("/api/replay/frame/2099-01-01T00:00:00Z").status_code == 404

    create_user("admin@example.com", "password123", role="admin")
    admin_login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert admin_login.status_code == 200
    first = client.post(
        "/api/auth/users",
        json={"email": "duplicate@example.com", "password": "password123", "role": "viewer"},
    )
    duplicate = client.post(
        "/api/auth/users",
        json={"email": "duplicate@example.com", "password": "password123", "role": "viewer"},
    )
    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error_type"] == "http_409"


def test_openapi_covers_runtime_routes_and_contract_metadata(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    operations = [
        operation
        for item in schema["paths"].values()
        for method, operation in item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    runtime_operations = [
        route
        for route in client.app.routes
        if getattr(route, "methods", None)
        and getattr(route, "include_in_schema", False)
    ]
    assert len(operations) == sum(len(route.methods - {"HEAD", "OPTIONS"}) for route in runtime_operations)
    assert len(operations) == 106
    for operation in operations:
        assert operation.get("operationId")
        assert operation.get("tags") or operation["operationId"] in {
            "read_root__get", "health_check_alias_health_get",
            "latest_upload_alias_latest_upload_get", "systems_alias_systems_get",
            "read_startup_status_api_startup_status_get", "read_route_debug_api_routes_debug_get",
        }
        for status_code in ("400", "401", "403", "404", "409", "413", "422", "500"):
            assert status_code in operation["responses"]

    assert schema["paths"]["/latest-upload"]["get"]["deprecated"] is True
    assert schema["paths"]["/systems"]["get"]["deprecated"] is True
    login_schema = schema["components"]["schemas"]["LoginRequest"]
    assert login_schema["additionalProperties"] is False
    assert login_schema["properties"]["email"]["maxLength"] == 320
