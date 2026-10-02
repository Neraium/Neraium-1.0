"""Optional real PostgreSQL certification of immutable V2 readback."""

from __future__ import annotations

import os
from copy import deepcopy
from uuid import uuid4

import pytest

from app.services import relationship_lineage as v1_lineage
from app.services.relationship_lineage_v2 import RelationshipLineageV2Error, readback
from app.services.telemetry_relationship_lineage_v2_repository import (
    EndpointLineageV2Conflict,
    PostgreSQLEndpointLineageV2Repository,
)
from db.migrations.create_telemetry_connection_tables import apply as foundation
from db.migrations.seed_telemetry_canonical_signal_concepts import apply as catalog
from db.migrations.extend_telemetry_ingestion_runtime import apply as ingestion
from db.migrations.persist_canonical_analysis_results import apply as results
from db.migrations.preserve_telemetry_source_representation import apply as source
from db.migrations.create_relationship_temporal_state import apply as temporal
from db.migrations.create_relationship_lineage_v2_artifacts import apply as lineage_v2, verify as verify_lineage_v2
from test_relationship_lineage_v2 import _pair
from test_telemetry_analysis_window_v2 import _window


DSN = os.environ.get("NERAIUM_TEST_POSTGRES_DSN", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="NERAIUM_TEST_POSTGRES_DSN is not configured")


def test_postgres_v2_artifact_is_immutable_and_replays_exact_endpoint_pair() -> None:
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    database = f"phase3_{uuid4().hex}"
    with psycopg.connect(DSN, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    test_dsn = make_conninfo(DSN, dbname=database)
    try:
        with psycopg.connect(test_dsn) as connection:
            for migration in (foundation, catalog, ingestion, results, source, temporal, lineage_v2):
                migration(connection)
            assert verify_lineage_v2(connection)["table"] == "relationship_lineage_artifacts_v2"
            assert connection.execute(
                "SELECT to_regclass('telemetry.relationship_temporal_state_heads')"
            ).fetchone()[0] is not None
        repository = PostgreSQLEndpointLineageV2Repository(lambda: psycopg.connect(test_dsn))
        window = _window()
        pair = _pair(window)
        artifact = repository.persist(
            window.scope, window=window, pair=pair,
            result={"correlation": 0.75}, evidence={"basis": "test-only"},
        )
        assert repository.read(window.scope, window=window, pair=pair) == artifact
        lineage = artifact["payload"]["lineage"]["payload"]
        assert lineage["scope"] == {
            "tenant_scope_id": window.scope.tenant_scope_id,
            "workspace_id": window.scope.workspace_id,
            "resource_scope_id": window.scope.resource_scope_id,
            "facility_id": window.scope.facility_id,
            "system_id": window.system_identity.system_id,
            "asset_id": window.asset_id,
        }
        assert lineage["schema_fingerprint"] == window.schema_fingerprint
        assert lineage["window_content_digest"] == window.content_digest
        assert lineage["pair_ref"] == pair.ref
        for field in (
            "endpoint_id", "resource_scope_id", "connection_id", "external_signal_id",
            "mapping_id", "mapping_revision", "authority_digest", "facility_id",
            "system_id", "asset_id", "canonical_concept_id",
        ):
            assert lineage["source_endpoint"][field] == getattr(pair.source, field)
            assert lineage["target_endpoint"][field] == getattr(pair.target, field)
        assert not v1_lineage.verify(artifact["payload"]["lineage"])

        same_concept_source = next(
            item.series_id for item in window.series
            if item.identity.canonical_concept_id == pair.source.canonical_concept_id
            and item.series_id != pair.source.endpoint_id
        )
        other_pair = window.relationship_pair(same_concept_source, pair.target.endpoint_id)
        other = repository.persist(
            window.scope, window=window, pair=other_pair,
            result={"correlation": 0.7}, evidence={"basis": "test-only"},
        )
        assert pair.source.canonical_concept_id == other_pair.source.canonical_concept_id
        assert pair.source.endpoint_id != other_pair.source.endpoint_id
        assert artifact["ref"] != other["ref"]
        assert repository.read(window.scope, window=window, pair=other_pair) == other
        assert repository.read(window.scope, window=window, pair=pair) == artifact
        assert repository.read(
            window.scope, window=window,
            pair=window.relationship_pair(pair.target.endpoint_id, pair.source.endpoint_id),
        ) is None

        corrupted = deepcopy(artifact)
        corrupted["payload"]["lineage"]["payload"]["source_endpoint"]["mapping_revision"] += 1
        with pytest.raises(RelationshipLineageV2Error):
            readback(corrupted, window=window, pair=pair)
        with psycopg.connect(test_dsn) as connection:
            rows = connection.execute(
                "SELECT source_endpoint_id, target_endpoint_id, artifact_payload FROM telemetry.relationship_lineage_artifacts_v2 ORDER BY source_endpoint_id"
            ).fetchall()
            assert len(rows) == 2
            assert {row[0] for row in rows} == {pair.source.endpoint_id, other_pair.source.endpoint_id}
            assert all(row[1] == pair.target.endpoint_id for row in rows)
            assert {row[2]["ref"] for row in rows} == {artifact["ref"], other["ref"]}
        with pytest.raises(EndpointLineageV2Conflict):
            repository.persist(
                window.scope, window=window, pair=pair,
                result={"correlation": 0.1}, evidence={"basis": "test-only"},
            )
        with psycopg.connect(test_dsn) as connection:
            with pytest.raises(psycopg.Error, match="relationship_lineage_v2_immutable"):
                connection.execute(
                    "UPDATE telemetry.relationship_lineage_artifacts_v2 SET system_id = 'tampered' WHERE artifact_ref = %s",
                    (artifact["ref"],),
                )
    finally:
        with psycopg.connect(DSN, autocommit=True, connect_timeout=5) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
            )
