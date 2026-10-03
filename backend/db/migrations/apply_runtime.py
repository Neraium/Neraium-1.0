"""Release-only schema command; never imported or invoked by API/worker startup.

PostgreSQL: python -m db.migrations.apply_runtime --component all
Supply NERAIUM_{RUNTIME,AUTH,TELEMETRY}_MIGRATION_DSN separately from runtime
configuration. There is deliberately no fallback to runtime DSNs or secrets.
Local SQLite: --sqlite-dir /path/to/runtime (runtime and auth ledgers).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import sys


def migrate_sqlite(directory: Path) -> None:
    from db.migrations import auth_schema, runtime_sqlite
    directory.mkdir(parents=True, exist_ok=True)
    for filename, migrate in (("runtime.db", runtime_sqlite.apply),
                              ("auth_store.db", lambda c: auth_schema.apply(c, dialect="sqlite", placeholder="?"))):
        with sqlite3.connect(directory / filename, timeout=30) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            migrate(connection)
        print(f"schema_migration_complete:sqlite:{filename}")
    from app.services.schema_verification import verify_sqlite_file
    verify_sqlite_file(directory / "runtime.db", "runtime_sqlite")
    verify_sqlite_file(directory / "auth_store.db", "auth_sqlite")


def migrate_postgres(component: str) -> None:
    import psycopg
    components = ("runtime", "auth", "telemetry") if component == "all" else (component,)
    # Check every required input before making any schema changes.
    dsns = {name: os.environ.get(f"NERAIUM_{name.upper()}_MIGRATION_DSN", "").strip() for name in components}
    if not all(dsns.values()):
        raise RuntimeError("schema_migration_identity_required")
    for name in components:
        print(f"schema_migration_starting:{name}")
        with psycopg.connect(dsns[name], connect_timeout=5) as connection:
            if name == "runtime":
                from db.migrations.runtime_postgres import apply
                apply(connection)
                print("schema_migration_complete:runtime:1")
            elif name == "auth":
                from db.migrations.auth_schema import apply
                apply(connection, dialect="postgresql", placeholder="%s")
                from app.services.schema_verification import verify_postgres
                verify_postgres(connection, "public", "auth_postgres")
                print("schema_migration_complete:auth:001-003")
            else:
                from db.migrations.apply_telemetry import apply_all
                apply_all(connection)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=("all", "runtime", "auth", "telemetry"), default="all")
    targets = parser.add_mutually_exclusive_group()
    targets.add_argument("--sqlite-dir", type=Path)
    targets.add_argument("--connector-replay-db", type=Path)
    args = parser.parse_args()
    try:
        if args.connector_replay_db:
            from db.migrations.connector_replay import apply
            apply(args.connector_replay_db)
            print("schema_migration_complete:connector_replay")
        elif args.sqlite_dir:
            migrate_sqlite(args.sqlite_dir)
        else:
            migrate_postgres(args.component)
    except Exception as error:
        from app.services.schema_verification import SchemaIncompatibilityError
        if isinstance(error, SchemaIncompatibilityError):
            print(str(error), file=sys.stderr)
        # Driver exceptions can contain credentials. Object diagnostics belong
        # to the verifier; command output reports only the failed release gate.
        print("schema_migration_failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
