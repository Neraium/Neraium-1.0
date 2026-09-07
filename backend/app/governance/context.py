"""Context Registry v1. Verification is an explicit source assertion, not attestation."""
from enum import Enum
from typing import Literal, Self

from pydantic import field_validator, model_validator

from app.governance.contracts import ContentRecord, Contract, Payload, Provenance, Text, Timestamp, Version, canonical_json
from app.governance.registry import VersionRegistry, covers, time


class ContextType(str, Enum):
    INFRASTRUCTURE_IDENTITY = "infrastructure_identity"
    OPERATING_CONTEXT = "operating_context"
    ENGINEERING_CONSTRAINT = "engineering_constraint"
    COMMISSIONING_REFERENCE = "commissioning_reference"
    MAINTENANCE_EVENT = "maintenance_event"
    CALIBRATION_EVENT = "calibration_event"
    SETPOINT_CHANGE = "setpoint_change"
    MODEL_HISTORY = "model_history"
    BASELINE_HISTORY = "baseline_history"
    ADAPTATION_EVENT = "adaptation_event"
    EXTERNAL_ANCHOR = "external_anchor"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    INVALIDATED = "invalidated"


class ContextObject(ContentRecord):
    identity_field = "context_id"
    identity_kind = "context"
    schema_version: Literal["context-v1"] = "context-v1"
    context_id: str = ""
    # Logical identity remains stable; context_id identifies an exact version.
    context_key: Text
    context_type: ContextType
    system_scope: Text
    source_type: Text
    source_reference: Text
    provenance: Provenance
    verification_status: VerificationStatus
    effective_from: Timestamp
    effective_to: Timestamp | None = None
    created_at: Timestamp
    version: Version = 1
    supersedes: Text | None = None
    # Exact JSON equality predicates. Unknown facts fail closed.
    validity_conditions: Payload = {}
    payload: Payload

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.effective_to and time(self.effective_to) <= time(self.effective_from):
            raise ValueError("empty_or_reversed_context_interval")
        if (self.version == 1) != (self.supersedes is None):
            raise ValueError("context_version_requires_predecessor")
        return self

    @property
    def registry_scope(self): return self.system_scope
    @property
    def registry_identity(self): return self.context_key
    @property
    def registry_version(self): return self.version
    @property
    def record_id(self): return self.context_id


class ContextRegistry(VersionRegistry):
    def __init__(self, storage):
        super().__init__(storage, ContextObject, "context-registry-v1")


class ContextBasis(Contract):
    system_scope: Text
    evaluated_at: Timestamp
    relevant_at: Timestamp
    records: tuple[ContextObject, ...] = ()
    # Facts are a frozen, time-stamped adapter assertion, not a live environment read.
    facts: Payload = {}
    facts_available_at: Timestamp
    facts_provenance: Provenance

    def validate_historical_basis(self, original: "ContextBasis") -> None:
        # Reconstruct only the history knowable at the earlier evaluation.
        # Its facts keep their original availability/provenance; today's facts
        # must never be substituted into historical qualification.
        known = tuple(item for item in self.records if time(item.created_at) <= time(original.evaluated_at))
        reconstructed = ContextBasis.model_validate({**original.as_dict(), "records": known})
        if reconstructed != original:
            raise ValueError("maturity_context_history_mismatch")

    @field_validator("records")
    @classmethod
    def ordered_records(cls, value):
        return tuple(sorted(value, key=lambda item: (item.system_scope, item.context_key, item.version)))

    @model_validator(mode="after")
    def available(self) -> Self:
        if time(self.relevant_at) > time(self.evaluated_at) or time(self.facts_available_at) > time(self.evaluated_at):
            raise ValueError("future_context_facts_or_relevant_time")
        if any(time(item.created_at) > time(self.evaluated_at) for item in self.records):
            raise ValueError("future_context_knowledge")
        ids = [item.context_id for item in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_context_version")
        # Multiple versions must form a complete non-branching chain.
        chains = {}
        for item in self.records:
            chains.setdefault((item.system_scope, item.context_key), []).append(item)
        for chain in chains.values():
            chain.sort(key=lambda item: item.version)
            for index, item in enumerate(chain):
                if item.version != index + 1 or (index and (
                    item.supersedes != chain[index - 1].context_id
                    or time(item.created_at) < time(chain[index - 1].created_at)
                )):
                    raise ValueError("incomplete_or_ambiguous_context_history")
        return self


class ContextQualification(Contract):
    applicable_context_ids: tuple[Text, ...]
    rejected_context_ids: tuple[Text, ...]
    verification_statuses: dict[str, VerificationStatus]
    qualification_reasons: tuple[Text, ...]
    limiting_context: tuple[Text, ...]
    unavailable_context: tuple[Text, ...]
    evaluated_at: Timestamp


QUALIFYING_TYPES = frozenset({ContextType.ENGINEERING_CONSTRAINT, ContextType.COMMISSIONING_REFERENCE,
    ContextType.MAINTENANCE_EVENT, ContextType.CALIBRATION_EVENT, ContextType.SETPOINT_CHANGE, ContextType.EXTERNAL_ANCHOR})


def qualify_context(basis: ContextBasis, *, external_only: bool = True) -> ContextQualification:
    basis = ContextBasis.model_validate(basis.as_dict())
    latest = {}
    for item in basis.records:
        key = (item.system_scope, item.context_key)
        if key not in latest or item.version > latest[key].version:
            latest[key] = item
    accepted, rejected, limited, reasons = [], [], [], []
    for item in sorted(basis.records, key=lambda item: item.context_id):
        reason = None
        if item.system_scope != basis.system_scope:
            reason = "scope_mismatch"
        elif latest[(item.system_scope, item.context_key)] != item:
            reason = "superseded"
        elif item.verification_status == VerificationStatus.INVALIDATED:
            reason = "invalidated"
        elif not covers(item.effective_from, item.effective_to, basis.relevant_at):
            reason = "outside_effective_interval"
        elif any(key not in basis.facts or canonical_json(basis.facts[key]) != canonical_json(value)
                 for key, value in item.validity_conditions.items()):
            reason = "validity_conditions_unsatisfied"
        elif external_only and item.context_type not in QUALIFYING_TYPES:
            reason = "not_external_qualification"
        elif item.verification_status != VerificationStatus.VERIFIED:
            reason = "verification_limited"
        if reason:
            rejected.append(item.context_id)
            limited.append(item.context_id)
        else:
            accepted.append(item.context_id)
        reasons.append(f"{item.context_id}:{reason or 'verified_applicable_anchor'}")
    return ContextQualification(applicable_context_ids=tuple(accepted), rejected_context_ids=tuple(rejected),
        verification_statuses={item.context_id: item.verification_status for item in basis.records},
        qualification_reasons=tuple(reasons), limiting_context=tuple(limited),
        unavailable_context=() if accepted else ("verified_applicable_external_anchor",), evaluated_at=basis.evaluated_at)
