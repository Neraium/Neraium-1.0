"""Disposable PostgreSQL-only qualification; creates and drops isolated fixtures.

Set NERAIUM_TEST_POSTGRES_DSN to an administrative disposable instance and run
with -m integration. No production environment variables or cloud services are
used. The fixture creates its own database and separate release/runtime roles.
"""
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.services import auth_store, runtime_db, runtime_postgres
from app.services.schema_verification import SchemaIncompatibilityError, postgres_catalog, verify_postgres
from app.services.telemetry_runtime import build_telemetry_runtime
from db.migrations.apply_runtime import main as migrate_command

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def database():
    admin = os.getenv("NERAIUM_TEST_POSTGRES_DSN")
    if not admin:
        pytest.skip("requires explicitly disposable PostgreSQL admin DSN")
    suffix = uuid.uuid4().hex[:16]
    database = "ddl_" + suffix
    migrator, runtime, grantee = ("ddl_m_" + suffix, "ddl_r_" + suffix, "ddl_g_" + suffix)
    fixture_password = secrets.token_hex(24)
    with psycopg.connect(admin, autocommit=True) as c:
        for role in (migrator, runtime, grantee):
            c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT").format(sql.Identifier(role), sql.Literal(fixture_password)))
        c.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(migrator)))
    migration_dsn = make_conninfo(admin, dbname=database, user=migrator, password=fixture_password, sslmode="require")
    runtime_dsn = make_conninfo(admin, dbname=database, user=runtime, password=fixture_password, sslmode="require")
    admin_dsn = make_conninfo(admin, dbname=database)
    try:
        with psycopg.connect(admin_dsn) as c:
            c.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
            c.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            c.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(sql.Identifier(database), sql.Identifier(migrator), sql.Identifier(runtime)))
        with pytest.MonkeyPatch.context() as patch:
            for name in ("RUNTIME", "AUTH", "TELEMETRY"):
                patch.setenv(f"NERAIUM_{name}_MIGRATION_DSN", migration_dsn)
            patch.setattr(sys, "argv", ["apply_runtime", "--component", "all"])
            assert migrate_command() == 0  # Clean database, migration identity.
            assert migrate_command() == 0  # Idempotent pre-change/current ledgers.
        with psycopg.connect(migration_dsn) as c:
            editable_runtime = {
                "upload_jobs", "upload_queue", "evidence_runs", "latest_payloads", "data_connections",
                "telemetry_ingestion_batches", "telemetry_signal_mappings", "normalized_telemetry",
                "rejected_telemetry", "telemetry_ingestion_health", "live_analysis_configurations",
                "live_analysis_runs", "live_findings", "live_analysis_health", "upload_queue_routing",
            }
            immutable_telemetry = {
                "analysis_result_artifacts",
                "analysis_window_observations", "normalized_observations", "observation_rejections",
                "telemetry_audit_events", "relationship_lineage_artifacts_v2", "endpoint_analysis_executions_v2",
            }
            for schema in ("public", "neraium_runtime", "telemetry"):
                c.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(sql.Identifier(schema)))
                c.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(runtime)))
                c.execute(sql.SQL("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {} FROM PUBLIC").format(sql.Identifier(schema)))
                c.execute(sql.SQL("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(runtime)))
                for (table,) in c.execute("SELECT tablename FROM pg_tables WHERE schemaname=%s", (schema,)).fetchall():
                    privileges = "SELECT"
                    if schema == "public" and table != "auth_schema_migrations":
                        privileges = "SELECT,INSERT,UPDATE" + (",DELETE" if table == "auth_sessions" else "")
                    elif schema == "neraium_runtime" and table not in {"runtime_schema_migrations", "postgres_runtime_migrations", "auth_users", "auth_sessions"}:
                        privileges = "SELECT,INSERT,UPDATE,DELETE" if table in editable_runtime else "SELECT,INSERT"
                    elif schema == "telemetry" and table not in {"schema_migrations", "canonical_signal_concepts"}:
                        privileges = "SELECT,INSERT" if table in immutable_telemetry else "SELECT,INSERT,UPDATE"
                        if table == "connection_checkpoints": privileges += ",DELETE"
                    c.execute(sql.SQL(f"GRANT {privileges} ON TABLE {{}}.{{}} TO {{}}").format(sql.Identifier(schema), sql.Identifier(table), sql.Identifier(runtime)))
                c.execute(sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(runtime)))
        yield dict(admin=admin_dsn, migration=migration_dsn, runtime=runtime_dsn,
                   migrator=migrator, role=runtime, grantee=grantee)
    finally:
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
            for role in (runtime, migrator, grantee):
                c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


@pytest.fixture
def runtime_environment(database, monkeypatch, tmp_path):
    # Remove ambient production configuration without reading or resolving it.
    for name in tuple(os.environ):
        if name.startswith(("NERAIUM_", "AWS_")) and name not in {"NERAIUM_TEST_POSTGRES_DSN", "NERAIUM_RUNTIME_DIR"}:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.test")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")
    for name in ("RUNTIME", "AUTH", "TELEMETRY"):
        # URL syntax is validated by app settings; psycopg accepts conninfo too.
        params = psycopg.conninfo.conninfo_to_dict(database["runtime"])
        from urllib.parse import quote
        dsn = f"postgresql://{quote(params['user'])}:{quote(params['password'])}@{params.get('host','127.0.0.1')}:{params.get('port','5432')}/{params['dbname']}?sslmode=require"
        monkeypatch.setenv(f"NERAIUM_{name}_DATABASE_URL", dsn)
    from test_upload_queue_scope_routing import _FakeS3Client, _configure_shared_runtime
    _configure_shared_runtime(monkeypatch, _FakeS3Client())
    monkeypatch.setattr(auth_store, "_AUTH_BACKEND", None)
    monkeypatch.setattr(auth_store, "_AUTH_BACKEND_KEY", None)
    settings = Settings(app_env="prod",backend_host="127.0.0.1",backend_port=8080,
        cors_origins=["https://app.example.test"], runtime_dir=runtime_db.RUNTIME_DIR,
        process_role="api", telemetry_database_url=os.environ["NERAIUM_TELEMETRY_DATABASE_URL"],
        telemetry_secret_region="us-east-2", telemetry_controlled_egress_enabled=True,
        telemetry_executor_url="https://executor.example.test:8443",
        telemetry_executor_ca_pem="-----BEGIN CERTIFICATE-----\nlocal-unused-fixture\n-----END CERTIFICATE-----",
        telemetry_executor_auth_secret_arn="local-fixture-only",
        telemetry_execution_identity_version="physical-endpoint-keyed.v2")
    monkeypatch.setenv("NERAIUM_TELEMETRY_EXECUTOR_URL", settings.telemetry_executor_url)
    monkeypatch.setenv("NERAIUM_TELEMETRY_EXECUTOR_CA_PEM", settings.telemetry_executor_ca_pem)
    monkeypatch.setenv("NERAIUM_TELEMETRY_EXECUTOR_AUTH_SECRET_ARN", settings.telemetry_executor_auth_secret_arn)
    monkeypatch.setenv("NERAIUM_TELEMETRY_SECRET_REGION", settings.telemetry_secret_region)
    monkeypatch.setenv("NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED", "true")
    yield settings


def test_api_and_worker_start_without_create_privilege(database, runtime_environment, monkeypatch):
    from app.main import create_app
    from app import entrypoint, live_analysis_worker
    # Only cloud artifact/heartbeat I/O is replaced. Database startup, auth
    # verification and the telemetry scheduler/repositories are real.
    monkeypatch.setattr(entrypoint, "_publish_worker_health", lambda **kwargs: None)
    monkeypatch.setattr(entrypoint, "_publish_telemetry_worker_health", lambda **kwargs: None)
    from app.services import telemetry_scheduler
    monkeypatch.setattr(telemetry_scheduler.TelemetryScheduler, "_publish_heartbeat", lambda *a, **k: None)
    with TestClient(create_app(runtime_environment), base_url="https://testserver") as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/ready").status_code == 200
        assert client.app.state.telemetry_runtime.verify_readiness()
    stop = threading.Event()
    real_process = entrypoint.process_next_queued_upload_job
    def one_iteration():
        result = real_process()
        stop.set()
        return result
    monkeypatch.setattr(entrypoint, "process_next_queued_upload_job", one_iteration)
    entrypoint.run_worker(replace(runtime_environment, process_role="worker"), poll_interval_seconds=0.01, shutdown_event=stop)
    assert stop.is_set()
    monkeypatch.setattr(live_analysis_worker, "_arguments", lambda: type("Args", (), {"once": True})())
    live_analysis_worker.main()
    with psycopg.connect(database["runtime"]) as c:
        assert c.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone() == (True,)
        assert c.execute("SELECT has_schema_privilege(current_user,'neraium_runtime','CREATE')").fetchone() == (False,)


def test_auth_sessions_shared_storage_and_evidence_preserve_payloads(database, runtime_environment):
    from app.services.dataset_scope import build_dataset_scope, dataset_scope_context
    from app.services.finding_workflow import materialize_evidence_finding_cases, read_finding_case
    assert auth_store.initialize_auth_store() == "postgresql"
    auth_store.create_user("runtime@example.test", "local-only-password-123", role="operator")
    assert auth_store.authenticate_user("runtime@example.test", "local-only-password-123")
    first = auth_store.create_session("runtime@example.test")
    assert auth_store.get_user_by_session(first)
    second = auth_store.create_session("runtime@example.test")
    assert auth_store.get_user_by_session(first) is None
    workspace = auth_store.create_workspace("Fixture", created_by="runtime@example.test")
    assert workspace["display_name"] == "Fixture"
    auth_store.revoke_session(session_id=second)
    assert auth_store.get_user_by_session(second) is None
    scope = build_dataset_scope(user_id="runtime@example.test", workspace_id="fixture")
    finding = {"id":"finding-1","headline":"persist exactly","severity":"medium"}
    record = {"run_id":"ddl-evidence","status":"completed", "created_at":datetime.now(UTC).isoformat(),
              "dataset_scope":scope.as_dict(), "evidence_hash":"retained-fixture-hash",
              "finding_identity_snapshot":[finding],"analytical_payload":{"value":1.23456789,"evidence":["unchanged"]}}
    with dataset_scope_context(scope):
        runtime_db.upsert_evidence_run_db(record)
        assert runtime_db.read_evidence_run_db(record["run_id"]) == record
        ids = materialize_evidence_finding_cases(record, evaluate_governance=False)
        assert len(ids) == 1
        assert read_finding_case(ids[0])["evidence"]["finding"] == finding
        runtime_db.upsert_latest_payload("ddl-counter", {"n":1})
        runtime_db.mutate_latest_payload("ddl-counter", lambda p:{"n":p["n"]+1})
        assert runtime_db.read_latest_payload("ddl-counter") == {"n":2}
        runtime_db.record_audit_event(request_id="fixture",actor="runtime",action="qualification",resource_type="evidence",resource_id=record["run_id"],detail={})
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with runtime_db.db_connection() as c:
                c.execute("UPDATE finding_cases SET source_snapshot_json='{}'")
        assert runtime_db.read_evidence_run_db(record["run_id"]) == record
        with pytest.raises(ValueError):
            with runtime_db.db_connection() as c:
                c.execute("INSERT INTO latest_payloads VALUES ('rolled-back', ?, '{}')", (runtime_db.now_iso(),))
                raise ValueError("transaction rollback")
        assert runtime_db.read_latest_payload("rolled-back") is None


def test_telemetry_repository_persistence_and_worker_claim(database, runtime_environment):
    from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
    from app.services.telemetry_repository import PostgreSQLTelemetryRepository, TelemetryRepositoryScope
    from app.services.telemetry_domain import ConnectorType
    scope = TelemetryRepositoryScope(tenant_scope_id="fixture",workspace_id="workspace",
        resource_scope_id=canonical_phase4_resource_scope_id("fixture","workspace"),facility_id="workspace")
    repo = PostgreSQLTelemetryRepository(lambda: psycopg.connect(database["runtime"]))
    connection_id, signal_id = str(uuid.uuid4()), str(uuid.uuid4())
    created = repo.create_connection(scope,connection_id=connection_id,name="Fixture",
        connector_type=ConnectorType.HTTPS_TELEMETRY,safe_config={},timezone_name="UTC",
        polling_interval_seconds=60,actor_id="runtime",audit_event_id=str(uuid.uuid4()))
    assert str(created["id"]) == connection_id
    signals = repo.upsert_external_signals(scope,connection_id=connection_id,
        signals=[dict(signal_id=signal_id,external_tag_id="tag",external_tag_name="Fixture signal",source_unit="c")])
    assert len(signals) == 1
    assert repo.get_connection(scope,connection_id)
    # Disabled connections are not claimed, including by ordinary scheduler startup.
    assert repo.claim_next_due_work(worker_id="qualification",lease_seconds=60,now=datetime.now(UTC)) is None
    from app.services.telemetry_units import conversion_contract
    now = datetime.now(UTC)
    conversion = conversion_contract(source_unit="c",canonical_unit="degC",expected_dimension="temperature")
    concept = "b7f427ba-b036-539e-a527-15ed76bf3b35"
    mapping_id = str(uuid.uuid4())
    repo.save_signal_mapping(scope,mapping_id=mapping_id,event_id=str(uuid.uuid4()),
        connection_id=connection_id,signal_id=signal_id,system_id="system",asset_id=None,
        canonical_concept_id=concept,canonical_signal_name="temperature",source_unit="c",canonical_unit="degC",
        conversion_id=conversion["conversion_id"],conversion_version=conversion["conversion_version"],
        expected_cadence_seconds=60,source_timezone="UTC",provenance="manual",provenance_reason="fixture",
        actor_id="runtime",authority_digest="a"*64,mapped_at=now)
    repo.set_connection_lifecycle(scope,connection_id=connection_id,target_status="validating",actor_id="runtime",enabled=True)
    repo.set_connection_lifecycle(scope,connection_id=connection_id,target_status="connected",actor_id="runtime",enabled=True)
    with psycopg.connect(database["runtime"]) as c:
        c.execute("UPDATE telemetry.data_connections SET next_attempt_at=%s WHERE id=%s", (now,connection_id))
    work = repo.claim_next_due_work(worker_id="qualification",lease_seconds=60,now=datetime.now(UTC))
    assert work is not None
    observation = dict(id=str(uuid.uuid4()),system_id="system",external_signal_id=signal_id,
        mapping_id=mapping_id,mapping_revision=1,canonical_concept_id=concept,canonical_signal_name="temperature",
        external_tag_id="tag",source_timestamp_raw=now.isoformat(),source_timezone="UTC",source_offset="+00:00",
        timestamp_normalization_version="timestamps.v1",observed_at_utc=now,original_value=12.5,
        original_unit="c",normalized_value=12.5,canonical_unit="degC",conversion_id=conversion["conversion_id"],
        conversion_version=conversion["conversion_version"],quality_state="good",ingestion_disposition="accepted",
        analysis_eligible=True,source_record_digest="b"*64,mapping_actor_id="runtime",mapping_mapped_at=now,
        mapping_authority_digest="a"*64,mapping_provenance="manual")
    persisted = repo.persist_ingestion_page(scope,connection_id=connection_id,run_id=work["run_id"],
        lease_token=str(work["lease_token"]),checkpoint_mode="incremental",expected_checkpoint_revision=0,
        cursor_payload={"cursor":"1"},high_water_at=now,observations=[observation],rejections=[])
    assert persisted["accepted"] == 1
    assert persisted["checkpoint_revision"] == 1
    repo.complete_ingestion_work(scope,connection_id=connection_id,run_id=work["run_id"],
        lease_token=str(work["lease_token"]),completed_at=datetime.now(UTC),next_attempt_at=datetime.now(UTC)+timedelta(seconds=60))
    with psycopg.connect(database["runtime"]) as c:
        assert c.execute("SELECT count(*) FROM telemetry.telemetry_audit_events WHERE connection_id=%s",(connection_id,)).fetchone()[0] >= 1
        assert c.execute("SELECT normalized_value FROM telemetry.normalized_observations WHERE id=%s",(observation["id"],)).fetchone() == (12.5,)


@pytest.mark.parametrize("statement", [
    "CREATE TABLE neraium_runtime.forbidden (id INTEGER)",
    "ALTER TABLE neraium_runtime.latest_payloads ADD COLUMN forbidden TEXT",
    "DROP TABLE neraium_runtime.latest_payloads",
    "CREATE SCHEMA forbidden",
    "CREATE ROLE forbidden",
    "CREATE INDEX forbidden ON neraium_runtime.latest_payloads (key)",
    "CREATE FUNCTION neraium_runtime.forbidden() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
    "CREATE SEQUENCE neraium_runtime.forbidden",
    "CREATE TEMP TABLE forbidden (id INTEGER)",
    "CREATE EXTENSION hstore",
    "INSERT INTO neraium_runtime.postgres_runtime_migrations VALUES (999)",
    "DELETE FROM public.auth_schema_migrations",
    "DELETE FROM telemetry.schema_migrations",
])
def test_runtime_ddl_and_ledger_writes_are_denied(database, statement):
    with psycopg.connect(database["runtime"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as denied:
            c.execute(statement)
        assert denied.value.sqlstate == "42501"
        c.rollback()


def test_grants_and_ownership_changes_are_denied(database):
    with psycopg.connect(database["runtime"]) as c:
        for statement in (
            sql.SQL("GRANT {} TO {}").format(sql.Identifier(database["migrator"]),sql.Identifier(database["grantee"])),
            sql.SQL("ALTER TABLE neraium_runtime.latest_payloads OWNER TO {}").format(sql.Identifier(database["role"])),
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege): c.execute(statement)
            c.rollback()
        # PostgreSQL may finish a table GRANT with a warning instead of raising.
        # The security requirement is that it transfers no authority.
        c.execute(sql.SQL("GRANT SELECT ON neraium_runtime.latest_payloads TO {}").format(sql.Identifier(database["grantee"])))
        assert c.execute("SELECT has_table_privilege(%s,'neraium_runtime.latest_payloads','SELECT')",(database["grantee"],)).fetchone() == (False,)
        c.rollback()


def test_schema_verification_succeeds_in_read_only_transactions(database, runtime_environment):
    readonly = make_conninfo(database["runtime"], options="-c default_transaction_read_only=on")
    backend = auth_store._PostgresAuthBackend(readonly)
    backend.ensure_schema()
    for schema,name in (("neraium_runtime","runtime_postgres"),("public","auth_postgres"),("telemetry","telemetry_v2")):
        with psycopg.connect(readonly) as c:
            assert c.execute("SHOW transaction_read_only").fetchone() == ("on",)
            before = postgres_catalog(c,schema)
            verify_postgres(c,schema,name)
            assert postgres_catalog(c,schema) == before


@pytest.mark.parametrize("remove,restore,diagnostic", [
    ("DROP INDEX neraium_runtime.idx_upload_jobs_updated_at",
     "CREATE INDEX idx_upload_jobs_updated_at ON neraium_runtime.upload_jobs (updated_at DESC)","indexes:idx_upload_jobs_updated_at"),
    ("ALTER TABLE neraium_runtime.latest_payloads RENAME TO missing_payloads",
     "ALTER TABLE neraium_runtime.missing_payloads RENAME TO latest_payloads", "tables:latest_payloads"),
    ("ALTER TABLE neraium_runtime.latest_payloads RENAME COLUMN payload_json TO removed_payload",
     "ALTER TABLE neraium_runtime.latest_payloads RENAME COLUMN removed_payload TO payload_json", "column:latest_payloads.payload_json"),
    ("ALTER TABLE neraium_runtime.finding_cases DISABLE TRIGGER trg_finding_cases_no_delete",
     "ALTER TABLE neraium_runtime.finding_cases ENABLE TRIGGER trg_finding_cases_no_delete", "triggers:finding_cases.trg_finding_cases_no_delete"),
])
def test_missing_required_state_refuses_api_worker_and_does_not_repair(database, runtime_environment, remove, restore, diagnostic, monkeypatch):
    with psycopg.connect(database["migration"]) as c: c.execute(remove)
    try:
        for _ in range(2):
            with pytest.raises(SchemaIncompatibilityError,match=diagnostic): runtime_postgres.initialize()
        from app.main import create_app
        from app.entrypoint import run_worker
        with pytest.raises(SchemaIncompatibilityError,match=diagnostic): create_app(runtime_environment)
        with pytest.raises(SchemaIncompatibilityError,match=diagnostic):
            run_worker(replace(runtime_environment,process_role="worker"),shutdown_event=threading.Event())
    finally:
        with psycopg.connect(database["migration"]) as c: c.execute(restore)
    runtime_postgres.initialize()


def test_missing_function_sequence_and_ledger_fail_without_repair(database, runtime_environment):
    # Rollback-only corruption avoids altering fixture sequence values or rows.
    operations = (
        "ALTER FUNCTION neraium_runtime.reject_runtime_mutation() RENAME TO removed_guard",
        "ALTER SEQUENCE neraium_runtime.audit_events_event_id_seq RENAME TO removed_sequence",
        "DELETE FROM neraium_runtime.postgres_runtime_migrations",
        "DROP TRIGGER trg_relationship_lineage_v2_immutable ON telemetry.relationship_lineage_artifacts_v2",
    )
    for operation in operations:
        with psycopg.connect(database["migration"]) as c:
            c.execute(operation)
            schema,name = ("telemetry","telemetry_v2") if "telemetry." in operation else ("neraium_runtime","runtime_postgres")
            for _ in range(2):
                with pytest.raises(SchemaIncompatibilityError): verify_postgres(c,schema,name)
            c.rollback()


def test_prechange_shared_schema_has_explicit_idempotent_migration(database):
    from db.migrations.runtime_postgres import apply
    with psycopg.connect(database["migration"]) as c:
        before=postgres_catalog(c,"neraium_runtime")
        apply(c)
        assert postgres_catalog(c,"neraium_runtime") == before


@pytest.mark.parametrize("remove,restore", [
    ("ALTER TABLE telemetry.schema_migrations RENAME TO removed_migrations",
     "ALTER TABLE telemetry.removed_migrations RENAME TO schema_migrations"),
    ("ALTER TABLE telemetry.schema_migrations RENAME COLUMN migration_id TO removed_id",
     "ALTER TABLE telemetry.schema_migrations RENAME COLUMN removed_id TO migration_id"),
])
def test_missing_telemetry_ledger_reports_incompatibility_without_repair(database, runtime_environment, remove, restore):
    from app.main import create_app
    from app.entrypoint import run_worker
    with psycopg.connect(database["migration"]) as c:
        c.execute(remove)
        before = postgres_catalog(c, "telemetry")
    try:
        for _ in range(2):
            with pytest.raises(SchemaIncompatibilityError, match="schema_incompatible:telemetry:migration_state"):
                build_telemetry_runtime(runtime_environment).verify_readiness()
        with pytest.raises(SchemaIncompatibilityError, match="schema_incompatible:telemetry:migration_state"):
            with TestClient(create_app(runtime_environment), base_url="https://testserver"):
                pass
        with pytest.raises(SchemaIncompatibilityError, match="schema_incompatible:telemetry:migration_state"):
            run_worker(replace(runtime_environment, process_role="worker"), shutdown_event=threading.Event())
        with psycopg.connect(database["migration"]) as c:
            assert postgres_catalog(c, "telemetry") == before
    finally:
        with psycopg.connect(database["migration"]) as c:
            c.execute(restore)
