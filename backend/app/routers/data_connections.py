"""Facility-scoped production telemetry lifecycle API."""

from __future__ import annotations

from json import JSONDecodeError
import re
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.security import require_admin_role, require_api_access, require_operator_role
from app.models.api_models import DataConnectionUpsertRequest
from app.models.telemetry_api_models import (
    BackfillCreateRequest,
    CanonicalSignalConceptsResponse,
    ConnectionActionResponse,
    ConnectionCreateRequest,
    ConnectionPatchRequest,
    ConnectionPublicResponse,
    ConnectionsListResponse,
    ConnectorProvidersResponse,
    CredentialPutRequest,
    CredentialStatusResponse,
    DiscoveryCheckpointRequest,
    DiscoveryResponse,
    IngestionErrorsListResponse,
    IngestionRunActionResponse,
    IngestionRunPublicResponse,
    IngestionRunsListResponse,
    MappingResponse,
    RetiredOperationResponse,
    SignalMappingPutRequest,
    SignalsListResponse,
    ValidationResponse,
)
from app.services.telemetry_backfill import TelemetryRunServiceError
from app.services.telemetry_connection_service import (
    TelemetryConnectionService,
    TelemetryConnectionServiceError,
)
from app.services.telemetry_runtime import TelemetryRuntimeUnavailable, telemetry_runtime_from_app
from app.services.telemetry_scope import (
    TelemetryScopeUnavailableError,
    current_telemetry_scope,
    normalize_audit_actor,
)
from app.services.telemetry_domain import ConnectorType


router = APIRouter(tags=["data-connections"], dependencies=[Depends(require_api_access)])
ConnectionIdPath = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]
SignalIdPath = Annotated[UUID, Path()]


def _legacy_compat(request: Request) -> bool:
    app_env = str(request.app.state.settings.app_env).strip().lower()
    return app_env in {"development", "test"} and bool(
        request.app.state.settings.telemetry_legacy_compat_enabled
    )


def _safe_legacy_message(value: Any) -> str:
    message = str(value or "").strip()
    if not message or re.search(
        r"traceback|stack trace|localhost|authorization|bearer|api[_-]?key|token=|\b(?:sql|python|psycopg|sqlite|errno)\b",
        message,
        re.IGNORECASE,
    ):
        return "The connector did not return usable telemetry. Check its settings and retry."
    return message[:500]


def _api_error(error: Exception) -> HTTPException:
    if isinstance(error, (TelemetryConnectionServiceError, TelemetryRunServiceError)):
        return HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.safe_message, "retryable": error.retryable},
        )
    if isinstance(error, TelemetryScopeUnavailableError):
        return HTTPException(
            status_code=404,
            detail={"code": "telemetry_workspace_not_found", "message": "Telemetry workspace not found.", "retryable": False},
        )
    return HTTPException(
        status_code=503,
        detail={
            "code": getattr(error, "code", "telemetry_service_unavailable"),
            "message": "Telemetry connections are temporarily unavailable.",
            "retryable": True,
        },
    )


def _service_scope(request: Request) -> tuple[TelemetryConnectionService, Any]:
    try:
        return TelemetryConnectionService(telemetry_runtime_from_app(request.app)), current_telemetry_scope()
    except (TelemetryRuntimeUnavailable, TelemetryScopeUnavailableError) as error:
        raise _api_error(error) from None


def _actor(request: Request) -> str:
    try:
        return normalize_audit_actor(getattr(request.state, "auth_context", None))
    except TelemetryScopeUnavailableError as error:
        raise _api_error(error) from None


def _require_existing(request: Request, connection_id: str) -> tuple[TelemetryConnectionService, Any]:
    service, scope = _service_scope(request)
    try:
        service.get_connection(scope, str(connection_id))
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None
    return service, scope


@router.get("/data-connections", response_model=ConnectionsListResponse)
def read_data_connections(request: Request) -> dict[str, Any]:
    if _legacy_compat(request):
        from app.services.data_connections import list_registered_data_connections

        return JSONResponse({"connections": list_registered_data_connections()})
    service, scope = _service_scope(request)
    try:
        return {"connections": service.list_connections(scope)}
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None


@router.post("/data-connections", response_model=ConnectionActionResponse, status_code=status.HTTP_201_CREATED)
async def create_data_connection(request: Request) -> dict[str, Any]:
    await require_admin_role(request)
    if _legacy_compat(request):
        from app.services.data_connections import upsert_registered_data_connection

        try:
            payload = DataConnectionUpsertRequest.model_validate(await request.json())
        except (JSONDecodeError, UnicodeDecodeError, ValidationError):
            raise HTTPException(status_code=422, detail="Connection payload is invalid.") from None
        connection_id = payload.connection_id or "rest-telemetry-intake"
        try:
            connection = upsert_registered_data_connection(
                {
                    "connection_id": connection_id,
                    **payload.model_dump(exclude={"connection_id"}),
                    "status": "polling" if payload.polling_enabled else "offline",
                }
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        return JSONResponse({"connection": connection, "message": f"{connection['name']} saved."})
    try:
        payload = ConnectionCreateRequest.model_validate(await request.json())
    except (JSONDecodeError, UnicodeDecodeError, ValidationError):
        raise HTTPException(status_code=422, detail="Telemetry connection payload is invalid.") from None
    service, scope = _service_scope(request)
    try:
        connection = service.create_connection(scope, payload, actor_id=_actor(request))
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "telemetry_connection_invalid", "message": "Telemetry connection configuration is invalid."}) from None
    return {"connection": connection, "message": "Telemetry connection created."}


@router.get("/data-connections/signal-concepts", response_model=CanonicalSignalConceptsResponse)
def list_signal_concepts(request: Request) -> dict[str, Any]:
    service, _scope = _service_scope(request)
    try:
        return {"concepts": service.list_signal_concepts()}
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None


@router.get(
    "/data-connections/providers",
    response_model=ConnectorProvidersResponse,
)
def list_data_connection_providers(request: Request) -> dict[str, Any]:
    """Describe only server-owned, retrieval-only production providers.

    The response deliberately excludes provider templates, connection
    configuration, secret bindings, and all legacy connector contracts.
    """

    try:
        runtime = telemetry_runtime_from_app(request.app)
        # Capability discovery is facility-authorized even though the returned
        # provider catalog is deployment-wide.
        current_telemetry_scope()
        providers: list[dict[str, Any]] = []
        for connector_type in ConnectorType:
            provider = runtime.providers.known(connector_type)
            descriptor = provider.descriptor()
            if (
                descriptor.connector_type is not connector_type
                or not descriptor.retrieval_only
            ):
                raise TelemetryRuntimeUnavailable(
                    "telemetry_connector_descriptor_invalid"
                )

            if connector_type is ConnectorType.HISTORIAN_TEMPLATE:
                availability_check = getattr(
                    provider, "is_production_available", None
                )
                available = bool(
                    callable(availability_check) and availability_check(None)
                )
                configuration_mode = "server_owned_template"
            else:
                try:
                    runtime.providers.get(connector_type)
                    available = True
                except TelemetryRuntimeUnavailable:
                    available = False
                configuration_mode = "safe_https_metadata"

            providers.append(
                {
                    "connector_type": connector_type,
                    "display_name": descriptor.display_name,
                    "description": descriptor.description,
                    "capabilities": sorted(
                        descriptor.capabilities, key=lambda item: item.value
                    ),
                    "available": available,
                    "retrieval_only": True,
                    "configuration_mode": configuration_mode,
                }
            )
        return {"providers": providers}
    except (TelemetryRuntimeUnavailable, TelemetryScopeUnavailableError) as error:
        raise _api_error(error) from None


@router.post("/data-connections/reset-all", response_model=RetiredOperationResponse, status_code=status.HTTP_410_GONE)
async def reset_all_connections(request: Request) -> dict[str, str]:
    # Compatibility may clear local development fixtures only; HTTP still says retired.
    if _legacy_compat(request):
        await require_admin_role(request)
        from app.services.data_connections import reset_all_data_connections

        connections = reset_all_data_connections()
        return JSONResponse({
            "connections": connections,
            "message": "All local development telemetry fixtures were reset.",
        }, status_code=200)
    return {"code": "legacy_connection_operation_retired", "message": "This legacy connection operation is retired."}


@router.get("/data-connections/{connection_id}", response_model=ConnectionPublicResponse)
def read_data_connection(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    if _legacy_compat(request):
        from app.services.data_connections import read_connection_status

        try:
            return JSONResponse(read_connection_status(connection_id))
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None
    service, scope = _require_existing(request, connection_id)
    try:
        return service.get_connection(scope, str(connection_id))
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None


@router.patch("/data-connections/{connection_id}", response_model=ConnectionActionResponse)
async def update_data_connection(request: Request, connection_id: ConnectionIdPath, payload: ConnectionPatchRequest) -> dict[str, Any]:
    service, scope = _require_existing(request, connection_id)
    await require_admin_role(request)
    try:
        connection = service.update_connection(scope, str(connection_id), payload, actor_id=_actor(request))
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "telemetry_connection_invalid", "message": "Telemetry connection configuration is invalid."}) from None
    return {"connection": connection, "message": "Telemetry connection updated."}


@router.put("/data-connections/{connection_id}/credentials", response_model=CredentialStatusResponse)
async def put_data_connection_credentials(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    # Authorization intentionally precedes consuming the one-way secret body.
    service, scope = _require_existing(request, connection_id)
    await require_admin_role(request)
    try:
        payload = CredentialPutRequest.model_validate(await request.json())
        return service.put_credentials(scope, str(connection_id), payload, actor_id=_actor(request))
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None
    except (JSONDecodeError, UnicodeDecodeError, ValidationError):
        raise HTTPException(status_code=422, detail={"code": "telemetry_credentials_invalid", "message": "Credential payload is invalid."}) from None


@router.post("/data-connections/{connection_id}/validate", response_model=ValidationResponse)
async def validate_data_connection(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    service, scope = _require_existing(request, connection_id)
    await require_operator_role(request)
    try:
        connection, result = service.validate_connection(scope, str(connection_id), actor_id=_actor(request))
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None
    return {"connection": connection, **result}


@router.post("/data-connections/{connection_id}/discover", response_model=DiscoveryResponse)
async def discover_data_connection_signals(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    service, scope = _require_existing(request, connection_id)
    await require_operator_role(request)
    try:
        try:
            body = await request.json()
        except JSONDecodeError:
            body = {}
        payload = DiscoveryCheckpointRequest.model_validate(body or {})
        return service.discover_signals(
            scope, str(connection_id), checkpoint=payload.checkpoint
        )
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None
    except (UnicodeDecodeError, ValidationError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "telemetry_discovery_checkpoint_invalid",
                "message": "Discovery checkpoint is invalid.",
            },
        ) from None


@router.get("/data-connections/{connection_id}/signals", response_model=SignalsListResponse)
def list_data_connection_signals(
    request: Request,
    connection_id: ConnectionIdPath,
    mapping_status: str | None = Query(default=None, pattern=r"^(unmapped|mapped|invalid|disabled)$"),
    limit: int = Query(default=250, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    service, scope = _require_existing(request, connection_id)
    try:
        return {
            "signals": service.list_signals(
                scope,
                str(connection_id),
                mapping_status=mapping_status,
                limit=limit,
                offset=offset,
            )
        }
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None


@router.get(
    "/data-connections/{connection_id}/runs",
    response_model=IngestionRunsListResponse,
)
def list_data_connection_runs(
    request: Request,
    connection_id: ConnectionIdPath,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> dict[str, Any]:
    service, scope = _require_existing(request, connection_id)
    try:
        return {
            "runs": service.list_ingestion_runs(
                scope, str(connection_id), limit=limit, offset=offset
            )
        }
    except (TelemetryConnectionServiceError, TelemetryRunServiceError) as error:
        raise _api_error(error) from None


@router.get(
    "/data-connections/{connection_id}/errors",
    response_model=IngestionErrorsListResponse,
)
def list_data_connection_errors(
    request: Request,
    connection_id: ConnectionIdPath,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> dict[str, Any]:
    service, scope = _require_existing(request, connection_id)
    try:
        return {
            "errors": service.list_ingestion_errors(
                scope, str(connection_id), limit=limit, offset=offset
            )
        }
    except (TelemetryConnectionServiceError, TelemetryRunServiceError) as error:
        raise _api_error(error) from None


@router.post(
    "/data-connections/{connection_id}/runs/{run_id}/retry",
    response_model=IngestionRunActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_data_connection_run(
    request: Request,
    connection_id: ConnectionIdPath,
    run_id: UUID,
) -> dict[str, Any]:
    service, scope = _require_existing(request, connection_id)
    await require_operator_role(request)
    try:
        run = service.retry_ingestion_run(
            scope,
            str(connection_id),
            str(run_id),
            actor_id=_actor(request),
        )
    except (TelemetryConnectionServiceError, TelemetryRunServiceError) as error:
        raise _api_error(error) from None
    return {"run": run, "message": "Telemetry ingestion retry scheduled."}


@router.post(
    "/data-connections/{connection_id}/backfills",
    response_model=IngestionRunActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_data_connection_backfill(
    request: Request,
    connection_id: ConnectionIdPath,
) -> dict[str, Any]:
    # Resolve scope and role before consuming bounded scheduling input.
    service, scope = _require_existing(request, connection_id)
    await require_operator_role(request)
    try:
        payload = BackfillCreateRequest.model_validate(await request.json())
        run = service.start_backfill(
            scope,
            str(connection_id),
            payload,
            actor_id=_actor(request),
        )
    except (TelemetryConnectionServiceError, TelemetryRunServiceError) as error:
        raise _api_error(error) from None
    except (JSONDecodeError, UnicodeDecodeError, ValidationError):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "telemetry_backfill_invalid",
                "message": "Backfill bounds must be a bounded UTC range.",
            },
        ) from None
    return {"run": run, "message": "Telemetry backfill scheduled."}


@router.get(
    "/data-connections/{connection_id}/backfills/{run_id}",
    response_model=IngestionRunPublicResponse,
)
def read_data_connection_backfill(
    request: Request,
    connection_id: ConnectionIdPath,
    run_id: UUID,
) -> dict[str, Any]:
    service, scope = _require_existing(request, connection_id)
    try:
        return service.get_backfill(scope, str(connection_id), str(run_id))
    except (TelemetryConnectionServiceError, TelemetryRunServiceError) as error:
        raise _api_error(error) from None


@router.put("/data-connections/{connection_id}/signals/{signal_id}/mapping", response_model=MappingResponse)
async def update_signal_mapping(
    request: Request,
    connection_id: ConnectionIdPath,
    signal_id: SignalIdPath,
    payload: SignalMappingPutRequest,
) -> dict[str, Any]:
    service, scope = _require_existing(request, connection_id)
    await require_operator_role(request)
    try:
        signal = service.map_signal(scope, str(connection_id), str(signal_id), payload, actor_id=_actor(request))
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None
    return {"signal": signal, "message": "Signal mapping approved."}


async def _set_enabled(request: Request, connection_id: str, *, enabled: bool) -> dict[str, Any]:
    if _legacy_compat(request):
        await require_admin_role(request)
        from app.services.data_connections import set_connection_polling

        try:
            connection = set_connection_polling(connection_id, enabled=enabled)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None
        return JSONResponse({
            "connection": connection,
            "message": f"Continuous ingestion {'started' if enabled else 'stopped'} for {connection['name']}.",
        })
    service, scope = _require_existing(request, connection_id)
    await require_admin_role(request)
    try:
        connection = service.set_enabled(scope, str(connection_id), enabled=enabled, actor_id=_actor(request))
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None
    except ValueError:
        raise HTTPException(status_code=409, detail={"code": "telemetry_lifecycle_conflict", "message": "Connection lifecycle transition is not allowed."}) from None
    return {"connection": connection, "message": "Telemetry ingestion enabled." if enabled else "Telemetry ingestion disabled."}


@router.post("/data-connections/{connection_id}/enable", response_model=ConnectionActionResponse)
async def enable_data_connection(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    return await _set_enabled(request, connection_id, enabled=True)


@router.post("/data-connections/{connection_id}/disable", response_model=ConnectionActionResponse)
async def disable_data_connection(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    return await _set_enabled(request, connection_id, enabled=False)


@router.delete("/data-connections/{connection_id}", response_model=ConnectionActionResponse)
async def archive_data_connection(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    service, scope = _require_existing(request, connection_id)
    await require_admin_role(request)
    try:
        connection = service.archive_connection(scope, str(connection_id), actor_id=_actor(request))
    except TelemetryConnectionServiceError as error:
        raise _api_error(error) from None
    return {"connection": connection, "message": "Telemetry connection archived."}


# Scope-authorized aliases retained for one compatibility release.
@router.post("/data-connections/{connection_id}/start", response_model=ConnectionActionResponse)
async def start_data_connection(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    return await _set_enabled(request, connection_id, enabled=True)


@router.post("/data-connections/{connection_id}/stop", response_model=ConnectionActionResponse)
async def stop_data_connection(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    return await _set_enabled(request, connection_id, enabled=False)


@router.post("/data-connections/{connection_id}/test", response_model=ValidationResponse)
async def test_data_connection_alias(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    if _legacy_compat(request):
        await require_operator_role(request)
        from app.services.data_connections import read_connection_status, test_data_connection

        try:
            existing = read_connection_status(connection_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None
        try:
            result = test_data_connection(connection_id)
        except Exception as error:
            from app.services.data_connections import upsert_registered_data_connection

            message = _safe_legacy_message(error)
            connection = upsert_registered_data_connection(
                {**existing, "status": "error", "error_message": message}
            )
            return JSONResponse({
                "connection": connection,
                "message": message,
                "normalized_preview": [],
            })
        return JSONResponse({
            "connection": result["connection"],
            "message": f"{result['connection']['name']} responded with valid telemetry.",
            "normalized_preview": result["normalized_preview"],
        })
    return await validate_data_connection(request, connection_id)


@router.post("/data-connections/{connection_id}/poll-once", response_model=ValidationResponse)
async def poll_data_connection_alias(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    if _legacy_compat(request):
        await require_operator_role(request)
        from app.services.data_connections import poll_data_connection_once

        try:
            result = poll_data_connection_once(connection_id, actor="operator:poll-once")
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None
        return JSONResponse({
            "connection": result["connection"],
            "message": f"Checked {result['connection']['name']}.",
            "latest_result": result.get("latest_result"),
            "meaningful_change": result.get("meaningful_change"),
        })
    return await validate_data_connection(request, connection_id)


@router.get("/data-connections/{connection_id}/status", response_model=ConnectionPublicResponse)
def data_connection_status_alias(request: Request, connection_id: ConnectionIdPath) -> dict[str, Any]:
    return read_data_connection(request, connection_id)


@router.post("/data-connections/{connection_id}/reset-baseline", response_model=RetiredOperationResponse, status_code=status.HTTP_410_GONE)
async def reset_data_connection_baseline(request: Request, connection_id: ConnectionIdPath) -> dict[str, str]:
    if _legacy_compat(request):
        await require_admin_role(request)
        from app.services.data_connections import reset_connection_live_baseline

        try:
            connection = reset_connection_live_baseline(connection_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from None
        return JSONResponse({
            "connection": connection,
            "message": f"Live baseline reset for {connection['name']}.",
        }, status_code=200)
    return {"code": "legacy_connection_operation_retired", "message": "This legacy connection operation is retired."}
