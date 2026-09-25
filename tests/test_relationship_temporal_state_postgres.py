"""Real PostgreSQL transaction certification for Phase C temporal state."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_repository import (
    PostgreSQLTelemetryRepository,
    RelationshipTemporalStateConflict,
)


DSN = os.environ.get("NERAIUM_TEST_POSTGRES_DSN", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="NERAIUM_TEST_POSTGRES_DSN is not configured")


def _scope(tenant: str, workspace: str) -> TelemetryScopeRef:
    return TelemetryScopeRef(
        tenant, workspace, canonical_phase4_resource_scope_id(tenant, workspace), workspace
    )


def _state(event_ref: str, interval_ref: str = "window-1") -> dict:
    return {
        "version": 1,
        "identity": {"basis": "global"},
        "observations": [{"interval_ref": interval_ref, "event_ref": event_ref}],
    }


def test_postgres_temporal_state_transaction_contract():
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    # Give this run its own database so migrations and cleanup cannot touch a
    # caller's telemetry data, even when the configured DSN is externally owned.
    database = f"phasec_{uuid4().hex}"
    with psycopg.connect(DSN, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    test_dsn = make_conninfo(DSN, dbname=database)
    try:
        from db.migrations.create_telemetry_connection_tables import apply as apply_foundation
        from db.migrations.seed_telemetry_canonical_signal_concepts import apply as apply_catalog
        from db.migrations.extend_telemetry_ingestion_runtime import apply as apply_ingestion
        from db.migrations.persist_canonical_analysis_results import apply as apply_results
        from db.migrations.preserve_telemetry_source_representation import apply as apply_source
        from db.migrations.create_relationship_temporal_state import apply as apply_temporal

        with psycopg.connect(test_dsn) as connection:
            for migration in (
                apply_foundation, apply_catalog, apply_ingestion,
                apply_results, apply_source, apply_temporal,
            ):
                migration(connection)

        repository = PostgreSQLTelemetryRepository(lambda: psycopg.connect(test_dsn))
        tenant, workspace = f"tenant-{uuid4().hex}", f"workspace-{uuid4().hex}"
        resource_scope = _scope(tenant, workspace)
        compatibility = "a" * 64
        t0 = datetime(2026, 1, 1, tzinfo=UTC)
        first_state = _state("source-1")

        def write(event: str, at: datetime, state: dict, *, revision: int, head: str | None,
                  target_scope=resource_scope, system="system-a", asset="asset-a", lineage="lineage-a"):
            return repository.compare_and_swap_relationship_temporal_state(
                target_scope, system_id=system, asset_id=asset, lineage_ref=lineage,
                compatibility_digest=compatibility, reducer_state=state,
                head_event_ref=event, head_event_time=at,
                expected_revision=revision, expected_head_event_ref=head,
            )

        def read(*, target_scope=resource_scope, system="system-a", asset="asset-a", lineage="lineage-a"):
            return repository.read_relationship_temporal_state(
                target_scope, system_id=system, asset_id=asset, lineage_ref=lineage,
            )

        created = write("event-1", t0, first_state, revision=0, head=None)
        assert created["storage_revision"] == 1
        assert created["idempotent_replay"] is False
        assert read()["reducer_state"] == first_state

        replay = write("event-1", t0, first_state, revision=1, head="event-1")
        assert replay["idempotent_replay"] is True
        assert replay["storage_revision"] == 1

        def unchanged():
            current = read()
            assert current["head_event_ref"] == "event-1"
            assert current["head_event_time"] == t0
            assert current["storage_revision"] == 1
            assert current["reducer_state"] == first_state

        rejected = [
            ("conflicting_replay", lambda: write("event-1", t0 + timedelta(days=1), first_state,
                                                   revision=1, head="event-1")),
            ("conflicting_interval", lambda: write("event-2", t0 + timedelta(days=1),
                                                     _state("different-source"), revision=1, head="event-1")),
            ("stale_head", lambda: write("event-2", t0 + timedelta(days=1), _state("source-2"),
                                           revision=1, head="wrong-head")),
            ("stale_head", lambda: write("event-2", t0 + timedelta(days=1), _state("source-2"),
                                           revision=0, head="event-1")),
            ("out_of_order", lambda: write("event-2", t0, _state("source-2"),
                                             revision=1, head="event-1")),
        ]
        for code, operation in rejected:
            with pytest.raises(RelationshipTemporalStateConflict, match=code):
                operation()
            unchanged()

        # Every key dimension has an independent head; reads through a changed
        # scope/system/asset/lineage cannot borrow the original state.
        variants = (
            {"target_scope": _scope(f"tenant-{uuid4().hex}", f"workspace-{uuid4().hex}")},
            {"system": "system-b"},
            {"asset": "asset-b"},
            {"lineage": "lineage-b"},
        )
        for variant in variants:
            assert read(**variant) is None
            isolated = write("isolated-event", t0, _state("isolated-source"), revision=0,
                             head=None, **variant)
            assert isolated["storage_revision"] == 1
            assert read(**variant)["head_event_ref"] == "isolated-event"
            unchanged()

        barrier_count = 2
        from threading import Barrier
        barrier = Barrier(barrier_count)

        def competing(event: str):
            barrier.wait(timeout=10)
            try:
                return write(event, t0 + timedelta(days=2), _state(event, f"window-{event}"),
                             revision=1, head="event-1")
            except RelationshipTemporalStateConflict as error:
                return error

        with ThreadPoolExecutor(max_workers=barrier_count) as pool:
            outcomes = list(pool.map(competing, ("writer-a", "writer-b")))
        successes = [item for item in outcomes if isinstance(item, dict)]
        conflicts = [item for item in outcomes if isinstance(item, RelationshipTemporalStateConflict)]
        assert len(successes) == 1
        assert len(conflicts) == 1
        assert "stale_head" in str(conflicts[0])
        winner = read()
        assert winner["head_event_ref"] in {"writer-a", "writer-b"}
        assert winner["storage_revision"] == 2
        assert winner["reducer_state"] == _state(
            winner["head_event_ref"], f"window-{winner['head_event_ref']}"
        )
    finally:
        with psycopg.connect(DSN, autocommit=True, connect_timeout=5) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
            )
