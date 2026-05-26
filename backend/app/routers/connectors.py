from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.models.connector_models import ConnectorHealthStatus, ConnectorTestRequest
from app.services.connector_registry import build_connector_instance, normalize_or_fail
from app.services.runtime_db import append_connector_health

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.post("/test")
def test_connector(request: Request, payload: ConnectorTestRequest) -> dict[str, Any]:
    connector = build_connector_instance(payload.connector_type, payload.configuration)
    batch = normalize_or_fail(connector)
    health = ConnectorHealthStatus(
        connector_type=payload.connector_type,
        display_name=connector.display_name,
        functional=True,
        connection_status="ready",
        last_sync_time=batch.last_sync_time,
        sensors_detected=batch.sensor_count,
        records_ingested=batch.record_count,
        warnings=batch.warnings,
        errors=batch.errors,
        masked_configuration=connector.masked_configuration(),
    )
    append_connector_health(health)
    return health.model_dump()


@router.post("/csv/upload")
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
        errors=batch.errors,
        masked_configuration=connector.masked_configuration(),
    )
    append_connector_health(health)
    return health.model_dump()
