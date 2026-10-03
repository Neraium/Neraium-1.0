"""Apply the existing ordered telemetry migrations before starting ECS services."""

from __future__ import annotations

import os
import sys

from app.services.telemetry_runtime import build_telemetry_connection_factory
from db.migrations import (
    allow_same_concept_physical_endpoints,
    create_endpoint_analysis_executions_v2,
    create_relationship_lineage_v2_artifacts,
    create_relationship_temporal_state,
    create_telemetry_connection_tables,
    extend_telemetry_ingestion_runtime,
    persist_canonical_analysis_results,
    preserve_telemetry_source_representation,
    seed_telemetry_canonical_signal_concepts,
)

MIGRATIONS = (
    create_telemetry_connection_tables,
    seed_telemetry_canonical_signal_concepts,
    extend_telemetry_ingestion_runtime,
    persist_canonical_analysis_results,
    preserve_telemetry_source_representation,
    create_relationship_temporal_state,
    create_relationship_lineage_v2_artifacts,
    create_endpoint_analysis_executions_v2,
    allow_same_concept_physical_endpoints,
)


def apply_all(connection) -> None:
    for migration in MIGRATIONS:
        migration.apply(connection)
        migration.verify(connection)
        print(f"schema_migration_complete:telemetry:{migration.MIGRATION_ID}")
    from app.services.schema_verification import verify_postgres
    verify_postgres(connection, "telemetry", "telemetry_v2")


def main() -> int:
    url = os.environ.get("NERAIUM_TELEMETRY_MIGRATION_DSN", "").strip()
    if not url:
        print("telemetry_migration_identity_required", file=sys.stderr)
        return 1
    try:
        factory = build_telemetry_connection_factory(url)
        with factory() as connection:
            apply_all(connection)
    except Exception:
        print("telemetry_schema_migration_failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
