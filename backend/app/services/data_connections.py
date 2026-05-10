from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.connectors.models import NormalizedTelemetryRecord
from app.core.config import Settings, get_settings
from app.services.evidence_store import digest_payload, upsert_evidence_run
from app.services.runtime_db import (
    list_data_connections,
    read_data_connection,
    read_latest_payload,
    upsert_data_connection,
    upsert_latest_payload,
)
from app.services.upload_jobs import (
    build_upload_result,
    read_latest_upload_result,
    summarize_result,
    write_latest_upload_result,
    write_latest_upload_summary,
)


logger = logging.getLogger(__name__)
DEFAULT_CONNECTION_ID = "node-red-cultivation-telemetry"
DEFAULT_CONNECTION_NAME = "Node-RED Cultivation Telemetry"
DEFAULT_CONNECTION_URL = "http://18.216.253.180:1880/telemetry/latest"
DEFAULT_POLLING_INTERVAL_SECONDS = 5
MAX_BUFFER_RECORDS = 2048
MEANINGFUL_STATE_KEYS = ("neraium_score", "operating_state", "primary_room", "drift_status", "primary_driver")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def default_connection_payload(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    return {
        "connection_id": DEFAULT_CONNECTION_ID,
        "name": DEFAULT_CONNECTION_NAME,
        "url": DEFAULT_CONNECTION_URL,
        "source_type": "external_rest_api",
        "facility_id": "cultivation-facility-001",
        "room_id": "flower-room-1",
        "polling_enabled": settings.app_env == "development",
        "polling_interval_seconds": DEFAULT_POLLING_INTERVAL_SECONDS,
        "last_poll_at": None,
        "last_success_at": None,
        "status": "polling" if settings.app_env == "development" else "offline",
        "error_message": "",
        "readings_received": 0,
        "readings_accepted": 0,
        "readings_rejected": 0,
        "sensors_detected": 0,
        "current_scenario": None,
        "current_tick": None,
        "latest_telemetry_timestamp": None,
        "last_ingestion_source": None,
        "masked_configuration": {"url": DEFAULT_CONNECTION_URL},
    }


def ensure_default_data_connection(settings: Settings | None = None) -> dict[str, Any]:
    existing = read_data_connection(DEFAULT_CONNECTION_ID)
    if existing:
        return existing
    payload = default_connection_payload(settings)
    upsert_data_connection(payload)
    return payload


def list_registered_data_connections() -> list[dict[str, Any]]:
    ensure_default_data_connection()
    return list_data_connections(limit=100)


def upsert_registered_data_connection(payload: dict[str, Any]) -> dict[str, Any]:
    current = read_data_connection(payload.get("connection_id", "")) or {}
    merged = {
        **default_connection_payload(),
        **current,
        **payload,
    }
    merged["masked_configuration"] = {"url": merged.get("url")}
    merged["status"] = merged.get("status") or ("polling" if merged.get("polling_enabled") else "offline")
    merged["error_message"] = merged.get("error_message") or ""
    upsert_data_connection(merged)
    return merged


def set_connection_polling(connection_id: str, *, enabled: bool) -> dict[str, Any]:
    connection = require_connection(connection_id)
    connection["polling_enabled"] = enabled
    connection["status"] = "polling" if enabled else "offline"
    connection["error_message"] = ""
    return upsert_registered_data_connection(connection)


def require_connection(connection_id: str) -> dict[str, Any]:
    ensure_default_data_connection()
    connection = read_data_connection(connection_id)
    if connection is None:
        raise ValueError(f"Data connection {connection_id} was not found.")
    return connection


def read_connection_status(connection_id: str) -> dict[str, Any]:
    return require_connection(connection_id)


def is_connection_due(connection: dict[str, Any], current_time: datetime | None = None) -> bool:
    if not connection.get("polling_enabled"):
        return False
    current_time = current_time or datetime.now(UTC)
    interval = max(int(connection.get("polling_interval_seconds") or DEFAULT_POLLING_INTERVAL_SECONDS), 1)
    last_poll_at = parse_iso(connection.get("last_poll_at"))
    if last_poll_at is None:
        return True
    return (current_time - last_poll_at).total_seconds() >= interval


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_external_rest_payload(payload: dict[str, Any], connection: dict[str, Any]) -> tuple[list[NormalizedTelemetryRecord], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("External telemetry response must be a JSON object.")
    readings = payload.get("readings")
    if not isinstance(readings, list) or not readings:
        raise ValueError("External telemetry response did not include any readings.")

    source_id = str(payload.get("source_id") or connection.get("connection_id"))
    facility_id = str(payload.get("facility_id") or connection.get("facility_id") or "unknown-facility")
    room_id = str(payload.get("room_id") or connection.get("room_id") or "unknown-room")
    scenario = payload.get("scenario")
    tick = payload.get("tick")
    external_source_url = connection.get("url")
    normalized: list[NormalizedTelemetryRecord] = []
    rejected = 0

    for item in readings:
        if not isinstance(item, dict):
            rejected += 1
            continue
        sensor_id = item.get("sensor_id")
        sensor_name = item.get("sensor_name")
        raw_value = item.get("value")
        timestamp = item.get("timestamp") or payload.get("timestamp")
        if not sensor_id or not sensor_name or raw_value is None or not timestamp:
            rejected += 1
            continue
        try:
            numeric_value = float(raw_value)
        except (TypeError, ValueError):
            rejected += 1
            continue
        normalized.append(
            NormalizedTelemetryRecord(
                source_id=source_id,
                facility_id=facility_id,
                room_id=room_id,
                system_id=facility_id,
                sensor_id=str(sensor_id),
                sensor_name=str(sensor_name),
                value=numeric_value,
                unit=str(item.get("unit") or "").strip().lower(),
                timestamp=str(timestamp),
                quality_status=str(item.get("quality") or "good").strip().lower() or "good",
                metadata={
                    "scenario": scenario,
                    "tick": tick,
                    "external_source_url": external_source_url,
                    "ingestion_type": "rest_poll",
                    "source_type": payload.get("source_type") or connection.get("source_type"),
                },
            )
        )

    if not normalized:
        raise ValueError("External telemetry did not contain any valid readings.")

    return normalized, {
        "scenario": scenario,
        "tick": tick,
        "source_id": source_id,
        "facility_id": facility_id,
        "room_id": room_id,
        "timestamp": payload.get("timestamp"),
        "source_type": payload.get("source_type") or connection.get("source_type"),
        "external_source_url": external_source_url,
        "readings_received": len(readings),
        "readings_accepted": len(normalized),
        "readings_rejected": rejected,
        "sensors_detected": len({record.sensor_id for record in normalized}),
    }


def records_buffer_key(connection_id: str) -> str:
    return f"data_connection_buffer:{connection_id}"


def state_fingerprint_key(connection_id: str) -> str:
    return f"data_connection_last_fingerprint:{connection_id}"


def read_connection_buffer(connection_id: str) -> list[dict[str, Any]]:
    payload = read_latest_payload(records_buffer_key(connection_id))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def write_connection_buffer(connection_id: str, records: list[dict[str, Any]]) -> None:
    upsert_latest_payload(records_buffer_key(connection_id), records[-MAX_BUFFER_RECORDS:])


def append_connection_buffer(connection_id: str, records: list[NormalizedTelemetryRecord]) -> list[dict[str, Any]]:
    existing = read_connection_buffer(connection_id)
    serialized = [record.model_dump() for record in records]
    combined = existing + serialized
    combined.sort(key=lambda item: (item.get("timestamp") or "", item.get("sensor_id") or ""))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in combined:
        key = (
            str(item.get("timestamp") or ""),
            str(item.get("room_id") or ""),
            str(item.get("sensor_id") or ""),
            str(item.get("value") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    write_connection_buffer(connection_id, deduped)
    return deduped[-MAX_BUFFER_RECORDS:]


def build_rows_from_normalized_records(records: list[dict[str, Any]]) -> tuple[list[str], list[list[str]], dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(dict)
    sensor_names: set[str] = set()
    room_counts: dict[str, int] = defaultdict(int)

    for item in records:
        timestamp = str(item.get("timestamp") or "")
        room_id = str(item.get("room_id") or item.get("metadata", {}).get("room_id") or "Current room")
        facility_id = str(item.get("facility_id") or item.get("system_id") or "Current facility")
        sensor_name = str(item.get("sensor_name") or item.get("sensor_id") or "sensor")
        grouped[(timestamp, room_id, facility_id)][sensor_name] = item.get("value")
        room_counts[room_id] += 1
        sensor_names.add(sensor_name)

    ordered_sensors = sorted(sensor_names)
    columns = ["timestamp", "room", "facility_id", *ordered_sensors]
    rows: list[list[str]] = []
    for (timestamp, room_id, facility_id), values in sorted(grouped.items(), key=lambda item: item[0][0]):
        rows.append(
            [
                timestamp,
                room_id,
                facility_id,
                *[
                    "" if values.get(sensor_name) is None else str(values.get(sensor_name))
                    for sensor_name in ordered_sensors
                ],
            ]
        )

    room_summary = {
        "room_count": len(room_counts),
        "rooms": [
            {"room": room, "row_count": count}
            for room, count in sorted(room_counts.items(), key=lambda item: (-item[1], item[0].lower()))
        ],
        "total_rows": len(rows),
        "unassigned_rows": 0,
    }
    return columns, rows, room_summary


def result_from_connection_batch(connection: dict[str, Any], normalized_records: list[NormalizedTelemetryRecord], metadata: dict[str, Any]) -> dict[str, Any]:
    buffer = append_connection_buffer(connection["connection_id"], normalized_records)
    columns, rows, room_summary = build_rows_from_normalized_records(buffer)
    result = build_upload_result(
        columns=columns,
        data_rows=rows,
        total_rows=len(rows),
        filename=connection["name"],
        processing_stats={
            "chunk_count": 1 if rows else 0,
            "sampled_rows": len(rows),
            "sii_sampled_rows": len(rows),
            "memory_estimate_bytes": sum(sum(len(cell) for cell in row) + len(row) * 8 for row in rows),
            "used_streaming": False,
            "engine_runtime_seconds": 0,
            "room_summary": room_summary,
            "record_count": metadata.get("readings_received", 0),
            "accepted_record_count": metadata.get("readings_accepted", 0),
            "rejected_record_count": metadata.get("readings_rejected", 0),
            "sensors_detected": metadata.get("sensors_detected", 0),
        },
        intelligence_source="rest_poll",
        intelligence_mode="live",
        intelligence_source_metadata=metadata,
    )
    result["source_name"] = connection["name"]
    result["source_url"] = connection["url"]
    result["source_type"] = connection["source_type"]
    result["connection_id"] = connection["connection_id"]
    result["ingestion_metadata"] = metadata
    result["filename"] = connection["name"]
    result["processing_stats"]["record_count"] = metadata.get("readings_received", 0)
    result["processing_stats"]["accepted_record_count"] = metadata.get("readings_accepted", 0)
    result["processing_stats"]["rejected_record_count"] = metadata.get("readings_rejected", 0)
    result["processing_stats"]["sensors_detected"] = metadata.get("sensors_detected", 0)
    result["sii_intelligence"]["source"] = "rest_poll"
    result["sii_intelligence"]["source_metadata"] = metadata
    return result


def summarize_connection_result(connection: dict[str, Any], result: dict[str, Any], completed_at: str, metadata: dict[str, Any]) -> dict[str, Any]:
    summary = summarize_result(result, completed_at)
    summary["filename"] = connection["name"]
    summary["source"] = "rest_poll"
    summary["upload_result_source"] = "rest_poll"
    summary["source_name"] = connection["name"]
    summary["source_url"] = connection["url"]
    summary["connection_id"] = connection["connection_id"]
    summary["facility_id"] = metadata.get("facility_id")
    summary["room_id"] = metadata.get("room_id")
    summary["scenario"] = metadata.get("scenario")
    summary["tick"] = metadata.get("tick")
    summary["latest_telemetry_timestamp"] = metadata.get("timestamp")
    summary["readings_received"] = metadata.get("readings_received", 0)
    summary["readings_accepted"] = metadata.get("readings_accepted", 0)
    summary["readings_rejected"] = metadata.get("readings_rejected", 0)
    summary["sensors_detected"] = metadata.get("sensors_detected", 0)
    summary["primary_driver"] = result.get("sii_intelligence", {}).get("primary_driver")
    return summary


def current_state_fingerprint(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: summary.get(key) for key in MEANINGFUL_STATE_KEYS}


def has_meaningful_state_change(connection_id: str, summary: dict[str, Any]) -> bool:
    previous = read_latest_payload(state_fingerprint_key(connection_id))
    current = current_state_fingerprint(summary)
    if previous != current:
        upsert_latest_payload(state_fingerprint_key(connection_id), current)
        return True
    return False


def build_connection_evidence_record(connection: dict[str, Any], result: dict[str, Any], summary: dict[str, Any], completed_at: str, metadata: dict[str, Any], *, status: str) -> dict[str, Any]:
    intelligence = result.get("sii_intelligence", {})
    return {
        "run_id": f"{connection['connection_id']}-{uuid.uuid4().hex[:10]}",
        "source_type": connection.get("source_type", "external_rest_api"),
        "source_name": connection.get("name"),
        "filename": connection.get("url"),
        "created_at": completed_at,
        "completed_at": completed_at,
        "status": status,
        "rows_received": metadata.get("readings_received", 0),
        "rows_accepted": metadata.get("readings_accepted", 0),
        "rows_rejected": metadata.get("readings_rejected", 0),
        "sensors_detected": metadata.get("sensors_detected", 0),
        "system_id": metadata.get("facility_id"),
        "room": metadata.get("room_id"),
        "operating_state": intelligence.get("facility_state"),
        "neraium_score": intelligence.get("neraium_score"),
        "drift_status": intelligence.get("urgency"),
        "primary_drivers": [intelligence.get("primary_driver")] if intelligence.get("primary_driver") else [],
        "evidence_summary": (intelligence.get("supporting_evidence") or [])[:6],
        "warnings": result.get("warnings", [])[:10],
        "errors": result.get("sii_runner_result", {}).get("errors", [])[:5],
        "input_hash": digest_payload(metadata),
        "result_hash": digest_payload(summary),
        "initiated_by": "system:rest-poller",
        "source_url": connection.get("url"),
        "scenario": metadata.get("scenario"),
        "tick": metadata.get("tick"),
    }


def build_failed_poll_evidence_record(connection: dict[str, Any], error_message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    completed_at = now_iso()
    return {
        "run_id": f"{connection['connection_id']}-failed-{uuid.uuid4().hex[:10]}",
        "source_type": connection.get("source_type", "external_rest_api"),
        "source_name": connection.get("name"),
        "filename": connection.get("url"),
        "created_at": completed_at,
        "completed_at": completed_at,
        "status": "failed",
        "rows_received": metadata.get("readings_received", 0),
        "rows_accepted": 0,
        "rows_rejected": metadata.get("readings_received", 0),
        "sensors_detected": metadata.get("sensors_detected", 0),
        "system_id": connection.get("facility_id"),
        "room": connection.get("room_id"),
        "operating_state": None,
        "neraium_score": None,
        "drift_status": None,
        "primary_drivers": [],
        "evidence_summary": [],
        "warnings": [],
        "errors": [error_message],
        "input_hash": digest_payload({"url": connection.get("url"), "timestamp": completed_at}),
        "result_hash": None,
        "initiated_by": "system:rest-poller",
        "source_url": connection.get("url"),
        "scenario": metadata.get("scenario"),
        "tick": metadata.get("tick"),
    }


def update_connection_health_fields(connection: dict[str, Any], metadata: dict[str, Any], *, status: str, error_message: str = "") -> dict[str, Any]:
    connection["status"] = status
    connection["error_message"] = error_message
    connection["last_poll_at"] = now_iso()
    if not error_message:
        connection["last_success_at"] = connection["last_poll_at"]
    connection["readings_received"] = metadata.get("readings_received", connection.get("readings_received", 0))
    connection["readings_accepted"] = metadata.get("readings_accepted", connection.get("readings_accepted", 0))
    connection["readings_rejected"] = metadata.get("readings_rejected", connection.get("readings_rejected", 0))
    connection["sensors_detected"] = metadata.get("sensors_detected", connection.get("sensors_detected", 0))
    connection["current_scenario"] = metadata.get("scenario")
    connection["current_tick"] = metadata.get("tick")
    connection["latest_telemetry_timestamp"] = metadata.get("timestamp")
    connection["last_ingestion_source"] = "rest_poll"
    return upsert_registered_data_connection(connection)


def fetch_connection_payload(connection: dict[str, Any], transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    with httpx.Client(timeout=10.0, transport=transport) as client:
        response = client.get(connection["url"], headers=headers)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("External telemetry response must be a JSON object.")
    return payload


def test_data_connection(connection_id: str, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    connection = require_connection(connection_id)
    payload = fetch_connection_payload(connection, transport=transport)
    records, metadata = normalize_external_rest_payload(payload, connection)
    tested = update_connection_health_fields(connection, metadata, status="online")
    return {
        "connection": tested,
        "normalized_preview": [record.model_dump() for record in records[:6]],
    }


def poll_data_connection_once(connection_id: str, *, transport: httpx.BaseTransport | None = None, actor: str = "system:rest-poller") -> dict[str, Any]:
    connection = require_connection(connection_id)
    last_status = connection.get("status")
    try:
        connection["last_poll_at"] = now_iso()
        upsert_registered_data_connection(connection)
        payload = fetch_connection_payload(connection, transport=transport)
        normalized_records, metadata = normalize_external_rest_payload(payload, connection)
        result = result_from_connection_batch(connection, normalized_records, metadata)
        completed_at = now_iso()
        summary = summarize_connection_result(connection, result, completed_at, metadata)
        meaningful_change = has_meaningful_state_change(connection_id, summary)
        write_latest_upload_result(connection_id, result)
        write_latest_upload_summary(connection_id, summary, append_history=meaningful_change)
        connection = update_connection_health_fields(connection, metadata, status="polling")
        logger.info(
            "data_connection_poll_complete connection_id=%s readings_received=%s readings_accepted=%s sensors_detected=%s scenario=%s tick=%s meaningful_change=%s",
            connection_id,
            metadata.get("readings_received"),
            metadata.get("readings_accepted"),
            metadata.get("sensors_detected"),
            metadata.get("scenario"),
            metadata.get("tick"),
            meaningful_change,
        )
        if meaningful_change:
            upsert_evidence_run(
                build_connection_evidence_record(connection, result, summary, completed_at, metadata, status="completed")
            )
        return {
            "connection": connection,
            "summary": summary,
            "latest_result": result,
            "meaningful_change": meaningful_change,
            "actor": actor,
        }
    except Exception as exc:
        error_message = str(exc)
        logger.warning("data_connection_poll_failed connection_id=%s error=%s", connection_id, error_message)
        failure_metadata = {
            "scenario": connection.get("current_scenario"),
            "tick": connection.get("current_tick"),
            "timestamp": connection.get("latest_telemetry_timestamp"),
            "readings_received": 0,
            "sensors_detected": connection.get("sensors_detected", 0),
        }
        connection = update_connection_health_fields(connection, failure_metadata, status="error", error_message=error_message)
        if last_status != "error":
            upsert_evidence_run(build_failed_poll_evidence_record(connection, error_message, failure_metadata))
        return {
            "connection": connection,
            "summary": None,
            "latest_result": read_latest_upload_result(),
            "meaningful_change": False,
            "actor": actor,
            "error": error_message,
        }
