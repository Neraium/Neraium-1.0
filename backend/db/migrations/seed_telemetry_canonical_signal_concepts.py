"""Seed Neraium's initial versioned canonical telemetry taxonomy."""

from __future__ import annotations

from typing import Any

from app.services.canonical_signal_catalog import CANONICAL_SIGNAL_CONCEPTS_V1


MIGRATION_ID = "003_seed_telemetry_canonical_signal_concepts_v1"


def _verify_catalog_rows(cursor: Any) -> int:
    expected = {concept.concept_id: concept for concept in CANONICAL_SIGNAL_CONCEPTS_V1}
    cursor.execute(
        """
        SELECT id::TEXT, canonical_name, display_name, physical_dimension,
               canonical_unit, description, taxonomy_version, active
        FROM telemetry.canonical_signal_concepts
        WHERE id = ANY(%s::UUID[])
        """,
        (sorted(expected),),
    )
    rows = cursor.fetchall()
    if len(rows) != len(expected):
        raise RuntimeError("telemetry_canonical_catalog_incomplete")
    for row in rows:
        concept = expected.get(str(row[0]))
        if concept is None or tuple(row[1:]) != (
            concept.canonical_name,
            concept.display_name,
            concept.physical_dimension,
            concept.canonical_unit,
            concept.description,
            concept.taxonomy_version,
            True,
        ):
            raise RuntimeError("telemetry_canonical_catalog_mismatch")
    return len(rows)


def apply(conn: Any) -> None:
    """Insert immutable v1 product concepts without changing customer data."""
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (MIGRATION_ID,))
            cursor.execute(
                "SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s",
                (MIGRATION_ID,),
            )
            if cursor.fetchone():
                _verify_catalog_rows(cursor)
                conn.commit()
                return
            for concept in CANONICAL_SIGNAL_CONCEPTS_V1:
                cursor.execute(
                    """
                    INSERT INTO telemetry.canonical_signal_concepts (
                        id, canonical_name, display_name, physical_dimension,
                        canonical_unit, description, taxonomy_version, active
                    ) VALUES (%s::UUID, %s, %s, %s, %s, %s, %s, TRUE)
                    ON CONFLICT (canonical_name, taxonomy_version) DO NOTHING
                    """,
                    (
                        concept.concept_id,
                        concept.canonical_name,
                        concept.display_name,
                        concept.physical_dimension,
                        concept.canonical_unit,
                        concept.description,
                        concept.taxonomy_version,
                    ),
                )
            _verify_catalog_rows(cursor)
            cursor.execute(
                "INSERT INTO telemetry.schema_migrations (migration_id) VALUES (%s)",
                (MIGRATION_ID,),
            )
    except Exception:
        conn.rollback()
        raise
    conn.commit()


run = apply


def verify(conn: Any) -> dict[str, Any]:
    """Verify every shipped v1 identity and semantic contract."""
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM telemetry.schema_migrations WHERE migration_id = %s",
            (MIGRATION_ID,),
        )
        if not cursor.fetchone():
            raise RuntimeError("telemetry_canonical_catalog_migration_not_applied")
        concept_count = _verify_catalog_rows(cursor)
    return {
        "migration_id": MIGRATION_ID,
        "taxonomy_version": 1,
        "concept_count": concept_count,
    }
