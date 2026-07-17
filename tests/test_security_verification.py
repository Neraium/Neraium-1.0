from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.connectors.rest_connector import RESTConnector, mask_secret, masked_headers
from app.core.config import DEFAULT_MAX_UPLOAD_SIZE_BYTES, Settings
from app.core.outbound_url import sanitize_url_for_display, validate_outbound_http_url
from app.core.upload_security import sanitize_upload_filename
from app.main import create_app
from app.services.auth_store import create_user
from app.services.data_connections import upsert_registered_data_connection
from app.services.rate_limiter import clear_rate_limits


def production_client(monkeypatch, tmp_path, *, token: str = "") -> TestClient:
    clear_rate_limits()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    if token:
        monkeypatch.setenv("NERAIUM_API_TOKEN", token)
    else:
        monkeypatch.delenv("NERAIUM_API_TOKEN", raising=False)
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    return TestClient(create_app(settings))


@pytest.mark.parametrize(
    "path",
    [
        "/api/facility/systems",
        "/api/data/latest-upload",
        "/api/data/upload-status/" + "a" * 32,
        "/api/data/intake/" + "a" * 32 + "/result",
        "/api/data/replay/" + "a" * 32,
        "/api/replay/timeline",
        "/api/intelligence/engine-identity",
        "/latest-upload",
        "/systems",
    ],
)
def test_uploaded_artifact_routes_require_authentication_in_production(monkeypatch, tmp_path, path) -> None:
    client = production_client(monkeypatch, tmp_path)

    response = client.get(path)

    assert response.status_code == 401
    assert response.json()["error_type"] == "auth"



def test_verbose_readiness_requires_admin_authentication_in_production(monkeypatch, tmp_path) -> None:
    client = production_client(monkeypatch, tmp_path, token="service-secret")

    assert client.get("/api/ready?verbose=true").status_code == 401
    authenticated = client.get(
        "/api/ready?verbose=true",
        headers={"X-Neraium-Access-Code": "service-secret"},
    )
    assert authenticated.status_code in {200, 503}

def test_exact_public_health_allowlist_does_not_prefix_match(monkeypatch, tmp_path) -> None:
    client = production_client(monkeypatch, tmp_path)

    assert client.get("/api/health").status_code in {200, 503}
    assert client.get("/api/health-private").status_code == 404


def test_login_response_never_contains_bearer_session_secret(monkeypatch, tmp_path) -> None:
    client = production_client(monkeypatch, tmp_path)
    create_user("operator-security@example.com", "password123", role="operator")

    response = client.post(
        "/api/auth/login",
        json={"email": "operator-security@example.com", "password": "password123"},
    )

    assert response.status_code == 200
    public_handle = response.json()["session"]["session_id"]
    cookie_secret = client.cookies.get("neraium_session")
    assert public_handle.startswith("session_")
    assert cookie_secret
    assert public_handle != cookie_secret
    assert cookie_secret not in response.text


def test_cookie_authenticated_writes_reject_untrusted_origin(monkeypatch, tmp_path) -> None:
    client = production_client(monkeypatch, tmp_path)
    create_user("operator-csrf@example.com", "password123", role="operator")
    assert client.post(
        "/api/auth/login",
        json={"email": "operator-csrf@example.com", "password": "password123"},
    ).status_code == 200

    rejected = client.post("/api/data/reset", headers={"Origin": "https://attacker.example"})
    accepted = client.post("/api/data/reset", headers={"Origin": "https://app.neraium.com"})

    assert rejected.status_code == 403
    assert accepted.status_code == 200


def test_logout_rejects_cross_origin_cookie_request_and_revokes_on_allowed_origin(monkeypatch, tmp_path) -> None:
    client = production_client(monkeypatch, tmp_path)
    create_user("operator-logout@example.com", "password123", role="operator")
    assert client.post(
        "/api/auth/login",
        json={"email": "operator-logout@example.com", "password": "password123"},
    ).status_code == 200

    assert client.post("/api/auth/logout", headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.get("/api/auth/me").json()["authenticated"] is True
    assert client.post("/api/auth/logout", headers={"Origin": "https://app.neraium.com"}).status_code == 200
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_forwarded_for_cannot_bypass_login_rate_limit(monkeypatch, tmp_path) -> None:
    client = production_client(monkeypatch, tmp_path)
    response = None
    for attempt in range(6):
        response = client.post(
            "/api/auth/login",
            headers={"X-Forwarded-For": f"198.51.100.{attempt + 1}"},
            json={"email": "missing-security@example.com", "password": "wrongpass123"},
        )
    assert response is not None
    assert response.status_code == 429


def test_all_required_security_headers_are_present_in_production(monkeypatch, tmp_path) -> None:
    response = production_client(monkeypatch, tmp_path).get("/api/health")

    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://[::1]/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/internal",
        "file:///etc/passwd",
        "https://user:password@example.com/data",
    ],
)
def test_ssrf_guard_rejects_local_non_http_and_credentialed_targets(url) -> None:
    with pytest.raises(ValueError):
        validate_outbound_http_url(url, resolve_dns=False)


def test_rest_connector_applies_ssrf_guard_even_with_mock_transport() -> None:
    connector = RESTConnector(
        {"endpoint": "http://127.0.0.1/internal"},
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"records": []})),
    )
    with pytest.raises(ValueError, match="local or private"):
        connector.fetch_historical()


def test_data_connection_rejects_private_target_before_persistence() -> None:
    with pytest.raises(ValueError, match="local or private"):
        upsert_registered_data_connection(
            {
                "connection_id": "private-target",
                "name": "Private target",
                "url": "http://192.168.1.20/telemetry",
            }
        )


def test_connector_secret_masking_and_url_display_are_non_reversible() -> None:
    assert mask_secret("super-secret-token") == "********"
    masked = masked_headers(
        {"Authorization": "Bearer top-secret", "X-Custom-Token": "token-value", "Accept": "application/json"},
        "another-secret",
    )
    assert masked["Authorization"] == "********"
    assert masked["X-Custom-Token"] == "********"
    assert masked["token"] == "********"
    assert masked["Accept"] == "application/json"
    displayed = sanitize_url_for_display("https://user:password@example.com/path?api_key=secret#fragment")
    assert displayed == "https://example.com/path"
    assert "password" not in displayed and "secret" not in displayed


def test_upload_filename_is_reduced_to_safe_basename() -> None:
    assert sanitize_upload_filename(r"..\..\operator<report>.csv") == "operator_report_.csv"
    assert sanitize_upload_filename("../../telemetry.csv") == "telemetry.csv"


def test_upload_rejects_mime_mismatch_binary_and_archive(monkeypatch, tmp_path) -> None:
    client = TestClient(
        create_app(
            Settings(
                app_env="development",
                backend_host="127.0.0.1",
                backend_port=8010,
                cors_origins=["*"],
                runtime_dir=tmp_path,
            )
        )
    )

    mime_mismatch = client.post(
        "/api/data/upload",
        files={"file": ("telemetry.csv", b"PK\x03\x04archive", "application/zip")},
    )
    binary = client.post(
        "/api/data/upload",
        files={"file": ("telemetry.csv", b"timestamp,value\n2026-01-01,1\x00", "text/csv")},
    )
    archive = client.post(
        "/api/data/upload",
        files={"file": ("telemetry.zip", b"PK\x03\x04archive", "application/zip")},
    )

    assert mime_mismatch.status_code == 400
    assert binary.status_code == 400
    assert binary.json()["error_type"] == "malformed_upload"
    assert archive.status_code == 400


def test_backend_default_upload_limit_matches_frontend_security_boundary() -> None:
    assert DEFAULT_MAX_UPLOAD_SIZE_BYTES == 250 * 1024 * 1024


def test_frontend_write_actions_are_role_gated_in_source() -> None:
    root = Path(__file__).resolve().parents[1]
    data_workspace = (root / "frontend/src/components/DataConnectionsWorkspace.jsx").read_text(encoding="utf-8")
    observation = (root / "frontend/src/components/ObservationCenterWorkspace.jsx").read_text(encoding="utf-8")

    assert 'const canOperate = !currentUser || ["operator", "admin"]' in data_workspace
    assert 'disabled={!canOperate}' in (root / "frontend/src/components/setup/IntakeFlowPanel.jsx").read_text(encoding="utf-8")
    assert 'const canSubmitFeedback = !currentUser || ["operator", "admin"]' in observation


def test_evidence_csv_export_neutralizes_spreadsheet_formulas() -> None:
    from app.services.evidence_store import build_evidence_export_csv

    exported = build_evidence_export_csv({"run_id": "run-1", "source_name": "=HYPERLINK(\"https://evil.example\")"})

    assert "'=HYPERLINK" in exported
    assert "\n=HYPERLINK" not in exported


def test_evidence_download_filename_is_header_safe() -> None:
    from app.core.upload_security import sanitize_upload_filename

    assert sanitize_upload_filename('neraium-evidence-run\r\nX-Evil: yes') == "neraium-evidence-run__X-Evil_ yes"


def _route_dependency_names(route) -> set[str]:
    names: set[str] = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dependency = stack.pop()
        stack.extend(dependency.dependencies)
        if dependency.call is not None:
            names.add(getattr(dependency.call, "__name__", repr(dependency.call)))
    return names


def test_every_nonpublic_api_endpoint_has_authentication_dependency() -> None:
    from fastapi.routing import APIRoute

    public_routes = {
        ("GET", "/"),
        ("GET", "/health"),
        ("GET", "/api/health"),
        ("GET", "/api/ready"),
        ("GET", "/api/app"),
        ("GET", "/api/domain/mode"),
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
    }
    auth_dependencies = {
        "require_api_access",
        "require_authenticated_api_access",
        "require_admin_role",
        "require_operator_role",
        "require_same_origin_cookie_request",
    }
    uncovered: list[str] = []
    for route in create_app().routes:
        if not isinstance(route, APIRoute):
            continue
        dependencies = _route_dependency_names(route)
        for method in route.methods:
            if (method, route.path) not in public_routes and not dependencies.intersection(auth_dependencies):
                uncovered.append(f"{method} {route.path}")
    assert uncovered == []


def test_every_business_state_change_has_role_enforcement() -> None:
    from fastapi.routing import APIRoute

    public_writes = {("POST", "/api/auth/login"), ("POST", "/api/auth/logout")}
    uncovered: list[str] = []
    for route in create_app().routes:
        if not isinstance(route, APIRoute):
            continue
        dependencies = _route_dependency_names(route)
        for method in route.methods.intersection({"POST", "PUT", "PATCH", "DELETE"}):
            if (method, route.path) not in public_writes and not dependencies.intersection({"require_operator_role", "require_admin_role"}):
                uncovered.append(f"{method} {route.path}")
    assert uncovered == []
