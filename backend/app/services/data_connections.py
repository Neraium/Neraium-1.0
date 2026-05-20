from __future__ import annotations

import json
import logging
import os
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.connectors.models import NormalizedTelemetryRecord
from app.core.config import Settings, get_settings
from app.services.evidence_store import digest_payload, upsert_evidence_run
from app.services.runtime_db import (
    delete_data_connection,
    list_data_connections,
    read_data_connection,
    read_latest_payload,
    upsert_data_connection,
    upsert_latest_payload,
)
from app.services.upload_jobs import (
    build_upload_result,
    read_latest_upload_result,
    reset_latest_upload_state,
    summarize_result,
    write_latest_upload_result,
    write_latest_upload_summary,
)


logger = logging.getLogger(__name__)
DEFAULT_CONNECTION_ID = "rest-telemetry-intake"
DEFAULT_CONNECTION_NAME = "Live Telemetry Intake"
LEGACY_NODE_RED_CONNECTION_ID = "node-red-cultivation-telemetry"
DEFAULT_POLLING_INTERVAL_SECONDS = 5
DEFAULT_LIVE_BASELINE_SAMPLE_COUNT = 6
MAX_BUFFER_RECORDS = 2048
MAX_BASELINE_RECORDS = 512
MAX_RECENT_RECORDS = 512
MEANINGFUL_STATE_KEYS = ("neraium_score", "operating_state", "primary_room", "drift_status", "primary_driver")


class TelemetryFetchError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def default_connection_payload(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    default_connection_url = settings.default_telemetry_url
    auto_polling_enabled = False
    return {
        "connection_id": DEFAULT_CONNECTION_ID,
        "name": DEFAULT_CONNECTION_NAME,
        "url": default_connection_url,
        "source_type": "external_rest_api",
        "facility_id": "cultivation-facility-001",
        "room_id": "flower-room-1",
        "polling_enabled": auto_polling_enabled,
        "polling_interval_seconds": DEFAULT_POLLING_INTERVAL_SECONDS,
        "last_poll_at": None,
        "last_success_at": None,
        "status": "polling" if auto_polling_enabled else "offline",
        "error_message": "",
        "readings_received": 0,
        "readings_accepted": 0,
        "readings_rejected": 0,
        "sensors_detected": 0,
        "current_scenario": None,
        "current_tick": None,
        "latest_telemetry_timestamp": None,
        "last_ingestion_source": None,
        "baseline_source": None,
        "baseline_status": "none",
        "baseline_samples_collected": 0,
        "baseline_samples_required": DEFAULT_LIVE_BASELINE_SAMPLE_COUNT,
        "last_baseline_update": None,
        "baseline_error_message": "",
        "masked_configuration": {"url": default_connection_url},
    }


def ensure_default_data_connection(settings: Settings | None = None) -> dict[str, Any]:
    remove_legacy_telemetry_connection()
    existing = read_data_connection(DEFAULT_CONNECTION_ID)
    if existing:
        return existing
    payload = default_connection_payload(settings)
    upsert_data_connection(payload)
    return payload


def remove_legacy_telemetry_connection() -> None:
    delete_data_connection(LEGACY_NODE_RED_CONNECTION_ID)


def list_registered_data_connections() -> list[dict[str, Any]]:
    ensure_default_data_connection()
    return [
        upsert_registered_data_connection(item)
        for item in list_data_connections(limit=100)
        if item.get("connection_id") != LEGACY_NODE_RED_CONNECTION_ID
    ]


def upsert_registered_data_connection(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("connection_id") == LEGACY_NODE_RED_CONNECTION_ID:
        remove_legacy_telemetry_connection()
        raise ValueError(f"Data connection {LEGACY_NODE_RED_CONNECTION_ID} was removed.")
    current = read_data_connection(payload.get("connection_id", "")) or {}
    merged = {
        **default_connection_payload(),
        **current,
        **payload,
    }
    merged["masked_configuration"] = {"url": merged.get("url")}
    merged["status"] = merged.get("status") or ("polling" if merged.get("polling_enabled") else "offline")
    merged["error_message"] = merged.get("error_message") or ""
    merged["baseline_status"] = merged.get("baseline_status") or "none"
    merged["baseline_samples_required"] = int(merged.get("baseline_samples_required") or DEFAULT_LIVE_BASELINE_SAMPLE_COUNT)
    merged["baseline_samples_collected"] = int(merged.get("baseline_samples_collected") or 0)
    merged["baseline_error_message"] = merged.get("baseline_error_message") or ""
    if merged["status"] != "error":
        merged["error_message"] = ""
    if merged["baseline_status"] in {"none", "active"}:
        merged["baseline_error_message"] = ""
    upsert_data_connection(merged)
    return merged


def set_connection_polling(connection_id: str, *, enabled: bool) -> dict[str, Any]:
    connection = require_connection(connection_id)
    connection["polling_enabled"] = enabled
    connection["status"] = "polling" if enabled else "offline"
    connection["error_message"] = ""
    return upsert_registered_data_connection(connection)


def reset_all_data_connections() -> list[dict[str, Any]]:
    """Reset all registered data connections and clear active telemetry state."""
    reset_connections: list[dict[str, Any]] = []
    for connection in list_registered_data_connections():
        connection_id = str(connection.get("connection_id") or "")
        if not connection_id:
            continue
        clear_live_baseline(connection_id)
        reset_payload = {
            **connection,
            "polling_enabled": False,
            "status": "offline",
            "error_message": "",
            "last_poll_at": None,
            "last_success_at": None,
            "readings_received": 0,
            "readings_accepted": 0,
            "readings_rejected": 0,
            "sensors_detected": 0,
            "current_scenario": None,
            "current_tick": None,
            "latest_telemetry_timestamp": None,
            "last_ingestion_source": None,
            "baseline_source": None,
            "baseline_status": "none",
            "baseline_samples_collected": 0,
            "last_baseline_update": None,
            "baseline_error_message": "",
        }
        reset_connections.append(upsert_registered_data_connection(reset_payload))

    reset_latest_upload_state(purge_job_records=True)
    return reset_connections


def clear_all_connection_runtime_state() -> list[dict[str, Any]]:
    """Clear live runtime/baseline markers while preserving connection configuration."""
    cleared_connections: list[dict[str, Any]] = []
    for connection in list_registered_data_connections():
        connection_id = str(connection.get("connection_id") or "")
        if not connection_id:
            continue
        clear_live_baseline(connection_id)
        cleared_payload = {
            **connection,
            "error_message": "",
            "last_poll_at": None,
            "last_success_at": None,
            "readings_received": 0,
            "readings_accepted": 0,
            "readings_rejected": 0,
            "sensors_detected": 0,
            "current_scenario": None,
            "current_tick": None,
            "latest_telemetry_timestamp": None,
            "last_ingestion_source": None,
            "baseline_source": None,
            "baseline_status": "none",
            "baseline_samples_collected": 0,
            "last_baseline_update": None,
            "baseline_error_message": "",
        }
        cleared_connections.append(upsert_registered_data_connection(cleared_payload))
    return cleared_connections


def reset_connection_live_baseline(connection_id: str) -> dict[str, Any]:
    connection = require_connection(connection_id)
    logger.info(
        "baseline_rebuild_started connection_id=%s previous_status=%s previous_samples=%s",
        connection_id,
        connection.get("baseline_status"),
        connection.get("baseline_samples_collected"),
    )
    clear_live_baseline(connection_id)
    samples_required = max(
        int(connection.get("baseline_samples_required") or DEFAULT_LIVE_BASELINE_SAMPLE_COUNT),
        1,
    )
    rebuilt_state = write_live_baseline_state(
        connection_id,
        {
            "connection_id": connection_id,
            "baseline_source": "live_rest",
            "baseline_status": "building",
            "samples_collected": 0,
            "samples_required": samples_required,
            "last_baseline_update": now_iso(),
            "activated_at": None,
            "error_message": "",
        },
    )
    connection["baseline_source"] = rebuilt_state.get("baseline_source")
    connection["baseline_status"] = rebuilt_state.get("baseline_status")
    connection["baseline_samples_collected"] = rebuilt_state.get("samples_collected", 0)
    connection["baseline_samples_required"] = rebuilt_state.get("samples_required", DEFAULT_LIVE_BASELINE_SAMPLE_COUNT)
    connection["last_baseline_update"] = rebuilt_state.get("last_baseline_update")
    connection["baseline_error_message"] = ""
    updated = upsert_registered_data_connection(connection)
    logger.info(
        "baseline_rebuild_completed connection_id=%s status=%s samples=%s required=%s",
        connection_id,
        updated.get("baseline_status"),
        updated.get("baseline_samples_collected"),
        updated.get("baseline_samples_required"),
    )
    return updated


def baseline_state_key(connection_id: str) -> str:
    return f"data_connection_live_baseline:{connection_id}"


def baseline_records_key(connection_id: str) -> str:
    return f"data_connection_live_baseline_records:{connection_id}"


def recent_records_key(connection_id: str) -> str:
    return f"data_connection_live_recent_records:{connection_id}"


def require_connection(connection_id: str) -> dict[str, Any]:
    if connection_id == LEGACY_NODE_RED_CONNECTION_ID:
        remove_legacy_telemetry_connection()
        raise ValueError(f"Data connection {connection_id} was removed.")
    ensure_default_data_connection()
    connection = read_data_connection(connection_id)
    if connection is None:
        raise ValueError(f"Data connection {connection_id} was not found.")
    return upsert_registered_data_connection(connection)


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


def baseline_event_key(connection_id: str, event_name: str) -> str:
    return f"data_connection_event:{connection_id}:{event_name}"


def read_connection_buffer(connection_id: str) -> list[dict[str, Any]]:
    payload = read_latest_payload(records_buffer_key(connection_id))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def read_live_baseline_state(connection_id: str) -> dict[str, Any]:
    payload = read_latest_payload(baseline_state_key(connection_id))
    if not isinstance(payload, dict):
        return {
            "connection_id": connection_id,
            "baseline_source": None,
            "baseline_status": "none",
            "samples_collected": 0,
            "samples_required": DEFAULT_LIVE_BASELINE_SAMPLE_COUNT,
            "last_baseline_update": None,
            "activated_at": None,
            "error_message": "",
        }
    return {
        "connection_id": connection_id,
        "baseline_source": payload.get("baseline_source"),
        "baseline_status": payload.get("baseline_status") or "none",
        "samples_collected": int(payload.get("samples_collected") or 0),
        "samples_required": int(payload.get("samples_required") or DEFAULT_LIVE_BASELINE_SAMPLE_COUNT),
        "last_baseline_update": payload.get("last_baseline_update"),
        "activated_at": payload.get("activated_at"),
        "error_message": payload.get("error_message") or "",
    }


def write_live_baseline_state(connection_id: str, state: dict[str, Any]) -> dict[str, Any]:
    persisted = {
        "connection_id": connection_id,
        "baseline_source": state.get("baseline_source"),
        "baseline_status": state.get("baseline_status") or "none",
        "samples_collected": int(state.get("samples_collected") or 0),
        "samples_required": int(state.get("samples_required") or DEFAULT_LIVE_BASELINE_SAMPLE_COUNT),
        "last_baseline_update": state.get("last_baseline_update"),
        "activated_at": state.get("activated_at"),
        "error_message": state.get("error_message") or "",
    }
    upsert_latest_payload(baseline_state_key(connection_id), persisted)
    return persisted


def read_buffered_records(key: str) -> list[dict[str, Any]]:
    payload = read_latest_payload(key)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def write_buffered_records(key: str, records: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    trimmed = records[-limit:]
    upsert_latest_payload(key, trimmed)
    return trimmed


def merge_normalized_record_dicts(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    combined = existing + incoming
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
    return deduped


def append_baseline_records(connection_id: str, records: list[NormalizedTelemetryRecord]) -> list[dict[str, Any]]:
    existing = read_buffered_records(baseline_records_key(connection_id))
    incoming = [record.model_dump() for record in records]
    merged = merge_normalized_record_dicts(existing, incoming)
    return write_buffered_records(baseline_records_key(connection_id), merged, limit=MAX_BASELINE_RECORDS)


def read_baseline_records(connection_id: str) -> list[dict[str, Any]]:
    return read_buffered_records(baseline_records_key(connection_id))


def append_recent_records(connection_id: str, records: list[NormalizedTelemetryRecord]) -> list[dict[str, Any]]:
    existing = read_buffered_records(recent_records_key(connection_id))
    incoming = [record.model_dump() for record in records]
    merged = merge_normalized_record_dicts(existing, incoming)
    return write_buffered_records(recent_records_key(connection_id), merged, limit=MAX_RECENT_RECORDS)


def read_recent_records(connection_id: str) -> list[dict[str, Any]]:
    return read_buffered_records(recent_records_key(connection_id))


def clear_live_baseline(connection_id: str, *, keep_connection_buffer: bool = False) -> None:
    if not keep_connection_buffer:
        upsert_latest_payload(records_buffer_key(connection_id), [])
    upsert_latest_payload(baseline_records_key(connection_id), [])
    upsert_latest_payload(recent_records_key(connection_id), [])
    upsert_latest_payload(state_fingerprint_key(connection_id), {})
    write_live_baseline_state(
        connection_id,
        {
            "baseline_source": None,
            "baseline_status": "none",
            "samples_collected": 0,
            "samples_required": DEFAULT_LIVE_BASELINE_SAMPLE_COUNT,
            "last_baseline_update": None,
            "activated_at": None,
            "error_message": "",
        },
    )


def grouped_sample_count(records: list[dict[str, Any]]) -> int:
    return len({(str(item.get("timestamp") or ""), str(item.get("room_id") or "")) for item in records})


def recover_live_baseline_from_buffer(connection: dict[str, Any]) -> dict[str, Any] | None:
    connection_id = connection["connection_id"]
    buffer_records = read_connection_buffer(connection_id)
    if not buffer_records:
        return None

    baseline_seed = buffer_records[:MAX_BASELINE_RECORDS]
    recent_seed = buffer_records[-MAX_RECENT_RECORDS:]
    write_buffered_records(baseline_records_key(connection_id), baseline_seed, limit=MAX_BASELINE_RECORDS)
    write_buffered_records(recent_records_key(connection_id), recent_seed, limit=MAX_RECENT_RECORDS)

    samples_required = max(int(connection.get("baseline_samples_required") or DEFAULT_LIVE_BASELINE_SAMPLE_COUNT), 1)
    samples_collected = grouped_sample_count(baseline_seed)
    baseline_status = "active" if samples_collected >= samples_required else "building"
    baseline_state = {
        "connection_id": connection_id,
        "baseline_source": "live_rest",
        "baseline_status": baseline_status,
        "samples_collected": max(samples_collected, samples_required) if baseline_status == "active" else samples_collected,
        "samples_required": samples_required,
        "last_baseline_update": now_iso(),
        "activated_at": now_iso() if baseline_status == "active" else None,
        "error_message": "",
    }
    persisted = write_live_baseline_state(connection_id, baseline_state)
    logger.info(
        "baseline_recovered_from_buffer connection_id=%s samples_collected=%s samples_required=%s status=%s",
        connection_id,
        persisted.get("samples_collected"),
        persisted.get("samples_required"),
        persisted.get("baseline_status"),
    )
    return persisted


def resolve_baseline_state_for_health_update(
    connection: dict[str, Any],
    metadata: dict[str, Any],
    baseline_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if baseline_state is not None:
        return baseline_state

    active_readings = int(metadata.get("readings_accepted") or 0)
    if active_readings <= 0:
        return read_live_baseline_state(connection["connection_id"])

    current = read_live_baseline_state(connection["connection_id"])
    if current.get("baseline_status") != "none" or int(current.get("samples_collected") or 0) > 0:
        return current

    recovered = recover_live_baseline_from_buffer(connection)
    return recovered or current


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


def result_from_connection_batch(
    connection: dict[str, Any],
    processing_records: list[dict[str, Any]],
    metadata: dict[str, Any],
    *,
    baseline_state: dict[str, Any],
) -> dict[str, Any]:
    columns, rows, room_summary = build_rows_from_normalized_records(processing_records)
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
        intelligence_source_metadata={
            **metadata,
            "baseline_source": baseline_state.get("baseline_source"),
            "baseline_status": baseline_state.get("baseline_status"),
            "baseline_samples_collected": baseline_state.get("samples_collected"),
            "baseline_samples_required": baseline_state.get("samples_required"),
            "last_baseline_update": baseline_state.get("last_baseline_update"),
        },
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
    result["processing_stats"]["baseline_source"] = baseline_state.get("baseline_source")
    result["processing_stats"]["baseline_status"] = baseline_state.get("baseline_status")
    result["processing_stats"]["baseline_samples_collected"] = baseline_state.get("samples_collected")
    result["processing_stats"]["baseline_samples_required"] = baseline_state.get("samples_required")
    result["sii_intelligence"]["source"] = "rest_poll"
    result["sii_intelligence"]["source_metadata"] = {
        **metadata,
        "baseline_source": baseline_state.get("baseline_source"),
        "baseline_status": baseline_state.get("baseline_status"),
        "baseline_samples_collected": baseline_state.get("samples_collected"),
        "baseline_samples_required": baseline_state.get("samples_required"),
    }
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
    summary["baseline_source"] = metadata.get("baseline_source")
    summary["baseline_status"] = metadata.get("baseline_status")
    summary["baseline_samples_collected"] = metadata.get("baseline_samples_collected", 0)
    summary["baseline_samples_required"] = metadata.get("baseline_samples_required", DEFAULT_LIVE_BASELINE_SAMPLE_COUNT)
    summary["last_baseline_update"] = metadata.get("last_baseline_update")
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


def should_emit_event(connection_id: str, event_name: str, fingerprint: dict[str, Any]) -> bool:
    key = baseline_event_key(connection_id, event_name)
    previous = read_latest_payload(key)
    if previous != fingerprint:
        upsert_latest_payload(key, fingerprint)
        return True
    return False


def build_connection_status_event_record(
    connection: dict[str, Any],
    *,
    event_name: str,
    status: str,
    completed_at: str,
    metadata: dict[str, Any],
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    evidence_summary: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "run_id": f"{connection['connection_id']}-{event_name}-{uuid.uuid4().hex[:10]}",
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
        "system_id": metadata.get("facility_id") or connection.get("facility_id"),
        "room": metadata.get("room_id") or connection.get("room_id"),
        "operating_state": metadata.get("operating_state"),
        "neraium_score": metadata.get("neraium_score"),
        "drift_status": metadata.get("drift_status"),
        "primary_drivers": metadata.get("primary_drivers", []),
        "evidence_summary": evidence_summary or [],
        "warnings": warnings or [],
        "errors": errors or [],
        "input_hash": digest_payload({"event_name": event_name, "metadata": metadata}),
        "result_hash": digest_payload({"status": status, "event_name": event_name, "metadata": metadata}),
        "initiated_by": "system:rest-poller",
        "source_url": connection.get("url"),
        "scenario": metadata.get("scenario"),
        "tick": metadata.get("tick"),
    }


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


def update_connection_health_fields(
    connection: dict[str, Any],
    metadata: dict[str, Any],
    *,
    status: str,
    error_message: str = "",
    baseline_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    resolved_baseline_state = resolve_baseline_state_for_health_update(connection, metadata, baseline_state)
    if resolved_baseline_state:
        connection["baseline_source"] = resolved_baseline_state.get("baseline_source")
        connection["baseline_status"] = resolved_baseline_state.get("baseline_status")
        connection["baseline_samples_collected"] = resolved_baseline_state.get("samples_collected", 0)
        connection["baseline_samples_required"] = resolved_baseline_state.get("samples_required", DEFAULT_LIVE_BASELINE_SAMPLE_COUNT)
        connection["last_baseline_update"] = resolved_baseline_state.get("last_baseline_update")
        connection["baseline_error_message"] = resolved_baseline_state.get("error_message", "")
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
    tested = update_connection_health_fields(
        connection,
        metadata,
        status="online",
        baseline_state=read_live_baseline_state(connection_id),
    )
    return {
        "connection": tested,
        "normalized_preview": [record.model_dump() for record in records[:6]],
    }


def build_processing_metadata(metadata: dict[str, Any], baseline_state: dict[str, Any]) -> dict[str, Any]:
    return {
        **metadata,
        "baseline_source": baseline_state.get("baseline_source"),
        "baseline_status": baseline_state.get("baseline_status"),
        "baseline_samples_collected": baseline_state.get("samples_collected"),
        "baseline_samples_required": baseline_state.get("samples_required"),
        "last_baseline_update": baseline_state.get("last_baseline_update"),
    }


def activate_live_baseline(connection: dict[str, Any], metadata: dict[str, Any], baseline_state: dict[str, Any]) -> dict[str, Any]:
    completed_at = now_iso()
    baseline_state.update(
        {
            "baseline_source": "live_rest",
            "baseline_status": "active",
            "samples_collected": max(
                grouped_sample_count(read_baseline_records(connection["connection_id"])),
                baseline_state.get("samples_required", DEFAULT_LIVE_BASELINE_SAMPLE_COUNT),
            ),
            "last_baseline_update": completed_at,
            "activated_at": completed_at,
            "error_message": "",
        }
    )
    persisted = write_live_baseline_state(connection["connection_id"], baseline_state)
    logger.info(
        "baseline_ready connection_id=%s samples_collected=%s samples_required=%s",
        connection["connection_id"],
        persisted.get("samples_collected"),
        persisted.get("samples_required"),
    )
    if should_emit_event(
        connection["connection_id"],
        "baseline_activated",
        {
            "activated_at": completed_at,
            "scenario": metadata.get("scenario"),
            "tick": metadata.get("tick"),
        },
    ):
        upsert_evidence_run(
            build_connection_status_event_record(
                connection,
                event_name="baseline-activated",
                status="baseline_active",
                completed_at=completed_at,
                metadata=build_processing_metadata(metadata, persisted),
                evidence_summary=[
                    f"Live baseline activated for {connection.get('name')}.",
                    f"{persisted.get('samples_collected')} live samples are now available for comparison.",
                ],
            )
        )
    return persisted


def update_live_baseline(connection: dict[str, Any], normalized_records: list[NormalizedTelemetryRecord], metadata: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    connection_id = connection["connection_id"]
    baseline_state = read_live_baseline_state(connection_id)
    if baseline_state.get("baseline_status") == "failed":
        baseline_state["baseline_status"] = "building"
        baseline_state["error_message"] = ""
    if baseline_state.get("baseline_status") == "none":
        baseline_state = {
            **baseline_state,
            "baseline_source": "live_rest",
            "baseline_status": "building",
            "samples_collected": 0,
            "samples_required": connection.get("baseline_samples_required", DEFAULT_LIVE_BASELINE_SAMPLE_COUNT),
            "last_baseline_update": now_iso(),
            "activated_at": None,
            "error_message": "",
        }
        baseline_state = write_live_baseline_state(connection_id, baseline_state)
        if should_emit_event(connection_id, "baseline_building_started", {"started_at": baseline_state["last_baseline_update"]}):
            upsert_evidence_run(
                build_connection_status_event_record(
                    connection,
                    event_name="baseline-building-started",
                    status="baseline_building",
                    completed_at=baseline_state["last_baseline_update"],
                    metadata=build_processing_metadata(metadata, baseline_state),
                    evidence_summary=[
                        f"Live source connected: {connection.get('name')}.",
                        f"Building baseline from {baseline_state['samples_required']} live telemetry samples.",
                    ],
                )
            )

    if baseline_state.get("baseline_status") != "active":
        previous_samples_collected = int(baseline_state.get("samples_collected") or 0)
        baseline_records = append_baseline_records(connection_id, normalized_records)
        samples_collected = grouped_sample_count(baseline_records)
        baseline_state.update(
            {
                "baseline_source": "live_rest",
                "baseline_status": "building",
                "samples_collected": min(samples_collected, baseline_state.get("samples_required", DEFAULT_LIVE_BASELINE_SAMPLE_COUNT)),
                "last_baseline_update": now_iso(),
                "error_message": "",
            }
        )
        baseline_state = write_live_baseline_state(connection_id, baseline_state)
        if baseline_state.get("samples_collected", 0) > previous_samples_collected:
            logger.info(
                "baseline_sample_added connection_id=%s samples_collected=%s samples_required=%s readings_accepted=%s scenario=%s tick=%s",
                connection_id,
                baseline_state.get("samples_collected"),
                baseline_state.get("samples_required"),
                metadata.get("readings_accepted"),
                metadata.get("scenario"),
                metadata.get("tick"),
            )
        if samples_collected >= baseline_state.get("samples_required", DEFAULT_LIVE_BASELINE_SAMPLE_COUNT):
            baseline_state = activate_live_baseline(connection, metadata, baseline_state)
            return baseline_state, True
        return baseline_state, False

    baseline_records = read_baseline_records(connection_id)
    if not baseline_records:
        clear_live_baseline(connection_id, keep_connection_buffer=True)
        return update_live_baseline(connection, normalized_records, metadata)

    baseline_state.update(
        {
            "baseline_source": "live_rest",
            "baseline_status": "active",
            "samples_collected": max(grouped_sample_count(baseline_records), baseline_state.get("samples_collected", 0)),
            "last_baseline_update": now_iso(),
            "error_message": "",
        }
    )
    return write_live_baseline_state(connection_id, baseline_state), True


def latest_result_without_live_baseline(connection: dict[str, Any], baseline_state: dict[str, Any]) -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    return {
        "connection": update_connection_health_fields(
            connection,
            {
                "timestamp": connection.get("latest_telemetry_timestamp"),
                "scenario": connection.get("current_scenario"),
                "tick": connection.get("current_tick"),
                "readings_received": connection.get("readings_received", 0),
                "readings_accepted": connection.get("readings_accepted", 0),
                "readings_rejected": connection.get("readings_rejected", 0),
                "sensors_detected": connection.get("sensors_detected", 0),
            },
            status="polling",
            baseline_state=baseline_state,
        ),
        "summary": None,
        "latest_result": latest_result,
        "meaningful_change": False,
    }


def poll_data_connection_once(connection_id: str, *, transport: httpx.BaseTransport | None = None, actor: str = "system:rest-poller") -> dict[str, Any]:
    connection = require_connection(connection_id)
    last_status = connection.get("status")
    try:
        connection["last_poll_at"] = now_iso()
        upsert_registered_data_connection(connection)
        try:
            payload = fetch_connection_payload(connection, transport=transport)
            normalized_records, metadata = normalize_external_rest_payload(payload, connection)
        except Exception as exc:
            if isinstance(exc, httpx.TimeoutException):
                logger.warning("telemetry_fetch_timeout connection_id=%s url=%s", connection_id, connection.get("url"))
                raise TelemetryFetchError("Telemetry source timed out while fetching live readings.") from exc
            raise TelemetryFetchError(str(exc)) from exc

        logger.info(
            "telemetry_fetch_success connection_id=%s readings_received=%s scenario=%s tick=%s timestamp=%s",
            connection_id,
            metadata.get("readings_received"),
            metadata.get("scenario"),
            metadata.get("tick"),
            metadata.get("timestamp"),
        )
        append_connection_buffer(connection_id, normalized_records)
        append_recent_records(connection_id, normalized_records)
        logger.info(
            "telemetry_readings_accepted connection_id=%s readings_accepted=%s readings_rejected=%s sensors_detected=%s",
            connection_id,
            metadata.get("readings_accepted"),
            metadata.get("readings_rejected"),
            metadata.get("sensors_detected"),
        )

        try:
            baseline_state, baseline_ready = update_live_baseline(connection, normalized_records, metadata)
        except Exception as exc:
            error_message = str(exc)
            logger.exception("baseline_build_failed connection_id=%s error=%s", connection_id, error_message)
            baseline_state = read_live_baseline_state(connection_id)
            baseline_state.update(
                {
                    "baseline_source": baseline_state.get("baseline_source") or "live_rest",
                    "baseline_status": "failed" if baseline_state.get("baseline_status") in {"none", "failed"} else "building",
                    "last_baseline_update": now_iso(),
                    "error_message": error_message,
                }
            )
            baseline_state = write_live_baseline_state(connection_id, baseline_state)
            metadata = build_processing_metadata(metadata, baseline_state)
            connection = update_connection_health_fields(connection, metadata, status="polling", baseline_state=baseline_state)
            partial = latest_result_without_live_baseline(connection, baseline_state)
            partial["actor"] = actor
            partial["baseline_error"] = error_message
            return partial

        metadata = build_processing_metadata(metadata, baseline_state)
        connection = update_connection_health_fields(connection, metadata, status="polling", baseline_state=baseline_state)
        if not baseline_ready:
            logger.info(
                "data_connection_baseline_building connection_id=%s samples_collected=%s samples_required=%s",
                connection_id,
                baseline_state.get("samples_collected"),
                baseline_state.get("samples_required"),
            )
            partial = latest_result_without_live_baseline(connection, baseline_state)
            partial["actor"] = actor
            return partial

        recent_records = read_recent_records(connection_id)
        baseline_records = read_baseline_records(connection_id)
        processing_records = merge_normalized_record_dicts(baseline_records, recent_records)
        result = result_from_connection_batch(connection, processing_records, metadata, baseline_state=baseline_state)
        completed_at = now_iso()
        summary = summarize_connection_result(connection, result, completed_at, metadata)
        meaningful_change = has_meaningful_state_change(connection_id, summary)
        write_latest_upload_result(connection_id, result)
        write_latest_upload_summary(connection_id, summary, append_history=meaningful_change)
        connection = update_connection_health_fields(connection, metadata, status="polling", baseline_state=baseline_state)
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
        elif should_emit_event(
            connection_id,
            "source_connected",
            {"status": connection.get("status"), "last_success_at": connection.get("last_success_at")},
        ):
            upsert_evidence_run(
                build_connection_status_event_record(
                    connection,
                    event_name="source-connected",
                    status="connected",
                    completed_at=completed_at,
                    metadata=metadata,
                    evidence_summary=[
                        f"Live source connected: {connection.get('name')}.",
                        f"Baseline status is {baseline_state.get('baseline_status')}.",
                    ],
                )
            )
        return {
            "connection": connection,
            "summary": summary,
            "latest_result": result,
            "meaningful_change": meaningful_change,
            "actor": actor,
        }
    except TelemetryFetchError as exc:
        error_message = str(exc)
        logger.warning(
            "data_connection_poll_failed connection_id=%s timeout=%s error=%s",
            connection_id,
            "timed out" in error_message.lower(),
            error_message,
        )
        baseline_state = read_live_baseline_state(connection_id)
        if baseline_state.get("baseline_status") in {"none", "failed"}:
            baseline_state["baseline_status"] = "failed"
        baseline_state["error_message"] = error_message
        baseline_state["last_baseline_update"] = now_iso()
        baseline_state = write_live_baseline_state(connection_id, baseline_state)
        failure_metadata = {
            "scenario": connection.get("current_scenario"),
            "tick": connection.get("current_tick"),
            "timestamp": connection.get("latest_telemetry_timestamp"),
            "readings_received": 0,
            "sensors_detected": connection.get("sensors_detected", 0),
        }
        connection = update_connection_health_fields(
            connection,
            failure_metadata,
            status="error",
            error_message=error_message,
            baseline_state=baseline_state,
        )
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
