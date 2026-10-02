"""Real PostgreSQL coexistence, ingestion, V2 lineage, and historical readback."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.engine.sii.phase4 import phase4_persistence_suppressed
from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_repository import PostgreSQLTelemetryRepository, TelemetryMappingConflict
from app.services.telemetry_analysis_service_v2 import read_persisted_execution_v2, run_post_ingestion_analysis_v2
from app.services.telemetry_analysis_service import run_post_ingestion_analysis
from app.services.telemetry_endpoint_result_v2 import list_customer_executions_v2
from app.services.telemetry_endpoint_execution_v2_repository import PostgreSQLEndpointExecutionV2Repository, EndpointExecutionV2Error
from app.services.telemetry_relationship_lineage_v2_repository import PostgreSQLEndpointLineageV2Repository
from app.services.telemetry_units import conversion_contract, normalize_telemetry_unit
from db.migrations.create_telemetry_connection_tables import apply as foundation
from db.migrations.seed_telemetry_canonical_signal_concepts import apply as catalog
from db.migrations.extend_telemetry_ingestion_runtime import apply as ingestion
from db.migrations.persist_canonical_analysis_results import apply as results
from db.migrations.preserve_telemetry_source_representation import apply as source
from db.migrations.create_relationship_temporal_state import apply as temporal
from db.migrations.create_relationship_lineage_v2_artifacts import apply as lineage
from db.migrations.create_endpoint_analysis_executions_v2 import apply as execution
from db.migrations.allow_same_concept_physical_endpoints import apply as coexistence, verify
from test_telemetry_connection_api import build_client


DSN = os.environ.get("NERAIUM_TEST_POSTGRES_DSN", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="NERAIUM_TEST_POSTGRES_DSN is not configured")
PRESSURE = "9fa5d454-6b13-5f59-99d1-7f6fb0a3e07f"
FLOW = "a19db5be-5ca1-5373-a9e4-6957e9f54c43"
START = datetime(2026, 8, 25, tzinfo=UTC)


def test_same_concept_mappings_ingest_execute_and_replay_after_revision(tmp_path) -> None:
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    database = f"phase5_{uuid4().hex}"
    with psycopg.connect(DSN, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    test_dsn = make_conninfo(DSN, dbname=database)
    try:
        with psycopg.connect(test_dsn) as connection:
            for migrate in (foundation, catalog, ingestion, results, source, temporal, lineage, execution, coexistence):
                migrate(connection)
            assert verify(connection)["endpoint_index"] == "ux_telemetry_signal_mapping_enabled"

        scope = TelemetryScopeRef(
            tenant_scope_id="tenant-a", workspace_id="ws-facility-a",
            resource_scope_id=canonical_phase4_resource_scope_id("tenant-a", "ws-facility-a"),
            facility_id="ws-facility-a",
        )
        connection_id, run_id, lease = (str(uuid4()) for _ in range(3))
        signal_ids = [str(uuid4()) for _ in range(3)]
        with psycopg.connect(test_dsn) as connection:
            connection.execute(
                """INSERT INTO telemetry.data_connections
                   (id, tenant_scope_id, workspace_id, resource_scope_id, facility_id,
                    name, connector_type, lifecycle_status, enabled, timezone,
                    polling_interval_seconds, created_by, updated_by,
                    lease_owner, lease_token, lease_expires_at)
                   VALUES (%s::UUID, %s, %s, %s, %s, 'phase5-test', 'https_telemetry',
                           'connected', TRUE, 'UTC', 60, 'operator-a', 'operator-a',
                           'phase5-worker', %s::UUID, NOW() + INTERVAL '1 hour')""",
                (connection_id, scope.tenant_scope_id, scope.workspace_id,
                 scope.resource_scope_id, scope.facility_id, lease),
            )
            connection.execute(
                """INSERT INTO telemetry.ingestion_runs
                   (id, tenant_scope_id, workspace_id, resource_scope_id, facility_id,
                    connection_id, mode, status, lease_token, started_at)
                   VALUES (%s::UUID, %s, %s, %s, %s, %s::UUID, 'incremental',
                           'running', %s::UUID, NOW())""",
                (run_id, scope.tenant_scope_id, scope.workspace_id,
                 scope.resource_scope_id, scope.facility_id, connection_id, lease),
            )

        repository = PostgreSQLTelemetryRepository(lambda: psycopg.connect(test_dsn))
        units = ("kPa", "psi", "L/s")
        concepts = (PRESSURE, PRESSURE, FLOW)
        names = ("pressure", "pressure", "volumetric_flow")
        dimensions = ("pressure", "pressure", "flow")
        canonical_units = ("kPa", "kPa", "L/s")
        mappings = []
        for index, signal_id in enumerate(signal_ids):
            repository.upsert_external_signals(
                scope, connection_id=connection_id,
                signals=[{"signal_id": signal_id, "external_tag_id": f"sensor-{index}",
                          "external_tag_name": f"sensor-{index}", "source_unit": units[index]}],
            )
            conversion = conversion_contract(
                source_unit=units[index], canonical_unit=canonical_units[index],
                expected_dimension=dimensions[index],
            )
            assert conversion["valid"]
            kwargs = dict(
                mapping_id=str(uuid4()), event_id=str(uuid4()),
                connection_id=connection_id, signal_id=signal_id,
                system_id="system-a", asset_id="pump-1",
                canonical_concept_id=concepts[index], canonical_signal_name=names[index],
                source_unit=units[index], canonical_unit=canonical_units[index],
                conversion_id=conversion["conversion_id"],
                conversion_version=conversion["conversion_version"],
                expected_cadence_seconds=60, source_timezone="UTC",
                provenance="manual", provenance_reason="explicit-test-approval",
                actor_id="operator-a", authority_digest="a" * 64, mapped_at=START,
            )
            if index == 1:
                with pytest.raises(TelemetryMappingConflict, match="canonical_hierarchy_duplicate"):
                    repository.save_signal_mapping(scope, **kwargs)
            mappings.append(repository.save_signal_mapping(
                scope, **kwargs, allow_same_concept_endpoints=True,
            ))
        assert len({item["signal_id"] for item in mappings[:2]}) == 2
        with pytest.raises(psycopg.errors.UniqueViolation):
            with psycopg.connect(test_dsn) as connection:
                connection.execute(
                    """INSERT INTO telemetry.signal_mappings
                       (id, tenant_scope_id, workspace_id, resource_scope_id, facility_id,
                        connection_id, external_signal_id, system_id, asset_id,
                        canonical_concept_id, canonical_signal_name, source_unit,
                        canonical_unit, conversion_id, conversion_version,
                        source_timezone, enabled, provenance, mapped_by, mapped_at,
                        authority_digest, revision)
                       SELECT %s::UUID, tenant_scope_id, workspace_id, resource_scope_id,
                              facility_id, connection_id, external_signal_id, system_id,
                              asset_id, canonical_concept_id, canonical_signal_name,
                              source_unit, canonical_unit, conversion_id,
                              conversion_version, source_timezone, TRUE, provenance,
                              mapped_by, mapped_at, authority_digest, revision
                       FROM telemetry.signal_mappings WHERE id = %s::UUID""",
                    (str(uuid4()), mappings[0]["id"]),
                )
        with pytest.raises(TelemetryMappingConflict, match="already_enabled"):
            repository.save_signal_mapping(
                scope, mapping_id=str(uuid4()), event_id=str(uuid4()),
                connection_id=connection_id, signal_id=signal_ids[0],
                system_id="system-a", asset_id="pump-1",
                canonical_concept_id=PRESSURE, canonical_signal_name="pressure",
                source_unit="kPa", canonical_unit="kPa",
                conversion_id=conversion_contract(source_unit="kPa", canonical_unit="kPa", expected_dimension="pressure")["conversion_id"],
                conversion_version=conversion_contract(source_unit="kPa", canonical_unit="kPa", expected_dimension="pressure")["conversion_version"],
                expected_cadence_seconds=60, source_timezone="UTC",
                provenance="manual", provenance_reason=None, actor_id="operator-a",
                authority_digest="a" * 64, mapped_at=START,
                allow_same_concept_endpoints=True,
            )

        prepared = []
        psi_factor = normalize_telemetry_unit(
            value=1.0, source_unit="psi", canonical_unit="kPa",
            expected_dimension="pressure",
        ).canonical_value
        assert psi_factor is not None
        for minute in range(30):
            timestamp = START + timedelta(minutes=minute)
            for index, signal_id in enumerate(signal_ids):
                value = float(100 + minute + (1 if index == 2 else 0))
                if index == 1:
                    value /= psi_factor
                normalized = normalize_telemetry_unit(
                    value=value, source_unit=units[index],
                    canonical_unit=canonical_units[index],
                    expected_dimension=dimensions[index],
                )
                prepared.append({
                    "id": str(uuid4()), "system_id": "system-a", "asset_id": "pump-1",
                    "external_signal_id": signal_id, "mapping_id": str(mappings[index]["id"]),
                    "mapping_revision": 1, "canonical_concept_id": concepts[index],
                    "canonical_signal_name": names[index], "external_tag_id": f"sensor-{index}",
                    "source_timestamp_raw": timestamp.isoformat(), "source_timezone": "UTC",
                    "source_offset": "+00:00", "timestamp_normalization_version": "timestamps.v1",
                    "observed_at_utc": timestamp, "original_value": value, "original_unit": units[index],
                    "normalized_value": normalized.canonical_value, "canonical_unit": canonical_units[index],
                    "conversion_id": normalized.conversion_id,
                    "conversion_version": normalized.conversion_version,
                    "quality_state": "good", "ingestion_disposition": "accepted",
                    "analysis_eligible": True, "reason_codes": [],
                    "source_record_digest": f"{minute * 3 + index + 1:064x}",
                    "source_metadata": {}, "mapping_actor_id": "operator-a",
                    "mapping_mapped_at": START, "mapping_authority_digest": "a" * 64,
                    "mapping_provenance": "manual",
                })
        counts = repository.persist_ingestion_page(
            scope, connection_id=connection_id, run_id=run_id, lease_token=lease,
            checkpoint_mode="incremental", expected_checkpoint_revision=0,
            cursor_payload={}, high_water_at=START + timedelta(minutes=29),
            observations=prepared, rejections=[],
        )
        assert counts["accepted"] == 90
        fetched = repository.list_analysis_eligible_observations(
            scope, connection_id=connection_id, source_run_id=run_id,
            system_id="system-a", asset_id="pump-1", asset_filter_applied=True,
            window_start=START, window_end=START + timedelta(minutes=30),
            authority_digest="a" * 64,
        )
        assert len(fetched) == 90
        assert {str(item["external_signal_id"]) for item in fetched} == set(signal_ids)
        first_values = {str(item["external_signal_id"]): item["normalized_value"]
                        for item in fetched if item["observed_at_utc"] == START}
        assert first_values[signal_ids[0]] == pytest.approx(first_values[signal_ids[1]])
        v1 = run_post_ingestion_analysis(
            repository=repository, scope=scope, connection_id=connection_id,
            source_run_id=run_id, system_id="system-a", asset_id="pump-1",
            window_start=START, window_end=START + timedelta(minutes=30),
            persisted_authority_digest="a" * 64,
        )
        assert v1.status == "ineligible"
        assert v1.reason_code == "telemetry_analysis_v1_concept_endpoint_ambiguous"

        lineage_repo = PostgreSQLEndpointLineageV2Repository(lambda: psycopg.connect(test_dsn))
        execution_repo = PostgreSQLEndpointExecutionV2Repository(lambda: psycopg.connect(test_dsn))
        with phase4_persistence_suppressed():
            analysis = run_post_ingestion_analysis_v2(
                repository=repository, lineage_repository=lineage_repo,
                execution_repository=execution_repo, scope=scope,
                connection_id=connection_id, source_run_id=run_id,
                system_id="system-a", asset_id="pump-1",
                window_start=START, window_end=START + timedelta(minutes=30),
                persisted_authority_digest="a" * 64,
            )
        assert analysis.status == "completed"
        listed = list_customer_executions_v2(
            repository=repository, lineage_repository=lineage_repo,
            execution_repository=execution_repo, scope=scope,
            connection_id=connection_id, source_run_id=run_id, limit=100,
        )
        assert [item["execution_ref"] for item in listed] == [analysis.result_id]
        app, _ = build_client(tmp_path)
        with TestClient(app, base_url="https://testserver") as client:
            runtime = app.state.telemetry_runtime
            runtime.repository = repository
            runtime.execution_identity_version = "physical-endpoint-keyed.v2"
            base = f"/api/data-connections/{connection_id}/runs/{run_id}"
            listing = client.get(f"{base}/analysis-results")
            assert listing.status_code == 200, listing.text
            assert listing.json()["results"] == listed
            exact = client.get(f"{base}/v2/analysis-results/{analysis.result_id}")
            assert exact.status_code == 200, exact.text
            assert exact.json()["result_id"] == analysis.result_id
            assert exact.json()["lineage_verified"] is True
            for headers in ({"X-Test-Workspace": "ws-other"}, {"X-Test-Tenant": "tenant-other"}):
                assert client.get(f"{base}/v2/analysis-results", headers=headers).status_code == 404
                assert client.get(f"{base}/v2/analysis-results/{analysis.result_id}", headers=headers).status_code == 404
            wrong_connection = str(uuid4())
            wrong_run = str(uuid4())
            wrong_ref = "telemetry-endpoint-execution.v2:" + "f" * 64
            assert client.get(f"/api/data-connections/{wrong_connection}/runs/{run_id}/v2/analysis-results").status_code == 404
            assert client.get(f"/api/data-connections/{connection_id}/runs/{wrong_run}/v2/analysis-results").status_code == 404
            assert client.get(f"{base}/v2/analysis-results/{wrong_ref}").status_code == 404
            runtime.execution_identity_version = "concept-keyed.v1"
            assert client.get(f"{base}/v2/analysis-results").status_code == 404
            assert client.get(f"{base}/v2/analysis-results/{analysis.result_id}").status_code == 404
        def read():
            return read_persisted_execution_v2(
                repository=repository, lineage_repository=lineage_repo,
                execution_repository=execution_repo, scope=scope,
                connection_id=connection_id, source_run_id=run_id,
                system_id="system-a", asset_id="pump-1",
                execution_ref=analysis.result_id,
            )
        before = read()
        assert len(before["payload"]["window"]["series"]) == 3
        pressure_series = [item for item in before["payload"]["window"]["series"]
                           if item["canonical_concept_id"] == PRESSURE]
        assert len({item["series_id"] for item in pressure_series}) == 2
        assert len(before["payload"]["relationship_refs"]) == 3
        pair_rows = execution_repo.list_window_pairs(scope, window_id=analysis.window_id)
        pressure_endpoints = {item["series_id"] for item in pressure_series}
        flow_endpoint = next(item["series_id"] for item in before["payload"]["window"]["series"]
                             if item["canonical_concept_id"] == FLOW)
        assert len({row["pair_ref"] for row in pair_rows}) == 3
        assert pressure_endpoints.issubset({row["source_endpoint_id"] for row in pair_rows}
                                            | {row["target_endpoint_id"] for row in pair_rows})
        actual_pairs = {frozenset((row["source_endpoint_id"], row["target_endpoint_id"]))
                        for row in pair_rows}
        assert {frozenset((pressure, flow_endpoint)) for pressure in pressure_endpoints}.issubset(actual_pairs)
        assert read() == before
        with phase4_persistence_suppressed():
            identical = run_post_ingestion_analysis_v2(
                repository=repository, lineage_repository=lineage_repo,
                execution_repository=execution_repo, scope=scope,
                connection_id=connection_id, source_run_id=run_id,
                system_id="system-a", asset_id="pump-1",
                window_start=START, window_end=START + timedelta(minutes=30),
                persisted_authority_digest="a" * 64,
            )
        assert identical.reused_existing and identical.result_id == analysis.result_id

        # A new approved revision cannot rewrite the original execution authority.
        conversion = conversion_contract(source_unit="kPa", canonical_unit="kPa", expected_dimension="pressure")
        repository.save_signal_mapping(
            scope, mapping_id=str(uuid4()), event_id=str(uuid4()),
            connection_id=connection_id, signal_id=signal_ids[0],
            system_id="system-a", asset_id="pump-1",
            canonical_concept_id=PRESSURE, canonical_signal_name="pressure",
            source_unit="kPa", canonical_unit="kPa",
            conversion_id=conversion["conversion_id"], conversion_version=conversion["conversion_version"],
            expected_cadence_seconds=60, source_timezone="UTC",
            provenance="manual", provenance_reason="revision-two",
            actor_id="operator-a", authority_digest="a" * 64,
            mapped_at=START + timedelta(hours=1), expected_revision=1,
            allow_same_concept_endpoints=True,
        )
        assert read() == before
        current = repository.list_analysis_eligible_observations(
            scope, connection_id=connection_id, source_run_id=run_id,
            system_id="system-a", asset_id="pump-1", asset_filter_applied=True,
            window_start=START, window_end=START + timedelta(minutes=30),
            authority_digest="a" * 64,
        )
        assert {str(item["external_signal_id"]) for item in current} == set(signal_ids[1:])
        with phase4_persistence_suppressed():
            replay = run_post_ingestion_analysis_v2(
                repository=repository, lineage_repository=lineage_repo,
                execution_repository=execution_repo, scope=scope,
                connection_id=connection_id, source_run_id=run_id,
                system_id="system-a", asset_id="pump-1",
                window_start=START, window_end=START + timedelta(minutes=30),
                persisted_authority_digest="a" * 64,
            )
        assert replay.reused_existing and replay.result_id == analysis.result_id
        # Replacement and separate hierarchy endpoints never inherit the old ID.
        additional = []
        for index, (other_system, other_asset) in enumerate((
            ("system-a", "pump-1"), ("system-a", "pump-2"),
            ("system-b", "pump-1"),
        ), start=3):
            new_signal = str(uuid4())
            repository.upsert_external_signals(
                scope, connection_id=connection_id,
                signals=[{"signal_id": new_signal,
                          "external_tag_id": f"sensor-{index}",
                          "external_tag_name": f"sensor-{index}", "source_unit": "kPa"}],
            )
            repository.save_signal_mapping(
                scope, mapping_id=str(uuid4()), event_id=str(uuid4()),
                connection_id=connection_id, signal_id=new_signal,
                system_id=other_system, asset_id=other_asset,
                canonical_concept_id=PRESSURE, canonical_signal_name="pressure",
                source_unit="kPa", canonical_unit="kPa",
                conversion_id=conversion["conversion_id"],
                conversion_version=conversion["conversion_version"],
                expected_cadence_seconds=60, source_timezone="UTC",
                provenance="manual", provenance_reason="distinct-endpoint",
                actor_id="operator-a", authority_digest="a" * 64,
                mapped_at=START + timedelta(hours=2),
                allow_same_concept_endpoints=True,
            )
            additional.append(new_signal)
        authority = repository.list_analysis_endpoint_authority(
            scope, connection_id=connection_id, external_signal_ids=additional,
        )
        assert {(item["system_id"], item["asset_id"]) for item in authority} == {
            ("system-a", "pump-1"), ("system-a", "pump-2"),
            ("system-b", "pump-1"),
        }
        assert read() == before
        repository.disable_signal_mapping(
            scope, connection_id=connection_id, signal_id=signal_ids[1],
            expected_revision=1, actor_id="operator-a", event_id=str(uuid4()),
            reason="retired-physical-sensor",
        )
        assert read() == before
        with pytest.raises(psycopg.errors.RaiseException, match="telemetry_mapping_authority_immutable"):
            with psycopg.connect(test_dsn) as connection:
                connection.execute(
                    "UPDATE telemetry.signal_mappings SET authority_digest = %s WHERE id = %s::UUID",
                    ("b" * 64, mappings[0]["id"]),
                )
        class TamperedAuthority:
            def __getattr__(self, name):
                return getattr(repository, name)

            def list_historical_analysis_endpoint_authority(self, *args, **kwargs):
                rows = repository.list_historical_analysis_endpoint_authority(*args, **kwargs)
                rows[0]["authority_digest"] = "b" * 64
                return rows

        with pytest.raises(EndpointExecutionV2Error, match="history_mismatch"):
            read_persisted_execution_v2(
                repository=TamperedAuthority(), lineage_repository=lineage_repo,
                execution_repository=execution_repo, scope=scope,
                connection_id=connection_id, source_run_id=run_id,
                system_id="system-a", asset_id="pump-1",
                execution_ref=analysis.result_id,
            )
        app, _ = build_client(tmp_path)
        with TestClient(app, base_url="https://testserver") as client:
            runtime = app.state.telemetry_runtime
            runtime.repository = TamperedAuthority()
            runtime.execution_identity_version = "physical-endpoint-keyed.v2"
            base = f"/api/data-connections/{connection_id}/runs/{run_id}/v2/analysis-results"
            assert client.get(base).status_code == 404
            assert client.get(f"{base}/{analysis.result_id}").status_code == 404
        assert read() == before
    finally:
        with psycopg.connect(DSN, autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
