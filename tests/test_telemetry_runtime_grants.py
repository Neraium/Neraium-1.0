"""Live privilege contract for the production telemetry runtime identity."""

import os

import pytest


RUNTIME_DSN = os.environ.get("NERAIUM_TEST_TELEMETRY_RUNTIME_DSN", "").strip()
pytestmark = pytest.mark.skipif(
    not RUNTIME_DSN, reason="NERAIUM_TEST_TELEMETRY_RUNTIME_DSN is not configured"
)


def test_runtime_identity_cannot_modify_telemetry_migration_ledger() -> None:
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(RUNTIME_DSN, connect_timeout=5) as connection:
        role, schema_create, ledger_select, ledger_insert, ledger_update, ledger_delete, ledger_truncate = (
            connection.execute(
                """
                SELECT current_user,
                       has_schema_privilege(current_user, 'telemetry', 'CREATE'),
                       has_table_privilege(current_user, 'telemetry.schema_migrations', 'SELECT'),
                       has_table_privilege(current_user, 'telemetry.schema_migrations', 'INSERT'),
                       has_table_privilege(current_user, 'telemetry.schema_migrations', 'UPDATE'),
                       has_table_privilege(current_user, 'telemetry.schema_migrations', 'DELETE'),
                       has_table_privilege(current_user, 'telemetry.schema_migrations', 'TRUNCATE')
                """
            ).fetchone()
        )
    assert role == "neraium_telemetry_runtime"
    assert ledger_select is True
    assert (schema_create, ledger_insert, ledger_update, ledger_delete, ledger_truncate) == (
        False, False, False, False, False,
    )
