"""Disposable PostgreSQL certification for the V2 execution result."""

from __future__ import annotations

import os
from datetime import timedelta
from uuid import uuid4

import pytest

from app.services.phase4_scope import ServerBoundSystemIdentityV2
from app.services.telemetry_analysis_service_v2 import read_persisted_execution_v2, run_post_ingestion_analysis_v2
from app.engine.sii.phase4 import phase4_persistence_suppressed
from app.services.telemetry_analysis_window_v2 import build_endpoint_analysis_window_v2
from app.services.telemetry_endpoint_execution_v2_repository import (
    EndpointExecutionV2Error,
    PostgreSQLEndpointExecutionV2Repository,
)
from app.services.telemetry_relationship_lineage_v2_repository import PostgreSQLEndpointLineageV2Repository
from db.migrations.create_telemetry_connection_tables import apply as foundation
from db.migrations.seed_telemetry_canonical_signal_concepts import apply as catalog
from db.migrations.extend_telemetry_ingestion_runtime import apply as ingestion
from db.migrations.persist_canonical_analysis_results import apply as results
from db.migrations.preserve_telemetry_source_representation import apply as source
from db.migrations.create_relationship_temporal_state import apply as temporal
from db.migrations.create_relationship_lineage_v2_artifacts import apply as lineage
from db.migrations.create_endpoint_analysis_executions_v2 import apply as execution, verify
from test_telemetry_analysis_window_v2 import DIGEST, CONCEPT_FLOW, START, _binding, _observation, _scope
from test_telemetry_analysis_service_v2 import _authority_row


DSN = os.environ.get("NERAIUM_TEST_POSTGRES_DSN", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="NERAIUM_TEST_POSTGRES_DSN is not configured")


def test_execution_roundtrip_requires_exact_window_pair_and_immutable_storage() -> None:
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    database = f"phase4_{uuid4().hex}"
    with psycopg.connect(DSN, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    test_dsn = make_conninfo(DSN, dbname=database)
    try:
        with psycopg.connect(test_dsn) as connection:
            for migration in (foundation, catalog, ingestion, results, source, temporal, lineage, execution):
                migration(connection)
            assert verify(connection)["table"] == "endpoint_analysis_executions_v2"
        scope = _scope()
        bindings = (_binding(1), _binding(2), _binding(3, CONCEPT_FLOW))
        source_run_id = str(uuid4())
        observations = tuple(
            {**_observation(binding, minute), "ingestion_run_id": source_run_id}
            for minute in (0, 1) for binding in bindings
        )
        window = build_endpoint_analysis_window_v2(
            window_id=str(uuid4()), source_run_id=source_run_id, scope=scope,
            system_identity=ServerBoundSystemIdentityV2(
                system_id="system-a", resource_scope_id=scope.resource_scope_id,
                authority_record_digest=DIGEST,
            ),
            asset_id="pump-1", bindings=bindings, observations=observations,
        )
        pair_a = window.relationship_pair(bindings[0].identity.endpoint_id, bindings[2].identity.endpoint_id)
        pair_b = window.relationship_pair(bindings[1].identity.endpoint_id, bindings[2].identity.endpoint_id)
        lineage_repo = PostgreSQLEndpointLineageV2Repository(lambda: psycopg.connect(test_dsn))
        result_repo = PostgreSQLEndpointExecutionV2Repository(lambda: psycopg.connect(test_dsn))
        for pair in (pair_a, pair_b):
            lineage_repo.persist(
                scope, window=window, pair=pair,
                result={"correlation": 0.75}, evidence={"basis": "test-only"},
            )
        result = {"status": "complete", "relationships": 2}
        stored = result_repo.persist_execution(
            scope, window=window, result=result, pairs=(pair_a, pair_b),
            lineage_repository=lineage_repo,
        )
        assert result_repo.persist_execution(
            scope, window=window, result={"status": "complete", "relationships": 2, "elapsed_ms": 99},
            pairs=(pair_a, pair_b), lineage_repository=lineage_repo,
        ) == stored
        assert result_repo.read_execution(
            scope, window=window, pairs=(pair_a, pair_b), lineage_repository=lineage_repo,
        ) == stored
        class AuthorityRepository:
            rows = [_authority_row(item) for item in bindings]

            def resolve_analysis_authority_snapshot(self, scope, **kwargs):
                if kwargs["authority_digest"] != DIGEST:
                    return None
                return ServerBoundSystemIdentityV2(
                    system_id=kwargs["system_id"], resource_scope_id=scope.resource_scope_id,
                    authority_record_digest=kwargs["authority_digest"],
                )

            def list_analysis_endpoint_authority(self, scope, **kwargs):
                return self.rows

        authority = AuthorityRepository()
        read = lambda: read_persisted_execution_v2(
            repository=authority, lineage_repository=lineage_repo,
            execution_repository=result_repo, scope=scope,
            connection_id=bindings[0].mapping.connection_id,
            source_run_id=source_run_id, system_id="system-a", asset_id="pump-1",
            execution_ref=stored["ref"],
        )
        assert read() == stored
        for field, value in (
            ("revision", 4), ("authority_digest", "b" * 64),
            ("canonical_concept_id", bindings[2].mapping.canonical_signal_id),
            ("system_id", "other-system"), ("asset_id", "other-asset"),
            ("connection_id", str(uuid4())), ("external_signal_id", str(uuid4())),
        ):
            authority.rows = [_authority_row(item) for item in bindings]
            authority.rows[0][field] = value
            with pytest.raises(EndpointExecutionV2Error):
                read()
        authority.rows = [_authority_row(item) for item in bindings]
        assert stored["payload"]["window"]["series"][0]["endpoint_identity"]["mapping_revision"] == 3
        assert pair_a.source.canonical_concept_id == pair_b.source.canonical_concept_id
        assert pair_a.source.endpoint_id != pair_b.source.endpoint_id
        with pytest.raises(EndpointExecutionV2Error):
            result_repo.read_execution(
                scope, window=window, pairs=(pair_a,), lineage_repository=lineage_repo,
            )
        with psycopg.connect(test_dsn) as connection:
            with pytest.raises(psycopg.Error, match="endpoint_analysis_execution_v2_immutable"):
                connection.execute(
                    "UPDATE telemetry.endpoint_analysis_executions_v2 SET system_id='other' WHERE execution_ref=%s",
                    (stored["ref"],),
                )

        production_run_id = str(uuid4())
        production_observations = [
            {**_observation(binding, minute), "ingestion_run_id": production_run_id}
            for minute in range(30) for binding in bindings
        ]

        class ProductionAuthority(AuthorityRepository):
            def list_analysis_eligible_observations(self, scope, **kwargs):
                return production_observations

        production_authority = ProductionAuthority()
        with phase4_persistence_suppressed():
            production = run_post_ingestion_analysis_v2(
                repository=production_authority, lineage_repository=lineage_repo,
                execution_repository=result_repo, scope=scope,
                connection_id=bindings[0].mapping.connection_id,
                source_run_id=production_run_id, system_id="system-a", asset_id="pump-1",
                window_start=START - timedelta(seconds=1),
                window_end=START + timedelta(minutes=31),
                persisted_authority_digest=DIGEST,
            )
        assert production.status == "completed"
        assert production.result_id.startswith("telemetry-endpoint-execution.v2:")
        replay = read_persisted_execution_v2(
            repository=production_authority, lineage_repository=lineage_repo,
            execution_repository=result_repo, scope=scope,
            connection_id=bindings[0].mapping.connection_id,
            source_run_id=production_run_id, system_id="system-a", asset_id="pump-1",
            execution_ref=production.result_id,
        )
        assert replay["ref"] == production.result_id
        assert len(replay["payload"]["relationship_refs"]) == 3
        repeated = run_post_ingestion_analysis_v2(
            repository=production_authority, lineage_repository=lineage_repo,
            execution_repository=result_repo, scope=scope,
            connection_id=bindings[0].mapping.connection_id,
            source_run_id=production_run_id, system_id="system-a", asset_id="pump-1",
            window_start=START - timedelta(seconds=1),
            window_end=START + timedelta(minutes=31),
            persisted_authority_digest=DIGEST,
            evaluator=lambda **_: pytest.fail("replay executed the numerical engine"),
        )
        assert repeated.reused_existing is True
        assert repeated.result_id == production.result_id
    finally:
        with psycopg.connect(DSN, autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
