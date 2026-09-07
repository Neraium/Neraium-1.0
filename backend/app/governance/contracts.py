"""Versioned, JSON-serializable audit contracts without runtime authority.

IDs fingerprint the complete normalized record (excluding its ID). Callers
provide timestamps: construction never reads a clock or generates randomness.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from typing import Annotated, ClassVar, Literal, Self

from pydantic import (
    AfterValidator, BaseModel, ConfigDict, Field, JsonValue, StrictBool,
    StringConstraints, field_validator, model_validator,
)


Text = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=2000, pattern=r"\S")]
Version = Annotated[int, Field(strict=True, ge=1)]


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def content_id(kind: str, value: object) -> str:
    return f"{kind}:{sha256(canonical_json(value).encode('utf-8')).hexdigest()}"


def _timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone_required")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


Timestamp = Annotated[Text, AfterValidator(_timestamp)]


def _bounded(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    if len(canonical_json(value).encode("utf-8")) > 65536:
        raise ValueError("payload_exceeds_65536_bytes")
    return value


Payload = Annotated[dict[str, JsonValue], AfterValidator(_bounded)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True, revalidate_instances="always")

    def as_dict(self) -> dict:
        return self.model_dump(mode="json")


class ContentRecord(Contract):
    identity_field: ClassVar[str]
    identity_kind: ClassVar[str]

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        body = self.as_dict()
        supplied = body.pop(self.identity_field)
        expected = content_id(self.identity_kind, body)
        if supplied and supplied != expected:
            raise ValueError(f"content_identity_mismatch:{self.identity_field}")
        object.__setattr__(self, self.identity_field, expected)
        return self


class EvidenceFamily(str, Enum):
    SIGNAL_LOCATION = "signal_location"
    RELATIONAL = "relational"
    COVARIANCE_GEOMETRY = "covariance_geometry"
    TEMPORAL = "temporal"
    EXPECTED_RESPONSE = "expected_response"
    MULTISCALE = "multiscale"
    PHYSICS_EXTERNAL = "physics_external"
    INSTRUMENTATION = "instrumentation"
    TREND = "trend"


class Provenance(Contract):
    source: Text
    source_version: Text
    reference_ids: tuple[Text, ...]


class SourceWindow(Contract):
    """Exact source snapshot/window ID; optional chronological bounds."""
    window_id: Text
    started_at: Timestamp | None = None
    ended_at: Timestamp | None = None

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if (self.started_at is None) != (self.ended_at is None):
            raise ValueError("both_window_bounds_required")
        if self.started_at and datetime.fromisoformat(self.started_at) > datetime.fromisoformat(self.ended_at):
            raise ValueError("reversed_window")
        return self


class DependencyRef(Contract):
    kind: Literal["observation", "evidence"]
    dependency_id: Text


class ObservationReference(Contract):
    """An immutable observation snapshot reference, not an inferred raw leaf."""
    observation_id: Text
    source_id: Text
    system_scope: Text
    source_signals: tuple[Text, ...]
    source_window: SourceWindow
    provenance: Provenance


class EvidenceObject(ContentRecord):
    identity_field = "evidence_id"
    identity_kind = "evidence"
    schema_version: Literal["evidence-object-v1"] = "evidence-object-v1"
    evidence_id: str = ""
    evidence_family: EvidenceFamily
    evidence_method: Text
    source_module: Text
    source_run_id: Text
    system_scope: Text
    source_signals: tuple[Text, ...]
    source_window: SourceWindow
    derived_from: tuple[DependencyRef, ...]
    assumption_set: tuple[Text, ...]
    context_refs: tuple[Text, ...]
    provenance: Provenance
    created_at: Timestamp
    effective_at: Timestamp | None = None
    version: Version = 1
    supersedes: Text | None = None
    payload: Payload | None = None
    result_ref: Text | None = None
    lineage_complete: StrictBool = False
    covariance_source_id: Text | None = None

    @field_validator("source_signals", "assumption_set", "context_refs")
    @classmethod
    def ordered_set(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))

    @field_validator("derived_from")
    @classmethod
    def ordered_dependencies(cls, value: tuple[DependencyRef, ...]) -> tuple[DependencyRef, ...]:
        return tuple(sorted(set(value), key=lambda item: (item.kind, item.dependency_id)))

    @model_validator(mode="after")
    def result_present(self) -> Self:
        if self.payload is None and self.result_ref is None:
            raise ValueError("payload_or_result_reference_required")
        if self.version == 1 and self.supersedes is not None:
            raise ValueError("initial_evidence_cannot_supersede")
        if self.version > 1 and self.supersedes is None:
            raise ValueError("versioned_evidence_requires_supersedes")
        return self


class MaturityLevel(str, Enum):
    # v1 still evaluates only L0–L2; v2 adds explicit characterization/context.
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class LifecycleState(str, Enum):
    NEW = "new"
    PERSISTENT = "persistent"
    RECOVERING = "recovering"
    ADAPTED = "adapted"
    EXTERNALLY_EXPLAINED = "externally_explained"
    UNRESOLVED = "unresolved"
    SUPERSEDED = "superseded"
    CLOSED = "closed"


class LifecycleChange(Contract):
    schema_version: Literal["finding-lifecycle-v1"] = "finding-lifecycle-v1"
    state: LifecycleState
    previous_event_id: Text | None = None
    effective_at: Timestamp
    evidence_ids: tuple[Text, ...]
    reasons: Annotated[tuple[Text, ...], Field(min_length=1)]
    source_run_id: Text
    provenance: Provenance


class FindingLifecycleEvent(LifecycleChange):
    """Envelope identity/version are assigned by the existing finding event log."""
    event_id: Text
    finding_id: Text
    version: Version
    recorded_at: Timestamp
    actor: Text


class AuthorityOutcome(str, Enum):
    PERMITTED = "permitted"
    DEFERRED = "deferred"
    BLOCKED = "blocked"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    RELEASED = "released"
    ESCALATED = "escalated"


class RequestedOperation(str, Enum):
    """Software operations only; extending this enum does not activate handlers."""
    PRESENT_EVIDENCE = "present_evidence"
    EVALUATE_ADAPTATION = "evaluate_adaptation"
    ADAPT_STATE_LOCATION = "adapt_state_location"
    ADAPT_STRUCTURE = "adapt_structure"
    ESCALATE_FINDING = "escalate_finding"
    CLOSE_FINDING = "close_finding"


class HumanReview(Contract):
    required: StrictBool
    status: Literal["not_required", "pending", "approved", "rejected"]
    reviewer_identity: Text | None = None
    reviewed_at: Timestamp | None = None
    rationale: Text | None = None

    @model_validator(mode="after")
    def review_consistency(self) -> Self:
        completed = self.status in {"approved", "rejected"}
        if completed != all((self.reviewer_identity, self.reviewed_at, self.rationale)):
            raise ValueError("completed_review_requires_identity_time_and_rationale")
        if not completed and any((self.reviewer_identity, self.reviewed_at, self.rationale)):
            raise ValueError("pending_review_cannot_claim_completion")
        if self.required and self.status == "not_required":
            raise ValueError("required_review_cannot_be_not_required")
        return self


class AuthorityDecision(ContentRecord):
    identity_field = "decision_id"
    identity_kind = "authority-decision"
    schema_version: Literal["authority-decision-v1"] = "authority-decision-v1"
    decision_id: str = ""
    finding_id: Text
    system_scope: Text
    decision_timestamp: Timestamp
    effective_timestamp: Timestamp
    policy_id: Text
    policy_version: Text
    policy_snapshot_id: Text
    evidence_snapshot_ids: Annotated[tuple[Text, ...], Field(min_length=1)]
    context_snapshot_id: Text
    dependency_graph_snapshot_id: Text
    maturity_at_decision: MaturityLevel
    maturity_snapshot_id: Text
    lifecycle_state_at_decision: LifecycleState
    lifecycle_event_id: Text
    requested_operation: RequestedOperation
    decision_outcome: AuthorityOutcome
    decision_reasons: Annotated[tuple[Text, ...], Field(min_length=1)]
    limiting_evidence: tuple[Text, ...]
    contradicting_evidence: tuple[Text, ...]
    # IDs of immutable model snapshots, never mutable active-model pointers.
    active_model_before: Text | None
    candidate_model: Text | None
    active_model_after: Text | None
    human_review: HumanReview
    supersedes_decision_id: Text | None = None
    source_run_id: Text

    @model_validator(mode="after")
    def review_outcome(self) -> Self:
        if self.decision_outcome == AuthorityOutcome.HUMAN_REVIEW_REQUIRED:
            if not self.human_review.required or self.human_review.status != "pending":
                raise ValueError("human_review_required_outcome_requires_pending_review")
        if self.decision_outcome in {AuthorityOutcome.PERMITTED, AuthorityOutcome.RELEASED}:
            if self.human_review.required and self.human_review.status != "approved":
                raise ValueError("permission_requires_completed_required_review")
        return self


class AuditSnapshot(ContentRecord):
    """Minimal frozen context/policy/model envelope, not a Context Registry."""
    identity_field = "snapshot_id"
    identity_kind = "governance-snapshot"
    schema_version: Literal["governance-snapshot-v1"] = "governance-snapshot-v1"
    snapshot_id: str = ""
    kind: Literal["context", "policy", "model"]
    object_id: Text
    version: Text
    system_scope: Text
    created_at: Timestamp
    provenance: Provenance
    payload: Payload
