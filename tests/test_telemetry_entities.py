from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
import json

import pytest

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.services.telemetry_domain import (
    AnalysisEligibility,
    AnalysisIneligibilityReason,
    ConnectionLifecycleStatus,
    ConnectorType,
    ConnectorCapability,
    DataConnectionRecord,
    InvalidLifecycleTransition,
    TelemetryScopeRef,
    can_transition_connection,
    require_connection_transition,
)


def _scope() -> TelemetryScopeRef:
    authority = AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a",
        workspace_id="ws-facility-a",
    )
    return TelemetryScopeRef(
        tenant_scope_id=authority.tenant_scope_id,
        workspace_id=authority.workspace_id,
        resource_scope_id=authority.resource_scope_id,
        facility_id="ws-facility-a",
    )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "validating"),
        ("validating", "connected"),
        ("validating", "disconnected"),
        ("connected", "degraded"),
        ("degraded", "connected"),
        ("error", "validating"),
        ("disabled", "disconnected"),
        ("connected", "archived"),
    ],
)
def test_valid_connection_lifecycle_transitions(current: str, target: str) -> None:
    assert can_transition_connection(current, target) is True
    assert require_connection_transition(current, target).value == target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "connected"),
        ("connected", "validating"),
        ("disabled", "connected"),
        ("archived", "draft"),
        ("archived", "archived"),
        ("unknown", "connected"),
    ],
)
def test_invalid_connection_lifecycle_transitions(current: str, target: str) -> None:
    assert can_transition_connection(current, target) is False
    with pytest.raises(InvalidLifecycleTransition):
        require_connection_transition(current, target)


def test_public_connection_record_is_immutable_and_has_no_secret_reference() -> None:
    connection = DataConnectionRecord(
        connection_id="connection-1",
        scope=_scope(),
        name="Synthetic HTTPS telemetry",
        connector_type="https_telemetry",
        lifecycle_status=ConnectionLifecycleStatus.DISCONNECTED,
        safe_configuration={
            "origin": "https://telemetry.example.test",
            "request_path": "/v1/observations",
        },
        capabilities=(
            ConnectorCapability.VALIDATE,
            ConnectorCapability.DISCOVER_SIGNALS,
            ConnectorCapability.INCREMENTAL_POLLING,
        ),
        credentials_configured=True,
        created_at=datetime(2026, 8, 25, tzinfo=UTC),
    )

    payload = connection.as_public_dict()
    encoded = json.dumps(payload)

    assert payload["credentials_configured"] is True
    assert payload["connector_type"] == ConnectorType.HTTPS_TELEMETRY.value
    assert payload["scope"]["resource_scope_id"] == _scope().resource_scope_id
    assert "secret_ref" not in payload
    assert "secret_reference" not in payload
    assert "secret_binding_id" not in payload
    assert "secret" not in encoded.lower()
    with pytest.raises(FrozenInstanceError):
        connection.name = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        connection.safe_configuration["origin"] = "https://changed.test"  # type: ignore[index]


def test_connection_record_default_safe_configuration_is_read_only() -> None:
    connection = DataConnectionRecord(
        connection_id="connection-1",
        scope=_scope(),
        name="Synthetic HTTPS telemetry",
        connector_type="https_telemetry",
    )

    assert connection.safe_configuration == {}
    with pytest.raises(TypeError):
        connection.safe_configuration["origin"] = "https://changed.test"  # type: ignore[index]


def test_connector_type_is_authoritative_and_rejects_unknown_providers() -> None:
    assert {item.value for item in ConnectorType} == {
        "https_telemetry",
        "historian_template",
    }
    with pytest.raises(ValueError):
        DataConnectionRecord(
            connection_id="connection-1",
            scope=_scope(),
            name="Synthetic unknown telemetry",
            connector_type="https",
        )


@pytest.mark.parametrize(
    "unsafe_configuration",
    [
        {"secret_ref": "arn:aws:secretsmanager:example"},
        {"headers": {"Authorization": "Bearer canary"}},
        {"headers": {"X-API-Key": "canary-api-key"}},
        {"advanced": [{"api_token": "canary-api-token"}]},
        {"advanced": {"access_token": "canary-access-token"}},
        {"oauth": {"clientSecret": "canary-client-secret"}},
        {"binding": {"internal_reference": "canary-internal-reference"}},
        {"token": "canary-token"},
        {"password": "canary-password"},
    ],
)
def test_public_connection_rejects_credential_shaped_configuration(
    unsafe_configuration: dict,
) -> None:
    with pytest.raises(ValueError, match="sensitive_public_field_forbidden"):
        DataConnectionRecord(
            connection_id="connection-1",
            scope=_scope(),
            name="Synthetic HTTPS telemetry",
            connector_type="https_telemetry",
            safe_configuration=unsafe_configuration,
        )


def test_public_connection_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="datetime_must_be_aware:created_at"):
        DataConnectionRecord(
            connection_id="connection-1",
            scope=_scope(),
            name="Synthetic HTTPS telemetry",
            connector_type="https_telemetry",
            created_at=datetime(2026, 8, 25),
        )


def test_scope_requires_facility_to_be_the_authoritative_workspace() -> None:
    authority = AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a",
        workspace_id="ws-facility-a",
    )
    with pytest.raises(ValueError, match="facility_workspace_mismatch"):
        TelemetryScopeRef(
            tenant_scope_id=authority.tenant_scope_id,
            workspace_id=authority.workspace_id,
            resource_scope_id=authority.resource_scope_id,
            facility_id="facility-from-payload",
        )


def test_analysis_eligibility_keeps_reasons_separate_from_quality() -> None:
    assert AnalysisEligibility.allowed().as_public_dict() == {
        "eligible": True,
        "reason_codes": [],
    }
    denied = AnalysisEligibility.denied(
        AnalysisIneligibilityReason.MAPPING_NOT_APPROVED,
        AnalysisIneligibilityReason.UNIT_UNRESOLVED,
    )
    assert denied.as_public_dict() == {
        "eligible": False,
        "reason_codes": ["mapping_not_approved", "unit_unresolved"],
    }
    with pytest.raises(ValueError, match="requires_reason"):
        AnalysisEligibility(eligible=False)
