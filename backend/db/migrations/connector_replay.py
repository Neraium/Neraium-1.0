"""Offline initialization of the existing unversioned local executor replay store."""
from pathlib import Path
import sqlite3


def apply(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("CREATE TABLE IF NOT EXISTS used_jobs (request_identity TEXT PRIMARY KEY, digest TEXT NOT NULL, created_at INTEGER NOT NULL)")
        connection.execute("CREATE INDEX IF NOT EXISTS ix_used_jobs_created ON used_jobs(created_at)")
    from app.services.schema_verification import verify_sqlite_file
    verify_sqlite_file(path, "connector_replay")
