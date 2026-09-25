from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_repository import (
    RelationshipTemporalStateConflict,
    PostgreSQLTelemetryRepository,
    _relationship_state_identity,
    _relationship_state_payload,
)
from db.migrations.create_relationship_temporal_state import DDL, MIGRATION_ID


def scope(tenant="tenant-a", workspace="workspace-a"):
    return TelemetryScopeRef(tenant, workspace,
        canonical_phase4_resource_scope_id(tenant, workspace), workspace)


def test_exact_scope_system_asset_and_lineage_isolate_state_keys():
    base = _relationship_state_identity(scope(), "system-a", "asset-a", "lineage-a")
    assert base != _relationship_state_identity(scope("tenant-b", "workspace-b"), "system-a", "asset-a", "lineage-a")
    assert base != _relationship_state_identity(scope(), "system-b", "asset-a", "lineage-a")
    assert base != _relationship_state_identity(scope(), "system-a", "asset-b", "lineage-a")
    assert base != _relationship_state_identity(scope(), "system-a", "asset-a", "lineage-b")


def test_state_envelope_is_versioned_bounded_and_digest_bound_to_head():
    identity = _relationship_state_identity(scope(), "system-a", None, "lineage-a")
    compat = "a" * 64
    state = {"version": 1, "identity": {"basis": "global"}, "observations": [{"eligible": True}] * 8}
    _body, digest = _relationship_state_payload(identity, compat, state,
        head_event_ref="event-a", head_event_time=datetime(2026, 1, 1, tzinfo=UTC))
    _body2, changed = _relationship_state_payload(identity, compat, state,
        head_event_ref="event-b", head_event_time=datetime(2026, 1, 2, tzinfo=UTC))
    assert digest != changed
    with pytest.raises(RelationshipTemporalStateConflict, match="unbounded"):
        _relationship_state_payload(identity, compat, {**state, "observations": state["observations"] + [{}]})


@pytest.mark.parametrize("scope_value", ["result-local", "placeholder"])
def test_placeholder_scope_cannot_create_identity(scope_value):
    invalid_scope = TelemetryScopeRef(scope_value, "workspace-a",
        canonical_phase4_resource_scope_id(scope_value, "workspace-a"), "workspace-a")
    with pytest.raises(RelationshipTemporalStateConflict, match="placeholder"):
        _relationship_state_identity(invalid_scope, "system-a", None, "lineage-a")


def test_migration_declares_unique_scoped_lineage_head_and_no_history_backfill():
    assert MIGRATION_ID == "007_create_relationship_temporal_state"
    assert "ux_relationship_temporal_state_scope_lineage" in DDL
    assert "storage_revision BIGINT NOT NULL" in DDL
    assert "INSERT INTO" not in DDL


def test_same_event_ref_and_state_with_different_time_is_conflicting_replay():
    identity = _relationship_state_identity(scope(), "system-a", None, "lineage-a")
    compatibility = "a" * 64
    state = {"version": 1, "identity": {"basis": "global"}, "observations": []}
    stored_time = datetime(2026, 1, 1, tzinfo=UTC)
    _body, state_digest = _relationship_state_payload(
        identity, compatibility, state,
        head_event_ref="event-a", head_event_time=stored_time,
    )

    class Cursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, *_args):
            return None

        def fetchone(self):
            return {
                "compatibility_digest": compatibility,
                "reducer_state": state,
                "head_event_ref": "event-a",
                "head_event_time": stored_time,
                "state_digest": state_digest,
                "storage_revision": 1,
            }

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            raise AssertionError("conflicting replay must not commit")

        def rollback(self):
            pass

        def close(self):
            pass

    repository = PostgreSQLTelemetryRepository(Connection)
    with pytest.raises(RelationshipTemporalStateConflict, match="conflicting_replay"):
        repository.compare_and_swap_relationship_temporal_state(
            scope(), system_id="system-a", asset_id=None, lineage_ref="lineage-a",
            compatibility_digest=compatibility, reducer_state=state,
            head_event_ref="event-a", head_event_time=datetime(2026, 1, 2, tzinfo=UTC),
            expected_revision=1, expected_head_event_ref="event-a",
        )
