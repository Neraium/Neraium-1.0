"""Add an isolated immutable store for endpoint-keyed relationship artifacts.

No V1 table or historical record is altered. Production V1 readiness does not
depend on this prospective V2 table until a caller explicitly selects V2.
"""

from __future__ import annotations

from typing import Any


MIGRATION_ID = "008_create_relationship_lineage_v2_artifacts"
REQUIRED_MIGRATIONS = ("007_create_relationship_temporal_state",)
TABLE = "relationship_lineage_artifacts_v2"

DDL = """
CREATE TABLE telemetry.relationship_lineage_artifacts_v2 (
    artifact_ref TEXT PRIMARY KEY CHECK (artifact_ref ~ '^telemetry-relationship-artifact[.]v2:[0-9a-f]{64}$'),
    lineage_ref TEXT NOT NULL CHECK (lineage_ref ~ '^relationship-lineage[.]v2:[0-9a-f]{64}$'),
    contract_version TEXT NOT NULL CHECK (contract_version = 'telemetry-relationship-artifact.v2'),
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    system_id TEXT NOT NULL,
    asset_id TEXT,
    window_id TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    schema_fingerprint TEXT NOT NULL CHECK (schema_fingerprint ~ '^telemetry-analysis-schema[.]v2:[0-9a-f]{64}$'),
    window_content_digest TEXT NOT NULL CHECK (window_content_digest ~ '^telemetry-analysis-window-content[.]v2:[0-9a-f]{64}$'),
    pair_ref TEXT NOT NULL CHECK (pair_ref ~ '^relationship-endpoint-pair[.]v2:[0-9a-f]{64}$'),
    source_endpoint_id TEXT NOT NULL,
    target_endpoint_id TEXT NOT NULL,
    artifact_payload JSONB NOT NULL CHECK (
        jsonb_typeof(artifact_payload) = 'object' AND pg_column_size(artifact_payload) <= 1000000
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (source_endpoint_id <> target_endpoint_id),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, window_id, lineage_ref)
);
CREATE INDEX ix_relationship_lineage_v2_scope_window
    ON telemetry.relationship_lineage_artifacts_v2
    (resource_scope_id, tenant_scope_id, workspace_id, facility_id, system_id, window_id);

CREATE FUNCTION telemetry.reject_relationship_lineage_v2_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'relationship_lineage_v2_immutable';
END;
$$;
CREATE TRIGGER trg_relationship_lineage_v2_immutable
BEFORE UPDATE OR DELETE ON telemetry.relationship_lineage_artifacts_v2
FOR EACH ROW EXECUTE FUNCTION telemetry.reject_relationship_lineage_v2_mutation();
"""


def apply(conn: Any) -> None:
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (MIGRATION_ID,))
        cursor.execute(
            "SELECT migration_id FROM telemetry.schema_migrations WHERE migration_id = ANY(%s)",
            (list(REQUIRED_MIGRATIONS),),
        )
        if set(REQUIRED_MIGRATIONS) - {str(row[0]) for row in cursor.fetchall()}:
            raise RuntimeError("relationship_lineage_v2_prerequisite_missing")
        cursor.execute("SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s", (MIGRATION_ID,))
        if cursor.fetchone() is None:
            cursor.execute(DDL)
            cursor.execute("INSERT INTO telemetry.schema_migrations (migration_id) VALUES (%s)", (MIGRATION_ID,))
    conn.commit()


run = apply


def verify(conn: Any) -> dict[str, str]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s", (MIGRATION_ID,))
        if cursor.fetchone() is None:
            raise RuntimeError("relationship_lineage_v2_migration_not_applied")
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='telemetry' AND table_name=%s",
            (TABLE,),
        )
        if cursor.fetchone() is None:
            raise RuntimeError("relationship_lineage_v2_table_missing")
    return {"migration_id": MIGRATION_ID, "table": TABLE}


def downgrade(_conn: Any) -> None:
    raise RuntimeError("relationship_lineage_v2_downgrade_unsupported")
