from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from app.services.canonical_signal_catalog import (
    CANONICAL_SIGNAL_CONCEPTS_BY_ID,
    CANONICAL_SIGNAL_CONCEPTS_V1,
)
from db.migrations.seed_telemetry_canonical_signal_concepts import (
    MIGRATION_ID,
    apply,
    verify,
)


class _Cursor:
    def __init__(self, connection: "_Connection") -> None:
        self.connection = connection
        self.one: Any = None
        self.many: list[tuple[Any, ...]] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        normalized = " ".join(sql.split())
        self.one = None
        self.many = []
        if normalized.startswith("SELECT 1 FROM telemetry.schema_migrations"):
            self.one = (1,) if self.connection.applied else None
        elif normalized.startswith("INSERT INTO telemetry.canonical_signal_concepts"):
            conflicts = any(
                row[0] == params[1] and row[5] == params[6]
                for row in self.connection.rows.values()
            )
            if not conflicts:
                self.connection.rows[str(params[0])] = tuple(params[1:7]) + (True,)
        elif normalized.startswith("INSERT INTO telemetry.schema_migrations"):
            self.connection.applied = True
        elif normalized.startswith("SELECT id::TEXT"):
            self.many = [
                (concept_id, *self.connection.rows[concept_id])
                for concept_id in params[0]
                if concept_id in self.connection.rows
            ]

    def fetchone(self) -> Any:
        return self.one

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.many


class _Connection:
    def __init__(self) -> None:
        self.applied = False
        self.rows: dict[str, tuple[Any, ...]] = {}
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_v1_catalog_is_stable_generic_and_versioned() -> None:
    assert len(CANONICAL_SIGNAL_CONCEPTS_V1) == 5
    assert len(CANONICAL_SIGNAL_CONCEPTS_BY_ID) == 5
    assert {item.physical_dimension for item in CANONICAL_SIGNAL_CONCEPTS_V1} == {
        "power", "temperature", "pressure", "flow", "fraction"
    }
    assert all(item.taxonomy_version == 1 for item in CANONICAL_SIGNAL_CONCEPTS_V1)
    assert all(str(UUID(item.concept_id)) == item.concept_id for item in CANONICAL_SIGNAL_CONCEPTS_V1)
    joined = " ".join(item.canonical_name for item in CANONICAL_SIGNAL_CONCEPTS_V1)
    assert not any(term in joined.lower() for term in ("customer", "resort", "vendor", "chwp1"))


def test_seed_migration_is_idempotent_and_verifiable() -> None:
    connection = _Connection()
    apply(connection)
    apply(connection)

    assert connection.applied is True
    assert set(connection.rows) == set(CANONICAL_SIGNAL_CONCEPTS_BY_ID)
    assert connection.commits == 2
    assert verify(connection) == {
        "migration_id": MIGRATION_ID,
        "taxonomy_version": 1,
        "concept_count": 5,
    }


def test_seed_verification_fails_closed_for_missing_or_changed_catalog() -> None:
    missing = _Connection()
    with pytest.raises(RuntimeError, match="migration_not_applied"):
        verify(missing)

    changed = _Connection()
    apply(changed)
    first = next(iter(changed.rows))
    changed.rows[first] = ("changed", *changed.rows[first][1:])
    with pytest.raises(RuntimeError, match="catalog_mismatch"):
        verify(changed)


def test_seed_rolls_back_before_ledger_when_name_version_conflicts_under_wrong_id() -> None:
    connection = _Connection()
    concept = CANONICAL_SIGNAL_CONCEPTS_V1[0]
    connection.rows["00000000-0000-0000-0000-000000000000"] = (
        concept.canonical_name,
        "Conflicting display name",
        concept.physical_dimension,
        concept.canonical_unit,
        concept.description,
        concept.taxonomy_version,
        True,
    )

    with pytest.raises(RuntimeError, match="catalog_incomplete"):
        apply(connection)

    assert connection.applied is False
    assert connection.commits == 0
    assert connection.rollbacks == 1
