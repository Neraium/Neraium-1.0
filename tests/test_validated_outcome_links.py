from __future__ import annotations

import pytest

from app.services.dataset_scope import build_dataset_scope
from app.services.runtime_db import db_connection
from app.services.validated_outcomes import (
    HealthRelevanceAccessError,
    HealthRelevanceConflictError,
    HealthRelevanceValidationError,
    append_outcome_link_revision,
    append_outcome_revision,
    authorize_internal_access,
    context_fingerprint,
    get_latest_link_revision,
    get_link_revision,
    list_latest_links,
)


def _access(*, tenant="tenant-a", facility="facility-a", system="system-a"):
    scope = build_dataset_scope(
        tenant_id=tenant,
        user_id=f"service@{tenant}",
        workspace_id=f"ws-{facility}",
    )
    return authorize_internal_access(
        scope=scope,
        facility_id=facility,
        system_id=system,
        actor="health-relevance-service",
        auth_source="service_token",
        role="admin",
        workspace_authorized=True,
    )


def _outcome(access, *, outcome_id="outcome-1", stable=False):
    payload = {
        "outcome_id": outcome_id,
        "outcome_type": "confirmed_fault",
        "health_disposition": "fault_confirmed",
        "validation_status": "validated",
        "asset_equipment_id": "asset-a",
        "occurred_start_at": "2026-01-02T00:00:00+00:00",
        "occurred_end_at": "2026-01-02T01:00:00+00:00",
        "source_category": "maintenance",
        "source_system": "cmms-test",
        "source_record_id": outcome_id,
        "source_record_version": "1",
        "source_recorded_at": "2026-01-01T22:00:00+00:00",
        "reported_by": "reporter@example.com",
        "reported_at": "2026-01-02T02:00:00+00:00",
        "validated_by": "validator@example.com",
        "validated_at": "2026-01-02T03:00:00+00:00",
        "validation_basis": {"independent_of_neraium": True},
        "provenance_categories": [
            "independently_documented_outcome",
            "maintenance_system_sourced",
        ],
        "dedup_basis": {"external_incident_id": outcome_id},
    }
    if stable:
        payload.update(
            {
                "outcome_type": "stable_operation_observation",
                "health_disposition": "stable_observation",
                "observation_protocol": {
                    "protocol_id": "stable-protocol",
                    "protocol_version": "1",
                    "window_declared_at": "2026-01-01T00:00:00+00:00",
                    "expected_sample_count": 10,
                    "observed_sample_count": 8,
                    "scheduled_windows": 5,
                    "completed_windows": 4,
                    "completed": True,
                    "context_complete": True,
                    "expected_signal_reference_set": ["relationship-r"],
                    "sampling_cadence": "1m",
                    "subject_evaluability_rule": "reference-and-signal-present",
                    "basis": "predeclared_protocol",
                },
            }
        )
    return append_outcome_revision(access, payload, idempotency_key=f"create:{outcome_id}")


def _link(outcome, **overrides):
    context = {"operating_mode": "high_load", "load_band": "high"}
    configuration = "configuration-v1"
    payload = {
        "link_id": f"link-{outcome['outcome_id']}",
        "outcome_id": outcome["outcome_id"],
        "outcome_revision_id": outcome["outcome_revision_id"],
        "asset_equipment_id": "asset-a",
        "evidence_content_hash": "evidence-package-sha256",
        "evidence_package_id": "evidence-package-1",
        "evidence_package_revision": 1,
        "subject_type": "relationship",
        "subject_id": "relationship-r",
        "subject_mapping_version": "mapping-v1",
        "behavioral_model_id": "behavioral-model-1",
        "behavioral_model_version": "model-version-1",
        "behavioral_snapshot_id": "behavioral-snapshot-1",
        "baseline_reference_id": "baseline-1",
        "baseline_reference_version": "reference-version-1",
        "telemetry_schema_fingerprint": "telemetry-schema-v1",
        "system_configuration_fingerprint": configuration,
        "compatibility_epoch": "epoch-v1",
        "context_schema_version": "context-v1",
        "context": context,
        "context_fingerprint": context_fingerprint(
            context_schema_version="context-v1",
            context=context,
            system_configuration_fingerprint=configuration,
        ),
        "context_episode_id": "episode-1",
        "context_source_refs": ["facility-context-v1"],
        "temporal_role": "outcome_period",
        "window_start_at": "2026-01-02T00:00:00+00:00",
        "window_end_at": "2026-01-02T01:00:00+00:00",
        "link_origin": "human_reviewed",
        "link_confidence": "reviewed",
        "link_basis": {"association_only": True},
        "linked_by": "validator@example.com",
        "linked_at": "2026-01-02T03:00:00+00:00",
        "subject_state": "active_changed",
        "observation_basis": {"classification": "reviewed"},
        "link_status": "active",
    }
    payload.update(overrides)
    return payload


def test_link_revision_lifecycle_is_append_only_idempotent_and_exactly_bound() -> None:
    access = _access()
    outcome = _outcome(access)
    payload = _link(outcome)
    first = append_outcome_link_revision(access, payload, idempotency_key="link-create")
    replay = append_outcome_link_revision(access, payload, idempotency_key="link-create")
    assert replay == first
    assert first["revision"] == 1
    assert first["context_fingerprint"] == payload["context_fingerprint"]
    assert first["behavioral_model_version"] == "model-version-1"
    assert first["baseline_reference_version"] == "reference-version-1"

    retracted = append_outcome_link_revision(
        access,
        {"link_id": first["link_id"], "link_status": "retracted"},
        idempotency_key="link-retract",
    )
    assert retracted["revision"] == 2
    assert get_latest_link_revision(access, link_id=first["link_id"])["link_status"] == "retracted"
    assert get_link_revision(
        access, link_id=first["link_id"], link_revision_id=first["link_revision_id"]
    )["link_status"] == "active"
    assert list_latest_links(
        access,
        subject_type="relationship",
        subject_id="relationship-r",
        context_fingerprint=first["context_fingerprint"],
        compatibility_epoch="epoch-v1",
        link_status="active",
    ) == []
    with db_connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM validated_outcome_links WHERE link_id = ?",
            (first["link_id"],),
        ).fetchone()["count"] == 2


def test_link_idempotency_conflict_does_not_overwrite_original() -> None:
    access = _access()
    outcome = _outcome(access)
    payload = _link(outcome)
    first = append_outcome_link_revision(access, payload, idempotency_key="same-key")
    with pytest.raises(HealthRelevanceConflictError, match="idempotency_key_reused"):
        append_outcome_link_revision(
            access,
            {**payload, "subject_state": "present_aligned"},
            idempotency_key="same-key",
        )
    assert get_latest_link_revision(access, link_id=first["link_id"])["subject_state"] == "active_changed"


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"asset_equipment_id": "asset-other"}, HealthRelevanceAccessError),
        ({"compatibility_epoch": ""}, HealthRelevanceValidationError),
        ({"behavioral_model_version": None}, HealthRelevanceValidationError),
        ({"baseline_reference_version": None}, HealthRelevanceValidationError),
        ({"telemetry_schema_fingerprint": ""}, HealthRelevanceValidationError),
        ({"system_configuration_fingerprint": ""}, HealthRelevanceValidationError),
        ({"context_fingerprint": "fabricated"}, HealthRelevanceValidationError),
    ],
)
def test_link_fails_closed_for_incomplete_or_mismatched_identity(change, error) -> None:
    access = _access()
    outcome = _outcome(access)
    with pytest.raises(error):
        append_outcome_link_revision(
            access,
            _link(outcome, **change),
            idempotency_key=f"invalid:{next(iter(change))}",
        )


def test_cross_tenant_facility_and_system_linking_is_opaque() -> None:
    owner = _access()
    outcome = _outcome(owner)
    for other in (
        _access(tenant="tenant-b"),
        _access(facility="facility-b"),
        _access(system="system-b"),
    ):
        with pytest.raises(HealthRelevanceAccessError, match="record not found"):
            append_outcome_link_revision(
                other,
                _link(outcome),
                idempotency_key=f"cross:{other.scope.storage_id}:{other.facility_id}:{other.system_id}",
            )


def test_stable_comparison_requires_explicit_stable_outcome_and_protocol() -> None:
    access = _access()
    fault = _outcome(access)
    with pytest.raises(HealthRelevanceValidationError, match="explicit_stable_outcome"):
        append_outcome_link_revision(
            access,
            _link(fault, temporal_role="stable_comparison", subject_state="present_aligned"),
            idempotency_key="fault-not-denominator",
        )

    stable = _outcome(access, outcome_id="stable-1", stable=True)
    linked = append_outcome_link_revision(
        access,
        _link(
            stable,
            temporal_role="stable_comparison",
            subject_state="absent_evaluable",
            link_id="stable-link",
        ),
        idempotency_key="stable-denominator",
    )
    assert linked["temporal_role"] == "stable_comparison"
    assert linked["subject_state"] == "absent_evaluable"


def test_link_to_pending_or_different_outcome_revision_cannot_be_active() -> None:
    access = _access()
    pending_payload = {
        "outcome_id": "pending-outcome",
        "outcome_type": "inspection_result",
        "health_disposition": "indeterminate",
        "validation_status": "pending",
        "occurred_start_at": "2026-01-02T00:00:00+00:00",
        "occurred_end_at": "2026-01-02T01:00:00+00:00",
        "source_category": "inspection",
        "source_system": "inspection-test",
        "source_record_id": "inspection-pending",
        "source_record_version": "1",
        "reported_by": "reporter@example.com",
        "reported_at": "2026-01-02T02:00:00+00:00",
        "provenance_categories": ["inspection_sourced"],
        "dedup_basis": {"external_incident_id": "pending"},
    }
    pending = append_outcome_revision(access, pending_payload, idempotency_key="pending")
    with pytest.raises(HealthRelevanceValidationError, match="validated_outcome"):
        append_outcome_link_revision(
            access,
            _link(pending),
            idempotency_key="pending-link",
        )


def test_existing_finding_or_evidence_anchor_must_match_exact_scope_and_system() -> None:
    access = _access()
    outcome = _outcome(access)
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO evidence_runs(run_id, created_at, status, scope_storage_id, payload_json)
            VALUES (?, ?, 'completed', ?, ?)
            """,
            (
                "run-other-system",
                "2026-01-01T00:00:00+00:00",
                access.scope.storage_id,
                '{"facility_id":"facility-a","system_id":"system-other"}',
            ),
        )
    with pytest.raises(HealthRelevanceAccessError, match="record not found"):
        append_outcome_link_revision(
            access,
            _link(outcome, evidence_run_id="run-other-system"),
            idempotency_key="wrong-lineage",
        )
