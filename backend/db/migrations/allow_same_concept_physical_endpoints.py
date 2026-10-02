"""Permit distinct governed endpoints to share a concept; retain endpoint uniqueness."""

from __future__ import annotations

from typing import Any

MIGRATION_ID = "010_allow_same_concept_physical_endpoints"
REQUIRED_MIGRATIONS = ("009_create_endpoint_analysis_executions_v2",)
CONCEPT_INDEX = "ux_telemetry_signal_mapping_canonical_hierarchy"
ENDPOINT_INDEX = "ux_telemetry_signal_mapping_enabled"
AUTHORITY_TRIGGER = "trg_telemetry_signal_mapping_authority_immutable"

DDL = """
CREATE FUNCTION telemetry.reject_signal_mapping_authority_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'telemetry_mapping_history_immutable';
    END IF;
    IF (OLD.enabled = FALSE AND NEW.enabled = TRUE)
       OR (to_jsonb(NEW) - 'enabled' - 'provenance_reason' - 'updated_at')
          IS DISTINCT FROM
          (to_jsonb(OLD) - 'enabled' - 'provenance_reason' - 'updated_at') THEN
        RAISE EXCEPTION 'telemetry_mapping_authority_immutable';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_telemetry_signal_mapping_authority_immutable
BEFORE UPDATE OR DELETE ON telemetry.signal_mappings
FOR EACH ROW EXECUTE FUNCTION telemetry.reject_signal_mapping_authority_mutation();
"""


def apply(conn: Any) -> None:
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (MIGRATION_ID,))
        cursor.execute(
            "SELECT migration_id FROM telemetry.schema_migrations WHERE migration_id = ANY(%s)",
            (list(REQUIRED_MIGRATIONS),),
        )
        if set(REQUIRED_MIGRATIONS) - {str(row[0]) for row in cursor.fetchall()}:
            raise RuntimeError("same_concept_endpoint_prerequisite_missing")
        cursor.execute("SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s", (MIGRATION_ID,))
        if cursor.fetchone() is None:
            cursor.execute(f"DROP INDEX telemetry.{CONCEPT_INDEX}")
            cursor.execute(DDL)
            cursor.execute("INSERT INTO telemetry.schema_migrations (migration_id) VALUES (%s)", (MIGRATION_ID,))
    conn.commit()


run = apply


def verify(conn: Any) -> dict[str, str]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s", (MIGRATION_ID,))
        if cursor.fetchone() is None:
            raise RuntimeError("same_concept_endpoint_migration_not_applied")
        cursor.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'telemetry' "
            "AND indexname = ANY(%s)",
            ([CONCEPT_INDEX, ENDPOINT_INDEX],),
        )
        indexes = {str(row[0]): str(row[1]).lower() for row in cursor.fetchall()}
        endpoint_definition = indexes.get(ENDPOINT_INDEX, "")
        if (CONCEPT_INDEX in indexes
                or "create unique index" not in endpoint_definition
                or "(resource_scope_id, external_signal_id)" not in endpoint_definition
                or "where" not in endpoint_definition
                or "enabled" not in endpoint_definition):
            raise RuntimeError("same_concept_endpoint_uniqueness_invalid")
        cursor.execute(
            "SELECT 1 FROM pg_trigger WHERE tgrelid = "
            "'telemetry.signal_mappings'::regclass AND tgname = %s AND NOT tgisinternal",
            (AUTHORITY_TRIGGER,),
        )
        if cursor.fetchone() is None:
            raise RuntimeError("same_concept_endpoint_history_guard_missing")
    return {"migration_id": MIGRATION_ID, "endpoint_index": ENDPOINT_INDEX}


def downgrade(_conn: Any) -> None:
    raise RuntimeError("same_concept_endpoint_downgrade_unsupported")
