"""Create prospective scoped relationship temporal state heads."""
from __future__ import annotations

from typing import Any

MIGRATION_ID = "007_create_relationship_temporal_state"
REQUIRED_MIGRATIONS = ("006_preserve_telemetry_source_representation",)

DDL = """
CREATE TABLE IF NOT EXISTS telemetry.relationship_temporal_state_heads (
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    system_id TEXT NOT NULL CHECK (system_id <> ''),
    asset_id TEXT,
    relationship_lineage_ref TEXT NOT NULL CHECK (relationship_lineage_ref <> ''),
    state_schema TEXT NOT NULL CHECK (state_schema = 'relationship-temporal-state.v1'),
    compatibility_digest TEXT NOT NULL CHECK (compatibility_digest ~ '^[0-9a-f]{64}$'),
    reducer_state JSONB NOT NULL CHECK (jsonb_typeof(reducer_state) = 'object'),
    head_event_ref TEXT NOT NULL CHECK (head_event_ref <> ''),
    head_event_time TIMESTAMPTZ NOT NULL,
    state_digest TEXT NOT NULL CHECK (state_digest ~ '^[0-9a-f]{64}$'),
    storage_revision BIGINT NOT NULL CHECK (storage_revision > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_relationship_temporal_state_scope_lineage
    ON telemetry.relationship_temporal_state_heads
      (resource_scope_id, tenant_scope_id, workspace_id, facility_id, system_id,
       COALESCE(asset_id, ''), relationship_lineage_ref);
"""


def apply(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (MIGRATION_ID,))
        cur.execute("SELECT migration_id FROM telemetry.schema_migrations WHERE migration_id = ANY(%s)", (list(REQUIRED_MIGRATIONS),))
        if set(REQUIRED_MIGRATIONS) - {str(row[0]) for row in cur.fetchall()}:
            raise RuntimeError("relationship_temporal_state_prerequisite_missing")
        cur.execute("SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s", (MIGRATION_ID,))
        if cur.fetchone() is None:
            cur.execute(DDL)
            cur.execute("INSERT INTO telemetry.schema_migrations (migration_id) VALUES (%s)", (MIGRATION_ID,))
    conn.commit()


run = apply


def verify(conn: Any) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s", (MIGRATION_ID,))
        if cur.fetchone() is None:
            raise RuntimeError("relationship_temporal_state_migration_not_applied")
        cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='telemetry' AND table_name='relationship_temporal_state_heads'")
        if cur.fetchone() is None:
            raise RuntimeError("relationship_temporal_state_table_missing")
    return {"migration_id": MIGRATION_ID, "table": "relationship_temporal_state_heads"}


def downgrade(_conn: Any) -> None:
    raise RuntimeError("relationship_temporal_state_downgrade_unsupported")
