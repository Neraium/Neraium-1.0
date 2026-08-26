"""Persist immutable canonical connector analysis-result artifacts.

This forward-only migration extends only the dedicated ``telemetry`` schema.
It does not backfill legacy completed windows because their exact in-memory
analysis artifacts no longer exist. Downgrade is deliberately unsupported:
dropping this table would destroy the durable analytical authority and its
audit lineage.
"""

from __future__ import annotations

from typing import Any


MIGRATION_ID = "005_persist_canonical_analysis_results"
REQUIRED_MIGRATIONS = ("004_extend_telemetry_ingestion_runtime",)

TABLE_NAME = "analysis_result_artifacts"
EXPECTED_COLUMNS = frozenset(
    {
        "id",
        "tenant_scope_id",
        "workspace_id",
        "resource_scope_id",
        "facility_id",
        "analysis_window_id",
        "connection_id",
        "source_ingestion_run_id",
        "system_id",
        "asset_id",
        "window_start",
        "window_end",
        "authority_digest",
        "artifact_schema_version",
        "execution_contract_version",
        "analysis_schema_version",
        "analysis_contract_version",
        "engine_name",
        "engine_version",
        "reference_metadata",
        "observation_count",
        "observation_lineage_digest",
        "finding_ids",
        "evidence_ids",
        "payload_encoding",
        "payload_digest",
        "payload_uncompressed_bytes",
        "payload_stored_bytes",
        "serialization_ms",
        "payload",
        "created_at",
    }
)
EXPECTED_INDEXES = frozenset(
    {
        "ux_telemetry_analysis_result_window",
        "ix_telemetry_analysis_result_run",
        "ix_telemetry_analysis_result_system_window",
    }
)
EXPECTED_CONSTRAINTS = frozenset(
    {
        "analysis_result_artifacts_pkey",
        "fk_telemetry_analysis_result_window",
        "fk_telemetry_analysis_result_run",
        "fk_telemetry_analysis_result_connection",
    }
)
EXPECTED_TRIGGERS = frozenset(
    {
        "trg_telemetry_analysis_result_validate_scope",
        "trg_telemetry_analysis_result_immutable",
    }
)

DDL = r"""
CREATE TABLE IF NOT EXISTS telemetry.analysis_result_artifacts (
    id UUID PRIMARY KEY,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    analysis_window_id UUID NOT NULL,
    connection_id UUID NOT NULL,
    source_ingestion_run_id UUID NOT NULL,
    system_id TEXT NOT NULL,
    asset_id TEXT,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    authority_digest TEXT NOT NULL CHECK (
        authority_digest ~ '^[0-9a-f]{64}$'
    ),
    artifact_schema_version TEXT NOT NULL CHECK (
        artifact_schema_version <> ''
    ),
    execution_contract_version TEXT NOT NULL CHECK (
        execution_contract_version <> ''
    ),
    analysis_schema_version TEXT NOT NULL CHECK (
        analysis_schema_version <> ''
    ),
    analysis_contract_version TEXT NOT NULL CHECK (
        analysis_contract_version <> ''
    ),
    engine_name TEXT,
    engine_version TEXT,
    reference_metadata JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (
        jsonb_typeof(reference_metadata) = 'object'
        AND pg_column_size(reference_metadata) <= 32768
    ),
    observation_count BIGINT NOT NULL CHECK (observation_count >= 0),
    observation_lineage_digest TEXT NOT NULL CHECK (
        observation_lineage_digest ~ '^[0-9a-f]{64}$'
    ),
    finding_ids JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (
        jsonb_typeof(finding_ids) = 'object'
    ),
    evidence_ids JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (
        jsonb_typeof(evidence_ids) = 'object'
        AND pg_column_size(finding_ids) + pg_column_size(evidence_ids) <= 65536
    ),
    payload_encoding TEXT NOT NULL CHECK (
        payload_encoding = 'zlib+canonical-json.v1'
    ),
    payload_digest TEXT NOT NULL CHECK (
        payload_digest ~ '^[0-9a-f]{64}$'
    ),
    payload_uncompressed_bytes BIGINT NOT NULL CHECK (
        payload_uncompressed_bytes > 0
        AND payload_uncompressed_bytes <= 268435456
    ),
    payload_stored_bytes BIGINT NOT NULL CHECK (
        payload_stored_bytes > 0
        AND payload_stored_bytes <= 268435456
    ),
    serialization_ms DOUBLE PRECISION NOT NULL CHECK (
        serialization_ms >= 0
        AND serialization_ms = serialization_ms
        AND serialization_ms NOT IN (
            'Infinity'::DOUBLE PRECISION,
            '-Infinity'::DOUBLE PRECISION
        )
    ),
    payload BYTEA NOT NULL CHECK (payload_stored_bytes = octet_length(payload)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (window_end > window_start),
    CONSTRAINT fk_telemetry_analysis_result_window
        FOREIGN KEY (
            resource_scope_id, tenant_scope_id, workspace_id, facility_id,
            analysis_window_id
        ) REFERENCES telemetry.analysis_windows (
            resource_scope_id, tenant_scope_id, workspace_id, facility_id, id
        ) ON DELETE RESTRICT,
    CONSTRAINT fk_telemetry_analysis_result_run
        FOREIGN KEY (
            resource_scope_id, tenant_scope_id, workspace_id, facility_id,
            connection_id, source_ingestion_run_id
        ) REFERENCES telemetry.ingestion_runs (
            resource_scope_id, tenant_scope_id, workspace_id, facility_id,
            connection_id, id
        ) ON DELETE RESTRICT,
    CONSTRAINT fk_telemetry_analysis_result_connection
        FOREIGN KEY (
            resource_scope_id, tenant_scope_id, workspace_id, facility_id,
            connection_id
        ) REFERENCES telemetry.data_connections (
            resource_scope_id, tenant_scope_id, workspace_id, facility_id, id
        ) ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_telemetry_analysis_result_window
    ON telemetry.analysis_result_artifacts (
        resource_scope_id, tenant_scope_id, workspace_id, facility_id,
        analysis_window_id
    );

CREATE INDEX IF NOT EXISTS ix_telemetry_analysis_result_run
    ON telemetry.analysis_result_artifacts (
        resource_scope_id, facility_id, connection_id,
        source_ingestion_run_id, created_at DESC
    );

CREATE INDEX IF NOT EXISTS ix_telemetry_analysis_result_system_window
    ON telemetry.analysis_result_artifacts (
        resource_scope_id, facility_id, system_id, COALESCE(asset_id, ''),
        window_start DESC
    );

CREATE OR REPLACE FUNCTION telemetry.validate_analysis_result_artifact_scope()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $function$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM telemetry.analysis_windows AS analysis_window
        JOIN telemetry.ingestion_runs AS source_run
          ON source_run.resource_scope_id = analysis_window.resource_scope_id
         AND source_run.tenant_scope_id = analysis_window.tenant_scope_id
         AND source_run.workspace_id = analysis_window.workspace_id
         AND source_run.facility_id = analysis_window.facility_id
         AND source_run.id = analysis_window.source_ingestion_run_id
        WHERE analysis_window.resource_scope_id = NEW.resource_scope_id
          AND analysis_window.tenant_scope_id = NEW.tenant_scope_id
          AND analysis_window.workspace_id = NEW.workspace_id
          AND analysis_window.facility_id = NEW.facility_id
          AND analysis_window.id = NEW.analysis_window_id
          AND analysis_window.source_ingestion_run_id = NEW.source_ingestion_run_id
          AND analysis_window.system_id = NEW.system_id
          AND analysis_window.asset_id IS NOT DISTINCT FROM NEW.asset_id
          AND analysis_window.window_start = NEW.window_start
          AND analysis_window.window_end = NEW.window_end
          AND analysis_window.authority_digest = NEW.authority_digest
          AND source_run.connection_id = NEW.connection_id
    ) THEN
        RAISE EXCEPTION 'telemetry_analysis_result_scope_mismatch'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$function$;

CREATE OR REPLACE FUNCTION telemetry.reject_analysis_result_artifact_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE EXCEPTION 'telemetry_analysis_result_artifact_immutable'
        USING ERRCODE = '55000';
END
$function$;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_telemetry_analysis_result_validate_scope'
          AND tgrelid = 'telemetry.analysis_result_artifacts'::regclass
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER trg_telemetry_analysis_result_validate_scope
            BEFORE INSERT ON telemetry.analysis_result_artifacts
            FOR EACH ROW
            EXECUTE FUNCTION telemetry.validate_analysis_result_artifact_scope();
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_telemetry_analysis_result_immutable'
          AND tgrelid = 'telemetry.analysis_result_artifacts'::regclass
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER trg_telemetry_analysis_result_immutable
            BEFORE UPDATE OR DELETE ON telemetry.analysis_result_artifacts
            FOR EACH ROW
            EXECUTE FUNCTION telemetry.reject_analysis_result_artifact_mutation();
    END IF;
END
$migration$;
"""


def apply(conn: Any) -> None:
    """Apply the additive migration once under the shared ledger lock."""
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS telemetry")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry.schema_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (MIGRATION_ID,))
        cur.execute(
            "SELECT migration_id FROM telemetry.schema_migrations "
            "WHERE migration_id = ANY(%s)",
            (list(REQUIRED_MIGRATIONS),),
        )
        present = {str(row[0]) for row in cur.fetchall()}
        missing = set(REQUIRED_MIGRATIONS) - present
        if missing:
            raise RuntimeError(
                "telemetry_result_artifact_migration_prerequisite_missing:"
                + ",".join(sorted(missing))
            )
        cur.execute(
            "SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s",
            (MIGRATION_ID,),
        )
        if cur.fetchone():
            conn.commit()
            return
        cur.execute(DDL)
        cur.execute(
            "INSERT INTO telemetry.schema_migrations (migration_id) VALUES (%s)",
            (MIGRATION_ID,),
        )
    conn.commit()


run = apply


def verify(conn: Any) -> dict[str, Any]:
    """Verify the migration ledger and immutable artifact relation."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s",
            (MIGRATION_ID,),
        )
        if cur.fetchone() is None:
            raise RuntimeError("telemetry_result_artifact_migration_not_applied")
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'telemetry' AND table_name = %s
            """,
            (TABLE_NAME,),
        )
        actual_columns = {str(row[0]) for row in cur.fetchall()}
        cur.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'telemetry' AND indexname = ANY(%s)
            """,
            (sorted(EXPECTED_INDEXES),),
        )
        actual_indexes = {str(row[0]) for row in cur.fetchall()}
        cur.execute(
            """
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE constraint_schema = 'telemetry'
              AND table_name = %s
              AND constraint_name = ANY(%s)
            """,
            (TABLE_NAME, sorted(EXPECTED_CONSTRAINTS)),
        )
        actual_constraints = {str(row[0]) for row in cur.fetchall()}
        cur.execute(
            """
            SELECT trigger_name
            FROM information_schema.triggers
            WHERE event_object_schema = 'telemetry'
              AND event_object_table = %s
              AND trigger_name = ANY(%s)
            """,
            (TABLE_NAME, sorted(EXPECTED_TRIGGERS)),
        )
        actual_triggers = {str(row[0]) for row in cur.fetchall()}

    missing_columns = EXPECTED_COLUMNS - actual_columns
    missing_indexes = EXPECTED_INDEXES - actual_indexes
    missing_constraints = EXPECTED_CONSTRAINTS - actual_constraints
    missing_triggers = EXPECTED_TRIGGERS - actual_triggers
    if (
        missing_columns
        or missing_indexes
        or missing_constraints
        or missing_triggers
    ):
        raise RuntimeError(
            "telemetry_result_artifact_migration_incomplete:"
            f"columns={sorted(missing_columns)},"
            f"indexes={sorted(missing_indexes)},"
            f"constraints={sorted(missing_constraints)},"
            f"triggers={sorted(missing_triggers)}"
        )
    return {
        "migration_id": MIGRATION_ID,
        "columns": sorted(actual_columns),
        "indexes": sorted(actual_indexes),
        "constraints": sorted(actual_constraints),
        "triggers": sorted(actual_triggers),
    }


def downgrade(_conn: Any) -> None:
    """Refuse destructive removal of canonical analytical authority."""
    raise RuntimeError("telemetry_result_artifact_migration_downgrade_unsupported")
