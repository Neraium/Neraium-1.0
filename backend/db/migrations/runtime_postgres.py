"""Explicit PostgreSQL shared-storage migration using the existing version ledger."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from psycopg import sql

from app.services.schema_verification import verify_postgres

SCHEMA = "neraium_runtime"
VERSION = 1


def apply(connection: Any, *, schema: str = SCHEMA) -> None:
    """Install v1 once; incompatible existing state fails instead of being repaired."""
    connection.execute("SET LOCAL lock_timeout = '30s'")
    connection.execute("SELECT pg_advisory_xact_lock(173514002)")
    connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
    connection.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(schema)))
    connection.execute("CREATE TABLE IF NOT EXISTS postgres_runtime_migrations (version INTEGER PRIMARY KEY)")
    versions = {row[0] for row in connection.execute("SELECT version FROM postgres_runtime_migrations")}
    if versions - {VERSION}:
        raise RuntimeError("runtime_schema_migration_version_unsupported")
    if VERSION not in versions:
        connection.execute(Path(__file__).with_name("runtime_postgres_v1.sql").read_text())
        connection.execute("INSERT INTO postgres_runtime_migrations VALUES (%s)", (VERSION,))
    verify_postgres(connection, schema, "runtime_postgres")
