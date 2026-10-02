"""Add immutable V2 execution index without changing V1 result storage."""

from __future__ import annotations

from typing import Any

MIGRATION_ID = "009_create_endpoint_analysis_executions_v2"
REQUIRED_MIGRATIONS = ("008_create_relationship_lineage_v2_artifacts",)
TABLE = "endpoint_analysis_executions_v2"

DDL = """
CREATE TABLE telemetry.endpoint_analysis_executions_v2 (
    execution_ref TEXT PRIMARY KEY CHECK (execution_ref ~ '^telemetry-endpoint-execution[.]v2:[0-9a-f]{64}$'),
    contract_version TEXT NOT NULL CHECK (contract_version = 'telemetry-endpoint-execution.v2'),
    resource_scope_id TEXT NOT NULL,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    system_id TEXT NOT NULL,
    asset_id TEXT,
    connection_id UUID NOT NULL,
    window_id UUID NOT NULL,
    source_run_id UUID NOT NULL,
    schema_fingerprint TEXT NOT NULL,
    window_content_digest TEXT NOT NULL,
    window_payload JSONB NOT NULL CHECK (jsonb_typeof(window_payload) = 'object'),
    result_payload TEXT NOT NULL CHECK (octet_length(result_payload) <= 268435456),
    result_digest TEXT NOT NULL CHECK (result_digest ~ '^telemetry-endpoint-result[.]v2:[0-9a-f]{64}$'),
    relationship_refs JSONB NOT NULL CHECK (jsonb_typeof(relationship_refs) = 'array'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, window_id)
);
CREATE INDEX ix_endpoint_analysis_executions_v2_run
    ON telemetry.endpoint_analysis_executions_v2
    (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id, source_run_id);
CREATE FUNCTION telemetry.reject_endpoint_analysis_execution_v2_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'endpoint_analysis_execution_v2_immutable';
END;
$$;
CREATE TRIGGER trg_endpoint_analysis_execution_v2_immutable
BEFORE UPDATE OR DELETE ON telemetry.endpoint_analysis_executions_v2
FOR EACH ROW EXECUTE FUNCTION telemetry.reject_endpoint_analysis_execution_v2_mutation();
"""


def apply(conn: Any) -> None:
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (MIGRATION_ID,))
        cursor.execute(
            "SELECT migration_id FROM telemetry.schema_migrations WHERE migration_id = ANY(%s)",
            (list(REQUIRED_MIGRATIONS),),
        )
        if set(REQUIRED_MIGRATIONS) - {str(row[0]) for row in cursor.fetchall()}:
            raise RuntimeError("endpoint_analysis_v2_prerequisite_missing")
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
            raise RuntimeError("endpoint_analysis_v2_migration_not_applied")
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='telemetry' AND table_name=%s",
            (TABLE,),
        )
        if cursor.fetchone() is None:
            raise RuntimeError("endpoint_analysis_v2_table_missing")
    return {"migration_id": MIGRATION_ID, "table": TABLE}


def downgrade(_conn: Any) -> None:
    raise RuntimeError("endpoint_analysis_v2_downgrade_unsupported")
