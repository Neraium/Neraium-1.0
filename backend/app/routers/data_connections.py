from __future__ import annotations

import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path

from app.core.security import require_admin_role, require_api_access, require_operator_role
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

router = APIRouter(tags=["data-connections"], dependencies=[Depends(require_api_access)])
logger = logging.getLogger(__name__)

ConnectionIdPath = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]


def _safe_connection_message(value: Any, fallback: str) -> str:
    message = str(value or "").strip()
    if not message:
        return fallback
    if re.search(r"traceback|stack trace|exception|localhost|/api/|\b(?:sql|python|uvicorn|psycopg|sqlite|errno)\b|[a-z]:\\", message, re.IGNORECASE):
        return fallback
    return message


@router.get("/data-connections", response_model=DataConnectionsListResponse)
def read_data_connections() -> dict[str, Any]:
    return {"connections": list_registered_data_connections()}


@router.post("/data-connections", response_model=DataConnectionActionResponse, dependencies=[Depends(require_admin_role)])
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


@router.post("/data-connections/{connection_id}/test", response_model=DataConnectionActionResponse, dependencies=[Depends(require_operator_role)])
def test_registered_data_connection(connection_id: ConnectionIdPath) -> dict[str, Any]:
    try:
        existing_connection = read_connection_status(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    try:
        result = test_data_connection(connection_id)
    except Exception as exc:
        message = _safe_connection_message(exc, "The connector did not return usable telemetry. Check its settings and retry.")
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


@router.post("/data-connections/{connection_id}/start", response_model=DataConnectionActionResponse, dependencies=[Depends(require_admin_role)])
def start_data_connection(connection_id: ConnectionIdPath) -> dict[str, Any]:
    try:
        connection = set_connection_polling(connection_id, enabled=True)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"connection": connection, "message": f"Continuous ingestion started for {connection['name']}."}


@router.post("/data-connections/{connection_id}/stop", response_model=DataConnectionActionResponse, dependencies=[Depends(require_admin_role)])
def stop_data_connection(connection_id: ConnectionIdPath) -> dict[str, Any]:
    try:
        connection = set_connection_polling(connection_id, enabled=False)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"connection": connection, "message": f"Continuous ingestion stopped for {connection['name']}."}


@router.post("/data-connections/{connection_id}/poll-once", response_model=DataConnectionActionResponse, dependencies=[Depends(require_operator_role)])
def poll_data_connection(connection_id: ConnectionIdPath) -> dict[str, Any]:
    try:
        result = poll_data_connection_once(connection_id, actor="operator:poll-once")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    message = (
        _safe_connection_message(result.get("error"), "The connector check did not return usable telemetry. Check its settings and retry.")
        if result.get("error") else f"Checked {result['connection']['name']}."
    )
    return {
        "connection": result["connection"],
        "message": message,
        "latest_result": result.get("latest_result"),
        "meaningful_change": result.get("meaningful_change"),
    }


@router.post("/data-connections/{connection_id}/reset-baseline", response_model=DataConnectionActionResponse, dependencies=[Depends(require_admin_role)])
def reset_data_connection_baseline(connection_id: ConnectionIdPath) -> dict[str, Any]:
    try:
        connection = reset_connection_live_baseline(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {
        "connection": connection,
        "message": f"Live baseline reset for {connection['name']}. Polling will rebuild it from new telemetry.",
    }


@router.post("/data-connections/reset-all", response_model=DataConnectionsBulkActionResponse, dependencies=[Depends(require_admin_role)])
def reset_all_connections() -> dict[str, Any]:
    connections = reset_all_data_connections()
    return {
        "connections": connections,
        "message": "All telemetry connections were reset and active telemetry state was cleared.",
    }


@router.get("/data-connections/{connection_id}/status", response_model=DataConnectionResponse)
def read_data_connection_status(connection_id: ConnectionIdPath) -> dict[str, Any]:
    try:
        return read_connection_status(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
