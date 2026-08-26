from __future__ import annotations

import os
from typing import Any

import pytest

from app.services.telemetry_runtime import TelemetryRuntime, TelemetryRuntimeUnavailable
from db.migrations.create_telemetry_connection_tables import (
    DDL,
    EXPECTED_COLUMNS,
    EXPECTED_TABLES,
    MIGRATION_ID,
    apply,
    rollback_empty_schema_for_tests,
    verify,
)
from db.migrations.extend_telemetry_ingestion_runtime import (
    DDL as INGESTION_DDL,
    EXPECTED_COLUMNS as INGESTION_COLUMNS,
    EXPECTED_CONSTRAINTS as INGESTION_CONSTRAINTS,
    EXPECTED_INDEXES as INGESTION_INDEXES,
    MIGRATION_ID as INGESTION_MIGRATION_ID,
    REQUIRED_MIGRATIONS,
    apply as apply_ingestion_extension,
    downgrade as downgrade_ingestion_extension,
    verify as verify_ingestion_extension,
)
from db.migrations.persist_canonical_analysis_results import (
    DDL as RESULT_ARTIFACT_DDL,
    EXPECTED_COLUMNS as RESULT_ARTIFACT_COLUMNS,
    EXPECTED_CONSTRAINTS as RESULT_ARTIFACT_CONSTRAINTS,
    EXPECTED_INDEXES as RESULT_ARTIFACT_INDEXES,
    EXPECTED_TRIGGERS as RESULT_ARTIFACT_TRIGGERS,
    MIGRATION_ID as RESULT_ARTIFACT_MIGRATION_ID,
    REQUIRED_MIGRATIONS as RESULT_ARTIFACT_PREREQUISITES,
    apply as apply_result_artifact_migration,
    downgrade as downgrade_result_artifact_migration,
    verify as verify_result_artifact_migration,
)


class _MigrationCursor:
    def __init__(self, connection: "_MigrationConnection") -> None:
        self.connection = connection
        self._one: Any = None
        self._many: list[Any] = []

    def __enter__(self) -> "_MigrationCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.connection.statements.append((sql, params))
        normalized = " ".join(sql.split())
        self._one = None
        self._many = []
        if normalized.startswith("SELECT 1 FROM telemetry.schema_migrations"):
            self._one = (1,) if self.connection.applied else None
        elif normalized.startswith("INSERT INTO telemetry.schema_migrations"):
            self.connection.applied = True
        elif "FROM information_schema.tables" in normalized:
            if "table_name = ANY" in normalized:
                self._many = [(name,) for name in self.connection.existing_tables]
            else:
                self._many = [(name,) for name in sorted(EXPECTED_TABLES)]
        elif "FROM information_schema.columns" in normalized:
            self._many = [
                (table_name, column_name)
                for table_name, columns in EXPECTED_COLUMNS.items()
                for column_name in sorted(columns)
            ]
        elif normalized.startswith("SELECT EXISTS"):
            self._one = (self.connection.nonempty,)

    def fetchone(self) -> Any:
        return self._one

    def fetchall(self) -> list[Any]:
        return list(self._many)


class _MigrationConnection:
    def __init__(
        self,
        *,
        applied: bool = False,
        existing_tables: tuple[str, ...] = (),
        nonempty: bool = False,
    ) -> None:
        self.applied = applied
        self.existing_tables = existing_tables
        self.nonempty = nonempty
        self.statements: list[tuple[str, object]] = []
        self.commits = 0

    def cursor(self) -> _MigrationCursor:
        return _MigrationCursor(self)

    def commit(self) -> None:
        self.commits += 1


def test_telemetry_migration_is_additive_scoped_and_postgresql_first() -> None:
    required = EXPECTED_TABLES - {"schema_migrations"}
    for table in required:
        assert f"telemetry.{table}" in DDL
    assert DDL.count("resource_scope_id TEXT NOT NULL") >= len(required) - 1
    assert DDL.count("tenant_scope_id TEXT NOT NULL") >= len(required) - 1
    assert DDL.count("workspace_id TEXT NOT NULL") >= len(required) - 1
    assert DDL.count("facility_id TEXT NOT NULL") >= len(required) - 1
    assert "TIMESTAMPTZ" in DDL
    assert "FOR UPDATE" not in DDL
    assert "CREATE EXTENSION" not in DDL
    assert "ALTER TABLE data_connections" not in DDL
    assert "runtime.db" not in DDL
    assert "INSERT INTO telemetry.data_connections" not in DDL
    assert "UPDATE telemetry.data_connections" not in DDL


def test_telemetry_migration_has_lifecycle_quality_lineage_and_scale_contracts() -> None:
    assert "connector_type IN ('https_telemetry', 'historian_template')" in DDL
    assert "connector_type IN ('https'," not in DDL
    assert "mode IN ('discovery', 'incremental', 'backfill')" in DDL
    assert "'draft', 'validating', 'connected', 'degraded', 'disconnected'" in DDL
    assert "'good', 'stale', 'missing', 'invalid_value', 'unit_unresolved'" in DDL
    assert "source_timestamp_raw TEXT NOT NULL" in DDL
    assert "observed_at_utc TIMESTAMPTZ NOT NULL" in DDL
    assert "timestamp_normalization_version TEXT NOT NULL" in DDL
    assert "original_value JSONB NOT NULL" in DDL
    assert "source_record_digest TEXT NOT NULL" in DDL
    assert "conversion_version TEXT" in DDL
    assert "analysis_window_observations" in DDL
    assert "external_tag_id TEXT NOT NULL" in DDL
    assert "CREATE UNIQUE INDEX ux_telemetry_signal_mapping_enabled" in DDL
    assert "CREATE UNIQUE INDEX ux_telemetry_signal_mapping_canonical_hierarchy" in DDL
    assert "ix_telemetry_observation_signal_time" in DDL
    assert "ix_telemetry_observation_tenant_connection_time" in DDL
    assert "ix_telemetry_ingestion_run_tenant_connection_time" in DDL
    assert "ix_telemetry_connection_due" in DDL
    assert "internal_reference TEXT NOT NULL" in DDL
    assert "secret_value" not in DDL
    assert "password" not in DDL.lower()


def test_apply_is_versioned_advisory_locked_and_idempotent() -> None:
    connection = _MigrationConnection()
    apply(connection)
    apply(connection)

    all_sql = "\n".join(sql for sql, _ in connection.statements)
    assert all_sql.count("CREATE TABLE telemetry.data_connections") == 1
    assert "pg_advisory_xact_lock" in all_sql
    assert connection.applied is True
    assert connection.commits == 2


def test_verify_checks_ledger_and_complete_table_set() -> None:
    connection = _MigrationConnection(applied=True)
    report = verify(connection)
    assert report["migration_id"] == MIGRATION_ID
    assert set(report["tables"]) == EXPECTED_TABLES

    missing = _MigrationConnection(applied=False)
    with pytest.raises(RuntimeError, match="telemetry_schema_migration_not_applied"):
        verify(missing)


def test_test_rollback_requires_confirmation_and_refuses_nonempty_schema() -> None:
    connection = _MigrationConnection(existing_tables=("data_connections",), nonempty=True)
    with pytest.raises(ValueError, match="confirmation_required"):
        rollback_empty_schema_for_tests(connection, confirmation="no")
    with pytest.raises(RuntimeError, match="refused_nonempty_schema"):
        rollback_empty_schema_for_tests(
            connection,
            confirmation="DROP_EMPTY_TEST_TELEMETRY_SCHEMA",
        )
    assert "DROP SCHEMA telemetry CASCADE" not in {sql for sql, _ in connection.statements}


def test_test_rollback_allows_only_empty_disposable_schema() -> None:
    connection = _MigrationConnection(existing_tables=("data_connections",), nonempty=False)
    rollback_empty_schema_for_tests(
        connection,
        confirmation="DROP_EMPTY_TEST_TELEMETRY_SCHEMA",
    )
    assert "DROP SCHEMA telemetry CASCADE" in {sql for sql, _ in connection.statements}
    assert connection.commits == 1


class _ExtensionCursor:
    def __init__(self, connection: "_ExtensionConnection") -> None:
        self.connection = connection
        self._one: Any = None
        self._many: list[Any] = []

    def __enter__(self) -> "_ExtensionCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.connection.statements.append((sql, params))
        normalized = " ".join(sql.split())
        self._one = None
        self._many = []
        if normalized.startswith("SELECT migration_id FROM telemetry.schema_migrations"):
            self._many = [(item,) for item in self.connection.prerequisites]
        elif normalized.startswith("SELECT 1 FROM telemetry.schema_migrations"):
            self._one = (1,) if self.connection.applied else None
        elif normalized.startswith("INSERT INTO telemetry.schema_migrations"):
            self.connection.applied = True
        elif "FROM information_schema.columns" in normalized:
            self._many = [
                (table, column)
                for table, columns in INGESTION_COLUMNS.items()
                for column in columns
            ]
        elif "FROM pg_indexes" in normalized:
            self._many = [(item,) for item in INGESTION_INDEXES]
        elif "FROM information_schema.table_constraints" in normalized:
            self._many = [(item,) for item in INGESTION_CONSTRAINTS]

    def fetchone(self) -> Any:
        return self._one

    def fetchall(self) -> list[Any]:
        return list(self._many)


class _ExtensionConnection:
    def __init__(
        self,
        *,
        prerequisites: tuple[str, ...] = REQUIRED_MIGRATIONS,
        applied: bool = False,
    ) -> None:
        self.prerequisites = prerequisites
        self.applied = applied
        self.statements: list[tuple[str, object]] = []
        self.commits = 0

    def cursor(self) -> _ExtensionCursor:
        return _ExtensionCursor(self)

    def commit(self) -> None:
        self.commits += 1


def test_ingestion_extension_is_additive_lineage_and_scheduler_only() -> None:
    assert INGESTION_MIGRATION_ID == "004_extend_telemetry_ingestion_runtime"
    for column in INGESTION_COLUMNS["normalized_observations"]:
        assert column in INGESTION_DDL
    for column in INGESTION_COLUMNS["observation_rejections"]:
        assert column in INGESTION_DDL
    assert "ux_telemetry_observation_provider_event" in INGESTION_DDL
    assert "ix_telemetry_connection_worker_due" in INGESTION_DDL
    assert "ux_telemetry_active_backfill_connection" in INGESTION_DDL
    assert "ux_telemetry_active_retry_source" in INGESTION_DDL
    assert "source_run_id" in INGESTION_DDL
    assert "fk_telemetry_ingestion_run_source" in INGESTION_DDL
    assert "ux_telemetry_ingestion_run_scoped_connection_id" in INGESTION_DDL
    assert "analysis_authority_snapshots" in INGESTION_DDL
    assert "execution_claim_token" in INGESTION_DDL
    assert "result_metadata" in INGESTION_DDL
    assert "evidence_lineage" in INGESTION_DDL
    assert "'stale', 'missing', 'invalid_value'" in INGESTION_DDL
    lowered = INGESTION_DDL.lower()
    assert "legacy" not in lowered
    assert "upload" not in lowered
    assert "delete from" not in lowered
    assert "drop table" not in lowered
    assert "drop column" not in lowered
    assert "ingestion_retry_requested" in INGESTION_DDL


def test_ingestion_extension_requires_foundation_and_is_idempotent() -> None:
    missing = _ExtensionConnection(prerequisites=(REQUIRED_MIGRATIONS[0],))
    with pytest.raises(RuntimeError, match="prerequisite_missing"):
        apply_ingestion_extension(missing)

    connection = _ExtensionConnection()
    apply_ingestion_extension(connection)
    apply_ingestion_extension(connection)
    all_sql = "\n".join(sql for sql, _ in connection.statements)
    assert all_sql.count("ALTER TABLE telemetry.normalized_observations") == 1
    assert "pg_advisory_xact_lock" in all_sql
    assert connection.commits == 2


def test_ingestion_extension_verify_and_forward_only_downgrade() -> None:
    connection = _ExtensionConnection(applied=True)
    report = verify_ingestion_extension(connection)
    assert report["migration_id"] == INGESTION_MIGRATION_ID
    assert set(report["columns"]) == set(INGESTION_COLUMNS)
    assert set(report["indexes"]) == INGESTION_INDEXES
    assert set(report["constraints"]) == INGESTION_CONSTRAINTS
    with pytest.raises(RuntimeError, match="downgrade_unsupported"):
        downgrade_ingestion_extension(connection)


def test_ingestion_extension_contract_against_explicit_postgres() -> None:
    dsn = os.environ.get("NERAIUM_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("NERAIUM_TEST_POSTGRES_DSN is not configured")
    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as connection:
        report = verify_ingestion_extension(connection)
    assert report["migration_id"] == INGESTION_MIGRATION_ID


class _ResultArtifactCursor:
    def __init__(self, connection: "_ResultArtifactConnection") -> None:
        self.connection = connection
        self._one: Any = None
        self._many: list[Any] = []

    def __enter__(self) -> "_ResultArtifactCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.connection.statements.append((sql, params))
        normalized = " ".join(sql.split())
        self._one = None
        self._many = []
        if normalized.startswith("SELECT migration_id FROM telemetry.schema_migrations"):
            self._many = [(item,) for item in self.connection.prerequisites]
        elif normalized.startswith("SELECT 1 FROM telemetry.schema_migrations"):
            self._one = (1,) if self.connection.applied else None
        elif normalized.startswith("INSERT INTO telemetry.schema_migrations"):
            self.connection.applied = True
        elif "FROM information_schema.columns" in normalized:
            self._many = [(column,) for column in RESULT_ARTIFACT_COLUMNS]
        elif "FROM pg_indexes" in normalized:
            self._many = [(item,) for item in RESULT_ARTIFACT_INDEXES]
        elif "FROM information_schema.table_constraints" in normalized:
            self._many = [(item,) for item in RESULT_ARTIFACT_CONSTRAINTS]
        elif "FROM information_schema.triggers" in normalized:
            self._many = [(item,) for item in RESULT_ARTIFACT_TRIGGERS]

    def fetchone(self) -> Any:
        return self._one

    def fetchall(self) -> list[Any]:
        return list(self._many)


class _ResultArtifactConnection:
    def __init__(
        self,
        *,
        prerequisites: tuple[str, ...] = RESULT_ARTIFACT_PREREQUISITES,
        applied: bool = False,
    ) -> None:
        self.prerequisites = prerequisites
        self.applied = applied
        self.statements: list[tuple[str, object]] = []
        self.commits = 0

    def cursor(self) -> _ResultArtifactCursor:
        return _ResultArtifactCursor(self)

    def commit(self) -> None:
        self.commits += 1


def test_result_artifact_migration_is_scoped_bounded_and_immutable() -> None:
    assert RESULT_ARTIFACT_MIGRATION_ID == "005_persist_canonical_analysis_results"
    assert "CREATE TABLE IF NOT EXISTS telemetry.analysis_result_artifacts" in (
        RESULT_ARTIFACT_DDL
    )
    for column in RESULT_ARTIFACT_COLUMNS:
        assert column in RESULT_ARTIFACT_DDL
    for required_scope in (
        "tenant_scope_id TEXT NOT NULL",
        "workspace_id TEXT NOT NULL",
        "resource_scope_id TEXT NOT NULL",
        "facility_id TEXT NOT NULL",
        "connection_id UUID NOT NULL",
        "system_id TEXT NOT NULL",
    ):
        assert required_scope in RESULT_ARTIFACT_DDL
    assert "payload_uncompressed_bytes <= 268435456" in RESULT_ARTIFACT_DDL
    assert "payload_stored_bytes <= 268435456" in RESULT_ARTIFACT_DDL
    assert "payload_stored_bytes = octet_length(payload)" in RESULT_ARTIFACT_DDL
    assert "payload_encoding = 'zlib+canonical-json.v1'" in RESULT_ARTIFACT_DDL
    assert "BEFORE UPDATE OR DELETE" in RESULT_ARTIFACT_DDL
    assert "analysis_window.asset_id IS NOT DISTINCT FROM NEW.asset_id" in (
        RESULT_ARTIFACT_DDL
    )
    assert "ON DELETE RESTRICT" in RESULT_ARTIFACT_DDL
    lowered = RESULT_ARTIFACT_DDL.lower()
    assert "delete from" not in lowered
    assert "drop table" not in lowered
    assert "drop column" not in lowered
    assert "normalized_telemetry" not in lowered


def test_result_artifact_migration_requires_runtime_and_is_idempotent() -> None:
    missing = _ResultArtifactConnection(prerequisites=())
    with pytest.raises(RuntimeError, match="prerequisite_missing"):
        apply_result_artifact_migration(missing)

    connection = _ResultArtifactConnection()
    apply_result_artifact_migration(connection)
    apply_result_artifact_migration(connection)
    all_sql = "\n".join(sql for sql, _ in connection.statements)
    assert all_sql.count("CREATE TABLE IF NOT EXISTS telemetry.analysis_result_artifacts") == 1
    assert "pg_advisory_xact_lock" in all_sql
    assert connection.commits == 2


def test_result_artifact_migration_verify_and_forward_only_downgrade() -> None:
    connection = _ResultArtifactConnection(applied=True)
    report = verify_result_artifact_migration(connection)
    assert report["migration_id"] == RESULT_ARTIFACT_MIGRATION_ID
    assert set(report["columns"]) == RESULT_ARTIFACT_COLUMNS
    assert set(report["indexes"]) == RESULT_ARTIFACT_INDEXES
    assert set(report["constraints"]) == RESULT_ARTIFACT_CONSTRAINTS
    assert set(report["triggers"]) == RESULT_ARTIFACT_TRIGGERS
    with pytest.raises(RuntimeError, match="downgrade_unsupported"):
        downgrade_result_artifact_migration(connection)


def test_result_artifact_contract_against_explicit_postgres() -> None:
    dsn = os.environ.get("NERAIUM_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("NERAIUM_TEST_POSTGRES_DSN is not configured")
    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as connection:
        report = verify_result_artifact_migration(connection)
    assert report["migration_id"] == RESULT_ARTIFACT_MIGRATION_ID


def _ready_runtime(repository: object) -> TelemetryRuntime:
    return TelemetryRuntime(
        repository=repository,
        secret_store=object(),
        providers=object(),
        signal_registry=object(),
        health_service=object(),
        scheduler=object(),
    )


def test_runtime_readiness_runs_every_structural_migration_verifier(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    class Connection:
        def close(self) -> None:
            calls.append(("close", self))

    connection = Connection()

    class Repository:
        _connection_factory = staticmethod(lambda: connection)

    monkeypatch.setattr(
        "db.migrations.create_telemetry_connection_tables.verify",
        lambda candidate: calls.append(("base", candidate)),
    )
    monkeypatch.setattr(
        "db.migrations.seed_telemetry_canonical_signal_concepts.verify",
        lambda candidate: calls.append(("catalog", candidate)),
    )
    monkeypatch.setattr(
        "db.migrations.extend_telemetry_ingestion_runtime.verify",
        lambda candidate: calls.append(("runtime", candidate)),
    )
    monkeypatch.setattr(
        "db.migrations.persist_canonical_analysis_results.verify",
        lambda candidate: calls.append(("results", candidate)),
    )

    assert _ready_runtime(Repository()).verify_readiness() is True
    assert calls == [
        ("base", connection),
        ("catalog", connection),
        ("runtime", connection),
        ("results", connection),
        ("close", connection),
    ]


def test_runtime_readiness_fails_closed_on_structural_verification_error(
    monkeypatch,
) -> None:
    closed: list[bool] = []

    class Connection:
        def close(self) -> None:
            closed.append(True)

    class Repository:
        _connection_factory = staticmethod(Connection)

    def fail_verification(_candidate: object) -> None:
        raise RuntimeError("missing index")

    monkeypatch.setattr(
        "db.migrations.create_telemetry_connection_tables.verify",
        fail_verification,
    )

    with pytest.raises(TelemetryRuntimeUnavailable) as captured:
        _ready_runtime(Repository()).verify_readiness()

    assert captured.value.code == "telemetry_schema_not_ready"
    assert closed == [True]
