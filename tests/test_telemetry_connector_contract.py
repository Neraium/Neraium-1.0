from __future__ import annotations

import inspect

import pytest

from app.connectors.base import (
    BoundedBackfillRange,
    ConnectorCheckpoint,
    ConnectorExecutionContext,
    ConnectorProviderDescriptor,
    TelemetryConnector,
)
from app.connectors.registry import (
    PRODUCTION_CONNECTOR_CLASSES,
    build_production_connector_descriptors,
    get_connector,
    get_telemetry_connector,
)
from app.services.telemetry_domain import ConnectorCapability, ConnectorType


def test_production_contract_is_capability_driven_and_retrieval_only() -> None:
    methods = {
        name
        for name, value in inspect.getmembers(TelemetryConnector, inspect.isfunction)
        if not name.startswith("_")
    }
    assert methods == {
        "validate",
        "discover_signals",
        "fetch_incremental",
        "fetch_backfill",
        "health",
    }
    assert callable(TelemetryConnector.descriptor)
    forbidden = {"write", "command", "execute", "publish", "acknowledge", "setpoint", "control"}
    assert methods.isdisjoint(forbidden)


def test_production_registry_excludes_legacy_rest_and_raw_database_connectors() -> None:
    assert set(PRODUCTION_CONNECTOR_CLASSES) == {
        ConnectorType.HTTPS_TELEMETRY.value,
        ConnectorType.HISTORIAN_TEMPLATE.value,
    }
    assert "rest" not in PRODUCTION_CONNECTOR_CLASSES
    assert "database" not in PRODUCTION_CONNECTOR_CLASSES
    # Existing manual/historical connector behavior remains available.
    assert get_connector("rest").connector_type == "rest"
    assert get_connector("database").connector_type == "database"


def test_descriptors_require_validation_health_and_read_only_boundary() -> None:
    descriptors = build_production_connector_descriptors()
    assert {item.connector_type for item in descriptors} == set(ConnectorType)
    assert all(item.retrieval_only for item in descriptors)
    assert all(ConnectorCapability.VALIDATE in item.capabilities for item in descriptors)
    assert all(ConnectorCapability.HEALTH_CHECK in item.capabilities for item in descriptors)
    assert next(
        item for item in descriptors if item.connector_type is ConnectorType.HISTORIAN_TEMPLATE
    ).production_available is False

    with pytest.raises(ValueError, match="retrieval_only"):
        ConnectorProviderDescriptor(
            connector_type=ConnectorType.HTTPS_TELEMETRY,
            display_name="unsafe",
            description="unsafe",
            capabilities=frozenset(
                {ConnectorCapability.VALIDATE, ConnectorCapability.HEALTH_CHECK}
            ),
            production_available=True,
            retrieval_only=False,
        )


def test_server_dependencies_are_required_to_construct_configured_providers() -> None:
    connector = get_telemetry_connector("https_telemetry")
    assert isinstance(connector, TelemetryConnector)
    with pytest.raises(ValueError, match="not configured"):
        get_telemetry_connector("historian_template")
    with pytest.raises(ValueError, match="not supported"):
        get_telemetry_connector("rest")


def test_context_rejects_cross_scope_secret_binding(memory_secret_store) -> None:
    binding = memory_secret_store.create(
        resource_scope_id="scope-a",
        connection_id="connection-a",
        values={"api_key": "opaque-value"},
    )
    with pytest.raises(ValueError, match="connection_mismatch"):
        ConnectorExecutionContext(
            connection_id="connection-b",
            resource_scope_id="scope-a",
            configuration={},
            secret_binding=binding,
        )


@pytest.fixture
def memory_secret_store():
    from app.services.telemetry_secrets import MemoryTelemetrySecretStore

    return MemoryTelemetrySecretStore(allow_test_backend=True)


def test_checkpoint_and_backfill_bounds_are_explicit_and_aware() -> None:
    from datetime import datetime, timezone

    assert ConnectorCheckpoint(cursor="cursor:abc").cursor == "cursor:abc"
    with pytest.raises(ValueError, match="must_be_aware"):
        ConnectorCheckpoint(high_water_at=datetime(2026, 1, 1))
    bounded = BoundedBackfillRange(
        start_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    assert bounded.start_at.tzinfo is not None
