"""Pure deterministic identities for reconciled analytical authority.

This module owns only the directed identity graph.  It deliberately does not
schedule chronology, run analysis, publish records, or persist packages.  New
UUID identities use one unambiguous canonical byte contract; the two existing
identity authorities (canonical observations and P0.1 native results) are
wrapped without changing their allocation or derivation.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import re
from typing import Any, ClassVar, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from app.services.authority_contract_common import (
    AuthorityScope,
    ContractVersion,
    ScopeLevel,
    TypedDigest,
    VersionBundle,
    canonical_utc_timestamp,
)
from app.services.telemetry_result_artifact import (
    ARTIFACT_SCHEMA_VERSION,
    canonical_result_id,
)


IDENTITY_CANONICALIZATION_VERSION = "typed-length-prefixed-utf8.v1"
_CONTRACT_URL_ROOT = "https://neraium.com/contracts/"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,511}$")
_COMPONENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_COMPONENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


def _namespace(contract: str) -> UUID:
    """Mechanically derive a frozen type namespace from its contract URL."""

    return uuid5(NAMESPACE_URL, f"{_CONTRACT_URL_ROOT}{contract}")


CANONICAL_OBSERVATION_CONTRACT = "canonical-observation-existing.v1"
CHRONOLOGY_SLOT_CONTRACT = "chronology-slot.v1"
CHRONOLOGY_EXECUTION_CONTRACT = "chronology-execution.v1"
AUTHORITY_EXECUTION_CONTRACT = "authority-execution.v1"
ANALYTICAL_REFERENCE_CONTRACT = "analytical-reference.v1"
ANALYTICAL_FINDING_CONTRACT = "analytical-finding.v1"
EVIDENCE_FACT_CONTRACT = "evidence-fact.v1"
EVIDENCE_BINDING_CONTRACT = "evidence-binding.v1"
CLASSIFICATION_BINDING_CONTRACT = "classification-binding.v1"
CONFIDENCE_BINDING_CONTRACT = "confidence-binding.v1"
PERSISTENCE_ASSESSMENT_CONTRACT = "persistence-assessment.v1"
CANONICAL_PACKAGE_CONTRACT = "canonical-authority-package.v1"
SECTION_CONTRACT = "authority-section.v1"
WORKFLOW_CASE_CONTRACT = "workflow-case.v2"
AUTHORITY_AGGREGATE_VERSION_CONTRACT = "analytical-authority"
AUTHORITY_DETERMINATION_VERSION_CONTRACT = "finding-determination"
AUTHORITY_CONFIGURATION_VERSION_CONTRACT = "authority-configuration"
AUTHORITY_EXECUTION_REQUIRED_VERSION_CONTRACTS = (
    AUTHORITY_AGGREGATE_VERSION_CONTRACT,
    AUTHORITY_DETERMINATION_VERSION_CONTRACT,
    AUTHORITY_CONFIGURATION_VERSION_CONTRACT,
)

# The observation namespace is a type/serialization namespace only. Existing
# observation UUID allocation remains authoritative and is never re-derived.
CANONICAL_OBSERVATION_NAMESPACE = _namespace(CANONICAL_OBSERVATION_CONTRACT)
CHRONOLOGY_SLOT_NAMESPACE = _namespace(CHRONOLOGY_SLOT_CONTRACT)
CHRONOLOGY_EXECUTION_NAMESPACE = _namespace(CHRONOLOGY_EXECUTION_CONTRACT)
AUTHORITY_EXECUTION_NAMESPACE = _namespace(AUTHORITY_EXECUTION_CONTRACT)
ANALYTICAL_REFERENCE_NAMESPACE = _namespace(ANALYTICAL_REFERENCE_CONTRACT)
ANALYTICAL_FINDING_NAMESPACE = _namespace(ANALYTICAL_FINDING_CONTRACT)
EVIDENCE_FACT_NAMESPACE = _namespace(EVIDENCE_FACT_CONTRACT)
EVIDENCE_BINDING_NAMESPACE = _namespace(EVIDENCE_BINDING_CONTRACT)
CLASSIFICATION_BINDING_NAMESPACE = _namespace(CLASSIFICATION_BINDING_CONTRACT)
CONFIDENCE_BINDING_NAMESPACE = _namespace(CONFIDENCE_BINDING_CONTRACT)
PERSISTENCE_ASSESSMENT_NAMESPACE = _namespace(PERSISTENCE_ASSESSMENT_CONTRACT)
CANONICAL_PACKAGE_NAMESPACE = _namespace(CANONICAL_PACKAGE_CONTRACT)
SECTION_NAMESPACE = _namespace(SECTION_CONTRACT)
WORKFLOW_CASE_NAMESPACE = _namespace(WORKFLOW_CASE_CONTRACT)


@dataclass(frozen=True, slots=True)
class IdentityComponent:
    """One named, typed UTF-8 component in a declared identity order."""

    name: str
    value_type: str
    value: str

    def __post_init__(self) -> None:
        if not _COMPONENT_NAME_RE.fullmatch(self.name):
            raise ValueError("authority_identity_component_name_invalid")
        if not _COMPONENT_TYPE_RE.fullmatch(self.value_type):
            raise ValueError("authority_identity_component_type_invalid")
        if not isinstance(self.value, str):
            raise TypeError("authority_identity_component_value_required")

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "type": self.value_type,
            "value": self.value,
        }


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return str(len(encoded)).encode("ascii") + b":" + encoded


def canonical_identity_bytes(
    components: Sequence[IdentityComponent],
) -> bytes:
    """Serialize declared-order components without delimiter ambiguity."""

    if isinstance(components, (str, bytes)):
        raise TypeError("authority_identity_components_required")
    frozen = tuple(components)
    if any(not isinstance(component, IdentityComponent) for component in frozen):
        raise TypeError("authority_identity_component_required")
    names = tuple(component.name for component in frozen)
    if len(names) != len(set(names)):
        raise ValueError("authority_identity_component_names_not_unique")
    output = bytearray()
    output.extend(_frame(IDENTITY_CANONICALIZATION_VERSION))
    output.extend(_frame(str(len(frozen))))
    for component in frozen:
        output.extend(_frame(component.name))
        output.extend(_frame(component.value_type))
        output.extend(_frame(component.value))
    return bytes(output)


def _required_text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(code)
    return value


def _uuid(value: UUID | str, code: str) -> UUID:
    try:
        parsed = value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError(code) from error
    if str(parsed) != str(value).lower():
        raise ValueError(code)
    return parsed


def _text_component(name: str, value: str) -> IdentityComponent:
    return IdentityComponent(name, "text", _required_text(value, f"{name}_invalid"))


def _uuid_component(name: str, value: UUID | str) -> IdentityComponent:
    return IdentityComponent(name, "uuid", str(_uuid(value, f"{name}_invalid")))


def _integer_component(name: str, value: int, *, minimum: int = 0) -> IdentityComponent:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name}_invalid")
    return IdentityComponent(name, "integer", str(value))


def _timestamp_component(name: str, value: datetime) -> IdentityComponent:
    return IdentityComponent(name, "utc_datetime", canonical_utc_timestamp(value))


def _null_component(name: str) -> IdentityComponent:
    return IdentityComponent(name, "null", "")


def _digest_components(name: str, value: TypedDigest) -> tuple[IdentityComponent, ...]:
    if not isinstance(value, TypedDigest):
        raise TypeError(f"{name}_typed_digest_required")
    return (
        IdentityComponent(f"{name}.algorithm", "digest_algorithm", value.algorithm),
        IdentityComponent(f"{name}.contract", "digest_contract", value.contract),
        IdentityComponent(f"{name}.value", "digest_value", value.value),
    )


def _optional_digest_components(
    name: str, value: TypedDigest | None
) -> tuple[IdentityComponent, ...]:
    if value is None:
        return (_null_component(name),)
    return _digest_components(name, value)


def _version_components(name: str, value: ContractVersion) -> tuple[IdentityComponent, ...]:
    if not isinstance(value, ContractVersion):
        raise TypeError(f"{name}_contract_version_required")
    return (
        IdentityComponent(f"{name}.contract", "contract", value.contract),
        IdentityComponent(f"{name}.version", "version", value.version),
    )


def _version_bundle_components(bundle: VersionBundle) -> tuple[IdentityComponent, ...]:
    if not isinstance(bundle, VersionBundle):
        raise TypeError("authority_identity_version_bundle_required")
    output = [_integer_component("versions.count", len(bundle.versions))]
    for index, version in enumerate(bundle.versions):
        output.extend(_version_components(f"versions.{index}", version))
    return tuple(output)


def _scope_components(scope: AuthorityScope) -> tuple[IdentityComponent, ...]:
    if not isinstance(scope, AuthorityScope):
        raise TypeError("authority_identity_scope_required")
    level = getattr(scope.level, "value", scope.level)
    output: list[IdentityComponent] = [
        _text_component("scope.contract", "authority-scope.v1"),
        _text_component("scope.level", str(level)),
    ]
    field_names = (
        "tenant_id",
        "workspace_id",
        "resource_scope_id",
        "facility_id",
        "connection_id",
        "system_id",
        "asset_id",
        "native_result_id",
        "authority_execution_id",
        "finding_id",
    )
    level_index = tuple(item.value for item in ScopeLevel).index(str(level))
    for name in field_names[: level_index + 1]:
        value = getattr(scope, name)
        if value is None:
            output.append(_null_component(f"scope.{name}"))
        elif name in {"native_result_id", "authority_execution_id", "finding_id"}:
            output.append(_uuid_component(f"scope.{name}", value))
        else:
            output.append(_text_component(f"scope.{name}", value))
    return tuple(output)


def _scope_level(scope: AuthorityScope) -> str:
    return str(getattr(scope.level, "value", scope.level))


def _require_scope_level(scope: AuthorityScope, allowed: frozenset[str]) -> None:
    level = _scope_level(scope)
    if level not in allowed:
        raise ValueError("authority_identity_scope_level_invalid")


class TypedIdentity(Protocol):
    value: UUID

    @property
    def canonical_bytes(self) -> bytes: ...

    def as_dict(self) -> dict[str, Any]: ...


class _IdentityMethods:
    CONTRACT: ClassVar[str]
    NAMESPACE: ClassVar[UUID]
    value: UUID

    def _components(self) -> tuple[IdentityComponent, ...]:
        raise NotImplementedError

    @property
    def canonical_components(self) -> tuple[IdentityComponent, ...]:
        return self._components()

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_identity_bytes(self.canonical_components)

    @property
    def canonical_hex(self) -> str:
        return self.canonical_bytes.hex()

    def _derived_value(self) -> UUID:
        # UUIDv5 accepts text, so the frozen lowercase hex of the exact equality
        # bytes is its name. This avoids any locale or decoding ambiguity.
        return uuid5(self.NAMESPACE, self.canonical_hex)

    def _identity_dict(self, *, derived: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "contract": self.CONTRACT,
            "id": str(self.value),
            "canonicalization": IDENTITY_CANONICALIZATION_VERSION,
            "canonical_components": [
                component.as_dict() for component in self.canonical_components
            ],
            "canonical_hex": self.canonical_hex,
        }
        if derived:
            result["namespace"] = str(self.NAMESPACE)
        return result

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class CanonicalObservationIdentity(_IdentityMethods):
    """Typed wrapper over an existing admitted observation UUID."""

    scope: AuthorityScope
    value: UUID | str

    CONTRACT: ClassVar[str] = CANONICAL_OBSERVATION_CONTRACT
    NAMESPACE: ClassVar[UUID] = CANONICAL_OBSERVATION_NAMESPACE

    def __post_init__(self) -> None:
        _require_scope_level(self.scope, frozenset({"asset"}))
        object.__setattr__(
            self,
            "value",
            _uuid(self.value, "canonical_observation_identity_invalid"),
        )

    def _components(self) -> tuple[IdentityComponent, ...]:
        return _scope_components(self.scope) + (
            _uuid_component("existing_observation_id", self.value),
        )

    def as_dict(self) -> dict[str, Any]:
        result = self._identity_dict(derived=False)
        result["allocation"] = "existing_supplied_uuid"
        return result


@dataclass(frozen=True, slots=True)
class AnalyticalReferenceIdentity(_IdentityMethods):
    scope: AuthorityScope
    producer_family: str
    model_id: str
    model_version: str
    learning_generation: int
    configuration_generation: int
    snapshot_id: str
    snapshot_digest: TypedDigest
    causal_frontier_digest: TypedDigest
    chronology_binding_digest: TypedDigest
    method_identity: ContractVersion
    configuration_identity: TypedDigest
    integrity_identity: TypedDigest
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = ANALYTICAL_REFERENCE_CONTRACT
    NAMESPACE: ClassVar[UUID] = ANALYTICAL_REFERENCE_NAMESPACE

    def __post_init__(self) -> None:
        _require_scope_level(self.scope, frozenset({"asset"}))
        for name in ("producer_family", "model_id", "model_version", "snapshot_id"):
            _required_text(getattr(self, name), f"analytical_reference_{name}_invalid")
        if self.learning_generation < 1 or self.configuration_generation < 1:
            raise ValueError("analytical_reference_generation_invalid")
        # Validate typed objects before deriving.
        _digest_components("snapshot_digest", self.snapshot_digest)
        _digest_components("causal_frontier_digest", self.causal_frontier_digest)
        _digest_components("chronology_binding_digest", self.chronology_binding_digest)
        _version_components("method_identity", self.method_identity)
        _digest_components("configuration_identity", self.configuration_identity)
        _digest_components("integrity_identity", self.integrity_identity)
        object.__setattr__(self, "value", self._derived_value())

    def _components(self) -> tuple[IdentityComponent, ...]:
        return (
            _scope_components(self.scope)
            + (
                _text_component("producer_family", self.producer_family),
                _text_component("model_id", self.model_id),
                _text_component("model_version", self.model_version),
                _integer_component("learning_generation", self.learning_generation, minimum=1),
                _integer_component(
                    "configuration_generation", self.configuration_generation, minimum=1
                ),
                _text_component("snapshot_id", self.snapshot_id),
            )
            + _digest_components("snapshot_digest", self.snapshot_digest)
            + _digest_components("causal_frontier_digest", self.causal_frontier_digest)
            + _digest_components("chronology_binding_digest", self.chronology_binding_digest)
            + _version_components("method_identity", self.method_identity)
            + _digest_components("configuration_identity", self.configuration_identity)
            + _digest_components("integrity_identity", self.integrity_identity)
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class ChronologySlotIdentity(_IdentityMethods):
    scope: AuthorityScope
    authority_digest: TypedDigest
    analysis_config_digest: TypedDigest
    cadence_origin: datetime
    evaluation_endpoint: datetime
    contribution_start: datetime
    contribution_end: datetime
    lookback_start: datetime
    lookback_end: datetime
    learning_generation: int
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = CHRONOLOGY_SLOT_CONTRACT
    NAMESPACE: ClassVar[UUID] = CHRONOLOGY_SLOT_NAMESPACE

    def __post_init__(self) -> None:
        _require_scope_level(self.scope, frozenset({"asset"}))
        timestamps = (
            self.cadence_origin,
            self.evaluation_endpoint,
            self.contribution_start,
            self.contribution_end,
            self.lookback_start,
            self.lookback_end,
        )
        for timestamp in timestamps:
            canonical_utc_timestamp(timestamp)
        if self.contribution_start >= self.contribution_end:
            raise ValueError("chronology_slot_contribution_range_invalid")
        if self.lookback_start >= self.lookback_end:
            raise ValueError("chronology_slot_lookback_range_invalid")
        if self.contribution_end != self.evaluation_endpoint:
            raise ValueError("chronology_slot_contribution_endpoint_mismatch")
        if self.lookback_end != self.evaluation_endpoint:
            raise ValueError("chronology_slot_lookback_endpoint_mismatch")
        _integer_component("learning_generation", self.learning_generation, minimum=1)
        _digest_components("authority_digest", self.authority_digest)
        _digest_components("analysis_config_digest", self.analysis_config_digest)
        object.__setattr__(self, "value", self._derived_value())

    def _components(self) -> tuple[IdentityComponent, ...]:
        return (
            _scope_components(self.scope)
            + _digest_components("authority_digest", self.authority_digest)
            + _digest_components("analysis_config_digest", self.analysis_config_digest)
            + (
                _timestamp_component("cadence_origin", self.cadence_origin),
                _timestamp_component("evaluation_endpoint", self.evaluation_endpoint),
                _timestamp_component("contribution_start", self.contribution_start),
                _timestamp_component("contribution_end", self.contribution_end),
                _timestamp_component("lookback_start", self.lookback_start),
                _timestamp_component("lookback_end", self.lookback_end),
                _integer_component("learning_generation", self.learning_generation, minimum=1),
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class ChronologyExecutionIdentity(_IdentityMethods):
    chronology_slot_id: ChronologySlotIdentity
    analysis_generation: int
    execution_mode: str
    manifest_digest: TypedDigest
    analytical_input_digest: TypedDigest
    expected_progress_revision: int
    predecessor_reference_id: AnalyticalReferenceIdentity | None
    predecessor_reference_digest: TypedDigest | None
    authority_digest: TypedDigest
    configuration_digest: TypedDigest
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = CHRONOLOGY_EXECUTION_CONTRACT
    NAMESPACE: ClassVar[UUID] = CHRONOLOGY_EXECUTION_NAMESPACE
    EXECUTION_MODES: ClassVar[frozenset[str]] = frozenset(
        {"active", "evaluation_only", "historical_non_learning", "replay"}
    )

    def __post_init__(self) -> None:
        if not isinstance(self.chronology_slot_id, ChronologySlotIdentity):
            raise TypeError("chronology_execution_slot_identity_required")
        _integer_component("analysis_generation", self.analysis_generation, minimum=1)
        if self.execution_mode not in self.EXECUTION_MODES:
            raise ValueError("chronology_execution_mode_invalid")
        _integer_component("expected_progress_revision", self.expected_progress_revision)
        if (self.predecessor_reference_id is None) != (
            self.predecessor_reference_digest is None
        ):
            raise ValueError("chronology_execution_predecessor_binding_incomplete")
        if self.predecessor_reference_id is not None and not isinstance(
            self.predecessor_reference_id, AnalyticalReferenceIdentity
        ):
            raise TypeError("chronology_execution_predecessor_identity_invalid")
        if (
            self.predecessor_reference_id is not None
            and self.predecessor_reference_id.scope != self.scope
        ):
            raise ValueError("chronology_execution_predecessor_scope_mismatch")
        for name in (
            "manifest_digest",
            "analytical_input_digest",
            "authority_digest",
            "configuration_digest",
        ):
            _digest_components(name, getattr(self, name))
        _optional_digest_components(
            "predecessor_reference_digest", self.predecessor_reference_digest
        )
        object.__setattr__(self, "value", self._derived_value())

    @property
    def scope(self) -> AuthorityScope:
        return self.chronology_slot_id.scope

    def _components(self) -> tuple[IdentityComponent, ...]:
        predecessor = (
            _null_component("predecessor_reference_id")
            if self.predecessor_reference_id is None
            else _uuid_component(
                "predecessor_reference_id", self.predecessor_reference_id.value
            )
        )
        return (
            (
                _uuid_component("chronology_slot_id", self.chronology_slot_id.value),
                _integer_component("analysis_generation", self.analysis_generation, minimum=1),
                _text_component("execution_mode", self.execution_mode),
            )
            + _digest_components("manifest_digest", self.manifest_digest)
            + _digest_components("analytical_input_digest", self.analytical_input_digest)
            + (
                _integer_component(
                    "expected_progress_revision", self.expected_progress_revision
                ),
                predecessor,
            )
            + _optional_digest_components(
                "predecessor_reference_digest", self.predecessor_reference_digest
            )
            + _digest_components("authority_digest", self.authority_digest)
            + _digest_components("configuration_digest", self.configuration_digest)
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class NativeResultIdentity(_IdentityMethods):
    """Scoped P0.1 result wrapper; P0.1 remains the sole ID producer."""

    scope: AuthorityScope
    value: UUID | str

    CONTRACT: ClassVar[str] = ARTIFACT_SCHEMA_VERSION
    # A sentinel required by the mixin but never emitted or used to derive.
    NAMESPACE: ClassVar[UUID] = UUID(int=0)

    def __post_init__(self) -> None:
        _require_scope_level(self.scope, frozenset({"native_result"}))
        value = _uuid(self.value, "native_result_identity_invalid")
        if str(value) != self.scope.native_result_id:
            raise ValueError("native_result_identity_scope_mismatch")
        object.__setattr__(self, "value", value)

    @classmethod
    def from_window(
        cls,
        *,
        scope: AuthorityScope,
        window_id: str,
        execution_contract_version: str,
    ) -> NativeResultIdentity:
        """Call, rather than reproduce, the existing P0.1 identity producer."""

        if not isinstance(scope, AuthorityScope):
            raise TypeError("native_result_scope_required")
        _require_scope_level(scope, frozenset({"asset"}))
        result_id = canonical_result_id(
            window_id=window_id,
            execution_contract_version=execution_contract_version,
        )
        native_scope = AuthorityScope(
            level=ScopeLevel.NATIVE_RESULT,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            resource_scope_id=scope.resource_scope_id,
            facility_id=scope.facility_id,
            connection_id=scope.connection_id,
            system_id=scope.system_id,
            asset_id=scope.asset_id,
            native_result_id=result_id,
            authority_execution_id=None,
            finding_id=None,
        )
        return cls(scope=native_scope, value=result_id)

    def _components(self) -> tuple[IdentityComponent, ...]:
        return _scope_components(self.scope) + (
            _uuid_component("native_result_id", self.value),
        )

    def as_dict(self) -> dict[str, Any]:
        result = self._identity_dict(derived=False)
        result["allocation"] = "existing_p0.1_canonical_result_id"
        return result


@dataclass(frozen=True, slots=True)
class AuthorityExecutionIdentity(_IdentityMethods):
    scope: AuthorityScope
    source_kind: str
    native_terminal_source_id: UUID | str
    native_terminal_digest: TypedDigest
    chronology_execution_id: ChronologyExecutionIdentity
    versions: VersionBundle
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = AUTHORITY_EXECUTION_CONTRACT
    NAMESPACE: ClassVar[UUID] = AUTHORITY_EXECUTION_NAMESPACE

    def __post_init__(self) -> None:
        _require_scope_level(self.scope, frozenset({"asset"}))
        _required_text(self.source_kind, "authority_execution_source_kind_invalid")
        object.__setattr__(
            self,
            "native_terminal_source_id",
            _uuid(
                self.native_terminal_source_id,
                "authority_execution_native_terminal_source_id_invalid",
            ),
        )
        if not isinstance(self.chronology_execution_id, ChronologyExecutionIdentity):
            raise TypeError("authority_execution_chronology_identity_required")
        if self.scope != self.chronology_execution_id.scope:
            raise ValueError("authority_execution_chronology_scope_mismatch")
        _digest_components("native_terminal_digest", self.native_terminal_digest)
        _version_bundle_components(self.versions)
        for contract in AUTHORITY_EXECUTION_REQUIRED_VERSION_CONTRACTS:
            self.versions.require(contract)
        object.__setattr__(self, "value", self._derived_value())

    def _components(self) -> tuple[IdentityComponent, ...]:
        return (
            _scope_components(self.scope)
            + (
                _text_component("source_kind", self.source_kind),
                _uuid_component(
                    "native_terminal_source_id", self.native_terminal_source_id
                ),
            )
            + _digest_components("native_terminal_digest", self.native_terminal_digest)
            + (
                _uuid_component(
                    "chronology_execution_id", self.chronology_execution_id.value
                ),
            )
            + _version_bundle_components(self.versions)
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class AnalyticalFindingIdentity(_IdentityMethods):
    authority_execution_id: AuthorityExecutionIdentity
    determination_contract: ContractVersion
    finding_type: str
    affected_scope: AuthorityScope
    subject_identity: str
    relationship_metric_identities: tuple[str, ...]
    analytical_reference_id: AnalyticalReferenceIdentity
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = ANALYTICAL_FINDING_CONTRACT
    NAMESPACE: ClassVar[UUID] = ANALYTICAL_FINDING_NAMESPACE

    def __post_init__(self) -> None:
        if not isinstance(self.authority_execution_id, AuthorityExecutionIdentity):
            raise TypeError("analytical_finding_authority_identity_required")
        if not isinstance(self.analytical_reference_id, AnalyticalReferenceIdentity):
            raise TypeError("analytical_finding_reference_identity_required")
        if self.authority_execution_id.scope != self.affected_scope:
            raise ValueError("analytical_finding_scope_mismatch")
        if self.analytical_reference_id.scope != self.affected_scope:
            raise ValueError("analytical_finding_reference_scope_mismatch")
        _required_text(self.finding_type, "analytical_finding_type_invalid")
        _required_text(self.subject_identity, "analytical_finding_subject_invalid")
        _version_components("determination_contract", self.determination_contract)
        frozen = tuple(self.relationship_metric_identities)
        if not frozen or len(frozen) != len(set(frozen)):
            raise ValueError("analytical_finding_relationship_metric_set_invalid")
        for item in frozen:
            _required_text(item, "analytical_finding_relationship_metric_invalid")
        object.__setattr__(self, "relationship_metric_identities", frozen)
        object.__setattr__(self, "value", self._derived_value())

    @property
    def scope(self) -> AuthorityScope:
        return self.affected_scope

    def _components(self) -> tuple[IdentityComponent, ...]:
        relationships = [
            _integer_component(
                "relationship_metric_identities.count",
                len(self.relationship_metric_identities),
            )
        ]
        for index, item in enumerate(self.relationship_metric_identities):
            relationships.append(
                _text_component(f"relationship_metric_identities.{index}", item)
            )
        return (
            (
                _uuid_component(
                    "authority_execution_id", self.authority_execution_id.value
                ),
            )
            + _version_components("determination_contract", self.determination_contract)
            + (
                _text_component("finding_type", self.finding_type),
            )
            + _scope_components(self.affected_scope)
            + (
                _text_component("subject_identity", self.subject_identity),
                *relationships,
                _uuid_component(
                    "analytical_reference_id", self.analytical_reference_id.value
                ),
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class EvidenceFactIdentity(_IdentityMethods):
    authority_execution_id: AuthorityExecutionIdentity
    fact_type: str
    producer_schema: ContractVersion
    subject_scope: AuthorityScope
    subject_identity: str
    dimensions: tuple[tuple[str, str], ...]
    value_unit_event_time_digest: TypedDigest
    analytical_reference_id: AnalyticalReferenceIdentity | None = None
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = EVIDENCE_FACT_CONTRACT
    NAMESPACE: ClassVar[UUID] = EVIDENCE_FACT_NAMESPACE

    def __post_init__(self) -> None:
        if not isinstance(self.authority_execution_id, AuthorityExecutionIdentity):
            raise TypeError("evidence_fact_authority_identity_required")
        if self.subject_scope != self.authority_execution_id.scope:
            raise ValueError("evidence_fact_scope_mismatch")
        _required_text(self.fact_type, "evidence_fact_type_invalid")
        _required_text(self.subject_identity, "evidence_fact_subject_invalid")
        _version_components("producer_schema", self.producer_schema)
        dimensions = tuple(sorted(tuple(item) for item in self.dimensions))
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("evidence_fact_dimensions_not_unique")
        for item in dimensions:
            if len(item) != 2:
                raise ValueError("evidence_fact_dimension_invalid")
            _required_text(item[0], "evidence_fact_dimension_name_invalid")
            _required_text(item[1], "evidence_fact_dimension_value_invalid")
        object.__setattr__(self, "dimensions", dimensions)
        _digest_components(
            "value_unit_event_time_digest", self.value_unit_event_time_digest
        )
        if self.analytical_reference_id is not None:
            if not isinstance(self.analytical_reference_id, AnalyticalReferenceIdentity):
                raise TypeError("evidence_fact_reference_identity_invalid")
            if self.analytical_reference_id.scope != self.subject_scope:
                raise ValueError("evidence_fact_reference_scope_mismatch")
        object.__setattr__(self, "value", self._derived_value())

    @property
    def scope(self) -> AuthorityScope:
        return self.subject_scope

    def _components(self) -> tuple[IdentityComponent, ...]:
        dimensions = [_integer_component("dimensions.count", len(self.dimensions))]
        for index, (name, value) in enumerate(self.dimensions):
            dimensions.extend(
                (
                    _text_component(f"dimensions.{index}.name", name),
                    _text_component(f"dimensions.{index}.value", value),
                )
            )
        reference = (
            _null_component("analytical_reference_id")
            if self.analytical_reference_id is None
            else _uuid_component(
                "analytical_reference_id", self.analytical_reference_id.value
            )
        )
        return (
            (
                _uuid_component(
                    "authority_execution_id", self.authority_execution_id.value
                ),
                _text_component("fact_type", self.fact_type),
            )
            + _version_components("producer_schema", self.producer_schema)
            + _scope_components(self.subject_scope)
            + (
                _text_component("subject_identity", self.subject_identity),
                *dimensions,
            )
            + _digest_components(
                "value_unit_event_time_digest", self.value_unit_event_time_digest
            )
            + (reference,)
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class EvidenceBindingIdentity(_IdentityMethods):
    authority_execution_id: AuthorityExecutionIdentity
    analytical_finding_id: AnalyticalFindingIdentity
    evidence_fact_id: EvidenceFactIdentity
    role: str
    qualification: str
    qualification_contract: ContractVersion
    limitation_set_digest: TypedDigest
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = EVIDENCE_BINDING_CONTRACT
    NAMESPACE: ClassVar[UUID] = EVIDENCE_BINDING_NAMESPACE

    def __post_init__(self) -> None:
        if self.analytical_finding_id.authority_execution_id != self.authority_execution_id:
            raise ValueError("evidence_binding_finding_execution_mismatch")
        if self.evidence_fact_id.authority_execution_id != self.authority_execution_id:
            raise ValueError("evidence_binding_fact_execution_mismatch")
        if self.analytical_finding_id.scope != self.evidence_fact_id.scope:
            raise ValueError("evidence_binding_scope_mismatch")
        _required_text(self.role, "evidence_binding_role_invalid")
        _required_text(self.qualification, "evidence_binding_qualification_invalid")
        _version_components("qualification_contract", self.qualification_contract)
        _digest_components("limitation_set_digest", self.limitation_set_digest)
        object.__setattr__(self, "value", self._derived_value())

    def _components(self) -> tuple[IdentityComponent, ...]:
        return (
            (
                _uuid_component(
                    "authority_execution_id", self.authority_execution_id.value
                ),
                _uuid_component(
                    "analytical_finding_id", self.analytical_finding_id.value
                ),
                _uuid_component("evidence_fact_id", self.evidence_fact_id.value),
                _text_component("role", self.role),
                _text_component("qualification", self.qualification),
            )
            + _version_components("qualification_contract", self.qualification_contract)
            + _digest_components("limitation_set_digest", self.limitation_set_digest)
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class ClassificationBindingIdentity(_IdentityMethods):
    analytical_finding_id: AnalyticalFindingIdentity
    classifier_rule: ContractVersion
    input_contract: ContractVersion
    ordered_binding_set_digest: TypedDigest
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = CLASSIFICATION_BINDING_CONTRACT
    NAMESPACE: ClassVar[UUID] = CLASSIFICATION_BINDING_NAMESPACE

    def __post_init__(self) -> None:
        if not isinstance(self.analytical_finding_id, AnalyticalFindingIdentity):
            raise TypeError("classification_binding_finding_identity_required")
        _version_components("classifier_rule", self.classifier_rule)
        _version_components("input_contract", self.input_contract)
        _digest_components(
            "ordered_binding_set_digest", self.ordered_binding_set_digest
        )
        object.__setattr__(self, "value", self._derived_value())

    def _components(self) -> tuple[IdentityComponent, ...]:
        return (
            (_uuid_component("analytical_finding_id", self.analytical_finding_id.value),)
            + _version_components("classifier_rule", self.classifier_rule)
            + _version_components("input_contract", self.input_contract)
            + _digest_components(
                "ordered_binding_set_digest", self.ordered_binding_set_digest
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class PersistenceAssessmentIdentity(_IdentityMethods):
    analytical_finding_id: AnalyticalFindingIdentity
    method: ContractVersion
    chronology_execution_id: ChronologyExecutionIdentity
    event_time_window_digest: TypedDigest
    exact_fact_set_digest: TypedDigest
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = PERSISTENCE_ASSESSMENT_CONTRACT
    NAMESPACE: ClassVar[UUID] = PERSISTENCE_ASSESSMENT_NAMESPACE

    def __post_init__(self) -> None:
        if self.analytical_finding_id.authority_execution_id.chronology_execution_id != self.chronology_execution_id:
            raise ValueError("persistence_assessment_chronology_mismatch")
        _version_components("method", self.method)
        _digest_components("event_time_window_digest", self.event_time_window_digest)
        _digest_components("exact_fact_set_digest", self.exact_fact_set_digest)
        object.__setattr__(self, "value", self._derived_value())

    def _components(self) -> tuple[IdentityComponent, ...]:
        return (
            (
                _uuid_component(
                    "analytical_finding_id", self.analytical_finding_id.value
                ),
            )
            + _version_components("method", self.method)
            + (
                _uuid_component(
                    "chronology_execution_id", self.chronology_execution_id.value
                ),
            )
            + _digest_components("event_time_window_digest", self.event_time_window_digest)
            + _digest_components("exact_fact_set_digest", self.exact_fact_set_digest)
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class ConfidenceBindingIdentity(_IdentityMethods):
    analytical_finding_id: AnalyticalFindingIdentity
    confidence_contract: ContractVersion
    exact_input_set_digest: TypedDigest
    persistence_assessment_id: PersistenceAssessmentIdentity
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = CONFIDENCE_BINDING_CONTRACT
    NAMESPACE: ClassVar[UUID] = CONFIDENCE_BINDING_NAMESPACE

    def __post_init__(self) -> None:
        if self.persistence_assessment_id.analytical_finding_id != self.analytical_finding_id:
            raise ValueError("confidence_binding_persistence_finding_mismatch")
        _version_components("confidence_contract", self.confidence_contract)
        _digest_components("exact_input_set_digest", self.exact_input_set_digest)
        object.__setattr__(self, "value", self._derived_value())

    def _components(self) -> tuple[IdentityComponent, ...]:
        return (
            (_uuid_component("analytical_finding_id", self.analytical_finding_id.value),)
            + _version_components("confidence_contract", self.confidence_contract)
            + _digest_components("exact_input_set_digest", self.exact_input_set_digest)
            + (
                _uuid_component(
                    "persistence_assessment_id", self.persistence_assessment_id.value
                ),
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class CanonicalPackageIdentity(_IdentityMethods):
    authority_execution_id: AuthorityExecutionIdentity
    package_schema: ContractVersion
    generation: int = 1
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = CANONICAL_PACKAGE_CONTRACT
    NAMESPACE: ClassVar[UUID] = CANONICAL_PACKAGE_NAMESPACE

    def __post_init__(self) -> None:
        if not isinstance(self.authority_execution_id, AuthorityExecutionIdentity):
            raise TypeError("canonical_package_authority_identity_required")
        _version_components("package_schema", self.package_schema)
        if self.generation != 1:
            raise ValueError("canonical_package_generation_must_equal_one")
        object.__setattr__(self, "value", self._derived_value())

    def _components(self) -> tuple[IdentityComponent, ...]:
        return (
            (_uuid_component("authority_execution_id", self.authority_execution_id.value),)
            + _version_components("package_schema", self.package_schema)
            + (_integer_component("generation", self.generation, minimum=1),)
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class SectionIdentity(_IdentityMethods):
    package_id: CanonicalPackageIdentity
    section_family: str
    section_schema: ContractVersion
    sequence_number: int
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = SECTION_CONTRACT
    NAMESPACE: ClassVar[UUID] = SECTION_NAMESPACE

    def __post_init__(self) -> None:
        if not isinstance(self.package_id, CanonicalPackageIdentity):
            raise TypeError("authority_section_package_identity_required")
        _required_text(self.section_family, "authority_section_family_invalid")
        _version_components("section_schema", self.section_schema)
        _integer_component("sequence_number", self.sequence_number)
        object.__setattr__(self, "value", self._derived_value())

    def _components(self) -> tuple[IdentityComponent, ...]:
        return (
            (
                _uuid_component("package_id", self.package_id.value),
                _text_component("section_family", self.section_family),
            )
            + _version_components("section_schema", self.section_schema)
            + (_integer_component("sequence_number", self.sequence_number),)
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


@dataclass(frozen=True, slots=True)
class WorkflowCaseIdentity(_IdentityMethods):
    scope: AuthorityScope
    authority_execution_id: AuthorityExecutionIdentity
    analytical_finding_id: AnalyticalFindingIdentity
    workflow_contract: ContractVersion
    value: UUID = field(init=False)

    CONTRACT: ClassVar[str] = WORKFLOW_CASE_CONTRACT
    NAMESPACE: ClassVar[UUID] = WORKFLOW_CASE_NAMESPACE

    def __post_init__(self) -> None:
        _require_scope_level(self.scope, frozenset({"finding"}))
        if self.analytical_finding_id.authority_execution_id != self.authority_execution_id:
            raise ValueError("workflow_case_finding_execution_mismatch")
        base_fields = (
            "tenant_id",
            "workspace_id",
            "resource_scope_id",
            "facility_id",
            "connection_id",
            "system_id",
            "asset_id",
        )
        if any(
            getattr(self.scope, name) != getattr(self.authority_execution_id.scope, name)
            for name in base_fields
        ):
            raise ValueError("workflow_case_scope_base_mismatch")
        if str(self.scope.authority_execution_id) != str(self.authority_execution_id.value):
            raise ValueError("workflow_case_scope_authority_mismatch")
        if str(self.scope.finding_id) != str(self.analytical_finding_id.value):
            raise ValueError("workflow_case_scope_finding_mismatch")
        _version_components("workflow_contract", self.workflow_contract)
        object.__setattr__(self, "value", self._derived_value())

    def _components(self) -> tuple[IdentityComponent, ...]:
        return (
            _scope_components(self.scope)
            + (
                _uuid_component(
                    "authority_execution_id", self.authority_execution_id.value
                ),
                _uuid_component(
                    "analytical_finding_id", self.analytical_finding_id.value
                ),
            )
            + _version_components("workflow_contract", self.workflow_contract)
        )

    def as_dict(self) -> dict[str, Any]:
        return self._identity_dict()


def deterministic_identity_set_digest(
    identities: Iterable[TypedIdentity | UUID | str],
    *,
    ordered: bool,
    contract: str,
) -> TypedDigest:
    """Digest an exact identity set, sorting UUIDs only for unordered sets."""

    contract = _required_text(contract, "identity_set_digest_contract_invalid")
    values: list[UUID] = []
    for identity in identities:
        candidate = getattr(identity, "value", identity)
        values.append(_uuid(candidate, "identity_set_member_invalid"))
    if len(values) != len(set(values)):
        raise ValueError("identity_set_members_not_unique")
    if not ordered:
        values.sort(key=lambda item: item.bytes)
    components: list[IdentityComponent] = [
        _text_component("set.contract", contract),
        IdentityComponent("set.order", "set_order", "ordered" if ordered else "unordered"),
        _integer_component("set.count", len(values)),
    ]
    components.extend(
        _uuid_component(f"set.member.{index}", value)
        for index, value in enumerate(values)
    )
    digest = hashlib.sha256(canonical_identity_bytes(tuple(components))).hexdigest()
    return TypedDigest(
        algorithm="sha256",
        contract=f"{contract}.{IDENTITY_CANONICALIZATION_VERSION}",
        value=digest,
    )


def ordered_identity_set_digest(
    identities: Iterable[TypedIdentity | UUID | str], *, contract: str
) -> TypedDigest:
    return deterministic_identity_set_digest(
        identities, ordered=True, contract=contract
    )


def unordered_identity_set_digest(
    identities: Iterable[TypedIdentity | UUID | str], *, contract: str
) -> TypedDigest:
    return deterministic_identity_set_digest(
        identities, ordered=False, contract=contract
    )


__all__ = [
    "ANALYTICAL_FINDING_CONTRACT",
    "ANALYTICAL_FINDING_NAMESPACE",
    "ANALYTICAL_REFERENCE_CONTRACT",
    "ANALYTICAL_REFERENCE_NAMESPACE",
    "AUTHORITY_EXECUTION_CONTRACT",
    "AUTHORITY_EXECUTION_NAMESPACE",
    "AUTHORITY_EXECUTION_REQUIRED_VERSION_CONTRACTS",
    "AnalyticalFindingIdentity",
    "AnalyticalReferenceIdentity",
    "AuthorityExecutionIdentity",
    "CANONICAL_OBSERVATION_CONTRACT",
    "CANONICAL_OBSERVATION_NAMESPACE",
    "CANONICAL_PACKAGE_CONTRACT",
    "CANONICAL_PACKAGE_NAMESPACE",
    "CHRONOLOGY_EXECUTION_CONTRACT",
    "CHRONOLOGY_EXECUTION_NAMESPACE",
    "CHRONOLOGY_SLOT_CONTRACT",
    "CHRONOLOGY_SLOT_NAMESPACE",
    "CLASSIFICATION_BINDING_CONTRACT",
    "CLASSIFICATION_BINDING_NAMESPACE",
    "CONFIDENCE_BINDING_CONTRACT",
    "CONFIDENCE_BINDING_NAMESPACE",
    "CanonicalObservationIdentity",
    "CanonicalPackageIdentity",
    "ChronologyExecutionIdentity",
    "ChronologySlotIdentity",
    "ClassificationBindingIdentity",
    "ConfidenceBindingIdentity",
    "EVIDENCE_BINDING_CONTRACT",
    "EVIDENCE_BINDING_NAMESPACE",
    "EVIDENCE_FACT_CONTRACT",
    "EVIDENCE_FACT_NAMESPACE",
    "EvidenceBindingIdentity",
    "EvidenceFactIdentity",
    "IDENTITY_CANONICALIZATION_VERSION",
    "IdentityComponent",
    "NativeResultIdentity",
    "PERSISTENCE_ASSESSMENT_CONTRACT",
    "PERSISTENCE_ASSESSMENT_NAMESPACE",
    "PersistenceAssessmentIdentity",
    "SECTION_CONTRACT",
    "SECTION_NAMESPACE",
    "SectionIdentity",
    "TypedIdentity",
    "WORKFLOW_CASE_CONTRACT",
    "WORKFLOW_CASE_NAMESPACE",
    "WorkflowCaseIdentity",
    "canonical_identity_bytes",
    "deterministic_identity_set_digest",
    "ordered_identity_set_digest",
    "unordered_identity_set_digest",
]
