"""Runtime never repairs schemas; migrations own creation and evolution."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app.services import auth_store, runtime_db, runtime_postgres
from app.services.schema_verification import SchemaIncompatibilityError, verify_sqlite_file
from db.migrations.apply_runtime import migrate_sqlite


def test_missing_sqlite_database_is_not_created(tmp_path):
    runtime_db.configure_runtime_dir(tmp_path / "missing")
    with pytest.raises(SchemaIncompatibilityError, match="database_missing"):
        runtime_db.init_runtime_db()
    assert not runtime_db.DB_PATH.exists()
    backend = auth_store._SQLiteAuthBackend(tmp_path / "missing-auth.db")
    with pytest.raises(SchemaIncompatibilityError, match="database_missing"):
        backend.ensure_schema()
    assert not backend.db_path.exists()


@pytest.mark.parametrize("object_kind,sql,diagnostic", [
    ("table", "DROP TABLE latest_payloads", "tables:latest_payloads"),
    ("column", "ALTER TABLE latest_payloads RENAME COLUMN payload_json TO removed_payload", "column:latest_payloads.payload_json"),
    ("index", "DROP INDEX idx_upload_jobs_updated_at", "indexes:idx_upload_jobs_updated_at"),
    ("trigger", "DROP TRIGGER trg_finding_cases_no_delete", "triggers:trg_finding_cases_no_delete"),
    ("migration", "DELETE FROM runtime_schema_migrations WHERE migration_id='014_governance_lifecycle_events'", "migration_state"),
])
def test_missing_required_sqlite_state_fails_without_repair(object_kind, sql, diagnostic):
    with sqlite3.connect(runtime_db.DB_PATH) as c:
        c.execute(sql)
    before = runtime_db.DB_PATH.read_bytes()
    for _ in range(2):
        with pytest.raises(SchemaIncompatibilityError, match=diagnostic):
            runtime_db.init_runtime_db()
    assert runtime_db.DB_PATH.read_bytes() == before


def test_schema_verification_is_read_only(monkeypatch):
    real_connect = sqlite3.connect
    statements = []
    forbidden = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                 sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_CREATE_INDEX,
                 sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_ALTER_TABLE,
                 sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_DROP_INDEX, sqlite3.SQLITE_DROP_TRIGGER}
    def open_readonly(*args, **kwargs):
        assert "mode=ro" in args[0]
        c = real_connect(*args, **kwargs)
        c.set_authorizer(lambda action, *rest: sqlite3.SQLITE_DENY if action in forbidden else sqlite3.SQLITE_OK)
        c.set_trace_callback(statements.append)
        return c
    monkeypatch.setattr(sqlite3, "connect", open_readonly)
    runtime_db.init_runtime_db()
    auth_store._SQLiteAuthBackend(runtime_db.RUNTIME_DIR / "auth_store.db").ensure_schema()
    assert statements and all(s.lstrip().upper().startswith(("SELECT", "PRAGMA")) for s in statements)


def test_explicit_local_migration_is_complete_and_idempotent(tmp_path):
    migrate_sqlite(tmp_path)
    verify_sqlite_file(tmp_path / "runtime.db", "runtime_sqlite")
    verify_sqlite_file(tmp_path / "auth_store.db", "auth_sqlite")
    before = (tmp_path / "runtime.db").read_bytes()
    migrate_sqlite(tmp_path)
    assert (tmp_path / "runtime.db").read_bytes() == before


def test_release_command_has_no_runtime_credential_fallback(monkeypatch, capsys):
    from db.migrations.apply_runtime import main
    for component in ("RUNTIME", "AUTH", "TELEMETRY"):
        monkeypatch.delenv(f"NERAIUM_{component}_MIGRATION_DSN", raising=False)
        monkeypatch.setenv(f"NERAIUM_{component}_DATABASE_URL", "must-not-be-opened")
    monkeypatch.setattr(sys, "argv", ["migration"])
    monkeypatch.setattr("psycopg.connect", lambda *a, **k: pytest.fail("opened runtime credentials"))
    assert main() == 1
    assert "schema_migration_failed" in capsys.readouterr().err


def test_migration_failure_rolls_back_schema_creation(tmp_path):
    from db.migrations.runtime_sqlite import apply
    path = tmp_path / "failed.db"
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE upload_jobs (wrong TEXT)")
    with pytest.raises(sqlite3.OperationalError):
        with sqlite3.connect(path) as c:
            c.row_factory = sqlite3.Row
            apply(c)
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("upload_jobs",)]


def test_connector_replay_requires_explicit_migration(tmp_path):
    from app.services.connector_execution import ConnectorExecutionBroker
    from db.migrations.connector_replay import apply
    path = tmp_path / "replay.db"
    with pytest.raises(SchemaIncompatibilityError, match="database_missing"):
        ConnectorExecutionBroker(secret_store=object(), auth_secret_arn="fixture", replay_db_path=str(path))
    assert not path.exists()
    apply(path)
    ConnectorExecutionBroker(secret_store=object(), auth_secret_arn="fixture", replay_db_path=str(path))
    with sqlite3.connect(path) as c:
        c.execute("DROP TABLE used_jobs")
    with pytest.raises(SchemaIncompatibilityError):
        ConnectorExecutionBroker(secret_store=object(), auth_secret_arn="fixture", replay_db_path=str(path))
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE name='used_jobs'").fetchone() is None


def test_auth_failed_verification_cannot_publish_cached_backend(monkeypatch):
    backend = auth_store._SQLiteAuthBackend(runtime_db.RUNTIME_DIR / "missing.db")
    monkeypatch.setattr(auth_store, "_AUTH_BACKEND", None)
    monkeypatch.setattr(auth_store, "_AUTH_BACKEND_KEY", None)
    monkeypatch.setattr(auth_store, "_SQLiteAuthBackend", lambda _: backend)
    for _ in range(2):
        with pytest.raises(SchemaIncompatibilityError):
            auth_store.initialize_auth_store()
        assert auth_store._AUTH_BACKEND is None


def test_runtime_process_does_not_import_migration_implementations():
    # Fresh interpreter prevents test fixtures' explicit migration imports from
    # hiding accidental runtime imports. No database or secret access is needed.
    code = "import app.main, app.entrypoint; import sys; assert not any(n.startswith('db.migrations.') for n in sys.modules)"
    subprocess.run([sys.executable, "-c", code], check=True)
