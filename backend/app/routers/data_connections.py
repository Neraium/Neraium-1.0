from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_api_access
from app.models.api_models import (
    DataConnectionActionResponse,
    DataConnectionsListResponse,
    DataConnectionResponse,
    DataConnectionUpsertRequest,
)
from app.services.data_connections import (
    list_registered_data_connections,
    poll_data_connection_once,
    read_connection_status,
    reset_connection_live_baseline,
    set_connection_polling,
    test_data_connection,
    upsert_registered_data_connection,
)

router = APIRouter(tags=["data-connections"], dependencies=[Depends(require_api_access)])


@router.get("/data-connections", response_model=DataConnectionsListResponse)
def read_data_connections() -> dict[str, Any]:
    return {"connections": list_registered_data_connections()}


@router.post("/data-connections", response_model=DataConnectionActionResponse)
def create_or_update_data_connection(payload: DataConnectionUpsertRequest) -> dict[str, Any]:
    connection_id = payload.connection_id or "node-red-cultivation-telemetry"
    connection = upsert_registered_data_connection(
        {
            "connection_id": connection_id,
            **payload.model_dump(exclude={"connection_id"}),
            "status": "polling" if payload.polling_enabled else "offline",
        }
    )
    return {"connection": connection, "message": f"{connection['name']} saved."}


@router.post("/data-connections/{connection_id}/test", response_model=DataConnectionActionResponse)
def test_registered_data_connection(connection_id: str) -> dict[str, Any]:
    try:
        result = test_data_connection(connection_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
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


@router.get("/data-connections/{connection_id}/status", response_model=DataConnectionResponse)
def read_data_connection_status(connection_id: str) -> dict[str, Any]:
    try:
        return read_connection_status(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
