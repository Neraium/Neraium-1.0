from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.routers import connectors as connectors_router


RETIRED_ROUTES = (
    ("GET", "/api/connectors/types"),
    ("GET", "/api/connectors/health"),
    ("POST", "/api/connectors/test"),
    ("POST", "/api/connectors/csv/upload"),
    ("POST", "/api/connectors/rest/test"),
    ("POST", "/api/connectors/rest/ingest"),
    ("POST", "/api/connectors/database/test"),
    ("POST", "/api/connectors/database/ingest"),
)
RETIRED_RESPONSE = {
    "code": "legacy_connection_operation_retired",
    "message": "This legacy connection operation is retired.",
}
GLOBAL_TELEMETRY_RETIRED_RESPONSE = {
    "code": "legacy_global_telemetry_retired",
    "message": "This global telemetry compatibility operation is retired.",
}
GLOBAL_TELEMETRY_RETIRED_ROUTES = (
    ("POST", "/api/telemetry/ingest"),
    ("POST", "/api/telemetry/signal-mappings"),
    ("GET", "/api/telemetry/signal-mappings"),
    ("GET", "/api/telemetry/signal-mappings/mapping-1"),
    ("PUT", "/api/telemetry/signal-mappings/mapping-1"),
    ("POST", "/api/telemetry/signal-mappings/mapping-1/disable"),
    ("GET", "/api/telemetry/ingestion-health"),
    ("POST", "/api/live-analysis/configurations"),
    ("GET", "/api/live-analysis/configurations"),
    ("GET", "/api/live-analysis/configurations/system-1"),
    ("PUT", "/api/live-analysis/configurations/system-1"),
    ("POST", "/api/live-analysis/configurations/system-1/enable"),
    ("POST", "/api/live-analysis/configurations/system-1/disable"),
    ("POST", "/api/live-analysis/systems/system-1/runs"),
    ("GET", "/api/live-analysis/runs"),
    ("GET", "/api/live-analysis/runs/run-1"),
    ("GET", "/api/live-analysis/findings"),
    ("GET", "/api/live-analysis/findings/finding-1"),
    ("GET", "/api/live-analysis/health"),
)


def _client(tmp_path, *, app_env: str, legacy_compat: bool = True) -> TestClient:
    settings = Settings(
        app_env=app_env,
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
        telemetry_legacy_compat_enabled=legacy_compat,
    )
    return TestClient(create_app(settings), base_url="https://testserver")


@pytest.mark.parametrize("app_env", ["staging", "prod", "production"])
@pytest.mark.parametrize(("method", "path"), RETIRED_ROUTES)
def test_deployed_environments_retire_unsafe_legacy_connector_routes_before_payload_validation(
    monkeypatch,
    tmp_path,
    app_env: str,
    method: str,
    path: str,
) -> None:
    monkeypatch.setenv("NERAIUM_API_TOKEN", "retirement-test-token")
    monkeypatch.setenv("NERAIUM_API_TOKEN_ROLE", "admin")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("legacy connector activity must not run")

    monkeypatch.setattr(connectors_router, "build_connector_instance", fail_if_called)
    client = _client(tmp_path / app_env, app_env=app_env, legacy_compat=True)

    response = client.request(
        method,
        path,
        content=b'{"deliberately": "not a valid legacy connector payload",',
        headers={
            "Authorization": "Bearer retirement-test-token",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 410
    assert response.json()["detail"] == RETIRED_RESPONSE


@pytest.mark.parametrize(("method", "path"), RETIRED_ROUTES)
def test_local_legacy_connector_routes_are_retired_when_compatibility_is_disabled(
    monkeypatch,
    tmp_path,
    method: str,
    path: str,
) -> None:
    monkeypatch.setattr(
        connectors_router,
        "build_connector_instance",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy connector activity must not run")
        ),
    )
    client = _client(tmp_path, app_env="development", legacy_compat=False)

    response = client.request(method, path, content=b"not-json", headers={"Content-Type": "application/json"})

    assert response.status_code == 410
    assert response.json()["detail"] == RETIRED_RESPONSE


def test_production_retirement_preserves_connector_admin_authorization(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NERAIUM_API_TOKEN", "operator-token")
    monkeypatch.setenv("NERAIUM_API_TOKEN_ROLE", "operator")
    client = _client(tmp_path, app_env="production")

    unauthenticated = client.post("/api/connectors/test", content=b"not-json")
    operator = client.post(
        "/api/connectors/test",
        content=b"not-json",
        headers={"Authorization": "Bearer operator-token"},
    )

    assert unauthenticated.status_code == 401
    assert operator.status_code == 403


def test_local_legacy_compatibility_still_runs_when_explicitly_enabled(monkeypatch, tmp_path) -> None:
    observed: list[tuple[str, dict[str, object]]] = []

    class CompatibleConnector:
        def validate_connection(self):
            return {"ok": True, "message": "Local connector validated."}

        def health_check(self):
            from app.connectors.models import ConnectorHealthStatus

            return ConnectorHealthStatus(
                connector_type="rest",
                display_name="Local REST fixture",
                functional=True,
                connection_status="ready",
            )

    def build(connector_type: str, config: dict[str, object]):
        observed.append((connector_type, config))
        return CompatibleConnector()

    monkeypatch.setattr(connectors_router, "build_connector_instance", build)
    client = _client(tmp_path, app_env="test", legacy_compat=True)

    response = client.post(
        "/api/connectors/test",
        json={"connector_type": "rest", "config": {"endpoint": "https://fixture.example.test/telemetry"}},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Local connector validated."
    assert observed == [("rest", {"endpoint": "https://fixture.example.test/telemetry"})]


@pytest.mark.parametrize("app_env", ["staging", "prod", "production"])
@pytest.mark.parametrize(("method", "path"), GLOBAL_TELEMETRY_RETIRED_ROUTES)
def test_deployed_environments_retire_global_telemetry_and_live_analysis_before_request_parsing(
    monkeypatch,
    tmp_path,
    app_env: str,
    method: str,
    path: str,
) -> None:
    monkeypatch.setenv("NERAIUM_API_TOKEN", "retirement-test-token")
    monkeypatch.setenv("NERAIUM_API_TOKEN_ROLE", "admin")
    client = _client(tmp_path / f"global-{app_env}", app_env=app_env, legacy_compat=True)

    response = client.request(
        method,
        path,
        content=b'{"deliberately": "not a valid legacy telemetry payload",',
        headers={
            "Authorization": "Bearer retirement-test-token",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 410
    assert response.json()["detail"] == GLOBAL_TELEMETRY_RETIRED_RESPONSE
