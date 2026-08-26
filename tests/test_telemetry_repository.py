from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

import pytest

from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_repository import (
    PostgreSQLTelemetryRepository,
    TelemetryCheckpointConflict,
    TelemetryMappingConflict,
    TelemetryRepositoryScope,
    repository_sql_contract,
)
from app.services.telemetry_domain import CheckpointMode, ConnectorType


class _Cursor:
    def __init__(self, connection: "_Connection") -> None:
        self.connection = connection
        self.rowcount = connection.rowcount
        self.description: list[Any] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.connection.statements.append((sql, params))

    def fetchone(self) -> Any:
        if not self.connection.fetches:
            return None
        return self.connection.fetches.pop(0)

    def fetchall(self) -> list[Any]:
        if not self.connection.fetches:
            return []
        rows = self.connection.fetches.pop(0)
        return list(rows)


class _Connection:
    def __init__(self, fetches: list[Any] | None = None, *, rowcount: int = 1) -> None:
        self.fetches = list(fetches or [])
        self.rowcount = rowcount
        self.statements: list[tuple[str, object]] = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed += 1


class _UniqueViolation(Exception):
    sqlstate = "23505"


class _UniqueCursor(_Cursor):
    def execute(self, sql: str, params: object = None) -> None:
        super().execute(sql, params)
        if "INSERT INTO telemetry.signal_mappings" in sql:
            raise _UniqueViolation("constraint detail must not escape")


class _UniqueConnection(_Connection):
    def cursor(self) -> _UniqueCursor:
        return _UniqueCursor(self)


class _Factory:
    def __init__(self, connections: list[_Connection]) -> None:
        self.connections = connections

    def __call__(self) -> _Connection:
        return self.connections.pop(0)


@pytest.fixture
def scope() -> TelemetryRepositoryScope:
    return TelemetryRepositoryScope(
        tenant_scope_id="tenant-a",
        workspace_id="workspace-a",
        resource_scope_id=canonical_phase4_resource_scope_id("tenant-a", "workspace-a"),
        facility_id="workspace-a",
    )


def test_scope_requires_every_server_attested_dimension() -> None:
    with pytest.raises(ValueError, match="resource_scope_id"):
        TelemetryRepositoryScope(
            tenant_scope_id="tenant-a",
            workspace_id="workspace-a",
            resource_scope_id="",
            facility_id="facility-a",
        )


def test_public_connection_lookup_is_compound_scoped_and_secret_safe(
    scope: TelemetryRepositoryScope,
) -> None:
    record = {
        "id": "00000000-0000-0000-0000-000000000001",
        "resource_scope_id": scope.resource_scope_id,
        "safe_config": {},
        "credentials_configured": True,
    }
    connection = _Connection([record])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    returned = repository.get_connection(scope, record["id"])

    assert returned == record
    sql, params = connection.statements[0]
    assert "c.resource_scope_id = %s" in sql
    assert "c.tenant_scope_id = %s" in sql
    assert "c.workspace_id = %s" in sql
    assert "c.facility_id = %s" in sql
    assert "internal_reference" not in sql
    assert "secret_binding_id" not in sql
    assert params == (
        scope.resource_scope_id,
        scope.tenant_scope_id,
        scope.workspace_id,
        scope.facility_id,
        record["id"],
    )


def test_connection_creation_and_audit_commit_atomically(
    scope: TelemetryRepositoryScope,
) -> None:
    record = {
        "id": "00000000-0000-0000-0000-000000000001",
        "resource_scope_id": scope.resource_scope_id,
        "safe_config": {},
        "credentials_configured": False,
    }
    connection = _Connection([record])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))

    returned = repository.create_connection(
        scope,
        connection_id=record["id"],
        name="Synthetic HTTPS telemetry",
        connector_type=ConnectorType.HTTPS_TELEMETRY,
        safe_config={"base_url": "https://telemetry.example.test"},
        timezone_name="UTC",
        polling_interval_seconds=300,
        actor_id="admin@example.test",
        audit_event_id="00000000-0000-0000-0000-000000000010",
        audit_safe_detail={"connector_type": "https_telemetry"},
    )

    assert returned == record
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert any("INSERT INTO telemetry.data_connections" in sql for sql, _ in connection.statements)
    assert any("INSERT INTO telemetry.telemetry_audit_events" in sql for sql, _ in connection.statements)


def test_secret_binding_write_never_returns_reference(
    scope: TelemetryRepositoryScope,
) -> None:
    connection = _Connection([("connection",)])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    result = repository.upsert_secret_binding(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        binding_id="00000000-0000-0000-0000-000000000002",
        provider="aws_secrets_manager",
        internal_reference="arn:aws:secretsmanager:region:account:secret:opaque",
        version_marker="v2",
    )

    assert result == {"credentials_configured": True, "version_marker": "v2"}
    assert "arn:" not in repr(result)
    assert any(
        "internal_reference" in sql and "connection_secret_bindings" in sql
        for sql, _ in connection.statements
    )


def test_secret_binding_and_audit_commit_atomically_without_reference_in_audit(
    scope: TelemetryRepositoryScope,
) -> None:
    connection = _Connection([("connection",)])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    repository.upsert_secret_binding(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        binding_id="00000000-0000-0000-0000-000000000002",
        provider="aws_secrets_manager",
        internal_reference="arn:aws:secretsmanager:region:account:secret:opaque",
        version_marker="v2",
        actor_id="admin@example.test",
        audit_event_id="00000000-0000-0000-0000-000000000011",
        audit_safe_detail={"credential_version_changed": True},
    )

    audit_statements = [
        (sql, params)
        for sql, params in connection.statements
        if "INSERT INTO telemetry.telemetry_audit_events" in sql
    ]
    assert len(audit_statements) == 1
    assert "arn:" not in repr(audit_statements[0][1])
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_audit_detail_recursively_drops_secret_shaped_fields(
    scope: TelemetryRepositoryScope,
) -> None:
    connection = _Connection()
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    repository.record_audit_event(
        scope,
        event_id="00000000-0000-0000-0000-000000000010",
        connection_id="00000000-0000-0000-0000-000000000001",
        actor_id="operator@example.test",
        action="connection_created",
        safe_detail={
            "result": "configured",
            "nested": [
                {"Authorization": "Bearer canary", "kept": True},
                {"clientSecret": "canary-client-secret"},
                {"secret_ref": "canary-reference"},
                {"internal_reference": "canary-internal-reference"},
            ],
        },
    )
    _, params = connection.statements[0]
    encoded_detail = params[-1]
    assert "canary" not in encoded_detail
    assert json.loads(encoded_detail) == {
        "nested": [{"kept": True}, {}, {}, {}],
        "result": "configured",
    }


@pytest.mark.parametrize(
    "unsafe_config",
    [
        {"headers": {"Authorization": "Bearer canary"}},
        {"headers": {"x-api-key": "canary"}},
        {"pagination": [{"api_token": "canary"}]},
        {"oauth": {"access_token": "canary"}},
        {"oauth": {"clientSecret": "canary"}},
        {"secret_ref": "canary"},
        {"binding": {"internal_reference": "canary"}},
    ],
)
def test_safe_config_rejects_nested_secret_shaped_fields_before_sql(
    scope: TelemetryRepositoryScope,
    unsafe_config: dict[str, Any],
) -> None:
    repository = PostgreSQLTelemetryRepository(_Factory([]))
    with pytest.raises(ValueError, match="telemetry_connection_safe_config_invalid"):
        repository.create_connection(
            scope,
            connection_id="00000000-0000-0000-0000-000000000001",
            name="Synthetic HTTPS telemetry",
            connector_type=ConnectorType.HTTPS_TELEMETRY,
            safe_config=unsafe_config,
            timezone_name="UTC",
            polling_interval_seconds=300,
            actor_id="operator@example.test",
        )


def test_public_connection_read_recursively_sanitizes_untrusted_json(
    scope: TelemetryRepositoryScope,
) -> None:
    record = {
        "id": "00000000-0000-0000-0000-000000000001",
        "safe_config": {
            "origin": "https://telemetry.example.test",
            "nested": {"api_token": "legacy-canary", "page_size": 100},
        },
    }
    connection = _Connection([record])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    returned = repository.get_connection(scope, record["id"])
    assert returned == {
        "id": record["id"],
        "safe_config": {
            "origin": "https://telemetry.example.test",
            "nested": {"page_size": 100},
        },
    }


def test_claim_uses_skip_locked_and_binds_scope_twice(
    scope: TelemetryRepositoryScope,
) -> None:
    claimed = {
        "id": "00000000-0000-0000-0000-000000000001",
        "lease_token": "00000000-0000-0000-0000-000000000099",
        "safe_config": {},
    }
    now = datetime(2026, 8, 25, tzinfo=UTC)
    connection = _Connection([claimed])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    assert repository.claim_due_connection(
        scope,
        worker_id="worker-a",
        lease_seconds=120,
        now=now,
    ) == claimed

    sql, params = connection.statements[0]
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "lease_token" in sql
    expected_scope = (
        scope.resource_scope_id,
        scope.tenant_scope_id,
        scope.workspace_id,
        scope.facility_id,
    )
    assert tuple(params)[:4] == expected_scope
    assert tuple(params)[-4:] == expected_scope


def test_checkpoint_advance_validates_lease_and_uses_revision_cas(
    scope: TelemetryRepositoryScope,
) -> None:
    connection = _Connection([("connection",), (8,)])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    revision = repository.advance_checkpoint(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        mode="incremental",
        expected_revision=7,
        cursor_payload={"cursor": "opaque-page-4"},
        high_water_at=datetime(2026, 8, 25, tzinfo=UTC),
        updated_run_id="00000000-0000-0000-0000-000000000003",
        lease_token="00000000-0000-0000-0000-000000000004",
    )

    assert revision == 8
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "FOR UPDATE" in sql
    assert "cp.revision = %s" in sql
    assert "lease_expires_at > NOW()" in sql


def test_checkpoint_conflict_rolls_back(scope: TelemetryRepositoryScope) -> None:
    connection = _Connection([("connection",), None])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    with pytest.raises(TelemetryCheckpointConflict):
        repository.advance_checkpoint(
            scope,
            connection_id="00000000-0000-0000-0000-000000000001",
            mode="incremental",
            expected_revision=2,
            cursor_payload={},
            high_water_at=None,
            updated_run_id="00000000-0000-0000-0000-000000000003",
            lease_token="00000000-0000-0000-0000-000000000004",
        )
    assert connection.commits == 0
    assert connection.rollbacks == 1


@pytest.mark.parametrize("mode", ["validation", "retry", "streaming", ""])
def test_checkpoint_mode_is_rejected_before_sql(
    scope: TelemetryRepositoryScope,
    mode: str,
) -> None:
    repository = PostgreSQLTelemetryRepository(_Factory([]))
    with pytest.raises(ValueError, match="telemetry_checkpoint_mode_invalid"):
        repository.get_checkpoint(
            scope,
            connection_id="00000000-0000-0000-0000-000000000001",
            mode=mode,
        )


def test_checkpoint_mode_enum_matches_persistence_contract() -> None:
    assert {item.value for item in CheckpointMode} == {
        "discovery",
        "incremental",
        "backfill",
    }


def test_connector_type_is_rejected_before_sql(scope: TelemetryRepositoryScope) -> None:
    repository = PostgreSQLTelemetryRepository(_Factory([]))
    with pytest.raises(ValueError, match="telemetry_connector_type_invalid"):
        repository.create_connection(
            scope,
            connection_id="00000000-0000-0000-0000-000000000001",
            name="Unsafe legacy connector label",
            connector_type="https",
            safe_config={},
            timezone_name="UTC",
            polling_interval_seconds=300,
            actor_id="operator@example.test",
        )


def test_repository_contract_has_no_public_secret_fields() -> None:
    contract = repository_sql_contract()
    assert contract["public_secret_fields"] == ()
    assert contract["scope_columns"] == (
        "resource_scope_id",
        "tenant_scope_id",
        "workspace_id",
        "facility_id",
    )
    assert "FOR UPDATE SKIP LOCKED" in contract["lease_primitives"]


def test_metadata_patch_is_scoped_secret_safe_and_audited(
    scope: TelemetryRepositoryScope,
) -> None:
    record = {
        "id": "00000000-0000-0000-0000-000000000001",
        "safe_config": {"origin": "https://telemetry.example.test"},
    }
    connection = _Connection([("updated",), record])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    returned = repository.update_connection_metadata(
        scope,
        connection_id=record["id"],
        actor_id="operator@example.test",
        name="Synthetic telemetry",
        safe_config={"origin": "https://telemetry.example.test"},
        timezone_name="America/Phoenix",
        polling_interval_seconds=300,
    )
    assert returned == record
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "c.resource_scope_id = %s" in sql
    assert "connection_updated" in repr(connection.statements)
    assert "telemetry_audit_events" in sql


def test_metadata_patch_rejects_nested_credentials_before_sql(
    scope: TelemetryRepositoryScope,
) -> None:
    repository = PostgreSQLTelemetryRepository(_Factory([]))
    with pytest.raises(ValueError, match="safe_config_invalid"):
        repository.update_connection_metadata(
            scope,
            connection_id="00000000-0000-0000-0000-000000000001",
            actor_id="operator@example.test",
            safe_config={"pagination": {"accessToken": "canary"}},
        )


def test_lifecycle_transition_is_scoped_and_audited(
    scope: TelemetryRepositoryScope,
) -> None:
    record = {
        "id": "00000000-0000-0000-0000-000000000001",
        "lifecycle_status": "validating",
        "safe_config": {},
    }
    connection = _Connection([("draft", False), ("updated",), record])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    returned = repository.set_connection_lifecycle(
        scope,
        connection_id=record["id"],
        target_status="validating",
        actor_id="operator@example.test",
        enabled=False,
        last_attempt_at=datetime(2026, 8, 25, tzinfo=UTC),
    )
    assert returned == record
    assert "validation" not in repr(returned)
    assert "telemetry_audit_events" in "\n".join(
        statement for statement, _ in connection.statements
    )


def test_lifecycle_rejects_secret_shaped_error_summary(
    scope: TelemetryRepositoryScope,
) -> None:
    repository = PostgreSQLTelemetryRepository(_Factory([]))
    with pytest.raises(ValueError, match="error_summary_invalid"):
        repository.set_connection_lifecycle(
            scope,
            connection_id="00000000-0000-0000-0000-000000000001",
            target_status="validating",
            actor_id="operator@example.test",
            last_error_summary="Authorization: Bearer canary",
        )


def test_archive_is_scoped_releases_lease_and_records_audit(
    scope: TelemetryRepositoryScope,
) -> None:
    archived = {
        "id": "00000000-0000-0000-0000-000000000001",
        "lifecycle_status": "archived",
        "safe_config": {},
    }
    connection = _Connection([("disabled",), ("updated",), archived])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    assert repository.archive_connection(
        scope,
        connection_id=archived["id"],
        actor_id="operator@example.test",
    ) == archived
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "lease_owner = NULL" in sql
    assert "connection_archived" in repr(connection.statements)


def test_server_secret_lookup_returns_opaque_binding_not_mapping(
    scope: TelemetryRepositoryScope,
) -> None:
    reference = "arn:aws:secretsmanager:us-east-1:123456789012:secret:opaque"
    connection = _Connection(
        [
            (
                "00000000-0000-0000-0000-000000000002",
                "aws_secrets_manager",
                scope.resource_scope_id,
                "00000000-0000-0000-0000-000000000001",
                reference,
                "v1",
                datetime(2026, 8, 25, tzinfo=UTC),
            )
        ]
    )
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    binding = repository.load_secret_binding(
        scope, connection_id="00000000-0000-0000-0000-000000000001"
    )
    assert binding is not None
    assert not isinstance(binding, dict)
    assert reference not in repr(binding)
    assert binding.public_metadata().as_dict()["credentials_configured"] is True
    sql = connection.statements[0][0]
    assert "c.tenant_scope_id = %s" in sql
    assert "c.facility_id = %s" in sql


def test_discovered_signal_upsert_defaults_to_unmapped_and_disabled(
    scope: TelemetryRepositoryScope,
) -> None:
    returned = {
        "id": "00000000-0000-0000-0000-000000000002",
        "external_tag_id": "CHWP1_KW",
        "enabled": False,
        "mapping_status": "unmapped",
        "quality_state": "mapping_required",
        "source_metadata": "{}",
    }
    connection = _Connection([("connection",), [returned]])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    result = repository.upsert_external_signals(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        signals=[
            {
                "signal_id": returned["id"],
                "external_tag_id": "CHWP1_KW",
                "external_tag_name": "CHWP1_KW",
                "source_unit": "kW",
                "metadata": {},
            }
        ],
    )
    assert result[0]["enabled"] is False
    assert result[0]["mapping_status"] == "unmapped"
    insert_sql = connection.statements[1][0]
    assert "FALSE, 'unmapped', 'mapping_required'" in insert_sql


def test_signal_discovery_is_set_based_not_one_insert_per_signal(
    scope: TelemetryRepositoryScope,
) -> None:
    returned = [
        {
            "id": f"00000000-0000-0000-0000-{index:012d}",
            "external_tag_id": f"tag-{index}",
        }
        for index in (2, 3)
    ]
    connection = _Connection([("connection",), returned])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    result = repository.upsert_external_signals(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        signals=[
            {
                "signal_id": item["id"],
                "external_tag_id": item["external_tag_id"],
                "external_tag_name": item["external_tag_id"],
                "metadata": {},
            }
            for item in returned
        ],
    )
    assert result == returned
    inserts = [
        sql
        for sql, _ in connection.statements
        if "INSERT INTO telemetry.external_signals" in sql
    ]
    assert len(inserts) == 1
    assert "jsonb_to_recordset" in inserts[0]


def test_signal_list_joins_mapping_only_through_full_scope(
    scope: TelemetryRepositoryScope,
) -> None:
    connection = _Connection([[{"id": "signal-1", "source_metadata": {}}]])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    assert repository.list_external_signals(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
    ) == [{"id": "signal-1", "source_metadata": {}}]
    sql = connection.statements[0][0]
    for dimension in (
        "resource_scope_id",
        "tenant_scope_id",
        "workspace_id",
        "facility_id",
    ):
        assert f"m.{dimension} = s.{dimension}" in sql
        assert f"c.{dimension} = %s" in sql


def test_exact_signal_lookup_cannot_cross_connection_or_scope(
    scope: TelemetryRepositoryScope,
) -> None:
    signal = {"id": "00000000-0000-0000-0000-000000000002"}
    connection = _Connection([signal])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    assert repository.get_external_signal(
        scope,
        connection_id="00000000-0000-0000-0000-000000000001",
        signal_id=signal["id"],
    ) == signal
    sql, params = connection.statements[0]
    assert "c.id = %s::UUID" in sql and "s.id = %s::UUID" in sql
    assert tuple(params)[:4] == (
        scope.resource_scope_id,
        scope.tenant_scope_id,
        scope.workspace_id,
        scope.facility_id,
    )


def test_mapping_write_prevents_duplicate_enabled_canonical_hierarchy(
    scope: TelemetryRepositoryScope,
) -> None:
    connection = _Connection([("signal", "kW", "power"), None, (1,)])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    with pytest.raises(TelemetryMappingConflict, match="hierarchy_duplicate"):
        repository.save_signal_mapping(
            scope,
            mapping_id="00000000-0000-0000-0000-000000000010",
            event_id="00000000-0000-0000-0000-000000000011",
            connection_id="00000000-0000-0000-0000-000000000001",
            signal_id="00000000-0000-0000-0000-000000000002",
            system_id="chw-loop-1",
            asset_id="pump-1",
            canonical_concept_id="00000000-0000-0000-0000-000000000003",
            canonical_signal_name="pump_power",
            source_unit="kW",
            canonical_unit="kW",
            conversion_id="kw_to_kw",
            conversion_version="neraium.telemetry.units/v1",
            expected_cadence_seconds=300,
            source_timezone="UTC",
            provenance="manual",
            provenance_reason=None,
            actor_id="operator@example.test",
            authority_digest="a" * 64,
            mapped_at=datetime(2026, 8, 25, tzinfo=UTC),
        )
    assert connection.rollbacks == 1


def test_mapping_unique_race_is_translated_without_constraint_detail(
    scope: TelemetryRepositoryScope,
) -> None:
    connection = _UniqueConnection(
        [("signal", "kW", "power"), None, None]
    )
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    with pytest.raises(TelemetryMappingConflict) as caught:
        repository.save_signal_mapping(
            scope,
            mapping_id="00000000-0000-0000-0000-000000000010",
            event_id="00000000-0000-0000-0000-000000000011",
            connection_id="00000000-0000-0000-0000-000000000001",
            signal_id="00000000-0000-0000-0000-000000000002",
            system_id="chw-loop-1",
            asset_id="pump-1",
            canonical_concept_id="00000000-0000-0000-0000-000000000003",
            canonical_signal_name="pump_power",
            source_unit="kW",
            canonical_unit="kW",
            conversion_id="kw_to_kw",
            conversion_version="neraium.telemetry.units/v1",
            expected_cadence_seconds=300,
            source_timezone="UTC",
            provenance="manual",
            provenance_reason=None,
            actor_id="operator@example.test",
            authority_digest="a" * 64,
            mapped_at=datetime(2026, 8, 25, tzinfo=UTC),
        )
    assert str(caught.value) == "telemetry_mapping_concurrent_conflict"
    assert "constraint" not in str(caught.value)
    assert connection.rollbacks == 1


def test_mapping_rejects_non_authority_digest_before_sql(
    scope: TelemetryRepositoryScope,
) -> None:
    repository = PostgreSQLTelemetryRepository(_Factory([]))
    with pytest.raises(ValueError, match="authority_digest_invalid"):
        repository.save_signal_mapping(
            scope,
            mapping_id="00000000-0000-0000-0000-000000000010",
            event_id="00000000-0000-0000-0000-000000000011",
            connection_id="00000000-0000-0000-0000-000000000001",
            signal_id="00000000-0000-0000-0000-000000000002",
            system_id="chw-loop-1",
            asset_id=None,
            canonical_concept_id="00000000-0000-0000-0000-000000000003",
            canonical_signal_name="pump_power",
            source_unit="kW",
            canonical_unit="kW",
            conversion_id="kw_to_kw",
            conversion_version="neraium.telemetry.units/v1",
            expected_cadence_seconds=300,
            source_timezone="UTC",
            provenance="manual",
            provenance_reason=None,
            actor_id="operator@example.test",
            authority_digest="client-selected-ids",
            mapped_at=datetime(2026, 8, 25, tzinfo=UTC),
        )


def test_health_read_is_scoped_through_connection_authority(
    scope: TelemetryRepositoryScope,
) -> None:
    health = {"connection_id": "00000000-0000-0000-0000-000000000001"}
    connection = _Connection([health])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    assert repository.get_connection_health(
        scope, connection_id=health["connection_id"]
    ) == health
    sql, params = connection.statements[0]
    assert "h.tenant_scope_id = c.tenant_scope_id" in sql
    assert tuple(params)[:4] == (
        scope.resource_scope_id,
        scope.tenant_scope_id,
        scope.workspace_id,
        scope.facility_id,
    )


def test_health_persistence_is_scoped_and_rejects_secret_detail(
    scope: TelemetryRepositoryScope,
) -> None:
    now = datetime(2026, 8, 25, tzinfo=UTC)
    persisted = {
        "connection_id": "00000000-0000-0000-0000-000000000001",
        "aggregate_status": "degraded",
        "details": {},
    }
    health = {
        "aggregate_status": "degraded",
        "reachability_state": "healthy",
        "authentication_state": "healthy",
        "telemetry_freshness_state": "unhealthy",
        "mapping_completeness_state": "degraded",
        "data_quality_state": "healthy",
        "worker_checkpoint_state": "healthy",
        "discovered_signal_count": 4,
        "mapped_signal_count": 3,
        "healthy_signal_count": 3,
        "stale_signal_count": 0,
        "last_healthy_at": None,
        "last_evaluated_at": now,
        "details": {"telemetry_freshness": {"reason_code": "telemetry_stale"}},
    }
    connection = _Connection([persisted])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    assert repository.save_connection_health(
        scope,
        connection_id=persisted["connection_id"],
        health=health,
    ) == persisted
    sql, params = connection.statements[0]
    assert "FROM telemetry.data_connections c" in sql
    assert scope.resource_scope_id in params

    repository = PostgreSQLTelemetryRepository(_Factory([]))
    with pytest.raises(ValueError, match="health_details_invalid"):
        repository.save_connection_health(
            scope,
            connection_id=persisted["connection_id"],
            health={**health, "details": {"nested": {"authToken": "canary"}}},
        )


def test_product_taxonomy_is_the_only_deliberately_unscoped_registry_read() -> None:
    connection = _Connection([[{"canonical_name": "pump_power"}]])
    repository = PostgreSQLTelemetryRepository(_Factory([connection]))
    assert repository.list_canonical_signal_concepts(limit=5000) == [
        {"canonical_name": "pump_power"}
    ]
    sql, params = connection.statements[0]
    assert "canonical_signal_concepts" in sql
    assert params == (1000,)
