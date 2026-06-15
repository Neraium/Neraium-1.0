from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.core.config import get_settings


RUNTIME_DIR = get_settings().runtime_dir
DB_PATH = RUNTIME_DIR / "runtime.db" 
UPLOAD_QUEUE_RETENTION_DAYS = int(os.getenv("NERAIUM_UPLOAD_QUEUE_RETENTION_DAYS", "14"))
EVIDENCE_RUN_RETENTION_DAYS = int(os.getenv("NERAIUM_EVIDENCE_RUN_RETENTION_DAYS", "45"))
logger = logging.getLogger(__name__)


@dataclass
class RuntimeDbClients:
    upload_queue_s3_client: Any | None = None


RUNTIME_DB_CLIENTS = RuntimeDbClients()

def configure_runtime_dir(runtime_dir: Path) -> None:
    global RUNTIME_DIR, DB_PATH
    RUNTIME_DIR = runtime_dir
    DB_PATH = RUNTIME_DIR / "runtime.db"
    RUNTIME_DB_CLIENTS.upload_queue_s3_client = None


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_upload_queue_status(status: str | None) -> str | None:
    normalized = str(status or "").strip().lower()
    if not normalized:
        return None
    if normalized == "queued":
        return "pending"
    return normalized


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

            CREATE INDEX IF NOT EXISTS idx_upload_jobs_updated_at ON upload_jobs(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_upload_jobs_status_updated ON upload_jobs(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_upload_queue_status_created ON upload_queue(status, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_upload_queue_updated_at ON upload_queue(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_evidence_runs_created_at ON evidence_runs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_evidence_runs_status_created ON evidence_runs(status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_latest_payloads_updated_at ON latest_payloads(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_data_connections_updated_at ON data_connections(updated_at DESC);
            """ 
        ) 


def prune_runtime_db_records() -> dict[str, int]:
    init_runtime_db()
    now = datetime.now(UTC)
    queue_cutoff = now.timestamp() - max(UPLOAD_QUEUE_RETENTION_DAYS, 1) * 86400
    evidence_cutoff = now.timestamp() - max(EVIDENCE_RUN_RETENTION_DAYS, 1) * 86400
    queue_cutoff_iso = datetime.fromtimestamp(queue_cutoff, UTC).isoformat()
    evidence_cutoff_iso = datetime.fromtimestamp(evidence_cutoff, UTC).isoformat()
    with db_connection() as connection:
        queue_deleted = connection.execute(
            """
            DELETE FROM upload_queue
            WHERE status IN ('completed', 'failed')
              AND updated_at < ?
            """,
            (queue_cutoff_iso,),
        ).rowcount
        evidence_deleted = connection.execute(
            """
            DELETE FROM evidence_runs
            WHERE created_at < ?
            """,
            (evidence_cutoff_iso,),
        ).rowcount
    return {
        "upload_queue_deleted": int(queue_deleted or 0),
        "evidence_runs_deleted": int(evidence_deleted or 0),
    }


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


def upload_duration_samples(limit: int = 200) -> list[float]:
    init_runtime_db()
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT payload_json FROM upload_jobs
            WHERE status = 'COMPLETE'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    samples: list[float] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        value = payload.get("processing_duration_seconds")
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if numeric > 0:
            samples.append(numeric)
    return samples


def _upload_state_bucket() -> str:
    return os.getenv("NERAIUM_UPLOAD_STATE_BUCKET", "").strip()


def _upload_state_prefix() -> str:
    prefix = os.getenv("NERAIUM_UPLOAD_STATE_PREFIX", "upload-state/").strip()
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    return prefix


def _upload_queue_prefix() -> str:
    return f"{_upload_state_prefix()}upload-queue/"


def upload_queue_backend() -> str:
    if _upload_state_bucket():
        return "s3"
    return "runtime_db"


def _split_role_shared_queue_required() -> bool:
    app_env = os.getenv("APP_ENV", "").strip().lower()
    process_role = os.getenv("NERAIUM_PROCESS_ROLE", "").strip().lower()
    return app_env in {"prod", "production"} and process_role in {"api", "worker"}


def _ensure_shared_upload_queue_backend() -> None:
    if _split_role_shared_queue_required() and not _upload_state_bucket():
        raise RuntimeError(
            "shared_upload_queue_not_configured: set NERAIUM_UPLOAD_STATE_BUCKET for split-role production uploads"
        )


def _queue_object_key(job_id: str) -> str:
    return f"{_upload_queue_prefix()}{job_id}.json"


def _get_s3_client() -> Any | None:
    if RUNTIME_DB_CLIENTS.upload_queue_s3_client is not None:
        return RUNTIME_DB_CLIENTS.upload_queue_s3_client
    if not _upload_state_bucket():
        return None
    try:
        import boto3  # type: ignore

        RUNTIME_DB_CLIENTS.upload_queue_s3_client = boto3.client("s3")
        return RUNTIME_DB_CLIENTS.upload_queue_s3_client
    except Exception:
        logger.exception("upload_queue_s3_client_unavailable queue_backend=s3")
        return None


def _queue_status_rank(status: str | None) -> int:
    normalized = _normalize_upload_queue_status(status) or str(status or "").lower()
    return {"processing": 0, "pending": 1, "completed": 2, "failed": 3}.get(normalized, 99)


def _queue_timestamp(value: str | None) -> str:
    return str(value or "")


def _normalize_queue_record(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload or {})
    raw_status = normalized.get("status")
    normalized["status"] = _normalize_upload_queue_status(raw_status) or str(raw_status or "pending").lower()
    normalized["job_id"] = str(normalized.get("job_id") or "")
    normalized["attempts"] = int(normalized.get("attempts") or 0)
    normalized["last_error"] = normalized.get("last_error")
    normalized["created_at"] = str(normalized.get("created_at") or now_iso())
    normalized["updated_at"] = str(normalized.get("updated_at") or normalized["created_at"])
    normalized["locked_at"] = normalized.get("locked_at")
    return normalized


def _queue_sort_key(payload: dict[str, Any]) -> tuple[int, str, str]:
    return (
        _queue_status_rank(str(payload.get("status") or "")),
        _queue_timestamp(payload.get("created_at")),
        str(payload.get("job_id") or ""),
    )


def _write_s3_queue_job(payload: dict[str, Any]) -> None:
    client = _get_s3_client()
    bucket = _upload_state_bucket()
    if client is None or not bucket:
        raise RuntimeError("shared_upload_queue_client_unavailable")
    normalized = _normalize_queue_record(payload)
    client.put_object(
        Bucket=bucket,
        Key=_queue_object_key(str(normalized["job_id"])),
        Body=json.dumps(normalized, indent=2, default=str).encode("utf-8"),
        ContentType="application/json",
    )


def _read_s3_queue_job(job_id: str) -> dict[str, Any] | None:
    client = _get_s3_client()
    bucket = _upload_state_bucket()
    if client is None or not bucket:
        return None
    try:
        response = client.get_object(Bucket=bucket, Key=_queue_object_key(job_id))
    except Exception:
        return None
    try:
        body = response["Body"].read().decode("utf-8")
        payload = json.loads(body)
    except Exception:
        logger.exception("upload_queue_read_failed queue_backend=s3 job_id=%s", job_id)
        return None
    return _normalize_queue_record(payload) if isinstance(payload, dict) else None


def _list_s3_queue_jobs(*, statuses: set[str] | None = None) -> list[dict[str, Any]]:
    client = _get_s3_client()
    bucket = _upload_state_bucket()
    if not bucket:
        return []
    if client is None:
        raise RuntimeError("shared_upload_queue_client_unavailable")
    jobs: list[dict[str, Any]] = []
    continuation_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": _upload_queue_prefix()}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        response = client.list_objects_v2(**kwargs)
        for item in response.get("Contents") or []:
            key = str(item.get("Key") or "")
            if not key.endswith('.json'):
                continue
            try:
                body = client.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
                payload = json.loads(body)
            except Exception:
                logger.exception("upload_queue_list_read_failed queue_backend=s3 key=%s", key)
                continue
            if not isinstance(payload, dict):
                continue
            normalized = _normalize_queue_record(payload)
            if statuses and normalized["status"] not in statuses:
                continue
            jobs.append(normalized)
        if not response.get("IsTruncated"):
            break
        continuation_token = response.get("NextContinuationToken")
        if not continuation_token:
            break
    jobs.sort(key=_queue_sort_key)
    return jobs


def _queue_metrics_from_records(records: list[dict[str, Any]]) -> dict[str, int]:
    metrics = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    for record in records:
        status = _normalize_upload_queue_status(record.get("status")) or str(record.get("status") or "").lower()
        if status not in metrics:
            metrics[status] = 0
        metrics[status] += 1
    return metrics


def _queue_operational_metrics_from_records(records: list[dict[str, Any]]) -> dict[str, int | float | None]:
    now = datetime.now(timezone.utc)
    pending_records = sorted(
        [record for record in records if record.get("status") == "pending"],
        key=lambda record: _queue_timestamp(record.get("created_at")),
    )
    processing_records = sorted(
        [record for record in records if record.get("status") == "processing"],
        key=lambda record: _queue_timestamp(record.get("updated_at")),
    )

    pending_age = None
    processing_age = None
    try:
        if pending_records:
            created = datetime.fromisoformat(str(pending_records[0].get("created_at") or "").replace("Z", "+00:00"))
            pending_age = max(0.0, (now - created).total_seconds())
    except Exception:
        pending_age = None
    try:
        if processing_records:
            updated = datetime.fromisoformat(str(processing_records[0].get("updated_at") or "").replace("Z", "+00:00"))
            processing_age = max(0.0, (now - updated).total_seconds())
    except Exception:
        processing_age = None

    counts = _queue_metrics_from_records(records)
    return {
        "pending": int(counts.get("pending", 0)),
        "processing": int(counts.get("processing", 0)),
        "completed": int(counts.get("completed", 0)),
        "failed": int(counts.get("failed", 0)),
        "oldest_pending_age_seconds": round(pending_age, 2) if pending_age is not None else None,
        "oldest_processing_age_seconds": round(processing_age, 2) if processing_age is not None else None,
    }


def enqueue_upload_job(job_id: str) -> None:
    _ensure_shared_upload_queue_backend()
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        timestamp = now_iso()
        existing = _read_s3_queue_job(job_id) or {}
        _write_s3_queue_job(
            {
                "job_id": job_id,
                "status": "pending",
                "attempts": int(existing.get("attempts") or 0),
                "last_error": None,
                "created_at": existing.get("created_at") or timestamp,
                "updated_at": timestamp,
                "locked_at": None,
            }
        )
        logger.info("upload_queue_enqueued queue_backend=%s job_id=%s", backend, job_id)
        return

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
    logger.info("upload_queue_enqueued queue_backend=%s job_id=%s", backend, job_id)


def claim_next_upload_job() -> str | None:
    _ensure_shared_upload_queue_backend()
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        pending_jobs = _list_s3_queue_jobs(statuses={"pending"})
        logger.info(
            "upload_queue_claim_scan queue_backend=%s pending_job_count=%s",
            backend,
            len(pending_jobs),
        )
        if not pending_jobs:
            logger.info("upload_queue_no_pending_jobs queue_backend=%s pending_job_count=0 no_pending_jobs=true", backend)
            return None
        selected = pending_jobs[0]
        timestamp = now_iso()
        selected["status"] = "processing"
        selected["attempts"] = int(selected.get("attempts") or 0) + 1
        selected["updated_at"] = timestamp
        selected["locked_at"] = timestamp
        _write_s3_queue_job(selected)
        logger.info(
            "upload_queue_claimed queue_backend=%s pending_job_count=%s claimed_job_id=%s",
            backend,
            len(pending_jobs),
            selected["job_id"],
        )
        return str(selected["job_id"])

    init_runtime_db()
    with db_connection() as connection:
        pending_count_row = connection.execute(
            "SELECT COUNT(*) AS count FROM upload_queue WHERE status IN ('pending', 'queued')"
        ).fetchone()
        pending_count = int((pending_count_row["count"] if pending_count_row else 0) or 0)
        logger.info(
            "upload_queue_claim_scan queue_backend=%s pending_job_count=%s",
            backend,
            pending_count,
        )
        row = connection.execute(
            """
            SELECT job_id FROM upload_queue
            WHERE status IN ('pending', 'queued')
            ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            logger.info("upload_queue_no_pending_jobs queue_backend=%s pending_job_count=0 no_pending_jobs=true", backend)
            return None
        job_id = row["job_id"]
        timestamp = now_iso()
        connection.execute(
            """
            UPDATE upload_queue
            SET status='processing',
                attempts=attempts + 1,
                updated_at=?,
                locked_at=?
            WHERE job_id = ?
            """,
            (timestamp, timestamp, job_id),
        )
    logger.info(
        "upload_queue_claimed queue_backend=%s pending_job_count=%s claimed_job_id=%s",
        backend,
        pending_count,
        job_id,
    )
    return job_id


def peek_next_upload_job_for_worker() -> str | None:
    _ensure_shared_upload_queue_backend()
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        records = _list_s3_queue_jobs(statuses={"pending", "processing"})
        return None if not records else str(records[0]["job_id"])

    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT job_id
            FROM upload_queue
            WHERE status IN ('pending', 'processing')
            ORDER BY CASE status WHEN 'processing' THEN 0 ELSE 1 END, created_at ASC
            LIMIT 1
            """
        ).fetchone()
    return None if row is None else str(row["job_id"])


def mark_queue_job_failed(job_id: str, reason: str) -> None:
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        existing = _read_s3_queue_job(job_id) or {"job_id": job_id, "created_at": now_iso(), "attempts": 0}
        _write_s3_queue_job(
            {
                **existing,
                "job_id": job_id,
                "status": "failed",
                "last_error": reason,
                "updated_at": now_iso(),
                "locked_at": None,
            }
        )
        return

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
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        processing_jobs = _list_s3_queue_jobs(statuses={"processing"})
        for record in processing_jobs:
            _write_s3_queue_job(
                {
                    **record,
                    "status": "failed",
                    "last_error": "stale_processing_job_recovered",
                    "updated_at": now_iso(),
                    "locked_at": None,
                }
            )
        return len(processing_jobs)

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
    normalized_status = _normalize_upload_queue_status(status) or "completed"
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        existing = _read_s3_queue_job(job_id) or {"job_id": job_id, "created_at": now_iso(), "attempts": 0}
        _write_s3_queue_job(
            {
                **existing,
                "job_id": job_id,
                "status": normalized_status,
                "last_error": last_error,
                "updated_at": now_iso(),
                "locked_at": None,
            }
        )
        return

    init_runtime_db()
    with db_connection() as connection:
        connection.execute(
            """
            UPDATE upload_queue
            SET status = ?, last_error = ?, updated_at = ?, locked_at = NULL
            WHERE job_id = ?
            """,
            (normalized_status, last_error, now_iso(), job_id),
        )


def touch_upload_queue_job(job_id: str, status: str | None = None) -> None:
    normalized_status = _normalize_upload_queue_status(status)
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        existing = _read_s3_queue_job(job_id)
        if existing is None:
            return
        payload = {**existing, "updated_at": now_iso()}
        if normalized_status:
            payload["status"] = normalized_status
        _write_s3_queue_job(payload)
        return

    init_runtime_db()
    with db_connection() as connection:
        if normalized_status:
            connection.execute(
                """
                UPDATE upload_queue
                SET status = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (normalized_status, now_iso(), job_id),
            )
        else:
            connection.execute(
                """
                UPDATE upload_queue
                SET updated_at = ?
                WHERE job_id = ?
                """,
                (now_iso(), job_id),
            )


def read_upload_queue_job(job_id: str) -> dict[str, Any] | None:
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        record = _read_s3_queue_job(job_id)
        if record is None:
            return None
        position = None
        if record.get("status") == "pending":
            pending_jobs = _list_s3_queue_jobs(statuses={"pending"})
            for index, pending_record in enumerate(pending_jobs, start=1):
                if str(pending_record.get("job_id")) == job_id:
                    position = index
                    break
        return {**record, "queue_position": position}

    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT job_id, status, attempts, last_error, created_at, updated_at, locked_at
            FROM upload_queue
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        raw_status = str(row["status"] or "").lower()
        normalized_status = _normalize_upload_queue_status(raw_status) or raw_status
        position = None
        if normalized_status == "pending":
            pos_row = connection.execute(
                """
                SELECT COUNT(*) AS ahead
                FROM upload_queue
                WHERE status IN ('pending', 'queued')
                  AND created_at < ?
                """,
                (row["created_at"],),
            ).fetchone()
            position = int((pos_row["ahead"] if pos_row else 0) or 0) + 1
    return {
        "job_id": row["job_id"],
        "status": normalized_status,
        "attempts": row["attempts"],
        "last_error": row["last_error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "locked_at": row["locked_at"],
        "queue_position": position,
    }


def queue_metrics() -> dict[str, int]:
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        return _queue_metrics_from_records(_list_s3_queue_jobs())

    init_runtime_db()
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM upload_queue GROUP BY status"
        ).fetchall()
    metrics = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    for row in rows:
        metrics[row["status"]] = row["count"]
    return metrics


def queue_operational_metrics() -> dict[str, int | float | None]:
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        return _queue_operational_metrics_from_records(_list_s3_queue_jobs())

    init_runtime_db()
    with db_connection() as connection:
        oldest_pending = connection.execute(
            """
            SELECT created_at
            FROM upload_queue
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        oldest_processing = connection.execute(
            """
            SELECT updated_at
            FROM upload_queue
            WHERE status = 'processing'
            ORDER BY updated_at ASC
            LIMIT 1
            """
        ).fetchone()

    now = datetime.now(timezone.utc)
    pending_age = None
    processing_age = None
    try:
        if oldest_pending and oldest_pending["created_at"]:
            created = datetime.fromisoformat(str(oldest_pending["created_at"]).replace("Z", "+00:00"))
            pending_age = max(0.0, (now - created).total_seconds())
    except Exception:
        pending_age = None
    try:
        if oldest_processing and oldest_processing["updated_at"]:
            updated = datetime.fromisoformat(str(oldest_processing["updated_at"]).replace("Z", "+00:00"))
            processing_age = max(0.0, (now - updated).total_seconds())
    except Exception:
        processing_age = None

    counts = queue_metrics()
    return {
        "pending": int(counts.get("pending", 0)),
        "processing": int(counts.get("processing", 0)),
        "completed": int(counts.get("completed", 0)),
        "failed": int(counts.get("failed", 0)),
        "oldest_pending_age_seconds": round(pending_age, 2) if pending_age is not None else None,
        "oldest_processing_age_seconds": round(processing_age, 2) if processing_age is not None else None,
    }


def clear_upload_runtime_tables() -> None:
    if upload_queue_backend() == "s3" and _upload_state_bucket():
        client = _get_s3_client()
        bucket = _upload_state_bucket()
        if client is not None and bucket:
            for record in _list_s3_queue_jobs():
                try:
                    client.delete_object(Bucket=bucket, Key=_queue_object_key(str(record.get("job_id") or "")))
                except Exception:
                    logger.exception(
                        "upload_queue_delete_failed queue_backend=s3 job_id=%s",
                        record.get("job_id"),
                    )
    init_runtime_db()
    with db_connection() as connection:
        connection.execute("DELETE FROM upload_queue")
        connection.execute("DELETE FROM upload_jobs")


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


def delete_latest_payload_prefix(prefix: str) -> int:
    init_runtime_db()
    with db_connection() as connection:
        deleted = connection.execute(
            "DELETE FROM latest_payloads WHERE key LIKE ?",
            (f"{prefix}%",),
        ).rowcount
    return int(deleted or 0)


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
