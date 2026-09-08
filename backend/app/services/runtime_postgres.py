"""Shared runtime storage; local SQLite remains the development fallback.

Keep existing SQL callers and their transaction boundaries. The small dialect
adapter handles only the three SQLite spellings used outside schema migrations.
A database transaction lock preserves SQLite's single-writer semantics across
API/worker processes, including read/modify/write governance operations.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
import os
from pathlib import Path
import re
import threading

_SCHEMA = "neraium_runtime"
_LOCK = 173514002
_initialized: set[str] = set()
_init_lock = threading.Lock()


def database_url() -> str:
    return os.getenv("NERAIUM_RUNTIME_DATABASE_URL", "").strip()


def _open_connection(*, rows: bool = False):
    # Keep SQLite-only local installations independent of the optional driver.
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(database_url(), **({"row_factory": dict_row} if rows else {}))


def _sql(statement: str) -> str:
    statement = statement.strip().rstrip(";")
    if statement.upper() == "BEGIN IMMEDIATE":
        return f"SELECT pg_advisory_xact_lock({_LOCK})"
    ignore = statement.upper().startswith("INSERT OR IGNORE")
    if ignore:
        statement = statement.replace("INSERT OR IGNORE", "INSERT", 1)
        statement += " ON CONFLICT DO NOTHING"
    statement = re.sub(
        r"json_extract\((\w+), '\$\.(\w+)'\)",
        r"(\1::json ->> '\2')", statement,
    )
    # Do not change question marks inside SQL string literals or identifiers.
    return re.sub(r"'(''|[^'])*'|\"(\"\"|[^\"])*\"|\?",
                  lambda match: "%s" if match.group() == "?" else match.group(), statement)


class Connection:
    def __init__(self, connection):
        self.connection = connection
        self.locked = False

    def _write_lock(self, statement):
        if not self.locked and statement.lstrip().split(None, 1)[0].upper() in {
            "INSERT", "UPDATE", "DELETE", "BEGIN", "CREATE", "ALTER", "DROP",
        }:
            self.connection.execute(f"SELECT pg_advisory_xact_lock({_LOCK})")
            self.locked = True

    def execute(self, statement, parameters=()):
        self._write_lock(statement)
        return self.connection.execute(_sql(statement), parameters or None)

    def executemany(self, statement, parameters):
        self._write_lock(statement)
        cursor = self.connection.cursor()
        cursor.executemany(_sql(statement), parameters)
        return cursor


@contextmanager
def connect(*, readonly: bool = False):
    with _open_connection(rows=True) as connection:
        if readonly:
            connection.execute("SET TRANSACTION READ ONLY")
        connection.execute(f"SET LOCAL search_path TO {_SCHEMA}, pg_catalog")
        connection.execute("SET LOCAL lock_timeout = '30s'")
        yield Connection(connection)


def initialize() -> None:
    dsn = database_url()
    with _init_lock:
        if dsn in _initialized:
            return
        with _open_connection() as connection:
            connection.execute("SET LOCAL lock_timeout = '30s'")
            connection.execute(f"SELECT pg_advisory_xact_lock({_LOCK})")
            connection.execute(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}")
            connection.execute(f"SET LOCAL search_path TO {_SCHEMA}, pg_catalog")
            connection.execute("CREATE TABLE IF NOT EXISTS postgres_runtime_migrations (version INTEGER PRIMARY KEY)")
            if not connection.execute("SELECT 1 FROM postgres_runtime_migrations WHERE version = 1").fetchone():
                connection.execute(Path(__file__).with_name("runtime_postgres_v1.sql").read_text())
                connection.execute("INSERT INTO postgres_runtime_migrations VALUES (1)")
        _initialized.add(dsn)


_queue_transaction = threading.local()


def shared_queue_transaction(operation):
    """Serialize existing S3 queue transitions across production tasks.

    A distinct lock allows queue recovery to persist evidence using ordinary
    runtime transactions. Nested queue operations reuse the outer transaction.
    """
    @wraps(operation)
    def wrapped(*args, **kwargs):
        if (not database_url() or not os.getenv("NERAIUM_UPLOAD_STATE_BUCKET", "").strip()
                or getattr(_queue_transaction, "active", False)):
            return operation(*args, **kwargs)
        with _open_connection() as connection:
            connection.execute("SET LOCAL lock_timeout = '30s'")
            connection.execute("SELECT pg_advisory_xact_lock(173514003)")
            _queue_transaction.active = True
            try:
                return operation(*args, **kwargs)
            finally:
                _queue_transaction.active = False
    return wrapped
