from __future__ import annotations

from json import JSONDecodeError
from typing import Annotated, Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from app.core.security import (
    require_admin_role,
    require_api_access,
    require_legacy_global_telemetry_access,
    require_operator_role,
)
from app.models.api_models import (
    TelemetryIngestionHealthListResponse,
    TelemetryIngestionRequest,
    TelemetryIngestionResponse,
    TelemetrySignalMappingCreateRequest,
    TelemetrySignalMappingResponse,
    TelemetrySignalMappingsListResponse,
    TelemetrySignalMappingUpdateRequest,
)
from app.services.live_telemetry import (
    TelemetryConflictError,
    TelemetryLimitError,
    TelemetryNotFoundError,
    create_signal_mapping,
    disable_signal_mapping,
    ingest_telemetry_batch,
    list_ingestion_health,
    list_signal_mappings,
    read_signal_mapping,
    update_signal_mapping,
)


router = APIRouter(
    tags=["telemetry"],
    dependencies=[
        Depends(require_api_access),
        Depends(require_legacy_global_telemetry_access),
    ],
)
LegacyTelemetryRequest = TypeVar("LegacyTelemetryRequest", bound=BaseModel)

MappingIdPath = Annotated[
    str,
    Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
OptionalIdentifierQuery = Annotated[
    str | None,
    Query(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


async def parse_legacy_telemetry_request(
    request: Request,
    model: type[LegacyTelemetryRequest],
) -> LegacyTelemetryRequest:
    try:
        return model.model_validate(await request.json())
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from None
    except (JSONDecodeError, UnicodeDecodeError):
        raise RequestValidationError(
            [{"type": "json_invalid", "loc": ("body",), "msg": "Invalid JSON body.", "input": None}]
        ) from None


@router.post(
    "/telemetry/ingest",
    response_model=TelemetryIngestionResponse,
    dependencies=[Depends(require_operator_role)],
)
async def ingest_live_telemetry(request: Request) -> dict[str, Any]:
    payload = await parse_legacy_telemetry_request(request, TelemetryIngestionRequest)
    try:
        return ingest_telemetry_batch(payload.model_dump(), settings=request.app.state.settings)
    except TelemetryLimitError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from None
    except TelemetryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.post(
    "/telemetry/signal-mappings",
    response_model=TelemetrySignalMappingResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_role)],
)
async def create_live_telemetry_signal_mapping(request: Request) -> dict[str, Any]:
    payload = await parse_legacy_telemetry_request(request, TelemetrySignalMappingCreateRequest)
    try:
        return create_signal_mapping(payload.model_dump())
    except TelemetryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.get(
    "/telemetry/signal-mappings",
    response_model=TelemetrySignalMappingsListResponse,
)
def read_live_telemetry_signal_mappings(
    system_id: OptionalIdentifierQuery = None,
    include_disabled: bool = False,
) -> dict[str, Any]:
    return {
        "mappings": list_signal_mappings(
            system_id=system_id,
            include_disabled=include_disabled,
        )
    }


@router.get(
    "/telemetry/signal-mappings/{mapping_id}",
    response_model=TelemetrySignalMappingResponse,
)
def read_live_telemetry_signal_mapping(mapping_id: MappingIdPath) -> dict[str, Any]:
    try:
        return read_signal_mapping(mapping_id)
    except TelemetryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.put(
    "/telemetry/signal-mappings/{mapping_id}",
    response_model=TelemetrySignalMappingResponse,
    dependencies=[Depends(require_admin_role)],
)
async def update_live_telemetry_signal_mapping(
    mapping_id: MappingIdPath,
    request: Request,
) -> dict[str, Any]:
    payload = await parse_legacy_telemetry_request(request, TelemetrySignalMappingUpdateRequest)
    updates = {
        key: value
        for key, value in payload.model_dump().items()
        if key in payload.model_fields_set
    }
    nullable_field = next(
        (key for key in ("canonical_signal", "enabled") if key in updates and updates[key] is None),
        None,
    )
    if nullable_field:
        raise HTTPException(status_code=422, detail=f"{nullable_field} cannot be null.")
    try:
        return update_signal_mapping(mapping_id, updates)
    except TelemetryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/telemetry/signal-mappings/{mapping_id}/disable",
    response_model=TelemetrySignalMappingResponse,
    dependencies=[Depends(require_admin_role)],
)
def disable_live_telemetry_signal_mapping(mapping_id: MappingIdPath) -> dict[str, Any]:
    try:
        return disable_signal_mapping(mapping_id)
    except TelemetryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get(
    "/telemetry/ingestion-health",
    response_model=TelemetryIngestionHealthListResponse,
)
def read_live_telemetry_ingestion_health(
    request: Request,
    system_id: OptionalIdentifierQuery = None,
    source: OptionalIdentifierQuery = None,
) -> dict[str, Any]:
    return {
        "health": list_ingestion_health(
            settings=request.app.state.settings,
            system_id=system_id,
            source=source,
        )
    }
