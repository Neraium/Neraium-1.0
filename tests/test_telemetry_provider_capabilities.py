from __future__ import annotations

from fastapi import Request
from fastapi.testclient import TestClient

from app.connectors.base import ConnectorProviderDescriptor
from app.core.config import Settings
from app.core.security import require_api_access
from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.main import create_app
from app.services.dataset_scope import build_dataset_scope, set_current_dataset_scope
from app.services.phase4_scope import set_current_authenticated_phase4_scope
from app.services.telemetry_domain import ConnectorCapability, ConnectorType
from app.services.telemetry_runtime import TelemetryProviderRegistry, TelemetryRuntime
from app.services.workspace_authorization import WorkspaceContext, set_current_workspace_context


_CAPABILITIES = frozenset(
    {
        ConnectorCapability.VALIDATE,
        ConnectorCapability.DISCOVER_SIGNALS,
        ConnectorCapability.INCREMENTAL_POLLING,
        ConnectorCapability.BOUNDED_BACKFILL,
        ConnectorCapability.HEALTH_CHECK,
    }
)


class _Provider:
    def __init__(
        self,
        connector_type: ConnectorType,
        *,
        descriptor_available: bool,
        runtime_available: bool,
    ) -> None:
        self.connector_type = connector_type
        self.descriptor_available = descriptor_available
        self.runtime_available = runtime_available
        self.internal_secret_reference = "SECRET-CANARY-never-public"
        self.internal_template_ids = ("private-template-never-public",)

    def descriptor(self) -> ConnectorProviderDescriptor:
        return ConnectorProviderDescriptor(
            connector_type=self.connector_type,
            display_name=(
                "HTTPS telemetry API"
                if self.connector_type is ConnectorType.HTTPS_TELEMETRY
                else "Managed historian provider"
            ),
            description="Read-only telemetry retrieval provider.",
            capabilities=_CAPABILITIES,
            production_available=self.descriptor_available,
        )

    def is_production_available(self, configuration=None) -> bool:
        del configuration
        return self.runtime_available


def _client(tmp_path, *, controlled_egress_enabled: bool) -> TestClient:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
        telemetry_controlled_egress_enabled=controlled_egress_enabled,
    )
    app = create_app(settings)
    providers = TelemetryProviderRegistry(
        {
            ConnectorType.HTTPS_TELEMETRY: _Provider(
                ConnectorType.HTTPS_TELEMETRY,
                descriptor_available=True,
                runtime_available=True,
            ),
            ConnectorType.HISTORIAN_TEMPLATE: _Provider(
                ConnectorType.HISTORIAN_TEMPLATE,
                descriptor_available=False,
                runtime_available=True,
            ),
        },
        app_env="production",
        controlled_egress_enabled=controlled_egress_enabled,
    )
    app.state.telemetry_runtime = TelemetryRuntime(
        repository=object(),
        secret_store=object(),
        providers=providers,
        signal_registry=object(),
        health_service=object(),
        scheduler=object(),
    )

    async def authorize(request: Request) -> None:
        dataset_scope = build_dataset_scope(
            tenant_id="tenant-a",
            user_id="viewer@example.com",
            workspace_id="ws-facility-a",
        )
        workspace = WorkspaceContext(
            workspace_id="ws-facility-a",
            display_name="Facility A",
            kind="facility",
            membership_active=True,
            dataset_scope=dataset_scope,
        )
        request.state.auth_context = {
            "authenticated": True,
            "auth_subject": "viewer@example.com",
            "auth_role": "viewer",
        }
        set_current_dataset_scope(dataset_scope)
        set_current_workspace_context(workspace)
        set_current_authenticated_phase4_scope(
            AuthenticatedPhase4Scope(
                tenant_scope_id=dataset_scope.tenant_id,
                workspace_id=workspace.workspace_id,
            )
        )

    app.dependency_overrides[require_api_access] = authorize
    return TestClient(app, base_url="https://testserver")


def test_provider_capabilities_expose_only_safe_production_contracts(tmp_path) -> None:
    with _client(tmp_path, controlled_egress_enabled=True) as client:
        response = client.get("/api/data-connections/providers")

    assert response.status_code == 200, response.text
    providers = response.json()["providers"]
    assert {item["connector_type"] for item in providers} == {
        "https_telemetry",
        "historian_template",
    }
    assert all(item["retrieval_only"] is True for item in providers)
    assert all(item["available"] is True for item in providers)
    assert all("validate" in item["capabilities"] for item in providers)
    assert all("health_check" in item["capabilities"] for item in providers)
    assert "rest" not in response.text
    assert "database" not in response.text
    assert "SECRET-CANARY" not in response.text
    assert "private-template-never-public" not in response.text


def test_https_provider_availability_fails_closed_without_controlled_egress(tmp_path) -> None:
    with _client(tmp_path, controlled_egress_enabled=False) as client:
        response = client.get("/api/data-connections/providers")

    assert response.status_code == 200, response.text
    providers = {
        item["connector_type"]: item for item in response.json()["providers"]
    }
    assert providers["https_telemetry"]["available"] is False
    assert providers["historian_template"]["available"] is True
