from __future__ import annotations

import json

import pytest

from app.services.dataset_scope import build_dataset_scope
from app.services.runtime_db import db_connection
from app.services.validated_outcomes import (
    ApprovedOutcomeSourceRule,
    HealthRelevanceAccessError,
    HealthRelevanceConflictError,
    HealthRelevanceValidationError,
    OutcomeSourceAuthorityPolicy,
    append_outcome_revision,
    authorize_internal_access,
    get_latest_outcome_revision,
    get_outcome_revision,
    list_latest_outcomes,
)


def _access(*, tenant: str = "tenant-a", facility: str = "facility-a", system: str = "system-a"):
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


def _outcome(**overrides):
    payload = {
        "outcome_id": "outcome-1",
        "outcome_type": "confirmed_fault",
        "health_disposition": "fault_confirmed",
        "validation_status": "validated",
        "asset_equipment_id": "asset-a",
        "occurred_start_at": "2026-01-02T00:00:00+00:00",
        "occurred_end_at": "2026-01-02T01:00:00+00:00",
        "source_category": "maintenance",
        "source_system": "cmms-approved-test-source",
        "source_record_id": "work-order-1",
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
        "dedup_basis": {"external_incident_id": "incident-1"},
        "structured_metadata": {"component": "compressor"},
        "reliability_basis": {"source_contract": "fixture-only"},
    }
    payload.update(overrides)
    return payload


def _source_policy(
    *,
    source_system: str,
    source_category: str,
    outcome_type: str,
    rule_id: str = "approved-source-rule",
) -> OutcomeSourceAuthorityPolicy:
    return OutcomeSourceAuthorityPolicy(
        version="approved-source-policy.v1",
        rules=(
            ApprovedOutcomeSourceRule(
                rule_id=rule_id,
                source_system=source_system,
                source_category=source_category,
                allowed_outcome_types=frozenset({outcome_type}),
            ),
        ),
    )


def _stable(**overrides):
    payload = _outcome(
        outcome_id="stable-1",
        outcome_type="stable_operation_observation",
        health_disposition="stable_observation",
        source_record_id="inspection-window-1",
        provenance_categories=[
            "independently_documented_outcome",
            "inspection_sourced",
        ],
        observation_protocol={
            "protocol_id": "stable-observation-protocol",
            "protocol_version": "1",
            "window_declared_at": "2026-01-01T00:00:00+00:00",
            "expected_sample_count": 100,
            "observed_sample_count": 80,
            "sample_coverage": 0.8,
            "scheduled_windows": 5,
            "completed_windows": 4,
            "protocol_completion": 0.8,
            "completed": True,
            "context_complete": True,
            "expected_signal_reference_set": ["relationship-r"],
            "sampling_cadence": "1m",
            "subject_evaluability_rule": "reference-and-signal-present",
            "basis": "predeclared_protocol",
        },
    )
    payload.update(overrides)
    return payload


def test_internal_access_fails_closed_for_non_service_or_non_admin() -> None:
    scope = build_dataset_scope(user_id="operator@example.com", workspace_id="ws-facility-a")
    common = {
        "scope": scope,
        "facility_id": "facility-a",
        "system_id": "system-a",
        "actor": "operator@example.com",
        "workspace_authorized": True,
    }
    with pytest.raises(HealthRelevanceAccessError, match="record not found"):
        authorize_internal_access(**common, auth_source="session", role="admin")
    with pytest.raises(HealthRelevanceAccessError, match="record not found"):
        authorize_internal_access(**common, auth_source="service_token", role="operator")
    with pytest.raises(HealthRelevanceAccessError, match="record not found"):
        authorize_internal_access(
            **{**common, "workspace_authorized": False},
            auth_source="service_token",
            role="admin",
        )


def test_outcome_revision_is_idempotent_append_only_and_retraction_preserves_history() -> None:
    access = _access()
    first = append_outcome_revision(access, _outcome(), idempotency_key="outcome-create")
    replay = append_outcome_revision(access, _outcome(), idempotency_key="outcome-create")
    assert replay == first
    assert first["revision"] == 1
    assert first["authority_tier"] == "B"
    assert first["reliability_basis_json"]["source_authority_policy_version"] == (
        "unconfigured-no-tier-a-sources"
    )
    assert first["reliability_basis_json"]["named_source_system_approved"] is False

    corrected = append_outcome_revision(
        access,
        {
            "outcome_id": first["outcome_id"],
            "validation_status": "validated",
            "structured_metadata": {"component": "compressor", "correction": "serial"},
        },
        idempotency_key="outcome-correct",
    )
    retracted = append_outcome_revision(
        access,
        {"outcome_id": first["outcome_id"], "validation_status": "retracted"},
        idempotency_key="outcome-retract",
    )
    assert corrected["revision"] == 2
    assert retracted["revision"] == 3
    assert retracted["supersedes_revision_id"] == corrected["outcome_revision_id"]
    assert get_outcome_revision(
        access,
        outcome_id=first["outcome_id"],
        outcome_revision_id=first["outcome_revision_id"],
    )["validation_status"] == "validated"
    assert get_latest_outcome_revision(access, outcome_id=first["outcome_id"])[
        "validation_status"
    ] == "retracted"
    assert list_latest_outcomes(access, validation_status="validated") == []
    with db_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM validated_outcomes WHERE outcome_id = ?",
            (first["outcome_id"],),
        ).fetchone()["count"]
    assert count == 3


def test_idempotency_conflict_and_exact_source_replay_are_deterministic_and_audited() -> None:
    access = _access()
    first = append_outcome_revision(access, _outcome(), idempotency_key="first-key")
    with pytest.raises(HealthRelevanceConflictError, match="idempotency_key_reused"):
        append_outcome_revision(
            access,
            _outcome(health_disposition="degraded"),
            idempotency_key="first-key",
        )
    with pytest.raises(HealthRelevanceConflictError, match="source_identity_reused"):
        append_outcome_revision(
            access,
            _outcome(outcome_id="different-logical-outcome", health_disposition="degraded"),
            idempotency_key="second-key",
        )
    with db_connection() as connection:
        actions = {
            row["action"]
            for row in connection.execute(
                "SELECT action FROM audit_events WHERE resource_type = 'validated_outcome'"
            ).fetchall()
        }
    assert "health_relevance.outcome_revision_appended" in actions
    assert "health_relevance.outcome_conflict" in actions


def test_authority_categories_remain_distinct_and_neraium_influence_caps_tier() -> None:
    access = _access()
    policy = _source_policy(
        source_system="cmms-approved-test-source",
        source_category="maintenance",
        outcome_type="confirmed_fault",
    )
    tier_a = append_outcome_revision(
        access,
        _outcome(),
        idempotency_key="tier-a",
        source_authority_policy=policy,
    )
    tier_d = append_outcome_revision(
        access,
        _outcome(
            outcome_id="outcome-tier-d",
            source_record_id="work-order-d",
            provenance_categories=[
                "independently_documented_outcome",
                "maintenance_system_sourced",
                "operator_confirmed_after_neraium_review",
            ],
            validation_basis={
                "independent_of_neraium": False,
                "neraium_reviewed_at": "2025-12-30T00:00:00+00:00",
            },
        ),
        idempotency_key="tier-d",
        source_authority_policy=policy,
    )
    tier_c = append_outcome_revision(
        access,
        _outcome(
            outcome_id="outcome-tier-c",
            source_record_id="work-order-c",
            reported_by="same@example.com",
            validated_by="same@example.com",
        ),
        idempotency_key="tier-c",
    )
    assert tier_a["authority_tier"] == "A"
    assert tier_d["authority_tier"] == "D"
    assert "operator_confirmed_after_neraium_review" in tier_d[
        "provenance_categories_json"
    ]
    assert tier_c["authority_tier"] == "C"


@pytest.mark.parametrize(
    ("outcome_id", "outcome_type", "disposition", "source_category", "provenance"),
    [
        (
            "independent-maintenance",
            "confirmed_maintenance_event",
            "intervention_recorded",
            "maintenance",
            ["independently_documented_outcome", "maintenance_system_sourced"],
        ),
        (
            "independent-inspection",
            "inspection_result",
            "fault_confirmed",
            "inspection",
            ["independently_documented_outcome", "inspection_sourced"],
        ),
        (
            "independent-fault",
            "confirmed_fault",
            "fault_confirmed",
            "fault_record",
            ["independently_documented_outcome"],
        ),
        (
            "independent-repair",
            "repair",
            "intervention_recorded",
            "repair_record",
            ["independently_documented_outcome"],
        ),
    ],
)
def test_named_maintenance_inspection_fault_and_repair_sources_require_explicit_policy(
    outcome_id, outcome_type, disposition, source_category, provenance
) -> None:
    access = _access()
    source_system = f"approved-{source_category}-source"
    unapproved = append_outcome_revision(
        access,
        _outcome(
            outcome_id=f"{outcome_id}-unapproved",
            outcome_type=outcome_type,
            health_disposition=disposition,
            source_category=source_category,
            source_system=source_system,
            source_record_id=f"{outcome_id}-unapproved",
            provenance_categories=provenance,
        ),
        idempotency_key=f"{outcome_id}-unapproved",
    )
    policy = _source_policy(
        source_system=source_system,
        source_category=source_category,
        outcome_type=outcome_type,
        rule_id=f"{source_category}-approved-v1",
    )
    approved = append_outcome_revision(
        access,
        _outcome(
            outcome_id=f"{outcome_id}-approved",
            outcome_type=outcome_type,
            health_disposition=disposition,
            source_category=source_category,
            source_system=source_system,
            source_record_id=f"{outcome_id}-approved",
            provenance_categories=provenance,
        ),
        idempotency_key=f"{outcome_id}-approved",
        source_authority_policy=policy,
    )
    assert unapproved["authority_tier"] == "B"
    assert approved["authority_tier"] == "A"
    assert approved["reliability_basis_json"]["source_authority_policy_version"] == policy.version
    assert approved["reliability_basis_json"]["source_authority_policy_hash"]
    assert approved["reliability_basis_json"]["approved_source_rule_id"] == (
        f"{source_category}-approved-v1"
    )


def test_arbitrary_source_name_does_not_grant_tier_a() -> None:
    access = _access()
    outcome = append_outcome_revision(
        access,
        _outcome(
            outcome_id="arbitrary-source",
            source_category="trusted-looking-name",
            source_record_id="arbitrary-source",
            provenance_categories=["independently_documented_outcome"],
        ),
        idempotency_key="arbitrary-source",
    )
    assert outcome["authority_tier"] == "B"


def test_incident_identity_reuse_requires_compatible_family_and_window_evidence() -> None:
    access = _access()
    original = append_outcome_revision(
        access,
        _outcome(),
        idempotency_key="incident-original",
    )
    overlapping = append_outcome_revision(
        access,
        _outcome(
            outcome_id="incident-overlapping",
            source_record_id="work-order-overlapping",
            occurred_start_at="2026-01-02T00:30:00+00:00",
            occurred_end_at="2026-01-02T02:00:00+00:00",
        ),
        idempotency_key="incident-overlapping",
    )
    incompatible = append_outcome_revision(
        access,
        _outcome(
            outcome_id="incident-incompatible",
            outcome_type="false_positive_not_useful",
            health_disposition="not_useful",
            source_record_id="work-order-incompatible",
        ),
        idempotency_key="incident-incompatible",
    )
    nonoverlapping = append_outcome_revision(
        access,
        _outcome(
            outcome_id="incident-nonoverlap",
            outcome_type="repair",
            health_disposition="intervention_recorded",
            source_record_id="work-order-nonoverlap",
            occurred_start_at="2026-02-02T00:00:00+00:00",
            occurred_end_at="2026-02-02T01:00:00+00:00",
        ),
        idempotency_key="incident-nonoverlap",
    )
    explicitly_linked = append_outcome_revision(
        access,
        _outcome(
            outcome_id="incident-explicit-link",
            outcome_type="repair",
            health_disposition="intervention_recorded",
            source_record_id="work-order-explicit-link",
            occurred_start_at="2026-03-02T00:00:00+00:00",
            occurred_end_at="2026-03-02T01:00:00+00:00",
            dedup_basis={
                "external_incident_id": "incident-1",
                "explicitly_linked_outcome_ids": [
                    original["outcome_id"],
                    overlapping["outcome_id"],
                ],
                "explicit_occurrence_link_basis": {
                    "kind": "reviewed_work_order_lifecycle",
                    "reviewed_by": "validator@example.com",
                },
            },
        ),
        idempotency_key="incident-explicit-link",
    )

    assert overlapping["canonical_incident_key"] == original["canonical_incident_key"]
    assert incompatible["dedup_status"] == "possible_duplicate"
    assert incompatible["canonical_incident_key"] is None
    assert original["outcome_id"] in incompatible["possible_duplicate_of_json"]
    assert "incident_identity_reuse_incompatible_family" in incompatible[
        "dedup_basis_json"
    ]["incident_reuse_evaluation"]["reason_codes"]
    assert nonoverlapping["dedup_status"] == "possible_duplicate"
    assert "incident_identity_reuse_nonoverlapping_window" in nonoverlapping[
        "dedup_basis_json"
    ]["incident_reuse_evaluation"]["reason_codes"]
    assert explicitly_linked["dedup_status"] == "canonical"
    assert explicitly_linked["canonical_incident_key"] == original["canonical_incident_key"]


def test_stable_operation_requires_predeclared_complete_eighty_percent_protocol() -> None:
    access = _access()
    exact_boundary = append_outcome_revision(access, _stable(), idempotency_key="stable-80")
    assert exact_boundary["observation_protocol_json"]["sample_coverage"] == 0.8
    assert exact_boundary["observation_protocol_json"]["protocol_completion"] == 0.8

    with pytest.raises(HealthRelevanceValidationError, match="below_minimum"):
        append_outcome_revision(
            access,
            _stable(
                outcome_id="stable-low",
                source_record_id="inspection-window-low",
                observation_protocol={
                    **_stable()["observation_protocol"],
                    "observed_sample_count": 79,
                    "sample_coverage": 0.79,
                },
            ),
            idempotency_key="stable-low",
        )
    with pytest.raises(HealthRelevanceValidationError, match="protocol_completion_below_minimum"):
        append_outcome_revision(
            access,
            _stable(
                outcome_id="stable-low-completion",
                source_record_id="inspection-window-low-completion",
                observation_protocol={
                    **_stable()["observation_protocol"],
                    "scheduled_windows": 5,
                    "completed_windows": 3,
                    "protocol_completion": 0.6,
                },
            ),
            idempotency_key="stable-low-completion",
        )
    with pytest.raises(HealthRelevanceValidationError, match="cannot_be_inferred_from_silence"):
        append_outcome_revision(
            access,
            _stable(
                outcome_id="stable-silence",
                source_record_id="inspection-window-silence",
                observation_protocol={
                    **_stable()["observation_protocol"],
                    "basis": "absence_of_findings",
                },
            ),
            idempotency_key="stable-silence",
        )
    with pytest.raises(HealthRelevanceValidationError, match="cannot_be_inferred_from_silence"):
        append_outcome_revision(
            access,
            _outcome(
                outcome_id="silence-label",
                source_record_id="silence-label",
                structured_metadata={"inferred_from_absence_of_findings": True},
            ),
            idempotency_key="silence-label",
        )


def test_possible_duplicates_are_preserved_without_silent_incident_merge() -> None:
    access = _access()
    canonical = append_outcome_revision(access, _outcome(), idempotency_key="canonical")
    possible = append_outcome_revision(
        access,
        _outcome(
            outcome_id="outcome-possible",
            source_system=None,
            source_record_id=None,
            source_record_version=None,
            source_recorded_at=None,
            provenance_categories=["retrospective_label"],
            possible_duplicate_of=[canonical["outcome_id"]],
            dedup_basis={"similar_time_only": True},
        ),
        idempotency_key="possible",
    )
    assert possible["dedup_status"] == "possible_duplicate"
    assert possible["canonical_incident_key"] is None
    assert possible["possible_duplicate_of_json"] == [canonical["outcome_id"]]
    assert canonical["canonical_incident_key"] is not None
    assert canonical["outcome_revision_id"] != possible["outcome_revision_id"]


def test_every_read_is_tenant_facility_and_system_scoped_with_opaque_failure() -> None:
    owner = _access()
    other_tenant = _access(tenant="tenant-b")
    other_facility = _access(facility="facility-b")
    other_system = _access(system="system-b")
    record = append_outcome_revision(owner, _outcome(), idempotency_key="owner")
    for unauthorized in (other_tenant, other_facility, other_system):
        with pytest.raises(HealthRelevanceAccessError, match="record not found"):
            get_outcome_revision(
                unauthorized,
                outcome_id=record["outcome_id"],
                outcome_revision_id=record["outcome_revision_id"],
            )
        assert list_latest_outcomes(unauthorized) == []
    with db_connection() as connection:
        persisted = connection.execute(
            "SELECT provenance_categories_json FROM validated_outcomes WHERE outcome_revision_id = ?",
            (record["outcome_revision_id"],),
        ).fetchone()
    assert json.loads(persisted["provenance_categories_json"]) == sorted(
        ["independently_documented_outcome", "maintenance_system_sourced"]
    )
