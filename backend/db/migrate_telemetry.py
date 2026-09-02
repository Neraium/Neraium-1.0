"""Apply and verify the forward-only production telemetry schema."""

from __future__ import annotations

import os

import psycopg

from app.core.config import get_settings
from db.migrations.create_telemetry_connection_tables import apply as apply_002
from db.migrations.create_telemetry_connection_tables import verify as verify_002
from db.migrations.extend_telemetry_ingestion_runtime import apply as apply_004
from db.migrations.extend_telemetry_ingestion_runtime import verify as verify_004
from db.migrations.persist_canonical_analysis_results import apply as apply_005
from db.migrations.persist_canonical_analysis_results import verify as verify_005
from db.migrations.seed_telemetry_canonical_signal_concepts import apply as apply_003
from db.migrations.seed_telemetry_canonical_signal_concepts import verify as verify_003


def migrate() -> None:
    """Apply migrations in dependency order and verify the resulting schema."""
    database_url = str(get_settings().telemetry_database_url or "").strip()
    if not database_url:
        raise RuntimeError("NERAIUM_TELEMETRY_DATABASE_URL is required")

    with psycopg.connect(database_url, connect_timeout=5) as connection:
        for migration in (apply_002, apply_003, apply_004, apply_005):
            migration(connection)
        for verifier in (verify_002, verify_003, verify_004, verify_005):
            verifier(connection)

    application_database_url = str(
        os.getenv("NERAIUM_TELEMETRY_APPLICATION_DATABASE_URL", "")
    ).strip()
    if application_database_url:
        with psycopg.connect(application_database_url, connect_timeout=5) as connection:
            for verifier in (verify_002, verify_003, verify_004, verify_005):
                verifier(connection)


if __name__ == "__main__":
    migrate()
