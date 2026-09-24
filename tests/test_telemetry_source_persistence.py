"""Focused real PostgreSQL test; requires an explicitly disposable test database."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
import json
from collections.abc import Mapping

import pytest

from app.services.telemetry_ingestion import validate_source_representation
from app.services.telemetry_repository import PostgreSQLTelemetryRepository
from app.services.telemetry_scheduler import _observation_record, _rejection_record
from db.migrations import (
    create_telemetry_connection_tables as foundation,
    seed_telemetry_canonical_signal_concepts as catalog,
    extend_telemetry_ingestion_runtime as ingestion,
    persist_canonical_analysis_results as results,
    preserve_telemetry_source_representation as source,
)
from test_telemetry_ingestion import CONNECTION_ID, RUN_ID, NOW, mapping, scope, raw, prepare


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    return value


@pytest.mark.integration
def test_source_provenance_postgres_roundtrip_and_historical_compatibility(scope, mapping):
    dsn = os.environ.get('NERAIUM_TEST_SOURCE_POSTGRES_DSN')
    if not dsn:
        pytest.skip('NERAIUM_TEST_SOURCE_POSTGRES_DSN must name a disposable database')
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb

    lease = '00000000-0000-0000-0000-000000000003'
    now = datetime.now(UTC)
    authority = scope.as_public_dict()

    def insert(conn, table, values):
        # Identifiers are test-owned; parameters always carry values.
        with conn.cursor() as cur:
            cur.execute(sql.SQL('INSERT INTO telemetry.{} ({}) VALUES ({})').format(
                sql.Identifier(table),
                sql.SQL(',').join(map(sql.Identifier, values)),
                sql.SQL(',').join(sql.Placeholder() for _ in values),
            ), tuple(values.values()))

    with psycopg.connect(dsn) as conn:
        # This test intentionally refuses an existing telemetry schema.
        assert conn.execute("SELECT to_regnamespace('telemetry')").fetchone()[0] is None
        for migration in (foundation, catalog, ingestion, results):
            migration.apply(conn)
        insert(conn, 'data_connections', {
            **authority, 'id': CONNECTION_ID, 'name': 'source-test',
            'connector_type': 'https_telemetry', 'timezone': 'UTC',
            'polling_interval_seconds': 60, 'created_by': 'test', 'updated_by': 'test',
            'lease_owner': 'test-worker', 'lease_token': lease,
            'lease_expires_at': now + timedelta(hours=1),
        })
        insert(conn, 'canonical_signal_concepts', {
            'id': mapping.canonical_signal_id, 'canonical_name': 'test_temperature',
            'display_name': 'Test temperature', 'physical_dimension': 'temperature',
            'canonical_unit': mapping.canonical_unit, 'taxonomy_version': 1,
        })
        insert(conn, 'external_signals', {
            **authority, 'id': mapping.external_signal_id, 'connection_id': CONNECTION_ID,
            'external_tag_id': mapping.external_tag_id, 'external_tag_name': 'Temperature',
        })
        insert(conn, 'signal_mappings', {
            **authority, 'id': mapping.mapping_id, 'connection_id': CONNECTION_ID,
            'external_signal_id': mapping.external_signal_id, 'system_id': mapping.system_id,
            'asset_id': mapping.asset_id, 'canonical_concept_id': mapping.canonical_signal_id,
            'canonical_signal_name': mapping.canonical_signal_name, 'source_unit': mapping.source_unit,
            'canonical_unit': mapping.canonical_unit, 'conversion_id': mapping.conversion_id,
            'conversion_version': mapping.conversion_version, 'source_timezone': mapping.source_timezone,
            'enabled': True, 'provenance': mapping.provenance, 'mapped_by': mapping.actor_id,
            'mapped_at': mapping.mapped_at, 'authority_digest': mapping.authority_digest,
            'revision': mapping.revision,
        })
        insert(conn, 'ingestion_runs', {
            **authority, 'id': RUN_ID, 'connection_id': CONNECTION_ID,
            'mode': 'incremental', 'status': 'running', 'lease_token': lease, 'started_at': now,
        })
        old = prepare(scope=scope, mapping=mapping, observations=(raw(event_id='historical'),)).observations[0]
        old_record = {**_observation_record(old), **authority, 'ingestion_run_id': RUN_ID}
        columns = {row[0] for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='telemetry' AND table_name='normalized_observations'"
        )}
        old_record = {key: value for key, value in old_record.items() if key in columns}
        old_record['reason_codes'] = list(old_record['reason_codes'])
        for key in ('original_value', 'source_metadata'):
            old_record[key] = Jsonb(_plain(old_record[key]))
        insert(conn, 'normalized_observations', old_record)
        old_id = old_record['id']
        before = conn.execute('SELECT to_jsonb(o) FROM telemetry.normalized_observations o').fetchone()[0]
        conn.commit()
        source.apply(conn)
        source.apply(conn)
        assert source.verify(conn)['migration_id'] == source.MIGRATION_ID
        after = conn.execute('SELECT to_jsonb(o) FROM telemetry.normalized_observations o').fetchone()[0]
        assert after.pop('source_representation') is None
        assert after.pop('acquired_at_utc') is None
        assert after == before

    acquired = NOW - timedelta(minutes=1)
    inputs = (
        replace(raw(value=Decimal('9007199254740993.000'), event_id='new'),
                acquired_at_utc=acquired, native_quality=192),
        raw(event_id='missing-quality', quality=None),
        replace(raw(event_id='structured-good', quality="['good']"), native_quality=['good']),
        replace(raw(event_id='structured-bad', quality="['bad']"), native_quality=['bad']),
        replace(raw(event_id='suspect', quality='suspect'), acquired_at_utc=acquired, native_quality=64),
        raw(event_id='bad', quality='bad'),
        raw(event_id='unknown', quality='unknown'),
        raw(event_id='boolean', value=True),
        raw(event_id='state', value='RUNNING'),
        raw(event_id='nan', value=float('nan')),
        raw(event_id='infinity', value=float('inf')),
        raw(event_id='negative-infinity', value=float('-inf')),
    )
    prepared = prepare(scope=scope, mapping=mapping, observations=inputs)
    repository = PostgreSQLTelemetryRepository(lambda: psycopg.connect(dsn))
    observations = [_observation_record(item) for item in prepared.observations]
    rejections = [_rejection_record(item) for item in prepared.rejections]
    counts = repository.persist_ingestion_page(
        scope, connection_id=CONNECTION_ID, run_id=RUN_ID, lease_token=lease,
        checkpoint_mode='incremental', expected_checkpoint_revision=0,
        cursor_payload={}, high_water_at=NOW, observations=observations, rejections=rejections,
    )
    assert counts['accepted'] == 3
    assert counts['rejected'] == 9
    stored = repository.list_observations(scope, connection_id=CONNECTION_ID)
    by_event = {row['provider_event_id']: row for row in stored}
    assert str(by_event['historical']['id']) == old_id
    assert by_event['historical']['source_representation'] is None
    expected = validate_source_representation(prepared.observations[0].source_representation)
    assert by_event['new']['source_representation'] == expected
    assert Decimal(expected['value']['value']) == Decimal('9007199254740993.000')
    assert expected['value']['type'] == 'decimal'
    assert expected['native_quality'] == {'type': 'int', 'value': '192'}
    assert by_event['new']['normalized_value'] == prepared.observations[0].normalized_value
    assert by_event['new']['acquired_at_utc'] == acquired
    assert acquired != by_event['new']['observed_at_utc']
    assert acquired != by_event['new']['ingested_at_utc']
    assert by_event['missing-quality']['acquired_at_utc'] is None
    assert by_event['missing-quality']['quality_state'] == 'good'
    structured = by_event['structured-good']['source_representation']
    assert structured['quality_state'] == 'unknown'
    assert structured['native_quality']['type'] == 'json'
    assert json.loads(structured['native_quality']['value']) == ['good']
    assert by_event['structured-good']['quality_state'] == 'good'
    errors = repository.list_ingestion_errors(scope, connection_id=CONNECTION_ID)
    errors_by_event = {row['provider_event_id']: row for row in errors}
    assert errors_by_event['suspect']['source_representation']['quality_state'] == 'uncertain'
    assert errors_by_event['suspect']['source_representation']['native_quality']['value'] == '64'
    assert errors_by_event['suspect']['acquired_at_utc'] == acquired
    structured_rejected = errors_by_event['structured-bad']['source_representation']
    assert structured_rejected['quality_state'] == 'unknown'
    assert json.loads(structured_rejected['native_quality']['value']) == ['bad']
    assert errors_by_event['structured-bad']['quality_state'] == 'invalid_value'
    assert errors_by_event['bad']['source_representation']['quality_state'] == 'bad'
    assert errors_by_event['unknown']['source_representation']['quality_state'] == 'unknown'
    assert errors_by_event['boolean']['source_representation']['value'] == {'type': 'bool', 'value': True}
    assert errors_by_event['state']['source_representation']['value'] == {'type': 'str', 'value': 'RUNNING'}
    for event, marker in (('nan', 'nan'), ('infinity', 'infinity'), ('negative-infinity', '-infinity')):
        assert errors_by_event[event]['source_representation']['value'] == {'type': 'float', 'value': marker}
        assert errors_by_event[event]['quality_state'] == 'invalid_value'
    analytical = repository.list_analysis_eligible_observations(
        scope, connection_id=CONNECTION_ID, source_run_id=RUN_ID,
    )
    assert len(analytical) == 4
    assert all('source_representation' not in item and 'acquired_at_utc' not in item for item in analytical)
    # Database-conflict retry keeps original admitted identity/provenance.
    repository.persist_ingestion_page(
        scope, connection_id=CONNECTION_ID, run_id=RUN_ID, lease_token=lease,
        checkpoint_mode='incremental', expected_checkpoint_revision=1,
        cursor_payload={}, high_water_at=NOW, observations=observations, rejections=rejections,
    )
    assert repository.list_observations(scope, connection_id=CONNECTION_ID) == stored
    repeated = repository.list_ingestion_errors(scope, connection_id=CONNECTION_ID)
    assert all(row['source_representation'] is not None for row in repeated)
