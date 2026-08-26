"""Fail-closed server-owned historian/database provider boundary.

This module intentionally contains no SQL driver and accepts no network target,
DSN, path, table, or query. Deployments may register reviewed server-side
templates and executors that enforce read-only roles, parameter binding, TLS,
statement timeouts, and row caps outside the browser-controlled configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import re
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from app.connectors.base import (
    BoundedBackfillRange,
    ConnectorCheckpoint,
    ConnectorExecutionContext,
    ConnectorFailureKind,
    ConnectorPage,
    ConnectorProviderDescriptor,
    ConnectorValidationResult,
    ProviderHealthResult,
    TelemetryConnector,
    TelemetryConnectorError,
)
from app.services.telemetry_domain import (
    ConnectorCapability,
    ConnectorType,
    reject_sensitive_telemetry_fields,
)
from app.services.telemetry_secrets import (
    ResolvedSecret,
    TelemetrySecretError,
    TelemetrySecretStore,
)


_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_FORBIDDEN_PARAMETER_RE = re.compile(
    r"(?:sql|query|statement|dsn|database|catalog|schema|table|column|path|file|url|uri|host|port|socket|command|procedure|function|copy)",
    re.IGNORECASE,
)
_ALLOWED_CONFIG_KEYS = frozenset({"template_id", "network_profile_id", "parameters"})


@dataclass(frozen=True, slots=True)
class ServerHistorianTemplate:
    """An approval reference, never the SQL/query implementation itself."""

    template_id: str
    provider_id: str
    network_profile_id: str
    allowed_parameter_names: frozenset[str]
    capabilities: frozenset[ConnectorCapability]
    max_backfill_days: int = 366

    def __post_init__(self) -> None:
        for value in (self.template_id, self.provider_id, self.network_profile_id):
            if not _IDENTIFIER_RE.fullmatch(str(value or "")):
                raise ValueError("historian_template_identifier_invalid")
        parameters = frozenset(str(name) for name in self.allowed_parameter_names)
        if len(parameters) > 32 or any(
            not _IDENTIFIER_RE.fullmatch(name) or _FORBIDDEN_PARAMETER_RE.search(name)
            for name in parameters
        ):
            raise ValueError("historian_template_parameter_invalid")
        capabilities = frozenset(ConnectorCapability(item) for item in self.capabilities)
        required = {ConnectorCapability.VALIDATE, ConnectorCapability.HEALTH_CHECK}
        if not required.issubset(capabilities):
            raise ValueError("historian_template_capability_invalid")
        if ConnectorCapability.READ_EVENTS in capabilities:
            raise ValueError("historian_event_streaming_not_enabled")
        if not 1 <= int(self.max_backfill_days) <= 366:
            raise ValueError("historian_backfill_limit_invalid")
        object.__setattr__(self, "allowed_parameter_names", parameters)
        object.__setattr__(self, "capabilities", capabilities)


@dataclass(frozen=True, slots=True)
class HistorianReadRequest:
    """Bounded values passed to a reviewed server-owned executor."""

    connection_id: str
    resource_scope_id: str
    template_id: str
    network_profile_id: str
    parameters: Mapping[str, str | int | float | bool]
    checkpoint: ConnectorCheckpoint | None
    time_range: BoundedBackfillRange | None
    credentials: ResolvedSecret

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


class HistorianTemplateExecutor(Protocol):
    """Implemented only by deployment-owned reviewed read-only providers."""

    def validate(self, request: HistorianReadRequest) -> ConnectorValidationResult: ...

    def discover_signals(self, request: HistorianReadRequest) -> ConnectorPage: ...

    def fetch_incremental(self, request: HistorianReadRequest) -> ConnectorPage: ...

    def fetch_backfill(self, request: HistorianReadRequest) -> ConnectorPage: ...

    def health(self, request: HistorianReadRequest) -> ProviderHealthResult: ...


class HistorianProviderRegistry:
    """Process-local registry populated exclusively by server startup wiring."""

    def __init__(self) -> None:
        self._templates: dict[str, tuple[ServerHistorianTemplate, HistorianTemplateExecutor]] = {}

    def register_server_template(
        self,
        template: ServerHistorianTemplate,
        executor: HistorianTemplateExecutor,
    ) -> None:
        if template.template_id in self._templates:
            raise ValueError("historian_template_already_registered")
        required_executor_methods = (
            "validate",
            "discover_signals",
            "fetch_incremental",
            "fetch_backfill",
            "health",
        )
        if any(not callable(getattr(executor, name, None)) for name in required_executor_methods):
            raise ValueError("historian_template_executor_invalid")
        self._templates[template.template_id] = (template, executor)

    def resolve(
        self,
        template_id: str,
    ) -> tuple[ServerHistorianTemplate, HistorianTemplateExecutor]:
        resolved = self._templates.get(str(template_id))
        if resolved is None:
            raise TelemetryConnectorError(
                "historian_template_not_configured",
                kind=ConnectorFailureKind.NOT_CONFIGURED,
                safe_message="The selected historian provider is not configured.",
            )
        return resolved

    def configured_template_ids(self) -> tuple[str, ...]:
        """Internal operations metadata; not a browser discovery endpoint."""

        return tuple(sorted(self._templates))

    @property
    def has_server_templates(self) -> bool:
        """Whether deployment startup registered any reviewed template."""

        return bool(self._templates)

    def has_server_template(self, template_id: str) -> bool:
        """Check one server selection without exposing registry contents."""

        return str(template_id) in self._templates


class HistorianTemplateConnector(TelemetryConnector):
    def __init__(
        self,
        *,
        provider_registry: HistorianProviderRegistry,
        secret_store: TelemetrySecretStore,
        now: Any = lambda: datetime.now(UTC),
    ) -> None:
        self._provider_registry = provider_registry
        self._secret_store = secret_store
        self._now = now

    @property
    def production_available(self) -> bool:
        """Instance availability derived only from server startup wiring.

        The class descriptor stays conservatively unavailable because it has no
        deployment registry. Runtime code may consult this instance predicate
        without exposing template IDs through browser capability discovery.
        """

        return self._provider_registry.has_server_templates

    def is_production_available(self, configuration: Mapping[str, Any] | None = None) -> bool:
        """Fail closed unless the instance can resolve the selected template.

        With no configuration this reports instance readiness. When runtime
        dispatch supplies connection configuration, the named template must be
        present in the server-owned registry; browser input cannot turn an
        unregistered provider into an available one.
        """

        if not self.production_available:
            return False
        if configuration is None:
            return True
        template_id = str(configuration.get("template_id") or "").strip()
        return bool(template_id) and self._provider_registry.has_server_template(template_id)

    @classmethod
    def descriptor(cls) -> ConnectorProviderDescriptor:
        return ConnectorProviderDescriptor(
            connector_type=ConnectorType.HISTORIAN_TEMPLATE,
            display_name="Managed historian provider",
            description="Read through a deployment-owned historian template.",
            capabilities=frozenset(
                {
                    ConnectorCapability.VALIDATE,
                    ConnectorCapability.DISCOVER_SIGNALS,
                    ConnectorCapability.INCREMENTAL_POLLING,
                    ConnectorCapability.BOUNDED_BACKFILL,
                    ConnectorCapability.HEALTH_CHECK,
                }
            ),
            # A concrete template must be registered before this is available.
            production_available=False,
        )

    def validate(self, context: ConnectorExecutionContext) -> ConnectorValidationResult:
        template, executor, request = self._request(context, checkpoint=None, time_range=None)
        self._require_capability(template, ConnectorCapability.VALIDATE)
        return self._guard(lambda: executor.validate(request))

    def discover_signals(
        self,
        context: ConnectorExecutionContext,
        *,
        checkpoint: ConnectorCheckpoint | None = None,
    ) -> ConnectorPage:
        template, executor, request = self._request(
            context,
            checkpoint=checkpoint,
            time_range=None,
        )
        self._require_capability(template, ConnectorCapability.DISCOVER_SIGNALS)
        return self._guard(lambda: executor.discover_signals(request))

    def fetch_incremental(
        self,
        context: ConnectorExecutionContext,
        *,
        checkpoint: ConnectorCheckpoint | None = None,
    ) -> ConnectorPage:
        template, executor, request = self._request(
            context,
            checkpoint=checkpoint,
            time_range=None,
        )
        self._require_capability(template, ConnectorCapability.INCREMENTAL_POLLING)
        return self._guard(lambda: executor.fetch_incremental(request))

    def fetch_backfill(
        self,
        context: ConnectorExecutionContext,
        *,
        time_range: BoundedBackfillRange,
        checkpoint: ConnectorCheckpoint | None = None,
    ) -> ConnectorPage:
        template, executor, request = self._request(
            context,
            checkpoint=checkpoint,
            time_range=time_range,
        )
        self._require_capability(template, ConnectorCapability.BOUNDED_BACKFILL)
        if time_range.end_at - time_range.start_at > timedelta(days=template.max_backfill_days):
            raise TelemetryConnectorError(
                "historian_backfill_range_too_large",
                kind=ConnectorFailureKind.CONFIGURATION,
                safe_message="Historian backfill range exceeds the approved template limit.",
            )
        return self._guard(lambda: executor.fetch_backfill(request))

    def health(self, context: ConnectorExecutionContext) -> ProviderHealthResult:
        try:
            template, executor, request = self._request(
                context,
                checkpoint=None,
                time_range=None,
            )
            self._require_capability(template, ConnectorCapability.HEALTH_CHECK)
            return self._guard(lambda: executor.health(request))
        except TelemetryConnectorError as error:
            return ProviderHealthResult(
                reachable=False,
                authenticated=False,
                provider_healthy=False,
                checked_at=self._now(),
                code=error.code,
            )

    def _request(
        self,
        context: ConnectorExecutionContext,
        *,
        checkpoint: ConnectorCheckpoint | None,
        time_range: BoundedBackfillRange | None,
    ) -> tuple[ServerHistorianTemplate, HistorianTemplateExecutor, HistorianReadRequest]:
        configuration = context.configuration
        try:
            reject_sensitive_telemetry_fields(
                configuration,
                code="unsafe_historian_configuration",
                path="configuration",
            )
        except ValueError:
            raise _historian_config_error("historian_credential_fields_not_allowed") from None
        if set(configuration) - _ALLOWED_CONFIG_KEYS:
            raise _historian_config_error("historian_configuration_field_not_allowed")
        try:
            if len(json.dumps(dict(configuration), default=str).encode("utf-8")) > 32 * 1024:
                raise _historian_config_error("historian_configuration_too_large")
        except (TypeError, ValueError):
            raise _historian_config_error("historian_configuration_invalid") from None

        template_id = str(configuration.get("template_id") or "").strip()
        network_profile_id = str(configuration.get("network_profile_id") or "").strip()
        if not _IDENTIFIER_RE.fullmatch(template_id) or not _IDENTIFIER_RE.fullmatch(network_profile_id):
            raise _historian_config_error("historian_template_selection_invalid")
        template, executor = self._provider_registry.resolve(template_id)
        if network_profile_id != template.network_profile_id:
            raise _historian_config_error("historian_network_profile_not_approved")

        raw_parameters = configuration.get("parameters") or {}
        if not isinstance(raw_parameters, Mapping):
            raise _historian_config_error("historian_parameters_invalid")
        if set(str(key) for key in raw_parameters) != set(raw_parameters):
            raise _historian_config_error("historian_parameters_invalid")
        if not set(raw_parameters).issubset(template.allowed_parameter_names):
            raise _historian_config_error("historian_parameter_not_approved")
        parameters: dict[str, str | int | float | bool] = {}
        for key, value in raw_parameters.items():
            if _FORBIDDEN_PARAMETER_RE.search(str(key)):
                raise _historian_config_error("historian_parameter_not_approved")
            if not isinstance(value, (str, int, float, bool)) or len(str(value)) > 1_024:
                raise _historian_config_error("historian_parameter_value_invalid")
            parameters[str(key)] = value

        if context.secret_binding is None:
            raise TelemetryConnectorError(
                "historian_credentials_not_configured",
                kind=ConnectorFailureKind.NOT_CONFIGURED,
                safe_message="Historian credentials are not configured.",
            )
        try:
            credentials = self._secret_store.resolve(context.secret_binding)
        except TelemetrySecretError:
            raise TelemetryConnectorError(
                "historian_credentials_unavailable",
                kind=ConnectorFailureKind.AUTHENTICATION,
                safe_message="Historian credentials are unavailable.",
            ) from None
        return (
            template,
            executor,
            HistorianReadRequest(
                connection_id=context.connection_id,
                resource_scope_id=context.resource_scope_id,
                template_id=template.template_id,
                network_profile_id=template.network_profile_id,
                parameters=parameters,
                checkpoint=checkpoint,
                time_range=time_range,
                credentials=credentials,
            ),
        )

    @staticmethod
    def _require_capability(
        template: ServerHistorianTemplate,
        capability: ConnectorCapability,
    ) -> None:
        if capability not in template.capabilities:
            raise TelemetryConnectorError(
                "historian_capability_not_configured",
                kind=ConnectorFailureKind.NOT_CONFIGURED,
                safe_message="The selected historian operation is not configured.",
            )

    @staticmethod
    def _guard(operation: Any) -> Any:
        try:
            return operation()
        except TelemetryConnectorError:
            raise
        except Exception:
            # Driver errors frequently contain connection strings or SQL. They
            # must never cross the provider boundary.
            raise TelemetryConnectorError(
                "historian_provider_failed",
                kind=ConnectorFailureKind.PROVIDER,
                retryable=True,
                safe_message="Historian retrieval failed.",
            ) from None


def _historian_config_error(code: str) -> TelemetryConnectorError:
    return TelemetryConnectorError(
        code,
        kind=ConnectorFailureKind.CONFIGURATION,
        safe_message="Historian connector configuration is invalid.",
    )


__all__ = [
    "HistorianProviderRegistry",
    "HistorianReadRequest",
    "HistorianTemplateConnector",
    "HistorianTemplateExecutor",
    "ServerHistorianTemplate",
]
