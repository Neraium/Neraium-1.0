from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.engine.sii.behavioral_model_contract import (
    AuthenticatedPhase4Scope,
    canonical_phase4_resource_scope_id,
)
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.phase4_scope import build_telemetry_server_bound_system_identity
from app.services.telemetry_repository import (
    PostgreSQLTelemetryRepository,
    TelemetryCheckpointConflict,
    TelemetryMappingConflict,
    TelemetryRepositoryError,
)
from app.services.telemetry_result_artifact import CanonicalResultArtifact


class _Cursor:
    def __init__(self, connection: "_Connection") -> None:
        self.connection = connection
        self.rowcount = 1
        self.description: list[Any] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.connection.statements.append((sql, params))

    def fetchone(self) -> Any:
        return self.connection.fetches.pop(0) if self.connection.fetches else None

    def fetchall(self) -> list[Any]:
        return list(self.connection.fetches.pop(0)) if self.connection.fetches else []


class _Connection:
    def __init__(self, fetches: list[Any]) -> None:
        self.fetches = list(fetches)
        self.statements: list[tuple[str, object]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        return None


class _UniqueRetryError(Exception):
    sqlstate = "23505"


class _UniqueRetryCursor(_Cursor):
    def execute(self, sql: str, params: object = None) -> None:
        super().execute(sql, params)
        if "INSERT INTO telemetry.ingestion_runs" in sql and "source_run_id" in sql:
            raise _UniqueRetryError("constraint detail")


class _UniqueRetryConnection(_Connection):
    def cursor(self) -> _UniqueRetryCursor:
        return _UniqueRetryCursor(self)


class _UniqueBackfillCursor(_Cursor):
    def execute(self, sql: str, params: object = None) -> None:
        super().execute(sql, params)
        if "INSERT INTO telemetry.ingestion_runs" in sql:
            raise _UniqueRetryError("constraint detail")


class _UniqueBackfillConnection(_Connection):
    def cursor(self) -> _UniqueBackfillCursor:
        return _UniqueBackfillCursor(self)


@pytest.fixture
def scope() -> TelemetryScopeRef:
    return TelemetryScopeRef(
        tenant_scope_id="tenant-a",
        workspace_id="facility-a",
        resource_scope_id=canonical_phase4_resource_scope_id("tenant-a", "facility-a"),
        facility_id="facility-a",
    )


def _prepared_observation(now: datetime) -> dict[str, Any]:
    return {
        "id": "00000000-0000-0000-0000-000000000010",
        "system_id": "system-a",
        "asset_id": None,
        "external_signal_id": "00000000-0000-0000-0000-000000000011",
        "mapping_id": "00000000-0000-0000-0000-000000000012",
        "mapping_revision": 1,
        "mapping_actor_id": "operator@example.test",
        "mapping_mapped_at": now,
        "mapping_authority_digest": "b" * 64,
        "mapping_provenance": "manual",
        "canonical_concept_id": "00000000-0000-0000-0000-000000000013",
        "canonical_signal_name": "flow_rate",
        "external_tag_id": "tag-1",
        "provider_event_id": "event-1",
        "source_timestamp_raw": now.isoformat(),
        "source_timezone": "UTC",
        "source_offset": "+00:00",
        "timestamp_normalization_version": "timestamps.v1",
        "observed_at_utc": now,
        "original_value": 12.0,
        "original_unit": "gpm",
        "normalized_value": 0.000757,
        "canonical_unit": "m3/s",
        "conversion_id": "gpm_to_m3_s",
        "conversion_version": "units.v1",
        "quality_state": "good",
        "ingestion_disposition": "accepted",
        "analysis_eligible": True,
        "reason_codes": [],
        "source_record_digest": "a" * 64,
        "source_metadata": {},
    }


def test_global_claim_reconstructs_scope_and_assigns_run_and_lease_atomically(
    scope: TelemetryScopeRef,
) -> None:
    connection_id = "00000000-0000-0000-0000-000000000001"
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _Connection(
        [
            {
                "id": connection_id,
                **scope.as_public_dict(),
                "connector_type": "https_telemetry",
                "safe_config": {},
                "timezone": "UTC",
                "polling_interval_seconds": 60,
                "pending_run_id": None,
                "range_start": None,
                "range_end": None,
            },
            {"lease_expires_at": now + timedelta(seconds=120)},
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)

    result = repository.claim_next_due_work(worker_id="worker-a", now=now)

    assert result is not None
    assert result["scope"] == scope
    assert result["connection_id"] == connection_id
    assert result["run_mode"] == "incremental"
    assert result["checkpoint_mode"] == "incremental"
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "FOR UPDATE OF c SKIP LOCKED" in sql
    assert "AND c.next_attempt_at <= %s" in sql
    assert "pending.id IS NOT NULL OR c.next_attempt_at" not in sql
    assert "INSERT INTO telemetry.ingestion_runs" in sql
    assert "tenant_scope_id = %s" in sql  # assignment after scope validation
    assert connection.commits == 1


def test_global_claim_quarantines_legacy_scope_without_assigning_a_lease() -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _Connection(
        [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "tenant_scope_id": "",
                "workspace_id": "legacy-global",
                "resource_scope_id": "legacy",
                "facility_id": "legacy-global",
                "pending_run_id": None,
            }
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)

    assert repository.claim_next_due_work(worker_id="worker-a", now=now) is None

    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "telemetry_scope_invalid" in sql
    assert "lease_owner = %s" not in sql
    assert "INSERT INTO telemetry.ingestion_runs" not in sql
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_global_claim_skips_invalid_scope_and_claims_next_valid_connection(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    valid_connection_id = "00000000-0000-0000-0000-000000000002"
    connection = _Connection(
        [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "tenant_scope_id": "",
                "workspace_id": "legacy-global",
                "resource_scope_id": "legacy",
                "facility_id": "legacy-global",
                "pending_run_id": None,
            },
            {
                "id": valid_connection_id,
                **scope.as_public_dict(),
                "connector_type": "https_telemetry",
                "safe_config": {},
                "timezone": "UTC",
                "polling_interval_seconds": 60,
                "pending_run_id": None,
                "range_start": None,
                "range_end": None,
            },
            {"lease_expires_at": now + timedelta(seconds=120)},
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)

    claimed = repository.claim_next_due_work(worker_id="worker-a", now=now)

    assert claimed is not None
    assert claimed["connection_id"] == valid_connection_id
    assert claimed["scope"] == scope
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "telemetry_scope_invalid" in sql
    assert "INSERT INTO telemetry.ingestion_runs" in sql
    assert connection.commits == 1


def test_persist_page_keeps_writes_run_counters_and_checkpoint_cas_atomic(
    scope: TelemetryScopeRef,
) -> None:
    connection = _Connection([("lease",), None])
    repository = PostgreSQLTelemetryRepository(lambda: connection)

    with pytest.raises(TelemetryCheckpointConflict):
        repository.persist_ingestion_page(
            scope,
            connection_id="00000000-0000-0000-0000-000000000001",
            run_id="00000000-0000-0000-0000-000000000002",
            lease_token="00000000-0000-0000-0000-000000000003",
            checkpoint_mode="incremental",
            expected_checkpoint_revision=3,
            cursor_payload={"cursor": "page-4"},
            high_water_at=datetime(2026, 8, 25, tzinfo=UTC),
            observations=(),
            rejections=(),
        )

    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "r.lease_token = c.lease_token" in sql
    assert "cp.revision = %s" in sql
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_persist_page_uses_bulk_recordsets_and_snapshots_mapping_authority(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    observation = {
        "id": "00000000-0000-0000-0000-000000000010",
        "system_id": "system-a",
        "asset_id": None,
        "external_signal_id": "00000000-0000-0000-0000-000000000011",
        "mapping_id": "00000000-0000-0000-0000-000000000012",
        "mapping_revision": 1,
        "mapping_actor_id": "operator@example.test",
        "mapping_mapped_at": now,
        "mapping_authority_digest": "b" * 64,
        "mapping_provenance": "manual",
        "canonical_concept_id": "00000000-0000-0000-0000-000000000013",
        "canonical_signal_name": "flow_rate",
        "external_tag_id": "tag-1",
        "provider_event_id": "event-1",
        "source_timestamp_raw": now.isoformat(),
        "source_timezone": "UTC",
        "source_offset": "+00:00",
        "timestamp_normalization_version": "timestamps.v1",
        "observed_at_utc": now,
        "original_value": 12.0,
        "original_unit": "gpm",
        "normalized_value": 0.000757,
        "canonical_unit": "m3/s",
        "conversion_id": "gpm_to_m3_s",
        "conversion_version": "units.v1",
        "quality_state": "good",
        "ingestion_disposition": "accepted",
        "analysis_eligible": True,
        "reason_codes": [],
        "source_record_digest": "a" * 64,
        "source_metadata": {},
    }
    connection = _Connection(
        [
            ("lease",),
            (True,),
            [
                {
                    "source_record_digest": "a" * 64,
                    "ingestion_disposition": "accepted",
                    "external_signal_id": observation["external_signal_id"],
                    "observed_at_utc": now,
                    "quality_state": "good",
                }
            ],
            (4,),
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    result = repository.persist_ingestion_page(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        lease_token="00000000-0000-0000-0000-000000000003",
        checkpoint_mode="incremental",
        expected_checkpoint_revision=3,
        cursor_payload={"cursor": "page-4"},
        high_water_at=now,
        observations=[observation],
        rejections=(),
        checkpoint_before_digest="c" * 64,
        checkpoint_after_digest="d" * 64,
    )

    assert result == {
        "checkpoint_revision": 4,
        "accepted": 1,
        "rejected": 0,
        "duplicate": 0,
        "out_of_order": 0,
    }
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "jsonb_to_recordset" in sql
    assert "mapping_provenance" in sql
    assert "m.authority_digest" in sql
    assert "m.mapped_by = x.mapping_actor_id" in sql
    assert "m.mapped_at = x.mapping_mapped_at" in sql
    assert "ON CONFLICT DO NOTHING" in sql
    assert "pages_processed = r.pages_processed + 1" in sql
    assert "checkpoint_before_digest = COALESCE" in sql
    assert "checkpoint_after_digest = COALESCE" in sql
    counter_params = connection.statements[-1][1]
    assert counter_params is not None
    assert "c" * 64 in counter_params
    assert "d" * 64 in counter_params


def test_persist_page_preserves_stale_and_missing_rejection_quality(
    scope: TelemetryScopeRef,
) -> None:
    connection = _Connection([("lease",), (1,)])
    repository = PostgreSQLTelemetryRepository(lambda: connection)

    result = repository.persist_ingestion_page(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        lease_token="00000000-0000-0000-0000-000000000003",
        checkpoint_mode="incremental",
        expected_checkpoint_revision=0,
        cursor_payload={},
        high_water_at=datetime(2026, 8, 25, tzinfo=UTC),
        observations=(),
        rejections=(
            {
                "source_record_digest": "a" * 64,
                "quality_state": "stale",
                "reason_code": "reported_quality_stale",
                "disposition": "rejected",
            },
            {
                "source_record_digest": "b" * 64,
                "quality_state": "missing",
                "reason_code": "reported_quality_missing",
                "disposition": "rejected",
            },
        ),
    )

    assert result["rejected"] == 2
    rejection_statement = next(
        (statement, params)
        for statement, params in connection.statements
        if "INSERT INTO telemetry.observation_rejections" in statement
    )
    encoded = str(rejection_statement[1][0])
    assert '"quality_state":"stale"' in encoded
    assert '"quality_state":"missing"' in encoded


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("canonical_unit", "bar"),
        ("conversion_id", "psi_to_bar"),
        ("conversion_version", "units.v999"),
        ("original_unit", "psi"),
    ],
)
def test_persist_page_rejects_tampered_conversion_lineage(
    scope: TelemetryScopeRef,
    field: str,
    tampered_value: str,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    observation = _prepared_observation(now)
    observation[field] = tampered_value
    connection = _Connection([("lease",), (False,)])
    repository = PostgreSQLTelemetryRepository(lambda: connection)

    with pytest.raises(
        TelemetryMappingConflict,
        match="telemetry_ingestion_mapping_snapshot_conflict",
    ):
        repository.persist_ingestion_page(
            scope,
            connection_id="00000000-0000-0000-0000-000000000001",
            run_id="00000000-0000-0000-0000-000000000002",
            lease_token="00000000-0000-0000-0000-000000000003",
            checkpoint_mode="incremental",
            expected_checkpoint_revision=0,
            cursor_payload={},
            high_water_at=now,
            observations=[observation],
            rejections=(),
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "INSERT INTO telemetry.normalized_observations" not in sql


def test_health_inputs_use_only_incremental_checkpoint_for_worker_progress(
    scope: TelemetryScopeRef,
) -> None:
    connection = _Connection([None])
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    repository.load_connection_health_inputs(
        scope, connection_id="00000000-0000-0000-0000-000000000001"
    )
    sql = connection.statements[0][0]
    assert "FILTER (WHERE cp.mode = 'incremental')" in sql


def test_transient_failure_backoff_is_bounded_requeues_same_run_and_releases_lease(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _Connection(
        [
            {"retry_count": 8, "mode": "backfill",
             "range_start": now - timedelta(days=1), "range_end": now},
            {"id": "00000000-0000-0000-0000-000000000001", "retry_count": 9,
             "next_attempt_at": now + timedelta(days=1), "lifecycle_status": "degraded"},
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    result = repository.record_ingestion_failure(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        lease_token="00000000-0000-0000-0000-000000000003",
        failed_at=now,
        error_code="provider_unavailable",
        retry_after_seconds=999_999,
    )
    assert result["retry_count"] == 9
    assert result["status"] == "pending"
    params = connection.statements[-1][1]
    assert params is not None
    assert now < params[1] <= now + timedelta(days=1)
    assert "lease_owner = NULL" in connection.statements[-1][0]
    run_sql, run_params = connection.statements[1]
    assert "lease_token = NULL" in run_sql
    assert run_params is not None and run_params[0] == "pending"
    assert "telemetry.telemetry_audit_events" not in "\n".join(
        statement for statement, _ in connection.statements
    )


def test_run_and_error_lists_are_scoped_and_offset_bounded(scope: TelemetryScopeRef) -> None:
    first = _Connection([[{"id": "run"}]])
    second = _Connection([[{"id": "error"}]])
    connections = [first, second]
    repository = PostgreSQLTelemetryRepository(lambda: connections.pop(0))
    repository.list_ingestion_runs(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        limit=50,
        offset=20,
    )
    repository.list_ingestion_errors(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        limit=50,
        offset=20,
    )
    for connection in (first, second):
        sql, params = connection.statements[0]
        assert "resource_scope_id = %s" in sql
        assert "tenant_scope_id = %s" in sql
        assert "LIMIT %s OFFSET %s" in sql
        assert params is not None and params[-2:] == (50, 20)


def test_create_backfill_is_due_and_audited_in_same_transaction(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _Connection([("connection",)])
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    result = repository.create_backfill_run(
        scope,
        run_id="00000000-0000-0000-0000-000000000020",
        connection_id="00000000-0000-0000-0000-000000000001",
        range_start=now - timedelta(days=1),
        range_end=now,
        actor_id="operator@example.test",
        requested_at=now,
    )
    assert result["actor_id"] == "operator@example.test"
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "'backfill', 'pending'" in sql
    assert "DELETE FROM telemetry.connection_checkpoints" in sql
    assert "cp.mode = 'backfill'" in sql
    assert "next_attempt_at = %s" in sql
    assert "retry_count = 0" in sql
    assert "telemetry.telemetry_audit_events" in sql
    assert connection.commits == 1


def test_rejected_overlapping_backfill_does_not_reset_checkpoint(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _UniqueBackfillConnection([("connection",)])
    repository = PostgreSQLTelemetryRepository(lambda: connection)

    with pytest.raises(TelemetryRepositoryError, match="telemetry_backfill_already_active"):
        repository.create_backfill_run(
            scope,
            run_id="00000000-0000-0000-0000-000000000020",
            connection_id="00000000-0000-0000-0000-000000000001",
            range_start=now - timedelta(days=1),
            range_end=now,
            actor_id="operator@example.test",
            requested_at=now,
        )

    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "DELETE FROM telemetry.connection_checkpoints" not in sql
    assert connection.rollbacks == 1


def test_retry_creates_retry_mode_preserves_bounds_and_audits_atomically(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    start = now - timedelta(days=1)
    connection = _Connection(
        [{
            "connection_id": "00000000-0000-0000-0000-000000000001",
            "mode": "backfill",
            "status": "failed",
            "range_start": start,
            "range_end": now,
        }]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    result = repository.retry_ingestion_run(
        scope,
        run_id="00000000-0000-0000-0000-000000000020",
        new_run_id="00000000-0000-0000-0000-000000000021",
        actor_id="operator@example.test",
        requested_at=now,
    )
    assert result["mode"] == "retry"
    assert result["range_start"] == start
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "r.mode IN ('incremental', 'backfill', 'retry')" in sql
    assert "'retry'," in sql
    assert "source_run_id" in sql
    assert "DELETE FROM telemetry.connection_checkpoints" in sql
    assert "cp.mode = 'backfill'" in sql
    assert "next_attempt_at = %s" in sql
    assert "ingestion_retry_requested" in str(connection.statements[-1][1])
    assert connection.commits == 1


def test_active_retry_for_same_source_is_rejected_without_constraint_detail(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _UniqueRetryConnection(
        [{
            "connection_id": "00000000-0000-0000-0000-000000000001",
            "mode": "incremental", "status": "failed",
            "range_start": None, "range_end": None,
        }]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    with pytest.raises(TelemetryRepositoryError, match="telemetry_retry_already_active") as raised:
        repository.retry_ingestion_run(
            scope,
            run_id="00000000-0000-0000-0000-000000000020",
            actor_id="operator@example.test",
            requested_at=now,
        )
    assert "constraint" not in str(raised.value)
    assert connection.rollbacks == 1


def test_rejected_bounded_retry_does_not_reset_checkpoint(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _UniqueRetryConnection(
        [{
            "connection_id": "00000000-0000-0000-0000-000000000001",
            "mode": "backfill", "status": "failed",
            "range_start": now - timedelta(days=1), "range_end": now,
        }]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)

    with pytest.raises(TelemetryRepositoryError, match="telemetry_retry_already_active"):
        repository.retry_ingestion_run(
            scope,
            run_id="00000000-0000-0000-0000-000000000020",
            actor_id="operator@example.test",
            requested_at=now,
        )

    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "DELETE FROM telemetry.connection_checkpoints" not in sql
    assert connection.rollbacks == 1


def test_explicit_schedule_resets_retry_budget(scope: TelemetryScopeRef) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _Connection([])
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    assert repository.schedule_connection_now(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        requested_at=now,
    )
    assert "retry_count = 0" in connection.statements[0][0]


def test_continuation_requeues_same_run_and_releases_lease(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _Connection(
        [
            {"mode": "backfill", "range_start": now - timedelta(days=1), "range_end": now},
            {"id": "00000000-0000-0000-0000-000000000001", "next_attempt_at": now},
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    result = repository.continue_ingestion_work(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        lease_token="00000000-0000-0000-0000-000000000003",
        continued_at=now,
        next_attempt_at=now,
    )
    assert result["status"] == "pending"
    assert result["run_id"] == "00000000-0000-0000-0000-000000000002"
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "SET status = 'pending'" in sql
    assert "finished_at" not in sql
    assert "lease_owner = NULL" in sql


def test_terminal_backfill_completion_is_audited_with_safe_counts(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _Connection(
        [
            {
                "status": "partial",
                "mode": "backfill", "range_start": now - timedelta(days=1),
                "range_end": now, "audit_actor": "operator@example.test",
                "pages_processed": 2, "observations_received": 5,
                "observations_accepted": 4, "observations_rejected": 1,
                "observations_duplicate": 0,
            },
            {"id": "00000000-0000-0000-0000-000000000001",
             "lifecycle_status": "connected", "next_attempt_at": now + timedelta(minutes=5)},
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    result = repository.complete_ingestion_work(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        lease_token="00000000-0000-0000-0000-000000000003",
        completed_at=now,
        next_attempt_at=now + timedelta(minutes=5),
    )
    assert result["status"] == "partial"
    completion_sql, completion_params = connection.statements[0]
    assert "r.observations_rejected > 0" in completion_sql
    assert "latency_ms" in completion_sql
    assert completion_params is not None and completion_params[0] is False
    audit_sql, audit_params = connection.statements[-1]
    assert "telemetry.telemetry_audit_events" in audit_sql
    assert audit_params is not None and "backfill_completed" in audit_params
    assert "operator@example.test" in audit_params


def test_terminal_backfill_failure_is_audited_with_safe_error_code(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _Connection(
        [
            {
                "retry_count": 0, "mode": "retry",
                "range_start": now - timedelta(days=1), "range_end": now,
                "audit_actor": "operator@example.test", "pages_processed": 1,
                "observations_received": 2, "observations_accepted": 1,
                "observations_rejected": 1, "observations_duplicate": 0,
            },
            {"id": "00000000-0000-0000-0000-000000000001", "retry_count": 1,
             "next_attempt_at": now + timedelta(seconds=30), "lifecycle_status": "degraded"},
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    repository.record_ingestion_failure(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        lease_token="00000000-0000-0000-0000-000000000003",
        failed_at=now,
        error_code="provider_unavailable",
        retryable=False,
    )
    audit_sql, audit_params = connection.statements[-1]
    assert "telemetry.telemetry_audit_events" in audit_sql
    assert audit_params is not None and "backfill_failed" in audit_params
    assert "provider_unavailable" in str(audit_params[-1])


def test_retry_exhaustion_terminalizes_run_and_stops_scheduling(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _Connection(
        [
            {"retry_count": 9, "mode": "incremental", "range_start": None,
             "range_end": None, "audit_actor": "telemetry-worker"},
            {"id": "00000000-0000-0000-0000-000000000001", "retry_count": 10,
             "next_attempt_at": None, "lifecycle_status": "error"},
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    result = repository.record_ingestion_failure(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        lease_token="00000000-0000-0000-0000-000000000003",
        failed_at=now,
        error_code="provider_unavailable",
        retryable=True,
    )
    assert result["status"] == "failed"
    run_sql, run_params = connection.statements[1]
    assert "latency_ms" in run_sql
    assert run_params is not None and run_params[0] == "failed"
    connection_params = connection.statements[2][1]
    assert connection_params is not None and connection_params[1] is None


def test_transient_retry_uses_injected_bounded_full_jitter_and_keeps_checkpoint(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _Connection(
        [
            {"retry_count": 2, "mode": "backfill",
             "range_start": now - timedelta(days=1), "range_end": now},
            {"id": "00000000-0000-0000-0000-000000000001", "retry_count": 3,
             "next_attempt_at": now + timedelta(seconds=30),
             "lifecycle_status": "degraded"},
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)

    result = repository.record_ingestion_failure(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        lease_token="00000000-0000-0000-0000-000000000003",
        failed_at=now,
        error_code="provider_unavailable",
        retry_jitter=0.25,
    )

    assert result["status"] == "pending"
    connection_params = connection.statements[2][1]
    assert connection_params is not None
    assert connection_params[1] == now + timedelta(seconds=30)
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "DELETE FROM telemetry.connection_checkpoints" not in sql


@pytest.mark.parametrize("run_mode", ["incremental", "backfill"])
def test_expired_running_work_recovers_same_run(
    scope: TelemetryScopeRef, run_mode: str
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    run_id = "00000000-0000-0000-0000-000000000030"
    connection = _Connection(
        [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                **scope.as_public_dict(),
                "connector_type": "https_telemetry", "safe_config": {},
                "timezone": "UTC", "polling_interval_seconds": 60,
                "pending_run_id": run_id, "pending_mode": run_mode,
                "pending_status": "running",
                "range_start": now - timedelta(days=1) if run_mode == "backfill" else None,
                "range_end": now if run_mode == "backfill" else None,
            },
            {"lease_expires_at": now + timedelta(seconds=120)},
            {"id": run_id},
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    result = repository.claim_next_due_work(worker_id="worker-recovery", now=now)
    assert result is not None and result["run_id"] == run_id
    assert result["run_mode"] == run_mode
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "r.status IN ('pending', 'running')" in sql
    assert "INSERT INTO telemetry.ingestion_runs" not in sql


def test_live_lease_is_not_claimed() -> None:
    connection = _Connection([None])
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    assert repository.claim_next_due_work(
        worker_id="worker-a", now=datetime(2026, 8, 25, tzinfo=UTC)
    ) is None
    assert len(connection.statements) == 1
    assert "c.lease_expires_at <= %s" in connection.statements[0][0]


def test_analysis_eligible_query_is_fully_scoped_bounded_and_lineage_complete(
    scope: TelemetryScopeRef,
) -> None:
    connection = _Connection([[{"id": "observation"}]])
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    result = repository.list_analysis_eligible_observations(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        source_run_id="00000000-0000-0000-0000-000000000002",
    )
    assert result == [{"id": "observation"}]
    sql = connection.statements[0][0]
    assert "o.resource_scope_id = %s" in sql
    assert "o.tenant_scope_id = %s" in sql
    assert "o.analysis_eligible = TRUE" in sql
    assert "o.quality_state = 'good'" in sql
    assert "m.enabled = TRUE" in sql
    assert "o.asset_id IS NOT DISTINCT FROM %s" in sql
    assert "%s::TEXT IS NULL OR o.system_id = %s::TEXT" in sql
    assert "o.asset_id IS NOT DISTINCT FROM %s::TEXT" in sql
    assert "%s::TIMESTAMPTZ IS NULL" in sql
    assert "o.mapping_authority_digest" in sql
    assert "o.provider_event_id" in sql
    assert "LIMIT %s" in sql


def test_worker_resolves_shared_authority_snapshot_without_runtime_sqlite(
    scope: TelemetryScopeRef,
) -> None:
    identity = build_telemetry_server_bound_system_identity(
        scope=AuthenticatedPhase4Scope(
            tenant_scope_id=scope.tenant_scope_id,
            workspace_id=scope.workspace_id,
            resource_scope_id=scope.resource_scope_id,
        ),
        system_id="system-a",
        authority_record_digest="c" * 64,
    )
    connection = _Connection(
        [
            [
                {
                    "system_id": "system-a",
                    "asset_id": "asset-a",
                    "authority_digest": "c" * 64,
                    "identity_digest": identity.identity_digest,
                    "authority_snapshot": {
                        "contract_version": "telemetry-analysis-authority-snapshot.v1",
                        "facility_id": scope.facility_id,
                        "system_id": "system-a",
                        "asset_id": "asset-a",
                    },
                }
            ]
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)

    resolved = repository.resolve_analysis_authority_snapshot(
        scope,
        system_id="system-a",
        asset_id="asset-a",
        authority_digest="c" * 64,
    )

    assert resolved == identity
    sql = connection.statements[0][0]
    assert "telemetry.analysis_authority_snapshots" in sql
    assert "runtime" not in sql.lower()
    assert "a.resource_scope_id = %s" in sql


def test_analysis_eligible_query_raises_instead_of_truncating(
    scope: TelemetryScopeRef,
) -> None:
    connection = _Connection([[{"id": "a"}, {"id": "b"}, {"id": "c"}]])
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    with pytest.raises(
        TelemetryRepositoryError, match="telemetry_analysis_observation_limit_exceeded"
    ):
        repository.list_analysis_eligible_observations(
            scope,
            connection_id="00000000-0000-0000-0000-000000000001",
            source_run_id="00000000-0000-0000-0000-000000000002",
            limit=2,
        )
    assert connection.statements[0][1][-1] == 3


def test_analysis_window_persistence_is_atomic_exact_and_idempotent(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    window_id = "00000000-0000-0000-0000-000000000040"
    run_id = "00000000-0000-0000-0000-000000000002"
    observation_ids = [
        "00000000-0000-0000-0000-000000000041",
        "00000000-0000-0000-0000-000000000042",
    ]
    final = {
        "id": window_id, "status": "eligible", "authority_digest": "c" * 64,
        "quality_summary": {"observation_count": 2},
    }
    connection = _Connection(
        [
            ("run", "00000000-0000-0000-0000-000000000001"),
            (2, 1),
            (window_id,),
            (2, 2),
            final,
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    record = {
        "id": window_id, **scope.as_public_dict(), "system_id": "system-a",
        "asset_id": None, "source_ingestion_run_id": run_id,
        "window_start": now - timedelta(hours=1), "window_end": now,
        "status": "eligible", "authority_digest": "c" * 64,
        "quality_summary": {"observation_count": 2},
    }
    links = [
        {**scope.as_public_dict(), "analysis_window_id": window_id,
         "observation_id": observation_id}
        for observation_id in observation_ids
    ]
    assert repository.persist_analysis_window(
        scope, window_record=record, observation_links=links
    ) == final
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "FOR SHARE" in sql
    assert "o.id = ANY(%s::UUID[])" in sql
    assert "o.connection_id = %s::UUID" in sql
    assert "WHERE o.ingestion_run_id = %s::UUID" in sql
    assert "o.ingestion_run_id = %s::UUID\n                      AND o.system_id" not in sql
    assert "ON CONFLICT (id) DO NOTHING" in sql
    assert "analysis_window_observations" in sql
    assert "matched_count" in sql
    assert connection.commits == 1


def test_ineligible_window_may_persist_without_observation_links(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    window_id = "00000000-0000-0000-0000-000000000040"
    final = {"id": window_id, "status": "ineligible", "quality_summary": {"reason_code": "no_observations"}}
    connection = _Connection(
        [
            ("run", "00000000-0000-0000-0000-000000000001"),
            (window_id,),
            (0, 0),
            final,
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    result = repository.persist_analysis_window(
        scope,
        window_record={
            "id": window_id, **scope.as_public_dict(), "system_id": "system-a",
            "asset_id": None,
            "source_ingestion_run_id": "00000000-0000-0000-0000-000000000002",
            "window_start": now - timedelta(hours=1), "window_end": now,
            "status": "ineligible", "authority_digest": "c" * 64,
            "quality_summary": {"reason_code": "no_observations"},
        },
        observation_links=(),
    )
    assert result["status"] == "ineligible"


def test_analysis_window_status_is_scoped_revision_cas(scope: TelemetryScopeRef) -> None:
    connection = _Connection([{"id": "window", "status": "running"}])
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    result = repository.update_analysis_window_status(
        scope,
        window_id="00000000-0000-0000-0000-000000000040",
        expected_status="eligible",
        target_status="running",
    )
    assert result["status"] == "running"
    sql = connection.statements[0][0]
    assert "w.resource_scope_id = %s" in sql
    assert "w.status = %s" in sql
    assert "status_reason_code" in sql
    assert "WHEN %s::TEXT IS NULL" in sql
    with pytest.raises(ValueError, match="status_transition_invalid"):
        repository.update_analysis_window_status(
            scope,
            window_id="00000000-0000-0000-0000-000000000040",
            expected_status="completed",
            target_status="running",
        )


def test_analysis_terminal_reason_is_bounded_and_status_specific(
    scope: TelemetryScopeRef,
) -> None:
    connection = _Connection([{"id": "window", "status": "failed", "quality_summary": {}}])
    repository = PostgreSQLTelemetryRepository(lambda: connection)
    repository.update_analysis_window_status(
        scope,
        window_id="00000000-0000-0000-0000-000000000040",
        expected_status="running",
        target_status="failed",
        reason_code="telemetry_analysis_execution_failed",
    )
    params = connection.statements[0][1]
    assert params is not None
    assert params[:3] == (
        "failed",
        "telemetry_analysis_execution_failed",
        "telemetry_analysis_execution_failed",
    )
    with pytest.raises(ValueError, match="reason_status_invalid"):
        repository.update_analysis_window_status(
            scope,
            window_id="00000000-0000-0000-0000-000000000040",
            expected_status="eligible",
            target_status="running",
            reason_code="not_allowed",
        )


def test_analysis_execution_claim_recovery_and_completion_are_scoped_cas(
    scope: TelemetryScopeRef,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    window_id = "00000000-0000-0000-0000-000000000040"
    claim_token = "00000000-0000-0000-0000-000000000050"
    claim_connection = _Connection(
        [
            {
                "id": window_id,
                "status": "running",
                "execution_claim_token": claim_token,
                "execution_claim_expires_at": now + timedelta(minutes=10),
                "execution_attempt_count": 1,
            }
        ]
    )
    repository = PostgreSQLTelemetryRepository(lambda: claim_connection)
    claimed = repository.claim_analysis_window_execution(
        scope,
        window_id=window_id,
        claim_token=claim_token,
        claimed_at=now,
        claim_expires_at=now + timedelta(minutes=10),
    )
    assert claimed["status"] == "running"
    claim_sql = claim_connection.statements[0][0]
    assert "w.status = 'eligible'" in claim_sql
    assert "w.execution_attempt_count + 1" in claim_sql
    assert "w.resource_scope_id = %s" in claim_sql

    recovery_connection = _Connection([None])
    PostgreSQLTelemetryRepository(
        lambda: recovery_connection
    ).recover_stale_analysis_window_execution(
        scope, window_id=window_id, recovered_at=now
    )
    recovery_sql = recovery_connection.statements[0][0]
    assert "execution_claim_expires_at <= %s" in recovery_sql
    assert "execution_claim_expired" in recovery_sql

    from app.services.telemetry_result_artifact import canonical_result_id

    source_run_id = "00000000-0000-4000-8000-000000000020"
    result_id = canonical_result_id(
        window_id=window_id,
        execution_contract_version="analysis-window-execution.v1",
    )
    artifact = CanonicalResultArtifact(
        result_id=result_id,
        analysis_window_id=window_id,
        source_run_id=source_run_id,
        artifact_schema_version="telemetry-canonical-result-artifact.v1",
        execution_contract_version="analysis-window-execution.v1",
        analysis_schema_version="analysis-result-v1",
        analysis_contract_version="analysis-result-v1",
        engine_name="sii",
        engine_version="1",
        reference_metadata={},
        observation_count=2,
        observation_lineage_digest="f" * 64,
        finding_ids={"ids": ["finding-a"], "total": 1, "truncated": False},
        evidence_ids={"ids": ["evidence-a"], "total": 1, "truncated": False},
        payload_encoding="zlib+canonical-json.v1",
        payload_digest="d" * 64,
        payload_uncompressed_bytes=10,
        payload_stored_bytes=7,
        serialization_ms=1.25,
        payload=b"payload",
    )
    completion_connection = _Connection(
        [
            {"id": result_id},
            {
                "id": result_id,
                "analysis_window_id": window_id,
                "source_ingestion_run_id": source_run_id,
                "artifact_schema_version": artifact.artifact_schema_version,
                "execution_contract_version": artifact.execution_contract_version,
                "analysis_schema_version": artifact.analysis_schema_version,
                "analysis_contract_version": artifact.analysis_contract_version,
                "engine_name": artifact.engine_name,
                "engine_version": artifact.engine_version,
                "reference_metadata": {},
                "observation_count": 2,
                "observation_lineage_digest": "f" * 64,
                "finding_ids": dict(artifact.finding_ids),
                "evidence_ids": dict(artifact.evidence_ids),
                "payload_encoding": artifact.payload_encoding,
                "payload_digest": artifact.payload_digest,
                "payload_uncompressed_bytes": 10,
                "payload_stored_bytes": 7,
                "serialization_ms": 1.25,
                "payload": b"payload",
            },
            {"id": window_id, "status": "completed", "result_digest": "d" * 64},
        ]
    )
    completed = PostgreSQLTelemetryRepository(
        lambda: completion_connection
    ).finish_analysis_window_execution(
        scope,
        window_id=window_id,
        claim_token=claim_token,
        completed_at=now,
        target_status="completed",
        result_digest="d" * 64,
        result_metadata={"status": "limited", "finding_id_count": 1},
        evidence_lineage={
            "reference_digest": "e" * 64,
            "evidence_ids": ["evidence-a"],
            "finding_ids": ["finding-a"],
            "observation_count": 2,
            "observation_lineage_digest": "f" * 64,
        },
        result_artifact=artifact,
    )
    assert completed["status"] == "completed"
    artifact_sql = completion_connection.statements[0][0]
    completion_sql = completion_connection.statements[2][0]
    assert "INSERT INTO telemetry.analysis_result_artifacts" in artifact_sql
    assert "ON CONFLICT" in artifact_sql
    assert "w.execution_claim_token = %s::UUID" in completion_sql
    assert "w.execution_claim_expires_at > %s" in completion_sql
    assert "result_metadata = %s::JSONB" in completion_sql
    assert "evidence_lineage = %s::JSONB" in completion_sql
    assert completion_connection.commits == 1
