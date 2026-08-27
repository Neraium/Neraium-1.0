"""Pure P1.2 canonical-authority package contracts.

The records in this module describe an immutable physical representation of
already-produced P0.3 authority.  They do not encode, persist, compress,
publish, route, or resolve packages.  Every locator carries an exact scope;
there is deliberately no raw-ID or global lookup interface here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from app.services.analytical_authority_contract import (
    AuthorityStatus,
    NativeExecutionBinding,
    TerminalOutcome,
    validate_terminal_outcome_cardinality,
)
from app.services.authority_contract_common import (
    AuthorityScope,
    Completeness,
    CompletenessState,
    ContractValidationError,
    ContractVersion,
    Integrity,
    ScopeLevel,
    TypedDigest,
    VersionBundle,
    canonical_json_bytes,
    canonical_json_text,
)
from app.services.authority_identity import (
    AnalyticalFindingIdentity,
    AnalyticalReferenceIdentity,
    AuthorityExecutionIdentity,
    CanonicalPackageIdentity,
    ClassificationBindingIdentity,
    ConfidenceBindingIdentity,
    EvidenceBindingIdentity,
    EvidenceFactIdentity,
    PersistenceAssessmentIdentity,
    SectionIdentity,
)
from app.services.telemetry_event_time import ChronologyReference

CANONICAL_PACKAGE_METADATA_CONTRACT = "canonical-authority-package-metadata.v1"
PACKAGE_VERSION_BINDING_CONTRACT = "canonical-authority-package-versions.v1"
SECTION_DESCRIPTOR_CONTRACT = "canonical-authority-section-descriptor.v1"
OBJECT_INDEX_DESCRIPTOR_CONTRACT = "canonical-authority-object-index.v1"
PACKAGE_INTEGRITY_DESCRIPTOR_CONTRACT = "canonical-authority-package-integrity.v1"
PACKAGE_COMPLETENESS_DESCRIPTOR_CONTRACT = "canonical-authority-package-completeness.v1"
OBJECT_FAMILY_DESCRIPTOR_CONTRACT = "canonical-authority-object-family.v1"
SECTION_INTEGRITY_ENTRY_CONTRACT = "canonical-authority-section-integrity-entry.v1"
OBJECT_INTEGRITY_ENTRY_CONTRACT = "canonical-authority-object-integrity-entry.v1"

FINDING_OBJECT_FAMILY = "analytical_finding"
FACT_OBJECT_FAMILY = "evidence_fact"
BINDING_OBJECT_FAMILY = "evidence_binding"


def _fail(code: str) -> None:
    raise ContractValidationError(code)


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(code)
    return value


def _count(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(code)
    return value


def _uuid(value: UUID | str, code: str) -> UUID:
    try:
        parsed = value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ContractValidationError(code) from exc
    if str(parsed) != str(value).lower():
        _fail(code)
    return parsed


def _require_sha256(value: object, code: str) -> TypedDigest:
    if not isinstance(value, TypedDigest) or value.algorithm != "sha256":
        _fail(code)
    return value


def _base_scope(scope: AuthorityScope) -> tuple[str | None, ...]:
    if not isinstance(scope, AuthorityScope):
        _fail("package_scope_required")
    if scope.level not in {
        ScopeLevel.ASSET,
        ScopeLevel.NATIVE_RESULT,
        ScopeLevel.AUTHORITY_EXECUTION,
        ScopeLevel.FINDING,
    }:
        _fail("package_asset_scope_required")
    return (
        scope.tenant_id,
        scope.workspace_id,
        scope.resource_scope_id,
        scope.facility_id,
        scope.connection_id,
        scope.system_id,
        scope.asset_id,
    )


def _require_same_base_scope(*scopes: AuthorityScope) -> None:
    values = tuple(_base_scope(scope) for scope in scopes)
    if not values or len(set(values)) != 1:
        _fail("package_base_scope_mismatch")


def _require_package_scope(
    scope: AuthorityScope,
    package_id: CanonicalPackageIdentity,
    native_source_id: UUID | str | None = None,
) -> AuthorityScope:
    scope.require_level(ScopeLevel.AUTHORITY_EXECUTION)
    authority = package_id.authority_execution_id
    _require_same_base_scope(scope, authority.scope)
    if scope.authority_execution_id != str(authority.value):
        _fail("package_scope_authority_execution_mismatch")
    expected_native = authority.native_terminal_source_id
    if (
        native_source_id is not None
        and _uuid(native_source_id, "package_native_source_identity_invalid")
        != expected_native
    ):
        _fail("package_native_source_authority_mismatch")
    if scope.native_result_id is not None and scope.native_result_id != str(expected_native):
        _fail("package_scope_native_source_mismatch")
    return scope


def _identity_authority(value: object) -> AuthorityExecutionIdentity | None:
    authority = getattr(value, "authority_execution_id", None)
    if isinstance(authority, AuthorityExecutionIdentity):
        return authority
    finding = getattr(value, "analytical_finding_id", None)
    finding_authority = getattr(finding, "authority_execution_id", None)
    if isinstance(finding_authority, AuthorityExecutionIdentity):
        return finding_authority
    return None


class PackageBuildMode(str, Enum):
    """Immutable construction intent; not customer-authority state."""

    SHADOW = "shadow"
    PUBLICATION_CANDIDATE = "publication_candidate"


@dataclass(frozen=True, slots=True)
class PackageVersionBundleBinding:
    """Exact package-specific schemas bound to the shared version bundle."""

    package_schema: ContractVersion
    metadata_schema: ContractVersion
    section_descriptor_schema: ContractVersion
    object_index_schema: ContractVersion
    integrity_schema: ContractVersion
    completeness_schema: ContractVersion
    versions: VersionBundle

    def __post_init__(self) -> None:
        version_fields = (
            self.package_schema,
            self.metadata_schema,
            self.section_descriptor_schema,
            self.object_index_schema,
            self.integrity_schema,
            self.completeness_schema,
        )
        if any(not isinstance(item, ContractVersion) for item in version_fields):
            _fail("package_version_binding_contract_version_invalid")
        if not isinstance(self.versions, VersionBundle):
            _fail("package_version_bundle_required")
        self.versions.validate_required(version_fields)

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": PACKAGE_VERSION_BINDING_CONTRACT,
            "package_schema": self.package_schema.as_dict(),
            "metadata_schema": self.metadata_schema.as_dict(),
            "section_descriptor_schema": self.section_descriptor_schema.as_dict(),
            "object_index_schema": self.object_index_schema.as_dict(),
            "integrity_schema": self.integrity_schema.as_dict(),
            "completeness_schema": self.completeness_schema.as_dict(),
            "versions": self.versions.as_dict(),
        }

    @property
    def digest(self) -> TypedDigest:
        return TypedDigest.from_value(PACKAGE_VERSION_BINDING_CONTRACT, self.as_dict())


@dataclass(frozen=True, slots=True)
class ObjectFamilyCountDigestDescriptor:
    """Expected and represented membership for one typed object family."""

    object_family: str
    expected_count: int
    actual_count: int
    expected_set_digest: TypedDigest
    actual_set_digest: TypedDigest
    completeness: Completeness

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "object_family", _text(self.object_family, "object_family_invalid")
        )
        _count(self.expected_count, "object_family_expected_count_invalid")
        _count(self.actual_count, "object_family_actual_count_invalid")
        _require_sha256(
            self.expected_set_digest, "object_family_expected_digest_invalid"
        )
        _require_sha256(self.actual_set_digest, "object_family_actual_digest_invalid")
        if not isinstance(self.completeness, Completeness):
            _fail("object_family_completeness_required")
        if self.completeness.state is CompletenessState.PARTIAL:
            _fail("canonical_package_partial_forbidden")
        if self.completeness.state is CompletenessState.COMPLETE:
            if self.expected_count != self.actual_count:
                _fail("complete_object_family_count_mismatch")
            if self.expected_set_digest != self.actual_set_digest:
                _fail("complete_object_family_digest_mismatch")
        elif (
            self.expected_count == self.actual_count
            and self.expected_set_digest == self.actual_set_digest
        ):
            _fail("noncomplete_object_family_cannot_claim_exact_membership")

    def require_complete(self) -> ObjectFamilyCountDigestDescriptor:
        self.completeness.require_complete()
        if self.expected_count != self.actual_count:
            _fail("object_family_count_mismatch")
        if self.expected_set_digest != self.actual_set_digest:
            _fail("object_family_digest_mismatch")
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": OBJECT_FAMILY_DESCRIPTOR_CONTRACT,
            "object_family": self.object_family,
            "expected_count": self.expected_count,
            "actual_count": self.actual_count,
            "expected_set_digest": self.expected_set_digest.as_dict(),
            "actual_set_digest": self.actual_set_digest.as_dict(),
            "completeness": self.completeness.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class SectionIntegrityEntry:
    section_id: SectionIdentity
    digest: TypedDigest

    def __post_init__(self) -> None:
        if not isinstance(self.section_id, SectionIdentity):
            _fail("section_integrity_identity_required")
        _require_sha256(self.digest, "section_integrity_digest_invalid")

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": SECTION_INTEGRITY_ENTRY_CONTRACT,
            "section_id": str(self.section_id.value),
            "digest": self.digest.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ObjectIntegrityEntry:
    object_family: str
    object_id: UUID | str
    digest: TypedDigest

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "object_family",
            _text(self.object_family, "object_integrity_family_invalid"),
        )
        object.__setattr__(
            self,
            "object_id",
            _uuid(self.object_id, "object_integrity_identity_invalid"),
        )
        _require_sha256(self.digest, "object_integrity_digest_invalid")

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": OBJECT_INTEGRITY_ENTRY_CONTRACT,
            "object_family": self.object_family,
            "object_id": str(self.object_id),
            "digest": self.digest.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class PackageIntegrityDescriptor:
    """Typed SHA-256 bindings, kept separate from package identity derivation."""

    package_id: CanonicalPackageIdentity
    contract_version: ContractVersion
    manifest_digest: TypedDigest
    payload_digest: TypedDigest
    section_entries: tuple[SectionIntegrityEntry, ...]
    object_entries: tuple[ObjectIntegrityEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.package_id, CanonicalPackageIdentity):
            _fail("package_integrity_package_identity_required")
        if not isinstance(self.contract_version, ContractVersion):
            _fail("package_integrity_contract_version_required")
        _require_sha256(self.manifest_digest, "package_manifest_digest_invalid")
        _require_sha256(self.payload_digest, "package_payload_digest_invalid")
        sections = tuple(self.section_entries)
        objects = tuple(self.object_entries)
        if any(not isinstance(item, SectionIntegrityEntry) for item in sections):
            _fail("package_section_integrity_entry_invalid")
        if any(not isinstance(item, ObjectIntegrityEntry) for item in objects):
            _fail("package_object_integrity_entry_invalid")
        section_ids = tuple(item.section_id.value for item in sections)
        object_keys = tuple((item.object_family, item.object_id) for item in objects)
        if len(section_ids) != len(set(section_ids)):
            _fail("package_section_integrity_duplicate")
        if len(object_keys) != len(set(object_keys)):
            _fail("package_object_integrity_duplicate")
        if tuple(sorted(section_ids, key=str)) != section_ids:
            _fail("package_section_integrity_order_invalid")
        if (
            tuple(sorted(object_keys, key=lambda item: (item[0], str(item[1]))))
            != object_keys
        ):
            _fail("package_object_integrity_order_invalid")
        object.__setattr__(self, "section_entries", sections)
        object.__setattr__(self, "object_entries", objects)

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": PACKAGE_INTEGRITY_DESCRIPTOR_CONTRACT,
            "package_id": str(self.package_id.value),
            "contract_version": self.contract_version.as_dict(),
            "manifest_digest": self.manifest_digest.as_dict(),
            "payload_digest": self.payload_digest.as_dict(),
            "section_entries": tuple(item.as_dict() for item in self.section_entries),
            "object_entries": tuple(item.as_dict() for item in self.object_entries),
        }


@dataclass(frozen=True, slots=True)
class PackageCompletenessDescriptor:
    package_id: CanonicalPackageIdentity
    completeness: Completeness
    expected_section_count: int
    actual_section_count: int
    expected_section_set_digest: TypedDigest
    actual_section_set_digest: TypedDigest
    object_families: tuple[ObjectFamilyCountDigestDescriptor, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.package_id, CanonicalPackageIdentity):
            _fail("package_completeness_package_identity_required")
        if not isinstance(self.completeness, Completeness):
            _fail("package_completeness_required")
        if self.completeness.state is CompletenessState.PARTIAL:
            _fail("canonical_package_partial_forbidden")
        _count(self.expected_section_count, "package_expected_section_count_invalid")
        _count(self.actual_section_count, "package_actual_section_count_invalid")
        _require_sha256(
            self.expected_section_set_digest, "package_expected_section_digest_invalid"
        )
        _require_sha256(
            self.actual_section_set_digest, "package_actual_section_digest_invalid"
        )
        families = tuple(self.object_families)
        if any(
            not isinstance(item, ObjectFamilyCountDigestDescriptor) for item in families
        ):
            _fail("package_object_family_descriptor_invalid")
        names = tuple(item.object_family for item in families)
        if len(names) != len(set(names)):
            _fail("package_object_family_duplicate")
        if tuple(sorted(names)) != names:
            _fail("package_object_family_order_invalid")
        object.__setattr__(self, "object_families", families)
        if self.completeness.state is CompletenessState.COMPLETE:
            self.require_complete()
        elif (
            self.expected_section_count == self.actual_section_count
            and self.expected_section_set_digest == self.actual_section_set_digest
            and all(
                item.completeness.state is CompletenessState.COMPLETE
                for item in families
            )
        ):
            _fail("noncomplete_package_cannot_claim_exact_membership")

    def require_complete(self) -> PackageCompletenessDescriptor:
        self.completeness.require_complete()
        if self.expected_section_count != self.actual_section_count:
            _fail("complete_package_section_count_mismatch")
        if self.expected_section_set_digest != self.actual_section_set_digest:
            _fail("complete_package_section_digest_mismatch")
        for item in self.object_families:
            item.require_complete()
        return self

    def family(self, object_family: str) -> ObjectFamilyCountDigestDescriptor:
        family = _text(object_family, "required_object_family_invalid")
        for item in self.object_families:
            if item.object_family == family:
                return item
        _fail(f"package_object_family_missing:{family}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": PACKAGE_COMPLETENESS_DESCRIPTOR_CONTRACT,
            "package_id": str(self.package_id.value),
            "completeness": self.completeness.as_dict(),
            "expected_section_count": self.expected_section_count,
            "actual_section_count": self.actual_section_count,
            "expected_section_set_digest": self.expected_section_set_digest.as_dict(),
            "actual_section_set_digest": self.actual_section_set_digest.as_dict(),
            "object_families": tuple(item.as_dict() for item in self.object_families),
        }


@dataclass(frozen=True, slots=True)
class SectionDescriptor:
    package_id: CanonicalPackageIdentity
    scope: AuthorityScope
    identity: SectionIdentity
    section_family: str
    section_schema: ContractVersion
    sequence_number: int
    encoding_contract: ContractVersion
    object_count: int
    stored_size_bytes: int
    uncompressed_size_bytes: int
    integrity: Integrity
    completeness: Completeness

    def __post_init__(self) -> None:
        if not isinstance(self.package_id, CanonicalPackageIdentity):
            _fail("section_package_identity_required")
        _require_package_scope(self.scope, self.package_id)
        if not isinstance(self.identity, SectionIdentity):
            _fail("section_identity_required")
        if self.identity.package_id != self.package_id:
            _fail("section_identity_package_mismatch")
        object.__setattr__(
            self, "section_family", _text(self.section_family, "section_family_invalid")
        )
        if self.section_family != self.identity.section_family:
            _fail("section_identity_family_mismatch")
        if not isinstance(self.section_schema, ContractVersion):
            _fail("section_schema_required")
        if self.section_schema != self.identity.section_schema:
            _fail("section_identity_schema_mismatch")
        _count(self.sequence_number, "section_sequence_invalid")
        if self.sequence_number != self.identity.sequence_number:
            _fail("section_identity_sequence_mismatch")
        if not isinstance(self.encoding_contract, ContractVersion):
            _fail("section_encoding_contract_required")
        _count(self.object_count, "section_object_count_invalid")
        _count(self.stored_size_bytes, "section_stored_size_invalid")
        _count(self.uncompressed_size_bytes, "section_uncompressed_size_invalid")
        if self.stored_size_bytes > self.uncompressed_size_bytes:
            _fail("section_stored_size_exceeds_uncompressed_size")
        if not isinstance(self.integrity, Integrity):
            _fail("section_integrity_required")
        _require_sha256(self.integrity.digest, "section_integrity_sha256_required")
        if not isinstance(self.completeness, Completeness):
            _fail("section_completeness_required")
        self.completeness.require_complete()

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": SECTION_DESCRIPTOR_CONTRACT,
            "package_id": str(self.package_id.value),
            "scope": self.scope.as_dict(),
            "identity": self.identity.as_dict(),
            "section_family": self.section_family,
            "section_schema": self.section_schema.as_dict(),
            "sequence_number": self.sequence_number,
            "encoding_contract": self.encoding_contract.as_dict(),
            "object_count": self.object_count,
            "stored_size_bytes": self.stored_size_bytes,
            "uncompressed_size_bytes": self.uncompressed_size_bytes,
            "integrity": self.integrity.as_dict(),
            "completeness": self.completeness.as_dict(),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.as_dict())


_INDEXABLE_IDENTITY_TYPES = (
    AnalyticalReferenceIdentity,
    AnalyticalFindingIdentity,
    EvidenceFactIdentity,
    EvidenceBindingIdentity,
    ClassificationBindingIdentity,
    ConfidenceBindingIdentity,
    PersistenceAssessmentIdentity,
)

_OBJECT_FAMILY_TYPES = {
    "analytical_reference": AnalyticalReferenceIdentity,
    FINDING_OBJECT_FAMILY: AnalyticalFindingIdentity,
    FACT_OBJECT_FAMILY: EvidenceFactIdentity,
    BINDING_OBJECT_FAMILY: EvidenceBindingIdentity,
    "classification_binding": ClassificationBindingIdentity,
    "confidence_binding": ConfidenceBindingIdentity,
    "persistence_assessment": PersistenceAssessmentIdentity,
}


@dataclass(frozen=True, slots=True)
class ObjectIndexDescriptor:
    """One exact scoped locator; consumers must authorize before decoding."""

    package_id: CanonicalPackageIdentity
    scope: AuthorityScope
    section_id: SectionIdentity
    object_family: str
    object_identity: object
    ordinal: int
    record_size_bytes: int
    object_integrity: Integrity
    completeness: Completeness

    def __post_init__(self) -> None:
        if not isinstance(self.package_id, CanonicalPackageIdentity):
            _fail("object_index_package_identity_required")
        _require_package_scope(self.scope, self.package_id)
        if not isinstance(self.section_id, SectionIdentity):
            _fail("object_index_section_identity_required")
        if self.section_id.package_id != self.package_id:
            _fail("object_index_section_package_mismatch")
        object.__setattr__(
            self,
            "object_family",
            _text(self.object_family, "object_index_family_invalid"),
        )
        if not isinstance(self.object_identity, _INDEXABLE_IDENTITY_TYPES):
            _fail("object_index_typed_identity_required")
        expected_type = _OBJECT_FAMILY_TYPES.get(self.object_family)
        if expected_type is None or not isinstance(self.object_identity, expected_type):
            _fail("object_index_family_identity_type_mismatch")
        authority = _identity_authority(self.object_identity)
        if (
            authority is not None
            and authority != self.package_id.authority_execution_id
        ):
            _fail("object_index_cross_authority_forbidden")
        identity_scope = getattr(self.object_identity, "scope", None)
        if isinstance(identity_scope, AuthorityScope):
            _require_same_base_scope(self.scope, identity_scope)
        _count(self.ordinal, "object_index_ordinal_invalid")
        _count(self.record_size_bytes, "object_index_record_size_invalid")
        if not isinstance(self.object_integrity, Integrity):
            _fail("object_index_integrity_required")
        _require_sha256(
            self.object_integrity.digest, "object_index_integrity_sha256_required"
        )
        if not isinstance(self.completeness, Completeness):
            _fail("object_index_completeness_required")
        self.completeness.require_complete()

    @property
    def object_id(self) -> UUID:
        return self.object_identity.value

    def validate_section(self, section: SectionDescriptor) -> ObjectIndexDescriptor:
        if not isinstance(section, SectionDescriptor):
            _fail("object_index_section_descriptor_required")
        if section.identity != self.section_id:
            _fail("object_index_section_descriptor_mismatch")
        section.scope.require_exact(self.scope)
        if self.ordinal >= section.object_count:
            _fail("object_index_ordinal_out_of_range")
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": OBJECT_INDEX_DESCRIPTOR_CONTRACT,
            "package_id": str(self.package_id.value),
            "scope": self.scope.as_dict(),
            "section_id": str(self.section_id.value),
            "object_family": self.object_family,
            "object_identity": self.object_identity.as_dict(),
            "ordinal": self.ordinal,
            "record_size_bytes": self.record_size_bytes,
            "object_integrity": self.object_integrity.as_dict(),
            "completeness": self.completeness.as_dict(),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.as_dict())


@dataclass(frozen=True, slots=True)
class CanonicalAuthorityPackageMetadata:
    """Complete immutable metadata for one physical authority package."""

    identity: CanonicalPackageIdentity
    scope: AuthorityScope
    native_execution: NativeExecutionBinding
    authority_execution_id: AuthorityExecutionIdentity
    chronology_reference: ChronologyReference
    analytical_reference_id: AnalyticalReferenceIdentity
    terminal_outcome: TerminalOutcome
    finding_count: int
    finding_set_digest: TypedDigest
    fact_count: int
    fact_set_digest: TypedDigest
    binding_count: int
    binding_set_digest: TypedDigest
    sections: tuple[SectionDescriptor, ...]
    versions: PackageVersionBundleBinding
    build_mode: PackageBuildMode
    authority_status: AuthorityStatus
    integrity: PackageIntegrityDescriptor
    completeness: PackageCompletenessDescriptor

    def __post_init__(self) -> None:
        if not isinstance(self.identity, CanonicalPackageIdentity):
            _fail("package_metadata_identity_required")
        if not isinstance(self.authority_execution_id, AuthorityExecutionIdentity):
            _fail("package_metadata_authority_identity_required")
        if self.identity.authority_execution_id != self.authority_execution_id:
            _fail("package_identity_authority_mismatch")
        if not isinstance(self.native_execution, NativeExecutionBinding):
            _fail("package_native_execution_required")
        _require_package_scope(
            self.scope, self.identity, self.native_execution.source_identity
        )
        if self.native_execution.source_kind != self.authority_execution_id.source_kind:
            _fail("package_native_source_kind_mismatch")
        if (
            self.native_execution.source_identity
            != self.authority_execution_id.native_terminal_source_id
        ):
            _fail("package_native_source_identity_mismatch")
        if (
            self.native_execution.source_integrity.digest
            != self.authority_execution_id.native_terminal_digest
        ):
            _fail("package_native_source_integrity_mismatch")
        if self.native_execution.native_result_identity is not None:
            _require_same_base_scope(
                self.scope, self.native_execution.native_result_identity.scope
            )
            if self.scope.native_result_id != str(
                self.native_execution.native_result_identity.value
            ):
                _fail("package_scope_native_result_mismatch")
        elif self.scope.native_result_id is not None:
            _fail("package_terminal_decision_cannot_alias_native_result")
        if not isinstance(self.chronology_reference, ChronologyReference):
            _fail("package_chronology_reference_required")
        if (
            self.chronology_reference.execution_identity
            != self.authority_execution_id.chronology_execution_id
        ):
            _fail("package_chronology_execution_mismatch")
        _require_same_base_scope(self.scope, self.chronology_reference.scope)
        if not isinstance(self.analytical_reference_id, AnalyticalReferenceIdentity):
            _fail("package_analytical_reference_identity_required")
        if (
            self.analytical_reference_id
            != self.chronology_reference.selected_analytical_reference_id
        ):
            _fail("package_analytical_reference_mismatch")
        _require_same_base_scope(self.scope, self.analytical_reference_id.scope)

        _count(self.finding_count, "package_finding_count_invalid")
        _count(self.fact_count, "package_fact_count_invalid")
        _count(self.binding_count, "package_binding_count_invalid")
        object.__setattr__(
            self,
            "terminal_outcome",
            validate_terminal_outcome_cardinality(
                self.terminal_outcome, self.finding_count
            ),
        )
        if self.terminal_outcome in {
            TerminalOutcome.FINDINGS_PRESENT,
            TerminalOutcome.STABLE_NO_CHANGE,
            TerminalOutcome.INSUFFICIENT_EVIDENCE,
        }:
            self.chronology_reference.require_authority_bindable()
            if self.native_execution.terminal_state != "completed":
                _fail("completed_package_requires_completed_native_execution")
        elif self.native_execution.terminal_state != self.terminal_outcome.value:
            _fail("terminal_package_native_state_mismatch")
        _require_sha256(self.finding_set_digest, "package_finding_set_digest_invalid")
        _require_sha256(self.fact_set_digest, "package_fact_set_digest_invalid")
        _require_sha256(self.binding_set_digest, "package_binding_set_digest_invalid")

        sections = tuple(self.sections)
        if any(not isinstance(item, SectionDescriptor) for item in sections):
            _fail("package_section_descriptor_invalid")
        if tuple(item.sequence_number for item in sections) != tuple(
            range(len(sections))
        ):
            _fail("package_sections_must_be_contiguous_and_ordered")
        if len({item.identity.value for item in sections}) != len(sections):
            _fail("package_section_identity_duplicate")
        for section in sections:
            if section.package_id != self.identity:
                _fail("package_section_package_mismatch")
            section.scope.require_exact(self.scope)
            section.completeness.require_complete()
        object.__setattr__(self, "sections", sections)

        if not isinstance(self.versions, PackageVersionBundleBinding):
            _fail("package_versions_required")
        if self.identity.package_schema != self.versions.package_schema:
            _fail("package_identity_schema_mismatch")
        try:
            mode = PackageBuildMode(self.build_mode)
            status = AuthorityStatus(self.authority_status)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                "package_mode_or_authority_status_invalid"
            ) from exc
        object.__setattr__(self, "build_mode", mode)
        object.__setattr__(self, "authority_status", status)
        if status is not AuthorityStatus.SHADOW:
            _fail("package_metadata_cannot_confer_authority")
        if not isinstance(self.integrity, PackageIntegrityDescriptor):
            _fail("package_integrity_descriptor_required")
        if not isinstance(self.completeness, PackageCompletenessDescriptor):
            _fail("package_completeness_descriptor_required")
        if self.integrity.package_id != self.identity:
            _fail("package_integrity_identity_mismatch")
        if self.completeness.package_id != self.identity:
            _fail("package_completeness_identity_mismatch")
        self.completeness.require_complete()
        if self.completeness.actual_section_count != len(sections):
            _fail("package_section_count_mismatch")

        family_counts = {
            FINDING_OBJECT_FAMILY: (self.finding_count, self.finding_set_digest),
            FACT_OBJECT_FAMILY: (self.fact_count, self.fact_set_digest),
            BINDING_OBJECT_FAMILY: (self.binding_count, self.binding_set_digest),
        }
        for family, (count, digest) in family_counts.items():
            descriptor = self.completeness.family(family).require_complete()
            if (
                descriptor.actual_count != count
                or descriptor.actual_set_digest != digest
            ):
                _fail(f"package_{family}_membership_mismatch")

        integrity_sections = {
            item.section_id: item.digest for item in self.integrity.section_entries
        }
        if set(integrity_sections) != {item.identity for item in sections}:
            _fail("package_section_integrity_set_mismatch")
        for section in sections:
            if integrity_sections[section.identity] != section.integrity.digest:
                _fail("package_section_integrity_digest_mismatch")

    @property
    def section_count(self) -> int:
        return len(self.sections)

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": CANONICAL_PACKAGE_METADATA_CONTRACT,
            "identity": self.identity.as_dict(),
            "scope": self.scope.as_dict(),
            "native_execution": self.native_execution.as_dict(),
            "authority_execution_id": str(self.authority_execution_id.value),
            "chronology_reference": self.chronology_reference.as_dict(),
            "analytical_reference_id": self.analytical_reference_id.as_dict(),
            "terminal_outcome": self.terminal_outcome.value,
            "finding_count": self.finding_count,
            "finding_set_digest": self.finding_set_digest.as_dict(),
            "fact_count": self.fact_count,
            "fact_set_digest": self.fact_set_digest.as_dict(),
            "binding_count": self.binding_count,
            "binding_set_digest": self.binding_set_digest.as_dict(),
            "section_count": self.section_count,
            "sections": tuple(item.as_dict() for item in self.sections),
            "versions": self.versions.as_dict(),
            "build_mode": self.build_mode.value,
            "authority_status": self.authority_status.value,
            "integrity": self.integrity.as_dict(),
            "completeness": self.completeness.as_dict(),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.as_dict())

    @property
    def canonical_text(self) -> str:
        return canonical_json_text(self.as_dict())


PackageMetadata = CanonicalAuthorityPackageMetadata


__all__ = (
    "BINDING_OBJECT_FAMILY",
    "CANONICAL_PACKAGE_METADATA_CONTRACT",
    "CanonicalAuthorityPackageMetadata",
    "FACT_OBJECT_FAMILY",
    "FINDING_OBJECT_FAMILY",
    "OBJECT_FAMILY_DESCRIPTOR_CONTRACT",
    "OBJECT_INDEX_DESCRIPTOR_CONTRACT",
    "OBJECT_INTEGRITY_ENTRY_CONTRACT",
    "ObjectFamilyCountDigestDescriptor",
    "ObjectIndexDescriptor",
    "ObjectIntegrityEntry",
    "PACKAGE_COMPLETENESS_DESCRIPTOR_CONTRACT",
    "PACKAGE_INTEGRITY_DESCRIPTOR_CONTRACT",
    "PACKAGE_VERSION_BINDING_CONTRACT",
    "PackageBuildMode",
    "PackageCompletenessDescriptor",
    "PackageIntegrityDescriptor",
    "PackageMetadata",
    "PackageVersionBundleBinding",
    "SECTION_DESCRIPTOR_CONTRACT",
    "SECTION_INTEGRITY_ENTRY_CONTRACT",
    "SectionDescriptor",
    "SectionIntegrityEntry",
)
