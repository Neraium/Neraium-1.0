"""Pure P0.3 logical authority contracts.

These immutable records validate already-produced analytical values.  They do
not invoke SII, classification, confidence, persistence, chronology, storage,
publication, routing, or presentation behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Iterable, Mapping
from uuid import UUID

from app.services.authority_contract_common import (
    AuthorityScope,
    Completeness,
    CompletenessState,
    ContractValidationError,
    ContractVersion,
    Integrity,
    Limitation,
    Provenance,
    ScopeLevel,
    TypedDigest,
    VersionBundle,
    canonical_json_bytes,
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
    NativeResultIdentity,
    PersistenceAssessmentIdentity,
    ordered_identity_set_digest,
    unordered_identity_set_digest,
)
from app.services.telemetry_event_time import ChronologyReference
from app.services.analysis_provenance import FINDING_RULE_VERSION
from app.services.finding_confidence import SCHEMA_VERSION as FINDING_CONFIDENCE_SCHEMA_VERSION


AUTHORITATIVE_ANALYSIS_CONTRACT = "authoritative-analysis.v1"
ANALYTICAL_REFERENCE_RECORD_CONTRACT = "analytical-reference-record.v1"
EVIDENCE_FACT_RECORD_CONTRACT = "evidence-fact-record.v1"
EVIDENCE_BINDING_RECORD_CONTRACT = "evidence-binding-record.v1"
AUTHORITATIVE_FINDING_CONTRACT = "authoritative-finding.v1"
PROJECTION_ENVELOPE_CONTRACT = "authority-projection-envelope.v1"
CLASSIFICATION_RULE_CONTRACT = "finding-classification"
CLASSIFICATION_RULE_VERSION = FINDING_RULE_VERSION
CONFIDENCE_CONTRACT_NAME = "finding-confidence"
CONFIDENCE_CONTRACT_VERSION = FINDING_CONFIDENCE_SCHEMA_VERSION
CLASSIFICATION_OUTPUT_DIGEST_CONTRACT = "classification-binding-output.v1"
PERSISTENCE_OUTPUT_DIGEST_CONTRACT = "persistence-assessment-output.v1"
CONFIDENCE_OUTPUT_DIGEST_CONTRACT = "confidence-binding-output.v1"
CONFIDENCE_INPUT_DIGEST_CONTRACT = "finding-confidence-input-set.v1"
CLASSIFICATION_OUTPUT_VERSION = ContractVersion("classification-binding-output", "1")
PERSISTENCE_OUTPUT_VERSION = ContractVersion("persistence-assessment-output", "1")
CONFIDENCE_OUTPUT_VERSION = ContractVersion("confidence-binding-output", "1")
CONFIDENCE_INPUT_VERSION = ContractVersion("finding-confidence-input", "1")


def _fail(code: str) -> None:
    raise ContractValidationError(code)


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
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


def _base_scope_values(scope: AuthorityScope) -> tuple[str | None, ...]:
    if not isinstance(scope, AuthorityScope):
        _fail("authority_scope_required")
    if scope.level not in {
        ScopeLevel.ASSET,
        ScopeLevel.NATIVE_RESULT,
        ScopeLevel.AUTHORITY_EXECUTION,
        ScopeLevel.FINDING,
    }:
        _fail("full_asset_scope_required")
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
    values = tuple(_base_scope_values(scope) for scope in scopes)
    if not values or len(set(values)) != 1:
        _fail("authority_base_scope_mismatch")


def _limitations_digest(limitations: tuple[Limitation, ...]) -> TypedDigest:
    ordered = tuple(
        item.as_dict()
        for item in sorted(limitations, key=lambda value: canonical_json_bytes(value.as_dict()))
    )
    return TypedDigest.from_value(
        "limitation-set.v1", ordered
    )


def _unique_identities(values: Iterable[Any], code: str) -> tuple[Any, ...]:
    frozen = tuple(values)
    ids = tuple(str(getattr(item, "value", item)) for item in frozen)
    if len(ids) != len(set(ids)):
        _fail(code)
    return frozen


def _require_binding_identity_ownership(
    binding_ids: Iterable[EvidenceBindingIdentity],
    finding_id: AnalyticalFindingIdentity,
    code: str,
) -> tuple[EvidenceBindingIdentity, ...]:
    bindings = tuple(binding_ids)
    for binding_id in bindings:
        if not isinstance(binding_id, EvidenceBindingIdentity):
            _fail(code)
        if binding_id.analytical_finding_id != finding_id:
            _fail(code)
        if binding_id.authority_execution_id != finding_id.authority_execution_id:
            _fail(code)
    return bindings


def _require_output_integrity(
    integrity: Integrity,
    expected_digest: TypedDigest,
    expected_version: ContractVersion,
    code: str,
) -> None:
    if not isinstance(integrity, Integrity):
        _fail(f"{code}_required")
    if integrity.digest != expected_digest or integrity.contract_version != expected_version:
        _fail(f"{code}_mismatch")


def classification_output_digest(
    *, value: str, trace: tuple[str, ...], evidence_binding_ids: tuple[EvidenceBindingIdentity, ...]
) -> TypedDigest:
    return TypedDigest.from_value(
        CLASSIFICATION_OUTPUT_DIGEST_CONTRACT,
        {
            "value": value,
            "trace": trace,
            "evidence_binding_ids": tuple(str(item.value) for item in evidence_binding_ids),
        },
    )


@dataclass(frozen=True, slots=True)
class PersistencePayload:
    """Immutable lossless payload from the selected persistence producer."""

    canonical_payload: bytes

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> PersistencePayload:
        return cls(canonical_json_bytes(payload))

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_payload, bytes):
            _fail("persistence_payload_bytes_required")
        try:
            decoded = json.loads(self.canonical_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractValidationError("persistence_payload_invalid") from exc
        if not isinstance(decoded, dict) or canonical_json_bytes(decoded) != self.canonical_payload:
            _fail("persistence_payload_must_be_canonical_mapping")
        if not isinstance(decoded.get("status"), str) or not decoded["status"]:
            _fail("persistence_payload_status_required")
        if (
            not isinstance(decoded.get("reason"), str)
            or not decoded["reason"]
            or "evidence_refs" not in decoded
        ):
            _fail("persistence_payload_traceability_required")
        if not isinstance(decoded["evidence_refs"], list) or any(
            not isinstance(item, str) or not item for item in decoded["evidence_refs"]
        ):
            _fail("persistence_payload_evidence_refs_invalid")

    def as_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_payload.decode("utf-8"))
        assert isinstance(value, dict)
        return value


@dataclass(frozen=True, slots=True)
class FindingConfidencePayload:
    """Exact immutable `finding-confidence-v1` structured producer output."""

    canonical_payload: bytes

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> FindingConfidencePayload:
        return cls(canonical_json_bytes(payload))

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_payload, bytes):
            _fail("finding_confidence_payload_bytes_required")
        try:
            decoded = json.loads(self.canonical_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractValidationError("finding_confidence_payload_invalid") from exc
        if not isinstance(decoded, dict) or canonical_json_bytes(decoded) != self.canonical_payload:
            _fail("finding_confidence_payload_must_be_canonical_mapping")
        required = {
            "schema_version",
            "change_detection",
            "interpretation",
            "persistence",
            "operating_context",
            "evidence_quality",
            "relationship_comparison",
        }
        if decoded.get("schema_version") != CONFIDENCE_CONTRACT_VERSION:
            _fail("finding_confidence_payload_schema_mismatch")
        if not required.issubset(decoded) or any(
            not isinstance(decoded[name], dict) for name in required - {"schema_version"}
        ):
            _fail("finding_confidence_payload_structure_invalid")
        if set(decoded) - required - {"support_trend"}:
            _fail("finding_confidence_payload_unknown_field")
        if "support_trend" in decoded and not isinstance(decoded["support_trend"], dict):
            _fail("finding_confidence_payload_support_trend_invalid")

    def as_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_payload.decode("utf-8"))
        assert isinstance(value, dict)
        return value


def persistence_output_digest(
    *,
    assessment_value: str,
    payload: PersistencePayload,
    evidence_binding_ids: tuple[EvidenceBindingIdentity, ...],
    analytical_reference_id: AnalyticalReferenceIdentity,
    limitations: tuple[Limitation, ...],
    dependency_state: P05DependencyState,
) -> TypedDigest:
    return TypedDigest.from_value(
        PERSISTENCE_OUTPUT_DIGEST_CONTRACT,
        {
            "assessment_value": assessment_value,
            "payload": payload.as_dict(),
            "evidence_binding_ids": tuple(str(item.value) for item in evidence_binding_ids),
            "analytical_reference_id": str(analytical_reference_id.value),
            "limitations": tuple(item.as_dict() for item in limitations),
            "dependency_state": dependency_state.value,
        },
    )


def confidence_output_digest(
    *,
    payload: FindingConfidencePayload,
    dimensions: tuple[ConfidenceDimension, ...],
    persistence_assessment_id: PersistenceAssessmentIdentity,
    dependency_state: P05DependencyState,
) -> TypedDigest:
    return TypedDigest.from_value(
        CONFIDENCE_OUTPUT_DIGEST_CONTRACT,
        {
            "structured_payload": payload.as_dict(),
            "dimensions": tuple(item.as_dict() for item in dimensions),
            "aggregate": "aggregate_not_defined",
            "persistence_assessment_id": str(persistence_assessment_id.value),
            "dependency_state": dependency_state.value,
        },
    )


def confidence_input_set_digest(
    *,
    dimensions: tuple[ConfidenceDimension, ...],
    persistence_assessment_id: PersistenceAssessmentIdentity,
) -> TypedDigest:
    """Digest exact typed confidence inputs; no confidence math is performed."""

    return TypedDigest.from_value(
        CONFIDENCE_INPUT_DIGEST_CONTRACT,
        {
            "dimensions": tuple(item.as_dict() for item in dimensions),
            "persistence_assessment_id": str(persistence_assessment_id.value),
        },
    )


class TerminalOutcome(str, Enum):
    FINDINGS_PRESENT = "findings_present"
    STABLE_NO_CHANGE = "stable_no_change"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    PROCESSING_FAILURE = "processing_failure"
    INELIGIBLE_DATA = "ineligible_data"


def validate_terminal_outcome_cardinality(
    outcome: TerminalOutcome | str, finding_count: int
) -> TerminalOutcome:
    try:
        resolved = TerminalOutcome(outcome)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError("terminal_outcome_invalid") from exc
    if isinstance(finding_count, bool) or not isinstance(finding_count, int):
        _fail("terminal_outcome_finding_count_invalid")
    if resolved is TerminalOutcome.FINDINGS_PRESENT:
        if finding_count <= 0:
            _fail("findings_present_requires_positive_finding_count")
    elif finding_count != 0:
        _fail("zero_finding_terminal_outcome_requires_zero_findings")
    return resolved


class AuthorityStatus(str, Enum):
    AUTHORITATIVE = "authoritative"
    SHADOW = "shadow"
    LEGACY_BOUNDED = "legacy_bounded"
    UNAVAILABLE = "unavailable"


class EvidenceRole(str, Enum):
    SUPPORTING = "supporting"
    LIMITING = "limiting"
    CONTRADICTORY = "contradictory"
    CONTEXT_ONLY = "context_only"


class EvidenceAdmissibility(str, Enum):
    ADMITTED = "admitted"
    LIMITED = "limited"
    EXCLUDED = "excluded"


class P05DependencyState(str, Enum):
    NOT_REQUIRED = "not_required"
    REQUIRED_NON_LOSSLESS_CONFIDENCE = "required_non_lossless_confidence"
    REQUIRED_NON_LOSSLESS_PERSISTENCE = "required_non_lossless_persistence"
    REQUIRED_FINDING_CONSOLIDATION = "required_finding_consolidation"
    REQUIRED_AGGREGATE_CONFIDENCE = "required_aggregate_confidence"
    REQUIRED_LONGITUDINAL_CONTINUATION = "required_longitudinal_continuation"


@dataclass(frozen=True, slots=True)
class NativeExecutionBinding:
    source_kind: str
    source_identity: UUID | str
    source_integrity: Integrity
    terminal_state: str
    native_result_identity: NativeResultIdentity | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_kind", _text(self.source_kind, "native_source_kind_invalid"))
        object.__setattr__(
            self, "source_identity", _uuid(self.source_identity, "native_source_identity_invalid")
        )
        object.__setattr__(self, "terminal_state", _text(self.terminal_state, "native_terminal_state_invalid"))
        if self.terminal_state not in {"completed", "processing_failure", "ineligible_data"}:
            _fail("native_terminal_state_unsupported")
        if not isinstance(self.source_integrity, Integrity):
            _fail("native_source_integrity_required")
        if self.native_result_identity is not None:
            if not isinstance(self.native_result_identity, NativeResultIdentity):
                _fail("native_result_identity_invalid")
            if self.native_result_identity.value != self.source_identity:
                _fail("native_result_source_identity_mismatch")

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "source_identity": str(self.source_identity),
            "source_integrity": self.source_integrity.as_dict(),
            "terminal_state": self.terminal_state,
            "native_result_identity": (
                self.native_result_identity.as_dict()
                if self.native_result_identity is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class AnalyticalReference:
    identity: AnalyticalReferenceIdentity
    scope: AuthorityScope
    producer_family: str
    state_identity: str
    state_version: str
    snapshot_identity: str
    chronology_generation: int
    chronology_binding: TypedDigest
    method_identity: ContractVersion
    configuration_identity: TypedDigest
    integrity: Integrity
    versions: VersionBundle

    def __post_init__(self) -> None:
        if not isinstance(self.identity, AnalyticalReferenceIdentity):
            _fail("analytical_reference_identity_required")
        self.scope.require_level(ScopeLevel.ASSET)
        if self.identity.scope != self.scope:
            _fail("analytical_reference_scope_mismatch")
        if self.producer_family != self.identity.producer_family:
            _fail("analytical_reference_producer_mismatch")
        if self.state_identity != self.identity.model_id or self.state_version != self.identity.model_version:
            _fail("analytical_reference_state_mismatch")
        if self.snapshot_identity != self.identity.snapshot_id:
            _fail("analytical_reference_snapshot_mismatch")
        if self.chronology_generation != self.identity.learning_generation:
            _fail("analytical_reference_generation_mismatch")
        if self.chronology_binding != self.identity.chronology_binding_digest:
            _fail("analytical_reference_chronology_binding_mismatch")
        if self.method_identity != self.identity.method_identity:
            _fail("analytical_reference_method_mismatch")
        if self.configuration_identity != self.identity.configuration_identity:
            _fail("analytical_reference_configuration_mismatch")
        if not isinstance(self.integrity, Integrity) or self.integrity.digest != self.identity.integrity_identity:
            _fail("analytical_reference_integrity_mismatch")
        if not isinstance(self.versions, VersionBundle):
            _fail("analytical_reference_versions_required")
        self.versions.require("analytical-reference", "1")
        self.versions.require(
            self.method_identity.contract, self.method_identity.version
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": ANALYTICAL_REFERENCE_RECORD_CONTRACT,
            "identity": self.identity.as_dict(),
            "scope": self.scope.as_dict(),
            "producer_family": self.producer_family,
            "state_identity": self.state_identity,
            "state_version": self.state_version,
            "snapshot_identity": self.snapshot_identity,
            "chronology_generation": self.chronology_generation,
            "chronology_binding": self.chronology_binding.as_dict(),
            "method_identity": self.method_identity.as_dict(),
            "configuration_identity": self.configuration_identity.as_dict(),
            "integrity": self.integrity.as_dict(),
            "versions": self.versions.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    identity: EvidenceFactIdentity
    authority_execution_id: AuthorityExecutionIdentity
    scope: AuthorityScope
    fact_type: str
    schema: ContractVersion
    subject_identity: str
    value_integrity: Integrity
    trace_identity: str
    analytical_reference_id: AnalyticalReferenceIdentity | None
    limitations: tuple[Limitation, ...]
    provenance: Provenance
    integrity: Integrity
    versions: VersionBundle

    def __post_init__(self) -> None:
        if not isinstance(self.identity, EvidenceFactIdentity):
            _fail("evidence_fact_identity_required")
        self.scope.require_level(ScopeLevel.ASSET)
        if self.identity.authority_execution_id != self.authority_execution_id:
            _fail("evidence_fact_authority_mismatch")
        if self.identity.subject_scope != self.scope:
            _fail("evidence_fact_scope_mismatch")
        if self.fact_type != self.identity.fact_type or self.schema != self.identity.producer_schema:
            _fail("evidence_fact_type_schema_mismatch")
        if self.subject_identity != self.identity.subject_identity:
            _fail("evidence_fact_subject_mismatch")
        if self.analytical_reference_id != self.identity.analytical_reference_id:
            _fail("evidence_fact_reference_mismatch")
        if not isinstance(self.value_integrity, Integrity):
            _fail("evidence_fact_value_integrity_required")
        if self.value_integrity.digest != self.identity.value_unit_event_time_digest:
            _fail("evidence_fact_value_integrity_mismatch")
        object.__setattr__(self, "trace_identity", _text(self.trace_identity, "evidence_fact_trace_required"))
        if any(not isinstance(item, Limitation) for item in self.limitations):
            _fail("evidence_fact_limitation_invalid")
        if not isinstance(self.provenance, Provenance) or not isinstance(self.integrity, Integrity):
            _fail("evidence_fact_traceability_required")
        if not isinstance(self.versions, VersionBundle):
            _fail("evidence_fact_versions_required")
        if self.versions != self.authority_execution_id.versions:
            _fail("evidence_fact_authority_versions_mismatch")
        self.versions.require(self.schema.contract, self.schema.version)

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": EVIDENCE_FACT_RECORD_CONTRACT,
            "identity": self.identity.as_dict(),
            "authority_execution_id": str(self.authority_execution_id.value),
            "scope": self.scope.as_dict(),
            "fact_type": self.fact_type,
            "schema": self.schema.as_dict(),
            "subject_identity": self.subject_identity,
            "value_integrity": self.value_integrity.as_dict(),
            "trace_identity": self.trace_identity,
            "analytical_reference_id": (
                str(self.analytical_reference_id.value)
                if self.analytical_reference_id is not None
                else None
            ),
            "limitations": tuple(item.as_dict() for item in self.limitations),
            "provenance": self.provenance.as_dict(),
            "integrity": self.integrity.as_dict(),
            "versions": self.versions.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    identity: EvidenceBindingIdentity
    authority_execution_id: AuthorityExecutionIdentity
    analytical_finding_id: AnalyticalFindingIdentity
    evidence_fact: EvidenceFact
    role: EvidenceRole
    admissibility: EvidenceAdmissibility
    qualification_contract: ContractVersion
    limitations: tuple[Limitation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, EvidenceBindingIdentity):
            _fail("evidence_binding_identity_required")
        try:
            role = EvidenceRole(self.role)
            admissibility = EvidenceAdmissibility(self.admissibility)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("evidence_binding_role_or_admissibility_invalid") from exc
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "admissibility", admissibility)
        if self.identity.authority_execution_id != self.authority_execution_id:
            _fail("evidence_binding_authority_mismatch")
        if self.identity.analytical_finding_id != self.analytical_finding_id:
            _fail("evidence_binding_finding_mismatch")
        if self.identity.evidence_fact_id != self.evidence_fact.identity:
            _fail("evidence_binding_fact_mismatch")
        if self.evidence_fact.authority_execution_id != self.authority_execution_id:
            _fail("evidence_binding_cross_execution_forbidden")
        _require_same_base_scope(
            self.analytical_finding_id.scope, self.evidence_fact.scope
        )
        if self.identity.role != role.value or self.identity.qualification != admissibility.value:
            _fail("evidence_binding_qualification_mismatch")
        if self.identity.qualification_contract != self.qualification_contract:
            _fail("evidence_binding_qualification_contract_mismatch")
        if any(not isinstance(item, Limitation) for item in self.limitations):
            _fail("evidence_binding_limitation_invalid")
        if self.identity.limitation_set_digest != _limitations_digest(self.limitations):
            _fail("evidence_binding_limitation_digest_mismatch")

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": EVIDENCE_BINDING_RECORD_CONTRACT,
            "identity": self.identity.as_dict(),
            "authority_execution_id": str(self.authority_execution_id.value),
            "analytical_finding_id": str(self.analytical_finding_id.value),
            "evidence_fact_id": str(self.evidence_fact.identity.value),
            "role": self.role.value,
            "admissibility": self.admissibility.value,
            "qualification_contract": self.qualification_contract.as_dict(),
            "limitations": tuple(item.as_dict() for item in self.limitations),
        }


@dataclass(frozen=True, slots=True)
class PersistenceAssessment:
    identity: PersistenceAssessmentIdentity
    analytical_finding_id: AnalyticalFindingIdentity
    method: ContractVersion
    assessment_value: str
    structured_payload: PersistencePayload
    evidence_binding_ids: tuple[EvidenceBindingIdentity, ...]
    analytical_reference_id: AnalyticalReferenceIdentity
    limitations: tuple[Limitation, ...]
    dependency_state: P05DependencyState
    output_integrity: Integrity

    def __post_init__(self) -> None:
        if self.identity.analytical_finding_id != self.analytical_finding_id:
            _fail("persistence_finding_mismatch")
        if self.identity.method != self.method:
            _fail("persistence_method_mismatch")
        object.__setattr__(self, "assessment_value", _text(self.assessment_value, "persistence_value_invalid"))
        if not isinstance(self.structured_payload, PersistencePayload):
            _fail("persistence_structured_payload_required")
        if self.structured_payload.as_dict()["status"] != self.assessment_value:
            _fail("persistence_payload_status_mismatch")
        bindings = _unique_identities(self.evidence_binding_ids, "persistence_binding_duplicate")
        _require_binding_identity_ownership(
            bindings, self.analytical_finding_id, "persistence_cross_finding_binding_forbidden"
        )
        object.__setattr__(self, "evidence_binding_ids", bindings)
        expected_facts = unordered_identity_set_digest(
            (item.evidence_fact_id for item in bindings),
            contract="persistence-fact-set.v1",
        )
        if expected_facts != self.identity.exact_fact_set_digest:
            _fail("persistence_fact_set_digest_mismatch")
        if self.analytical_reference_id != self.analytical_finding_id.analytical_reference_id:
            _fail("persistence_reference_mismatch")
        if any(not isinstance(item, Limitation) for item in self.limitations):
            _fail("persistence_limitation_invalid")
        try:
            state = P05DependencyState(self.dependency_state)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("persistence_dependency_state_invalid") from exc
        object.__setattr__(self, "dependency_state", state)
        _require_output_integrity(
            self.output_integrity,
            persistence_output_digest(
                assessment_value=self.assessment_value,
                payload=self.structured_payload,
                evidence_binding_ids=self.evidence_binding_ids,
                analytical_reference_id=self.analytical_reference_id,
                limitations=self.limitations,
                dependency_state=state,
            ),
            PERSISTENCE_OUTPUT_VERSION,
            "persistence_output_integrity",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.as_dict(),
            "analytical_finding_id": str(self.analytical_finding_id.value),
            "method": self.method.as_dict(),
            "assessment_value": self.assessment_value,
            "structured_payload": self.structured_payload.as_dict(),
            "evidence_binding_ids": tuple(str(item.value) for item in self.evidence_binding_ids),
            "analytical_reference_id": str(self.analytical_reference_id.value),
            "limitations": tuple(item.as_dict() for item in self.limitations),
            "dependency_state": self.dependency_state.value,
            "output_integrity": self.output_integrity.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ClassificationBinding:
    identity: ClassificationBindingIdentity
    analytical_finding_id: AnalyticalFindingIdentity
    value: str
    trace: tuple[str, ...]
    evidence_binding_ids: tuple[EvidenceBindingIdentity, ...]
    input_integrity: Integrity
    output_integrity: Integrity

    def __post_init__(self) -> None:
        if self.identity.analytical_finding_id != self.analytical_finding_id:
            _fail("classification_finding_mismatch")
        if self.identity.classifier_rule != ContractVersion(
            CLASSIFICATION_RULE_CONTRACT, CLASSIFICATION_RULE_VERSION
        ):
            _fail("classification_rule_version_mismatch")
        object.__setattr__(self, "value", _text(self.value, "classification_value_invalid"))
        if not self.trace:
            _fail("classification_trace_required")
        trace = tuple(_text(item, "classification_trace_invalid") for item in self.trace)
        object.__setattr__(self, "trace", trace)
        bindings = _unique_identities(self.evidence_binding_ids, "classification_binding_duplicate")
        _require_binding_identity_ownership(
            bindings, self.analytical_finding_id, "classification_cross_finding_binding_forbidden"
        )
        object.__setattr__(self, "evidence_binding_ids", bindings)
        expected = ordered_identity_set_digest(
            bindings, contract="classification-evidence-bindings.v1"
        )
        if expected != self.identity.ordered_binding_set_digest:
            _fail("classification_binding_set_digest_mismatch")
        if not isinstance(self.input_integrity, Integrity):
            _fail("classification_input_integrity_required")
        if (
            self.input_integrity.digest != self.identity.ordered_binding_set_digest
            or self.input_integrity.contract_version != self.identity.input_contract
        ):
            _fail("classification_input_integrity_mismatch")
        _require_output_integrity(
            self.output_integrity,
            classification_output_digest(
                value=self.value,
                trace=self.trace,
                evidence_binding_ids=self.evidence_binding_ids,
            ),
            CLASSIFICATION_OUTPUT_VERSION,
            "classification_output_integrity",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.as_dict(),
            "analytical_finding_id": str(self.analytical_finding_id.value),
            "value": self.value,
            "trace": self.trace,
            "evidence_binding_ids": tuple(str(item.value) for item in self.evidence_binding_ids),
            "input_integrity": self.input_integrity.as_dict(),
            "output_integrity": self.output_integrity.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ConfidenceDimension:
    """Typed evidence membership for one key in the structured payload."""

    name: str
    evidence_binding_ids: tuple[EvidenceBindingIdentity, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "confidence_dimension_name_invalid"))
        object.__setattr__(
            self,
            "evidence_binding_ids",
            _unique_identities(self.evidence_binding_ids, "confidence_dimension_binding_duplicate"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "evidence_binding_ids": tuple(str(item.value) for item in self.evidence_binding_ids),
        }


@dataclass(frozen=True, slots=True)
class ConfidenceBinding:
    identity: ConfidenceBindingIdentity
    analytical_finding_id: AnalyticalFindingIdentity
    structured_payload: FindingConfidencePayload
    dimensions: tuple[ConfidenceDimension, ...]
    persistence_assessment: PersistenceAssessment
    input_integrity: Integrity
    dependency_state: P05DependencyState
    output_integrity: Integrity

    def __post_init__(self) -> None:
        if self.identity.analytical_finding_id != self.analytical_finding_id:
            _fail("confidence_finding_mismatch")
        if self.identity.confidence_contract != ContractVersion(
            CONFIDENCE_CONTRACT_NAME, CONFIDENCE_CONTRACT_VERSION
        ):
            _fail("confidence_contract_version_mismatch")
        if self.identity.persistence_assessment_id != self.persistence_assessment.identity:
            _fail("confidence_persistence_mismatch")
        if not isinstance(self.structured_payload, FindingConfidencePayload):
            _fail("confidence_structured_payload_required")
        if not self.dimensions or any(
            not isinstance(item, ConfidenceDimension) for item in self.dimensions
        ):
            _fail("confidence_dimension_invalid")
        if len({item.name for item in self.dimensions}) != len(self.dimensions):
            _fail("confidence_dimensions_invalid")
        payload_dimensions = self.structured_payload.as_dict()
        if any(item.name not in payload_dimensions for item in self.dimensions):
            _fail("confidence_dimension_payload_key_mismatch")
        for dimension in self.dimensions:
            _require_binding_identity_ownership(
                dimension.evidence_binding_ids,
                self.analytical_finding_id,
                "confidence_cross_finding_binding_forbidden",
            )
        expected_inputs = confidence_input_set_digest(
            dimensions=self.dimensions,
            persistence_assessment_id=self.persistence_assessment.identity,
        )
        if self.identity.exact_input_set_digest != expected_inputs:
            _fail("confidence_exact_input_set_mismatch")
        if not isinstance(self.input_integrity, Integrity):
            _fail("confidence_input_integrity_required")
        if (
            self.input_integrity.digest != self.identity.exact_input_set_digest
            or self.input_integrity.contract_version != CONFIDENCE_INPUT_VERSION
        ):
            _fail("confidence_input_integrity_mismatch")
        try:
            state = P05DependencyState(self.dependency_state)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("confidence_dependency_state_invalid") from exc
        object.__setattr__(self, "dependency_state", state)
        _require_output_integrity(
            self.output_integrity,
            confidence_output_digest(
                payload=self.structured_payload,
                dimensions=self.dimensions,
                persistence_assessment_id=self.persistence_assessment.identity,
                dependency_state=state,
            ),
            CONFIDENCE_OUTPUT_VERSION,
            "confidence_output_integrity",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.as_dict(),
            "analytical_finding_id": str(self.analytical_finding_id.value),
            "contract_version": CONFIDENCE_CONTRACT_VERSION,
            "structured_payload": self.structured_payload.as_dict(),
            "dimensions": tuple(item.as_dict() for item in self.dimensions),
            "aggregate": "aggregate_not_defined",
            "persistence_assessment_id": str(self.persistence_assessment.identity.value),
            "input_integrity": self.input_integrity.as_dict(),
            "dependency_state": self.dependency_state.value,
            "output_integrity": self.output_integrity.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class AuthoritativeFinding:
    identity: AnalyticalFindingIdentity
    authority_execution_id: AuthorityExecutionIdentity
    affected_scope: AuthorityScope
    category: str
    finding_type: str
    subject_identity: str
    analytical_reference: AnalyticalReference
    evidence_bindings: tuple[EvidenceBinding, ...]
    classification: ClassificationBinding
    confidence: ConfidenceBinding
    persistence: PersistenceAssessment
    limitations: tuple[Limitation, ...]
    versions: VersionBundle

    def __post_init__(self) -> None:
        if self.identity.authority_execution_id != self.authority_execution_id:
            _fail("finding_authority_mismatch")
        self.affected_scope.require_level(ScopeLevel.ASSET)
        if self.identity.affected_scope != self.affected_scope:
            _fail("finding_scope_mismatch")
        object.__setattr__(self, "category", _text(self.category, "finding_category_invalid"))
        if self.finding_type != self.identity.finding_type or self.subject_identity != self.identity.subject_identity:
            _fail("finding_semantic_identity_mismatch")
        if self.analytical_reference.identity != self.identity.analytical_reference_id:
            _fail("finding_reference_mismatch")
        bindings = _unique_identities(self.evidence_bindings, "finding_evidence_binding_duplicate")
        if not bindings:
            _fail("finding_evidence_binding_required")
        object.__setattr__(self, "evidence_bindings", bindings)
        for binding in bindings:
            if binding.analytical_finding_id != self.identity:
                _fail("finding_cross_binding_forbidden")
        owned_binding_ids = {binding.identity for binding in bindings}
        if self.classification.analytical_finding_id != self.identity:
            _fail("finding_classification_mismatch")
        if self.confidence.analytical_finding_id != self.identity:
            _fail("finding_confidence_mismatch")
        if self.persistence.analytical_finding_id != self.identity:
            _fail("finding_persistence_mismatch")
        if self.confidence.persistence_assessment != self.persistence:
            _fail("finding_persistence_not_single_source")
        downstream_binding_ids = set(self.classification.evidence_binding_ids)
        downstream_binding_ids.update(self.persistence.evidence_binding_ids)
        for dimension in self.confidence.dimensions:
            downstream_binding_ids.update(dimension.evidence_binding_ids)
        if not downstream_binding_ids.issubset(owned_binding_ids):
            _fail("finding_downstream_evidence_binding_not_owned")
        if any(not isinstance(item, Limitation) for item in self.limitations):
            _fail("finding_limitation_invalid")
        if not isinstance(self.versions, VersionBundle):
            _fail("finding_versions_required")
        if self.versions != self.authority_execution_id.versions:
            _fail("finding_authority_versions_mismatch")
        self.versions.validate_required(
            (
                self.identity.determination_contract,
                self.analytical_reference.method_identity,
                self.classification.identity.classifier_rule,
                self.classification.identity.input_contract,
                self.confidence.identity.confidence_contract,
                self.persistence.method,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": AUTHORITATIVE_FINDING_CONTRACT,
            "identity": self.identity.as_dict(),
            "authority_execution_id": str(self.authority_execution_id.value),
            "affected_scope": self.affected_scope.as_dict(),
            "category": self.category,
            "finding_type": self.finding_type,
            "subject_identity": self.subject_identity,
            "analytical_reference_id": str(self.analytical_reference.identity.value),
            "evidence_bindings": tuple(item.as_dict() for item in self.evidence_bindings),
            "classification": self.classification.as_dict(),
            "confidence": self.confidence.as_dict(),
            "persistence": self.persistence.as_dict(),
            "limitations": tuple(item.as_dict() for item in self.limitations),
            "versions": self.versions.as_dict(),
        }


def authoritative_evidence_set_digest(
    facts: Iterable[EvidenceFact], bindings: Iterable[EvidenceBinding]
) -> TypedDigest:
    members = sorted(
        [f"fact:{item.identity.value}" for item in facts]
        + [f"binding:{item.identity.value}" for item in bindings]
    )
    return TypedDigest.from_value("authoritative-evidence-set.v1", tuple(members))


@dataclass(frozen=True, slots=True)
class AuthoritativeAnalysis:
    authority_execution_id: AuthorityExecutionIdentity
    native_execution: NativeExecutionBinding
    scope: AuthorityScope
    chronology_reference: ChronologyReference
    analytical_reference: AnalyticalReference
    terminal_outcome: TerminalOutcome
    authoritative_findings: tuple[AuthoritativeFinding, ...]
    evidence_facts: tuple[EvidenceFact, ...]
    finding_set_identity: TypedDigest
    evidence_set_identity: TypedDigest
    versions: VersionBundle
    limitations: tuple[Limitation, ...]
    provenance: Provenance
    integrity: Integrity
    completeness: Completeness

    def __post_init__(self) -> None:
        self.scope.require_level(ScopeLevel.ASSET)
        if self.authority_execution_id.scope != self.scope:
            _fail("authoritative_analysis_scope_mismatch")
        if self.chronology_reference.execution_identity != self.authority_execution_id.chronology_execution_id:
            _fail("authoritative_analysis_chronology_mismatch")
        if self.analytical_reference.identity != self.chronology_reference.selected_analytical_reference_id:
            _fail("authoritative_analysis_reference_mismatch")
        if self.native_execution.source_identity != self.authority_execution_id.native_terminal_source_id:
            _fail("authoritative_analysis_native_source_mismatch")
        if self.native_execution.source_kind != self.authority_execution_id.source_kind:
            _fail("authoritative_analysis_native_source_kind_mismatch")
        if self.native_execution.source_integrity.digest != self.authority_execution_id.native_terminal_digest:
            _fail("authoritative_analysis_native_integrity_mismatch")
        if self.native_execution.native_result_identity is not None:
            _require_same_base_scope(self.scope, self.native_execution.native_result_identity.scope)
        findings = _unique_identities(self.authoritative_findings, "authoritative_finding_duplicate")
        facts = _unique_identities(self.evidence_facts, "authoritative_evidence_fact_duplicate")
        object.__setattr__(self, "authoritative_findings", findings)
        object.__setattr__(self, "evidence_facts", facts)
        outcome = validate_terminal_outcome_cardinality(self.terminal_outcome, len(findings))
        object.__setattr__(self, "terminal_outcome", outcome)
        if outcome in {
            TerminalOutcome.FINDINGS_PRESENT,
            TerminalOutcome.STABLE_NO_CHANGE,
            TerminalOutcome.INSUFFICIENT_EVIDENCE,
        }:
            self.chronology_reference.require_authority_bindable()
            if self.native_execution.terminal_state != "completed":
                _fail("completed_analysis_requires_completed_native_execution")
        elif self.native_execution.terminal_state != outcome.value:
            _fail("terminal_analysis_native_state_mismatch")
        all_bindings: list[EvidenceBinding] = []
        fact_ids = {item.identity for item in facts}
        for finding in findings:
            if finding.authority_execution_id != self.authority_execution_id:
                _fail("authoritative_analysis_cross_finding_forbidden")
            if finding.analytical_reference != self.analytical_reference:
                _fail("authoritative_analysis_finding_reference_mismatch")
            if (
                finding.confidence.dependency_state is not P05DependencyState.NOT_REQUIRED
                or finding.persistence.dependency_state is not P05DependencyState.NOT_REQUIRED
            ):
                _fail("canonical_authority_blocked_by_p0_5_dependency")
            all_bindings.extend(finding.evidence_bindings)
        for fact in facts:
            if fact.authority_execution_id != self.authority_execution_id:
                _fail("authoritative_analysis_cross_fact_forbidden")
        for binding in all_bindings:
            if binding.evidence_fact.identity not in fact_ids:
                _fail("authoritative_analysis_binding_fact_missing")
        expected_findings = unordered_identity_set_digest(
            (item.identity for item in findings), contract="authoritative-finding-set.v1"
        )
        if self.finding_set_identity != expected_findings:
            _fail("authoritative_analysis_finding_set_mismatch")
        if self.evidence_set_identity != authoritative_evidence_set_digest(facts, all_bindings):
            _fail("authoritative_analysis_evidence_set_mismatch")
        if not isinstance(self.versions, VersionBundle):
            _fail("authoritative_analysis_versions_required")
        if self.versions != self.authority_execution_id.versions:
            _fail("authoritative_analysis_authority_versions_mismatch")
        if self.analytical_reference.versions != self.versions:
            _fail("authoritative_analysis_reference_versions_mismatch")
        if any(not isinstance(item, Limitation) for item in self.limitations):
            _fail("authoritative_analysis_limitation_invalid")
        if not isinstance(self.provenance, Provenance) or not isinstance(self.integrity, Integrity):
            _fail("authoritative_analysis_traceability_required")
        self.completeness.require_canonical_authority()

    @property
    def authoritative_finding_ids(self) -> tuple[AnalyticalFindingIdentity, ...]:
        return tuple(item.identity for item in self.authoritative_findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": AUTHORITATIVE_ANALYSIS_CONTRACT,
            "authority_execution_id": str(self.authority_execution_id.value),
            "native_execution": self.native_execution.as_dict(),
            "scope": self.scope.as_dict(),
            "chronology_reference": self.chronology_reference.as_dict(),
            "analytical_reference": self.analytical_reference.as_dict(),
            "terminal_outcome": self.terminal_outcome.value,
            "authoritative_finding_ids": tuple(str(item.value) for item in self.authoritative_finding_ids),
            "authoritative_findings": tuple(item.as_dict() for item in self.authoritative_findings),
            "evidence_facts": tuple(item.as_dict() for item in self.evidence_facts),
            "finding_set_identity": self.finding_set_identity.as_dict(),
            "evidence_set_identity": self.evidence_set_identity.as_dict(),
            "versions": self.versions.as_dict(),
            "limitations": tuple(item.as_dict() for item in self.limitations),
            "provenance": self.provenance.as_dict(),
            "integrity": self.integrity.as_dict(),
            "completeness": self.completeness.as_dict(),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.as_dict())


@dataclass(frozen=True, slots=True)
class ProjectionCursorReference:
    opaque_reference: str
    contract_version: ContractVersion
    integrity: Integrity

    def __post_init__(self) -> None:
        object.__setattr__(self, "opaque_reference", _text(self.opaque_reference, "projection_cursor_invalid"))
        if not isinstance(self.contract_version, ContractVersion) or not isinstance(self.integrity, Integrity):
            _fail("projection_cursor_contract_invalid")

    def as_dict(self) -> dict[str, Any]:
        return {
            "opaque_reference": self.opaque_reference,
            "contract_version": self.contract_version.as_dict(),
            "integrity": self.integrity.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ProjectionEnvelope:
    status: AuthorityStatus
    scope: AuthorityScope
    native_source_identity: UUID | str
    native_result_identity: NativeResultIdentity | None
    authority_execution_id: AuthorityExecutionIdentity
    package_id: CanonicalPackageIdentity | None
    finding_id: AnalyticalFindingIdentity | None
    completeness: Completeness
    total: int | None
    returned_count: int
    returned_ids: tuple[UUID | str, ...]
    authoritative_set_digest: TypedDigest | None
    omissions: tuple[str, ...]
    cursor: ProjectionCursorReference | None
    integrity: Integrity
    etag_inputs: tuple[TypedDigest, ...]
    version: ContractVersion

    def __post_init__(self) -> None:
        try:
            status = AuthorityStatus(self.status)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("projection_authority_status_invalid") from exc
        object.__setattr__(self, "status", status)
        native_source = _uuid(
            self.native_source_identity, "projection_native_source_identity_invalid"
        )
        object.__setattr__(self, "native_source_identity", native_source)
        if native_source != self.authority_execution_id.native_terminal_source_id:
            _fail("projection_native_source_authority_mismatch")
        expected_level = ScopeLevel.FINDING if self.finding_id is not None else ScopeLevel.AUTHORITY_EXECUTION
        self.scope.require_level(expected_level)
        _require_same_base_scope(self.scope, self.authority_execution_id.scope)
        if self.native_result_identity is not None:
            if not isinstance(self.native_result_identity, NativeResultIdentity):
                _fail("projection_native_result_identity_invalid")
            _require_same_base_scope(self.scope, self.native_result_identity.scope)
            if self.native_result_identity.value != native_source:
                _fail("projection_native_result_source_mismatch")
            if self.scope.native_result_id != str(self.native_result_identity.value):
                _fail("projection_native_scope_mismatch")
        elif self.scope.native_result_id is not None:
            _fail("projection_terminal_decision_cannot_alias_native_result")
        if self.scope.authority_execution_id != str(self.authority_execution_id.value):
            _fail("projection_authority_scope_mismatch")
        if self.package_id is not None and self.package_id.authority_execution_id != self.authority_execution_id:
            _fail("projection_package_authority_mismatch")
        if self.finding_id is not None:
            if self.finding_id.authority_execution_id != self.authority_execution_id:
                _fail("projection_finding_authority_mismatch")
            if self.scope.finding_id != str(self.finding_id.value):
                _fail("projection_finding_scope_mismatch")
        if isinstance(self.returned_count, bool) or not isinstance(self.returned_count, int) or self.returned_count < 0:
            _fail("projection_returned_count_invalid")
        returned = tuple(_uuid(item, "projection_returned_id_invalid") for item in self.returned_ids)
        if len(returned) != len(set(returned)) or len(returned) != self.returned_count:
            _fail("projection_returned_identity_count_mismatch")
        object.__setattr__(self, "returned_ids", returned)
        omissions = tuple(_text(item, "projection_omission_invalid") for item in self.omissions)
        if len(omissions) != len(set(omissions)):
            _fail("projection_omission_duplicate")
        omissions = tuple(sorted(omissions))
        object.__setattr__(self, "omissions", omissions)
        state = self.completeness.state
        if (status is AuthorityStatus.UNAVAILABLE) != (state is CompletenessState.UNAVAILABLE):
            _fail("projection_status_completeness_mismatch")
        if state is CompletenessState.UNAVAILABLE:
            if self.returned_count != 0 or returned or self.cursor is not None:
                _fail("unavailable_projection_cannot_return_objects")
            if not omissions:
                _fail("unavailable_projection_requires_omission_reason")
            if self.total is not None and (
                isinstance(self.total, bool)
                or not isinstance(self.total, int)
                or self.total < 0
            ):
                _fail("unavailable_projection_total_invalid")
        else:
            if isinstance(self.total, bool) or not isinstance(self.total, int) or self.total < self.returned_count:
                _fail("projection_total_invalid")
            if self.authoritative_set_digest is None:
                _fail("projection_authoritative_set_digest_required")
            if state is CompletenessState.COMPLETE:
                if self.returned_count != self.total or omissions:
                    _fail("complete_projection_count_or_omission_mismatch")
            elif state is CompletenessState.PARTIAL:
                if self.returned_count == self.total and not omissions:
                    _fail("partial_projection_requires_bounded_omission")
                if self.cursor is None:
                    _fail("partial_projection_cursor_required")
        if tuple(self.completeness.omissions) != tuple(sorted(omissions)):
            _fail("projection_completeness_omission_mismatch")
        if not isinstance(self.integrity, Integrity):
            _fail("projection_integrity_required")
        if not self.etag_inputs or any(not isinstance(item, TypedDigest) for item in self.etag_inputs):
            _fail("projection_etag_inputs_required")
        if not isinstance(self.version, ContractVersion):
            _fail("projection_version_required")

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": PROJECTION_ENVELOPE_CONTRACT,
            "status": self.status.value,
            "scope": self.scope.as_dict(),
            "native_source_id": str(self.native_source_identity),
            "native_result_id": (
                str(self.native_result_identity.value)
                if self.native_result_identity is not None
                else None
            ),
            "authority_execution_id": str(self.authority_execution_id.value),
            "package_id": str(self.package_id.value) if self.package_id is not None else None,
            "finding_id": str(self.finding_id.value) if self.finding_id is not None else None,
            "completeness": self.completeness.as_dict(),
            "total": self.total,
            "returned_count": self.returned_count,
            "returned_ids": tuple(str(item) for item in self.returned_ids),
            "authoritative_set_digest": (
                self.authoritative_set_digest.as_dict()
                if self.authoritative_set_digest is not None
                else None
            ),
            "omissions": self.omissions,
            "cursor": self.cursor.as_dict() if self.cursor is not None else None,
            "integrity": self.integrity.as_dict(),
            "etag_inputs": tuple(item.as_dict() for item in self.etag_inputs),
            "version": self.version.as_dict(),
        }


__all__ = (
    "ANALYTICAL_REFERENCE_RECORD_CONTRACT",
    "AUTHORITATIVE_ANALYSIS_CONTRACT",
    "AUTHORITATIVE_FINDING_CONTRACT",
    "AuthorityStatus",
    "AuthoritativeAnalysis",
    "AuthoritativeFinding",
    "AnalyticalReference",
    "ClassificationBinding",
    "CLASSIFICATION_OUTPUT_VERSION",
    "ConfidenceBinding",
    "ConfidenceDimension",
    "CONFIDENCE_OUTPUT_VERSION",
    "CONFIDENCE_INPUT_VERSION",
    "EvidenceAdmissibility",
    "EvidenceBinding",
    "EvidenceFact",
    "EvidenceRole",
    "FindingConfidencePayload",
    "NativeExecutionBinding",
    "P05DependencyState",
    "PersistenceAssessment",
    "PersistencePayload",
    "PERSISTENCE_OUTPUT_VERSION",
    "ProjectionCursorReference",
    "ProjectionEnvelope",
    "TerminalOutcome",
    "authoritative_evidence_set_digest",
    "classification_output_digest",
    "confidence_output_digest",
    "confidence_input_set_digest",
    "persistence_output_digest",
    "validate_terminal_outcome_cardinality",
)
