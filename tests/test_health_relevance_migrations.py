from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from app.services import runtime_db


HEALTH_RELEVANCE_TABLES = {
    "validated_outcomes",
    "validated_outcome_links",
    "health_relevance_versions",
    "health_relevance_contributions",
}


def _insert(connection: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def _outcome_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "outcome_revision_id": "outcome-revision-1",
        "outcome_id": "outcome-1",
        "revision": 1,
        "supersedes_revision_id": None,
        "scope_storage_id": "scope-a",
        "tenant_id": "tenant-a",
        "facility_id": "facility-a",
        "system_id": "system-a",
        "asset_equipment_id": "asset-a",
        "outcome_schema_version": "1",
        "outcome_type": "confirmed_degraded_condition",
        "outcome_family": "degradation_or_fault",
        "health_disposition": "degraded",
        "validation_status": "validated",
        "occurred_start_at": "2026-01-01T00:00:00+00:00",
        "occurred_end_at": "2026-01-01T01:00:00+00:00",
        "windows_json": "{}",
        "source_category": "maintenance",
        "source_system": "cmms-test",
        "source_record_id": "work-order-1",
        "source_record_version": "1",
        "source_recorded_at": "2025-12-31T23:00:00+00:00",
        "source_identity_hash": "source-hash-1",
        "reported_by": "reporter@example.com",
        "reported_at": "2026-01-01T02:00:00+00:00",
        "validated_by": "validator@example.com",
        "validated_at": "2026-01-01T03:00:00+00:00",
        "validation_basis_json": "{}",
        "provenance_categories_json": (
            '["independently_documented_outcome","maintenance_system_sourced"]'
        ),
        "authority_tier": "A",
        "reliability_class": "authoritative_independent",
        "reliability_basis_json": "{}",
        "canonical_incident_key": "incident-1",
        "dedup_status": "canonical",
        "possible_duplicate_of_json": "[]",
        "dedup_basis_json": "{}",
        "observation_protocol_json": None,
        "structured_metadata_json": "{}",
        "metadata_schema_version": "1",
        "actor": "validator@example.com",
        "recorded_at": "2026-01-01T03:00:00+00:00",
        "idempotency_key": "outcome-key-1",
        "request_fingerprint": "outcome-request-hash-1",
    }
    values.update(overrides)
    return values


def _link_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "link_revision_id": "link-revision-1",
        "link_id": "link-1",
        "revision": 1,
        "supersedes_revision_id": None,
        "outcome_id": "outcome-1",
        "outcome_revision_id": "outcome-revision-1",
        "scope_storage_id": "scope-a",
        "tenant_id": "tenant-a",
        "facility_id": "facility-a",
        "system_id": "system-a",
        "asset_equipment_id": "asset-a",
        "finding_id": None,
        "evidence_run_id": "evidence-run-1",
        "evidence_package_id": "evidence-package-1",
        "evidence_package_revision": 1,
        "evidence_content_hash": "evidence-hash-1",
        "subject_type": "relationship",
        "subject_id": "relationship-r",
        "subject_mapping_version": "mapping-1",
        "behavioral_model_id": "model-1",
        "behavioral_model_version": "1",
        "behavioral_snapshot_id": "snapshot-1",
        "baseline_reference_id": "baseline-1",
        "baseline_reference_version": "1",
        "telemetry_schema_fingerprint": "telemetry-schema-1",
        "system_configuration_fingerprint": "system-config-1",
        "compatibility_epoch": "epoch-1",
        "context_schema_version": "1",
        "context_json": '{"operating_mode":"high_load"}',
        "context_fingerprint": "context-high-load",
        "context_episode_id": "episode-1",
        "context_source_refs_json": "[]",
        "temporal_role": "outcome_period",
        "window_start_at": "2026-01-01T00:00:00+00:00",
        "window_end_at": "2026-01-01T01:00:00+00:00",
        "link_origin": "human_reviewed",
        "link_confidence": "reviewed",
        "link_basis_json": "{}",
        "linked_by": "validator@example.com",
        "linked_at": "2026-01-01T03:00:00+00:00",
        "retrospective_window_selection": 0,
        "subject_state": "active_changed",
        "observation_basis_json": "{}",
        "link_status": "active",
        "actor": "validator@example.com",
        "recorded_at": "2026-01-01T03:00:00+00:00",
        "idempotency_key": "link-key-1",
        "request_fingerprint": "link-request-hash-1",
    }
    values.update(overrides)
    return values


def _version_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "relevance_version_id": "relevance-version-1",
        "state_key_hash": "state-key-hash-1",
        "version": 1,
        "scope_storage_id": "scope-a",
        "tenant_id": "tenant-a",
        "facility_id": "facility-a",
        "system_id": "system-a",
        "asset_equipment_id": "asset-a",
        "subject_type": "relationship",
        "subject_id": "relationship-r",
        "subject_mapping_version": "mapping-1",
        "context_schema_version": "1",
        "context_json": '{"operating_mode":"high_load"}',
        "context_fingerprint": "context-high-load",
        "compatibility_epoch": "epoch-1",
        "method_class": "bayesian_shrinkage_v1",
        "method_version": "1",
        "method_config_version": "1",
        "input_snapshot_id": "input-snapshot-1",
        "input_manifest_hash": "input-manifest-hash-1",
        "outcome_watermark": "outcome-revision-1",
        "link_watermark": "link-revision-1",
        "previous_version_id": None,
        "raw_outcome_count": 1,
        "eligible_outcome_count": 1,
        "canonical_incident_count": 1,
        "recurrence_count": 1,
        "positive_count": 1,
        "negative_count": 0,
        "neutral_count": 0,
        "comparison_window_count": 0,
        "excluded_count": 0,
        "duplicate_suppressed_count": 0,
        "outcome_family_counts_json": '{"degradation_or_fault":1}',
        "context_metadata_completeness": 1.0,
        "context_episode_count": 1,
        "protocol_completion": None,
        "temporal_consistency": 1.0,
        "tier_a_count": 1,
        "tier_b_count": 0,
        "tier_c_count": 0,
        "tier_d_count": 0,
        "independent_count": 1,
        "neraium_influenced_count": 0,
        "same_actor_validation_count": 0,
        "evidence_state": "insufficient_outcome_evidence",
        "evidence_direction": "positive_dominant",
        "state_reason_codes_json": '["minimum_validated_outcomes"]',
        "freshness_status": "current",
        "method_components_json": '{"alpha":3,"beta":2}',
        "uncertainty_json": '{"credible_interval":null}',
        "outcome_schema_version": "1",
        "threshold_config_version": "1",
        "threshold_config_json": "{}",
        "authority_rules_version": "1",
        "dedup_rules_version": "1",
        "compatibility_rules_version": "1",
        "configuration_hash": "configuration-hash-1",
        "first_evidence_at": "2026-01-01T00:00:00+00:00",
        "last_evidence_at": "2026-01-01T01:00:00+00:00",
        "computed_at": "2026-01-01T04:00:00+00:00",
        "created_by": "health-relevance-test",
        "code_build_version": "test-build-1",
    }
    values.update(overrides)
    return values


def _contribution_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "contribution_id": "contribution-1",
        "relevance_version_id": "relevance-version-1",
        "outcome_id": "outcome-1",
        "outcome_revision_id": "outcome-revision-1",
        "link_id": "link-1",
        "link_revision_id": "link-revision-1",
        "scope_storage_id": "scope-a",
        "tenant_id": "tenant-a",
        "facility_id": "facility-a",
        "system_id": "system-a",
        "asset_equipment_id": "asset-a",
        "subject_type": "relationship",
        "subject_id": "relationship-r",
        "subject_mapping_version": "mapping-1",
        "context_fingerprint": "context-high-load",
        "compatibility_epoch": "epoch-1",
        "canonical_incident_key": "incident-1",
        "outcome_family": "degradation_or_fault",
        "evidence_treatment": "positive",
        "subject_state": "active_changed",
        "temporal_role": "outcome_period",
        "authority_tier": "A",
        "provenance_categories_json": (
            '["independently_documented_outcome","maintenance_system_sourced"]'
        ),
        "method_input_cell": "bayesian_positive",
        "method_component_json": '{"count":1}',
        "reason_code": "eligible_positive_support",
        "finding_id": None,
        "evidence_run_id": "evidence-run-1",
        "evidence_package_id": "evidence-package-1",
        "evidence_content_hash": "evidence-hash-1",
        "behavioral_model_id": "model-1",
        "behavioral_model_version": "1",
        "behavioral_snapshot_id": "snapshot-1",
        "baseline_reference_id": "baseline-1",
        "baseline_reference_version": "1",
        "telemetry_schema_fingerprint": "telemetry-schema-1",
        "system_configuration_fingerprint": "system-config-1",
        "input_manifest_hash": "input-manifest-hash-1",
        "configuration_hash": "configuration-hash-1",
        "created_by": "health-relevance-test",
        "created_at": "2026-01-01T04:00:00+00:00",
    }
    values.update(overrides)
    return values


def test_migration_013_creates_only_the_four_empty_internal_ledgers(
    tmp_path: Path,
) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    runtime_db.init_runtime_db()
    runtime_db.init_runtime_db()

    with runtime_db.db_connection() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert HEALTH_RELEVANCE_TABLES <= tables
        assert connection.execute(
            "SELECT COUNT(*) FROM runtime_schema_migrations "
            "WHERE migration_id = '013_internal_health_relevance'"
        ).fetchone()[0] == 1
        assert all(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            for table in HEALTH_RELEVANCE_TABLES
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert {
            "idx_validated_outcomes_latest",
            "uq_validated_outcomes_source_identity",
            "idx_validated_outcome_links_subject",
            "idx_health_relevance_versions_latest",
            "uq_health_relevance_versions_input",
            "idx_health_relevance_contributions_version",
        } <= indexes

        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        assert {
            f"trg_{table}_{operation}"
            for table in HEALTH_RELEVANCE_TABLES
            for operation in ("no_update", "no_delete")
        } <= triggers


def test_migration_013_upgrades_012_without_backfill_or_existing_schema_changes(
    tmp_path: Path,
) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    runtime_db.init_runtime_db()

    with runtime_db.db_connection() as connection:
        for table in HEALTH_RELEVANCE_TABLES:
            for operation in ("no_update", "no_delete"):
                connection.execute(f"DROP TRIGGER trg_{table}_{operation}")
        for table in (
            "health_relevance_contributions",
            "health_relevance_versions",
            "validated_outcome_links",
            "validated_outcomes",
        ):
            connection.execute(f"DROP TABLE {table}")
        connection.execute(
            "DELETE FROM runtime_schema_migrations "
            "WHERE migration_id = '013_internal_health_relevance'"
        )
        existing_table_sql = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' AND name <> 'runtime_schema_migrations'"
            )
        }
        connection.execute(
            "INSERT INTO finding_cases ("
            "finding_id, source_kind, source_id, source_finding_key, "
            "scope_storage_id, source_snapshot_json, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "existing-finding",
                "evidence_run",
                "existing-run",
                "existing-key",
                "scope-a",
                "{}",
                "2026-01-01T00:00:00+00:00",
            ),
        )

    runtime_db.init_runtime_db()

    with runtime_db.db_connection() as connection:
        assert {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' "
                "AND name <> 'runtime_schema_migrations' "
                "AND name NOT IN ("
                "'validated_outcomes', 'validated_outcome_links', "
                "'health_relevance_versions', 'health_relevance_contributions'"
                ")"
            )
        } == existing_table_sql
        assert connection.execute(
            "SELECT COUNT(*) FROM finding_cases WHERE finding_id = 'existing-finding'"
        ).fetchone()[0] == 1
        assert all(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            for table in HEALTH_RELEVANCE_TABLES
        )


def test_migration_013_enforces_constraints_scope_foreign_keys_and_append_only(
    tmp_path: Path,
) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    runtime_db.init_runtime_db()

    with runtime_db.db_connection() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            _insert(
                connection,
                "validated_outcomes",
                _outcome_values(
                    outcome_revision_id="bad-stable",
                    outcome_id="bad-stable",
                    source_identity_hash="bad-stable",
                    idempotency_key="bad-stable",
                    outcome_type="stable_operation_observation",
                    outcome_family="expected_or_no_fault",
                    health_disposition="stable_observation",
                    observation_protocol_json=None,
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert(
                connection,
                "validated_outcomes",
                _outcome_values(
                    outcome_revision_id="bad-json",
                    outcome_id="bad-json",
                    source_identity_hash="bad-json",
                    idempotency_key="bad-json",
                    structured_metadata_json="not-json",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert(
                connection,
                "validated_outcomes",
                _outcome_values(
                    outcome_revision_id="bad-time",
                    outcome_id="bad-time",
                    source_identity_hash="bad-time",
                    idempotency_key="bad-time",
                    occurred_start_at="2026-01-02T00:00:00+00:00",
                    occurred_end_at="2026-01-01T00:00:00+00:00",
                ),
            )

        _insert(connection, "validated_outcomes", _outcome_values())
        with pytest.raises(sqlite3.IntegrityError):
            _insert(
                connection,
                "validated_outcomes",
                _outcome_values(
                    outcome_revision_id="duplicate-source",
                    outcome_id="duplicate-source",
                    revision=1,
                    idempotency_key="different-idempotency-key",
                ),
            )
        # An immutable correction may retain its source identity, but must
        # explicitly descend from the same logical outcome in the same scope.
        _insert(
            connection,
            "validated_outcomes",
            _outcome_values(
                outcome_revision_id="outcome-revision-2",
                revision=2,
                supersedes_revision_id="outcome-revision-1",
                idempotency_key="outcome-key-2",
                request_fingerprint="outcome-request-hash-2",
            ),
        )
        _insert(
            connection,
            "validated_outcomes",
            _outcome_values(
                outcome_revision_id="outcome-revision-scope-b",
                scope_storage_id="scope-b",
                tenant_id="tenant-b",
                facility_id="facility-b",
                system_id="system-b",
                source_identity_hash="source-hash-b",
                idempotency_key="outcome-key-b",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            _insert(
                connection,
                "validated_outcomes",
                _outcome_values(
                    outcome_revision_id="cross-scope-outcome-revision",
                    revision=2,
                    supersedes_revision_id="outcome-revision-scope-b",
                    source_identity_hash="cross-scope-outcome-source",
                    idempotency_key="cross-scope-outcome-key",
                ),
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert(
                connection,
                "validated_outcome_links",
                _link_values(
                    link_revision_id="cross-scope-link",
                    link_id="cross-scope-link",
                    tenant_id="tenant-b",
                    idempotency_key="cross-scope-link",
                ),
            )
        _insert(connection, "validated_outcome_links", _link_values())
        _insert(
            connection,
            "validated_outcome_links",
            _link_values(
                link_revision_id="link-revision-scope-b",
                scope_storage_id="scope-b",
                tenant_id="tenant-b",
                facility_id="facility-b",
                system_id="system-b",
                outcome_revision_id="outcome-revision-scope-b",
                idempotency_key="link-key-b",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            _insert(
                connection,
                "validated_outcome_links",
                _link_values(
                    link_revision_id="cross-scope-link-revision",
                    revision=2,
                    supersedes_revision_id="link-revision-scope-b",
                    idempotency_key="cross-scope-link-revision-key",
                ),
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert(
                connection,
                "health_relevance_versions",
                _version_values(
                    relevance_version_id="third-method-version",
                    state_key_hash="third-method-state-key",
                    method_class="third_method",
                ),
            )
        _insert(connection, "health_relevance_versions", _version_values())
        _insert(
            connection,
            "health_relevance_versions",
            _version_values(
                relevance_version_id="relevance-version-scope-b",
                state_key_hash="state-key-hash-b",
                scope_storage_id="scope-b",
                tenant_id="tenant-b",
                facility_id="facility-b",
                system_id="system-b",
                input_snapshot_id="input-snapshot-b",
                input_manifest_hash="input-manifest-hash-b",
            ),
        )
        with pytest.raises(sqlite3.IntegrityError):
            _insert(
                connection,
                "health_relevance_versions",
                _version_values(
                    relevance_version_id="cross-scope-relevance-version",
                    version=2,
                    previous_version_id="relevance-version-scope-b",
                    input_snapshot_id="cross-scope-input-snapshot",
                    input_manifest_hash="cross-scope-input-manifest",
                ),
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert(
                connection,
                "health_relevance_contributions",
                _contribution_values(
                    contribution_id="cross-system-contribution",
                    system_id="system-b",
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            _insert(
                connection,
                "health_relevance_contributions",
                _contribution_values(
                    contribution_id="null-method-cell-contribution",
                    method_input_cell=None,
                ),
            )
        _insert(
            connection,
            "health_relevance_contributions",
            _contribution_values(),
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

        for table, identity_column in (
            ("validated_outcomes", "outcome_revision_id"),
            ("validated_outcome_links", "link_revision_id"),
            ("health_relevance_versions", "relevance_version_id"),
            ("health_relevance_contributions", "contribution_id"),
        ):
            identity = connection.execute(
                f"SELECT {identity_column} FROM {table} LIMIT 1"
            ).fetchone()[0]
            with pytest.raises(sqlite3.IntegrityError, match=f"{table}_append_only"):
                connection.execute(
                    f"UPDATE {table} SET {identity_column} = {identity_column} "
                    f"WHERE {identity_column} = ?",
                    (identity,),
                )
            with pytest.raises(sqlite3.IntegrityError, match=f"{table}_append_only"):
                connection.execute(
                    f"DELETE FROM {table} WHERE {identity_column} = ?",
                    (identity,),
                )
