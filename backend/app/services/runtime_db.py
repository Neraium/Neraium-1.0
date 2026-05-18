from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from app.core.config import get_settings


RUNTIME_DIR = get_settings().runtime_dir
DB_PATH = RUNTIME_DIR / "runtime.db"

def configure_runtime_dir(runtime_dir: Path) -> None:
    global RUNTIME_DIR, DB_PATH
    RUNTIME_DIR = runtime_dir
    DB_PATH = RUNTIME_DIR / "runtime.db"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    ensure_runtime_dir()
    connection = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_runtime_db() -> None:
    with db_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS upload_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS upload_queue (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                locked_at TEXT
            );

            CREATE TABLE IF NOT EXISTS evidence_runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                source_name TEXT,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                request_id TEXT,
                actor TEXT,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT,
                detail_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS latest_payloads (
                key TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS data_connections (
                connection_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                polling_enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )


def upsert_upload_job(payload: dict[str, Any]) -> None:
    init_runtime_db()
    timestamp = now_iso()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO upload_jobs (job_id, status, started_at, completed_at, updated_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                status=excluded.status,
                started_at=excluded.started_at,
                completed_at=excluded.completed_at,
                updated_at=excluded.updated_at,
                payload_json=excluded.payload_json
            """,
            (
                payload["job_id"],
                payload.get("status"),
                payload.get("started_at"),
                payload.get("completed_at"),
                timestamp,
                json.dumps(payload),
            ),
        )


def read_upload_job(job_id: str) -> dict[str, Any] | None:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT payload_json FROM upload_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload_json"])


def list_upload_jobs(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    init_runtime_db()
    query = "SELECT payload_json FROM upload_jobs"
    params: list[Any] = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    with db_connection() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def enqueue_upload_job(job_id: str) -> None:
    init_runtime_db()
    timestamp = now_iso()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO upload_queue (job_id, status, attempts, last_error, created_at, updated_at, locked_at)
            VALUES (?, 'pending', 0, NULL, ?, ?, NULL)
            ON CONFLICT(job_id) DO UPDATE SET
                status='pending',
                updated_at=excluded.updated_at,
                last_error=NULL,
                locked_at=NULL
            """,
            (job_id, timestamp, timestamp),
        )


def claim_next_upload_job() -> str | None:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT job_id FROM upload_queue
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        job_id = row["job_id"]
        connection.execute(
            """
            UPDATE upload_queue
            SET status='processing',
                attempts=attempts + 1,
                updated_at=?,
                locked_at=?
            WHERE job_id = ?
            """,
            (now_iso(), now_iso(), job_id),
        )
        return job_id


def mark_queue_job_failed(job_id: str, reason: str) -> None:
    init_runtime_db()
    with db_connection() as connection:
        connection.execute(
            """
            UPDATE upload_queue
            SET status = 'failed', last_error = ?, updated_at = ?, locked_at = NULL
            WHERE job_id = ?
            """,
            (reason, now_iso(), job_id),
        )


def clear_stale_processing_queue_jobs() -> int:
    init_runtime_db()
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT job_id FROM upload_queue WHERE status = 'processing'"
        ).fetchall()
        stale_job_ids = [row["job_id"] for row in rows]
        if stale_job_ids:
            connection.executemany(
                """
                UPDATE upload_queue
                SET status='failed', last_error=?, updated_at=?, locked_at=NULL
                WHERE job_id = ?
                """,
                [("stale_processing_job_recovered", now_iso(), job_id) for job_id in stale_job_ids],
            )
    return len(stale_job_ids)


def complete_upload_queue_job(job_id: str, status: str, last_error: str | None = None) -> None:
    init_runtime_db()
    with db_connection() as connection:
        connection.execute(
            """
            UPDATE upload_queue
            SET status = ?, last_error = ?, updated_at = ?, locked_at = NULL
            WHERE job_id = ?
            """,
            (status, last_error, now_iso(), job_id),
        )


def queue_metrics() -> dict[str, int]:
    init_runtime_db()
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM upload_queue GROUP BY status"
        ).fetchall()
    metrics = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    for row in rows:
        metrics[row["status"]] = row["count"]
    return metrics


def upsert_latest_payload(key: str, payload: Any) -> None:
    init_runtime_db()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO latest_payloads (key, updated_at, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                updated_at=excluded.updated_at,
                payload_json=excluded.payload_json
            """,
            (key, now_iso(), json.dumps(payload)),
        )


def read_latest_payload(key: str) -> Any | None:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT payload_json FROM latest_payloads WHERE key = ?",
            (key,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload_json"])


def upsert_evidence_run_db(record: dict[str, Any]) -> None:
    init_runtime_db()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO evidence_runs (run_id, created_at, completed_at, status, source_name, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                created_at=excluded.created_at,
                completed_at=excluded.completed_at,
                status=excluded.status,
                source_name=excluded.source_name,
                payload_json=excluded.payload_json
            """,
            (
                record["run_id"],
                record.get("created_at") or now_iso(),
                record.get("completed_at"),
                record.get("status", "pending"),
                record.get("source_name"),
                json.dumps(record),
            ),
        )


def list_evidence_runs_db(limit: int = 50) -> list[dict[str, Any]]:
    init_runtime_db()
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM evidence_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def read_evidence_run_db(run_id: str) -> dict[str, Any] | None:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT payload_json FROM evidence_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload_json"])


def record_audit_event(
    *,
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    request_id: str | None,
    detail: dict[str, Any],
) -> None:
    init_runtime_db()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO audit_events (created_at, request_id, actor, action, resource_type, resource_id, detail_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now_iso(), request_id, actor, action, resource_type, resource_id, json.dumps(detail)),
        )


def audit_events_count() -> int:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM audit_events").fetchone()
    return int(row["count"]) if row else 0


def upsert_data_connection(payload: dict[str, Any]) -> None:
    init_runtime_db()
    timestamp = now_iso()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO data_connections (connection_id, name, status, polling_enabled, updated_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(connection_id) DO UPDATE SET
                name=excluded.name,
                status=excluded.status,
                polling_enabled=excluded.polling_enabled,
                updated_at=excluded.updated_at,
                payload_json=excluded.payload_json
            """,
            (
                payload["connection_id"],
                payload.get("name", payload["connection_id"]),
                payload.get("status", "not_configured"),
                1 if payload.get("polling_enabled") else 0,
                timestamp,
                json.dumps(payload),
            ),
        )


def delete_data_connection(connection_id: str) -> None:
    init_runtime_db()
    with db_connection() as connection:
        connection.execute(
            "DELETE FROM data_connections WHERE connection_id = ?",
            (connection_id,),
        )


def read_data_connection(connection_id: str) -> dict[str, Any] | None:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT payload_json FROM data_connections WHERE connection_id = ?",
            (connection_id,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload_json"])


def list_data_connections(limit: int = 100) -> list[dict[str, Any]]:
    init_runtime_db()
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM data_connections ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]
