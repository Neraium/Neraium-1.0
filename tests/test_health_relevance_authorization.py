from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services.dataset_scope import build_dataset_scope
from app.services.health_relevance import (
    HealthRelevanceNotFoundError,
    compute_health_relevance,
    inspect_health_relevance,
)
from app.services.health_relevance_methods import BAYESIAN_METHOD_ID, INFORMATION_METHOD_ID
from app.services.validated_outcomes import (
    InternalHealthRelevanceAccess,
    authorize_internal_access,
)


def _access(*, tenant="tenant-a", facility="facility-a", system="system-a"):
    return authorize_internal_access(
        scope=build_dataset_scope(
            tenant_id=tenant,
            user_id=f"service@{tenant}",
            workspace_id=f"workspace-{tenant}",
        ),
        facility_id=facility,
        system_id=system,
        actor="internal-health-relevance",
        auth_source="service_token",
        role="admin",
        workspace_authorized=True,
    )


STATE = {
    "subject_type": "relationship",
    "subject_id": "relationship-r",
    "subject_mapping_version": "mapping-v1",
    "context_fingerprint": "context-high-load",
    "compatibility_epoch": "epoch-v1",
}


def _compute_empty(access):
    return compute_health_relevance(
        access,
        **STATE,
        computed_at=datetime(2026, 2, 1, tzinfo=UTC),
        method_config={INFORMATION_METHOD_ID: {"permutation_iterations": 100}},
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"auth_source": "session"},
        {"role": "operator"},
        {"workspace_authorized": False},
    ],
)
def test_forged_or_customer_access_fails_with_one_opaque_result(overrides):
    valid = _access()
    forged = InternalHealthRelevanceAccess(
        scope=valid.scope,
        facility_id=valid.facility_id,
        system_id=valid.system_id,
        actor=valid.actor,
        auth_source=overrides.get("auth_source", valid.auth_source),
        role=overrides.get("role", valid.role),
        workspace_authorized=overrides.get(
            "workspace_authorized", valid.workspace_authorized
        ),
    )
    with pytest.raises(
        HealthRelevanceNotFoundError, match=r"^Health Relevance state not found\.$"
    ):
        _compute_empty(forged)


@pytest.mark.parametrize(
    "other_access",
    [
        lambda: _access(tenant="tenant-b"),
        lambda: _access(facility="facility-b"),
        lambda: _access(system="system-b"),
    ],
)
def test_tenant_facility_and_system_mismatches_are_opaque(other_access):
    owning = _access()
    _compute_empty(owning)
    with pytest.raises(
        HealthRelevanceNotFoundError, match=r"^Health Relevance state not found\.$"
    ):
        inspect_health_relevance(
            other_access(), **STATE, method_class=BAYESIAN_METHOD_ID
        )


def test_context_epoch_subject_and_method_are_all_exact_read_boundaries():
    access = _access()
    _compute_empty(access)
    variants = [
        {**STATE, "context_fingerprint": "context-normal-load"},
        {**STATE, "compatibility_epoch": "epoch-v2"},
        {**STATE, "subject_id": "relationship-other"},
    ]
    for state in variants:
        with pytest.raises(HealthRelevanceNotFoundError):
            inspect_health_relevance(
                access, **state, method_class=BAYESIAN_METHOD_ID
            )
    with pytest.raises(HealthRelevanceNotFoundError):
        inspect_health_relevance(access, **STATE, method_class="unapproved-method")


def test_inspection_service_exposes_no_discovery_or_write_operation():
    import app.services.health_relevance as service

    assert not hasattr(service, "list_health_relevance")
    assert not hasattr(service, "update_health_relevance")
    assert not hasattr(service, "delete_health_relevance")
