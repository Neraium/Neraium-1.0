"""Authoritative existing SQLite runtime migrations, invoked only offline."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from app.services.dataset_scope import dataset_scope_from_payload


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def apply(connection: sqlite3.Connection) -> None:
    """Explicit offline migration; retain the existing SQLite ledger and upgrades."""
    connection.execute("BEGIN IMMEDIATE")
    _execute_transactional_script(connection,
        """
        CREATE TABLE IF NOT EXISTS upload_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS upload_queue (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
            attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            locked_at TEXT,
            FOREIGN KEY(job_id) REFERENCES upload_jobs(job_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS evidence_runs (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            source_name TEXT,
            scope_storage_id TEXT,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS operator_feedback_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            category TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            FOREIGN KEY(run_id) REFERENCES evidence_runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS finding_status_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('open', 'acknowledged', 'investigating', 'monitoring', 'resolved', 'dismissed')),
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            FOREIGN KEY(run_id) REFERENCES evidence_runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS finding_cases (
            finding_id TEXT PRIMARY KEY,
            source_kind TEXT NOT NULL CHECK (source_kind IN ('evidence_run', 'live_finding')),
            source_id TEXT NOT NULL,
            source_finding_key TEXT NOT NULL,
            scope_storage_id TEXT,
            dataset_scope_json TEXT CHECK (dataset_scope_json IS NULL OR json_valid(dataset_scope_json)),
            source_snapshot_json TEXT NOT NULL CHECK (json_valid(source_snapshot_json)),
            created_at TEXT NOT NULL,
            UNIQUE (source_kind, source_id, source_finding_key)
        );

        CREATE TABLE IF NOT EXISTS finding_workflow_events (
            event_id TEXT PRIMARY KEY,
            finding_id TEXT NOT NULL,
            version INTEGER NOT NULL CHECK (version > 0),
            event_type TEXT NOT NULL CHECK (event_type IN (
                'workflow_updated', 'feedback_recorded', 'resolution_recorded',
                'legacy_status_imported', 'legacy_feedback_imported',
                'field_report_recorded'
            )),
            recorded_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            idempotency_key TEXT,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            FOREIGN KEY(finding_id) REFERENCES finding_cases(finding_id) ON DELETE RESTRICT,
            UNIQUE (finding_id, version),
            UNIQUE (finding_id, idempotency_key)
        );

        CREATE TABLE IF NOT EXISTS evidence_audit_tag_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
            FOREIGN KEY(run_id) REFERENCES evidence_runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            request_id TEXT,
            actor TEXT,
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT,
            detail_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS latest_payloads (
            key TEXT PRIMARY KEY,
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS data_connections (
            connection_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('offline', 'polling', 'online', 'ready', 'error', 'not_configured')),
            polling_enabled INTEGER NOT NULL DEFAULT 0 CHECK (polling_enabled IN (0, 1)),
            updated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
        );

        CREATE TABLE IF NOT EXISTS auth_users (
            email TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('viewer', 'operator', 'admin')),
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
            deactivated_at TEXT,
            bootstrap_managed INTEGER NOT NULL DEFAULT 0 CHECK (bootstrap_managed IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS auth_sessions (
            session_id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen_at TEXT,
            revoked_at TEXT,
            FOREIGN KEY(email) REFERENCES auth_users(email) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_upload_jobs_updated_at ON upload_jobs(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_upload_jobs_status_updated ON upload_jobs(status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_upload_queue_status_created ON upload_queue(status, created_at ASC);
        CREATE INDEX IF NOT EXISTS idx_upload_queue_updated_at ON upload_queue(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_upload_queue_status_updated ON upload_queue(status, updated_at ASC);
        CREATE INDEX IF NOT EXISTS idx_evidence_runs_created_at ON evidence_runs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_evidence_runs_status_created ON evidence_runs(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_feedback_events_run_time ON operator_feedback_events(run_id, recorded_at DESC);
        CREATE INDEX IF NOT EXISTS idx_finding_status_events_run_time ON finding_status_events(run_id, recorded_at DESC);
        CREATE INDEX IF NOT EXISTS idx_finding_cases_source ON finding_cases(source_kind, source_id, source_finding_key);
        CREATE INDEX IF NOT EXISTS idx_finding_workflow_events_finding_version ON finding_workflow_events(finding_id, version DESC);
        CREATE INDEX IF NOT EXISTS idx_evidence_audit_tags_run_time ON evidence_audit_tag_events(run_id, recorded_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_latest_payloads_updated_at ON latest_payloads(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_data_connections_updated_at ON data_connections(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_data_connections_polling_updated ON data_connections(polling_enabled, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_auth_users_role_active ON auth_users(role, is_active);
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_email ON auth_sessions(email, expires_at DESC);
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_revoked ON auth_sessions(revoked_at, expires_at DESC);
        """
    )
    _apply_runtime_migrations(connection)


RUNTIME_SCHEMA_MIGRATIONS = (
    "001_queue_integrity",
    "002_query_indexes",
    "003_state_constraints",
    "004_append_only_finding_events",
    "005_live_telemetry_ingestion",
    "006_live_analysis_orchestration",
    "007_finding_workflow_sidecar",
    "008_finding_workflow_scope",
    "009_finding_field_reports",
    "010_workspace_evidence_scope",
    "011_workspace_live_analysis_scope",
    "012_upload_queue_phase4_scope",
    "013_internal_health_relevance",
    "014_governance_lifecycle_events",
)


def _table_sql(connection: sqlite3.Connection, table_name: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return str(row["sql"] or "") if row else ""


def _execute_transactional_script(connection: sqlite3.Connection, script: str) -> None:
    """Execute a SQL script without committing the caller's transaction."""
    pending_lines: list[str] = []
    for line in script.splitlines():
        pending_lines.append(line)
        statement = "\n".join(pending_lines).strip()
        if statement and sqlite3.complete_statement(statement):
            connection.execute(statement)
            pending_lines.clear()
    if "\n".join(pending_lines).strip():
        raise ValueError("incomplete_runtime_migration_statement")


def _apply_runtime_migrations(connection: sqlite3.Connection) -> None:
    """Upgrade every supported runtime schema state.

    Supported inputs are an empty database and the unversioned schema shipped
    before the migration ledger. Downgrades are intentionally unsupported.
    Migration 001 rebuilds only the bounded upload queue table so SQLite can add
    a real foreign key and CHECK constraints; orphaned legacy queue rows are
    discarded because they cannot be processed without a matching upload job.
    """
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = {
        str(row["migration_id"])
        for row in connection.execute("SELECT migration_id FROM runtime_schema_migrations").fetchall()
    }

    if "001_queue_integrity" not in applied:
        queue_sql = _table_sql(connection, "upload_queue").lower()
        needs_rebuild = "references upload_jobs" not in queue_sql or "check" not in queue_sql
        if needs_rebuild:
            connection.execute(
                """
                CREATE TABLE upload_queue_migrating (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    locked_at TEXT,
                    FOREIGN KEY(job_id) REFERENCES upload_jobs(job_id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                INSERT INTO upload_queue_migrating
                    (job_id, status, attempts, last_error, created_at, updated_at, locked_at)
                SELECT q.job_id,
                       CASE lower(q.status) WHEN 'queued' THEN 'pending' ELSE lower(q.status) END,
                       CASE WHEN q.attempts < 0 THEN 0 ELSE q.attempts END,
                       q.last_error, q.created_at, q.updated_at, q.locked_at
                FROM upload_queue AS q
                INNER JOIN upload_jobs AS j ON j.job_id = q.job_id
                WHERE lower(q.status) IN ('queued', 'pending', 'processing', 'completed', 'failed')
                """
            )
            connection.execute("DROP TABLE upload_queue")
            connection.execute("ALTER TABLE upload_queue_migrating RENAME TO upload_queue")
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("001_queue_integrity", now_iso()),
        )

    if "002_query_indexes" not in applied:
        # Keep only the newest legacy active session before enforcing the
        # cross-process single-session invariant.
        migration_time = now_iso()
        connection.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = ?
            WHERE revoked_at IS NULL
              AND session_id NOT IN (
                  SELECT session_id FROM (
                      SELECT session_id,
                             ROW_NUMBER() OVER (
                                 PARTITION BY email ORDER BY created_at DESC, session_id DESC
                             ) AS position
                      FROM auth_sessions
                      WHERE revoked_at IS NULL
                  ) ranked
                  WHERE position = 1
              )
            """,
            (migration_time,),
        )
        for statement in (
            "CREATE INDEX IF NOT EXISTS idx_upload_queue_status_created ON upload_queue(status, created_at ASC)",
            "CREATE INDEX IF NOT EXISTS idx_upload_queue_status_updated ON upload_queue(status, updated_at ASC)",
            "CREATE INDEX IF NOT EXISTS idx_evidence_runs_status_created ON evidence_runs(status, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_data_connections_polling_updated ON data_connections(polling_enabled, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_email ON auth_sessions(email, expires_at DESC)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_sessions_active_email ON auth_sessions(email) WHERE revoked_at IS NULL",
        ):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("002_query_indexes", now_iso()),
        )

    if "003_state_constraints" not in applied:
        connection.execute(
            "UPDATE data_connections SET status = 'offline' "
            "WHERE status NOT IN ('offline', 'polling', 'online', 'ready', 'error', 'not_configured')"
        )
        connection.execute(
            "UPDATE auth_users SET role = 'operator' WHERE role NOT IN ('viewer', 'operator', 'admin')"
        )
        for statement in (
            """
            CREATE TRIGGER IF NOT EXISTS trg_data_connections_state_insert
            BEFORE INSERT ON data_connections
            WHEN NEW.status NOT IN ('offline', 'polling', 'online', 'ready', 'error', 'not_configured')
              OR NEW.polling_enabled NOT IN (0, 1)
            BEGIN SELECT RAISE(ABORT, 'data_connection_state'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_data_connections_state_update
            BEFORE UPDATE OF status, polling_enabled ON data_connections
            WHEN NEW.status NOT IN ('offline', 'polling', 'online', 'ready', 'error', 'not_configured')
              OR NEW.polling_enabled NOT IN (0, 1)
            BEGIN SELECT RAISE(ABORT, 'data_connection_state'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_runtime_auth_role_insert
            BEFORE INSERT ON auth_users
            WHEN NEW.role NOT IN ('viewer', 'operator', 'admin')
            BEGIN SELECT RAISE(ABORT, 'auth_role'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_runtime_auth_role_update
            BEFORE UPDATE OF role ON auth_users
            WHEN NEW.role NOT IN ('viewer', 'operator', 'admin')
            BEGIN SELECT RAISE(ABORT, 'auth_role'); END
            """,
        ):
            connection.execute(statement)
        for table_name, column_name in (
            ("upload_jobs", "payload_json"),
            ("evidence_runs", "payload_json"),
            ("audit_events", "detail_json"),
            ("latest_payloads", "payload_json"),
            ("data_connections", "payload_json"),
        ):
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS trg_{table_name}_json_insert
                BEFORE INSERT ON {table_name}
                WHEN NOT json_valid(NEW.{column_name})
                BEGIN SELECT RAISE(ABORT, 'invalid_json'); END
                """
            )
            connection.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS trg_{table_name}_json_update
                BEFORE UPDATE OF {column_name} ON {table_name}
                WHEN NOT json_valid(NEW.{column_name})
                BEGIN SELECT RAISE(ABORT, 'invalid_json'); END
                """
            )
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("003_state_constraints", now_iso()),
        )

    if "004_append_only_finding_events" not in applied:
        for statement in (
            "CREATE INDEX IF NOT EXISTS idx_feedback_events_run_time ON operator_feedback_events(run_id, recorded_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_finding_status_events_run_time ON finding_status_events(run_id, recorded_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_evidence_audit_tags_run_time ON evidence_audit_tag_events(run_id, recorded_at DESC)",
        ):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("004_append_only_finding_events", now_iso()),
        )

    if "005_live_telemetry_ingestion" not in applied:
        for statement in (
            """
            CREATE TABLE IF NOT EXISTS telemetry_ingestion_batches (
                batch_id TEXT PRIMARY KEY,
                system_id TEXT NOT NULL,
                source TEXT NOT NULL,
                received_at TEXT NOT NULL,
                completed_at TEXT,
                result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json))
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS telemetry_signal_mappings (
                mapping_id TEXT PRIMARY KEY,
                system_id TEXT NOT NULL,
                source_tag TEXT NOT NULL,
                canonical_signal TEXT NOT NULL,
                unit TEXT,
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (system_id, source_tag)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS normalized_telemetry (
                telemetry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                system_id TEXT NOT NULL,
                canonical_signal TEXT NOT NULL,
                telemetry_timestamp TEXT NOT NULL,
                value REAL NOT NULL CHECK (
                    value = value
                    AND value <= 1.7976931348623157e308
                    AND value >= -1.7976931348623157e308
                ),
                source TEXT NOT NULL,
                source_tag TEXT NOT NULL,
                quality_status TEXT NOT NULL CHECK (quality_status IN ('good', 'out_of_order')),
                ingested_at TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                FOREIGN KEY(batch_id) REFERENCES telemetry_ingestion_batches(batch_id),
                UNIQUE (system_id, canonical_signal, telemetry_timestamp, source)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS rejected_telemetry (
                rejection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                system_id TEXT NOT NULL,
                source TEXT NOT NULL,
                source_tag TEXT,
                telemetry_timestamp TEXT,
                submitted_value_json TEXT CHECK (
                    submitted_value_json IS NULL OR json_valid(submitted_value_json)
                ),
                rejection_reason TEXT NOT NULL CHECK (rejection_reason IN (
                    'missing_timestamp',
                    'invalid_timestamp',
                    'future_timestamp',
                    'non_numeric_value',
                    'nan_value',
                    'infinite_value',
                    'unmapped_signal',
                    'duplicate_record',
                    'out_of_order_record'
                )),
                ingested_at TEXT NOT NULL,
                FOREIGN KEY(batch_id) REFERENCES telemetry_ingestion_batches(batch_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS telemetry_ingestion_health (
                system_id TEXT NOT NULL,
                source TEXT NOT NULL,
                last_successful_ingestion_at TEXT,
                last_telemetry_timestamp TEXT,
                accepted_count INTEGER NOT NULL DEFAULT 0 CHECK (accepted_count >= 0),
                rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
                latest_error_or_warning TEXT,
                status TEXT NOT NULL CHECK (status IN ('healthy', 'delayed', 'error', 'never_received')),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (system_id, source)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_telemetry_mappings_system_enabled
                ON telemetry_signal_mappings (system_id, enabled, source_tag)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_telemetry_mappings_system_canonical
                ON telemetry_signal_mappings (system_id, canonical_signal)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_normalized_telemetry_system_time
                ON normalized_telemetry (system_id, telemetry_timestamp DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_normalized_telemetry_system_signal_time
                ON normalized_telemetry (system_id, canonical_signal, telemetry_timestamp DESC)
            """,
            "CREATE INDEX IF NOT EXISTS idx_normalized_telemetry_batch ON normalized_telemetry (batch_id)",
            "CREATE INDEX IF NOT EXISTS idx_rejected_telemetry_batch ON rejected_telemetry (batch_id, rejection_id)",
            """
            CREATE INDEX IF NOT EXISTS idx_rejected_telemetry_system_time
                ON rejected_telemetry (system_id, ingested_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_telemetry_health_updated
                ON telemetry_ingestion_health (updated_at DESC)
            """,
        ):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("005_live_telemetry_ingestion", now_iso()),
        )

    if "006_live_analysis_orchestration" not in applied:
        for statement in (
            """
            CREATE TABLE IF NOT EXISTS live_analysis_configurations (
                system_id TEXT PRIMARY KEY,
                scope_storage_id TEXT,
                enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
                approved_baseline_id TEXT,
                analysis_interval_seconds INTEGER NOT NULL DEFAULT 300 CHECK (analysis_interval_seconds > 0),
                comparison_window_minutes INTEGER NOT NULL DEFAULT 60 CHECK (comparison_window_minutes > 0),
                minimum_coverage_percent REAL NOT NULL DEFAULT 80 CHECK (
                    minimum_coverage_percent >= 0 AND minimum_coverage_percent <= 100
                ),
                allowed_lateness_minutes INTEGER NOT NULL DEFAULT 5 CHECK (allowed_lateness_minutes >= 0),
                last_analysis_started_at TEXT,
                last_analysis_completed_at TEXT,
                next_analysis_at TEXT,
                current_status TEXT NOT NULL DEFAULT 'disabled' CHECK (
                    current_status IN ('enabled', 'disabled', 'running', 'waiting', 'error')
                ),
                latest_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS live_analysis_runs (
                run_id TEXT PRIMARY KEY,
                scope_storage_id TEXT,
                system_id TEXT NOT NULL,
                baseline_reference TEXT NOT NULL DEFAULT '',
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'skipped', 'failed')),
                started_at TEXT,
                completed_at TEXT,
                rows_analyzed INTEGER NOT NULL DEFAULT 0 CHECK (rows_analyzed >= 0),
                signals_analyzed INTEGER NOT NULL DEFAULT 0 CHECK (signals_analyzed >= 0),
                coverage REAL NOT NULL DEFAULT 0 CHECK (coverage >= 0 AND coverage <= 100),
                skipped_reason TEXT CHECK (skipped_reason IS NULL OR skipped_reason IN (
                    'disabled', 'missing_baseline', 'insufficient_coverage',
                    'insufficient_signals', 'telemetry_delayed', 'telemetry_unavailable',
                    'duplicate_window', 'analysis_already_running'
                )),
                error_summary TEXT,
                analytics_result_reference TEXT,
                analytics_result_json TEXT CHECK (
                    analytics_result_json IS NULL OR json_valid(analytics_result_json)
                ),
                created_findings_count INTEGER NOT NULL DEFAULT 0 CHECK (created_findings_count >= 0),
                updated_findings_count INTEGER NOT NULL DEFAULT 0 CHECK (updated_findings_count >= 0),
                resolved_findings_count INTEGER NOT NULL DEFAULT 0 CHECK (resolved_findings_count >= 0),
                created_at TEXT NOT NULL,
                UNIQUE (system_id, baseline_reference, window_start, window_end)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS live_findings (
                finding_id TEXT PRIMARY KEY,
                scope_storage_id TEXT,
                deduplication_key TEXT NOT NULL UNIQUE,
                system_id TEXT NOT NULL,
                relationship_identity TEXT NOT NULL,
                finding_classification_json TEXT NOT NULL CHECK (json_valid(finding_classification_json)),
                first_detected_at TEXT NOT NULL,
                last_observed_at TEXT NOT NULL,
                opened_at TEXT,
                resolved_at TEXT,
                current_state TEXT NOT NULL CHECK (current_state IN ('observing', 'open', 'resolved')),
                persistence_state_json TEXT NOT NULL CHECK (json_valid(persistence_state_json)),
                severity_score REAL,
                latest_evidence_json TEXT NOT NULL CHECK (json_valid(latest_evidence_json)),
                source_live_analysis_run_id TEXT NOT NULL,
                baseline_reference TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(source_live_analysis_run_id) REFERENCES live_analysis_runs(run_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS live_analysis_health (
                system_id TEXT PRIMARY KEY,
                scope_storage_id TEXT,
                last_attempted_run_at TEXT,
                last_completed_run_at TEXT,
                last_successful_run_at TEXT,
                current_status TEXT NOT NULL CHECK (current_status IN (
                    'healthy', 'waiting_for_data', 'missing_baseline', 'delayed',
                    'running', 'error', 'disabled', 'never_run'
                )),
                current_window_coverage REAL NOT NULL DEFAULT 0 CHECK (
                    current_window_coverage >= 0 AND current_window_coverage <= 100
                ),
                latest_skipped_reason TEXT,
                consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
                latest_error TEXT,
                next_scheduled_run TEXT,
                updated_at TEXT NOT NULL
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_live_analysis_config_due
                   ON live_analysis_configurations (enabled, next_analysis_at, system_id)""",
            """CREATE INDEX IF NOT EXISTS idx_live_analysis_runs_system_created
                   ON live_analysis_runs (system_id, created_at DESC)""",
            """CREATE INDEX IF NOT EXISTS idx_live_analysis_runs_window
                   ON live_analysis_runs (system_id, window_end DESC)""",
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_live_analysis_one_running
                   ON live_analysis_runs (scope_storage_id, system_id)
                   WHERE status = 'running' AND scope_storage_id IS NOT NULL""",
            """CREATE INDEX IF NOT EXISTS idx_live_findings_system_state
                   ON live_findings (system_id, current_state, last_observed_at DESC)""",
            """CREATE INDEX IF NOT EXISTS idx_live_findings_baseline_relationship
                   ON live_findings (baseline_reference, relationship_identity)""",
            """CREATE INDEX IF NOT EXISTS idx_live_analysis_health_status
                   ON live_analysis_health (current_status, updated_at DESC)""",
        ):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("006_live_analysis_orchestration", now_iso()),
        )

    if "007_finding_workflow_sidecar" not in applied:
        for statement in (
            """
            CREATE TABLE IF NOT EXISTS finding_cases (
                finding_id TEXT PRIMARY KEY,
                source_kind TEXT NOT NULL CHECK (source_kind IN ('evidence_run', 'live_finding')),
                source_id TEXT NOT NULL,
                source_finding_key TEXT NOT NULL,
                scope_storage_id TEXT,
                dataset_scope_json TEXT CHECK (dataset_scope_json IS NULL OR json_valid(dataset_scope_json)),
                source_snapshot_json TEXT NOT NULL CHECK (json_valid(source_snapshot_json)),
                created_at TEXT NOT NULL,
                UNIQUE (source_kind, source_id, source_finding_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS finding_workflow_events (
                event_id TEXT PRIMARY KEY,
                finding_id TEXT NOT NULL,
                version INTEGER NOT NULL CHECK (version > 0),
                event_type TEXT NOT NULL CHECK (event_type IN (
                    'workflow_updated', 'feedback_recorded', 'resolution_recorded',
                    'legacy_status_imported', 'legacy_feedback_imported',
                    'field_report_recorded'
                )),
                recorded_at TEXT NOT NULL,
                actor TEXT NOT NULL,
                idempotency_key TEXT,
                payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
                FOREIGN KEY(finding_id) REFERENCES finding_cases(finding_id) ON DELETE RESTRICT,
                UNIQUE (finding_id, version),
                UNIQUE (finding_id, idempotency_key)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_finding_cases_source ON finding_cases(source_kind, source_id, source_finding_key)",
            "CREATE INDEX IF NOT EXISTS idx_finding_cases_scope_created ON finding_cases(scope_storage_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_finding_workflow_events_finding_version ON finding_workflow_events(finding_id, version DESC)",
            """
            CREATE TRIGGER IF NOT EXISTS trg_finding_cases_source_immutable
            BEFORE UPDATE OF source_kind, source_id, source_finding_key, scope_storage_id,
                             dataset_scope_json, source_snapshot_json
            ON finding_cases
            BEGIN SELECT RAISE(ABORT, 'finding_case_source_immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_finding_cases_no_delete
            BEFORE DELETE ON finding_cases
            BEGIN SELECT RAISE(ABORT, 'finding_cases_preserve_identity'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_finding_workflow_events_no_update
            BEFORE UPDATE ON finding_workflow_events
            BEGIN SELECT RAISE(ABORT, 'finding_workflow_events_append_only'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_finding_workflow_events_no_delete
            BEFORE DELETE ON finding_workflow_events
            BEGIN SELECT RAISE(ABORT, 'finding_workflow_events_append_only'); END
            """,
        ):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("007_finding_workflow_sidecar", now_iso()),
        )

    if "008_finding_workflow_scope" not in applied:
        finding_case_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(finding_cases)").fetchall()
        }
        if "scope_storage_id" not in finding_case_columns:
            connection.execute("ALTER TABLE finding_cases ADD COLUMN scope_storage_id TEXT")
        if "dataset_scope_json" not in finding_case_columns:
            connection.execute(
                "ALTER TABLE finding_cases ADD COLUMN dataset_scope_json TEXT "
                "CHECK (dataset_scope_json IS NULL OR json_valid(dataset_scope_json))"
            )
        for statement in (
            "CREATE INDEX IF NOT EXISTS idx_finding_cases_scope_created ON finding_cases(scope_storage_id, created_at DESC)",
            """
            CREATE TRIGGER IF NOT EXISTS trg_finding_cases_source_immutable
            BEFORE UPDATE OF source_kind, source_id, source_finding_key, scope_storage_id,
                             dataset_scope_json, source_snapshot_json
            ON finding_cases
            BEGIN SELECT RAISE(ABORT, 'finding_case_source_immutable'); END
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_finding_cases_no_delete
            BEFORE DELETE ON finding_cases
            BEGIN SELECT RAISE(ABORT, 'finding_cases_preserve_identity'); END
            """,
        ):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("008_finding_workflow_scope", now_iso()),
        )

    if "009_finding_field_reports" not in applied or "014_governance_lifecycle_events" not in applied:
        table_sql = _table_sql(connection, "finding_workflow_events")
        if "governance_lifecycle_recorded" not in table_sql:
            # SQLite cannot alter CHECK constraints. Rebuild this append-only
            # table transactionally while preserving every event and uniqueness
            # constraint, then restore its immutability triggers.
            connection.execute("DROP TRIGGER IF EXISTS trg_finding_workflow_events_no_update")
            connection.execute("DROP TRIGGER IF EXISTS trg_finding_workflow_events_no_delete")
            connection.execute(
                "ALTER TABLE finding_workflow_events RENAME TO finding_workflow_events_legacy"
            )
            connection.execute(
                """
                CREATE TABLE finding_workflow_events (
                    event_id TEXT PRIMARY KEY,
                    finding_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    event_type TEXT NOT NULL CHECK (event_type IN (
                        'workflow_updated', 'feedback_recorded', 'resolution_recorded',
                        'legacy_status_imported', 'legacy_feedback_imported',
                        'field_report_recorded', 'governance_lifecycle_recorded'
                    )),
                    recorded_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    idempotency_key TEXT,
                    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
                    FOREIGN KEY(finding_id) REFERENCES finding_cases(finding_id) ON DELETE RESTRICT,
                    UNIQUE (finding_id, version),
                    UNIQUE (finding_id, idempotency_key)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO finding_workflow_events (
                    event_id, finding_id, version, event_type, recorded_at, actor,
                    idempotency_key, payload_json
                )
                SELECT event_id, finding_id, version, event_type, recorded_at, actor,
                       idempotency_key, payload_json
                FROM finding_workflow_events_legacy
                """
            )
            connection.execute("DROP TABLE finding_workflow_events_legacy")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_finding_workflow_events_finding_version "
                "ON finding_workflow_events(finding_id, version DESC)"
            )
            connection.execute(
                """
                CREATE TRIGGER trg_finding_workflow_events_no_update
                BEFORE UPDATE ON finding_workflow_events
                BEGIN SELECT RAISE(ABORT, 'finding_workflow_events_append_only'); END
                """
            )
            connection.execute(
                """
                CREATE TRIGGER trg_finding_workflow_events_no_delete
                BEFORE DELETE ON finding_workflow_events
                BEGIN SELECT RAISE(ABORT, 'finding_workflow_events_append_only'); END
                """
            )
        for migration_id in ("009_finding_field_reports", "014_governance_lifecycle_events"):
            if migration_id not in applied:
                connection.execute(
                    "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
                    (migration_id, now_iso()),
                )

    if "010_workspace_evidence_scope" not in applied:
        evidence_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(evidence_runs)").fetchall()
        }
        if "scope_storage_id" not in evidence_columns:
            connection.execute("ALTER TABLE evidence_runs ADD COLUMN scope_storage_id TEXT")
        # Backfill only rows that carry an authoritative full DatasetScope. A
        # missing or malformed scope remains NULL and therefore fail-closed.
        rows = connection.execute(
            "SELECT run_id, payload_json FROM evidence_runs WHERE scope_storage_id IS NULL"
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            scope = dataset_scope_from_payload(payload if isinstance(payload, dict) else None)
            if scope is not None:
                connection.execute(
                    "UPDATE evidence_runs SET scope_storage_id = ? WHERE run_id = ?",
                    (scope.storage_id, str(row["run_id"])),
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_evidence_runs_scope_created "
            "ON evidence_runs(scope_storage_id, created_at DESC, run_id DESC)"
        )
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("010_workspace_evidence_scope", now_iso()),
        )

    if "011_workspace_live_analysis_scope" not in applied:
        # Legacy live-analysis rows do not carry enough information to infer an
        # owner. Add nullable keys without backfilling; exact-scope queries keep
        # those ambiguous source rows inaccessible until an audited adoption.
        for table_name in (
            "live_analysis_configurations",
            "live_analysis_runs",
            "live_findings",
            "live_analysis_health",
        ):
            columns = {
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
            if "scope_storage_id" not in columns:
                connection.execute(f"ALTER TABLE {table_name} ADD COLUMN scope_storage_id TEXT")
        # Rebuild the tables so normal facility-local identifiers can repeat in
        # unrelated scopes. UUID run/finding IDs remain stable; all natural-key
        # uniqueness and the run->finding relationship include exact scope.
        connection.execute("PRAGMA defer_foreign_keys = ON")
        _execute_transactional_script(
            connection,
            """
            CREATE TABLE live_analysis_configurations_scoped (
                system_id TEXT NOT NULL,
                scope_storage_id TEXT,
                enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
                approved_baseline_id TEXT,
                analysis_interval_seconds INTEGER NOT NULL DEFAULT 300 CHECK (analysis_interval_seconds > 0),
                comparison_window_minutes INTEGER NOT NULL DEFAULT 60 CHECK (comparison_window_minutes > 0),
                minimum_coverage_percent REAL NOT NULL DEFAULT 80 CHECK (
                    minimum_coverage_percent >= 0 AND minimum_coverage_percent <= 100
                ),
                allowed_lateness_minutes INTEGER NOT NULL DEFAULT 5 CHECK (allowed_lateness_minutes >= 0),
                last_analysis_started_at TEXT,
                last_analysis_completed_at TEXT,
                next_analysis_at TEXT,
                current_status TEXT NOT NULL DEFAULT 'disabled' CHECK (
                    current_status IN ('enabled', 'disabled', 'running', 'waiting', 'error')
                ),
                latest_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(scope_storage_id, system_id)
            );

            CREATE TABLE live_analysis_runs_scoped (
                run_id TEXT PRIMARY KEY,
                scope_storage_id TEXT,
                system_id TEXT NOT NULL,
                baseline_reference TEXT NOT NULL DEFAULT '',
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'skipped', 'failed')),
                started_at TEXT,
                completed_at TEXT,
                rows_analyzed INTEGER NOT NULL DEFAULT 0 CHECK (rows_analyzed >= 0),
                signals_analyzed INTEGER NOT NULL DEFAULT 0 CHECK (signals_analyzed >= 0),
                coverage REAL NOT NULL DEFAULT 0 CHECK (coverage >= 0 AND coverage <= 100),
                skipped_reason TEXT CHECK (skipped_reason IS NULL OR skipped_reason IN (
                    'disabled', 'missing_baseline', 'insufficient_coverage',
                    'insufficient_signals', 'telemetry_delayed', 'telemetry_unavailable',
                    'duplicate_window', 'analysis_already_running'
                )),
                error_summary TEXT,
                analytics_result_reference TEXT,
                analytics_result_json TEXT CHECK (
                    analytics_result_json IS NULL OR json_valid(analytics_result_json)
                ),
                created_findings_count INTEGER NOT NULL DEFAULT 0 CHECK (created_findings_count >= 0),
                updated_findings_count INTEGER NOT NULL DEFAULT 0 CHECK (updated_findings_count >= 0),
                resolved_findings_count INTEGER NOT NULL DEFAULT 0 CHECK (resolved_findings_count >= 0),
                created_at TEXT NOT NULL,
                UNIQUE(scope_storage_id, run_id),
                UNIQUE(scope_storage_id, system_id, baseline_reference, window_start, window_end)
            );

            CREATE TABLE live_findings_scoped (
                finding_id TEXT PRIMARY KEY,
                scope_storage_id TEXT,
                deduplication_key TEXT NOT NULL,
                system_id TEXT NOT NULL,
                relationship_identity TEXT NOT NULL,
                finding_classification_json TEXT NOT NULL CHECK (json_valid(finding_classification_json)),
                first_detected_at TEXT NOT NULL,
                last_observed_at TEXT NOT NULL,
                opened_at TEXT,
                resolved_at TEXT,
                current_state TEXT NOT NULL CHECK (current_state IN ('observing', 'open', 'resolved')),
                persistence_state_json TEXT NOT NULL CHECK (json_valid(persistence_state_json)),
                severity_score REAL,
                latest_evidence_json TEXT NOT NULL CHECK (json_valid(latest_evidence_json)),
                source_live_analysis_run_id TEXT NOT NULL,
                baseline_reference TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(scope_storage_id, deduplication_key),
                FOREIGN KEY(scope_storage_id, source_live_analysis_run_id)
                    REFERENCES live_analysis_runs_scoped(scope_storage_id, run_id)
            );

            CREATE TABLE live_analysis_health_scoped (
                system_id TEXT NOT NULL,
                scope_storage_id TEXT,
                last_attempted_run_at TEXT,
                last_completed_run_at TEXT,
                last_successful_run_at TEXT,
                current_status TEXT NOT NULL CHECK (current_status IN (
                    'healthy', 'waiting_for_data', 'missing_baseline', 'delayed',
                    'running', 'error', 'disabled', 'never_run'
                )),
                current_window_coverage REAL NOT NULL DEFAULT 0 CHECK (
                    current_window_coverage >= 0 AND current_window_coverage <= 100
                ),
                latest_skipped_reason TEXT,
                consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
                latest_error TEXT,
                next_scheduled_run TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(scope_storage_id, system_id)
            );

            INSERT INTO live_analysis_configurations_scoped (
                system_id, scope_storage_id, enabled, approved_baseline_id,
                analysis_interval_seconds, comparison_window_minutes,
                minimum_coverage_percent, allowed_lateness_minutes,
                last_analysis_started_at, last_analysis_completed_at,
                next_analysis_at, current_status, latest_error, created_at, updated_at
            ) SELECT system_id, scope_storage_id, enabled, approved_baseline_id,
                     analysis_interval_seconds, comparison_window_minutes,
                     minimum_coverage_percent, allowed_lateness_minutes,
                     last_analysis_started_at, last_analysis_completed_at,
                     next_analysis_at, current_status, latest_error, created_at, updated_at
              FROM live_analysis_configurations;
            INSERT INTO live_analysis_runs_scoped (
                run_id, scope_storage_id, system_id, baseline_reference,
                window_start, window_end, status, started_at, completed_at,
                rows_analyzed, signals_analyzed, coverage, skipped_reason,
                error_summary, analytics_result_reference, analytics_result_json,
                created_findings_count, updated_findings_count,
                resolved_findings_count, created_at
            ) SELECT run_id, scope_storage_id, system_id, baseline_reference,
                     window_start, window_end, status, started_at, completed_at,
                     rows_analyzed, signals_analyzed, coverage, skipped_reason,
                     error_summary, analytics_result_reference, analytics_result_json,
                     created_findings_count, updated_findings_count,
                     resolved_findings_count, created_at
              FROM live_analysis_runs;
            INSERT INTO live_findings_scoped (
                finding_id, scope_storage_id, deduplication_key, system_id,
                relationship_identity, finding_classification_json,
                first_detected_at, last_observed_at, opened_at, resolved_at,
                current_state, persistence_state_json, severity_score,
                latest_evidence_json, source_live_analysis_run_id,
                baseline_reference, created_at, updated_at
            ) SELECT finding_id, scope_storage_id, deduplication_key, system_id,
                     relationship_identity, finding_classification_json,
                     first_detected_at, last_observed_at, opened_at, resolved_at,
                     current_state, persistence_state_json, severity_score,
                     latest_evidence_json, source_live_analysis_run_id,
                     baseline_reference, created_at, updated_at
              FROM live_findings;
            INSERT INTO live_analysis_health_scoped (
                system_id, scope_storage_id, last_attempted_run_at,
                last_completed_run_at, last_successful_run_at, current_status,
                current_window_coverage, latest_skipped_reason,
                consecutive_failures, latest_error, next_scheduled_run, updated_at
            ) SELECT system_id, scope_storage_id, last_attempted_run_at,
                     last_completed_run_at, last_successful_run_at, current_status,
                     current_window_coverage, latest_skipped_reason,
                     consecutive_failures, latest_error, next_scheduled_run, updated_at
              FROM live_analysis_health;

            DROP TABLE live_findings;
            DROP TABLE live_analysis_runs;
            DROP TABLE live_analysis_configurations;
            DROP TABLE live_analysis_health;
            ALTER TABLE live_analysis_configurations_scoped RENAME TO live_analysis_configurations;
            ALTER TABLE live_analysis_runs_scoped RENAME TO live_analysis_runs;
            ALTER TABLE live_findings_scoped RENAME TO live_findings;
            ALTER TABLE live_analysis_health_scoped RENAME TO live_analysis_health;

            CREATE INDEX idx_live_config_scope_due
                ON live_analysis_configurations(scope_storage_id, enabled, next_analysis_at, system_id);
            CREATE INDEX idx_live_runs_scope_created
                ON live_analysis_runs(scope_storage_id, created_at DESC, run_id DESC);
            CREATE INDEX idx_live_analysis_runs_system_created
                ON live_analysis_runs(scope_storage_id, system_id, created_at DESC);
            CREATE INDEX idx_live_analysis_runs_window
                ON live_analysis_runs(scope_storage_id, system_id, window_end DESC);
            CREATE UNIQUE INDEX idx_live_analysis_one_running
                ON live_analysis_runs(scope_storage_id, system_id)
                WHERE status = 'running' AND scope_storage_id IS NOT NULL;
            CREATE INDEX idx_live_findings_scope_observed
                ON live_findings(scope_storage_id, last_observed_at DESC, finding_id DESC);
            CREATE INDEX idx_live_findings_system_state
                ON live_findings(scope_storage_id, system_id, current_state, last_observed_at DESC);
            CREATE INDEX idx_live_findings_baseline_relationship
                ON live_findings(scope_storage_id, baseline_reference, relationship_identity);
            CREATE INDEX idx_live_health_scope_system
                ON live_analysis_health(scope_storage_id, system_id);
            CREATE INDEX idx_live_analysis_health_status
                ON live_analysis_health(scope_storage_id, current_status, updated_at DESC);
            """
        )
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("011_workspace_live_analysis_scope", now_iso()),
        )

    if "012_upload_queue_phase4_scope" not in applied:
        # Routing is separate from mutable job payloads and from the bounded
        # queue lifecycle columns used by older operators. Legacy queue rows
        # intentionally have no matching route and therefore fail closed.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS upload_queue_routing (
                job_id TEXT PRIMARY KEY,
                routing_json TEXT NOT NULL CHECK (json_valid(routing_json)),
                created_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES upload_queue(job_id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("012_upload_queue_phase4_scope", now_iso()),
        )

    if "013_internal_health_relevance" not in applied:
        # Health Relevance is an isolated, internal-only, append-only learning
        # sidecar. This migration is deliberately additive: it creates no
        # production-table columns, performs no backfill, and establishes no
        # write path back into findings, evidence ordering, SII, or behavioral
        # reference evolution.
        _execute_transactional_script(
            connection,
            """
            CREATE TABLE validated_outcomes (
                outcome_revision_id TEXT PRIMARY KEY,
                outcome_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK (revision > 0),
                supersedes_revision_id TEXT,
                scope_storage_id TEXT NOT NULL CHECK (length(trim(scope_storage_id)) > 0),
                tenant_id TEXT NOT NULL CHECK (length(trim(tenant_id)) > 0),
                facility_id TEXT NOT NULL CHECK (length(trim(facility_id)) > 0),
                system_id TEXT NOT NULL CHECK (length(trim(system_id)) > 0),
                asset_equipment_id TEXT,
                outcome_schema_version TEXT NOT NULL,
                outcome_type TEXT NOT NULL CHECK (outcome_type IN (
                    'confirmed_maintenance_event', 'inspection_result',
                    'confirmed_fault', 'confirmed_degraded_condition', 'repair',
                    'component_replacement', 'operator_confirmed_explanation',
                    'return_toward_expected_behavior',
                    'expected_no_fault_confirmation', 'false_positive_not_useful',
                    'stable_operation_observation'
                )),
                outcome_family TEXT NOT NULL CHECK (outcome_family IN (
                    'degradation_or_fault', 'inspection_confirmation',
                    'maintenance_or_intervention', 'repair_or_replacement',
                    'recovery', 'expected_or_no_fault',
                    'not_useful_or_false_positive', 'validated_explanation'
                )),
                health_disposition TEXT NOT NULL CHECK (health_disposition IN (
                    'degraded', 'fault_confirmed', 'expected_behavior', 'no_fault',
                    'not_useful', 'explained', 'intervention_recorded',
                    'recovery_observed', 'unrelated_maintenance',
                    'no_observed_behavior_change', 'stable_observation',
                    'indeterminate'
                )),
                validation_status TEXT NOT NULL CHECK (validation_status IN (
                    'pending', 'validated', 'rejected', 'retracted', 'superseded'
                )),
                occurred_start_at TEXT NOT NULL,
                occurred_end_at TEXT NOT NULL,
                windows_json TEXT CHECK (
                    windows_json IS NULL OR (
                        json_valid(windows_json) AND json_type(windows_json) = 'object'
                    )
                ),
                source_category TEXT NOT NULL,
                source_system TEXT,
                source_record_id TEXT,
                source_record_version TEXT,
                source_recorded_at TEXT,
                source_identity_hash TEXT,
                reported_by TEXT NOT NULL,
                reported_at TEXT NOT NULL,
                validated_by TEXT,
                validated_at TEXT,
                validation_basis_json TEXT NOT NULL CHECK (
                    json_valid(validation_basis_json)
                    AND json_type(validation_basis_json) = 'object'
                ),
                provenance_categories_json TEXT NOT NULL CHECK (
                    json_valid(provenance_categories_json)
                    AND json_type(provenance_categories_json) = 'array'
                ),
                authority_tier TEXT NOT NULL CHECK (authority_tier IN ('A', 'B', 'C', 'D')),
                reliability_class TEXT NOT NULL,
                reliability_basis_json TEXT NOT NULL CHECK (
                    json_valid(reliability_basis_json)
                    AND json_type(reliability_basis_json) = 'object'
                ),
                canonical_incident_key TEXT,
                dedup_status TEXT NOT NULL CHECK (dedup_status IN (
                    'canonical', 'confirmed_distinct', 'possible_duplicate',
                    'confirmed_duplicate', 'unadjudicated'
                )),
                possible_duplicate_of_json TEXT NOT NULL DEFAULT '[]' CHECK (
                    json_valid(possible_duplicate_of_json)
                    AND json_type(possible_duplicate_of_json) = 'array'
                ),
                dedup_basis_json TEXT NOT NULL CHECK (
                    json_valid(dedup_basis_json)
                    AND json_type(dedup_basis_json) = 'object'
                ),
                observation_protocol_json TEXT CHECK (
                    observation_protocol_json IS NULL OR (
                        json_valid(observation_protocol_json)
                        AND json_type(observation_protocol_json) = 'object'
                    )
                ),
                structured_metadata_json TEXT NOT NULL CHECK (
                    json_valid(structured_metadata_json)
                    AND json_type(structured_metadata_json) = 'object'
                ),
                metadata_schema_version TEXT NOT NULL,
                actor TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                idempotency_key TEXT,
                request_fingerprint TEXT,
                UNIQUE(scope_storage_id, tenant_id, facility_id, system_id, outcome_id, revision),
                UNIQUE(scope_storage_id, tenant_id, facility_id, system_id, outcome_id, outcome_revision_id),
                FOREIGN KEY(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    outcome_id, supersedes_revision_id
                ) REFERENCES validated_outcomes(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    outcome_id, outcome_revision_id
                ) ON DELETE RESTRICT,
                CHECK (occurred_end_at >= occurred_start_at),
                CHECK (
                    (revision = 1 AND supersedes_revision_id IS NULL)
                    OR (revision > 1 AND supersedes_revision_id IS NOT NULL)
                ),
                CHECK (
                    (validation_status = 'pending' AND validated_by IS NULL AND validated_at IS NULL)
                    OR (validation_status <> 'pending' AND validated_by IS NOT NULL AND validated_at IS NOT NULL)
                ),
                CHECK (
                    outcome_type <> 'stable_operation_observation'
                    OR observation_protocol_json IS NOT NULL
                ),
                CHECK (idempotency_key IS NULL OR request_fingerprint IS NOT NULL)
            );

            CREATE TABLE validated_outcome_links (
                link_revision_id TEXT PRIMARY KEY,
                link_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK (revision > 0),
                supersedes_revision_id TEXT,
                outcome_id TEXT NOT NULL,
                outcome_revision_id TEXT NOT NULL,
                scope_storage_id TEXT NOT NULL CHECK (length(trim(scope_storage_id)) > 0),
                tenant_id TEXT NOT NULL CHECK (length(trim(tenant_id)) > 0),
                facility_id TEXT NOT NULL CHECK (length(trim(facility_id)) > 0),
                system_id TEXT NOT NULL CHECK (length(trim(system_id)) > 0),
                asset_equipment_id TEXT,
                finding_id TEXT,
                evidence_run_id TEXT,
                evidence_package_id TEXT,
                evidence_package_revision INTEGER CHECK (
                    evidence_package_revision IS NULL OR evidence_package_revision > 0
                ),
                evidence_content_hash TEXT,
                subject_type TEXT NOT NULL CHECK (subject_type IN (
                    'signal', 'relationship', 'asset_equipment', 'subsystem'
                )),
                subject_id TEXT NOT NULL,
                subject_mapping_version TEXT NOT NULL,
                behavioral_model_id TEXT,
                behavioral_model_version TEXT,
                behavioral_snapshot_id TEXT,
                baseline_reference_id TEXT,
                baseline_reference_version TEXT,
                telemetry_schema_fingerprint TEXT,
                system_configuration_fingerprint TEXT,
                compatibility_epoch TEXT,
                context_schema_version TEXT NOT NULL,
                context_json TEXT NOT NULL CHECK (
                    json_valid(context_json) AND json_type(context_json) = 'object'
                ),
                context_fingerprint TEXT NOT NULL,
                context_episode_id TEXT NOT NULL,
                context_source_refs_json TEXT NOT NULL CHECK (
                    json_valid(context_source_refs_json)
                    AND json_type(context_source_refs_json) = 'array'
                ),
                temporal_role TEXT NOT NULL CHECK (temporal_role IN (
                    'pre_outcome', 'outcome_period', 'post_intervention',
                    'recovery', 'stable_comparison'
                )),
                window_start_at TEXT NOT NULL,
                window_end_at TEXT NOT NULL,
                link_origin TEXT NOT NULL CHECK (link_origin IN (
                    'direct_source', 'human_reviewed', 'deterministic_reference'
                )),
                link_confidence TEXT NOT NULL CHECK (link_confidence IN (
                    'direct', 'reviewed', 'limited'
                )),
                link_basis_json TEXT NOT NULL CHECK (
                    json_valid(link_basis_json) AND json_type(link_basis_json) = 'object'
                ),
                linked_by TEXT NOT NULL,
                linked_at TEXT NOT NULL,
                retrospective_window_selection INTEGER NOT NULL DEFAULT 0 CHECK (
                    retrospective_window_selection IN (0, 1)
                ),
                subject_state TEXT NOT NULL CHECK (subject_state IN (
                    'active_changed', 'present_aligned', 'absent_evaluable', 'not_evaluable'
                )),
                observation_basis_json TEXT NOT NULL CHECK (
                    json_valid(observation_basis_json)
                    AND json_type(observation_basis_json) = 'object'
                ),
                link_status TEXT NOT NULL CHECK (link_status IN (
                    'pending', 'active', 'rejected', 'retracted', 'superseded'
                )),
                actor TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                idempotency_key TEXT,
                request_fingerprint TEXT,
                FOREIGN KEY(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    outcome_id, outcome_revision_id
                ) REFERENCES validated_outcomes(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    outcome_id, outcome_revision_id
                ) ON DELETE RESTRICT,
                UNIQUE(scope_storage_id, tenant_id, facility_id, system_id, link_id, revision),
                UNIQUE(scope_storage_id, tenant_id, facility_id, system_id, link_id, link_revision_id),
                FOREIGN KEY(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    link_id, supersedes_revision_id
                ) REFERENCES validated_outcome_links(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    link_id, link_revision_id
                ) ON DELETE RESTRICT,
                CHECK (window_end_at >= window_start_at),
                CHECK (
                    (revision = 1 AND supersedes_revision_id IS NULL)
                    OR (revision > 1 AND supersedes_revision_id IS NOT NULL)
                ),
                CHECK (
                    finding_id IS NOT NULL OR evidence_run_id IS NOT NULL
                    OR evidence_content_hash IS NOT NULL
                    OR behavioral_snapshot_id IS NOT NULL
                    OR baseline_reference_id IS NOT NULL
                ),
                CHECK (idempotency_key IS NULL OR request_fingerprint IS NOT NULL)
            );

            CREATE TABLE health_relevance_versions (
                relevance_version_id TEXT PRIMARY KEY,
                state_key_hash TEXT NOT NULL,
                version INTEGER NOT NULL CHECK (version > 0),
                scope_storage_id TEXT NOT NULL CHECK (length(trim(scope_storage_id)) > 0),
                tenant_id TEXT NOT NULL CHECK (length(trim(tenant_id)) > 0),
                facility_id TEXT NOT NULL CHECK (length(trim(facility_id)) > 0),
                system_id TEXT NOT NULL CHECK (length(trim(system_id)) > 0),
                asset_equipment_id TEXT,
                subject_type TEXT NOT NULL CHECK (subject_type IN (
                    'signal', 'relationship', 'asset_equipment', 'subsystem'
                )),
                subject_id TEXT NOT NULL,
                subject_mapping_version TEXT NOT NULL,
                context_schema_version TEXT NOT NULL,
                context_json TEXT NOT NULL CHECK (
                    json_valid(context_json) AND json_type(context_json) = 'object'
                ),
                context_fingerprint TEXT NOT NULL,
                compatibility_epoch TEXT NOT NULL,
                method_class TEXT NOT NULL CHECK (method_class IN (
                    'bayesian_shrinkage_v1', 'outcome_conditioned_information_v1'
                )),
                method_version TEXT NOT NULL,
                method_config_version TEXT NOT NULL,
                input_snapshot_id TEXT NOT NULL,
                input_manifest_hash TEXT NOT NULL,
                outcome_watermark TEXT NOT NULL,
                link_watermark TEXT NOT NULL,
                previous_version_id TEXT,
                raw_outcome_count INTEGER NOT NULL CHECK (raw_outcome_count >= 0),
                eligible_outcome_count INTEGER NOT NULL CHECK (eligible_outcome_count >= 0),
                canonical_incident_count INTEGER NOT NULL CHECK (canonical_incident_count >= 0),
                recurrence_count INTEGER NOT NULL CHECK (recurrence_count >= 0),
                positive_count INTEGER NOT NULL CHECK (positive_count >= 0),
                negative_count INTEGER NOT NULL CHECK (negative_count >= 0),
                neutral_count INTEGER NOT NULL CHECK (neutral_count >= 0),
                comparison_window_count INTEGER NOT NULL CHECK (comparison_window_count >= 0),
                excluded_count INTEGER NOT NULL CHECK (excluded_count >= 0),
                duplicate_suppressed_count INTEGER NOT NULL CHECK (duplicate_suppressed_count >= 0),
                outcome_family_counts_json TEXT NOT NULL CHECK (
                    json_valid(outcome_family_counts_json)
                    AND json_type(outcome_family_counts_json) = 'object'
                ),
                context_metadata_completeness REAL NOT NULL CHECK (
                    context_metadata_completeness >= 0.0
                    AND context_metadata_completeness <= 1.0
                ),
                context_episode_count INTEGER NOT NULL CHECK (context_episode_count >= 0),
                protocol_completion REAL CHECK (
                    protocol_completion IS NULL
                    OR (protocol_completion >= 0.0 AND protocol_completion <= 1.0)
                ),
                temporal_consistency REAL CHECK (
                    temporal_consistency IS NULL
                    OR (temporal_consistency >= 0.0 AND temporal_consistency <= 1.0)
                ),
                tier_a_count INTEGER NOT NULL CHECK (tier_a_count >= 0),
                tier_b_count INTEGER NOT NULL CHECK (tier_b_count >= 0),
                tier_c_count INTEGER NOT NULL CHECK (tier_c_count >= 0),
                tier_d_count INTEGER NOT NULL CHECK (tier_d_count >= 0),
                independent_count INTEGER NOT NULL CHECK (independent_count >= 0),
                neraium_influenced_count INTEGER NOT NULL CHECK (neraium_influenced_count >= 0),
                same_actor_validation_count INTEGER NOT NULL CHECK (same_actor_validation_count >= 0),
                evidence_state TEXT NOT NULL CHECK (evidence_state IN (
                    'insufficient_outcome_evidence', 'emerging_relevance',
                    'supported_relevance', 'contradictory_evidence',
                    'not_supported_by_outcomes'
                )),
                evidence_direction TEXT NOT NULL CHECK (evidence_direction IN (
                    'positive_dominant', 'negative_dominant', 'mixed', 'indeterminate'
                )),
                state_reason_codes_json TEXT NOT NULL CHECK (
                    json_valid(state_reason_codes_json)
                    AND json_type(state_reason_codes_json) = 'array'
                ),
                freshness_status TEXT NOT NULL CHECK (freshness_status IN (
                    'current', 'stale', 'superseded_epoch'
                )),
                method_components_json TEXT NOT NULL CHECK (
                    json_valid(method_components_json)
                    AND json_type(method_components_json) = 'object'
                ),
                uncertainty_json TEXT NOT NULL CHECK (
                    json_valid(uncertainty_json) AND json_type(uncertainty_json) = 'object'
                ),
                outcome_schema_version TEXT NOT NULL,
                threshold_config_version TEXT NOT NULL,
                threshold_config_json TEXT NOT NULL CHECK (
                    json_valid(threshold_config_json)
                    AND json_type(threshold_config_json) = 'object'
                ),
                authority_rules_version TEXT NOT NULL,
                dedup_rules_version TEXT NOT NULL,
                compatibility_rules_version TEXT NOT NULL,
                configuration_hash TEXT NOT NULL,
                first_evidence_at TEXT,
                last_evidence_at TEXT,
                computed_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                code_build_version TEXT NOT NULL,
                UNIQUE(state_key_hash, version),
                UNIQUE(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    relevance_version_id
                ),
                UNIQUE(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    state_key_hash, relevance_version_id
                ),
                FOREIGN KEY(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    state_key_hash, previous_version_id
                ) REFERENCES health_relevance_versions(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    state_key_hash, relevance_version_id
                ) ON DELETE RESTRICT,
                CHECK (
                    (version = 1 AND previous_version_id IS NULL)
                    OR (version > 1 AND previous_version_id IS NOT NULL)
                ),
                CHECK (
                    (first_evidence_at IS NULL AND last_evidence_at IS NULL)
                    OR (first_evidence_at IS NOT NULL AND last_evidence_at IS NOT NULL
                        AND last_evidence_at >= first_evidence_at)
                )
            );

            CREATE TABLE health_relevance_contributions (
                contribution_id TEXT PRIMARY KEY,
                relevance_version_id TEXT NOT NULL,
                outcome_id TEXT NOT NULL,
                outcome_revision_id TEXT NOT NULL,
                link_id TEXT NOT NULL,
                link_revision_id TEXT NOT NULL,
                scope_storage_id TEXT NOT NULL CHECK (length(trim(scope_storage_id)) > 0),
                tenant_id TEXT NOT NULL CHECK (length(trim(tenant_id)) > 0),
                facility_id TEXT NOT NULL CHECK (length(trim(facility_id)) > 0),
                system_id TEXT NOT NULL CHECK (length(trim(system_id)) > 0),
                asset_equipment_id TEXT,
                subject_type TEXT NOT NULL CHECK (subject_type IN (
                    'signal', 'relationship', 'asset_equipment', 'subsystem'
                )),
                subject_id TEXT NOT NULL,
                subject_mapping_version TEXT NOT NULL,
                context_fingerprint TEXT NOT NULL,
                compatibility_epoch TEXT NOT NULL,
                canonical_incident_key TEXT,
                outcome_family TEXT NOT NULL CHECK (outcome_family IN (
                    'degradation_or_fault', 'inspection_confirmation',
                    'maintenance_or_intervention', 'repair_or_replacement',
                    'recovery', 'expected_or_no_fault',
                    'not_useful_or_false_positive', 'validated_explanation'
                )),
                evidence_treatment TEXT NOT NULL CHECK (evidence_treatment IN (
                    'positive', 'negative', 'neutral', 'comparison',
                    'contradictory', 'excluded', 'duplicate_suppressed'
                )),
                subject_state TEXT NOT NULL CHECK (subject_state IN (
                    'active_changed', 'present_aligned', 'absent_evaluable', 'not_evaluable'
                )),
                temporal_role TEXT NOT NULL CHECK (temporal_role IN (
                    'pre_outcome', 'outcome_period', 'post_intervention',
                    'recovery', 'stable_comparison'
                )),
                authority_tier TEXT NOT NULL CHECK (authority_tier IN ('A', 'B', 'C', 'D')),
                provenance_categories_json TEXT NOT NULL CHECK (
                    json_valid(provenance_categories_json)
                    AND json_type(provenance_categories_json) = 'array'
                ),
                method_input_cell TEXT NOT NULL DEFAULT 'not_applicable',
                method_component_json TEXT NOT NULL CHECK (
                    json_valid(method_component_json)
                    AND json_type(method_component_json) = 'object'
                ),
                reason_code TEXT NOT NULL,
                finding_id TEXT,
                evidence_run_id TEXT,
                evidence_package_id TEXT,
                evidence_content_hash TEXT,
                behavioral_model_id TEXT,
                behavioral_model_version TEXT,
                behavioral_snapshot_id TEXT,
                baseline_reference_id TEXT,
                baseline_reference_version TEXT,
                telemetry_schema_fingerprint TEXT,
                system_configuration_fingerprint TEXT,
                input_manifest_hash TEXT NOT NULL,
                configuration_hash TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    relevance_version_id
                ) REFERENCES health_relevance_versions(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    relevance_version_id
                ) ON DELETE RESTRICT,
                FOREIGN KEY(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    outcome_id, outcome_revision_id
                ) REFERENCES validated_outcomes(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    outcome_id, outcome_revision_id
                ) ON DELETE RESTRICT,
                FOREIGN KEY(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    link_id, link_revision_id
                ) REFERENCES validated_outcome_links(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    link_id, link_revision_id
                ) ON DELETE RESTRICT,
                UNIQUE(
                    relevance_version_id, outcome_revision_id, link_revision_id,
                    evidence_treatment, method_input_cell
                )
            );

            CREATE INDEX idx_validated_outcomes_latest
                ON validated_outcomes(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    outcome_id, revision DESC
                );
            CREATE INDEX idx_validated_outcomes_status_time
                ON validated_outcomes(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    validation_status, occurred_start_at DESC
                );
            CREATE INDEX idx_validated_outcomes_incident
                ON validated_outcomes(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    canonical_incident_key, occurred_start_at DESC
                );
            CREATE UNIQUE INDEX uq_validated_outcomes_source_identity
                ON validated_outcomes(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    source_identity_hash
                ) WHERE source_identity_hash IS NOT NULL AND revision = 1;
            CREATE UNIQUE INDEX uq_validated_outcomes_idempotency
                ON validated_outcomes(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    idempotency_key
                ) WHERE idempotency_key IS NOT NULL;

            CREATE INDEX idx_validated_outcome_links_latest
                ON validated_outcome_links(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    link_id, revision DESC
                );
            CREATE INDEX idx_validated_outcome_links_outcome
                ON validated_outcome_links(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    outcome_id, outcome_revision_id
                );
            CREATE INDEX idx_validated_outcome_links_subject
                ON validated_outcome_links(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    subject_type, subject_id, context_fingerprint, compatibility_epoch
                );
            CREATE INDEX idx_validated_outcome_links_lineage
                ON validated_outcome_links(finding_id, evidence_run_id, evidence_content_hash);
            CREATE UNIQUE INDEX uq_validated_outcome_links_idempotency
                ON validated_outcome_links(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    idempotency_key
                ) WHERE idempotency_key IS NOT NULL;

            CREATE INDEX idx_health_relevance_versions_latest
                ON health_relevance_versions(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    subject_type, subject_id, context_fingerprint,
                    compatibility_epoch, method_class, version DESC
                );
            CREATE INDEX idx_health_relevance_versions_snapshot
                ON health_relevance_versions(input_snapshot_id, input_manifest_hash, method_class);
            CREATE UNIQUE INDEX uq_health_relevance_versions_input
                ON health_relevance_versions(
                    state_key_hash, input_snapshot_id, input_manifest_hash,
                    method_class, method_version, configuration_hash, code_build_version
                );

            CREATE INDEX idx_health_relevance_contributions_version
                ON health_relevance_contributions(relevance_version_id, evidence_treatment);
            CREATE INDEX idx_health_relevance_contributions_outcome
                ON health_relevance_contributions(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    outcome_id, outcome_revision_id
                );
            CREATE INDEX idx_health_relevance_contributions_link
                ON health_relevance_contributions(
                    scope_storage_id, tenant_id, facility_id, system_id,
                    link_id, link_revision_id
                );

            CREATE TRIGGER trg_validated_outcomes_no_update
            BEFORE UPDATE ON validated_outcomes
            BEGIN SELECT RAISE(ABORT, 'validated_outcomes_append_only'); END;
            CREATE TRIGGER trg_validated_outcomes_no_delete
            BEFORE DELETE ON validated_outcomes
            BEGIN SELECT RAISE(ABORT, 'validated_outcomes_append_only'); END;
            CREATE TRIGGER trg_validated_outcome_links_no_update
            BEFORE UPDATE ON validated_outcome_links
            BEGIN SELECT RAISE(ABORT, 'validated_outcome_links_append_only'); END;
            CREATE TRIGGER trg_validated_outcome_links_no_delete
            BEFORE DELETE ON validated_outcome_links
            BEGIN SELECT RAISE(ABORT, 'validated_outcome_links_append_only'); END;
            CREATE TRIGGER trg_health_relevance_versions_no_update
            BEFORE UPDATE ON health_relevance_versions
            BEGIN SELECT RAISE(ABORT, 'health_relevance_versions_append_only'); END;
            CREATE TRIGGER trg_health_relevance_versions_no_delete
            BEFORE DELETE ON health_relevance_versions
            BEGIN SELECT RAISE(ABORT, 'health_relevance_versions_append_only'); END;
            CREATE TRIGGER trg_health_relevance_contributions_no_update
            BEFORE UPDATE ON health_relevance_contributions
            BEGIN SELECT RAISE(ABORT, 'health_relevance_contributions_append_only'); END;
            CREATE TRIGGER trg_health_relevance_contributions_no_delete
            BEFORE DELETE ON health_relevance_contributions
            BEGIN SELECT RAISE(ABORT, 'health_relevance_contributions_append_only'); END;
            """
        )
        connection.execute(
            "INSERT INTO runtime_schema_migrations (migration_id, applied_at) VALUES (?, ?)",
            ("013_internal_health_relevance", now_iso()),
        )
