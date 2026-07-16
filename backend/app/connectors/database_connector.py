from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import psycopg

from app.connectors.models import ConnectorHealthStatus, NormalizedConnectorBatch
from app.connectors.rest_connector import RESTConnector


class DatabaseConnector(RESTConnector):
    """Read-only relational database telemetry connector.

    The configured query is executed inside a database-enforced read-only
    session. Query results use the same wide-row telemetry normalization as
    REST and CSV connectors.
    """

    connector_type = "database"
    display_name = "Database"
    functional = True

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        normalized_config = dict(config or {})
        normalized_config.setdefault("source_id", "customer-database")
        normalized_config.setdefault("system_id", "facility-database")
        super().__init__(normalized_config)

    def connect(self) -> dict[str, Any]:
        database_url = self.config.get("database_url")
        query = self.config.get("query")
        if not database_url:
            return {"ok": False, "message": "Database URL is required."}
        if not query:
            return {"ok": False, "message": "A read-only telemetry query is required."}
        return {
            "ok": True,
            "message": "Read-only database connector settings are complete.",
            "database": self._masked_database_configuration(),
        }

    def validate_connection(self) -> dict[str, Any]:
        try:
            rows = self.fetch_historical()
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        if not rows:
            return {"ok": False, "message": "Database query returned an empty dataset."}
        return {"ok": True, "message": f"Database access confirmed with {len(rows)} telemetry rows."}

    def fetch_historical(self) -> list[dict[str, Any]]:
        return self._execute_query(str(self.config.get("query") or ""))

    def stream_latest(self) -> list[dict[str, Any]]:
        latest_query = self.config.get("latest_query")
        if latest_query:
            rows = self._execute_query(str(latest_query), max_rows=1)
            return rows[:1]
        rows = self.fetch_historical()
        return rows[-1:] if rows else []

    def normalize(self, raw_data: list[dict[str, Any]]) -> NormalizedConnectorBatch:
        if not raw_data:
            raise ValueError("Database query returned no telemetry records.")
        try:
            batch = super().normalize(raw_data)
        except ValueError as exc:
            message = str(exc).replace("REST API", "database query").replace("REST telemetry", "Database telemetry")
            raise ValueError(message) from None
        batch.metadata = {
            "database": self._masked_database_configuration(),
            "row_limit": self._max_rows(),
            "query_timeout_seconds": self._query_timeout_seconds(),
        }
        return batch

    def health_check(self) -> ConnectorHealthStatus:
        database_url = self.config.get("database_url")
        query = self.config.get("query")
        try:
            max_rows: int | str = self._max_rows()
        except ValueError:
            max_rows = "invalid"
        try:
            query_timeout: int | str = self._query_timeout_seconds()
        except ValueError:
            query_timeout = "invalid"
        return ConnectorHealthStatus(
            connector_type=self.connector_type,
            display_name=self.display_name,
            functional=True,
            connection_status="ready" if database_url and query else "not_configured",
            masked_configuration={
                "database": self._masked_database_configuration(),
                "source_id": self.config.get("source_id"),
                "system_id": self.config.get("system_id"),
                "max_rows": max_rows,
                "query_timeout_seconds": query_timeout,
                "sslmode": self._masked_sslmode(),
                "query_configured": bool(query),
            },
        )

    def _execute_query(self, query: str, *, max_rows: int | None = None) -> list[dict[str, Any]]:
        database_url = str(self.config.get("database_url") or "").strip()
        if not database_url:
            raise ValueError("Database URL is required.")
        clean_query = self._validate_query(query)
        limit = max_rows or self._max_rows()
        timeout_seconds = self._query_timeout_seconds()
        parameters = self.config.get("parameters") or ()
        bounded_query = self._bounded_query(clean_query, limit)

        if database_url.startswith("sqlite:///"):
            return self._execute_sqlite(database_url, bounded_query, parameters, limit, timeout_seconds)
        if database_url.startswith(("postgresql://", "postgres://")):
            return self._execute_postgres(database_url, bounded_query, parameters, limit, timeout_seconds)
        raise ValueError("Database URL must use a supported sqlite:/// or postgresql:// scheme.")

    def _execute_sqlite(
        self,
        database_url: str,
        query: str,
        parameters: Any,
        limit: int,
        timeout_seconds: int,
    ) -> list[dict[str, Any]]:
        raw_path = unquote(database_url.removeprefix("sqlite:///"))
        if not raw_path or raw_path == ":memory:":
            raise ValueError("SQLite connector requires an existing database file.")
        if re.match(r"^/[A-Za-z]:/", raw_path):
            raw_path = raw_path[1:]
        database_path = Path(raw_path).expanduser()
        if not database_path.is_absolute():
            database_path = database_path.resolve()
        if not database_path.is_file():
            raise ValueError("SQLite database file does not exist.")

        deadline = time.monotonic() + timeout_seconds
        timed_out = False

        def abort_expired_query() -> int:
            nonlocal timed_out
            timed_out = time.monotonic() >= deadline
            return 1 if timed_out else 0

        def deny_system_catalog_reads(action: int, target: str | None, _column: str | None, *_args: Any) -> int:
            if action == sqlite3.SQLITE_READ and str(target or "").lower().startswith("sqlite_"):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        try:
            database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
            connection = sqlite3.connect(database_uri, uri=True, timeout=min(timeout_seconds, 10))
            connection.row_factory = sqlite3.Row

            def interrupt_expired_query() -> None:
                nonlocal timed_out
                timed_out = True
                connection.interrupt()

            timeout_timer = threading.Timer(timeout_seconds, interrupt_expired_query)
            timeout_timer.daemon = True
            try:
                connection.execute("PRAGMA query_only = ON")
                connection.set_authorizer(deny_system_catalog_reads)
                connection.set_progress_handler(abort_expired_query, 1000)
                timeout_timer.start()
                cursor = connection.execute(query, parameters)
                return self._rows_from_cursor(cursor, limit)
            finally:
                timeout_timer.cancel()
                connection.close()
        except (sqlite3.Error, TypeError):
            if timed_out:
                raise ValueError(f"Database query exceeded the configured {timeout_seconds}-second timeout.") from None
            raise ValueError("Database connection or query failed. Check the file, parameters, and read-only query.") from None

    def _execute_postgres(
        self,
        database_url: str,
        query: str,
        parameters: Any,
        limit: int,
        timeout_seconds: int,
    ) -> list[dict[str, Any]]:
        try:
            with psycopg.connect(
                database_url,
                connect_timeout=min(timeout_seconds, 10),
                sslmode=self._sslmode(),
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute(
                        "SELECT set_config('statement_timeout', %s, true)",
                        (f"{timeout_seconds * 1000}ms",),
                    )
                    cursor.execute(query, parameters)
                    return self._rows_from_cursor(cursor, limit)
        except psycopg.errors.QueryCanceled:
            raise ValueError(f"Database query exceeded the configured {timeout_seconds}-second timeout.") from None
        except (psycopg.Error, TypeError):
            raise ValueError("Database connection or query failed. Check the URL, credentials, and read-only query.") from None

    @staticmethod
    def _rows_from_cursor(cursor: Any, limit: int) -> list[dict[str, Any]]:
        if cursor.description is None:
            raise ValueError("Database query did not return a result set.")
        columns = [column[0] for column in cursor.description]
        raw_rows = cursor.fetchmany(limit + 1)
        if len(raw_rows) > limit:
            raise ValueError(f"Database query exceeded the configured {limit}-row limit.")
        return [dict(zip(columns, row, strict=True)) for row in raw_rows]

    @staticmethod
    def _bounded_query(query: str, limit: int) -> str:
        return f"SELECT * FROM ({query}) AS neraium_telemetry_query LIMIT {limit + 1}"

    @staticmethod
    def _validate_query(query: str) -> str:
        stripped = query.strip()
        if not stripped:
            raise ValueError("A read-only telemetry query is required.")
        without_trailing_semicolon = stripped[:-1].rstrip() if stripped.endswith(";") else stripped
        if ";" in without_trailing_semicolon:
            raise ValueError("Database connector accepts exactly one read-only query.")
        first_keyword = without_trailing_semicolon.split(None, 1)[0].lower()
        if first_keyword not in {"select", "with"}:
            raise ValueError("Database connector only accepts SELECT or WITH queries.")
        return without_trailing_semicolon

    def _max_rows(self) -> int:
        try:
            value = int(self.config.get("max_rows", 5000))
        except (TypeError, ValueError):
            raise ValueError("max_rows must be an integer between 1 and 10000.") from None
        if not 1 <= value <= 10_000:
            raise ValueError("max_rows must be between 1 and 10000.")
        return value

    def _query_timeout_seconds(self) -> int:
        try:
            value = int(self.config.get("query_timeout_seconds", 30))
        except (TypeError, ValueError):
            raise ValueError("query_timeout_seconds must be an integer between 1 and 120.") from None
        if not 1 <= value <= 120:
            raise ValueError("query_timeout_seconds must be between 1 and 120.")
        return value

    def _sslmode(self) -> str:
        value = str(self.config.get("sslmode", "require")).strip().lower()
        if value not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("sslmode must be require, verify-ca, or verify-full.")
        return value

    def _masked_sslmode(self) -> str:
        try:
            return self._sslmode()
        except ValueError:
            return "invalid"

    def _masked_database_configuration(self) -> dict[str, Any]:
        database_url = str(self.config.get("database_url") or "")
        if not database_url:
            return {"driver": "not_configured"}
        if database_url.startswith("sqlite:///"):
            raw_path = unquote(database_url.removeprefix("sqlite:///"))
            return {"driver": "sqlite", "database": Path(raw_path).name or "configured"}
        parsed = urlsplit(database_url)
        try:
            port: int | str | None = parsed.port
        except ValueError:
            port = "invalid"
        return {
            "driver": "postgresql" if parsed.scheme in {"postgres", "postgresql"} else parsed.scheme,
            "host": parsed.hostname or "configured",
            "port": port,
            "database": parsed.path.lstrip("/") or "configured",
            "username": parsed.username or "configured",
        }
