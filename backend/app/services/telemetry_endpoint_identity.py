"""Versioned physical endpoint identity projected from approved telemetry state.

This metadata does not change analytical column names or authorize an upload.
Callers must verify a projection against the server-owned mapping and signal
records before using it as authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.services.telemetry_domain import ExternalSignalRecord, SignalMappingStatus
from app.services.telemetry_ingestion import MappingSnapshot


ENDPOINT_IDENTITY_VERSION = "physical-endpoint-identity.v1"


def physical_endpoint_id(resource_scope_id: str, connection_id: str, external_signal_id: str) -> str:
    """Encode existing scoped endpoint IDs without minting another identifier."""
    scope_prefix = "phase4-scope:"
    if (
        not isinstance(resource_scope_id, str)
        or not resource_scope_id.startswith(scope_prefix)
        or len(resource_scope_id) != len(scope_prefix) + 32
        or any(char not in "0123456789abcdef" for char in resource_scope_id[len(scope_prefix):])
    ):
        raise ValueError("physical_endpoint_identity_component_invalid")
    for value in (connection_id, external_signal_id):
        if not isinstance(value, str):
            raise ValueError("physical_endpoint_identity_component_invalid")
        try:
            if str(UUID(value)) != value:
                raise ValueError("physical_endpoint_identity_component_invalid")
        except ValueError as exc:
            raise ValueError("physical_endpoint_identity_component_invalid") from exc
    return f"physical-endpoint:{resource_scope_id}:{connection_id}:{external_signal_id}"


@dataclass(frozen=True, slots=True)
class PhysicalEndpointIdentity:
    contract_version: str
    endpoint_id: str
    resource_scope_id: str
    connection_id: str
    external_signal_id: str
    canonical_concept_id: str
    mapping_id: str
    mapping_revision: int
    facility_id: str
    system_id: str
    asset_id: str | None
    authority_digest: str
    source: str = "telemetry.signal_mappings"

    def __post_init__(self) -> None:
        if self.contract_version != ENDPOINT_IDENTITY_VERSION:
            raise ValueError("physical_endpoint_identity_version_invalid")
        expected = physical_endpoint_id(
            self.resource_scope_id, self.connection_id, self.external_signal_id
        )
        if self.endpoint_id != expected:
            raise ValueError("physical_endpoint_identity_mismatch")
        if not isinstance(self.canonical_concept_id, str) or not self.canonical_concept_id.strip():
            raise ValueError("physical_endpoint_concept_required")
        if self.canonical_concept_id in {self.endpoint_id, self.external_signal_id}:
            raise ValueError("physical_endpoint_concept_alias")
        if not isinstance(self.mapping_id, str) or not self.mapping_id.strip():
            raise ValueError("physical_endpoint_mapping_required")
        if type(self.mapping_revision) is not int or self.mapping_revision < 1:
            raise ValueError("physical_endpoint_mapping_revision_invalid")
        if not isinstance(self.facility_id, str) or not self.facility_id.strip():
            raise ValueError("physical_endpoint_facility_required")
        if not isinstance(self.system_id, str) or not self.system_id.strip():
            raise ValueError("physical_endpoint_system_required")
        if self.asset_id is not None and (
            not isinstance(self.asset_id, str) or not self.asset_id.strip()
        ):
            raise ValueError("physical_endpoint_asset_invalid")
        if (
            not isinstance(self.authority_digest, str)
            or len(self.authority_digest) != 64
            or any(char not in "0123456789abcdef" for char in self.authority_digest)
        ):
            raise ValueError("physical_endpoint_authority_digest_invalid")
        if self.source != "telemetry.signal_mappings":
            raise ValueError("physical_endpoint_source_invalid")

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


def project_physical_endpoint_identity(
    mapping: MappingSnapshot, signal: ExternalSignalRecord
) -> PhysicalEndpointIdentity:
    """Fail closed unless both server-owned records describe one enabled endpoint."""
    if not isinstance(mapping, MappingSnapshot) or not isinstance(signal, ExternalSignalRecord):
        raise TypeError("physical_endpoint_authoritative_records_required")
    if (
        mapping.enabled is not True
        or signal.enabled is not True
        or signal.mapping_status is not SignalMappingStatus.MAPPED
    ):
        raise ValueError("physical_endpoint_mapping_not_enabled")
    if (
        mapping.scope != signal.scope
        or mapping.facility_id != signal.scope.facility_id
        or mapping.connection_id != signal.connection_id
        or mapping.external_signal_id != signal.signal_id
        or mapping.external_tag_id != signal.external_tag_id
    ):
        raise ValueError("physical_endpoint_source_mismatch")
    if (
        signal.canonical_signal_id != mapping.canonical_signal_id
        or signal.system_id != mapping.system_id
        or signal.asset_id != mapping.asset_id
    ):
        raise ValueError("physical_endpoint_mapping_mismatch")
    return PhysicalEndpointIdentity(
        contract_version=ENDPOINT_IDENTITY_VERSION,
        endpoint_id=physical_endpoint_id(
            mapping.scope.resource_scope_id, mapping.connection_id, mapping.external_signal_id
        ),
        resource_scope_id=mapping.scope.resource_scope_id,
        connection_id=mapping.connection_id,
        external_signal_id=mapping.external_signal_id,
        canonical_concept_id=mapping.canonical_signal_id,
        mapping_id=mapping.mapping_id,
        mapping_revision=mapping.revision,
        facility_id=mapping.facility_id,
        system_id=mapping.system_id,
        asset_id=mapping.asset_id,
        authority_digest=mapping.authority_digest,
    )


def verify_physical_endpoint_identity(
    identity: PhysicalEndpointIdentity, mapping: MappingSnapshot, signal: ExternalSignalRecord
) -> bool:
    """Compare a projection with the exact server-loaded mapping and signal."""
    if not isinstance(identity, PhysicalEndpointIdentity):
        return False
    try:
        return identity == project_physical_endpoint_identity(mapping, signal)
    except (TypeError, ValueError):
        return False
