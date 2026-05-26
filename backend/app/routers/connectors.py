from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.connectors.models import ConnectorActionResponse, ConnectorHealthStatus, ConnectorTestRequest, RestConnectorRequest
from app.connectors.registry import CONNECTOR_CLASSES, build_connector_descriptors, get_connector
from app.connectors.store import read_health_state, upsert_health_status
from app.core.security import require_api_access

router = APIRouter(tags=["connectors"], dependencies=[Depends(require_api_access)])


@router.get("/connectors/types")
def read_connector_types() -> dict[str, Any]:
    return {"types": [descriptor.model_dump() for descriptor in build_connector_descriptors()]}


@router.post("/connectors/test")
def test_connector(request: Request, payload: ConnectorTestRequest) -> dict[str, Any]:
    connector = build_connector_instance(payload.connector_type, payload.config)
    validation_result = connector.validate_connection()
    health = connector.health_check()
    if validation_result.get("ok") is False:
        raise HTTPException(status_code=400, detail=validation_result.get("message", "Connector validation failed."))

    update_runtime_health(request, health)
    return ConnectorActionResponse(
        connector_type=payload.connector_type,
        message=validation_result.get("message", "Connector validated."),
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
    source_id: str = Form("customer-csv"),
    system_id: str = Form("facility-csv"),
) -> dict[str, Any]:
    filename = file.filename or "telemetry.csv"
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only CSV files are supported for the CSV connector.")

    content_bytes = await file.read()
    if not content_bytes:
        raise HTTPException(status_code=400, detail="CSV dataset is empty.")

    connector = build_connector_instance(
        "csv",
        {
            "filename": filename,
            "content": content_bytes.decode("utf-8", errors="replace")
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
    return build_action_response(batch, health, "CSV telemetry normalized and ready for engine ingestion.")


@router.post("/connectors/rest/test")
def test_rest_connector(request: Request, payload: RestConnectorRequest) -> dict[str, Any]:
    connector = build_connector_instance("rest", payload.model_dump())
    validation_result = connector.validate_connection()
    health = connector.health_check()
    if validation_result.get("ok") is False:
        raise HTTPException(status_code=400, detail=validation_result.get("message", "REST connector validation failed."))
    update_runtime_health(request, health)
    return ConnectorActionResponse(
        connector_type="rest",
        message=validation_result.get("message", "REST connector validated."),
        connection_status=health.connection_status,
        last_sync_time=health.last_sync_time,
        sensors_detected=health.sensors_detected,
        records_ingested=health.records_ingested,
        warnings=health.warnings,
        errors=health.errors,
        masked_configuration=health.masked_configuration,
    ).model_dump()


@router.post("/connectors/rest/ingest")
def ingest_rest_connector(request: Request, payload: RestConnectorRequest) -> dict[str, Any]:
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
    return build_action_response(batch, health, "REST telemetry normalized and ready for engine ingestion.")


@router.get("/connectors/health")
def read_connectors_health(request: Request) -> dict[str, Any]:
    stored = read_health_state(runtime_dir_from_request(request)).get("connectors", {})
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


def runtime_dir_from_request(request: Request) -> Path:
    return request.app.state.settings.runtime_dir


def update_runtime_health(request: Request, health: ConnectorHealthStatus) -> None:
    upsert_health_status(runtime_dir_from_request(request), health)
