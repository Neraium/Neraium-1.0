"""Add durable ingestion lineage and scheduling constraints.

This forward-only migration extends only the dedicated ``telemetry`` schema.
It never reads, assigns, updates, or deletes legacy connection or upload rows.
Downgrade is deliberately unsupported because removing provenance columns would
destroy evidence lineage; disposable schemas should be recreated instead.
"""

from __future__ import annotations

from typing import Any


MIGRATION_ID = "004_extend_telemetry_ingestion_runtime"
REQUIRED_MIGRATIONS = (
    "002_create_telemetry_connection_tables",
    "003_seed_telemetry_canonical_signal_concepts_v1",
)

EXPECTED_COLUMNS = {
    "ingestion_runs": frozenset({"source_run_id"}),
    "normalized_observations": frozenset(
        {
            "provider_event_id",
            "mapping_provenance",
            "mapping_actor_id",
            "mapping_mapped_at",
            "mapping_authority_digest",
        }
    ),
    "observation_rejections": frozenset(
        {
            "disposition",
            "provider_event_id",
            "mapping_id",
            "original_value",
            "original_unit",
            "reported_quality",
            "occurrence_count",
            "first_seen_at",
            "last_seen_at",
        }
    ),
    "analysis_windows": frozenset(
        {
            "execution_claim_token",
            "execution_claim_expires_at",
            "execution_attempt_count",
            "result_digest",
            "result_metadata",
            "evidence_lineage",
            "completed_at",
        }
    ),
    "analysis_authority_snapshots": frozenset(
        {
            "id",
            "tenant_scope_id",
            "workspace_id",
            "resource_scope_id",
            "facility_id",
            "system_id",
            "asset_id",
            "authority_digest",
            "identity_digest",
            "authority_snapshot",
            "attested_by",
            "attested_at",
        }
    ),
}

EXPECTED_INDEXES = frozenset(
    {
        "ux_telemetry_active_retry_source",
        "ux_telemetry_observation_provider_event",
        "ix_telemetry_connection_worker_due",
        "ux_telemetry_active_backfill_connection",
        "ix_telemetry_rejection_disposition_time",
        "ux_telemetry_ingestion_run_scoped_connection_id",
        "ux_telemetry_analysis_authority_identity",
        "ix_telemetry_analysis_authority_scope",
        "ix_telemetry_analysis_execution_claim_expiry",
    }
)
EXPECTED_CONSTRAINTS = frozenset(
    {
        "fk_telemetry_ingestion_run_source",
        "telemetry_observation_rejections_quality_state_check_v2",
    }
)

DDL = r"""
ALTER TABLE telemetry.ingestion_runs
    ADD COLUMN IF NOT EXISTS source_run_id UUID;

CREATE UNIQUE INDEX IF NOT EXISTS ux_telemetry_ingestion_run_scoped_connection_id
    ON telemetry.ingestion_runs (
        resource_scope_id, tenant_scope_id, workspace_id, facility_id,
        connection_id, id
    );

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_telemetry_ingestion_run_source'
          AND conrelid = 'telemetry.ingestion_runs'::regclass
    ) THEN
        ALTER TABLE telemetry.ingestion_runs
            ADD CONSTRAINT fk_telemetry_ingestion_run_source
            FOREIGN KEY (
                resource_scope_id, tenant_scope_id, workspace_id, facility_id,
                connection_id, source_run_id
            ) REFERENCES telemetry.ingestion_runs (
                resource_scope_id, tenant_scope_id, workspace_id, facility_id,
                connection_id, id
            ) ON DELETE RESTRICT;
    END IF;
END
$migration$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_telemetry_active_retry_source
    ON telemetry.ingestion_runs
        (resource_scope_id, connection_id, source_run_id)
    WHERE mode = 'retry' AND status IN ('pending', 'running')
      AND source_run_id IS NOT NULL;

ALTER TABLE telemetry.normalized_observations
    ADD COLUMN IF NOT EXISTS provider_event_id TEXT,
    ADD COLUMN IF NOT EXISTS mapping_provenance TEXT,
    ADD COLUMN IF NOT EXISTS mapping_actor_id TEXT,
    ADD COLUMN IF NOT EXISTS mapping_mapped_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS mapping_authority_digest TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_telemetry_observation_provider_event
    ON telemetry.normalized_observations
        (resource_scope_id, connection_id, provider_event_id)
    WHERE provider_event_id IS NOT NULL;

ALTER TABLE telemetry.observation_rejections
    ADD COLUMN IF NOT EXISTS disposition TEXT NOT NULL DEFAULT 'rejected'
        CHECK (disposition IN ('duplicate', 'quarantined', 'rejected')),
    ADD COLUMN IF NOT EXISTS occurrence_count BIGINT NOT NULL DEFAULT 1
        CHECK (occurrence_count > 0),
    ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS provider_event_id TEXT,
    ADD COLUMN IF NOT EXISTS mapping_id UUID,
    ADD COLUMN IF NOT EXISTS original_value JSONB,
    ADD COLUMN IF NOT EXISTS original_unit TEXT,
    ADD COLUMN IF NOT EXISTS reported_quality TEXT;

ALTER TABLE telemetry.observation_rejections
    DROP CONSTRAINT IF EXISTS observation_rejections_quality_state_check;
ALTER TABLE telemetry.observation_rejections
    DROP CONSTRAINT IF EXISTS telemetry_observation_rejections_quality_state_check_v2;
ALTER TABLE telemetry.observation_rejections
    ADD CONSTRAINT telemetry_observation_rejections_quality_state_check_v2
    CHECK (quality_state IN (
        'stale', 'missing', 'invalid_value', 'unit_unresolved',
        'timestamp_invalid', 'mapping_required', 'format_invalid'
    ));

CREATE TABLE IF NOT EXISTS telemetry.analysis_authority_snapshots (
    id UUID PRIMARY KEY,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    system_id TEXT NOT NULL,
    asset_id TEXT,
    authority_digest TEXT NOT NULL CHECK (authority_digest ~ '^[0-9a-f]{64}$'),
    identity_digest TEXT NOT NULL CHECK (identity_digest ~ '^[0-9a-f]{64}$'),
    authority_snapshot JSONB NOT NULL CHECK (
        jsonb_typeof(authority_snapshot) = 'object'
        AND pg_column_size(authority_snapshot) <= 16384
    ),
    attested_by TEXT NOT NULL,
    attested_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_telemetry_analysis_authority_identity
    ON telemetry.analysis_authority_snapshots (
        resource_scope_id, system_id, COALESCE(asset_id, ''), authority_digest
    );

CREATE INDEX IF NOT EXISTS ix_telemetry_analysis_authority_scope
    ON telemetry.analysis_authority_snapshots (
        resource_scope_id, facility_id, system_id, COALESCE(asset_id, ''),
        attested_at DESC
    );

ALTER TABLE telemetry.analysis_windows
    ADD COLUMN IF NOT EXISTS execution_claim_token UUID,
    ADD COLUMN IF NOT EXISTS execution_claim_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS execution_attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (execution_attempt_count >= 0 AND execution_attempt_count <= 100),
    ADD COLUMN IF NOT EXISTS result_digest TEXT
        CHECK (result_digest IS NULL OR result_digest ~ '^[0-9a-f]{64}$'),
    ADD COLUMN IF NOT EXISTS result_metadata JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (jsonb_typeof(result_metadata) = 'object'
               AND pg_column_size(result_metadata) <= 16384),
    ADD COLUMN IF NOT EXISTS evidence_lineage JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (jsonb_typeof(evidence_lineage) = 'object'
               AND pg_column_size(evidence_lineage) <= 65536),
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_telemetry_analysis_execution_claim_expiry
    ON telemetry.analysis_windows (execution_claim_expires_at, id)
    WHERE status = 'running';

CREATE INDEX IF NOT EXISTS ix_telemetry_connection_worker_due
    ON telemetry.data_connections (next_attempt_at, id)
    WHERE enabled = TRUE AND archived_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_telemetry_active_backfill_connection
    ON telemetry.ingestion_runs (resource_scope_id, connection_id)
    WHERE (mode = 'backfill' OR (mode = 'retry' AND range_start IS NOT NULL))
      AND status IN ('pending', 'running');

CREATE INDEX IF NOT EXISTS ix_telemetry_rejection_disposition_time
    ON telemetry.observation_rejections
        (resource_scope_id, connection_id, disposition, last_seen_at DESC);

ALTER TABLE telemetry.telemetry_audit_events
    DROP CONSTRAINT IF EXISTS telemetry_audit_events_action_check;
ALTER TABLE telemetry.telemetry_audit_events
    ADD CONSTRAINT telemetry_audit_events_action_check CHECK (action IN (
        'connection_created', 'connection_updated', 'credential_binding_changed',
        'validation_completed', 'signal_mapping_changed',
        'connection_enabled', 'connection_disabled', 'connection_archived',
        'backfill_started', 'backfill_completed', 'backfill_failed',
        'ingestion_retry_requested'
    ));
"""


def apply(conn: Any) -> None:
    """Apply the additive migration once, under the shared ledger lock."""
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
                "telemetry_ingestion_migration_prerequisite_missing:"
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


def verify(conn: Any) -> dict[str, Any]:
    """Verify the ledger entry and every additive column."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s",
            (MIGRATION_ID,),
        )
        if cur.fetchone() is None:
            raise RuntimeError("telemetry_ingestion_migration_not_applied")
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'telemetry' AND table_name = ANY(%s)
            """,
            (sorted(EXPECTED_COLUMNS),),
        )
        actual: dict[str, set[str]] = {name: set() for name in EXPECTED_COLUMNS}
        for table_name, column_name in cur.fetchall():
            if str(table_name) in actual:
                actual[str(table_name)].add(str(column_name))
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
              AND constraint_name = ANY(%s)
            """,
            (sorted(EXPECTED_CONSTRAINTS),),
        )
        actual_constraints = {str(row[0]) for row in cur.fetchall()}
    missing = {
        table: sorted(expected - actual[table])
        for table, expected in EXPECTED_COLUMNS.items()
        if expected - actual[table]
    }
    if missing:
        raise RuntimeError(f"telemetry_ingestion_migration_incomplete:{missing}")
    missing_indexes = EXPECTED_INDEXES - actual_indexes
    missing_constraints = EXPECTED_CONSTRAINTS - actual_constraints
    if missing_indexes or missing_constraints:
        raise RuntimeError(
            "telemetry_ingestion_migration_incomplete:"
            f"indexes={sorted(missing_indexes)},"
            f"constraints={sorted(missing_constraints)}"
        )
    return {
        "migration_id": MIGRATION_ID,
        "columns": actual,
        "indexes": sorted(actual_indexes),
        "constraints": sorted(actual_constraints),
    }


def downgrade(_conn: Any) -> None:
    """Refuse destructive lineage removal in every environment."""
    raise RuntimeError("telemetry_ingestion_migration_downgrade_unsupported")
