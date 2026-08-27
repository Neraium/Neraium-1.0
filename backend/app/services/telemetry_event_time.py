"""Pure P0.2 chronology contracts for reconciled analytical authority.

The values in this module are supplied by the future P0.2 chronology owner.
They can be validated and carried by P0.3/P1.2, but this module does not
calculate slots, select references, inspect a processing clock, schedule work,
or perform lifecycle transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from app.services.authority_contract_common import (
    AllowedLatenessConfiguration,
    AuthorityScope,
    ContractValidationError,
    ContractVersion,
    EvaluationCadenceConfiguration,
    FutureSkewConfiguration,
    Integrity,
    TypedDigest,
    canonical_json_bytes,
    canonical_json_text,
    canonical_utc_timestamp,
)
from app.services.authority_identity import (
    AnalyticalReferenceIdentity,
    ChronologyExecutionIdentity,
    ChronologySlotIdentity,
)


CHRONOLOGY_REFERENCE_CONTRACT = "chronology-reference.v1"
CHRONOLOGY_READINESS_BINDING_CONTRACT = "chronology-readiness-binding.v1"
CHRONOLOGY_READINESS_CONFIGURATION_CONTRACT = (
    "chronology-readiness-configuration.v1"
)


class ChronologyExecutionMode(str, Enum):
    """P0.2 execution modes; none may be inferred from arrival or wall time."""

    ACTIVE = "active"
    EVALUATION_ONLY = "evaluation_only"
    HISTORICAL_NON_LEARNING = "historical_non_learning"
    REPLAY = "replay"


class ChronologyLifecycleState(str, Enum):
    """Persistable lifecycle vocabulary, not a state-transition engine."""

    ACCUMULATING = "accumulating"
    READY = "ready"
    ANALYZING = "analyzing"
    PUBLISHED_PENDING_LEARNING = "published_pending_learning"
    FINALIZED = "finalized"
    BLOCKED = "blocked"
    FAILED = "failed"


class LearningFinalizationState(str, Enum):
    """Truthful learning overlay carried separately from immutable analysis."""

    PENDING = "pending"
    FINALIZED = "finalized"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


class ChronologyDisposition(str, Enum):
    """P0.2-supplied processing disposition without implementing transitions."""

    NORMAL = "normal"
    OLD_AFTER_NEW_REJECTED = "old_after_new_rejected"
    HISTORICAL_NON_LEARNING = "historical_non_learning"
    RETRY_REUSE = "retry_reuse"
    LATE_BEFORE_FREEZE = "late_before_freeze"
    STALE_MANIFEST_PREPUBLICATION_REJECTED = (
        "stale_manifest_prepublication_rejected"
    )
    LATE_AFTER_PUBLICATION = "late_after_publication"
    FUTURE_QUARANTINED = "future_quarantined"
    INVALID_OR_MISSING_TIMESTAMP = "invalid_or_missing_timestamp"
    HISTORICAL_REFERENCE_REQUIRED = "historical_reference_required"
    READINESS_POLICY_REQUIRED = "readiness_policy_required"


_PREPUBLICATION_STATES = frozenset(
    {
        ChronologyLifecycleState.ACCUMULATING,
        ChronologyLifecycleState.READY,
        ChronologyLifecycleState.ANALYZING,
    }
)
_BLOCKING_DISPOSITIONS = frozenset(
    {
        ChronologyDisposition.OLD_AFTER_NEW_REJECTED,
        ChronologyDisposition.STALE_MANIFEST_PREPUBLICATION_REJECTED,
        ChronologyDisposition.FUTURE_QUARANTINED,
        ChronologyDisposition.INVALID_OR_MISSING_TIMESTAMP,
        ChronologyDisposition.HISTORICAL_REFERENCE_REQUIRED,
        ChronologyDisposition.READINESS_POLICY_REQUIRED,
    }
)
_ACTIVE_READY_DISPOSITIONS = frozenset(
    {
        ChronologyDisposition.NORMAL,
        ChronologyDisposition.RETRY_REUSE,
        ChronologyDisposition.LATE_BEFORE_FREEZE,
    }
)


def _enum_value(value: object, enum_type: type[Enum], code: str) -> Enum:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(code) from exc


def _require_nonnegative_integer(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractValidationError(code)
    return value


def _require_positive_integer(value: object, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractValidationError(code)
    return value


def _timestamp(value: object, code: str) -> datetime:
    if not isinstance(value, datetime):
        raise ContractValidationError(code)
    try:
        canonical_utc_timestamp(value)
    except ContractValidationError as exc:
        raise ContractValidationError(code) from exc
    return value


def chronology_readiness_configuration_identity(
    evaluation_cadence: EvaluationCadenceConfiguration,
    allowed_lateness: AllowedLatenessConfiguration,
    future_skew: FutureSkewConfiguration,
) -> TypedDigest:
    """Bind the exact supplied readiness policies without choosing values."""

    if not isinstance(evaluation_cadence, EvaluationCadenceConfiguration):
        raise ContractValidationError(
            "chronology_evaluation_cadence_configuration_required"
        )
    if not isinstance(allowed_lateness, AllowedLatenessConfiguration):
        raise ContractValidationError(
            "chronology_allowed_lateness_configuration_required"
        )
    if not isinstance(future_skew, FutureSkewConfiguration):
        raise ContractValidationError(
            "chronology_future_skew_configuration_required"
        )
    return TypedDigest.from_value(
        CHRONOLOGY_READINESS_CONFIGURATION_CONTRACT,
        {
            "evaluation_cadence": evaluation_cadence.as_dict(),
            "allowed_lateness": allowed_lateness.as_dict(),
            "future_skew": future_skew.as_dict(),
        },
    )


@dataclass(frozen=True, slots=True)
class ChronologyReference:
    """One exact, immutable P0.2 chronology binding consumed downstream.

    Duplicated identity components are intentional: validation proves the
    supplied interface was not rebound to a different scope, manifest,
    generation, predecessor, interval, configuration, or progress revision.
    No component is generated by this object.
    """

    slot_identity: ChronologySlotIdentity
    execution_identity: ChronologyExecutionIdentity
    analysis_generation: int
    learning_generation: int
    execution_mode: ChronologyExecutionMode
    predecessor_reference_id: AnalyticalReferenceIdentity | None
    predecessor_reference_digest: TypedDigest | None
    selected_analytical_reference_id: AnalyticalReferenceIdentity | None
    contribution_start: datetime
    contribution_end: datetime
    lookback_start: datetime
    lookback_end: datetime
    manifest_digest: TypedDigest
    analytical_input_digest: TypedDigest
    expected_progress_revision: int
    lifecycle_state: ChronologyLifecycleState
    learning_finalization: LearningFinalizationState
    disposition: ChronologyDisposition
    configuration_identity: TypedDigest
    version_identity: ContractVersion
    integrity: Integrity

    def __post_init__(self) -> None:
        if not isinstance(self.slot_identity, ChronologySlotIdentity):
            raise ContractValidationError("chronology_reference_slot_identity_required")
        if not isinstance(self.execution_identity, ChronologyExecutionIdentity):
            raise ContractValidationError(
                "chronology_reference_execution_identity_required"
            )
        if self.execution_identity.chronology_slot_id != self.slot_identity:
            raise ContractValidationError("chronology_reference_slot_mismatch")

        _require_positive_integer(
            self.analysis_generation,
            "chronology_reference_analysis_generation_invalid",
        )
        _require_positive_integer(
            self.learning_generation,
            "chronology_reference_learning_generation_invalid",
        )
        _require_nonnegative_integer(
            self.expected_progress_revision,
            "chronology_reference_progress_revision_invalid",
        )

        mode = _enum_value(
            self.execution_mode,
            ChronologyExecutionMode,
            "chronology_reference_execution_mode_invalid",
        )
        lifecycle = _enum_value(
            self.lifecycle_state,
            ChronologyLifecycleState,
            "chronology_reference_lifecycle_state_invalid",
        )
        finalization = _enum_value(
            self.learning_finalization,
            LearningFinalizationState,
            "chronology_reference_learning_finalization_invalid",
        )
        disposition = _enum_value(
            self.disposition,
            ChronologyDisposition,
            "chronology_reference_disposition_invalid",
        )
        object.__setattr__(self, "execution_mode", mode)
        object.__setattr__(self, "lifecycle_state", lifecycle)
        object.__setattr__(self, "learning_finalization", finalization)
        object.__setattr__(self, "disposition", disposition)

        if self.analysis_generation != self.execution_identity.analysis_generation:
            raise ContractValidationError(
                "chronology_reference_analysis_generation_mismatch"
            )
        if self.learning_generation != self.slot_identity.learning_generation:
            raise ContractValidationError(
                "chronology_reference_learning_generation_mismatch"
            )
        if mode.value != self.execution_identity.execution_mode:
            raise ContractValidationError("chronology_reference_execution_mode_mismatch")

        self._validate_predecessor_binding()
        self._validate_event_time_bounds()
        self._validate_execution_components()
        self._validate_state_binding()

        if not isinstance(self.configuration_identity, TypedDigest):
            raise ContractValidationError(
                "chronology_reference_configuration_identity_required"
            )
        if self.configuration_identity != self.execution_identity.configuration_digest:
            raise ContractValidationError(
                "chronology_reference_configuration_identity_mismatch"
            )
        if not isinstance(self.version_identity, ContractVersion):
            raise ContractValidationError("chronology_reference_version_identity_required")
        if self.version_identity != ContractVersion(
            contract=CHRONOLOGY_REFERENCE_CONTRACT,
            version="1",
        ):
            raise ContractValidationError("chronology_reference_version_identity_mismatch")
        if not isinstance(self.integrity, Integrity):
            raise ContractValidationError("chronology_reference_integrity_required")

    @property
    def scope(self) -> AuthorityScope:
        """Return the exact asset/null scope owned by the chronology slot."""

        return self.slot_identity.scope

    @property
    def chronology_slot_id(self) -> ChronologySlotIdentity:
        """Identity-spelled alias for consumers that bind typed IDs."""

        return self.slot_identity

    @property
    def chronology_execution_id(self) -> ChronologyExecutionIdentity:
        """Identity-spelled alias; never a raw/global UUID lookup key."""

        return self.execution_identity

    @property
    def finalization_state(self) -> LearningFinalizationState:
        """Compatibility spelling for the separate learning overlay."""

        return self.learning_finalization

    def _validate_predecessor_binding(self) -> None:
        if (self.predecessor_reference_id is None) != (
            self.predecessor_reference_digest is None
        ):
            raise ContractValidationError(
                "chronology_reference_predecessor_binding_incomplete"
            )
        if self.predecessor_reference_id is not None and not isinstance(
            self.predecessor_reference_id, AnalyticalReferenceIdentity
        ):
            raise ContractValidationError(
                "chronology_reference_predecessor_identity_invalid"
            )
        if self.predecessor_reference_digest is not None and not isinstance(
            self.predecessor_reference_digest, TypedDigest
        ):
            raise ContractValidationError(
                "chronology_reference_predecessor_digest_invalid"
            )
        if self.predecessor_reference_id != (
            self.execution_identity.predecessor_reference_id
        ):
            raise ContractValidationError(
                "chronology_reference_predecessor_identity_mismatch"
            )
        if self.predecessor_reference_digest != (
            self.execution_identity.predecessor_reference_digest
        ):
            raise ContractValidationError(
                "chronology_reference_predecessor_digest_mismatch"
            )
        if self.selected_analytical_reference_id is not None and not isinstance(
            self.selected_analytical_reference_id, AnalyticalReferenceIdentity
        ):
            raise ContractValidationError(
                "chronology_reference_selected_reference_invalid"
            )
        # The selected causal reference and the predecessor progress reference
        # are deliberately distinct.  A proven-empty new stream may select an
        # approved bootstrap reference while having no predecessor progress
        # record.  P0.2 supplies both values; downstream code must not infer
        # one from the other.
        if (
            self.selected_analytical_reference_id is not None
            and self.selected_analytical_reference_id.scope != self.scope
        ):
            raise ContractValidationError(
                "chronology_reference_selected_reference_scope_mismatch"
            )

    def _validate_event_time_bounds(self) -> None:
        bounds = (
            ("contribution_start", self.contribution_start),
            ("contribution_end", self.contribution_end),
            ("lookback_start", self.lookback_start),
            ("lookback_end", self.lookback_end),
        )
        for name, value in bounds:
            _timestamp(value, f"chronology_reference_{name}_invalid")
            if value != getattr(self.slot_identity, name):
                raise ContractValidationError(
                    f"chronology_reference_{name}_mismatch"
                )
        if self.contribution_start >= self.contribution_end:
            raise ContractValidationError(
                "chronology_reference_contribution_half_open_range_invalid"
            )
        if self.lookback_start >= self.lookback_end:
            raise ContractValidationError(
                "chronology_reference_lookback_half_open_range_invalid"
            )
        if self.contribution_end != self.lookback_end:
            raise ContractValidationError("chronology_reference_endpoint_mismatch")

    def _validate_execution_components(self) -> None:
        if not isinstance(self.manifest_digest, TypedDigest):
            raise ContractValidationError("chronology_reference_manifest_digest_required")
        if not isinstance(self.analytical_input_digest, TypedDigest):
            raise ContractValidationError(
                "chronology_reference_analytical_input_digest_required"
            )
        if self.manifest_digest != self.execution_identity.manifest_digest:
            raise ContractValidationError("chronology_reference_manifest_mismatch")
        if (
            self.analytical_input_digest
            != self.execution_identity.analytical_input_digest
        ):
            raise ContractValidationError("chronology_reference_input_mismatch")
        if (
            self.expected_progress_revision
            != self.execution_identity.expected_progress_revision
        ):
            raise ContractValidationError(
                "chronology_reference_progress_revision_mismatch"
            )

    def _validate_state_binding(self) -> None:
        if self.lifecycle_state in _PREPUBLICATION_STATES:
            if self.learning_finalization is not LearningFinalizationState.PENDING:
                raise ContractValidationError(
                    "prepublication_chronology_cannot_claim_learning_finalization"
                )
        elif (
            self.lifecycle_state
            is ChronologyLifecycleState.PUBLISHED_PENDING_LEARNING
        ):
            if self.learning_finalization is not LearningFinalizationState.PENDING:
                raise ContractValidationError(
                    "published_pending_chronology_requires_pending_learning"
                )
        elif self.lifecycle_state is ChronologyLifecycleState.FINALIZED:
            if self.learning_finalization not in {
                LearningFinalizationState.FINALIZED,
                LearningFinalizationState.NOT_APPLICABLE,
            }:
                raise ContractValidationError(
                    "finalized_chronology_requires_terminal_learning_state"
                )
        elif self.lifecycle_state in {
            ChronologyLifecycleState.BLOCKED,
            ChronologyLifecycleState.FAILED,
        }:
            if self.learning_finalization is not LearningFinalizationState.BLOCKED:
                raise ContractValidationError(
                    "blocked_chronology_requires_blocked_learning"
                )

        if self.disposition in _BLOCKING_DISPOSITIONS and self.lifecycle_state not in {
            ChronologyLifecycleState.ACCUMULATING,
            ChronologyLifecycleState.BLOCKED,
            ChronologyLifecycleState.FAILED,
        }:
            raise ContractValidationError(
                "blocking_chronology_disposition_requires_nonpublishable_state"
            )
        if (
            self.execution_mode is ChronologyExecutionMode.HISTORICAL_NON_LEARNING
            and self.disposition
            not in {
                ChronologyDisposition.HISTORICAL_NON_LEARNING,
                ChronologyDisposition.HISTORICAL_REFERENCE_REQUIRED,
            }
        ):
            raise ContractValidationError(
                "historical_mode_requires_historical_disposition"
            )
        if (
            self.disposition is ChronologyDisposition.HISTORICAL_NON_LEARNING
            and self.execution_mode
            is not ChronologyExecutionMode.HISTORICAL_NON_LEARNING
        ):
            raise ContractValidationError(
                "historical_disposition_requires_historical_mode"
            )
        if (
            self.disposition is ChronologyDisposition.HISTORICAL_REFERENCE_REQUIRED
            and self.selected_analytical_reference_id is not None
        ):
            raise ContractValidationError(
                "historical_reference_required_cannot_select_reference"
            )

    @property
    def is_authority_bindable(self) -> bool:
        """Whether this reference can bind successful canonical authority."""

        return (
            self.lifecycle_state
            in {
                ChronologyLifecycleState.ANALYZING,
                ChronologyLifecycleState.PUBLISHED_PENDING_LEARNING,
                ChronologyLifecycleState.FINALIZED,
            }
            and self.disposition not in _BLOCKING_DISPOSITIONS
            and self.selected_analytical_reference_id is not None
        )

    def require_authority_bindable(self) -> ChronologyReference:
        """Fail closed when a blocked/incomplete reference is offered to P0.3."""

        if not self.is_authority_bindable:
            raise ContractValidationError("chronology_reference_not_authority_bindable")
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": CHRONOLOGY_REFERENCE_CONTRACT,
            "slot_identity": self.slot_identity.as_dict(),
            "execution_identity": self.execution_identity.as_dict(),
            "analysis_generation": self.analysis_generation,
            "learning_generation": self.learning_generation,
            "execution_mode": self.execution_mode.value,
            "predecessor_reference_id": (
                self.predecessor_reference_id.as_dict()
                if self.predecessor_reference_id is not None
                else None
            ),
            "predecessor_reference_digest": (
                self.predecessor_reference_digest.as_dict()
                if self.predecessor_reference_digest is not None
                else None
            ),
            "selected_analytical_reference_id": (
                self.selected_analytical_reference_id.as_dict()
                if self.selected_analytical_reference_id is not None
                else None
            ),
            "contribution_start": canonical_utc_timestamp(self.contribution_start),
            "contribution_end": canonical_utc_timestamp(self.contribution_end),
            "lookback_start": canonical_utc_timestamp(self.lookback_start),
            "lookback_end": canonical_utc_timestamp(self.lookback_end),
            "manifest_digest": self.manifest_digest.as_dict(),
            "analytical_input_digest": self.analytical_input_digest.as_dict(),
            "expected_progress_revision": self.expected_progress_revision,
            "lifecycle_state": self.lifecycle_state.value,
            "learning_finalization": self.learning_finalization.value,
            "disposition": self.disposition.value,
            "configuration_identity": self.configuration_identity.as_dict(),
            "version_identity": self.version_identity.as_dict(),
            "integrity": self.integrity.as_dict(),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.as_dict())

    @property
    def canonical_text(self) -> str:
        return canonical_json_text(self.as_dict())


@dataclass(frozen=True, slots=True)
class ChronologyReadinessBinding:
    """Separate fail-closed assertion over architecture-significant policy.

    Holding a chronology reference does not imply readiness.  Only this
    explicit assertion requires the three governed policies to be configured.
    It still does not calculate readiness or perform a state transition.
    """

    chronology_reference: ChronologyReference
    source_scope: AuthorityScope
    source_contract: str
    active_readiness_asserted: bool
    evaluation_cadence: EvaluationCadenceConfiguration
    allowed_lateness: AllowedLatenessConfiguration
    future_skew: FutureSkewConfiguration

    def __post_init__(self) -> None:
        if not isinstance(self.chronology_reference, ChronologyReference):
            raise ContractValidationError(
                "chronology_readiness_reference_required"
            )
        if not isinstance(self.source_scope, AuthorityScope):
            raise ContractValidationError("chronology_readiness_source_scope_required")
        self.source_scope.require_exact(self.chronology_reference.scope)
        if (
            not isinstance(self.source_contract, str)
            or not self.source_contract
            or self.source_contract != self.source_contract.strip()
        ):
            raise ContractValidationError("chronology_readiness_source_contract_invalid")
        if not isinstance(self.active_readiness_asserted, bool):
            raise ContractValidationError(
                "chronology_active_readiness_assertion_must_be_boolean"
            )
        if not isinstance(self.evaluation_cadence, EvaluationCadenceConfiguration):
            raise ContractValidationError(
                "chronology_evaluation_cadence_configuration_required"
            )
        if not isinstance(self.allowed_lateness, AllowedLatenessConfiguration):
            raise ContractValidationError(
                "chronology_allowed_lateness_configuration_required"
            )
        if not isinstance(self.future_skew, FutureSkewConfiguration):
            raise ContractValidationError(
                "chronology_future_skew_configuration_required"
            )

        if not self.active_readiness_asserted:
            return
        self.evaluation_cadence.require_configured()
        self.allowed_lateness.require_configured()
        self.future_skew.require_configured()
        if (
            self.allowed_lateness.source_contract != self.source_contract
            or self.future_skew.source_contract != self.source_contract
        ):
            raise ContractValidationError(
                "chronology_readiness_source_contract_mismatch"
            )
        expected_configuration = chronology_readiness_configuration_identity(
            self.evaluation_cadence,
            self.allowed_lateness,
            self.future_skew,
        )
        if self.chronology_reference.configuration_identity != expected_configuration:
            raise ContractValidationError(
                "chronology_readiness_configuration_identity_mismatch"
            )
        reference = self.chronology_reference
        if reference.execution_mode is not ChronologyExecutionMode.ACTIVE:
            raise ContractValidationError(
                "active_readiness_requires_active_execution_mode"
            )
        if reference.lifecycle_state not in {
            ChronologyLifecycleState.READY,
            ChronologyLifecycleState.ANALYZING,
        }:
            raise ContractValidationError(
                "active_readiness_requires_ready_or_analyzing_state"
            )
        if reference.disposition not in _ACTIVE_READY_DISPOSITIONS:
            raise ContractValidationError(
                "active_readiness_rejects_chronology_disposition"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": CHRONOLOGY_READINESS_BINDING_CONTRACT,
            "chronology_execution_id": str(
                self.chronology_reference.execution_identity.value
            ),
            "source_scope": self.source_scope.as_dict(),
            "source_contract": self.source_contract,
            "active_readiness_asserted": self.active_readiness_asserted,
            "evaluation_cadence": self.evaluation_cadence.as_dict(),
            "allowed_lateness": self.allowed_lateness.as_dict(),
            "future_skew": self.future_skew.as_dict(),
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.as_dict())

    @property
    def canonical_text(self) -> str:
        return canonical_json_text(self.as_dict())


def require_active_chronology_readiness(
    *,
    chronology_reference: ChronologyReference,
    source_scope: AuthorityScope,
    source_contract: str,
    evaluation_cadence: EvaluationCadenceConfiguration,
    allowed_lateness: AllowedLatenessConfiguration,
    future_skew: FutureSkewConfiguration,
) -> ChronologyReadinessBinding:
    """Create an explicit assertion that fails closed on unresolved policy."""

    return ChronologyReadinessBinding(
        chronology_reference=chronology_reference,
        source_scope=source_scope,
        source_contract=source_contract,
        active_readiness_asserted=True,
        evaluation_cadence=evaluation_cadence,
        allowed_lateness=allowed_lateness,
        future_skew=future_skew,
    )


__all__ = [
    "CHRONOLOGY_READINESS_CONFIGURATION_CONTRACT",
    "CHRONOLOGY_READINESS_BINDING_CONTRACT",
    "CHRONOLOGY_REFERENCE_CONTRACT",
    "ChronologyDisposition",
    "ChronologyExecutionMode",
    "ChronologyLifecycleState",
    "ChronologyReadinessBinding",
    "ChronologyReference",
    "LearningFinalizationState",
    "chronology_readiness_configuration_identity",
    "require_active_chronology_readiness",
]
