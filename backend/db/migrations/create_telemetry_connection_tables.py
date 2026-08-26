"""Add the production telemetry connection and canonical-observation schema.

This migration is intentionally additive.  It does not inspect, copy, assign, or
delete rows from the legacy SQLite/runtime connection path.  Existing production
data is upgraded with forward fixes; the guarded rollback helper at the bottom is
only for empty, disposable test schemas.
"""

from __future__ import annotations

from typing import Any


MIGRATION_ID = "002_create_telemetry_connection_tables"
SCHEMA_NAME = "telemetry"

EXPECTED_TABLES = frozenset(
    {
        "analysis_window_observations",
        "analysis_windows",
        "canonical_signal_concepts",
        "connection_checkpoints",
        "connection_health",
        "connection_secret_bindings",
        "data_connections",
        "external_signals",
        "ingestion_runs",
        "normalized_observations",
        "observation_rejections",
        "schema_migrations",
        "signal_mappings",
        "telemetry_audit_events",
    }
)

EXPECTED_COLUMNS = {
    "data_connections": frozenset(
        {
            "tenant_scope_id",
            "workspace_id",
            "resource_scope_id",
            "facility_id",
            "secret_binding_id",
            "lease_token",
            "lease_expires_at",
        }
    ),
    "connection_checkpoints": frozenset(
        {"resource_scope_id", "connection_id", "mode", "cursor_payload", "revision"}
    ),
    "normalized_observations": frozenset(
        {
            "resource_scope_id",
            "connection_id",
            "external_signal_id",
            "mapping_id",
            "source_timestamp_raw",
            "timestamp_normalization_version",
            "observed_at_utc",
            "original_value",
            "normalized_value",
            "source_record_digest",
        }
    ),
    "analysis_window_observations": frozenset(
        {"resource_scope_id", "analysis_window_id", "observation_id"}
    ),
}


DDL = r"""
CREATE SCHEMA IF NOT EXISTS telemetry;

CREATE TABLE IF NOT EXISTS telemetry.schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE telemetry.canonical_signal_concepts (
    id UUID PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    physical_dimension TEXT NOT NULL,
    canonical_unit TEXT NOT NULL,
    description TEXT,
    taxonomy_version INTEGER NOT NULL CHECK (taxonomy_version > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (canonical_name, taxonomy_version)
);

CREATE TABLE telemetry.data_connections (
    id UUID PRIMARY KEY,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 160),
    connector_type TEXT NOT NULL CHECK (connector_type IN ('https_telemetry', 'historian_template')),
    lifecycle_status TEXT NOT NULL DEFAULT 'draft' CHECK (lifecycle_status IN (
        'draft', 'validating', 'connected', 'degraded', 'disconnected',
        'disabled', 'error', 'archived'
    )),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    safe_config JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (jsonb_typeof(safe_config) = 'object'),
    secret_binding_id UUID,
    timezone TEXT NOT NULL,
    polling_interval_seconds INTEGER NOT NULL CHECK (polling_interval_seconds BETWEEN 30 AND 86400),
    next_attempt_at TIMESTAMPTZ,
    last_attempt_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_healthy_at TIMESTAMPTZ,
    last_telemetry_at TIMESTAMPTZ,
    last_error_code TEXT,
    last_error_summary TEXT CHECK (last_error_summary IS NULL OR char_length(last_error_summary) <= 500),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    lease_owner TEXT,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    CHECK ((lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL)
        OR (lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)),
    CHECK ((lifecycle_status = 'archived') = (archived_at IS NOT NULL)),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
);

CREATE UNIQUE INDEX ux_telemetry_connection_active_name
    ON telemetry.data_connections (resource_scope_id, facility_id, lower(name))
    WHERE archived_at IS NULL;
CREATE INDEX ix_telemetry_connection_scope_updated
    ON telemetry.data_connections (resource_scope_id, facility_id, updated_at DESC);
CREATE INDEX ix_telemetry_connection_tenant_scope
    ON telemetry.data_connections
        (tenant_scope_id, resource_scope_id, facility_id, updated_at DESC);
CREATE INDEX ix_telemetry_connection_due
    ON telemetry.data_connections (resource_scope_id, next_attempt_at)
    WHERE enabled = TRUE AND archived_at IS NULL;
CREATE INDEX ix_telemetry_connection_lease
    ON telemetry.data_connections (lease_expires_at)
    WHERE lease_owner IS NOT NULL;

CREATE TABLE telemetry.connection_secret_bindings (
    id UUID PRIMARY KEY,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    connection_id UUID NOT NULL,
    provider TEXT NOT NULL CHECK (provider = 'aws_secrets_manager'),
    internal_reference TEXT NOT NULL,
    version_marker TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id, connection_id),
    UNIQUE (resource_scope_id, connection_id),
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id)
        REFERENCES telemetry.data_connections
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT
);

ALTER TABLE telemetry.data_connections
    ADD CONSTRAINT fk_telemetry_connection_secret_binding
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, secret_binding_id, id)
    REFERENCES telemetry.connection_secret_bindings
        (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id, connection_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE telemetry.external_signals (
    id UUID PRIMARY KEY,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    connection_id UUID NOT NULL,
    external_tag_id TEXT NOT NULL,
    external_tag_name TEXT NOT NULL,
    display_label TEXT,
    source_unit TEXT,
    sample_cadence_seconds DOUBLE PRECISION CHECK (sample_cadence_seconds IS NULL OR sample_cadence_seconds > 0),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    mapping_status TEXT NOT NULL DEFAULT 'unmapped'
        CHECK (mapping_status IN ('unmapped', 'mapped', 'invalid', 'disabled')),
    last_observed_at TIMESTAMPTZ,
    quality_state TEXT CHECK (quality_state IS NULL OR quality_state IN (
        'good', 'stale', 'missing', 'invalid_value', 'unit_unresolved',
        'timestamp_invalid', 'mapping_required', 'format_invalid'
    )),
    source_metadata JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (jsonb_typeof(source_metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id),
    UNIQUE (resource_scope_id, connection_id, external_tag_id),
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id)
        REFERENCES telemetry.data_connections
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT
);
CREATE INDEX ix_telemetry_external_signal_mapping
    ON telemetry.external_signals (resource_scope_id, connection_id, mapping_status, updated_at DESC);
CREATE INDEX ix_telemetry_external_signal_freshness
    ON telemetry.external_signals (resource_scope_id, facility_id, last_observed_at DESC);

CREATE TABLE telemetry.signal_mappings (
    id UUID PRIMARY KEY,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    connection_id UUID NOT NULL,
    external_signal_id UUID NOT NULL,
    system_id TEXT NOT NULL,
    asset_id TEXT,
    canonical_concept_id UUID NOT NULL REFERENCES telemetry.canonical_signal_concepts(id) ON DELETE RESTRICT,
    canonical_signal_name TEXT NOT NULL,
    source_unit TEXT NOT NULL,
    canonical_unit TEXT NOT NULL,
    conversion_id TEXT NOT NULL,
    conversion_version TEXT NOT NULL,
    expected_cadence_seconds DOUBLE PRECISION
        CHECK (expected_cadence_seconds IS NULL OR expected_cadence_seconds > 0),
    source_timezone TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    provenance TEXT NOT NULL CHECK (provenance IN ('manual', 'approved_suggestion', 'imported_verified')),
    provenance_reason TEXT,
    mapped_by TEXT NOT NULL,
    mapped_at TIMESTAMPTZ NOT NULL,
    authority_digest TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id),
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id)
        REFERENCES telemetry.data_connections
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, external_signal_id)
        REFERENCES telemetry.external_signals
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT
);
CREATE UNIQUE INDEX ux_telemetry_signal_mapping_enabled
    ON telemetry.signal_mappings (resource_scope_id, external_signal_id)
    WHERE enabled = TRUE;
CREATE UNIQUE INDEX ux_telemetry_signal_mapping_canonical_hierarchy
    ON telemetry.signal_mappings (
        resource_scope_id, connection_id, facility_id, system_id,
        COALESCE(asset_id, ''), canonical_concept_id
    )
    WHERE enabled = TRUE;
CREATE INDEX ix_telemetry_signal_mapping_hierarchy
    ON telemetry.signal_mappings
        (resource_scope_id, facility_id, system_id, asset_id, canonical_concept_id)
    WHERE enabled = TRUE;

CREATE TABLE telemetry.ingestion_runs (
    id UUID PRIMARY KEY,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    connection_id UUID NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('validation', 'discovery', 'incremental', 'backfill', 'retry')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'succeeded', 'partial', 'failed', 'cancelled')),
    lease_token UUID,
    range_start TIMESTAMPTZ,
    range_end TIMESTAMPTZ,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    pages_processed INTEGER NOT NULL DEFAULT 0 CHECK (pages_processed >= 0),
    observations_received BIGINT NOT NULL DEFAULT 0 CHECK (observations_received >= 0),
    observations_accepted BIGINT NOT NULL DEFAULT 0 CHECK (observations_accepted >= 0),
    observations_rejected BIGINT NOT NULL DEFAULT 0 CHECK (observations_rejected >= 0),
    observations_duplicate BIGINT NOT NULL DEFAULT 0 CHECK (observations_duplicate >= 0),
    observations_out_of_order BIGINT NOT NULL DEFAULT 0 CHECK (observations_out_of_order >= 0),
    latency_ms INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
    checkpoint_before_digest TEXT,
    checkpoint_after_digest TEXT,
    error_code TEXT,
    error_summary TEXT CHECK (error_summary IS NULL OR char_length(error_summary) <= 500),
    actor_id TEXT,
    worker_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (range_end IS NULL OR range_start IS NOT NULL),
    CHECK (range_end IS NULL OR range_end > range_start),
    CHECK ((status IN ('succeeded', 'partial', 'failed', 'cancelled')) = (finished_at IS NOT NULL)),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id),
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id)
        REFERENCES telemetry.data_connections
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT
);
CREATE INDEX ix_telemetry_ingestion_run_connection_time
    ON telemetry.ingestion_runs (resource_scope_id, connection_id, started_at DESC);
CREATE INDEX ix_telemetry_ingestion_run_tenant_connection_time
    ON telemetry.ingestion_runs
        (tenant_scope_id, resource_scope_id, connection_id, started_at DESC);
CREATE INDEX ix_telemetry_ingestion_run_status_time
    ON telemetry.ingestion_runs (resource_scope_id, status, started_at);

CREATE TABLE telemetry.connection_checkpoints (
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    connection_id UUID NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('discovery', 'incremental', 'backfill')),
    cursor_payload JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (
        jsonb_typeof(cursor_payload) = 'object' AND pg_column_size(cursor_payload) <= 65536
    ),
    high_water_at TIMESTAMPTZ,
    revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    updated_run_id UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (resource_scope_id, connection_id, mode),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id, mode),
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id)
        REFERENCES telemetry.data_connections
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, updated_run_id)
        REFERENCES telemetry.ingestion_runs
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT
);

CREATE TABLE telemetry.normalized_observations (
    id UUID PRIMARY KEY,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    system_id TEXT NOT NULL,
    asset_id TEXT,
    connection_id UUID NOT NULL,
    ingestion_run_id UUID NOT NULL,
    external_signal_id UUID NOT NULL,
    mapping_id UUID NOT NULL,
    mapping_revision INTEGER NOT NULL CHECK (mapping_revision > 0),
    canonical_concept_id UUID NOT NULL REFERENCES telemetry.canonical_signal_concepts(id) ON DELETE RESTRICT,
    canonical_signal_name TEXT NOT NULL,
    external_tag_id TEXT NOT NULL,
    source_timestamp_raw TEXT NOT NULL,
    source_timezone TEXT NOT NULL,
    source_offset TEXT,
    timestamp_normalization_version TEXT NOT NULL,
    observed_at_utc TIMESTAMPTZ NOT NULL,
    ingested_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    original_value JSONB NOT NULL,
    original_unit TEXT,
    normalized_value DOUBLE PRECISION CHECK (
        normalized_value IS NULL OR (
            normalized_value = normalized_value AND normalized_value NOT IN
                ('Infinity'::DOUBLE PRECISION, '-Infinity'::DOUBLE PRECISION)
        )
    ),
    canonical_unit TEXT,
    conversion_id TEXT,
    conversion_version TEXT,
    quality_state TEXT NOT NULL CHECK (quality_state IN (
        'good', 'stale', 'missing', 'invalid_value', 'unit_unresolved',
        'timestamp_invalid', 'mapping_required', 'format_invalid'
    )),
    ingestion_disposition TEXT NOT NULL CHECK (ingestion_disposition IN (
        'accepted', 'duplicate', 'out_of_order_accepted', 'quarantined', 'rejected'
    )),
    analysis_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    reason_codes TEXT[] NOT NULL DEFAULT '{}',
    source_record_digest TEXT NOT NULL,
    source_metadata JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (
        jsonb_typeof(source_metadata) = 'object' AND pg_column_size(source_metadata) <= 65536
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id),
    UNIQUE (resource_scope_id, connection_id, external_signal_id, source_record_digest),
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id)
        REFERENCES telemetry.data_connections
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, ingestion_run_id)
        REFERENCES telemetry.ingestion_runs
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, external_signal_id)
        REFERENCES telemetry.external_signals
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, mapping_id)
        REFERENCES telemetry.signal_mappings
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT
);
CREATE INDEX ix_telemetry_observation_connection_time
    ON telemetry.normalized_observations
        (resource_scope_id, connection_id, observed_at_utc DESC);
CREATE INDEX ix_telemetry_observation_tenant_connection_time
    ON telemetry.normalized_observations
        (tenant_scope_id, resource_scope_id, connection_id, observed_at_utc DESC);
CREATE INDEX ix_telemetry_observation_signal_time
    ON telemetry.normalized_observations
        (resource_scope_id, facility_id, system_id, canonical_concept_id, observed_at_utc DESC)
    WHERE analysis_eligible = TRUE;
CREATE INDEX ix_telemetry_observation_run
    ON telemetry.normalized_observations (resource_scope_id, ingestion_run_id);

CREATE TABLE telemetry.observation_rejections (
    id UUID PRIMARY KEY,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    connection_id UUID NOT NULL,
    ingestion_run_id UUID NOT NULL,
    external_signal_id UUID,
    external_tag_id TEXT,
    source_timestamp_raw TEXT,
    source_record_digest TEXT NOT NULL,
    quality_state TEXT NOT NULL CHECK (quality_state IN (
        'invalid_value', 'unit_unresolved', 'timestamp_invalid',
        'mapping_required', 'format_invalid'
    )),
    reason_code TEXT NOT NULL,
    safe_context JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (
        jsonb_typeof(safe_context) = 'object' AND pg_column_size(safe_context) <= 16384
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id),
    UNIQUE (resource_scope_id, connection_id, source_record_digest, reason_code),
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id)
        REFERENCES telemetry.data_connections
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, ingestion_run_id)
        REFERENCES telemetry.ingestion_runs
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, external_signal_id)
        REFERENCES telemetry.external_signals
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT
);
CREATE INDEX ix_telemetry_rejection_connection_time
    ON telemetry.observation_rejections (resource_scope_id, connection_id, created_at DESC);

CREATE TABLE telemetry.connection_health (
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    connection_id UUID NOT NULL,
    aggregate_status TEXT NOT NULL CHECK (aggregate_status IN (
        'unknown', 'healthy', 'degraded', 'disconnected', 'error'
    )),
    reachability_state TEXT NOT NULL CHECK (reachability_state IN
        ('healthy', 'degraded', 'unhealthy', 'unknown', 'not_applicable')),
    authentication_state TEXT NOT NULL CHECK (authentication_state IN
        ('healthy', 'degraded', 'unhealthy', 'unknown', 'not_applicable')),
    telemetry_freshness_state TEXT NOT NULL CHECK (telemetry_freshness_state IN
        ('healthy', 'degraded', 'unhealthy', 'unknown', 'not_applicable')),
    mapping_completeness_state TEXT NOT NULL CHECK (mapping_completeness_state IN
        ('healthy', 'degraded', 'unhealthy', 'unknown', 'not_applicable')),
    data_quality_state TEXT NOT NULL CHECK (data_quality_state IN
        ('healthy', 'degraded', 'unhealthy', 'unknown', 'not_applicable')),
    worker_checkpoint_state TEXT NOT NULL CHECK (worker_checkpoint_state IN
        ('healthy', 'degraded', 'unhealthy', 'unknown', 'not_applicable')),
    discovered_signal_count INTEGER NOT NULL DEFAULT 0 CHECK (discovered_signal_count >= 0),
    mapped_signal_count INTEGER NOT NULL DEFAULT 0 CHECK (mapped_signal_count >= 0),
    healthy_signal_count INTEGER NOT NULL DEFAULT 0 CHECK (healthy_signal_count >= 0),
    stale_signal_count INTEGER NOT NULL DEFAULT 0 CHECK (stale_signal_count >= 0),
    last_healthy_at TIMESTAMPTZ,
    last_evaluated_at TIMESTAMPTZ NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (jsonb_typeof(details) = 'object'),
    PRIMARY KEY (resource_scope_id, connection_id),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id),
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id)
        REFERENCES telemetry.data_connections
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT
);
CREATE INDEX ix_telemetry_health_facility
    ON telemetry.connection_health (resource_scope_id, facility_id, aggregate_status, last_evaluated_at DESC);

CREATE TABLE telemetry.telemetry_audit_events (
    id UUID PRIMARY KEY,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    connection_id UUID NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN (
        'connection_created', 'connection_updated', 'credential_binding_changed',
        'validation_completed', 'signal_mapping_changed',
        'connection_enabled', 'connection_disabled',
        'connection_archived', 'backfill_started', 'backfill_completed',
        'backfill_failed'
    )),
    before_digest TEXT,
    after_digest TEXT,
    safe_detail JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (
        jsonb_typeof(safe_detail) = 'object' AND pg_column_size(safe_detail) <= 16384
    ),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id),
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, connection_id)
        REFERENCES telemetry.data_connections
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT
);
CREATE INDEX ix_telemetry_audit_scope_time
    ON telemetry.telemetry_audit_events (resource_scope_id, facility_id, occurred_at DESC);
CREATE INDEX ix_telemetry_audit_connection_time
    ON telemetry.telemetry_audit_events (resource_scope_id, connection_id, occurred_at DESC);

CREATE TABLE telemetry.analysis_windows (
    id UUID PRIMARY KEY,
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    system_id TEXT NOT NULL,
    asset_id TEXT,
    source_ingestion_run_id UUID NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'eligible', 'running', 'completed', 'failed', 'ineligible')),
    authority_digest TEXT NOT NULL,
    quality_summary JSONB NOT NULL DEFAULT '{}'::JSONB CHECK (jsonb_typeof(quality_summary) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (window_end > window_start),
    UNIQUE (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id),
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, source_ingestion_run_id)
        REFERENCES telemetry.ingestion_runs
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT
);
CREATE INDEX ix_telemetry_analysis_window_hierarchy_time
    ON telemetry.analysis_windows
        (resource_scope_id, facility_id, system_id, asset_id, window_start DESC, window_end DESC);

CREATE TABLE telemetry.analysis_window_observations (
    tenant_scope_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    resource_scope_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    analysis_window_id UUID NOT NULL,
    observation_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (resource_scope_id, analysis_window_id, observation_id),
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, analysis_window_id)
        REFERENCES telemetry.analysis_windows
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT,
    FOREIGN KEY (resource_scope_id, tenant_scope_id, workspace_id, facility_id, observation_id)
        REFERENCES telemetry.normalized_observations
            (resource_scope_id, tenant_scope_id, workspace_id, facility_id, id)
        ON DELETE RESTRICT
);
CREATE INDEX ix_telemetry_analysis_observation_reverse
    ON telemetry.analysis_window_observations (resource_scope_id, observation_id, analysis_window_id);
"""


def apply(conn: Any) -> None:
    """Apply the additive PostgreSQL migration exactly once."""
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
    """Verify the migration ledger and required relation set without mutating data."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s",
            (MIGRATION_ID,),
        )
        if not cur.fetchone():
            raise RuntimeError("telemetry_schema_migration_not_applied")
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            """,
            (SCHEMA_NAME,),
        )
        actual = {str(row[0]) for row in cur.fetchall()}
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = ANY(%s)
            """,
            (SCHEMA_NAME, sorted(EXPECTED_COLUMNS)),
        )
        actual_columns: dict[str, set[str]] = {}
        for table_name, column_name in cur.fetchall():
            actual_columns.setdefault(str(table_name), set()).add(str(column_name))
    missing = EXPECTED_TABLES - actual
    if missing:
        raise RuntimeError(f"telemetry_schema_incomplete:{','.join(sorted(missing))}")
    missing_columns = {
        table_name: sorted(expected - actual_columns.get(table_name, set()))
        for table_name, expected in EXPECTED_COLUMNS.items()
        if expected - actual_columns.get(table_name, set())
    }
    if missing_columns:
        detail = ";".join(
            f"{table_name}:{','.join(columns)}"
            for table_name, columns in sorted(missing_columns.items())
        )
        raise RuntimeError(f"telemetry_schema_columns_incomplete:{detail}")
    return {"migration_id": MIGRATION_ID, "schema": SCHEMA_NAME, "tables": tuple(sorted(actual))}


def rollback_empty_schema_for_tests(conn: Any, *, confirmation: str) -> None:
    """Remove this migration only from an empty disposable test schema.

    Production rollback is forward-fix only.  This helper refuses to run when
    any operational table contains data and requires an explicit confirmation,
    making it suitable for migration tests without providing a data-destructive
    downgrade path.
    """
    if confirmation != "DROP_EMPTY_TEST_TELEMETRY_SCHEMA":
        raise ValueError("test_rollback_confirmation_required")
    operational = sorted(EXPECTED_TABLES - {"schema_migrations"})
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = ANY(%s)
            """,
            (SCHEMA_NAME, operational),
        )
        existing = [str(row[0]) for row in cur.fetchall()]
        for table_name in existing:
            cur.execute(f'SELECT EXISTS (SELECT 1 FROM telemetry."{table_name}" LIMIT 1)')
            if cur.fetchone()[0]:
                raise RuntimeError("test_rollback_refused_nonempty_schema")
        cur.execute("DROP SCHEMA telemetry CASCADE")
    conn.commit()
