from __future__ import annotations

import json
import logging
import math
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from numbers import Real
from typing import Any

from app.core.config import Settings
from app.services.runtime_db import db_connection, init_runtime_db


logger = logging.getLogger(__name__)

REJECTION_REASONS = frozenset(
    {
        "missing_timestamp",
        "invalid_timestamp",
        "future_timestamp",
        "non_numeric_value",
        "nan_value",
        "infinite_value",
        "unmapped_signal",
        "duplicate_record",
        "out_of_order_record",
    }
)


class TelemetryConflictError(ValueError):
    pass


class TelemetryLimitError(ValueError):
    pass


class TelemetryNotFoundError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _mapping_payload(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["enabled"] = bool(payload["enabled"])
    return payload


def create_signal_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    init_runtime_db()
    timestamp = _iso_utc(_utc_now())
    mapping_id = f"mapping-{uuid.uuid4().hex}"
    try:
        with db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO telemetry_signal_mappings (
                    mapping_id, system_id, source_tag, canonical_signal,
                    unit, enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mapping_id,
                    payload["system_id"],
                    payload["source_tag"],
                    payload["canonical_signal"],
                    payload.get("unit"),
                    1 if payload.get("enabled", True) else 0,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                "SELECT * FROM telemetry_signal_mappings WHERE mapping_id = ?",
                (mapping_id,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        if "UNIQUE constraint failed" in str(error):
            raise TelemetryConflictError("A mapping already exists for this system and source tag.") from None
        raise
    if row is None:
        raise RuntimeError("signal_mapping_insert_failed")
    return _mapping_payload(row)


def read_signal_mapping(mapping_id: str) -> dict[str, Any]:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM telemetry_signal_mappings WHERE mapping_id = ?",
            (mapping_id,),
        ).fetchone()
    if row is None:
        raise TelemetryNotFoundError("Signal mapping not found.")
    return _mapping_payload(row)


def list_signal_mappings(
    *,
    system_id: str | None = None,
    include_disabled: bool = False,
) -> list[dict[str, Any]]:
    init_runtime_db()
    conditions: list[str] = []
    params: list[Any] = []
    if system_id:
        conditions.append("system_id = ?")
        params.append(system_id)
    if not include_disabled:
        conditions.append("enabled = 1")
    query = "SELECT * FROM telemetry_signal_mappings"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY system_id, source_tag, mapping_id"
    with db_connection() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return [_mapping_payload(row) for row in rows]


def update_signal_mapping(mapping_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    allowed = {"canonical_signal", "unit", "enabled"}
    selected = {key: value for key, value in updates.items() if key in allowed}
    if not selected:
        raise ValueError("At least one mapping field must be supplied.")
    init_runtime_db()
    selected["updated_at"] = _iso_utc(_utc_now())
    assignments: list[str] = []
    params: list[Any] = []
    for key, value in selected.items():
        assignments.append(f"{key} = ?")
        params.append(1 if key == "enabled" and value else 0 if key == "enabled" else value)
    params.append(mapping_id)
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        updated = connection.execute(
            f"UPDATE telemetry_signal_mappings SET {', '.join(assignments)} WHERE mapping_id = ?",
            tuple(params),
        ).rowcount
        row = connection.execute(
            "SELECT * FROM telemetry_signal_mappings WHERE mapping_id = ?",
            (mapping_id,),
        ).fetchone()
    if not updated or row is None:
        raise TelemetryNotFoundError("Signal mapping not found.")
    return _mapping_payload(row)


def disable_signal_mapping(mapping_id: str) -> dict[str, Any]:
    return update_signal_mapping(mapping_id, {"enabled": False})


def _parse_timestamp(value: Any) -> tuple[datetime | None, str | None]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, "missing_timestamp"
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip()
        if len(normalized) > 128:
            return None, "invalid_timestamp"
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            return None, "invalid_timestamp"
    else:
        return None, "invalid_timestamp"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "invalid_timestamp"
    return parsed.astimezone(UTC), None


def _numeric_value(value: Any) -> tuple[float | None, str | None]:
    if isinstance(value, bool) or value is None:
        return None, "non_numeric_value"
    if isinstance(value, Real):
        try:
            numeric = float(value)
        except OverflowError:
            return None, "infinite_value"
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None, "non_numeric_value"
        try:
            numeric = float(normalized)
        except (ValueError, OverflowError):
            return None, "non_numeric_value"
    else:
        return None, "non_numeric_value"
    if math.isnan(numeric):
        return None, "nan_value"
    if math.isinf(numeric):
        return None, "infinite_value"
    return numeric, None


def _safe_submitted_value(value: Any) -> str | None:
    try:
        serialized = json.dumps(value, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError):
        return None
    return serialized if len(serialized.encode("utf-8")) <= 4096 else None


def _available_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:128] if text else None


def _record_rejection(
    connection: sqlite3.Connection,
    *,
    batch_id: str,
    system_id: str,
    source: str,
    source_tag: str | None,
    telemetry_timestamp: str | None,
    submitted_value: Any,
    reason: str,
    ingested_at: str,
) -> None:
    if reason not in REJECTION_REASONS:
        raise ValueError(f"unsupported telemetry rejection reason: {reason}")
    connection.execute(
        """
        INSERT INTO rejected_telemetry (
            batch_id, system_id, source, source_tag, telemetry_timestamp,
            submitted_value_json, rejection_reason, ingested_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            system_id,
            source,
            source_tag,
            telemetry_timestamp,
            _safe_submitted_value(submitted_value),
            reason,
            ingested_at,
        ),
    )


def _health_status(
    latest_timestamp: str | None,
    *,
    now: datetime,
    delay_threshold_seconds: float,
) -> str:
    if not latest_timestamp:
        return "never_received"
    parsed, error = _parse_timestamp(latest_timestamp)
    if error or parsed is None:
        return "error"
    return "delayed" if parsed < now - timedelta(seconds=delay_threshold_seconds) else "healthy"


def _upsert_ingestion_health(
    connection: sqlite3.Connection,
    *,
    system_id: str,
    source: str,
    accepted_count: int,
    rejected_count: int,
    latest_telemetry_timestamp: str | None,
    warnings: list[str],
    processing_timestamp: str,
    now: datetime,
    delay_threshold_seconds: float,
    duplicate_only: bool,
) -> None:
    existing = connection.execute(
        "SELECT * FROM telemetry_ingestion_health WHERE system_id = ? AND source = ?",
        (system_id, source),
    ).fetchone()
    prior = dict(existing) if existing else {}
    last_telemetry = prior.get("last_telemetry_timestamp")
    if latest_telemetry_timestamp and (
        not last_telemetry or latest_telemetry_timestamp > str(last_telemetry)
    ):
        last_telemetry = latest_telemetry_timestamp
    if accepted_count:
        status = _health_status(
            last_telemetry,
            now=now,
            delay_threshold_seconds=delay_threshold_seconds,
        )
        last_success = processing_timestamp
    elif duplicate_only and existing:
        status = str(prior.get("status") or "never_received")
        last_success = prior.get("last_successful_ingestion_at")
    else:
        status = "error"
        last_success = prior.get("last_successful_ingestion_at")
    latest_message = ", ".join(warnings) if warnings else None
    connection.execute(
        """
        INSERT INTO telemetry_ingestion_health (
            system_id, source, last_successful_ingestion_at,
            last_telemetry_timestamp, accepted_count, rejected_count,
            latest_error_or_warning, status, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(system_id, source) DO UPDATE SET
            last_successful_ingestion_at = excluded.last_successful_ingestion_at,
            last_telemetry_timestamp = excluded.last_telemetry_timestamp,
            accepted_count = excluded.accepted_count,
            rejected_count = excluded.rejected_count,
            latest_error_or_warning = excluded.latest_error_or_warning,
            status = excluded.status,
            updated_at = excluded.updated_at
        """,
        (
            system_id,
            source,
            last_success,
            last_telemetry,
            int(prior.get("accepted_count") or 0) + accepted_count,
            int(prior.get("rejected_count") or 0) + rejected_count,
            latest_message,
            status,
            processing_timestamp,
        ),
    )


def ingest_telemetry_batch(
    payload: dict[str, Any],
    *,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, Any]:
    readings = list(payload.get("readings") or [])
    if len(readings) > settings.telemetry_max_readings_per_batch:
        raise TelemetryLimitError(
            f"Telemetry batch exceeds the {settings.telemetry_max_readings_per_batch} reading limit."
        )
    for index, reading in enumerate(readings):
        signal_count = len(reading.get("signals") or {})
        if signal_count > settings.telemetry_max_signals_per_reading:
            raise TelemetryLimitError(
                f"Reading {index} exceeds the {settings.telemetry_max_signals_per_reading} signal limit."
            )

    processing_time = (now or _utc_now()).astimezone(UTC)
    processing_timestamp = _iso_utc(processing_time)
    system_id = str(payload["system_id"])
    source = str(payload["source"])
    batch_id = str(payload.get("batch_id") or f"telemetry-{uuid.uuid4().hex}")
    future_cutoff = processing_time + timedelta(seconds=settings.telemetry_future_skew_seconds)

    init_runtime_db()
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing_batch = connection.execute(
            "SELECT system_id, source, result_json FROM telemetry_ingestion_batches WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
        if existing_batch:
            if existing_batch["system_id"] != system_id or existing_batch["source"] != source:
                raise TelemetryConflictError("Batch ID is already associated with another system or source.")
            if existing_batch["result_json"]:
                return json.loads(existing_batch["result_json"])
            raise TelemetryConflictError("Telemetry batch is already being processed.")

        connection.execute(
            """
            INSERT INTO telemetry_ingestion_batches
                (batch_id, system_id, source, received_at, completed_at, result_json)
            VALUES (?, ?, ?, ?, NULL, NULL)
            """,
            (batch_id, system_id, source, processing_timestamp),
        )
        mapping_rows = connection.execute(
            """
            SELECT source_tag, canonical_signal, unit
            FROM telemetry_signal_mappings
            WHERE system_id = ? AND enabled = 1
            """,
            (system_id,),
        ).fetchall()
        mappings = {str(row["source_tag"]): dict(row) for row in mapping_rows}
        newest_rows = connection.execute(
            """
            SELECT canonical_signal, MAX(telemetry_timestamp) AS newest
            FROM normalized_telemetry
            WHERE system_id = ?
            GROUP BY canonical_signal
            """,
            (system_id,),
        ).fetchall()
        newest_by_signal = {
            str(row["canonical_signal"]): _parse_timestamp(row["newest"])[0]
            for row in newest_rows
            if row["newest"]
        }

        accepted_readings = 0
        rejected_readings = 0
        accepted_values = 0
        rejected_values = 0
        warning_codes: set[str] = set()
        rejection_reasons: list[str] = []
        accepted_timestamps: list[str] = []

        for reading in readings:
            signals = dict(reading.get("signals") or {})
            raw_timestamp = reading.get("timestamp")
            parsed_timestamp, timestamp_error = _parse_timestamp(raw_timestamp)
            normalized_timestamp = _iso_utc(parsed_timestamp) if parsed_timestamp else None
            if parsed_timestamp and parsed_timestamp > future_cutoff:
                timestamp_error = "future_timestamp"
            reading_accepted = False

            for source_tag, submitted_value in signals.items():
                reason = timestamp_error
                numeric_value: float | None = None
                mapping = mappings.get(str(source_tag))
                if reason is None:
                    numeric_value, reason = _numeric_value(submitted_value)
                if reason is None and mapping is None:
                    reason = "unmapped_signal"

                quality_status = "good"
                if reason is None and mapping is not None and parsed_timestamp is not None:
                    canonical_signal = str(mapping["canonical_signal"])
                    newest = newest_by_signal.get(canonical_signal)
                    if newest and parsed_timestamp < newest:
                        lateness = (newest - parsed_timestamp).total_seconds()
                        if lateness > settings.telemetry_out_of_order_tolerance_seconds:
                            duplicate = connection.execute(
                                """
                                SELECT 1
                                FROM normalized_telemetry
                                WHERE system_id = ?
                                  AND canonical_signal = ?
                                  AND telemetry_timestamp = ?
                                  AND source = ?
                                """,
                                (
                                    system_id,
                                    canonical_signal,
                                    normalized_timestamp,
                                    source,
                                ),
                            ).fetchone()
                            reason = "duplicate_record" if duplicate else "out_of_order_record"
                        else:
                            quality_status = "out_of_order"

                if reason is None and mapping is not None and numeric_value is not None and normalized_timestamp:
                    inserted = connection.execute(
                        """
                        INSERT OR IGNORE INTO normalized_telemetry (
                            system_id, canonical_signal, telemetry_timestamp, value,
                            source, source_tag, quality_status, ingested_at, batch_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            system_id,
                            mapping["canonical_signal"],
                            normalized_timestamp,
                            numeric_value,
                            source,
                            source_tag,
                            quality_status,
                            processing_timestamp,
                            batch_id,
                        ),
                    ).rowcount
                    if inserted:
                        accepted_values += 1
                        reading_accepted = True
                        accepted_timestamps.append(normalized_timestamp)
                        if quality_status == "out_of_order":
                            warning_codes.add("out_of_order_accepted")
                    else:
                        reason = "duplicate_record"

                if reason is not None:
                    rejected_values += 1
                    rejection_reasons.append(reason)
                    warning_codes.add(reason)
                    _record_rejection(
                        connection,
                        batch_id=batch_id,
                        system_id=system_id,
                        source=source,
                        source_tag=str(source_tag),
                        telemetry_timestamp=(
                            normalized_timestamp
                            if parsed_timestamp is not None
                            else _available_timestamp(raw_timestamp)
                        ),
                        submitted_value=submitted_value,
                        reason=reason,
                        ingested_at=processing_timestamp,
                    )

            if reading_accepted:
                accepted_readings += 1
            else:
                rejected_readings += 1

        warnings = sorted(warning_codes)
        result = {
            "batch_id": batch_id,
            "accepted_reading_count": accepted_readings,
            "rejected_reading_count": rejected_readings,
            "accepted_signal_value_count": accepted_values,
            "rejected_signal_value_count": rejected_values,
            "warnings": warnings,
            "processing_timestamp": processing_timestamp,
        }
        latest_timestamp = max(accepted_timestamps) if accepted_timestamps else None
        _upsert_ingestion_health(
            connection,
            system_id=system_id,
            source=source,
            accepted_count=accepted_values,
            rejected_count=rejected_values,
            latest_telemetry_timestamp=latest_timestamp,
            warnings=warnings,
            processing_timestamp=processing_timestamp,
            now=processing_time,
            delay_threshold_seconds=settings.telemetry_delay_threshold_seconds,
            duplicate_only=bool(rejection_reasons)
            and all(reason == "duplicate_record" for reason in rejection_reasons),
        )
        connection.execute(
            """
            UPDATE telemetry_ingestion_batches
            SET completed_at = ?, result_json = ?
            WHERE batch_id = ?
            """,
            (processing_timestamp, json.dumps(result, separators=(",", ":")), batch_id),
        )

    logger.info(
        "live_telemetry_batch_ingested",
        extra={
            "event": "live_telemetry_batch_ingested",
            "batch_id": batch_id,
            "system_id": system_id,
            "source": source,
            "accepted_signal_value_count": accepted_values,
            "rejected_signal_value_count": rejected_values,
        },
    )
    return result


def list_normalized_telemetry(
    *,
    system_id: str | None = None,
    canonical_signal: str | None = None,
    batch_id: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    init_runtime_db()
    conditions: list[str] = []
    params: list[Any] = []
    for column, value in (
        ("system_id", system_id),
        ("canonical_signal", canonical_signal),
        ("batch_id", batch_id),
    ):
        if value is not None:
            conditions.append(f"{column} = ?")
            params.append(value)
    query = "SELECT * FROM normalized_telemetry"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY telemetry_timestamp, telemetry_id LIMIT ?"
    params.append(max(1, min(int(limit), 10_000)))
    with db_connection() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def list_rejected_telemetry(
    *,
    batch_id: str | None = None,
    system_id: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    init_runtime_db()
    conditions: list[str] = []
    params: list[Any] = []
    if batch_id:
        conditions.append("batch_id = ?")
        params.append(batch_id)
    if system_id:
        conditions.append("system_id = ?")
        params.append(system_id)
    query = "SELECT * FROM rejected_telemetry"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY rejection_id LIMIT ?"
    params.append(max(1, min(int(limit), 10_000)))
    with db_connection() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    payloads = [dict(row) for row in rows]
    for payload in payloads:
        raw_value = payload.pop("submitted_value_json", None)
        payload["submitted_value"] = json.loads(raw_value) if raw_value is not None else None
    return payloads


def list_ingestion_health(
    *,
    settings: Settings,
    system_id: str | None = None,
    source: str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    init_runtime_db()
    conditions: list[str] = []
    params: list[Any] = []
    if system_id:
        conditions.append("system_id = ?")
        params.append(system_id)
    if source:
        conditions.append("source = ?")
        params.append(source)
    query = "SELECT * FROM telemetry_ingestion_health"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY system_id, source"
    current_time = (now or _utc_now()).astimezone(UTC)
    with db_connection() as connection:
        rows = [dict(row) for row in connection.execute(query, tuple(params)).fetchall()]
        for row in rows:
            if row["status"] in {"healthy", "delayed"}:
                current_status = _health_status(
                    row.get("last_telemetry_timestamp"),
                    now=current_time,
                    delay_threshold_seconds=settings.telemetry_delay_threshold_seconds,
                )
                if current_status != row["status"]:
                    row["status"] = current_status
                    row["updated_at"] = _iso_utc(current_time)
                    connection.execute(
                        """
                        UPDATE telemetry_ingestion_health
                        SET status = ?, updated_at = ?
                        WHERE system_id = ? AND source = ?
                        """,
                        (
                            current_status,
                            row["updated_at"],
                            row["system_id"],
                            row["source"],
                        ),
                    )
    if not rows and system_id and source:
        return [
            {
                "system_id": system_id,
                "source": source,
                "last_successful_ingestion_at": None,
                "last_telemetry_timestamp": None,
                "accepted_count": 0,
                "rejected_count": 0,
                "latest_error_or_warning": None,
                "status": "never_received",
                "updated_at": None,
            }
        ]
    return rows
