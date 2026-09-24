"""006 corruption probes: only an explicitly disposable, initially empty database."""
import os

import pytest

from db.migrations import (
    create_telemetry_connection_tables as foundation,
    seed_telemetry_canonical_signal_concepts as catalog,
    extend_telemetry_ingestion_runtime as ingestion,
    persist_canonical_analysis_results as results,
    preserve_telemetry_source_representation as source,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope='module')
def migration_dsn():
    dsn = os.environ.get('NERAIUM_TEST_MIGRATION_POSTGRES_DSN')
    if not dsn:
        pytest.skip('NERAIUM_TEST_MIGRATION_POSTGRES_DSN must name an empty disposable database')
    import psycopg
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT to_regnamespace('telemetry')").fetchone()[0] is None
        for migration in (foundation, catalog, ingestion, results, source):
            migration.apply(conn)
        source.apply(conn)
        assert source.verify(conn)['migration_id'] == source.MIGRATION_ID
    return dsn


@pytest.fixture
def connection(migration_dsn):
    import psycopg
    with psycopg.connect(migration_dsn) as conn:
        try:
            yield conn
        finally:
            # Every corruption probe is rolled back; no fixture depends on order.
            conn.rollback()


@pytest.mark.parametrize('table', sorted(source.EXPECTED_COLUMNS))
@pytest.mark.parametrize('corruption', [
    'missing_source', 'missing_acquisition', 'source_type', 'acquisition_type',
    'source_not_null', 'acquisition_not_null', 'source_default', 'acquisition_default',
    'generated_acquisition', 'missing_constraint', 'weak_constraint',
    'wrong_version', 'null_bypass', 'unvalidated_constraint',
])
def test_006_fails_closed_for_incomplete_schema(connection, table, corruption):
    from psycopg import sql
    alter = sql.SQL('ALTER TABLE telemetry.{} ').format(sql.Identifier(table))
    # Discover the actual server-generated name; names are not the contract.
    constraint = connection.execute(
        "SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass "
        "AND pg_get_expr(conbin, conrelid) = %s",
        (f'telemetry.{table}', source.EXPECTED_CHECK_EXPRESSION),
    ).fetchone()[0]
    if corruption in {'source_type', 'missing_constraint', 'weak_constraint',
                       'wrong_version', 'null_bypass', 'unvalidated_constraint'}:
        connection.execute(alter + sql.SQL('DROP CONSTRAINT {}').format(sql.Identifier(constraint)))
    operations = {
        'missing_source': 'DROP COLUMN source_representation',
        'missing_acquisition': 'DROP COLUMN acquired_at_utc',
        'source_type': 'ALTER COLUMN source_representation TYPE text USING source_representation::text',
        'acquisition_type': 'ALTER COLUMN acquired_at_utc TYPE timestamp without time zone',
        'source_not_null': 'ALTER COLUMN source_representation SET NOT NULL',
        'acquisition_not_null': 'ALTER COLUMN acquired_at_utc SET NOT NULL',
        'source_default': "ALTER COLUMN source_representation SET DEFAULT '{}'::jsonb",
        'acquisition_default': 'ALTER COLUMN acquired_at_utc SET DEFAULT now()',
        'generated_acquisition': 'DROP COLUMN acquired_at_utc, ADD COLUMN acquired_at_utc '
                                 'TIMESTAMPTZ GENERATED ALWAYS AS (NULL::timestamptz) STORED',
        'weak_constraint': "ADD CHECK (source_representation IS NULL OR jsonb_typeof(source_representation)='object')",
        'wrong_version': "ADD CHECK (source_representation IS NULL OR (jsonb_typeof(source_representation)='object' "
                         "AND source_representation->>'contract_version'='wrong-version') IS TRUE)",
        'null_bypass': "ADD CHECK (source_representation IS NULL OR (jsonb_typeof(source_representation)='object' "
                       "AND source_representation->>'contract_version'='neraium.telemetry.source-representation/v1'))",
        'unvalidated_constraint': 'ADD CHECK ' + source.EXPECTED_CHECK_EXPRESSION + ' NOT VALID',
    }
    if corruption in operations:
        connection.execute(alter + sql.SQL(operations[corruption]))
    with pytest.raises(RuntimeError, match='telemetry_source_representation_.*incomplete'):
        source.verify(connection)


def test_006_requires_ledger_entry(connection):
    connection.execute('DELETE FROM telemetry.schema_migrations WHERE migration_id=%s', (source.MIGRATION_ID,))
    with pytest.raises(RuntimeError, match='migration_not_applied'):
        source.verify(connection)


def test_006_accepts_pristine_and_cosmetically_equivalent_checks(connection):
    from psycopg import sql
    assert source.verify(connection)['migration_id'] == source.MIGRATION_ID
    for table in source.EXPECTED_COLUMNS:
        row = connection.execute(
            'SELECT conname FROM pg_constraint WHERE conrelid=%s::regclass '
            'AND pg_get_expr(conbin,conrelid)=%s',
            (f'telemetry.{table}', source.EXPECTED_CHECK_EXPRESSION),
        ).fetchone()
        connection.execute(sql.SQL('ALTER TABLE telemetry.{} DROP CONSTRAINT {}').format(
            sql.Identifier(table), sql.Identifier(row[0]),
        ))
        connection.execute(sql.SQL('ALTER TABLE telemetry.{} ADD CONSTRAINT custom_check CHECK (\n'
            ' (("source_representation") IS NULL) OR (((\n'
            ' jsonb_typeof(("source_representation")) = CAST(\'object\' AS text)\n'
            ' AND (("source_representation") ->> \'contract_version\') =\n'
            ' \'neraium.telemetry.source-representation/v1\'\n'
            ' ))) IS TRUE )').format(sql.Identifier(table)))
    assert source.verify(connection)['migration_id'] == source.MIGRATION_ID


def test_006_preexisting_unconstrained_columns_do_not_certify(connection):
    from psycopg import sql
    for table in source.EXPECTED_COLUMNS:
        connection.execute(sql.SQL('ALTER TABLE telemetry.{} DROP COLUMN source_representation, '
                                   'ADD COLUMN source_representation JSONB').format(sql.Identifier(table)))
    # This is also the resulting schema when ADD COLUMN IF NOT EXISTS skips an
    # already-present nullable JSONB column: the ledger cannot make it complete.
    with pytest.raises(RuntimeError, match='constraint_incomplete'):
        source.verify(connection)
