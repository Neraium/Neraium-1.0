"""Apply the existing ordered telemetry migrations before starting ECS services."""

from __future__ import annotations

import os

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


def main() -> None:
    url = os.environ.get("NERAIUM_TELEMETRY_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("telemetry_database_not_configured")
    factory = build_telemetry_connection_factory(url)
    for migration in MIGRATIONS:
        with factory() as connection:
            migration.apply(connection)
            migration.verify(connection)


if __name__ == "__main__":
    main()
