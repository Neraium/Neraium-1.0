"""Application wiring for production telemetry without SQLite or auth-store coupling."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
from typing import Any, Callable, Mapping

from app.connectors.base import TelemetryConnector
from app.connectors.https_telemetry import HttpsTelemetryConnector
from app.connectors.historian_provider import (
    HistorianProviderRegistry,
    HistorianTemplateConnector,
)
from app.core.config import Settings, parse_postgresql_url, validate_settings
from app.services.telemetry_domain import ConnectorType
from app.services.telemetry_repository import PostgreSQLTelemetryRepository
from app.services.telemetry_secrets import AwsSecretsManagerTelemetryStore, TelemetrySecretStore


logger = logging.getLogger(__name__)


class _LazySecretsManagerClient:
    """Delay AWS credential/provider resolution until a credential operation."""

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._client: Any | None = None
        self._lock = threading.Lock()

    def __getattr__(self, name: str) -> Any:
        client = self._client
        if client is None:
            with self._lock:
                client = self._client
                if client is None:
                    client = self._factory()
                    self._client = client
        return getattr(client, name)


class TelemetryRuntimeUnavailable(RuntimeError):
    def __init__(self, code: str = "telemetry_service_unavailable") -> None:
        super().__init__("Telemetry connections are temporarily unavailable.")
        self.code = code
        self.safe_message = "Telemetry connections are temporarily unavailable."


class TelemetryProviderRegistry:
    """Small retrieval-only registry; browser input selects only a known enum."""

    def __init__(
        self,
        providers: Mapping[ConnectorType, TelemetryConnector],
        *,
        app_env: str = "development",
        controlled_egress_enabled: bool = False,
    ) -> None:
        self._providers = dict(providers)
        self._app_env = str(app_env).strip().lower()
        self._controlled_egress_enabled = bool(controlled_egress_enabled)

    def get(
        self,
        connector_type: ConnectorType | str,
        *,
        configuration: Mapping[str, Any] | None = None,
    ) -> TelemetryConnector:
        provider = self.known(connector_type)
        descriptor = provider.descriptor()
        if (
            descriptor.connector_type is ConnectorType.HTTPS_TELEMETRY
            and self._app_env in {"staging", "prod", "production"}
            and not self._controlled_egress_enabled
        ):
            raise TelemetryRuntimeUnavailable("telemetry_controlled_egress_required")
        available = descriptor.production_available
        instance_check = getattr(provider, "is_production_available", None)
        if callable(instance_check):
            available = bool(instance_check(configuration or {}))
        elif descriptor.connector_type is ConnectorType.HISTORIAN_TEMPLATE:
            registry = getattr(provider, "_provider_registry", None)
            configured_ids = getattr(registry, "configured_template_ids", None)
            selected = str((configuration or {}).get("template_id") or "")
            available = bool(
                selected
                and callable(configured_ids)
                and selected in configured_ids()
            )
        if not available:
            raise TelemetryRuntimeUnavailable("telemetry_connector_not_available")
        return provider

    def known(self, connector_type: ConnectorType | str) -> TelemetryConnector:
        try:
            key = ConnectorType(connector_type)
        except (TypeError, ValueError):
            raise TelemetryRuntimeUnavailable("telemetry_connector_not_supported") from None
        provider = self._providers.get(key)
        if provider is None:
            raise TelemetryRuntimeUnavailable("telemetry_connector_not_available")
        return provider

    def capabilities(self, connector_type: ConnectorType | str) -> list[str]:
        provider = self.known(connector_type)
        return sorted(capability.value for capability in provider.descriptor().capabilities)


@dataclass(slots=True)
class TelemetryRuntime:
    repository: PostgreSQLTelemetryRepository | Any | None
    secret_store: TelemetrySecretStore | Any | None
    providers: TelemetryProviderRegistry | Any | None
    signal_registry: Any | None = None
    health_service: Any | None = None
    scheduler: Any | None = None
    unavailable_code: str | None = None

    @property
    def available(self) -> bool:
        return (
            self.unavailable_code is None
            and self.repository is not None
            and self.secret_store is not None
            and self.providers is not None
            and self.signal_registry is not None
            and self.health_service is not None
            and self.scheduler is not None
        )

    def require_available(self) -> "TelemetryRuntime":
        if not self.available:
            raise TelemetryRuntimeUnavailable(self.unavailable_code or "telemetry_service_unavailable")
        return self

    def verify_readiness(self) -> bool:
        """Verify the additive schema exists; migrations are never run here."""
        self.require_available()
        factory = getattr(self.repository, "_connection_factory", None)
        if not callable(factory):
            # Explicit test/service adapters own their readiness contract.
            verifier = getattr(self.repository, "verify_readiness", None)
            return bool(verifier()) if callable(verifier) else True
        connection = factory()
        try:
            from db.migrations.create_telemetry_connection_tables import (
                verify as verify_connection_schema,
            )
            from db.migrations.extend_telemetry_ingestion_runtime import (
                verify as verify_ingestion_runtime,
            )
            from db.migrations.seed_telemetry_canonical_signal_concepts import (
                verify as verify_signal_catalog,
            )

            for verifier in (
                verify_connection_schema,
                verify_signal_catalog,
                verify_ingestion_runtime,
            ):
                verifier(connection)
            return True
        except TelemetryRuntimeUnavailable:
            raise
        except Exception as error:
            raise TelemetryRuntimeUnavailable("telemetry_schema_not_ready") from error
        finally:
            connection.close()


def build_telemetry_connection_factory(database_url: str) -> Callable[[], Any]:
    """Return a PostgreSQL-only factory; the URL is never logged or exposed."""
    dsn = parse_postgresql_url(
        database_url,
        name="NERAIUM_TELEMETRY_DATABASE_URL",
    )

    def connect() -> Any:
        import psycopg

        return psycopg.connect(dsn, connect_timeout=5)

    return connect


def build_telemetry_runtime(settings: Settings) -> TelemetryRuntime:
    database_url = str(settings.telemetry_database_url or "").strip()
    if not database_url:
        return TelemetryRuntime(
            repository=None,
            secret_store=None,
            providers=None,
            unavailable_code="telemetry_database_not_configured",
        )
    try:
        validate_settings(settings)
        import boto3

        client_options: dict[str, str] = {}
        if settings.telemetry_secret_region:
            client_options["region_name"] = settings.telemetry_secret_region
        secret_store = AwsSecretsManagerTelemetryStore(
            client=_LazySecretsManagerClient(
                lambda: boto3.client("secretsmanager", **client_options)
            ),
            environment=settings.app_env,
            dynamic_writes_enabled=settings.telemetry_dynamic_secret_writes_enabled,
        )
        repository = PostgreSQLTelemetryRepository(
            build_telemetry_connection_factory(database_url)
        )
        providers = TelemetryProviderRegistry(
            {
                ConnectorType.HTTPS_TELEMETRY: HttpsTelemetryConnector(
                    secret_store=secret_store
                ),
                ConnectorType.HISTORIAN_TEMPLATE: HistorianTemplateConnector(
                    provider_registry=HistorianProviderRegistry(),
                    secret_store=secret_store,
                ),
            },
            app_env=settings.app_env,
            controlled_egress_enabled=settings.telemetry_controlled_egress_enabled,
        )
        runtime = TelemetryRuntime(
            repository=repository,
            secret_store=secret_store,
            providers=providers,
        )
        # Registry and health services are imported lazily so provider and
        # canonical-foundation modules remain independently testable.
        try:
            from app.services.signal_registry import (
                FacilityContextHierarchyAuthority,
                SignalRegistryService,
            )

            runtime.signal_registry = SignalRegistryService(
                repository, FacilityContextHierarchyAuthority()
            )
        except (ImportError, TypeError):
            runtime.signal_registry = None
        try:
            from app.services.telemetry_health import TelemetryHealthService

            runtime.health_service = TelemetryHealthService(repository)
        except (ImportError, TypeError):
            runtime.health_service = None
        try:
            from app.services.telemetry_ingestion import prepare_connector_page
            from app.services.telemetry_analysis_service import process_ingestion_run
            from app.services.telemetry_scheduler import TelemetryScheduler

            runtime.scheduler = TelemetryScheduler(
                repository=repository,
                providers=providers,
                normalize_page=prepare_connector_page,
                analyze_run=process_ingestion_run,
                lease_seconds=settings.telemetry_scheduler_lease_seconds,
                poll_interval_seconds=settings.telemetry_scheduler_poll_interval_seconds,
                heartbeat_interval_seconds=(
                    settings.telemetry_worker_heartbeat_interval_seconds
                ),
            )
        except (ImportError, TypeError, ValueError):
            runtime.scheduler = None
        return runtime
    except Exception:
        logger.error(
            "telemetry_runtime_configuration_failed",
            extra={"event": "telemetry_runtime_configuration_failed"},
        )
        return TelemetryRuntime(
            repository=None,
            secret_store=None,
            providers=None,
            unavailable_code="telemetry_runtime_configuration_invalid",
        )


def telemetry_runtime_from_app(app: Any) -> TelemetryRuntime:
    runtime = getattr(app.state, "telemetry_runtime", None)
    if not isinstance(runtime, TelemetryRuntime):
        raise TelemetryRuntimeUnavailable()
    return runtime.require_available()


__all__ = [
    "TelemetryProviderRegistry",
    "TelemetryRuntime",
    "TelemetryRuntimeUnavailable",
    "build_telemetry_connection_factory",
    "build_telemetry_runtime",
    "telemetry_runtime_from_app",
]
