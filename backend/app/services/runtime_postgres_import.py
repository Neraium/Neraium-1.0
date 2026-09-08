"""Copy an offline SQLite snapshot verbatim into the shared runtime database.

Explicit operator command only. Never initializes or migrates the source,
recomputes evidence, updates target rows, or resolves conflicting histories.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3

from psycopg import sql

from app.services import runtime_postgres


def import_snapshot(path: Path, *, apply: bool = False) -> dict[str, int]:
    if not runtime_postgres.database_url():
        raise ValueError("NERAIUM_RUNTIME_DATABASE_URL is required")
    runtime_postgres.initialize()
    counts = {}
    source = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        with runtime_postgres.connect() as target:
            target.execute("BEGIN IMMEDIATE")
            raw = target.connection
            sequences = []
            tables = source.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
            ).fetchall()
            for table_row in tables:
                table = table_row["name"]
                # Runtime migration bookkeeping is dialect-specific.
                if table == "runtime_schema_migrations":
                    continue
                quoted_table = '"' + table.replace('"', '""') + '"'
                columns = source.execute(f"PRAGMA table_info({quoted_table})").fetchall()
                names = [column["name"] for column in columns]
                primary_key = [c["name"] for c in sorted(columns, key=lambda c: c["pk"]) if c["pk"]]
                if not primary_key:
                    # Scoped legacy tables use UNIQUE natural keys. A legacy
                    # row missing that scope is rejected below, never guessed.
                    for index in source.execute(f"PRAGMA index_list({quoted_table})").fetchall():
                        if not index["unique"] or index["partial"]:
                            continue
                        quoted_index = '"' + index["name"].replace('"', '""') + '"'
                        candidate = [item["name"] for item in source.execute(f"PRAGMA index_info({quoted_index})")]
                        if candidate and all(candidate):
                            primary_key = candidate
                            break
                if not primary_key:
                    raise ValueError(f"Missing stable row identity: {table}")
                count = 0
                for row in source.execute(f"SELECT * FROM {quoted_table} ORDER BY rowid"):
                    values = dict(row)
                    if any(values[key] is None for key in primary_key):
                        raise ValueError(f"Ambiguous legacy row identity in {table}; no rows were imported")
                    raw.execute(sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                        sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, names)),
                        sql.SQL(", ").join(sql.Placeholder() for _ in names),
                    ), tuple(values[name] for name in names))
                    stored = raw.execute(sql.SQL("SELECT {} FROM {} WHERE {}").format(
                        sql.SQL(", ").join(map(sql.Identifier, names)), sql.Identifier(table),
                        sql.SQL(" AND ").join(sql.SQL("{} = %s").format(sql.Identifier(key)) for key in primary_key),
                    ), tuple(values[key] for key in primary_key)).fetchone()
                    if stored != values:
                        raise ValueError(f"Conflicting runtime history in {table}; no rows were imported")
                    count += 1
                counts[table] = count
                for name in primary_key:
                    sequence = raw.execute("SELECT pg_get_serial_sequence(%s, %s) AS name", (table, name)).fetchone()["name"]
                    if sequence:
                        sequences.append((table, name, sequence))
            if apply:
                for table, name, sequence in sequences:
                    # Sequence changes are not transactional: defer them until all
                    # rows verify, and never change sequences in a dry run.
                    raw.execute(sql.SQL(
                        "SELECT setval(%s, GREATEST(COALESCE(pg_sequence_last_value(%s::regclass), 1), "
                        "COALESCE(MAX({}), 0) + 1), false) FROM {}"
                    ).format(sql.Identifier(name), sql.Identifier(table)), (sequence, sequence))
            # Explicitly roll back the copy for the default dry run.
            if not apply:
                raw.rollback()
    finally:
        source.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--apply", action="store_true", help="Commit the verified copy (default: rollback)")
    args = parser.parse_args()
    print({"applied": args.apply, "rows_verified": import_snapshot(args.snapshot, apply=args.apply)})


if __name__ == "__main__":
    main()
