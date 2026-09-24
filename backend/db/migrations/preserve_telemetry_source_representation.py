"""Add nullable acquisition provenance; never backfill or rewrite old evidence."""

from __future__ import annotations

from typing import Any


MIGRATION_ID = "006_preserve_telemetry_source_representation"
REQUIRED_MIGRATIONS = ("005_persist_canonical_analysis_results",)
EXPECTED_COLUMNS = {
    table: frozenset({"source_representation", "acquired_at_utc"})
    for table in ("normalized_observations", "observation_rejections")
}

# PostgreSQL's canonical deparse of the CHECK below, not the submitted SQL or
# an automatically generated constraint name. Redundant parentheses, whitespace,
# quoted identifiers and implicit text casts normalize in the server parser.
EXPECTED_CHECK_EXPRESSION = (
    "((source_representation IS NULL) OR (((jsonb_typeof(source_representation) = 'object'::text) "
    "AND ((source_representation ->> 'contract_version'::text) = "
    "'neraium.telemetry.source-representation/v1'::text)) IS TRUE))"
)

DDL = "\n".join(
    f"""
ALTER TABLE telemetry.{table}
    ADD COLUMN IF NOT EXISTS source_representation JSONB
        CHECK (source_representation IS NULL OR (
            jsonb_typeof(source_representation) = 'object'
            AND source_representation->>'contract_version' =
                'neraium.telemetry.source-representation/v1'
        ) IS TRUE),
    ADD COLUMN IF NOT EXISTS acquired_at_utc TIMESTAMPTZ;
"""
    for table in EXPECTED_COLUMNS
)


def apply(conn: Any) -> None:
    """Apply once under the migration ledger lock after the existing foundation."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (MIGRATION_ID,))
        cur.execute(
            "SELECT migration_id FROM telemetry.schema_migrations WHERE migration_id = ANY(%s)",
            (list(REQUIRED_MIGRATIONS),),
        )
        present = {str(row[0]) for row in cur.fetchall()}
        if set(REQUIRED_MIGRATIONS) - present:
            raise RuntimeError("telemetry_source_representation_prerequisite_missing")
        cur.execute(
            "SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s", (MIGRATION_ID,),
        )
        if cur.fetchone() is None:
            cur.execute(DDL)
            cur.execute(
                "INSERT INTO telemetry.schema_migrations (migration_id) VALUES (%s)", (MIGRATION_ID,),
            )
    conn.commit()


run = apply


def verify(conn: Any) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s", (MIGRATION_ID,),
        )
        if cur.fetchone() is None:
            raise RuntimeError("telemetry_source_representation_migration_not_applied")
        for table, expected in EXPECTED_COLUMNS.items():
            cur.execute(
                "SELECT column_name, data_type, is_nullable, column_default, is_generated FROM information_schema.columns "
                "WHERE table_schema = 'telemetry' AND table_name = %s", (table,),
            )
            columns = {str(row[0]): (row[1], row[2], row[3], row[4]) for row in cur.fetchall()}
            if not expected.issubset(columns) or (
                columns["source_representation"] != ("jsonb", "YES", None, "NEVER")
                or columns["acquired_at_utc"] != ("timestamp with time zone", "YES", None, "NEVER")
            ):
                raise RuntimeError("telemetry_source_representation_migration_incomplete")
            cur.execute(
                "SELECT pg_get_expr(c.conbin, c.conrelid), c.convalidated "
                "FROM pg_catalog.pg_constraint c "
                "JOIN pg_catalog.pg_class t ON t.oid = c.conrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = 'telemetry' AND t.relname = %s AND c.contype = 'c'",
                (table,),
            )
            if not any(
                expression == EXPECTED_CHECK_EXPRESSION and validated
                for expression, validated in cur.fetchall()
            ):
                raise RuntimeError("telemetry_source_representation_constraint_incomplete")
    return {"migration_id": MIGRATION_ID, "tables": sorted(EXPECTED_COLUMNS)}


def downgrade(_conn: Any) -> None:
    raise RuntimeError("telemetry_source_representation_downgrade_unsupported")
