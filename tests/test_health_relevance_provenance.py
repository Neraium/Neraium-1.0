from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.health_relevance import (
    build_frozen_manifest,
    compute_health_relevance,
    inspect_health_relevance,
)
from app.services.health_relevance_methods import (
    BAYESIAN_METHOD_ID,
    INFORMATION_METHOD_ID,
)
from app.services.runtime_db import db_connection
from app.services.dataset_scope import build_dataset_scope
from app.services.validated_outcomes import (
    ApprovedOutcomeSourceRule,
    OutcomeSourceAuthorityPolicy,
    append_outcome_link_revision,
    append_outcome_revision,
    authorize_internal_access,
    context_fingerprint,
)


def _access():
    return authorize_internal_access(
        scope=build_dataset_scope(
            tenant_id="tenant-a",
            user_id="health-service@tenant-a",
            workspace_id="workspace-a",
        ),
        facility_id="facility-a",
        system_id="system-a",
        actor="health-relevance-service",
        auth_source="service_token",
        role="admin",
        workspace_authorized=True,
    )


def _outcome_payload(
    outcome_id: str, *, stable: bool = False, tier_d: bool = False, **overrides
):
    payload = {
        "outcome_id": outcome_id,
        "outcome_type": "confirmed_fault",
        "health_disposition": "fault_confirmed",
        "validation_status": "validated",
        "asset_equipment_id": "asset-a",
        "occurred_start_at": "2026-01-02T00:00:00+00:00",
        "occurred_end_at": "2026-01-02T01:00:00+00:00",
        "source_category": "maintenance",
        "source_system": "approved-cmms-fixture",
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
        "dedup_basis": {"external_incident_id": f"incident-{outcome_id}"},
        "structured_metadata": {"fixture": True},
        "reliability_basis": {"source_contract": "fixture"},
    }
    if tier_d:
        payload.update(
            source_system=None,
            source_record_id=None,
            source_record_version=None,
            source_recorded_at=None,
            validation_basis={"neraium_reviewed_at": "2026-01-01T20:00:00+00:00"},
            provenance_categories=[
                "operator_confirmed_after_neraium_review",
                "other_explicitly_validated_human_outcome",
            ],
        )
    if stable:
        payload.update(
            outcome_type="stable_operation_observation",
            health_disposition="stable_observation",
            provenance_categories=[
                "independently_documented_outcome",
                "inspection_sourced",
            ],
            observation_protocol={
                "protocol_id": f"protocol-{outcome_id}",
                "protocol_version": "1",
                "window_declared_at": "2026-01-01T00:00:00+00:00",
                "expected_sample_count": 100,
                "observed_sample_count": 80,
                "sample_coverage": 0.80,
                "scheduled_windows": 1,
                "completed_windows": 1,
                "protocol_completion": 1.0,
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


def _append_outcome(access, outcome_id: str, **kwargs):
    payload = _outcome_payload(outcome_id, **kwargs)
    source_system = payload.get("source_system")
    source_category = payload.get("source_category")
    outcome_type = payload.get("outcome_type")
    policy = None
    allowed_by_category = {
        "maintenance": {
            "confirmed_maintenance_event",
            "confirmed_fault",
            "confirmed_degraded_condition",
            "repair",
            "component_replacement",
        },
        "inspection": {
            "inspection_result",
            "confirmed_fault",
            "confirmed_degraded_condition",
            "expected_no_fault_confirmation",
            "stable_operation_observation",
        },
    }
    if source_system and outcome_type in allowed_by_category.get(str(source_category), set()):
        policy = OutcomeSourceAuthorityPolicy(
            version="fixture-source-policy.v1",
            rules=(
                ApprovedOutcomeSourceRule(
                    rule_id=f"fixture-{source_category}",
                    source_system=str(source_system),
                    source_category=str(source_category),
                    allowed_outcome_types=frozenset({str(outcome_type)}),
                ),
            ),
        )
    return append_outcome_revision(
        access,
        payload,
        idempotency_key=f"outcome:{outcome_id}",
        source_authority_policy=policy,
    )


def _link_payload(
    outcome, *, episode="episode-1", epoch="epoch-v1", stable=False, **overrides
):
    context = {"operating_mode": "high_load", "load_band": "high"}
    configuration = "configuration-v1"
    payload = {
        "link_id": f"link-{outcome['outcome_id']}",
        "outcome_id": outcome["outcome_id"],
        "outcome_revision_id": outcome["outcome_revision_id"],
        "asset_equipment_id": "asset-a",
        "evidence_content_hash": f"evidence-{outcome['outcome_id']}",
        "evidence_package_id": f"package-{outcome['outcome_id']}",
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
        "compatibility_epoch": epoch,
        "context_schema_version": "context-v1",
        "context": context,
        "context_fingerprint": context_fingerprint(
            context_schema_version="context-v1",
            context=context,
            system_configuration_fingerprint=configuration,
        ),
        "context_episode_id": episode,
        "context_source_refs": ["facility-context-v1"],
        "temporal_role": "stable_comparison" if stable else "outcome_period",
        "window_start_at": "2026-01-02T00:00:00+00:00",
        "window_end_at": "2026-01-02T01:00:00+00:00",
        "link_origin": "human_reviewed",
        "link_confidence": "reviewed",
        "link_basis": {"association_only": True},
        "linked_by": "validator@example.com",
        "linked_at": "2026-01-02T03:00:00+00:00",
        "subject_state": "absent_evaluable" if stable else "active_changed",
        "observation_basis": {"classification": "reviewed"},
        "link_status": "active",
    }
    payload.update(overrides)
    return payload


def _append_link(access, outcome, **kwargs):
    payload = _link_payload(outcome, **kwargs)
    return append_outcome_link_revision(
        access, payload, idempotency_key=f"link:{outcome['outcome_id']}"
    )


def _state_args(link):
    return {
        "subject_type": "relationship",
        "subject_id": "relationship-r",
        "subject_mapping_version": "mapping-v1",
        "context_fingerprint": link["context_fingerprint"],
        "compatibility_epoch": "epoch-v1",
    }


def test_both_methods_share_one_frozen_manifest_and_recompute_is_noop():
    access = _access()
    positive = _append_outcome(access, "positive-1")
    link = _append_link(access, positive)
    stable = _append_outcome(access, "stable-1", stable=True)
    _append_link(access, stable, stable=True, episode="episode-2")

    first = compute_health_relevance(
        access,
        **_state_args(link),
        computed_at=datetime(2026, 2, 1, tzinfo=UTC),
        method_config={
            INFORMATION_METHOD_ID: {"permutation_iterations": 100, "permutation_seed": 17}
        },
    )
    second = compute_health_relevance(
        access,
        **_state_args(link),
        computed_at=datetime(2026, 2, 2, tzinfo=UTC),
        method_config={
            INFORMATION_METHOD_ID: {"permutation_iterations": 100, "permutation_seed": 17}
        },
    )

    assert first["input_manifest_hash"] == second["input_manifest_hash"]
    assert set(first["versions"]) == {BAYESIAN_METHOD_ID, INFORMATION_METHOD_ID}
    assert {
        version["input_manifest_hash"] for version in first["versions"].values()
    } == {first["input_manifest_hash"]}
    assert all(version["created"] is True for version in first["versions"].values())
    assert all(version["created"] is False for version in second["versions"].values())
    assert first["summary"]["comparison_window_count"] == 1
    with db_connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM health_relevance_versions"
        ).fetchone()["count"] == 2


def test_provenance_inspection_preserves_authority_counts_and_supporting_revisions():
    access = _access()
    independent = _append_outcome(access, "independent")
    link = _append_link(access, independent)
    influenced = _append_outcome(access, "influenced", tier_d=True)
    _append_link(access, influenced, episode="episode-2")
    result = compute_health_relevance(
        access,
        **_state_args(link),
        computed_at=datetime(2026, 2, 1, tzinfo=UTC),
        method_config={INFORMATION_METHOD_ID: {"permutation_iterations": 100}},
    )

    assert result["summary"]["tier_a_count"] == 1
    assert result["summary"]["tier_d_count"] == 1
    assert result["summary"]["independent_count"] == 1
    assert result["summary"]["neraium_influenced_count"] == 1
    inspected = inspect_health_relevance(
        access,
        **_state_args(link),
        method_class=BAYESIAN_METHOD_ID,
        as_of=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert inspected["internal_only"] is True
    assert inspected["non_causal"] is True
    assert len(inspected["contributions"]) == 2
    assert {row["authority_tier"] for row in inspected["contributions"]} == {"A", "D"}
    assert all(row["outcome_revision_id"] for row in inspected["contributions"])
    assert all(row["link_revision_id"] for row in inspected["contributions"])
    assert all(row["input_manifest_hash"] == result["input_manifest_hash"] for row in inspected["contributions"])


def test_retraction_creates_new_versions_without_deleting_historical_contributions():
    access = _access()
    positive = _append_outcome(access, "positive-retract")
    link = _append_link(access, positive)
    first = compute_health_relevance(
        access,
        **_state_args(link),
        computed_at=datetime(2026, 2, 1, tzinfo=UTC),
        method_config={INFORMATION_METHOD_ID: {"permutation_iterations": 100}},
    )
    append_outcome_revision(
        access,
        {
            "outcome_id": positive["outcome_id"],
            "validation_status": "retracted",
            "validated_by": "validator@example.com",
            "validated_at": "2026-02-02T00:00:00+00:00",
            "validation_basis": {"reason": "source-correction"},
        },
        idempotency_key="outcome:positive-retract:retract",
    )
    second = compute_health_relevance(
        access,
        **_state_args(link),
        computed_at=datetime(2026, 2, 3, tzinfo=UTC),
        method_config={INFORMATION_METHOD_ID: {"permutation_iterations": 100}},
    )
    assert second["input_manifest_hash"] != first["input_manifest_hash"]
    assert all(version["version"] == 2 for version in second["versions"].values())
    assert second["summary"]["positive_count"] == 0
    with db_connection() as connection:
        old = connection.execute(
            "SELECT COUNT(*) AS count FROM health_relevance_contributions WHERE relevance_version_id = ?",
            (first["versions"][BAYESIAN_METHOD_ID]["relevance_version_id"],),
        ).fetchone()["count"]
        new_rows = connection.execute(
            "SELECT evidence_treatment, reason_code FROM health_relevance_contributions WHERE relevance_version_id = ?",
            (second["versions"][BAYESIAN_METHOD_ID]["relevance_version_id"],),
        ).fetchall()
    assert old == 1
    assert [(row["evidence_treatment"], row["reason_code"]) for row in new_rows] == [
        ("excluded", "outcome_not_validated")
    ]


def test_explicit_stable_protocol_is_required_and_silence_adds_no_denominator():
    access = _access()
    positive = _append_outcome(access, "positive-only")
    link = _append_link(access, positive)
    before = build_frozen_manifest(access, **_state_args(link))
    assert sum(row.get("outcome_class") == "explicit_comparison" for row in before["contributions"]) == 0

    stable = _append_outcome(access, "stable-explicit", stable=True)
    _append_link(access, stable, stable=True, episode="episode-2")
    after = build_frozen_manifest(access, **_state_args(link))
    comparisons = [
        row for row in after["contributions"] if row.get("outcome_class") == "explicit_comparison"
    ]
    assert len(comparisons) == 1
    assert comparisons[0]["information_cell"] == "d"
    assert comparisons[0]["telemetry_completeness"] == 0.80


def test_inspection_staleness_is_dynamic_without_rewriting_historical_state():
    access = _access()
    positive = _append_outcome(access, "stale-positive")
    link = _append_link(access, positive)
    computed = compute_health_relevance(
        access,
        **_state_args(link),
        computed_at=datetime(2026, 1, 10, tzinfo=UTC),
        method_config={INFORMATION_METHOD_ID: {"permutation_iterations": 100}},
    )
    last = datetime.fromisoformat(computed["summary"]["last_evidence_at"])
    current = inspect_health_relevance(
        access,
        **_state_args(link),
        method_class=BAYESIAN_METHOD_ID,
        as_of=last + timedelta(days=180),
    )
    stale = inspect_health_relevance(
        access,
        **_state_args(link),
        method_class=BAYESIAN_METHOD_ID,
        as_of=last + timedelta(days=180, microseconds=1),
    )
    assert current["effective_freshness_status"] == "current"
    assert stale["effective_freshness_status"] == "stale"
    assert current["state"]["evidence_state"] == stale["state"]["evidence_state"]
    with db_connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM health_relevance_versions"
        ).fetchone()["count"] == 2


def test_multiple_outcome_families_in_one_incident_form_one_method_unit():
    access = _access()
    shared_incident = {"external_incident_id": "shared-incident"}
    fault = _append_outcome(
        access,
        "shared-fault",
        dedup_basis=shared_incident,
    )
    repair = _append_outcome(
        access,
        "shared-repair",
        outcome_type="repair",
        health_disposition="explained",
        dedup_basis=shared_incident,
    )
    recovery = _append_outcome(
        access,
        "shared-recovery",
        outcome_type="return_toward_expected_behavior",
        health_disposition="recovery_observed",
        dedup_basis=shared_incident,
    )
    link = _append_link(access, fault)
    _append_link(access, repair)
    _append_link(access, recovery)
    manifest = build_frozen_manifest(access, **_state_args(link))
    result = compute_health_relevance(
        access,
        **_state_args(link),
        method_config={INFORMATION_METHOD_ID: {"permutation_iterations": 100}},
    )

    assert result["summary"]["eligible_outcome_count"] == 3
    assert result["summary"]["canonical_incident_count"] == 1
    assert result["summary"]["positive_family_count"] == 3
    assert sum(row["eligible"] is True for row in manifest["contributions"]) == 1
    assert (
        result["versions"][BAYESIAN_METHOD_ID]["positive_count"]
        == 1
    )
    components = result["versions"][BAYESIAN_METHOD_ID]["method_components_json"]
    assert components["contribution_counts"]["primary_directional"] == 1


def test_overlapping_stable_protocol_windows_cannot_inflate_denominator_or_information_cell():
    access = _access()
    protocol = {
        "protocol_id": "shared-stable-protocol",
        "protocol_version": "1",
        "window_declared_at": "2026-01-01T00:00:00+00:00",
        "expected_sample_count": 100,
        "observed_sample_count": 80,
        "sample_coverage": 0.80,
        "scheduled_windows": 5,
        "completed_windows": 4,
        "protocol_completion": 0.80,
        "completed": True,
        "context_complete": True,
        "expected_signal_reference_set": ["relationship-r"],
        "sampling_cadence": "1m",
        "subject_evaluability_rule": "reference-and-signal-present",
        "basis": "predeclared_protocol",
    }
    first = _append_outcome(
        access,
        "stable-overlap-first",
        stable=True,
        observation_protocol=protocol,
    )
    second = _append_outcome(
        access,
        "stable-overlap-second",
        stable=True,
        observation_protocol=protocol,
    )
    first_link = _append_link(access, first, stable=True, episode="stable-episode-1")
    _append_link(
        access,
        second,
        stable=True,
        episode="stable-episode-1",
        window_start_at="2026-01-02T00:30:00+00:00",
        window_end_at="2026-01-02T01:30:00+00:00",
    )

    manifest = build_frozen_manifest(access, **_state_args(first_link))
    result = compute_health_relevance(
        access,
        **_state_args(first_link),
        method_config={INFORMATION_METHOD_ID: {"permutation_iterations": 100}},
    )

    eligible_comparisons = [
        row
        for row in manifest["contributions"]
        if row["eligible"] and row.get("outcome_class") == "explicit_comparison"
    ]
    suppressed = [
        row
        for row in manifest["contributions"]
        if row.get("reason_code") == "overlapping_comparison_window_suppressed"
    ]
    assert len(eligible_comparisons) == 1
    assert eligible_comparisons[0]["outcome_id"] == "stable-overlap-first"
    assert len(suppressed) == 1
    assert suppressed[0]["evidence_treatment"] == "duplicate_suppressed"
    assert result["summary"]["comparison_window_count"] == 1
    assert result["summary"]["protocol_completion"] == 0.80
    assert result["summary"]["duplicate_suppressed_count"] == 1
    information = result["versions"][INFORMATION_METHOD_ID]["method_components_json"]
    assert information["primary_view"]["contingency_table"] == {
        "a": 0,
        "b": 0,
        "c": 0,
        "d": 1,
    }
