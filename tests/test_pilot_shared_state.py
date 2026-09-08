"""Focused real-PostgreSQL contracts; set NERAIUM_TEST_RUNTIME_POSTGRES_DSN."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import os
import subprocess
import sys
import uuid

import psycopg
from psycopg import sql
import pytest

from app.services import auth_store, runtime_db, runtime_postgres
from app.services.analysis_provenance import canonical_digest
from app.services.dataset_scope import dataset_scope_context
from datasets.verification_consequence import RUN_ID, SCOPE, seed_fixture


@pytest.fixture
def postgres_runtime(monkeypatch):
    dsn = os.getenv("NERAIUM_TEST_RUNTIME_POSTGRES_DSN")
    if not dsn:
        pytest.skip("requires isolated PostgreSQL test database")
    schema = "pilot_test_" + uuid.uuid4().hex
    monkeypatch.setenv("NERAIUM_RUNTIME_DATABASE_URL", dsn)
    monkeypatch.setattr(runtime_postgres, "_SCHEMA", schema)
    monkeypatch.setattr(runtime_postgres, "_initialized", set())
    runtime_db.init_runtime_db()
    try:
        yield dsn, schema
    finally:
        with psycopg.connect(dsn) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.mark.integration
def test_shared_payload_restart_concurrent_mutation_and_pure_reads(postgres_runtime, monkeypatch, tmp_path):
    dsn, schema = postgres_runtime
    runtime_db.upsert_latest_payload("counter", 0)
    script = """
from pathlib import Path
import sys
from app.services import runtime_db, runtime_postgres
runtime_postgres._SCHEMA = sys.argv[1]
runtime_db.configure_runtime_dir(Path(sys.argv[2]))
for _ in range(5):
    runtime_db.mutate_latest_payload('counter', lambda n: n + 1)
"""
    def worker(index):
        subprocess.run([sys.executable, "-c", script, schema, str(tmp_path / str(index))], check=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(worker, (1, 2)))
    assert runtime_db.read_latest_payload_pure("counter") == 10
    monkeypatch.setattr(runtime_postgres, "initialize", lambda: pytest.fail("pure read initialized schema"))
    assert runtime_db.list_latest_payloads_prefix_pure("count") == [10]
    with runtime_postgres.connect(readonly=True) as connection:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            connection.execute("UPDATE latest_payloads SET payload_json = '99'")


@pytest.mark.integration
def test_postgres_replay_preserves_exact_artifacts_and_scope(postgres_runtime, client, monkeypatch, tmp_path):
    from test_verification_consequence import smoke_headers, test_fixture_replay_persistence_apis_and_frontend_projection
    # Reuse the complete HTTP/hash/no-write assertion from PR #130 against PG.
    headers = smoke_headers.__wrapped__(monkeypatch)
    test_fixture_replay_persistence_apis_and_frontend_projection(client, monkeypatch, headers, "shared", tmp_path)


@pytest.mark.integration
def test_postgres_auth_restart_revocation_activation_and_concurrent_startup(postgres_runtime, monkeypatch):
    dsn, schema = postgres_runtime
    class Backend(auth_store._PostgresAuthBackend):
        @contextmanager
        def _connect(self):
            with psycopg.connect(dsn) as connection:
                connection.execute(sql.SQL("SET LOCAL search_path TO {}, pg_catalog").format(sql.Identifier(schema)))
                yield connection
    # Use another schema because the runtime has deprecated auth compatibility tables.
    auth_schema = schema + "_auth"
    with psycopg.connect(dsn) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(auth_schema)))
    schema = auth_schema
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda _: Backend(dsn).ensure_schema(), range(2)))
        backend = Backend(dsn)
        monkeypatch.setattr(auth_store, "_get_backend", lambda: backend)
        monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_EMAIL", "durable@example.com")
        monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_PASSWORD", "local-test-only-password")
        monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_RESET_PASSWORD", "false")
        auth_store._ensure_bootstrap_admin(backend)
        first = auth_store.create_session("durable@example.com")
        backend = Backend(dsn)  # Fresh API instance has no user/session cache.
        assert auth_store.get_user_by_session(first)
        def login(index):
            session = f"concurrent-{index}"
            Backend(dsn).replace_active_session({"session_id": session, "email": "durable@example.com"})
            return session
        with ThreadPoolExecutor(max_workers=2) as executor:
            sessions = list(executor.map(login, range(2)))
        assert sum(auth_store.get_user_by_session(s) is not None for s in sessions) == 1
        assert auth_store.get_user_by_session(first) is None
        auth_store.deactivate_user("durable@example.com")
        backend = Backend(dsn)
        auth_store._ensure_bootstrap_admin(backend)
        assert not backend.read_user("durable@example.com")["is_active"]
        assert all(auth_store.get_user_by_session(s) is None for s in sessions)
        with pytest.raises(ValueError, match="inactive"):
            backend.replace_active_session({"session_id": "racing-login", "email": "durable@example.com"})
        auth_store.activate_user("durable@example.com")
        assert all(auth_store.get_user_by_session(s) is None for s in sessions)
        new_session = auth_store.create_session("durable@example.com")
        auth_store.revoke_session(session_id=new_session)
        backend = Backend(dsn)
        assert auth_store.get_user_by_session(new_session) is None
    finally:
        with psycopg.connect(dsn) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(auth_schema)))


@pytest.mark.integration
def test_snapshot_copy_is_verbatim_idempotent_and_conflicts_roll_back(postgres_runtime, tmp_path):
    from app.services.runtime_postgres_import import import_snapshot
    snapshot = runtime_db.DB_PATH  # Full existing SQLite schema from isolate_runtime.
    import sqlite3
    with sqlite3.connect(snapshot) as connection:
        connection.execute("INSERT INTO latest_payloads VALUES ('evidence', '2026-09-01', ?)", ('{ "hash": "untouched", "consequence": null }',))
        connection.execute("INSERT INTO audit_events (event_id, created_at, actor, action, resource_type, detail_json) VALUES (400, '2026-09-01', 'operator', 'review', 'evidence', '{}')")
    before = snapshot.read_bytes()
    assert import_snapshot(snapshot)["latest_payloads"] == 1
    assert runtime_db.read_latest_payload_pure("evidence") is None
    assert import_snapshot(snapshot, apply=True)["latest_payloads"] == 1
    assert import_snapshot(snapshot, apply=True)["latest_payloads"] == 1
    with runtime_postgres.connect(readonly=True) as connection:
        assert connection.execute("SELECT payload_json FROM latest_payloads WHERE key = 'evidence'").fetchone()["payload_json"] == '{ "hash": "untouched", "consequence": null }'
    assert snapshot.read_bytes() == before
    runtime_db.record_audit_event(request_id=None, actor="operator", action="review", resource_type="evidence", resource_id="new", detail={})
    with runtime_postgres.connect(readonly=True) as connection:
        assert connection.execute("SELECT MAX(event_id) AS id FROM audit_events").fetchone()["id"] == 401
    with sqlite3.connect(snapshot) as connection:
        connection.execute("INSERT INTO latest_payloads VALUES ('new', '2026-09-02', '{}')")
        connection.execute("DELETE FROM latest_payloads WHERE key = 'evidence'")
        connection.execute("INSERT INTO latest_payloads VALUES ('evidence', '2026-09-01', '{}')")
    with pytest.raises(ValueError, match="Conflicting runtime history"):
        import_snapshot(snapshot, apply=True)
    assert runtime_db.read_latest_payload_pure("new") is None


@pytest.mark.integration
def test_postgres_finding_and_governance_immutability(postgres_runtime):
    from app.services.finding_workflow import read_finding_case
    from test_runtime_governance import test_real_analytical_output_lineage_persistence_and_immutable_decision
    from app.governance.authority_store import RuntimeAuthorityDecisionStore
    test_real_analytical_output_lineage_persistence_and_immutable_decision(RuntimeAuthorityDecisionStore())
    seed_fixture()
    with dataset_scope_context(SCOPE):
        evidence = runtime_db.read_evidence_run_db(RUN_ID)
        before = canonical_digest(evidence)
        with runtime_postgres.connect(readonly=True) as connection:
            case = connection.execute("SELECT finding_id FROM finding_cases LIMIT 1").fetchone()
        assert read_finding_case(case["finding_id"])
        for statement in (
            "UPDATE finding_cases SET source_snapshot_json = '{}'",
            "DELETE FROM finding_cases",
        ):
            with pytest.raises(psycopg.errors.CheckViolation):
                with runtime_db.db_connection() as connection:
                    connection.execute(statement)
        assert canonical_digest(runtime_db.read_evidence_run_db(RUN_ID)) == before


def test_runtime_model_reads_refresh_other_worker_updates():
    from app.engine.sii.behavioral_model_store import RuntimeBehavioralModelStore
    from test_behavioral_model_store import _model, _model_id, _scope
    state = {}
    def reader(key):
        return deepcopy(state.get(key))
    def writer(key, value):
        state[key] = deepcopy(value)
    first = RuntimeBehavioralModelStore(reader=reader, writer=writer)
    second = RuntimeBehavioralModelStore(reader=reader, writer=writer)
    scope = _scope()
    model_id = _model_id(scope, "shared")
    assert second.load_model(scope, model_id) is None
    first.create_model(scope, _model(model_id), source_run_id="run-1")
    assert second.load_model(scope, model_id)["model_version"] == "v1"
    first.save_model(scope, _model(model_id, "v2"), source_run_id="run-2")
    assert second.load_model(scope, model_id)["model_version"] == "v2"


def test_shared_sii_state_does_not_fall_back_or_hide_write_failure(monkeypatch, tmp_path):
    from app.services import sii_runner
    monkeypatch.setenv("NERAIUM_RUNTIME_DATABASE_URL", "postgresql://configured")
    stale = tmp_path / "stale.json"
    stale.write_text('{"stale": true}')
    monkeypatch.setattr(sii_runner, "STATE_PATH", stale)
    def unavailable(*args):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(sii_runner, "read_latest_payload", unavailable)
    monkeypatch.setattr(sii_runner, "upsert_latest_payload", unavailable)
    with pytest.raises(RuntimeError, match="database unavailable"):
        sii_runner.read_latest_sii_state()
    with pytest.raises(RuntimeError, match="database unavailable"):
        sii_runner.write_latest_sii_state({"new": True})
    assert stale.read_text() == '{"stale": true}'


@pytest.mark.integration
def test_shared_queue_claims_once_and_restart_preserves_active_worker(postgres_runtime, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from test_upload_queue_scope_routing import _FakeS3Client, _configure_shared_runtime
    fake = _FakeS3Client()
    _configure_shared_runtime(monkeypatch, fake)
    with dataset_scope_context(SCOPE):
        runtime_db.enqueue_upload_job("pilot-queue")
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: runtime_db.claim_next_upload_job_record(), range(2)))
    assert sum(claim is not None for claim in claims) == 1
    assert runtime_db.read_upload_queue_job("pilot-queue")["attempts"] == 1
    recovered = []
    def publish(records):
        recovered.extend(records)
        return {record["job_id"]: "failed" for record in records}
    monkeypatch.setattr(runtime_db, "_publish_interrupted_upload_status", publish)
    assert runtime_db.clear_stale_processing_queue_jobs() == 0
    assert recovered == []
    record = runtime_db.read_upload_queue_job("pilot-queue")
    record["updated_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    runtime_db._write_s3_queue_job(record)
    assert runtime_db.clear_stale_processing_queue_jobs() == 1
    assert recovered[0]["job_id"] == "pilot-queue"
