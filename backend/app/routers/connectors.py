from __future__ import annotations

from json import JSONDecodeError
from pathlib import Path, PureWindowsPath
from typing import Any, TypeVar
from urllib.parse import unquote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from app.connectors.limits import MAX_CONNECTOR_RESPONSE_BYTES
from app.connectors.models import (
    ConnectorActionResponse,
    ConnectorHealthStatus,
    ConnectorTestRequest,
    DatabaseConnectorRequest,
    RestConnectorRequest,
)
from app.connectors.registry import CONNECTOR_CLASSES, build_connector_descriptors, get_connector
from app.connectors.store import ConnectorHealthStore
from app.core.security import require_admin_role, require_api_access

LegacyRequestModel = TypeVar("LegacyRequestModel", bound=BaseModel)
LEGACY_CONNECTOR_RETIRED_DETAIL = {
    "code": "legacy_connection_operation_retired",
    "message": "This legacy connection operation is retired.",
}


def legacy_connector_compat_enabled(request: Request) -> bool:
    settings = request.app.state.settings
    environment = str(settings.app_env).strip().lower()
    return environment in {"development", "test"} and bool(settings.telemetry_legacy_compat_enabled)


def require_legacy_connector_compatibility(request: Request) -> None:
    """Fail closed before FastAPI parses any legacy connector request body."""
    if not legacy_connector_compat_enabled(request):
        raise HTTPException(status_code=410, detail=LEGACY_CONNECTOR_RETIRED_DETAIL)


router = APIRouter(
    tags=["connectors"],
    dependencies=[
        Depends(require_api_access),
        Depends(require_admin_role),
        Depends(require_legacy_connector_compatibility),
    ],
)


async def parse_legacy_request(request: Request, model: type[LegacyRequestModel]) -> LegacyRequestModel:
    try:
        return model.model_validate(await request.json())
    except ValidationError as error:
        raise RequestValidationError(error.errors()) from None
    except (JSONDecodeError, UnicodeDecodeError):
        raise RequestValidationError(
            [{"type": "json_invalid", "loc": ("body",), "msg": "Invalid JSON body.", "input": None}]
        ) from None


@router.get("/connectors/types")
def read_connector_types() -> dict[str, Any]:
    return {"types": [descriptor.model_dump() for descriptor in build_connector_descriptors()]}


@router.post("/connectors/test")
async def test_connector(request: Request) -> Any:
    payload = await parse_legacy_request(request, ConnectorTestRequest)
    connector = build_connector_instance(payload.connector_type, payload.config)
    validation_result = connector.validate_connection()
    health = connector.health_check()
    if validation_result.get("ok") is False:
        if payload.connector_type == "database":
            update_runtime_health(
                request,
                failed_database_health(connector, validation_result.get("message", "Connector validation failed.")),
            )
        raise HTTPException(status_code=400, detail=validation_result.get("message", "Connector validation failed."))

    update_runtime_health(request, health)
    return ConnectorActionResponse(
        connector_type=payload.connector_type,
        message=validation_result.get("message", "Connector access confirmed."),
        connection_status=health.connection_status,
        last_sync_time=health.last_sync_time,
        sensors_detected=health.sensors_detected,
        records_ingested=health.records_ingested,
        warnings=health.warnings,
        errors=health.errors,
        masked_configuration=health.masked_configuration,
    ).model_dump()


@router.post("/connectors/csv/upload")
async def upload_csv_connector(
    request: Request,
    file: UploadFile = File(...),
    source_id: str = Form("customer-csv", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
    system_id: str = Form("facility-csv", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
) -> dict[str, Any]:
    filename = validate_csv_upload_filename(file.filename)
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only CSV files are supported for the CSV connector.")

    content = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_CONNECTOR_RESPONSE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"CSV connector upload exceeds the {MAX_CONNECTOR_RESPONSE_BYTES}-byte limit.",
            )
    content_bytes = bytes(content)
    if not content_bytes:
        raise HTTPException(status_code=400, detail="CSV dataset is empty.")

    connector = build_connector_instance(
        "csv",
        {
            "filename": filename,
            "content": content_bytes.decode("utf-8", errors="replace"),
            "source_id": source_id,
            "system_id": system_id,
        },
    )
    batch = normalize_or_fail(connector)
    health = ConnectorHealthStatus(
        connector_type="csv",
        display_name=connector.display_name,
        functional=True,
        connection_status="ready",
        last_sync_time=batch.last_sync_time,
        sensors_detected=batch.sensor_count,
        records_ingested=batch.record_count,
        warnings=batch.warnings,
        errors=[issue.message for issue in batch.errors[:8]],
        masked_configuration={"filename": filename, "source_id": source_id, "system_id": system_id},
    )
    update_runtime_health(request, health)
    return build_action_response(batch, health, "CSV dataset prepared for analysis.")


@router.post("/connectors/rest/test")
async def test_rest_connector(request: Request) -> dict[str, Any]:
    payload = await parse_legacy_request(request, RestConnectorRequest)
    connector = build_connector_instance("rest", payload.model_dump())
    try:
        validation_result = connector.validate_connection()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    health = connector.health_check()
    if validation_result.get("ok") is False:
        raise HTTPException(status_code=400, detail=validation_result.get("message", "REST connector validation failed."))
    update_runtime_health(request, health)
    return ConnectorActionResponse(
        connector_type="rest",
        message=validation_result.get("message", "REST API access confirmed."),
        connection_status=health.connection_status,
        last_sync_time=health.last_sync_time,
        sensors_detected=health.sensors_detected,
        records_ingested=health.records_ingested,
        warnings=health.warnings,
        errors=health.errors,
        masked_configuration=health.masked_configuration,
    ).model_dump()


@router.post("/connectors/rest/ingest")
async def ingest_rest_connector(request: Request) -> Any:
    payload = await parse_legacy_request(request, RestConnectorRequest)
    connector = build_connector_instance("rest", payload.model_dump())
    batch = normalize_or_fail(connector)
    health = ConnectorHealthStatus(
        connector_type="rest",
        display_name=connector.display_name,
        functional=True,
        connection_status="ready",
        last_sync_time=batch.last_sync_time,
        sensors_detected=batch.sensor_count,
        records_ingested=batch.record_count,
        warnings=batch.warnings,
        errors=[issue.message for issue in batch.errors[:8]],
        masked_configuration=connector.health_check().masked_configuration,
    )
    update_runtime_health(request, health)
    return build_action_response(batch, health, "REST telemetry sample prepared for analysis.")


@router.post("/connectors/database/test")
async def test_database_connector(request: Request) -> dict[str, Any]:
    payload = await parse_legacy_request(request, DatabaseConnectorRequest)
    connector = build_connector_instance("database", payload.model_dump())
    validation_result = connector.validate_connection()
    health = connector.health_check()
    if validation_result.get("ok") is False:
        message = validation_result.get("message", "Database connector validation failed.")
        update_runtime_health(request, failed_database_health(connector, message))
        raise HTTPException(status_code=400, detail=message)
    update_runtime_health(request, health)
    return ConnectorActionResponse(
        connector_type="database",
        message=validation_result.get("message", "Database access confirmed."),
        connection_status=health.connection_status,
        masked_configuration=health.masked_configuration,
    ).model_dump()


@router.post("/connectors/database/ingest")
async def ingest_database_connector(request: Request) -> Any:
    payload = await parse_legacy_request(request, DatabaseConnectorRequest)
    connector = build_connector_instance("database", payload.model_dump())
    try:
        batch = normalize_or_fail(connector)
    except HTTPException as exc:
        update_runtime_health(request, failed_database_health(connector, str(exc.detail)))
        raise
    health = ConnectorHealthStatus(
        connector_type="database",
        display_name=connector.display_name,
        functional=True,
        connection_status="ready",
        last_sync_time=batch.last_sync_time,
        sensors_detected=batch.sensor_count,
        records_ingested=batch.record_count,
        warnings=batch.warnings,
        errors=[issue.message for issue in batch.errors[:8]],
        masked_configuration=connector.health_check().masked_configuration,
    )
    update_runtime_health(request, health)
    return build_action_response(batch, health, "Database telemetry sample prepared for analysis.")


@router.get("/connectors/health")
def read_connectors_health(request: Request) -> dict[str, Any]:
    stored = connector_health_store_from_request(request).read().get("connectors", {})
    statuses: list[dict[str, Any]] = []
    for descriptor in build_connector_descriptors():
        connector = build_connector_instance(descriptor.connector_type, {})
        current = connector.health_check().model_dump()
        if descriptor.connector_type in stored:
            current.update(stored[descriptor.connector_type])
        current["connector_type"] = descriptor.connector_type
        current["display_name"] = descriptor.display_name
        current["functional"] = descriptor.functional
        statuses.append(current)
    return {"connectors": statuses}


def build_connector_instance(connector_type: str, config: dict[str, Any]) -> Any:
    if connector_type not in CONNECTOR_CLASSES:
        raise HTTPException(status_code=404, detail=f"Connector type {connector_type} is not supported.")
    return get_connector(connector_type, config)


def normalize_or_fail(connector: Any) -> Any:
    try:
        raw_data = connector.fetch_historical()
        return connector.normalize(raw_data)
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file could not be decoded as UTF-8.") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


def failed_database_health(connector: Any, message: str) -> ConnectorHealthStatus:
    health = connector.health_check()
    health.connection_status = "offline"
    health.errors = [message]
    return health


def build_action_response(batch: Any, health: ConnectorHealthStatus, message: str) -> dict[str, Any]:
    return ConnectorActionResponse(
        connector_type=batch.connector_type,
        message=message,
        connection_status=health.connection_status,
        last_sync_time=batch.last_sync_time,
        sensors_detected=batch.sensor_count,
        records_ingested=batch.record_count,
        warnings=batch.warnings,
        errors=[issue.message for issue in batch.errors[:8]],
        masked_configuration=health.masked_configuration,
        normalized_preview=batch.records[:6],
    ).model_dump()


def connector_health_store_from_request(request: Request) -> ConnectorHealthStore:
    store = request.app.state.connector_health_store
    if not isinstance(store, ConnectorHealthStore):
        raise RuntimeError("Connector health store is not configured.")
    return store


def update_runtime_health(request: Request, health: ConnectorHealthStatus) -> None:
    connector_health_store_from_request(request).upsert(health)


def validate_csv_upload_filename(filename: str | None) -> str:
    value = filename or "telemetry.csv"
    decoded = value
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value

    if len(value) > 255 or len(decoded) > 255:
        raise HTTPException(status_code=400, detail="Filename must not exceed 255 characters.")
    if (
        not decoded
        or decoded in {".", ".."}
        or "\x00" in decoded
        or any(ord(character) < 32 for character in decoded)
        or "/" in decoded
        or "\\" in decoded
        or bool(PureWindowsPath(decoded).drive)
    ):
        raise HTTPException(status_code=400, detail="Filename must be a plain file name.")
    return value
