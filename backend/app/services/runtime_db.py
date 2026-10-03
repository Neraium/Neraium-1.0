from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from app.core.config import get_settings
from app.services import runtime_postgres
from app.services.schema_verification import load_contract, verify_sqlite_file
from app.services.dataset_scope import (
    attach_dataset_scope,
    build_upload_queue_routing,
    current_dataset_scope,
    dataset_scope_context,
    dataset_scope_from_payload,
    dataset_scope_from_queue_routing,
)
from app.services.phase4_scope import (
    ServerBoundSystemIdentity,
    build_upload_queue_phase4_scope_envelope,
)


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


def _require_upload_queue_status(status: str | None, allowed: set[str]) -> str:
    normalized = _normalize_upload_queue_status(status)
    if normalized not in allowed:
        raise ValueError("invalid_upload_queue_status_transition")
    return normalized


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    if runtime_postgres.database_url():
        with runtime_postgres.connect() as connection:
            yield connection
        return
    ensure_runtime_dir()
    connection = sqlite3.connect(f"{DB_PATH.resolve().as_uri()}?mode=rw", uri=True, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_runtime_db() -> None:
    """Verify existing schema only. Run db.migrations.apply_runtime before startup."""
    if runtime_postgres.database_url():
        runtime_postgres.initialize()
        return
    verify_sqlite_file(DB_PATH, "runtime_sqlite")


# Public compatibility for callers inspecting the expected ledger, without
# importing migration implementations into ordinary runtime startup.
RUNTIME_SCHEMA_MIGRATIONS = tuple(load_contract("runtime_sqlite")["migration_ids"])


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


def _normalize_queue_record(
    payload: dict[str, Any],
    *,
    fallback_job_id: str | None = None,
) -> dict[str, Any]:
    normalized = dict(payload or {})
    raw_status = normalized.get("status")
    normalized["status"] = _normalize_upload_queue_status(raw_status) or str(raw_status or "pending").lower()
    normalized["job_id"] = str(normalized.get("job_id") or fallback_job_id or "")
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
    except Exception as exc:
        error_code = str(
            getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        )
        if isinstance(exc, KeyError) or error_code in {"404", "NoSuchKey", "NotFound"}:
            return None
        logger.exception(
            "upload_queue_read_failed queue_backend=s3 job_id=%s",
            job_id,
        )
        raise RuntimeError("shared_upload_queue_read_failed") from exc
    try:
        body = response["Body"].read().decode("utf-8")
        payload = json.loads(body)
    except Exception:
        logger.exception("upload_queue_read_failed queue_backend=s3 job_id=%s", job_id)
        return None
    return _normalize_queue_record(payload, fallback_job_id=job_id) if isinstance(payload, dict) else None


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
            object_job_id = key.rsplit("/", 1)[-1].removesuffix(".json")
            normalized = _normalize_queue_record(payload, fallback_job_id=object_job_id)
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


def _current_upload_queue_routing(
    *,
    job_id: str,
    system_identity: ServerBoundSystemIdentity | None,
    dataset_id: Any,
    upload_session_id: Any,
) -> dict[str, Any]:
    dataset_scope = current_dataset_scope()
    phase4_envelope = build_upload_queue_phase4_scope_envelope(
        dataset_scope=dataset_scope,
        system_identity=system_identity,
        job_id=job_id,
        dataset_id=dataset_id,
        upload_session_id=upload_session_id,
    )
    return build_upload_queue_routing(
        dataset_scope,
        phase4_scope_envelope=phase4_envelope,
    )


def _resolve_enqueue_routing(
    *,
    generated_routing: dict[str, Any],
    existing_routing: dict[str, Any] | None,
    existing_status: str | None,
    preserve_existing_routing: bool,
) -> dict[str, Any]:
    if existing_routing is None:
        if existing_status in {"pending", "processing"}:
            raise RuntimeError("upload_queue_routing_missing")
        if existing_status is not None:
            # A legacy retry may recover its authenticated DatasetScope, but it
            # must never acquire Phase 4 system authority retroactively.
            return build_upload_queue_routing(current_dataset_scope())
        return generated_routing
    try:
        existing_scope = dataset_scope_from_queue_routing({"routing": existing_routing})
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    if existing_scope != current_dataset_scope():
        raise RuntimeError("upload_queue_scope_conflict")
    if preserve_existing_routing:
        return existing_routing
    if existing_routing != generated_routing:
        raise RuntimeError("upload_queue_phase4_scope_conflict")
    return existing_routing


@runtime_postgres.shared_queue_transaction
def enqueue_upload_job(
    job_id: str,
    *,
    system_identity: ServerBoundSystemIdentity | None = None,
    dataset_id: Any = None,
    upload_session_id: Any = None,
    preserve_existing_routing: bool = False,
) -> None:
    routing = _current_upload_queue_routing(
        job_id=job_id,
        system_identity=system_identity,
        dataset_id=dataset_id,
        upload_session_id=upload_session_id,
    )
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        timestamp = now_iso()
        existing_record = _read_s3_queue_job(job_id)
        existing = existing_record or {}
        if existing_record is not None:
            try:
                routing = _resolve_enqueue_routing(
                    generated_routing=routing,
                    existing_routing=(
                        existing.get("routing") if isinstance(existing.get("routing"), dict) else None
                    ),
                    existing_status=_normalize_upload_queue_status(existing.get("status")),
                    preserve_existing_routing=preserve_existing_routing,
                )
            except RuntimeError as exc:
                if _normalize_upload_queue_status(existing.get("status")) in {"pending", "processing"}:
                    _write_s3_queue_job(
                        {
                            **existing,
                            "status": "failed",
                            "last_error": str(exc),
                            "updated_at": timestamp,
                            "locked_at": None,
                        }
                    )
                raise
        if _normalize_upload_queue_status(existing.get("status")) in {"pending", "processing"}:
            logger.info("upload_queue_duplicate_enqueue_ignored queue_backend=%s job_id=%s status=%s", backend, job_id, existing.get("status"))
            return
        _write_s3_queue_job(
            {
                "job_id": job_id,
                "status": "pending",
                "attempts": int(existing.get("attempts") or 0),
                "last_error": None,
                "created_at": existing.get("created_at") or timestamp,
                "updated_at": timestamp,
                "locked_at": None,
                "routing": routing,
            }
        )
        logger.info("upload_queue_enqueued queue_backend=%s job_id=%s", backend, job_id)
        return

    init_runtime_db()
    timestamp = now_iso()
    with db_connection() as connection:
        existing_row = connection.execute(
            """
            SELECT q.status, r.routing_json
            FROM upload_queue AS q
            LEFT JOIN upload_queue_routing AS r ON r.job_id = q.job_id
            WHERE q.job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if existing_row is not None:
            try:
                existing_routing = json.loads(existing_row["routing_json"])
            except (TypeError, json.JSONDecodeError):
                existing_routing = None
            routing = _resolve_enqueue_routing(
                generated_routing=routing,
                existing_routing=existing_routing if isinstance(existing_routing, dict) else None,
                existing_status=_normalize_upload_queue_status(existing_row["status"]),
                preserve_existing_routing=preserve_existing_routing,
            )
        connection.execute(
            """
            INSERT INTO upload_queue (job_id, status, attempts, last_error, created_at, updated_at, locked_at)
            VALUES (?, 'pending', 0, NULL, ?, ?, NULL)
            ON CONFLICT(job_id) DO UPDATE SET
                status='pending',
                updated_at=excluded.updated_at,
                last_error=NULL,
                locked_at=NULL
            WHERE upload_queue.status NOT IN ('pending', 'processing')
            """,
            (job_id, timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO upload_queue_routing (job_id, routing_json, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET routing_json=excluded.routing_json
            """,
            (job_id, json.dumps(routing, sort_keys=True), timestamp),
        )
    logger.info("upload_queue_enqueued queue_backend=%s job_id=%s", backend, job_id)


@runtime_postgres.shared_queue_transaction
def claim_next_upload_job_record() -> dict[str, Any] | None:
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
        return dict(selected)

    init_runtime_db()
    with db_connection() as connection:
        # Serialize the select-and-transition across processes. A deferred SQLite
        # transaction permits two readers to select the same row before either
        # writes; BEGIN IMMEDIATE reserves the writer lock before the read.
        connection.execute("BEGIN IMMEDIATE")
        pending_count_row = connection.execute(
            "SELECT COUNT(*) AS count FROM upload_queue WHERE status = 'pending'"
        ).fetchone()
        pending_count = int((pending_count_row["count"] if pending_count_row else 0) or 0)
        logger.info(
            "upload_queue_claim_scan queue_backend=%s pending_job_count=%s",
            backend,
            pending_count,
        )
        row = connection.execute(
            """
            SELECT q.job_id, q.status, q.attempts, q.last_error,
                   q.created_at, q.updated_at, q.locked_at, r.routing_json
            FROM upload_queue AS q
            INNER JOIN upload_jobs AS j ON j.job_id = q.job_id
            LEFT JOIN upload_queue_routing AS r ON r.job_id = q.job_id
            WHERE q.status = 'pending'
            ORDER BY q.created_at ASC, q.job_id ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            logger.info("upload_queue_no_pending_jobs queue_backend=%s pending_job_count=0 no_pending_jobs=true", backend)
            return None
        job_id = str(row["job_id"])
        timestamp = now_iso()
        updated = connection.execute(
            """
            UPDATE upload_queue
            SET status='processing',
                attempts=attempts + 1,
                updated_at=?,
                locked_at=?
            WHERE job_id = ? AND status = 'pending'
            """,
            (timestamp, timestamp, job_id),
        ).rowcount
        if updated != 1:
            return None
    logger.info(
        "upload_queue_claimed queue_backend=%s pending_job_count=%s claimed_job_id=%s",
        backend,
        pending_count,
        job_id,
    )
    claimed_record = {
        "job_id": job_id,
        "status": "processing",
        "attempts": int(row["attempts"] or 0) + 1,
        "last_error": row["last_error"],
        "created_at": row["created_at"],
        "updated_at": timestamp,
        "locked_at": timestamp,
    }
    try:
        routing = json.loads(row["routing_json"])
    except (TypeError, json.JSONDecodeError):
        routing = None
    if isinstance(routing, dict):
        claimed_record["routing"] = routing
    return claimed_record


def claim_next_upload_job() -> str | None:
    """Compatibility wrapper for callers that only need the claimed job ID."""
    record = claim_next_upload_job_record()
    return None if record is None else str(record.get("job_id") or "") or None


def peek_next_upload_job_for_worker() -> str | None:
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


@runtime_postgres.shared_queue_transaction
def mark_queue_job_failed(job_id: str, reason: str) -> None:
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        existing = _read_s3_queue_job(job_id) or {"job_id": job_id, "created_at": now_iso(), "attempts": 0}
        if _normalize_upload_queue_status(existing.get("status")) == "completed":
            return
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
            WHERE job_id = ? AND status IN ('pending', 'processing', 'failed')
            """,
            (reason, now_iso(), job_id),
        )


def _publish_interrupted_upload_status(queue_records: list[dict[str, Any]]) -> dict[str, str]:
    if not queue_records:
        return {}
    # Lazy imports avoid a module cycle: the upload-state repository uses this
    # runtime store for its durable payload backend.
    from app.services.evidence_store import read_evidence_run, upsert_evidence_run
    from app.services.job_progress import fail_progress
    from app.services.upload_state_repository import (
        persist_latest_upload_state,
        read_latest_upload_record,
        read_upload_status,
        write_upload_status,
    )

    recovered_at = now_iso()
    terminal_outcomes: dict[str, str] = {}
    for record in queue_records:
        job_id = str(record.get("job_id") or "").strip()
        if not job_id:
            continue
        try:
            scope = dataset_scope_from_queue_routing(record)
        except ValueError as exc:
            if upload_queue_backend() == "s3":
                scope = None
            else:
                local_payload = read_upload_job(job_id) or {}
                scope = dataset_scope_from_payload(local_payload) or current_dataset_scope()
            if scope is None:
                logger.error(
                    "stale_upload_status_routing_failed job_id=%s reason=%s",
                    job_id,
                    str(exc),
                )
                continue

        with dataset_scope_context(scope):
            canonical = read_latest_upload_record() or {}
            canonical_summary = canonical.get("summary") if isinstance(canonical.get("summary"), dict) else {}
            canonical_job_id = str(canonical.get("job_id") or canonical_summary.get("job_id") or "")
            current = read_upload_status(job_id) or read_upload_job(job_id) or {"job_id": job_id}
            current_state = str(current.get("processing_state") or current.get("status") or "").strip().lower()
            if current_state in {"complete", "completed", "completed_compatibility", "success"}:
                terminal_outcomes[job_id] = "completed"
                continue
            if current_state in {"cancelled", "error", "failed", "failure", "timeout", "validation_error"}:
                terminal_outcomes[job_id] = "failed"
                continue
            failed = {
                **current,
                "job_id": job_id,
                "run_id": current.get("run_id") or job_id,
                "upload_id": current.get("upload_id") or job_id,
                "status": "FAILED",
                "processing_state": "failed",
                "error_type": "interrupted_upload",
                "error": "Upload processing was interrupted by a service restart.",
                "message": "Upload processing was interrupted by a service restart. Retry the analysis.",
                "progress_label": "Processing interrupted. Retry the analysis.",
                "result_available": False,
                "first_usable_available": False,
                "sii_completed": False,
                "replay_ready": False,
                "replay_frame_count": 0,
                "propagation_stage": "failed",
                "propagation_label": "Interrupted by restart.",
                "worker_state": "stopped",
                "updated_at": recovered_at,
            }
            current_progress = current.get("job_progress")
            if isinstance(current_progress, dict):
                failed_progress = fail_progress(
                    current_progress,
                    job_id=job_id,
                    workflow=str(
                        current_progress.get("workflow")
                        or current.get("workflow")
                        or "legacy_analysis"
                    ),
                    message=failed["message"],
                    retryable=True,
                )
                overall_progress = int(failed_progress.get("overall_percent_complete") or 0)
                failed.update(
                    {
                        "job_progress": failed_progress,
                        "percent": overall_progress,
                        "progress": overall_progress,
                        "contract_progress": overall_progress,
                        "propagation_progress": overall_progress,
                    }
                )
            published = write_upload_status(job_id, failed)
            published_state = str(
                published.get("processing_state")
                or published.get("status")
                or ""
            ).strip().lower()
            if published_state in {"complete", "completed", "completed_compatibility", "success"}:
                terminal_outcomes[job_id] = "completed"
                upsert_upload_job(published)
                continue
            if published_state not in {
                "cancelled",
                "error",
                "failed",
                "failure",
                "timeout",
                "validation_error",
            }:
                continue
            failed = published
            upsert_upload_job(failed)

            evidence = read_evidence_run(job_id)
            if isinstance(evidence, dict) and str(evidence.get("status") or "").lower() not in {"completed", "failed"}:
                errors = list(evidence.get("errors") or [])
                interruption = "Upload processing was interrupted by a service restart."
                if interruption not in errors:
                    errors.append(interruption)
                upsert_evidence_run(
                    {
                        **evidence,
                        "status": "failed",
                        "observation_status": "failed",
                        "completed_at": recovered_at,
                        "errors": errors,
                    }
                )

            if job_id == canonical_job_id:
                persist_latest_upload_state(summary=failed, result=None, keep_result=False)
            terminal_outcomes[job_id] = "failed"
    return terminal_outcomes


def _shared_processing_job_is_stale(record: dict[str, Any]) -> bool:
    try:
        updated = datetime.fromisoformat(str(record.get("updated_at") or "").replace("Z", "+00:00"))
        if updated.tzinfo is None:
            return False
        age = (datetime.now(UTC) - updated).total_seconds()
    except ValueError:
        return False  # Missing heartbeat evidence is not proof that ownership ended.
    return age > get_settings().worker_heartbeat_timeout_seconds


@runtime_postgres.shared_queue_transaction
def clear_stale_processing_queue_jobs() -> int:
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        processing_jobs = _list_s3_queue_jobs(statuses={"processing"})
        if runtime_postgres.database_url():
            processing_jobs = [record for record in processing_jobs if _shared_processing_job_is_stale(record)]
        terminal_outcomes = _publish_interrupted_upload_status(processing_jobs)
        for record in processing_jobs:
            job_id = str(record.get("job_id") or "")
            terminal_status = terminal_outcomes.get(job_id)
            if terminal_status is None:
                continue
            _write_s3_queue_job(
                {
                    **record,
                    "status": terminal_status,
                    "last_error": (
                        "stale_processing_job_recovered"
                        if terminal_status == "failed"
                        else None
                    ),
                    "updated_at": now_iso(),
                    "locked_at": None,
                }
            )
        return len(terminal_outcomes)

    init_runtime_db()
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT job_id, updated_at FROM upload_queue WHERE status = 'processing'"
        ).fetchall()
        stale_job_ids = [row["job_id"] for row in rows
                         if not runtime_postgres.database_url() or _shared_processing_job_is_stale(dict(row))]
    terminal_outcomes = _publish_interrupted_upload_status(
        [{"job_id": job_id} for job_id in stale_job_ids]
    )
    if terminal_outcomes:
        with db_connection() as connection:
            connection.executemany(
                """
                UPDATE upload_queue
                SET status='failed', last_error=?, updated_at=?, locked_at=NULL
                WHERE job_id = ?
                """,
                [
                    ("stale_processing_job_recovered", now_iso(), job_id)
                    for job_id, status in terminal_outcomes.items()
                    if status == "failed"
                ],
            )
            connection.executemany(
                """
                UPDATE upload_queue
                SET status='completed', last_error=NULL, updated_at=?, locked_at=NULL
                WHERE job_id = ?
                """,
                [
                    (now_iso(), job_id)
                    for job_id, status in terminal_outcomes.items()
                    if status == "completed"
                ],
            )
    return len(terminal_outcomes)


@runtime_postgres.shared_queue_transaction
def complete_upload_queue_job(job_id: str, status: str, last_error: str | None = None) -> None:
    normalized_status = _require_upload_queue_status(status, {"completed", "failed"})
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        existing = _read_s3_queue_job(job_id) or {"job_id": job_id, "created_at": now_iso(), "attempts": 0}
        current_status = _normalize_upload_queue_status(existing.get("status"))
        allowed_sources = {"processing", "completed"} if normalized_status == "completed" else {"pending", "processing", "failed"}
        if current_status is not None and current_status not in allowed_sources:
            return
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
    allowed_sources = ("processing", "completed") if normalized_status == "completed" else ("pending", "processing", "failed")
    placeholders = ", ".join("?" for _ in allowed_sources)
    with db_connection() as connection:
        connection.execute(
            f"""
            UPDATE upload_queue
            SET status = ?, last_error = ?, updated_at = ?, locked_at = NULL
            WHERE job_id = ? AND status IN ({placeholders})
            """,
            (normalized_status, last_error, now_iso(), job_id, *allowed_sources),
        )


@runtime_postgres.shared_queue_transaction
def touch_upload_queue_job(job_id: str, status: str | None = None) -> None:
    normalized_status = (
        _require_upload_queue_status(status, {"processing"}) if status is not None else None
    )
    backend = upload_queue_backend()
    if backend == "s3":
        _ensure_shared_upload_queue_backend()
        existing = _read_s3_queue_job(job_id)
        if existing is None:
            return
        payload = {**existing, "updated_at": now_iso()}
        if normalized_status:
            if _normalize_upload_queue_status(existing.get("status")) != "processing":
                return
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
                WHERE job_id = ? AND status = 'processing'
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
            SELECT q.job_id, q.status, q.attempts, q.last_error,
                   q.created_at, q.updated_at, q.locked_at, r.routing_json
            FROM upload_queue AS q
            LEFT JOIN upload_queue_routing AS r ON r.job_id = q.job_id
            WHERE q.job_id = ?
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
    try:
        routing = json.loads(row["routing_json"])
    except (TypeError, json.JSONDecodeError):
        routing = None
    result = {
        "job_id": row["job_id"],
        "status": normalized_status,
        "attempts": row["attempts"],
        "last_error": row["last_error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "locked_at": row["locked_at"],
        "queue_position": position,
    }
    if isinstance(routing, dict):
        result["routing"] = routing
    return result


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


def insert_latest_payload_if_absent(key: str, payload: Any) -> tuple[bool, Any]:
    """Atomically publish one immutable payload without replacing a prior value."""
    init_runtime_db()
    serialized = json.dumps(payload)
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            INSERT INTO latest_payloads (key, updated_at, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO NOTHING
            """,
            (key, now_iso(), serialized),
        )
        row = connection.execute(
            "SELECT payload_json FROM latest_payloads WHERE key = ?",
            (key,),
        ).fetchone()
    if row is None:
        raise RuntimeError("latest_payload_insert_failed")
    return cursor.rowcount == 1, json.loads(row["payload_json"])


def mutate_latest_payload(key: str, mutator: Callable[[Any | None], Any]) -> Any:
    """Atomically read, mutate, and persist one JSON payload.

    BEGIN IMMEDIATE prevents two ingestion processes from reading the same
    buffer version and then overwriting each other's append.
    """
    init_runtime_db()
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT payload_json FROM latest_payloads WHERE key = ?",
            (key,),
        ).fetchone()
        current = json.loads(row["payload_json"]) if row is not None else None
        updated = mutator(current)
        connection.execute(
            """
            INSERT INTO latest_payloads (key, updated_at, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                updated_at=excluded.updated_at,
                payload_json=excluded.payload_json
            """,
            (key, now_iso(), json.dumps(updated)),
        )
    return updated


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


def read_latest_payload_pure(key: str) -> Any | None:
    """Read without initializing, migrating, creating, or writing the database."""
    if runtime_postgres.database_url():
        with runtime_postgres.connect(readonly=True) as connection:
            row = connection.execute("SELECT payload_json FROM latest_payloads WHERE key = ?", (key,)).fetchone()
        return json.loads(row["payload_json"]) if row is not None else None
    path = Path(DB_PATH)
    if not path.exists():
        return None
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
        timeout=30,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT payload_json FROM latest_payloads WHERE key = ?",
            (key,),
        ).fetchone()
    finally:
        connection.close()
    return json.loads(row["payload_json"]) if row is not None else None


def list_latest_payloads_prefix(prefix: str) -> list[Any]:
    """List independently keyed payloads using a fresh database connection."""
    init_runtime_db()
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM latest_payloads WHERE key LIKE ? ORDER BY key ASC",
            (f"{prefix}%",),
        ).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def list_latest_payloads_prefix_pure(prefix: str) -> list[Any]:
    """List immutable payloads without touching runtime schema or timestamps."""
    if runtime_postgres.database_url():
        with runtime_postgres.connect(readonly=True) as connection:
            rows = connection.execute(
                "SELECT payload_json FROM latest_payloads WHERE key LIKE ? ORDER BY key ASC", (f"{prefix}%",)
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]
    path = Path(DB_PATH)
    if not path.exists():
        return []
    connection = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode=ro",
        uri=True,
        timeout=30,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT payload_json FROM latest_payloads WHERE key LIKE ? ORDER BY key ASC",
            (f"{prefix}%",),
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row["payload_json"]) for row in rows]


def delete_latest_payload_prefix(prefix: str) -> int:
    init_runtime_db()
    with db_connection() as connection:
        deleted = connection.execute(
            "DELETE FROM latest_payloads WHERE key LIKE ?",
            (f"{prefix}%",),
        ).rowcount
    return int(deleted or 0)


def upsert_evidence_runs_db(records: list[dict[str, Any]]) -> int:
    prepared = []
    for source in records:
        record = dict(source)
        scope = dataset_scope_from_payload(record) or current_dataset_scope()
        attach_dataset_scope(record, scope=scope, dataset_id=record.get("dataset_id"))
        prepared.append(
            (
                record["run_id"],
                record.get("created_at") or now_iso(),
                record.get("completed_at"),
                record.get("status", "pending"),
                record.get("source_name"),
                scope.storage_id,
                json.dumps(record),
            )
        )
    if not prepared:
        return 0
    init_runtime_db()
    with db_connection() as connection:
        for run_id, *_values, scope_storage_id, _payload_json in prepared:
            existing = connection.execute(
                "SELECT scope_storage_id FROM evidence_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if existing is not None and existing["scope_storage_id"] != scope_storage_id:
                raise ValueError("evidence_run_scope_conflict")
        connection.executemany(
            """
            INSERT INTO evidence_runs (
                run_id, created_at, completed_at, status, source_name,
                scope_storage_id, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                created_at=excluded.created_at,
                completed_at=excluded.completed_at,
                status=excluded.status,
                source_name=excluded.source_name,
                scope_storage_id=excluded.scope_storage_id,
                payload_json=excluded.payload_json
            """,
            prepared,
        )
    return len(prepared)


def upsert_evidence_run_db(record: dict[str, Any]) -> None:
    upsert_evidence_runs_db([record])


def list_evidence_runs_db(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    init_runtime_db()
    bounded_limit = max(1, min(int(limit), 1001))
    bounded_offset = max(0, int(offset))
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM evidence_runs WHERE scope_storage_id = ? "
            "ORDER BY created_at DESC, run_id DESC LIMIT ? OFFSET ?",
            (current_dataset_scope().storage_id, bounded_limit, bounded_offset),
        ).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def read_evidence_run_db(run_id: str) -> dict[str, Any] | None:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT payload_json FROM evidence_runs WHERE run_id = ? AND scope_storage_id = ?",
            (run_id, current_dataset_scope().storage_id),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload_json"])


def append_operator_feedback_event_db(run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    return _append_evidence_event(
        table="operator_feedback_events",
        run_id=run_id,
        event=event,
        extra_columns=("category",),
        extra_values=(str(event.get("category") or ""),),
    )


def append_finding_status_event_db(run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    return _append_evidence_event(
        table="finding_status_events",
        run_id=run_id,
        event=event,
        extra_columns=("state",),
        extra_values=(str(event.get("state") or ""),),
    )


def append_evidence_audit_tag_event_db(run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    return _append_evidence_event(
        table="evidence_audit_tag_events",
        run_id=run_id,
        event=event,
    )


def _append_evidence_event(
    *,
    table: str,
    run_id: str,
    event: dict[str, Any],
    extra_columns: tuple[str, ...] = (),
    extra_values: tuple[Any, ...] = (),
) -> dict[str, Any]:
    allowed_tables = {
        "operator_feedback_events",
        "finding_status_events",
        "evidence_audit_tag_events",
    }
    if table not in allowed_tables:
        raise ValueError("invalid_evidence_event_table")
    init_runtime_db()
    persisted = {
        **event,
        "event_id": str(event.get("event_id") or uuid.uuid4().hex),
        "run_id": str(run_id),
    }
    columns = ("event_id", "run_id", "recorded_at", "actor", *extra_columns, "payload_json")
    placeholders = ", ".join("?" for _ in columns)
    values = (
        persisted["event_id"],
        persisted["run_id"],
        str(persisted.get("recorded_at") or now_iso()),
        str(persisted.get("actor") or "operator"),
        *extra_values,
        json.dumps(persisted),
    )
    with db_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM evidence_runs WHERE run_id = ? AND scope_storage_id = ?",
            (run_id, current_dataset_scope().storage_id),
        ).fetchone()
        if exists is None:
            raise ValueError("evidence_run_not_found")
        connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
    return persisted


def hydrate_evidence_event_history_db(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scope = current_dataset_scope()
    scoped_records = [
        record for record in records
        if dataset_scope_from_payload(record) == scope
    ]
    run_ids = [
        str(record.get("run_id") or "") for record in scoped_records if record.get("run_id")
    ]
    if not run_ids:
        return []
    init_runtime_db()
    placeholders = ", ".join("?" for _ in run_ids)
    event_sets: dict[str, dict[str, list[dict[str, Any]]]] = {
        run_id: {"feedback": [], "status": [], "audit": []} for run_id in run_ids
    }
    with db_connection() as connection:
        for table, bucket in (
            ("operator_feedback_events", "feedback"),
            ("finding_status_events", "status"),
            ("evidence_audit_tag_events", "audit"),
        ):
            rows = connection.execute(
                f"SELECT run_id, payload_json FROM {table} WHERE run_id IN ({placeholders}) ORDER BY recorded_at DESC, event_id DESC",
                tuple(run_ids),
            ).fetchall()
            for row in rows:
                event_sets[str(row["run_id"])][bucket].append(json.loads(row["payload_json"]))
    hydrated = []
    for source in scoped_records:
        record = dict(source)
        events = event_sets.get(str(record.get("run_id") or ""), {})
        # New writes for an unambiguous one-finding run live only in the
        # canonical sidecar. Historical run-level events remain in their legacy
        # tables and are not copied back, preventing compatibility duplicates.
        from app.services.finding_workflow import (
            compatibility_events_for_run,
            materialize_evidence_finding_cases,
        )

        materialize_evidence_finding_cases(record)
        compatibility = compatibility_events_for_run(str(record.get("run_id") or ""))
        feedback = [
            *compatibility.get("feedback", []),
            *events.get("feedback", []),
            *list(record.get("operator_feedback_history") or []),
        ]
        statuses = [
            *compatibility.get("status", []),
            *events.get("status", []),
            *list(record.get("finding_status_history") or []),
        ]
        audit_tags = [*events.get("audit", []), *list(record.get("audit_tags") or [])]
        record["operator_feedback_history"] = feedback
        record["finding_status_history"] = statuses
        record["audit_tags"] = audit_tags
        if feedback:
            record["latest_feedback_category"] = feedback[0].get("category")
        if statuses:
            record["observation_status"] = statuses[0].get("state")
            record["finding_owner"] = statuses[0].get("owner") or statuses[0].get("actor")
            record["finding_assignee"] = statuses[0].get("assignee")
            record["work_order_reference"] = statuses[0].get("work_order_reference")
        hydrated.append(record)
    return hydrated


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


def upsert_auth_user(payload: dict[str, Any]) -> None:
    init_runtime_db()
    timestamp = now_iso()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_users (
                email, name, role, salt, password_hash, created_at, updated_at,
                last_login_at, is_active, deactivated_at, bootstrap_managed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                name=excluded.name,
                role=excluded.role,
                salt=excluded.salt,
                password_hash=excluded.password_hash,
                updated_at=excluded.updated_at,
                last_login_at=excluded.last_login_at,
                is_active=excluded.is_active,
                deactivated_at=excluded.deactivated_at,
                bootstrap_managed=excluded.bootstrap_managed
            """,
            (
                payload["email"],
                payload.get("name") or payload["email"],
                payload.get("role", "operator"),
                payload.get("salt", ""),
                payload.get("password_hash", ""),
                payload.get("created_at") or timestamp,
                payload.get("updated_at") or timestamp,
                payload.get("last_login_at"),
                1 if payload.get("is_active", True) else 0,
                payload.get("deactivated_at"),
                1 if payload.get("bootstrap_managed") else 0,
            ),
        )


def read_auth_user(email: str) -> dict[str, Any] | None:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM auth_users WHERE email = ?",
            (email,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def list_auth_users(include_inactive: bool = True, limit: int = 500) -> list[dict[str, Any]]:
    init_runtime_db()
    query = "SELECT * FROM auth_users"
    params: list[Any] = []
    if not include_inactive:
        query += " WHERE is_active = 1"
    query += " ORDER BY created_at ASC LIMIT ?"
    params.append(limit)
    with db_connection() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def set_auth_user_login(email: str, logged_in_at: str) -> None:
    init_runtime_db()
    with db_connection() as connection:
        connection.execute(
            """
            UPDATE auth_users
            SET last_login_at = ?, updated_at = ?
            WHERE email = ?
            """,
            (logged_in_at, logged_in_at, email),
        )


def set_auth_user_active_status(email: str, *, is_active: bool) -> dict[str, Any] | None:
    init_runtime_db()
    timestamp = now_iso()
    deactivated_at = None if is_active else timestamp
    with db_connection() as connection:
        connection.execute(
            """
            UPDATE auth_users
            SET is_active = ?, deactivated_at = ?, updated_at = ?
            WHERE email = ?
            """,
            (1 if is_active else 0, deactivated_at, timestamp, email),
        )
    return read_auth_user(email)


def upsert_auth_session(payload: dict[str, Any]) -> None:
    init_runtime_db()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_sessions (session_id, email, created_at, expires_at, last_seen_at, revoked_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                email=excluded.email,
                created_at=excluded.created_at,
                expires_at=excluded.expires_at,
                last_seen_at=excluded.last_seen_at,
                revoked_at=excluded.revoked_at
            """,
            (
                payload["session_id"],
                payload["email"],
                payload.get("created_at") or now_iso(),
                payload.get("expires_at") or now_iso(),
                payload.get("last_seen_at"),
                payload.get("revoked_at"),
            ),
        )


def read_auth_session(session_id: str) -> dict[str, Any] | None:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM auth_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def list_auth_sessions(*, email: str | None = None, include_revoked: bool = False, limit: int = 500) -> list[dict[str, Any]]:
    init_runtime_db()
    query = "SELECT * FROM auth_sessions"
    params: list[Any] = []
    conditions: list[str] = []
    if email:
        conditions.append("email = ?")
        params.append(email)
    if not include_revoked:
        conditions.append("revoked_at IS NULL")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with db_connection() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def revoke_auth_session(session_id: str, *, revoked_at: str | None = None) -> None:
    init_runtime_db()
    timestamp = revoked_at or now_iso()
    with db_connection() as connection:
        connection.execute(
            "UPDATE auth_sessions SET revoked_at = ? WHERE session_id = ?",
            (timestamp, session_id),
        )


def revoke_auth_sessions_for_email(email: str, *, revoked_at: str | None = None) -> int:
    init_runtime_db()
    timestamp = revoked_at or now_iso()
    with db_connection() as connection:
        rowcount = connection.execute(
            "UPDATE auth_sessions SET revoked_at = ? WHERE email = ? AND revoked_at IS NULL",
            (timestamp, email),
        ).rowcount
    return int(rowcount or 0)


def delete_expired_auth_sessions(now_value: str | None = None) -> int:
    init_runtime_db()
    cutoff = now_value or now_iso()
    with db_connection() as connection:
        rowcount = connection.execute(
            "DELETE FROM auth_sessions WHERE expires_at <= ?",
            (cutoff,),
        ).rowcount
    return int(rowcount or 0)


def auth_metrics() -> dict[str, int]:
    init_runtime_db()
    delete_expired_auth_sessions()
    with db_connection() as connection:
        users = connection.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active FROM auth_users"
        ).fetchone()
        sessions = connection.execute(
            "SELECT COUNT(*) AS active_sessions FROM auth_sessions WHERE revoked_at IS NULL AND expires_at > ?",
            (now_iso(),),
        ).fetchone()
    total_users = int(users["total"] or 0) if users else 0
    active_users = int(users["active"] or 0) if users else 0
    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": max(total_users - active_users, 0),
        "active_sessions": int(sessions["active_sessions"] or 0) if sessions else 0,
    }


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
