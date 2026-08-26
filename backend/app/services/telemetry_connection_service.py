"""Scoped application service for the production telemetry connection lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import uuid
from typing import Any, Mapping
from urllib.parse import urlsplit

from app.connectors.base import ConnectorExecutionContext, TelemetryConnectorError
from app.models.telemetry_api_models import (
    BackfillCreateRequest,
    ConnectionCreateRequest,
    ConnectionPatchRequest,
    CredentialPutRequest,
    SignalMappingPutRequest,
    _validate_safe_configuration,
)
from app.services.telemetry_backfill import TelemetryBackfillService
from app.services.signal_registry import SignalRegistryError
from app.services.telemetry_domain import (
    ConnectionLifecycleStatus,
    ConnectorType,
    HealthFacetStatus,
    TelemetryScopeRef,
)
from app.services.telemetry_health import ProbeFacet
from app.services.telemetry_repository import (
    TelemetryMappingConflict,
    TelemetryRepositoryError,
)
from app.services.telemetry_runtime import TelemetryRuntime, TelemetryRuntimeUnavailable
from app.services.telemetry_scope import (
    OPAQUE_TELEMETRY_NOT_FOUND,
    TelemetryResourceNotFoundError,
    require_scoped_resource,
)
from app.services.telemetry_secrets import TelemetrySecretError

logger = logging.getLogger(__name__)


class TelemetryConnectionServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        message: str = "Telemetry connection operation failed.",
        status_code: int = 400,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.status_code = status_code
        self.retryable = retryable


def _not_found() -> TelemetryConnectionServiceError:
    return TelemetryConnectionServiceError(
        "telemetry_resource_not_found",
        message=OPAQUE_TELEMETRY_NOT_FOUND,
        status_code=404,
    )


def _repository_unavailable() -> TelemetryConnectionServiceError:
    return TelemetryConnectionServiceError(
        "telemetry_repository_unavailable",
        message="Telemetry connections are temporarily unavailable.",
        status_code=503,
        retryable=True,
    )


def _lifecycle_conflict() -> TelemetryConnectionServiceError:
    return TelemetryConnectionServiceError(
        "telemetry_lifecycle_conflict",
        message="Connection lifecycle transition is not allowed.",
        status_code=409,
    )


def _https_credential_context(configuration: Mapping[str, Any]) -> tuple[str, str]:
    parsed = urlsplit(str(configuration.get("base_url") or ""))
    host = str(parsed.hostname or "").rstrip(".").lower()
    port = parsed.port or 443
    origin = f"{parsed.scheme.lower()}://{host}:{port}"
    scheme = str(configuration.get("authentication_scheme") or "none").strip().lower()
    return origin, scheme


class TelemetryConnectionService:
    def __init__(self, runtime: TelemetryRuntime) -> None:
        self.runtime = runtime.require_available()
        self.repository = self.runtime.repository
        self.runs = TelemetryBackfillService(self.runtime)

    def _get(self, scope: TelemetryScopeRef, connection_id: str) -> dict[str, Any]:
        try:
            record = self.repository.get_connection(scope, connection_id)
            scoped = require_scoped_resource(record, scope=scope)
        except (TelemetryResourceNotFoundError, ValueError):
            raise _not_found() from None
        except TelemetryRepositoryError as error:
            if str(error) == "telemetry_connection_not_found":
                raise _not_found() from None
            raise _repository_unavailable() from None
        if (
            str(scoped.get("lifecycle_status") or "")
            == ConnectionLifecycleStatus.ARCHIVED.value
            or scoped.get("archived_at") is not None
        ):
            raise _not_found()
        return scoped

    def _refresh_health(self, scope: TelemetryScopeRef, connection_id: str) -> None:
        try:
            self.runtime.health_service.evaluate_and_persist(
                scope, connection_id=connection_id
            )
        except TelemetryRepositoryError as error:
            if str(error) == "telemetry_connection_not_found":
                raise _not_found() from None
            raise _repository_unavailable() from None
        except (TypeError, ValueError):
            raise TelemetryConnectionServiceError(
                "telemetry_health_evaluation_failed",
                message="Telemetry connection health could not be evaluated.",
                status_code=503,
                retryable=True,
            ) from None

    def _set_lifecycle(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        target_status: ConnectionLifecycleStatus,
        actor_id: str,
        **changes: Any,
    ) -> dict[str, Any]:
        try:
            record = self.repository.set_connection_lifecycle(
                scope,
                connection_id=connection_id,
                target_status=target_status,
                actor_id=actor_id,
                **changes,
            )
        except ValueError:
            raise _lifecycle_conflict() from None
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        if record is None:
            raise _not_found()
        return record

    def _record_audit(self, scope: TelemetryScopeRef, **event: Any) -> None:
        try:
            self.repository.record_audit_event(scope, **event)
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None

    def _binding(self, scope: TelemetryScopeRef, connection: Mapping[str, Any]) -> Any | None:
        if not bool(connection.get("credentials_configured")):
            return None
        try:
            return self.repository.load_secret_binding(
                scope, connection_id=str(connection["id"])
            )
        except TelemetryRepositoryError:
            raise TelemetryConnectionServiceError(
                "telemetry_credentials_unavailable",
                message="Telemetry credentials are unavailable.",
                status_code=409,
            ) from None

    def _provider_context(
        self, scope: TelemetryScopeRef, connection: Mapping[str, Any]
    ) -> tuple[Any, ConnectorExecutionContext]:
        try:
            provider = self.runtime.providers.get(
                connection["connector_type"],
                configuration=connection.get("safe_config") or {},
            )
        except TelemetryRuntimeUnavailable as error:
            raise TelemetryConnectionServiceError(
                error.code,
                message="The selected telemetry connector is not available.",
                status_code=409,
            ) from None
        return provider, ConnectorExecutionContext(
            connection_id=str(connection["id"]),
            resource_scope_id=scope.resource_scope_id,
            configuration=connection.get("safe_config") or {},
            secret_binding=self._binding(scope, connection),
        )

    def public_connection(
        self, scope: TelemetryScopeRef, connection: Mapping[str, Any]
    ) -> dict[str, Any]:
        record = require_scoped_resource(connection, scope=scope)
        connector_type = ConnectorType(record["connector_type"])
        try:
            health = self.runtime.health_service.get_health(
                scope, connection_id=str(record["id"])
            )
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        return {
            "connection_id": str(record["id"]),
            "resource_scope_id": scope.resource_scope_id,
            "facility_id": scope.facility_id,
            "name": record["name"],
            "connector_type": connector_type.value,
            "lifecycle_status": record["lifecycle_status"],
            "enabled": bool(record["enabled"]),
            "configuration": record.get("safe_config") or {},
            "timezone": record["timezone"],
            "polling_interval_seconds": int(record["polling_interval_seconds"]),
            "capabilities": self.runtime.providers.capabilities(connector_type),
            "credentials_configured": bool(record.get("credentials_configured")),
            "last_attempt_at": record.get("last_attempt_at"),
            "last_success_at": record.get("last_success_at"),
            "last_healthy_at": record.get("last_healthy_at"),
            "last_telemetry_at": record.get("last_telemetry_at"),
            "last_error_code": record.get("last_error_code"),
            "last_error_summary": record.get("last_error_summary"),
            "health": health,
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
        }

    def list_connections(self, scope: TelemetryScopeRef) -> list[dict[str, Any]]:
        try:
            records = self.repository.list_connections(scope)
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        return [self.public_connection(scope, record) for record in records]

    def get_connection(self, scope: TelemetryScopeRef, connection_id: str) -> dict[str, Any]:
        return self.public_connection(scope, self._get(scope, connection_id))

    def create_connection(
        self, scope: TelemetryScopeRef, payload: ConnectionCreateRequest, *, actor_id: str
    ) -> dict[str, Any]:
        try:
            self.runtime.providers.get(
                payload.connector_type, configuration=payload.configuration
            )
        except TelemetryRuntimeUnavailable as error:
            raise TelemetryConnectionServiceError(
                error.code,
                message="The selected telemetry connector is not available.",
                status_code=409,
            ) from None
        connection_id = str(uuid.uuid4())
        try:
            record = self.repository.create_connection(
                scope,
                connection_id=connection_id,
                name=payload.name,
                connector_type=payload.connector_type,
                safe_config=payload.configuration,
                timezone_name=payload.timezone,
                polling_interval_seconds=payload.polling_interval_seconds,
                actor_id=actor_id,
                audit_event_id=str(uuid.uuid4()),
                audit_safe_detail={
                    "connector_type": payload.connector_type.value,
                    "name": payload.name,
                },
            )
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        return self.public_connection(scope, record)

    def update_connection(
        self,
        scope: TelemetryScopeRef,
        connection_id: str,
        payload: ConnectionPatchRequest,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        existing = self._get(scope, connection_id)
        safe_config = None
        if payload.configuration is not None:
            safe_config = _validate_safe_configuration(
                ConnectorType(existing["connector_type"]), payload.configuration
            )
            if (
                ConnectorType(existing["connector_type"])
                is ConnectorType.HTTPS_TELEMETRY
                and bool(existing.get("credentials_configured"))
                and _https_credential_context(existing.get("safe_config") or {})
                != _https_credential_context(safe_config)
            ):
                raise TelemetryConnectionServiceError(
                    "telemetry_credential_context_change_forbidden",
                    message=(
                        "Create a new connection before changing the HTTPS origin "
                        "or authentication scheme for configured credentials."
                    ),
                    status_code=409,
                )
        try:
            record = self.repository.update_connection_metadata(
                scope,
                connection_id=connection_id,
                actor_id=actor_id,
                name=payload.name,
                safe_config=safe_config,
                timezone_name=payload.timezone,
                polling_interval_seconds=payload.polling_interval_seconds,
            )
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        if record is None:
            raise _not_found()
        return self.public_connection(scope, record)

    def put_credentials(
        self,
        scope: TelemetryScopeRef,
        connection_id: str,
        payload: CredentialPutRequest,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        connection = self._get(scope, connection_id)
        values = payload.unsealed_values()
        secret_operation = "updated" if connection.get("credentials_configured") else "created"
        try:
            if connection.get("credentials_configured"):
                binding = self.repository.load_secret_binding(
                    scope, connection_id=connection_id
                )
                if binding is None:
                    raise TelemetryConnectionServiceError(
                        "telemetry_credentials_unavailable",
                        message="Telemetry credentials are unavailable.",
                        status_code=409,
                    )
                binding = self.runtime.secret_store.update(binding, values=values)
            else:
                binding = self.runtime.secret_store.create(
                    resource_scope_id=scope.resource_scope_id,
                    connection_id=connection_id,
                    values=values,
                )
            fields = binding.internal_persistence_fields()
            try:
                self.repository.upsert_secret_binding(
                    scope,
                    connection_id=connection_id,
                    binding_id=fields["binding_id"],
                    provider=fields["provider"],
                    internal_reference=fields["internal_reference"],
                    version_marker=fields["version_marker"],
                    actor_id=actor_id,
                    audit_event_id=str(uuid.uuid4()),
                    audit_safe_detail={"credential_version_changed": True},
                )
            except Exception as error:
                logger.error(
                    "telemetry_secret_binding_reconciliation_required",
                    extra={
                        "event": "telemetry_secret_binding_reconciliation_required",
                        "connection_id": connection_id,
                        "resource_scope_id": scope.resource_scope_id,
                        "secret_operation": secret_operation,
                        "reason": "repository_error",
                        "error_type": type(error).__name__,
                    },
                )
                raise _repository_unavailable() from None
            return binding.public_metadata().as_dict()
        except TelemetrySecretError as error:
            raise TelemetryConnectionServiceError(
                error.code,
                message=error.safe_message,
                status_code=409 if error.code == "dynamic_secret_writes_disabled" else 502,
            ) from None
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        finally:
            values.clear()

    def validate_connection(
        self, scope: TelemetryScopeRef, connection_id: str, *, actor_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        connection = self._get(scope, connection_id)
        now = datetime.now(UTC)
        starting_status = ConnectionLifecycleStatus(connection["lifecycle_status"])
        enabled = bool(connection.get("enabled"))
        transitioned_to_validating = starting_status in {
            ConnectionLifecycleStatus.DRAFT,
            ConnectionLifecycleStatus.DISCONNECTED,
            ConnectionLifecycleStatus.ERROR,
        }
        if transitioned_to_validating:
            self._set_lifecycle(
                scope,
                connection_id=connection_id,
                target_status=ConnectionLifecycleStatus.VALIDATING,
                actor_id=actor_id,
                enabled=enabled,
                last_attempt_at=now,
            )
        failure_kind: str | None = None
        try:
            provider, context = self._provider_context(scope, connection)
            result = provider.validate(context)
            success_status = (
                ConnectionLifecycleStatus.DISCONNECTED
                if transitioned_to_validating
                else starting_status
            )
            updated = self._set_lifecycle(
                scope,
                connection_id=connection_id,
                target_status=success_status,
                actor_id=actor_id,
                enabled=enabled,
                last_attempt_at=now,
                last_success_at=datetime.now(UTC),
            )
            safe = {
                "valid": result.valid,
                "reachable": result.reachable,
                "authenticated": result.authenticated,
                "observations_sampled": result.observations_sampled,
                "code": result.code,
            }
        except TelemetryConnectorError as error:
            failure_kind = error.kind.value
            if starting_status is ConnectionLifecycleStatus.DISABLED:
                failure_status = ConnectionLifecycleStatus.DISABLED
            elif error.kind.value == "network":
                failure_status = ConnectionLifecycleStatus.DISCONNECTED
            elif transitioned_to_validating:
                failure_status = ConnectionLifecycleStatus.ERROR
            else:
                failure_status = ConnectionLifecycleStatus.DEGRADED
            updated = self._set_lifecycle(
                scope,
                connection_id=connection_id,
                target_status=failure_status,
                actor_id=actor_id,
                enabled=enabled,
                last_attempt_at=now,
                last_error_code=error.code,
                last_error_summary=error.safe_message,
            )
            safe = {
                "valid": False,
                "reachable": error.kind.value == "authentication",
                "authenticated": False,
                "observations_sampled": 0,
                "code": error.code,
            }
        self._record_audit(
            scope,
            event_id=str(uuid.uuid4()),
            connection_id=connection_id,
            actor_id=actor_id,
            action="validation_completed",
            safe_detail=safe,
        )
        observed_at = datetime.now(UTC)
        if safe["valid"]:
            reachability_status = authentication_status = HealthFacetStatus.HEALTHY
        elif failure_kind == "authentication":
            reachability_status = HealthFacetStatus.HEALTHY
            authentication_status = HealthFacetStatus.UNHEALTHY
        elif failure_kind == "network":
            reachability_status = HealthFacetStatus.UNHEALTHY
            authentication_status = HealthFacetStatus.UNKNOWN
        else:
            reachability_status = authentication_status = HealthFacetStatus.UNKNOWN
        reachability = ProbeFacet(
            status=reachability_status,
            observed_at=observed_at,
            reason_code=None if reachability_status is HealthFacetStatus.HEALTHY else "probe_unresolved",
        )
        authentication = ProbeFacet(
            status=authentication_status,
            observed_at=observed_at,
            reason_code=None if authentication_status is HealthFacetStatus.HEALTHY else "probe_authentication_unresolved",
        )
        try:
            self.runtime.health_service.evaluate_and_persist(
                scope,
                connection_id=connection_id,
                reachability=reachability,
                authentication=authentication,
            )
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        except (TypeError, ValueError):
            raise TelemetryConnectionServiceError(
                "telemetry_health_evaluation_failed",
                message="Telemetry connection health could not be evaluated.",
                status_code=503,
                retryable=True,
            ) from None
        return self.public_connection(scope, updated), safe

    def discover_signals(
        self,
        scope: TelemetryScopeRef,
        connection_id: str,
        *,
        checkpoint: str | None = None,
    ) -> dict[str, Any]:
        connection = self._get(scope, connection_id)
        if checkpoint is not None:
            # Discovery continuation belongs to the leased worker/checkpoint
            # subsystem. Never decode or forward an untrusted browser token as
            # provider cursor state from this synchronous endpoint.
            raise TelemetryConnectionServiceError(
                "telemetry_discovery_checkpoint_unavailable",
                message="Discovery continuation is not available for this request.",
                status_code=409,
            )
        provider, context = self._provider_context(scope, connection)
        try:
            page = provider.discover_signals(context)
        except TelemetryConnectorError as error:
            raise TelemetryConnectionServiceError(
                error.code,
                message=error.safe_message,
                status_code=502,
                retryable=error.retryable,
            ) from None
        registry = self.runtime.signal_registry
        try:
            registered = registry.register_discovered_signals(
                scope,
                connection_id=connection_id,
                signals=[
                    {
                        "external_tag_id": item.external_tag_id,
                        "external_tag_name": item.external_tag_name,
                        "display_label": item.display_label,
                        "source_unit": item.reported_unit,
                        "metadata": dict(item.metadata),
                    }
                    for item in page.signals
                ],
            )
        except (SignalRegistryError, ValueError):
            raise TelemetryConnectionServiceError(
                "telemetry_discovery_payload_invalid",
                message="The telemetry provider returned invalid signal metadata.",
                status_code=502,
            ) from None
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        self._refresh_health(scope, connection_id)
        return {
            "connection_id": connection_id,
            "discovered_count": len(page.signals),
            "registered_count": len(registered),
            "has_more": page.has_more,
            "checkpoint": None,
        }

    def list_signals(
        self,
        scope: TelemetryScopeRef,
        connection_id: str,
        *,
        mapping_status: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        self._get(scope, connection_id)
        try:
            records = self.runtime.signal_registry.list_signals(
                scope,
                connection_id=connection_id,
                mapping_status=mapping_status,
                limit=limit,
                offset=offset,
            )
        except SignalRegistryError:
            raise TelemetryConnectionServiceError(
                "telemetry_signal_query_invalid",
                message="Telemetry signal query is invalid.",
                status_code=400,
            ) from None
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        return [self.public_signal(item) for item in records]

    def list_signal_concepts(self) -> list[dict[str, Any]]:
        try:
            records = self.repository.list_canonical_signal_concepts()
            return [
                {
                    "canonical_signal_id": str(item["id"]),
                    "canonical_name": item["canonical_name"],
                    "display_name": item["display_name"],
                    "physical_dimension": item["physical_dimension"],
                    "canonical_unit": item["canonical_unit"],
                    "taxonomy_version": int(item["taxonomy_version"]),
                }
                for item in records
            ]
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        except (KeyError, TypeError, ValueError):
            raise TelemetryConnectionServiceError(
                "telemetry_signal_catalog_invalid",
                message="Telemetry signal catalog is unavailable.",
                status_code=503,
            ) from None

    @staticmethod
    def public_signal(record: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {
            "connection_id", "external_tag_id", "external_tag_name", "display_label",
            "source_unit", "sample_cadence_seconds", "enabled", "mapping_status",
            "last_observed_at", "quality_state", "mapping_id", "system_id", "asset_id",
            "canonical_signal_id", "canonical_signal_name", "canonical_unit", "conversion_id",
            "conversion_version", "source_timezone", "expected_cadence_seconds",
            "provenance", "mapping_revision",
        }
        public = {"signal_id": str(record["id"]), **{key: record.get(key) for key in allowed}}
        if public.get("connection_id") is not None:
            public["connection_id"] = str(public["connection_id"])
        if public.get("canonical_signal_id") is not None:
            public["canonical_signal_id"] = str(public["canonical_signal_id"])
        return public

    def map_signal(
        self,
        scope: TelemetryScopeRef,
        connection_id: str,
        signal_id: str,
        payload: SignalMappingPutRequest,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        self._get(scope, connection_id)
        registry = self.runtime.signal_registry
        try:
            registry.map_signal(
                scope,
                connection_id=connection_id,
                signal_id=signal_id,
                system_id=payload.system_id,
                asset_id=payload.asset_id,
                canonical_concept_id=str(payload.canonical_signal_id),
                source_unit=payload.source_unit,
                source_timezone=payload.source_timezone,
                actor_id=actor_id,
                expected_cadence_seconds=payload.expected_cadence_seconds,
                provenance=payload.provenance,
                provenance_reason=payload.reason,
                expected_revision=payload.expected_revision,
            )
        except (SignalRegistryError, TelemetryMappingConflict):
            raise TelemetryConnectionServiceError(
                "telemetry_signal_mapping_invalid",
                message="Telemetry signal mapping is invalid or conflicts with an existing mapping.",
                status_code=409,
            ) from None
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        getter = getattr(registry, "get_signal", None)
        if callable(getter):
            try:
                exact = getter(scope, connection_id=connection_id, signal_id=signal_id)
            except TelemetryRepositoryError:
                raise _repository_unavailable() from None
            match = self.public_signal(exact) if exact is not None else None
        else:
            # Compatibility for narrow adapters while the repository exposes
            # the direct scoped lookup. Paging is bounded and never N+1 per row.
            match = None
            for offset in range(0, 10_000, 500):
                page = self.list_signals(
                    scope, connection_id, mapping_status=None, limit=500, offset=offset
                )
                match = next((item for item in page if item["signal_id"] == signal_id), None)
                if match is not None or len(page) < 500:
                    break
        if match is None:
            raise _not_found()
        self._refresh_health(scope, connection_id)
        return match

    def set_enabled(
        self,
        scope: TelemetryScopeRef,
        connection_id: str,
        *,
        enabled: bool,
        actor_id: str,
    ) -> dict[str, Any]:
        existing = self._get(scope, connection_id)
        target = (
            ConnectionLifecycleStatus.DISCONNECTED
            if enabled
            else ConnectionLifecycleStatus.DISABLED
        )
        changed = not (
            ConnectionLifecycleStatus(existing["lifecycle_status"]) is target
            and bool(existing.get("enabled")) is enabled
        )
        if not changed:
            record = existing
        else:
            record = self._set_lifecycle(
                scope,
                connection_id=connection_id,
                target_status=target,
                enabled=enabled,
                actor_id=actor_id,
            )
        if enabled:
            try:
                scheduled = self.repository.schedule_connection_now(
                    scope,
                    connection_id=connection_id,
                    requested_at=datetime.now(UTC),
                )
            except TelemetryRepositoryError:
                raise _repository_unavailable() from None
            if not scheduled:
                raise _not_found()
            record = self._get(scope, connection_id)
        self._refresh_health(scope, connection_id)
        return self.public_connection(scope, record)

    def list_ingestion_runs(
        self,
        scope: TelemetryScopeRef,
        connection_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        self._get(scope, connection_id)
        return self.runs.list_runs(
            scope, connection_id=connection_id, limit=limit, offset=offset
        )

    def list_ingestion_errors(
        self,
        scope: TelemetryScopeRef,
        connection_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        self._get(scope, connection_id)
        return self.runs.list_errors(
            scope, connection_id=connection_id, limit=limit, offset=offset
        )

    def retry_ingestion_run(
        self,
        scope: TelemetryScopeRef,
        connection_id: str,
        run_id: str,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        connection = self._get(scope, connection_id)
        if not bool(connection.get("enabled")):
            raise TelemetryConnectionServiceError(
                "telemetry_connection_not_enabled",
                message="Enable the telemetry connection before retrying ingestion.",
                status_code=409,
            )
        return self.runs.retry_run(
            scope,
            connection_id=connection_id,
            run_id=run_id,
            actor_id=actor_id,
        )

    def start_backfill(
        self,
        scope: TelemetryScopeRef,
        connection_id: str,
        payload: BackfillCreateRequest,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        connection = self._get(scope, connection_id)
        return self.runs.start_backfill(scope, connection, payload, actor_id=actor_id)

    def get_backfill(
        self,
        scope: TelemetryScopeRef,
        connection_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        self._get(scope, connection_id)
        record = self.runs.get_run(
            scope, connection_id=connection_id, run_id=run_id
        )
        if record["mode"] != "backfill":
            raise _not_found()
        return record

    def archive_connection(
        self, scope: TelemetryScopeRef, connection_id: str, *, actor_id: str
    ) -> dict[str, Any]:
        self._get(scope, connection_id)
        try:
            record = self.repository.archive_connection(
                scope, connection_id=connection_id, actor_id=actor_id
            )
        except ValueError:
            raise _lifecycle_conflict() from None
        except TelemetryRepositoryError:
            raise _repository_unavailable() from None
        if record is None:
            raise _not_found()
        return self.public_connection(scope, record)


__all__ = [
    "TelemetryConnectionService",
    "TelemetryConnectionServiceError",
]
