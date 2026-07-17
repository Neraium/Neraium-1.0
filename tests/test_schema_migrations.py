from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier

import pytest

from app.services import evidence_store, runtime_db
from app.connectors.models import NormalizedTelemetryRecord
from app.services.auth_store import _SQLiteAuthBackend
from app.services.data_connections import append_connection_buffer
from app.services.evidence_store import read_evidence_run, record_operator_feedback
from db.migrations.create_normalization_tables import run as run_normalization_migration


LEGACY_RUNTIME_SCHEMA = """
CREATE TABLE upload_jobs (
    job_id TEXT PRIMARY KEY, status TEXT NOT NULL, started_at TEXT,
    completed_at TEXT, updated_at TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE upload_queue (
    job_id TEXT PRIMARY KEY, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, locked_at TEXT
);
"""

LEGACY_AUTH_SCHEMA = """
CREATE TABLE auth_users (
    email TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
    salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, last_login_at TEXT, is_active BOOLEAN NOT NULL DEFAULT 1,
    deactivated_at TEXT, bootstrap_managed BOOLEAN NOT NULL DEFAULT 0
);
CREATE TABLE auth_sessions (
    session_id TEXT PRIMARY KEY, email TEXT NOT NULL, created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL, last_seen_at TEXT, revoked_at TEXT,
    FOREIGN KEY(email) REFERENCES auth_users(email) ON DELETE CASCADE
);
"""


def test_runtime_migrations_apply_cleanly_to_fresh_database(tmp_path: Path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    runtime_db.init_runtime_db()
    runtime_db.init_runtime_db()

    with runtime_db.db_connection() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        migrations = [
            row[0]
            for row in connection.execute(
                "SELECT migration_id FROM runtime_schema_migrations ORDER BY migration_id"
            )
        ]
        assert migrations == list(runtime_db.RUNTIME_SCHEMA_MIGRATIONS)
        foreign_keys = connection.execute("PRAGMA foreign_key_list(upload_queue)").fetchall()
        assert [(row[2], row[3], row[4], row[6]) for row in foreign_keys] == [
            ("upload_jobs", "job_id", "job_id", "CASCADE")
        ]
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(upload_queue)")}
        assert {"idx_upload_queue_status_created", "idx_upload_queue_status_updated"} <= indexes
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO data_connections VALUES (?, ?, ?, ?, ?, ?)",
                ("bad", "Bad", "arbitrary", 0, "2026-01-01T00:00:00+00:00", "{}"),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO latest_payloads VALUES (?, ?, ?)",
                ("bad-json", "2026-01-01T00:00:00+00:00", "not-json"),
            )


def test_runtime_upgrade_from_unversioned_schema_preserves_valid_rows(tmp_path: Path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    db_path = tmp_path / "runtime.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(LEGACY_RUNTIME_SCHEMA)
        connection.execute(
            "INSERT INTO upload_jobs VALUES (?, ?, ?, ?, ?, ?)",
            ("valid-job", "PENDING", None, None, "2026-01-01T00:00:00+00:00", "{}"),
        )
        connection.execute(
            "INSERT INTO upload_queue VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("valid-job", "queued", -2, None, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", None),
        )
        connection.execute(
            "INSERT INTO upload_queue VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("orphan", "pending", 0, None, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", None),
        )

    runtime_db.init_runtime_db()

    with runtime_db.db_connection() as connection:
        row = connection.execute(
            "SELECT status, attempts FROM upload_queue WHERE job_id = 'valid-job'"
        ).fetchone()
        assert dict(row) == {"status": "pending", "attempts": 0}
        assert connection.execute(
            "SELECT COUNT(*) FROM upload_queue WHERE job_id = 'orphan'"
        ).fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO upload_queue VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("missing", "pending", 0, None, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", None),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE upload_queue SET status = 'corrupt' WHERE job_id = 'valid-job'"
            )


def test_upload_queue_claim_is_atomic_across_connections(tmp_path: Path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    runtime_db.init_runtime_db()
    runtime_db.upsert_upload_job({"job_id": "job-1", "status": "PENDING"})
    runtime_db.enqueue_upload_job("job-1")
    barrier = Barrier(4)

    def claim() -> str | None:
        barrier.wait()
        return runtime_db.claim_next_upload_job()

    with ThreadPoolExecutor(max_workers=4) as executor:
        claimed = list(executor.map(lambda _: claim(), range(4)))

    assert claimed.count("job-1") == 1
    assert claimed.count(None) == 3
    with runtime_db.db_connection() as connection:
        assert connection.execute(
            "SELECT attempts FROM upload_queue WHERE job_id = 'job-1'"
        ).fetchone()[0] == 1


def test_auth_upgrade_enforces_roles_foreign_keys_and_one_active_session(tmp_path: Path) -> None:
    db_path = tmp_path / "auth.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(LEGACY_AUTH_SCHEMA)
        connection.execute(
            "INSERT INTO auth_users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("user@example.com", "User", "owner", "salt", "hash", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", None, 1, None, 0),
        )
        for session_id, created_at in (("old-session", "2026-01-01T00:00:00+00:00"), ("new-session", "2026-01-02T00:00:00+00:00")):
            connection.execute(
                "INSERT INTO auth_sessions VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, "user@example.com", created_at, "2099-01-01T00:00:00+00:00", created_at, None),
            )

    backend = _SQLiteAuthBackend(db_path)
    backend.ensure_schema()

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        assert connection.execute(
            "SELECT role FROM auth_users WHERE email = 'user@example.com'"
        ).fetchone()[0] == "operator"
        assert connection.execute(
            "SELECT COUNT(*) FROM auth_sessions WHERE email = 'user@example.com' AND revoked_at IS NULL"
        ).fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE auth_users SET role = 'owner' WHERE email = 'user@example.com'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO auth_sessions VALUES (?, ?, ?, ?, ?, ?)",
                ("bad", "missing@example.com", "2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00", None, None),
            )


def test_auth_user_insert_and_session_replacement_are_concurrency_safe(tmp_path: Path) -> None:
    backend = _SQLiteAuthBackend(tmp_path / "auth.db")
    backend.ensure_schema()
    payload = {
        "email": "race@example.com", "name": "Race", "role": "operator",
        "salt": "salt", "password_hash": "hash",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        "is_active": True,
    }
    barrier = Barrier(4)

    def insert() -> bool:
        barrier.wait()
        return backend.insert_user_if_absent(payload)

    with ThreadPoolExecutor(max_workers=4) as executor:
        inserted = list(executor.map(lambda _: insert(), range(4)))
    assert inserted.count(True) == 1

    def replace(index: int) -> None:
        backend.replace_active_session(
            {
                "session_id": f"session-{index}", "email": "race@example.com",
                "created_at": f"2026-01-0{index + 1}T00:00:00+00:00",
                "expires_at": "2099-01-01T00:00:00+00:00",
            }
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(replace, range(4)))
    active = backend.list_sessions(email="race@example.com", include_revoked=False)
    assert len(active) == 1


def test_database_timestamps_are_timezone_aware_iso_8601() -> None:
    value = runtime_db.now_iso()
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None


def test_live_ingestion_buffer_is_idempotent_and_concurrency_safe(tmp_path: Path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    runtime_db.init_runtime_db()
    barrier = Barrier(2)

    def append(sensor_id: str) -> None:
        record = NormalizedTelemetryRecord(
            source_id="source", system_id="system", sensor_id=sensor_id,
            sensor_name=sensor_id, value=1.25, unit="c",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        barrier.wait()
        append_connection_buffer("connection", [record, record])

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(append, ["sensor-a", "sensor-b"]))

    # Replaying either batch is a no-op at the logical-record level.
    replay = NormalizedTelemetryRecord(
        source_id="source", system_id="system", sensor_id="sensor-a",
        sensor_name="sensor-a", value=1.25, unit="c",
        timestamp="2026-01-01T00:00:00+00:00",
    )
    records = append_connection_buffer("connection", [replay])
    assert [item["sensor_id"] for item in records] == ["sensor-a", "sensor-b"]


class _RecordingCursor:
    def __init__(self, fetches: list[object]):
        self.fetches = list(fetches)
        self.statements: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql: str, params=None) -> None:
        self.statements.append((sql, params))

    def fetchone(self):
        return self.fetches.pop(0)


class _RecordingConnection:
    def __init__(self, fetches: list[object]):
        self.recording_cursor = _RecordingCursor(fetches)
        self.commits = 0

    def cursor(self):
        return self.recording_cursor

    def commit(self) -> None:
        self.commits += 1


def test_postgres_normalization_fresh_migration_is_versioned_and_safe() -> None:
    connection = _RecordingConnection([None, (None,), None])
    run_normalization_migration(connection)  # type: ignore[arg-type]
    sql = "\n".join(statement for statement, _ in connection.recording_cursor.statements)
    assert "neraium_schema_migrations" in sql
    assert "PRIMARY KEY (time, source_id, signal_id)" in sql
    assert "CHECK (window_end > window_start)" in sql
    assert "UNIQUE (signal_id, source_id, window_start, window_end)" in sql
    assert "CREATE EXTENSION" not in sql
    assert "migrate_data => FALSE" not in sql  # TimescaleDB was not installed.
    assert connection.commits == 1


def test_postgres_normalization_legacy_schema_requires_documented_online_upgrade() -> None:
    connection = _RecordingConnection([None, ("telemetry_normalized",)])
    with pytest.raises(RuntimeError, match="unsupported_unversioned_normalization_schema"):
        run_normalization_migration(connection)  # type: ignore[arg-type]
    assert connection.commits == 0


def test_evidence_feedback_append_does_not_lose_concurrent_updates(tmp_path: Path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    runtime_db.init_runtime_db()
    runtime_db.upsert_evidence_run_db(
        {
            "run_id": "run-1", "created_at": "2026-01-01T00:00:00+00:00",
            "status": "completed", "source_type": "csv_upload",
            "operator_feedback_history": [], "variables": [],
        }
    )
    barrier = Barrier(4)

    def feedback(index: int) -> None:
        barrier.wait()
        record_operator_feedback(
            "run-1", "confirmed_issue", f"note-{index}", f"operator-{index}",
            f"2026-01-01T00:00:0{index}+00:00",
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(feedback, range(4)))

    record = read_evidence_run("run-1")
    assert record is not None
    history = record["operator_feedback_history"]
    assert len(history) == 4
    assert {item["note"] for item in history} == {"note-0", "note-1", "note-2", "note-3"}

def test_legacy_evidence_is_imported_once_and_cannot_resurrect_after_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    runtime_db.init_runtime_db()
    evidence_dir = tmp_path / "evidence"
    evidence_path = evidence_dir / "runs.json"
    evidence_dir.mkdir(parents=True)
    evidence_path.write_text(
        json.dumps(
            [
                {
                    "run_id": "legacy-run",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "status": "completed",
                    "source_type": "csv_upload",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(evidence_store, "EVIDENCE_DIR", evidence_dir)
    monkeypatch.setattr(evidence_store, "EVIDENCE_RUNS_PATH", evidence_path)

    assert evidence_store.read_evidence_run("legacy-run") is not None
    with runtime_db.db_connection() as connection:
        connection.execute("DELETE FROM evidence_runs")

    assert evidence_store.list_evidence_runs() == []
    assert evidence_path.exists()  # The stale compatibility mirror remains harmless.

def test_upload_queue_helpers_validate_status_transitions(tmp_path: Path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    runtime_db.init_runtime_db()
    runtime_db.upsert_upload_job(
        {
            "job_id": "state-job",
            "status": "QUEUED",
            "started_at": None,
            "completed_at": None,
        }
    )
    runtime_db.enqueue_upload_job("state-job")
    assert runtime_db.claim_next_upload_job() == "state-job"
    runtime_db.complete_upload_queue_job("state-job", "completed")
    runtime_db.mark_queue_job_failed("state-job", "late failure")
    assert runtime_db.read_upload_queue_job("state-job")["status"] == "completed"

    with pytest.raises(ValueError, match="invalid_upload_queue_status_transition"):
        runtime_db.complete_upload_queue_job("state-job", "processing")
    with pytest.raises(ValueError, match="invalid_upload_queue_status_transition"):
        runtime_db.touch_upload_queue_job("state-job", "completed")

def test_s3_queue_helpers_apply_the_same_terminal_transition_guards(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"job_id": "state-job", "status": "completed", "attempts": 1}
    writes: list[dict[str, object]] = []
    monkeypatch.setattr(runtime_db, "upload_queue_backend", lambda: "s3")
    monkeypatch.setattr(runtime_db, "_ensure_shared_upload_queue_backend", lambda: None)
    monkeypatch.setattr(runtime_db, "_read_s3_queue_job", lambda _job_id: dict(state))
    monkeypatch.setattr(runtime_db, "_write_s3_queue_job", lambda payload: writes.append(dict(payload)))

    runtime_db.mark_queue_job_failed("state-job", "late failure")
    runtime_db.complete_upload_queue_job("state-job", "failed", "late failure")
    runtime_db.touch_upload_queue_job("state-job", "processing")
    assert writes == []
