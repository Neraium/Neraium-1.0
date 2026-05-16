from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_api_access
from app.models.api_models import (
    DataConnectionActionResponse,
    DataConnectionsBulkActionResponse,
    DataConnectionsListResponse,
    DataConnectionResponse,
    DataConnectionUpsertRequest,
)
from app.services.data_connections import (
    list_registered_data_connections,
    poll_data_connection_once,
    read_connection_status,
    reset_all_data_connections,
    reset_connection_live_baseline,
    set_connection_polling,
    test_data_connection,
    upsert_registered_data_connection,
)
from app.services.upload_jobs import latest_completed_job_summary

router = APIRouter(tags=["data-connections"], dependencies=[Depends(require_api_access)])
logger = logging.getLogger(__name__)


def enrich_connections_with_uploaded_telemetry(connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the UI from treating uploaded telemetry as if no data exists.

    File uploads are not the same thing as a live telemetry stream, but once a
    completed upload exists the customer UI should say an imported telemetry
    source is active instead of showing contradictory "awaiting telemetry" copy.
    """
    summary = latest_completed_job_summary()
    if not summary:
        return connections

    enriched: list[dict[str, Any]] = []
    for index, connection in enumerate(connections):
        next_connection = {**connection}
        if index == 0 or next_connection.get("connection_id") == "rest-telemetry-intake":
            next_connection.setdefault("last_success_at", summary.get("last_processed_at"))
            next_connection.setdefault("last_poll_at", summary.get("last_processed_at"))
            next_connection.setdefault("latest_telemetry_timestamp", summary.get("last_processed_at"))
            next_connection["current_scenario"] = next_connection.get("current_scenario") or "Monitoring uploaded telemetry"
            next_connection["last_ingestion_source"] = next_connection.get("last_ingestion_source") or "file_upload"
            next_connection["baseline_source"] = next_connection.get("baseline_source") or "uploaded_file"
            next_connection["baseline_status"] = next_connection.get("baseline_status") or "active"
            next_connection["baseline_samples_collected"] = next_connection.get("baseline_samples_collected") or summary.get("rows_processed", 0)
            next_connection["baseline_samples_required"] = next_connection.get("baseline_samples_required") or summary.get("rows_processed", 0)
            next_connection["last_baseline_update"] = next_connection.get("last_baseline_update") or summary.get("last_processed_at")
            next_connection["readings_received"] = max(next_connection.get("readings_received", 0), summary.get("rows_processed", 0) or 0)
            next_connection["readings_accepted"] = max(next_connection.get("readings_accepted", 0), summary.get("rows_processed", 0) or 0)
            next_connection["sensors_detected"] = max(next_connection.get("sensors_detected", 0), summary.get("columns_detected", 0) or 0)
            if next_connection.get("status") in {None, "offline", "error"}:
                next_connection["status"] = "online"
        enriched.append(next_connection)
    return enriched


@router.get("/data-connections", response_model=DataConnectionsListResponse)
def read_data_connections() -> dict[str, Any]:
    return {"connections": enrich_connections_with_uploaded_telemetry(list_registered_data_connections())}


@router.post("/data-connections", response_model=DataConnectionActionResponse)
def create_or_update_data_connection(payload: DataConnectionUpsertRequest) -> dict[str, Any]:
    connection_id = payload.connection_id or "rest-telemetry-intake"
    try:
        connection = upsert_registered_data_connection(
            {
                "connection_id": connection_id,
                **payload.model_dump(exclude={"connection_id"}),
                "status": "polling" if payload.polling_enabled else "offline",
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"connection": connection, "message": f"{connection['name']} saved."}


@router.post("/data-connections/{connection_id}/test", response_model=DataConnectionActionResponse)
def test_registered_data_connection(connection_id: str) -> dict[str, Any]:
    try:
        existing_connection = read_connection_status(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    try:
        result = test_data_connection(connection_id)
    except Exception as exc:
        message = str(exc) or "Telemetry source did not return usable readings."
        connection = {**existing_connection}
        connection.update(
            {
                "status": "error",
                "error_message": message,
                "readings_received": connection.get("readings_received", 0),
                "readings_accepted": connection.get("readings_accepted", 0),
                "readings_rejected": connection.get("readings_rejected", 0),
                "sensors_detected": connection.get("sensors_detected", 0),
            }
        )
        connection = upsert_registered_data_connection(connection)
        logger.warning("data_connection_test_failed connection_id=%s error=%s", connection_id, message)
        return {
            "connection": connection,
            "message": message,
            "normalized_preview": [],
            "latest_result": None,
            "meaningful_change": False,
        }
    return {
        "connection": result["connection"],
        "message": f"{result['connection']['name']} responded with valid telemetry.",
        "normalized_preview": result["normalized_preview"],
    }


@router.post("/data-connections/{connection_id}/start", response_model=DataConnectionActionResponse)
def start_data_connection(connection_id: str) -> dict[str, Any]:
    try:
        connection = set_connection_polling(connection_id, enabled=True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"connection": connection, "message": f"Started polling {connection['name']}."}


@router.post("/data-connections/{connection_id}/stop", response_model=DataConnectionActionResponse)
def stop_data_connection(connection_id: str) -> dict[str, Any]:
    try:
        connection = set_connection_polling(connection_id, enabled=False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"connection": connection, "message": f"Stopped polling {connection['name']}."}


@router.post("/data-connections/{connection_id}/poll-once", response_model=DataConnectionActionResponse)
def poll_data_connection(connection_id: str) -> dict[str, Any]:
    try:
        result = poll_data_connection_once(connection_id, actor="operator:poll-once")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    message = (
        result.get("error")
        or f"Polled {result['connection']['name']}."
    )
    return {
        "connection": result["connection"],
        "message": message,
        "latest_result": result.get("latest_result"),
        "meaningful_change": result.get("meaningful_change"),
    }


@router.post("/data-connections/{connection_id}/reset-baseline", response_model=DataConnectionActionResponse)
def reset_data_connection_baseline(connection_id: str) -> dict[str, Any]:
    try:
        connection = reset_connection_live_baseline(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {
        "connection": connection,
        "message": f"Live baseline reset for {connection['name']}. Polling will rebuild it from new telemetry.",
    }


@router.post("/data-connections/reset-all", response_model=DataConnectionsBulkActionResponse)
def reset_all_connections() -> dict[str, Any]:
    connections = reset_all_data_connections()
    return {
        "connections": connections,
        "message": "All telemetry connections were reset and active telemetry state was cleared.",
    }


@router.get("/data-connections/{connection_id}/status", response_model=DataConnectionResponse)
def read_data_connection_status(connection_id: str) -> dict[str, Any]:
    try:
        return read_connection_status(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
