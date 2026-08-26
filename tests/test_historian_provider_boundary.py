from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.connectors.base import (
    BoundedBackfillRange,
    ConnectorExecutionContext,
    ConnectorFailureKind,
    ConnectorPage,
    ConnectorValidationResult,
    ProviderHealthResult,
    TelemetryConnectorError,
)
from app.connectors.historian_provider import (
    HistorianProviderRegistry,
    HistorianTemplateConnector,
    ServerHistorianTemplate,
)
from app.services.telemetry_domain import ConnectorCapability
from app.services.telemetry_secrets import MemoryTelemetrySecretStore


class RecordingExecutor:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    def validate(self, request):
        self.requests.append(request)
        return ConnectorValidationResult(valid=True, reachable=True, authenticated=True)

    def discover_signals(self, request):
        self.requests.append(request)
        return ConnectorPage()

    def fetch_incremental(self, request):
        self.requests.append(request)
        return ConnectorPage()

    def fetch_backfill(self, request):
        self.requests.append(request)
        return ConnectorPage()

    def health(self, request):
        self.requests.append(request)
        return ProviderHealthResult(
            reachable=True,
            authenticated=True,
            provider_healthy=True,
            checked_at=datetime(2026, 1, 1, tzinfo=UTC),
            code="healthy",
        )


def setup_connector(*, allowed=frozenset({"facility_code", "batch_size"})):
    registry = HistorianProviderRegistry()
    executor = RecordingExecutor()
    registry.register_server_template(
        ServerHistorianTemplate(
            template_id="central_plant_v1",
            provider_id="managed_postgres",
            network_profile_id="customer_private_link_01",
            allowed_parameter_names=allowed,
            capabilities=frozenset(
                {
                    ConnectorCapability.VALIDATE,
                    ConnectorCapability.DISCOVER_SIGNALS,
                    ConnectorCapability.INCREMENTAL_POLLING,
                    ConnectorCapability.BOUNDED_BACKFILL,
                    ConnectorCapability.HEALTH_CHECK,
                }
            ),
            max_backfill_days=30,
        ),
        executor,
    )
    store = MemoryTelemetrySecretStore(allow_test_backend=True)
    binding = store.create(
        resource_scope_id="scope-a",
        connection_id="connection-a",
        values={"username": "readonly", "password": "canary-password"},
    )
    connector = HistorianTemplateConnector(provider_registry=registry, secret_store=store)
    return connector, executor, binding, registry


def context(binding, **configuration):
    config = {
        "template_id": "central_plant_v1",
        "network_profile_id": "customer_private_link_01",
        "parameters": {"facility_code": "FAC-1", "batch_size": 500},
    }
    config.update(configuration)
    return ConnectorExecutionContext(
        connection_id="connection-a",
        resource_scope_id="scope-a",
        configuration=config,
        secret_binding=binding,
    )


def test_historian_fails_closed_without_registered_server_template() -> None:
    store = MemoryTelemetrySecretStore(allow_test_backend=True)
    binding = store.create(
        resource_scope_id="scope-a",
        connection_id="connection-a",
        values={"username": "readonly", "password": "canary"},
    )
    connector = HistorianTemplateConnector(
        provider_registry=HistorianProviderRegistry(),
        secret_store=store,
    )
    with pytest.raises(TelemetryConnectorError) as error:
        connector.fetch_incremental(context(binding))
    assert error.value.code == "historian_template_not_configured"
    assert error.value.kind is ConnectorFailureKind.NOT_CONFIGURED


def test_historian_instance_availability_requires_a_valid_server_template() -> None:
    registry = HistorianProviderRegistry()
    store = MemoryTelemetrySecretStore(allow_test_backend=True)
    connector = HistorianTemplateConnector(provider_registry=registry, secret_store=store)

    assert registry.has_server_templates is False
    assert connector.production_available is False
    assert connector.is_production_available() is False
    assert connector.is_production_available({"template_id": "central_plant_v1"}) is False
    with pytest.raises(ValueError, match="executor_invalid"):
        registry.register_server_template(
            ServerHistorianTemplate(
                template_id="invalid_executor_v1",
                provider_id="managed_postgres",
                network_profile_id="customer_private_link_01",
                allowed_parameter_names=frozenset(),
                capabilities=frozenset(
                    {ConnectorCapability.VALIDATE, ConnectorCapability.HEALTH_CHECK}
                ),
            ),
            object(),  # type: ignore[arg-type]
        )
    assert connector.production_available is False

    configured, _, _, configured_registry = setup_connector()
    assert configured_registry.has_server_templates is True
    assert configured.production_available is True
    assert configured.is_production_available() is True
    assert configured.is_production_available({"template_id": "central_plant_v1"}) is True
    assert configured.is_production_available({"template_id": "unregistered_v1"}) is False
    assert configured.is_production_available({}) is False
    assert HistorianTemplateConnector.descriptor().production_available is False


@pytest.mark.parametrize(
    "unsafe",
    [
        {"query": "select * from secrets"},
        {"sql": "select 1"},
        {"dsn": "postgresql://user:canary@host/db"},
        {"database_url": "postgresql://host/db"},
        {"path": "/tmp/customer.sqlite"},
        {"parameters": {"query": "select 1"}},
        {"parameters": {"file_path": "/tmp/source"}},
    ],
)
def test_browser_sql_dsn_paths_and_unsafe_queries_are_rejected(unsafe) -> None:
    connector, _, binding, _ = setup_connector()
    with pytest.raises(TelemetryConnectorError) as error:
        connector.fetch_incremental(context(binding, **unsafe))
    assert error.value.kind is ConnectorFailureKind.CONFIGURATION
    assert "select" not in str(error.value).lower()
    assert "canary" not in str(error.value).lower()


def test_only_server_approved_template_network_profile_and_typed_parameters_reach_executor() -> None:
    connector, executor, binding, _ = setup_connector()
    result = connector.fetch_incremental(context(binding))
    assert result == ConnectorPage()
    request = executor.requests[0]
    assert request.template_id == "central_plant_v1"
    assert request.network_profile_id == "customer_private_link_01"
    assert dict(request.parameters) == {"facility_code": "FAC-1", "batch_size": 500}
    assert repr(request.credentials) == "ResolvedSecret([REDACTED])"
    assert not hasattr(request, "sql")
    assert not hasattr(request, "dsn")
    assert not hasattr(request, "path")

    with pytest.raises(TelemetryConnectorError) as profile_error:
        connector.fetch_incremental(
            context(binding, network_profile_id="unapproved_network")
        )
    assert profile_error.value.code == "historian_network_profile_not_approved"


def test_executor_exceptions_are_redacted_at_boundary() -> None:
    connector, executor, binding, _ = setup_connector()

    def fail(request):
        raise RuntimeError("postgresql://user:canary@private/select * from secret")

    executor.fetch_incremental = fail
    with pytest.raises(TelemetryConnectorError) as error:
        connector.fetch_incremental(context(binding))
    assert error.value.code == "historian_provider_failed"
    assert error.value.retryable is True
    assert "canary" not in str(error.value)
    assert error.value.__cause__ is None


def test_historian_health_sanitizes_driver_exceptions() -> None:
    connector, executor, binding, _ = setup_connector()

    def fail(request):
        raise RuntimeError(
            "arn:aws:secretsmanager:us-east-1:123456789012:secret:private canary-password"
        )

    executor.health = fail
    result = connector.health(context(binding))
    rendered = repr(result)
    assert result.provider_healthy is False
    assert result.code == "historian_provider_failed"
    assert "secretsmanager" not in rendered
    assert "canary-password" not in rendered


def test_historian_backfill_is_bounded_by_server_template() -> None:
    connector, executor, binding, _ = setup_connector()
    connector.fetch_backfill(
        context(binding),
        time_range=BoundedBackfillRange(
            start_at=datetime(2026, 1, 1, tzinfo=UTC),
            end_at=datetime(2026, 1, 15, tzinfo=UTC),
        ),
    )
    assert executor.requests[-1].time_range is not None

    with pytest.raises(TelemetryConnectorError) as error:
        connector.fetch_backfill(
            context(binding),
            time_range=BoundedBackfillRange(
                start_at=datetime(2026, 1, 1, tzinfo=UTC),
                end_at=datetime(2026, 2, 15, tzinfo=UTC),
            ),
        )
    assert error.value.code == "historian_backfill_range_too_large"


def test_server_template_definition_cannot_approve_query_shaped_parameters() -> None:
    with pytest.raises(ValueError, match="parameter_invalid"):
        ServerHistorianTemplate(
            template_id="template_v1",
            provider_id="provider",
            network_profile_id="profile",
            allowed_parameter_names=frozenset({"raw_sql_query"}),
            capabilities=frozenset(
                {ConnectorCapability.VALIDATE, ConnectorCapability.HEALTH_CHECK}
            ),
        )
