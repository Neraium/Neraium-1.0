"""Pure shared values for the reconciled analytical authority contracts.

This module intentionally contains no persistence, scheduling, analytical, or
publication behavior.  It gives later P0.2, P0.3, and P1.2 implementations a
single fail-closed vocabulary for canonical values, exact scope, integrity,
completeness, and governance inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Mapping, NoReturn
from uuid import UUID


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_WILDCARD_VALUES = frozenset({"*", "all", "any", "global", "wildcard"})


class ContractValidationError(ValueError):
    """Raised when an authority contract cannot be validated exactly."""


def _fail(code: str) -> NoReturn:
    raise ContractValidationError(code)


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        _fail(f"{field_name}_must_be_text")
    if not value:
        _fail(f"{field_name}_required")
    if value != value.strip():
        _fail(f"{field_name}_must_be_canonical_text")
    return value


def _canonical_value(value: Any) -> Any:
    """Return a JSON-compatible value without lossy string coercion."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("canonical_json_non_finite_number")
        return value
    if isinstance(value, datetime):
        return canonical_utc_timestamp(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("canonical_json_mapping_key_must_be_text")
            if key in normalized:
                _fail("canonical_json_duplicate_mapping_key")
            normalized[key] = _canonical_value(item)
        return normalized
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return _canonical_value(as_dict())
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _canonical_value(getattr(value, item.name))
            for item in fields(value)
        }
    _fail(f"canonical_json_type_unsupported:{type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a supported value to deterministic canonical UTF-8 JSON."""

    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_text(value: Any) -> str:
    """Return :func:`canonical_json_bytes` decoded as UTF-8 text."""

    return canonical_json_bytes(value).decode("utf-8")


def canonical_utc_timestamp(value: datetime) -> str:
    """Encode an aware timestamp as UTC ISO-8601 with fixed microseconds."""

    if not isinstance(value, datetime):
        _fail("timestamp_must_be_datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        _fail("timestamp_must_be_timezone_aware")
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class TypedDigest:
    """A SHA-256 digest whose contract prevents cross-domain comparison."""

    algorithm: str
    contract: str
    value: str

    def __post_init__(self) -> None:
        algorithm = _required_text(self.algorithm, "digest_algorithm").lower()
        contract = _required_text(self.contract, "digest_contract")
        value = _required_text(self.value, "digest_value").lower()
        if algorithm != "sha256":
            _fail("digest_algorithm_unsupported")
        if not _SHA256_PATTERN.fullmatch(value):
            _fail("digest_value_invalid")
        object.__setattr__(self, "algorithm", algorithm)
        object.__setattr__(self, "contract", contract)
        object.__setattr__(self, "value", value)

    @classmethod
    def from_value(cls, contract: str, value: Any) -> TypedDigest:
        """Hash canonical JSON, or exact bytes when bytes are supplied."""

        payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
        return cls(
            algorithm="sha256",
            contract=contract,
            value=hashlib.sha256(payload).hexdigest(),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "algorithm": self.algorithm,
            "contract": self.contract,
            "value": self.value,
        }

    def identity_components(self) -> tuple[str, str, str]:
        return (self.algorithm, self.contract, self.value)


@dataclass(frozen=True, slots=True, order=True)
class ContractVersion:
    """A version qualified by the contract that owns its semantics."""

    contract: str
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract", _required_text(self.contract, "contract"))
        object.__setattr__(self, "version", _required_text(self.version, "version"))

    def as_dict(self) -> dict[str, str]:
        return {"contract": self.contract, "version": self.version}

    def identity_components(self) -> tuple[str, str]:
        return (self.contract, self.version)


@dataclass(frozen=True, slots=True)
class VersionBundle:
    """A deterministic, contract-unique collection of contract versions."""

    versions: tuple[ContractVersion, ...]

    def __post_init__(self) -> None:
        versions = tuple(
            item
            if isinstance(item, ContractVersion)
            else _invalid_contract_version(item)
            for item in self.versions
        )
        if not versions:
            _fail("version_bundle_empty")
        by_contract: dict[str, ContractVersion] = {}
        for item in versions:
            if item.contract in by_contract:
                _fail(f"version_bundle_duplicate_contract:{item.contract}")
            by_contract[item.contract] = item
        object.__setattr__(self, "versions", tuple(sorted(versions)))

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": "authority-version-bundle.v1",
            "versions": tuple(item.as_dict() for item in self.versions),
        }

    @property
    def digest(self) -> TypedDigest:
        return TypedDigest.from_value("authority-version-bundle.v1", self.as_dict())

    def require(self, contract: str, version: str | None = None) -> ContractVersion:
        contract = _required_text(contract, "required_contract")
        for item in self.versions:
            if item.contract != contract:
                continue
            if version is not None and item.version != version:
                _fail(f"version_bundle_required_version_mismatch:{contract}")
            return item
        _fail(f"version_bundle_required_contract_missing:{contract}")

    def validate_required(
        self, required: tuple[ContractVersion, ...]
    ) -> VersionBundle:
        for item in required:
            if not isinstance(item, ContractVersion):
                _fail("required_version_must_be_contract_version")
            self.require(item.contract, item.version)
        return self

    def identity_components(self) -> tuple[str, ...]:
        return tuple(
            component
            for item in self.versions
            for component in item.identity_components()
        )


def _invalid_contract_version(value: object) -> NoReturn:
    _fail(f"version_bundle_member_invalid:{type(value).__name__}")


class ScopeLevel(str, Enum):
    TENANT = "tenant"
    WORKSPACE = "workspace"
    RESOURCE = "resource"
    FACILITY = "facility"
    CONNECTION = "connection"
    SYSTEM = "system"
    ASSET = "asset"
    NATIVE_RESULT = "native_result"
    AUTHORITY_EXECUTION = "authority_execution"
    FINDING = "finding"


_SCOPE_FIELDS = (
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
_SCOPE_LEVEL_INDEX = {
    ScopeLevel.TENANT: 0,
    ScopeLevel.WORKSPACE: 1,
    ScopeLevel.RESOURCE: 2,
    ScopeLevel.FACILITY: 3,
    ScopeLevel.CONNECTION: 4,
    ScopeLevel.SYSTEM: 5,
    ScopeLevel.ASSET: 6,
    ScopeLevel.NATIVE_RESULT: 7,
    ScopeLevel.AUTHORITY_EXECUTION: 8,
    ScopeLevel.FINDING: 9,
}


@dataclass(frozen=True, slots=True)
class AuthorityScope:
    """An exact, explicitly levelled authority scope; never a lookup query."""

    level: ScopeLevel
    tenant_id: str
    workspace_id: str | None
    resource_scope_id: str | None
    facility_id: str | None
    connection_id: str | None
    system_id: str | None
    asset_id: str | None
    native_result_id: str | None
    authority_execution_id: str | None
    finding_id: str | None

    def __post_init__(self) -> None:
        try:
            level = ScopeLevel(self.level)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("scope_level_invalid") from exc
        object.__setattr__(self, "level", level)
        level_index = _SCOPE_LEVEL_INDEX[level]
        for index, field_name in enumerate(_SCOPE_FIELDS):
            value = getattr(self, field_name)
            if field_name == "asset_id" and index <= level_index:
                if value is not None:
                    normalized = _required_text(value, field_name)
                    if normalized.casefold() in _WILDCARD_VALUES:
                        _fail("scope_asset_wildcard_forbidden")
                    object.__setattr__(self, field_name, normalized)
                # None is an exact typed-null asset at asset-or-deeper levels.
                continue
            if field_name == "native_result_id" and index <= level_index:
                if value is None:
                    if level is ScopeLevel.NATIVE_RESULT:
                        _fail("scope_native_result_id_required")
                    # A failure/ineligibility decision is an exact terminal
                    # source, not a P0.1 native result. Deeper scopes retain a
                    # typed-null native-result dimension in that case.
                    continue
                normalized = _required_text(value, field_name)
                if normalized.casefold() in _WILDCARD_VALUES:
                    _fail("scope_wildcard_forbidden:native_result_id")
                object.__setattr__(self, field_name, normalized)
                continue
            if index <= level_index:
                normalized = _required_text(value, field_name)
                if normalized.casefold() in _WILDCARD_VALUES:
                    _fail(f"scope_wildcard_forbidden:{field_name}")
                object.__setattr__(self, field_name, normalized)
            elif value is not None:
                _fail(f"scope_field_exceeds_declared_level:{field_name}")

    @property
    def tenant_scope_id(self) -> str:
        """Compatibility spelling for the repository's tenant scope value."""

        return self.tenant_id

    def as_dict(self) -> dict[str, str | None]:
        return {
            "contract": "authority-scope.v1",
            "level": self.level.value,
            **{field_name: getattr(self, field_name) for field_name in _SCOPE_FIELDS},
        }

    @property
    def digest(self) -> TypedDigest:
        return TypedDigest.from_value("authority-scope.v1", self.as_dict())

    @property
    def scope_digest(self) -> TypedDigest:
        return self.digest

    def identity_components(self) -> tuple[str | None, ...]:
        """Return declared-order scalars, retaining typed-null asset identity."""

        level_index = _SCOPE_LEVEL_INDEX[self.level]
        return (
            "authority-scope.v1",
            self.level.value,
            *(getattr(self, name) for name in _SCOPE_FIELDS[: level_index + 1]),
        )

    def require_level(self, required: ScopeLevel) -> AuthorityScope:
        try:
            required_level = ScopeLevel(required)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("required_scope_level_invalid") from exc
        if self.level is not required_level:
            _fail(
                "scope_level_mismatch:"
                f"expected={required_level.value}:actual={self.level.value}"
            )
        return self

    def require_exact(self, expected: AuthorityScope) -> AuthorityScope:
        if not isinstance(expected, AuthorityScope) or self != expected:
            _fail("authority_scope_exact_match_required")
        return self


@dataclass(frozen=True, slots=True)
class Limitation:
    code: str
    contract_version: ContractVersion
    applies_to: str
    parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _required_text(self.code, "limitation_code"))
        object.__setattr__(
            self, "applies_to", _required_text(self.applies_to, "limitation_applies_to")
        )
        if not isinstance(self.contract_version, ContractVersion):
            _fail("limitation_contract_version_invalid")
        parameters = _normalized_pairs(self.parameters, "limitation_parameter")
        object.__setattr__(self, "parameters", parameters)

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "contract_version": self.contract_version.as_dict(),
            "applies_to": self.applies_to,
            "parameters": self.parameters,
        }


@dataclass(frozen=True, slots=True)
class Provenance:
    producer: str
    producer_version: ContractVersion
    source_identities: tuple[str, ...]
    trace_digest: TypedDigest | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "producer", _required_text(self.producer, "producer"))
        if not isinstance(self.producer_version, ContractVersion):
            _fail("provenance_producer_version_invalid")
        sources = _normalized_unique_texts(
            self.source_identities, "provenance_source_identity"
        )
        if not sources:
            _fail("provenance_source_identity_required")
        object.__setattr__(self, "source_identities", sources)
        if self.trace_digest is not None and not isinstance(self.trace_digest, TypedDigest):
            _fail("provenance_trace_digest_invalid")

    def as_dict(self) -> dict[str, object]:
        return {
            "producer": self.producer,
            "producer_version": self.producer_version.as_dict(),
            "source_identities": self.source_identities,
            "trace_digest": (
                self.trace_digest.as_dict() if self.trace_digest is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class Integrity:
    digest: TypedDigest
    contract_version: ContractVersion

    def __post_init__(self) -> None:
        if not isinstance(self.digest, TypedDigest):
            _fail("integrity_digest_invalid")
        if not isinstance(self.contract_version, ContractVersion):
            _fail("integrity_contract_version_invalid")

    @classmethod
    def from_value(
        cls, *, digest_contract: str, contract_version: ContractVersion, value: Any
    ) -> Integrity:
        return cls(
            digest=TypedDigest.from_value(digest_contract, value),
            contract_version=contract_version,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "digest": self.digest.as_dict(),
            "contract_version": self.contract_version.as_dict(),
        }


class CompletenessState(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class Completeness:
    state: CompletenessState
    contract_version: ContractVersion
    omissions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            state = CompletenessState(self.state)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("completeness_state_invalid") from exc
        object.__setattr__(self, "state", state)
        if not isinstance(self.contract_version, ContractVersion):
            _fail("completeness_contract_version_invalid")
        omissions = _normalized_unique_texts(
            self.omissions, "completeness_omission"
        )
        if state is CompletenessState.COMPLETE and omissions:
            _fail("complete_contract_cannot_have_omissions")
        if state is CompletenessState.PARTIAL and not omissions:
            _fail("partial_contract_requires_omissions")
        object.__setattr__(self, "omissions", omissions)

    def require_canonical_authority(self) -> Completeness:
        if self.state is not CompletenessState.COMPLETE:
            _fail("canonical_authority_must_be_complete")
        return self

    def require_complete(self) -> Completeness:
        return self.require_canonical_authority()

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "contract_version": self.contract_version.as_dict(),
            "omissions": self.omissions,
        }


def require_canonical_authority_complete(value: Completeness) -> Completeness:
    if not isinstance(value, Completeness):
        _fail("canonical_authority_completeness_invalid")
    return value.require_canonical_authority()


def _normalized_pairs(
    values: tuple[tuple[str, str], ...], field_name: str
) -> tuple[tuple[str, str], ...]:
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, tuple) or len(value) != 2:
            _fail(f"{field_name}_invalid")
        key = _required_text(value[0], f"{field_name}_key")
        item = _required_text(value[1], f"{field_name}_value")
        if key in seen:
            _fail(f"{field_name}_duplicate:{key}")
        seen.add(key)
        normalized.append((key, item))
    return tuple(sorted(normalized))


def _normalized_unique_texts(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(_required_text(value, field_name) for value in values)
    if len(set(normalized)) != len(normalized):
        _fail(f"{field_name}_duplicate")
    return tuple(sorted(normalized))


class GovernanceOwner(str, Enum):
    PRODUCT_SYSTEM_BEHAVIOR = "product_system_behavior_owner"
    CONNECTOR_DATA_QUALITY = "connector_data_quality_owner"
    SECURITY_ADMINISTRATIVE = "security_administrative_owner"
    MIGRATION_OPERATIONS = "migration_operations_owner"
    PRODUCT_COMPATIBILITY = "product_compatibility_owner"
    VALIDATION = "validation_owner"


class ConfigurationStatus(str, Enum):
    CONFIGURED = "configured"
    REQUIRED_BUT_UNRESOLVED = "required_but_unresolved"


class ExistingStreamEnrollmentMode(str, Enum):
    RECONSTRUCT_EXISTING = "reconstruct_existing_stream"
    CLEAN_GENERATION = "clean_generation_enrollment"


class _RequiredConfiguration:
    status: ConfigurationStatus
    owner: GovernanceOwner

    def require_configured(self) -> _RequiredConfiguration:
        if self.status is not ConfigurationStatus.CONFIGURED:
            _fail(
                f"configuration_required_but_unresolved:{type(self).__name__}:"
                f"owner={self.owner.value}"
            )
        return self

    @property
    def is_configured(self) -> bool:
        return self.status is ConfigurationStatus.CONFIGURED

    def as_dict(self) -> dict[str, Any]:
        return {
            item.name: _canonical_value(getattr(self, item.name))
            for item in fields(self)
        }


def _configuration_status(value: object) -> ConfigurationStatus:
    try:
        return ConfigurationStatus(value)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError("configuration_status_invalid") from exc


def _reject_unresolved_values(status: ConfigurationStatus, *values: object) -> None:
    if status is ConfigurationStatus.REQUIRED_BUT_UNRESOLVED and any(
        value is not None for value in values
    ):
        _fail("unresolved_configuration_cannot_carry_policy_values")


def _positive_int(value: object | None, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{field_name}_must_be_positive_integer")
    return value


def _nonnegative_int(value: object | None, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"{field_name}_must_be_nonnegative_integer")
    return value


@dataclass(frozen=True, slots=True)
class EvaluationCadenceConfiguration(_RequiredConfiguration):
    status: ConfigurationStatus
    cadence_seconds: int | None = None
    lookback_seconds: int | None = None
    utc_origin: datetime | None = None
    partial_edge_policy: str | None = None
    overlapping_context_learning_policy: str | None = None
    owner: GovernanceOwner = field(
        default=GovernanceOwner.PRODUCT_SYSTEM_BEHAVIOR, init=False
    )

    def __post_init__(self) -> None:
        status = _configuration_status(self.status)
        object.__setattr__(self, "status", status)
        if self.owner is not GovernanceOwner.PRODUCT_SYSTEM_BEHAVIOR:
            _fail("evaluation_cadence_configuration_owner_invalid")
        values = (
            self.cadence_seconds,
            self.lookback_seconds,
            self.utc_origin,
            self.partial_edge_policy,
            self.overlapping_context_learning_policy,
        )
        _reject_unresolved_values(status, *values)
        if status is ConfigurationStatus.REQUIRED_BUT_UNRESOLVED:
            return
        cadence = _positive_int(self.cadence_seconds, "cadence_seconds")
        lookback = _positive_int(self.lookback_seconds, "lookback_seconds")
        if lookback % cadence:
            _fail("lookback_must_be_divisible_by_cadence")
        if not isinstance(self.utc_origin, datetime):
            _fail("utc_origin_required")
        if self.utc_origin.tzinfo is None or self.utc_origin.utcoffset() is None:
            _fail("utc_origin_must_be_timezone_aware")
        if self.utc_origin.utcoffset() != timezone.utc.utcoffset(self.utc_origin):
            _fail("utc_origin_must_be_utc")
        object.__setattr__(
            self,
            "partial_edge_policy",
            _required_text(self.partial_edge_policy, "partial_edge_policy"),
        )
        object.__setattr__(
            self,
            "overlapping_context_learning_policy",
            _required_text(
                self.overlapping_context_learning_policy,
                "overlapping_context_learning_policy",
            ),
        )


@dataclass(frozen=True, slots=True)
class AllowedLatenessConfiguration(_RequiredConfiguration):
    status: ConfigurationStatus
    source_contract: str | None = None
    allowed_lateness_seconds: int | None = None
    completeness_assertion: str | None = None
    owner: GovernanceOwner = field(
        default=GovernanceOwner.CONNECTOR_DATA_QUALITY, init=False
    )

    def __post_init__(self) -> None:
        status = _configuration_status(self.status)
        object.__setattr__(self, "status", status)
        if self.owner is not GovernanceOwner.CONNECTOR_DATA_QUALITY:
            _fail("allowed_lateness_configuration_owner_invalid")
        _reject_unresolved_values(
            status,
            self.source_contract,
            self.allowed_lateness_seconds,
            self.completeness_assertion,
        )
        if status is ConfigurationStatus.REQUIRED_BUT_UNRESOLVED:
            return
        object.__setattr__(
            self, "source_contract", _required_text(self.source_contract, "source_contract")
        )
        has_lateness = self.allowed_lateness_seconds is not None
        has_assertion = self.completeness_assertion is not None
        if has_lateness == has_assertion:
            _fail("allowed_lateness_requires_exactly_one_source_policy")
        if has_lateness:
            _nonnegative_int(
                self.allowed_lateness_seconds, "allowed_lateness_seconds"
            )
        else:
            object.__setattr__(
                self,
                "completeness_assertion",
                _required_text(
                    self.completeness_assertion, "completeness_assertion"
                ),
            )


@dataclass(frozen=True, slots=True)
class FutureSkewConfiguration(_RequiredConfiguration):
    status: ConfigurationStatus
    source_contract: str | None = None
    maximum_future_skew_seconds: int | None = None
    release_policy: str | None = None
    owner: GovernanceOwner = field(
        default=GovernanceOwner.CONNECTOR_DATA_QUALITY, init=False
    )

    def __post_init__(self) -> None:
        status = _configuration_status(self.status)
        object.__setattr__(self, "status", status)
        if self.owner is not GovernanceOwner.CONNECTOR_DATA_QUALITY:
            _fail("future_skew_configuration_owner_invalid")
        _reject_unresolved_values(
            status,
            self.source_contract,
            self.maximum_future_skew_seconds,
            self.release_policy,
        )
        if status is ConfigurationStatus.REQUIRED_BUT_UNRESOLVED:
            return
        object.__setattr__(
            self, "source_contract", _required_text(self.source_contract, "source_contract")
        )
        _nonnegative_int(
            self.maximum_future_skew_seconds, "maximum_future_skew_seconds"
        )
        object.__setattr__(
            self,
            "release_policy",
            _required_text(self.release_policy, "future_skew_release_policy"),
        )


@dataclass(frozen=True, slots=True)
class ReplayPolicyConfiguration(_RequiredConfiguration):
    status: ConfigurationStatus
    authorization_policy: str | None = None
    hard_limit_executions: int | None = None
    hard_limit_observations: int | None = None
    hard_limit_bytes: int | None = None
    hard_limit_cost_units: int | None = None
    audit_retention_days: int | None = None
    remediation_authority: str | None = None
    promotion_authority: str | None = None
    owner: GovernanceOwner = field(
        default=GovernanceOwner.SECURITY_ADMINISTRATIVE, init=False
    )

    def __post_init__(self) -> None:
        status = _configuration_status(self.status)
        object.__setattr__(self, "status", status)
        if self.owner is not GovernanceOwner.SECURITY_ADMINISTRATIVE:
            _fail("replay_policy_configuration_owner_invalid")
        values = (
            self.authorization_policy,
            self.hard_limit_executions,
            self.hard_limit_observations,
            self.hard_limit_bytes,
            self.hard_limit_cost_units,
            self.audit_retention_days,
            self.remediation_authority,
            self.promotion_authority,
        )
        _reject_unresolved_values(status, *values)
        if status is ConfigurationStatus.REQUIRED_BUT_UNRESOLVED:
            return
        for field_name in (
            "authorization_policy",
            "remediation_authority",
            "promotion_authority",
        ):
            object.__setattr__(
                self, field_name, _required_text(getattr(self, field_name), field_name)
            )
        _positive_int(self.hard_limit_executions, "hard_limit_executions")
        _positive_int(self.hard_limit_observations, "hard_limit_observations")
        _positive_int(self.hard_limit_bytes, "hard_limit_bytes")
        _positive_int(self.hard_limit_cost_units, "hard_limit_cost_units")
        _positive_int(self.audit_retention_days, "audit_retention_days")


@dataclass(frozen=True, slots=True)
class ExistingStreamEnrollmentPolicy(_RequiredConfiguration):
    status: ConfigurationStatus
    enrollment_mode: ExistingStreamEnrollmentMode | None = None
    owner: GovernanceOwner = field(
        default=GovernanceOwner.MIGRATION_OPERATIONS, init=False
    )

    def __post_init__(self) -> None:
        status = _configuration_status(self.status)
        object.__setattr__(self, "status", status)
        if self.owner is not GovernanceOwner.MIGRATION_OPERATIONS:
            _fail("existing_stream_enrollment_policy_owner_invalid")
        _reject_unresolved_values(status, self.enrollment_mode)
        if status is ConfigurationStatus.REQUIRED_BUT_UNRESOLVED:
            return
        try:
            mode = ExistingStreamEnrollmentMode(self.enrollment_mode)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("existing_stream_enrollment_mode_invalid") from exc
        object.__setattr__(self, "enrollment_mode", mode)


@dataclass(frozen=True, slots=True)
class LegacyCompatibilityPolicy(_RequiredConfiguration):
    status: ConfigurationStatus
    label_policy: str | None = None
    retention_policy: str | None = None
    package_terminology: str | None = None
    deprecation_policy: str | None = None
    owner: GovernanceOwner = field(
        default=GovernanceOwner.PRODUCT_COMPATIBILITY, init=False
    )

    def __post_init__(self) -> None:
        status = _configuration_status(self.status)
        object.__setattr__(self, "status", status)
        if self.owner is not GovernanceOwner.PRODUCT_COMPATIBILITY:
            _fail("legacy_compatibility_policy_owner_invalid")
        values = (
            self.label_policy,
            self.retention_policy,
            self.package_terminology,
            self.deprecation_policy,
        )
        _reject_unresolved_values(status, *values)
        if status is ConfigurationStatus.REQUIRED_BUT_UNRESOLVED:
            return
        for field_name in (
            "label_policy",
            "retention_policy",
            "package_terminology",
            "deprecation_policy",
        ):
            object.__setattr__(
                self, field_name, _required_text(getattr(self, field_name), field_name)
            )


@dataclass(frozen=True, slots=True)
class ParityCutoverPolicy(_RequiredConfiguration):
    status: ConfigurationStatus
    sustained_parity_duration_seconds: int | None = None
    sample_threshold: int | None = None
    scope_threshold: int | None = None
    maximum_unexplained_critical: int | None = None
    cutover_evidence_requirement: str | None = None
    owner: GovernanceOwner = field(default=GovernanceOwner.VALIDATION, init=False)

    def __post_init__(self) -> None:
        status = _configuration_status(self.status)
        object.__setattr__(self, "status", status)
        if self.owner is not GovernanceOwner.VALIDATION:
            _fail("parity_cutover_policy_owner_invalid")
        values = (
            self.sustained_parity_duration_seconds,
            self.sample_threshold,
            self.scope_threshold,
            self.maximum_unexplained_critical,
            self.cutover_evidence_requirement,
        )
        _reject_unresolved_values(status, *values)
        if status is ConfigurationStatus.REQUIRED_BUT_UNRESOLVED:
            return
        _positive_int(
            self.sustained_parity_duration_seconds,
            "sustained_parity_duration_seconds",
        )
        _positive_int(self.sample_threshold, "sample_threshold")
        _positive_int(self.scope_threshold, "scope_threshold")
        _nonnegative_int(
            self.maximum_unexplained_critical,
            "maximum_unexplained_critical",
        )
        object.__setattr__(
            self,
            "cutover_evidence_requirement",
            _required_text(
                self.cutover_evidence_requirement, "cutover_evidence_requirement"
            ),
        )


__all__ = (
    "AllowedLatenessConfiguration",
    "AuthorityScope",
    "Completeness",
    "CompletenessState",
    "ConfigurationStatus",
    "ContractValidationError",
    "ContractVersion",
    "EvaluationCadenceConfiguration",
    "ExistingStreamEnrollmentMode",
    "ExistingStreamEnrollmentPolicy",
    "FutureSkewConfiguration",
    "GovernanceOwner",
    "Integrity",
    "LegacyCompatibilityPolicy",
    "Limitation",
    "ParityCutoverPolicy",
    "Provenance",
    "ReplayPolicyConfiguration",
    "ScopeLevel",
    "TypedDigest",
    "VersionBundle",
    "canonical_json_bytes",
    "canonical_json_text",
    "canonical_utc_timestamp",
    "require_canonical_authority_complete",
)
