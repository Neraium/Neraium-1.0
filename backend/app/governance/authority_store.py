"""Application-level append-only authority history using runtime ledger storage.

Recording an outcome never executes the requested operation. The store retains
the exact basis atomically with each decision, including superseded decisions.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime
from threading import RLock
from typing import Any, Callable, Literal

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.governance.contracts import (
    AuditSnapshot, AuthorityDecision, Contract, FindingLifecycleEvent, Text, content_id,
)
from app.governance.context import ContextBasis
from app.governance.policy import AuthorityPolicy, PolicyEvaluation, evaluate_policy
from app.governance.dependencies import DependencyGraph
from app.governance.maturity import MaturityEvaluation, MaturityEvaluationV2, replay_maturity, evaluate_maturity


class AuthorityRecordConflict(ValueError):
    pass


class AuthorityStorageUnavailable(RuntimeError):
    pass


class DecisionBasis(Contract):
    schema_version: Literal["authority-decision-basis-v1"] = "authority-decision-basis-v1"
    graph: DependencyGraph
    maturity: MaturityEvaluation | MaturityEvaluationV2
    lifecycle: FindingLifecycleEvent
    snapshots: tuple[AuditSnapshot, ...]

    def validate_for(self, decision: AuthorityDecision) -> None:
        graph = self.graph
        maturity = self.maturity
        snapshots = {item.snapshot_id: item for item in self.snapshots}
        if len(snapshots) != len(self.snapshots):
            raise ValueError("duplicate_audit_snapshot")
        if any(item.system_scope != decision.system_scope for item in (*self.snapshots, graph, maturity)):
            raise ValueError("decision_basis_system_scope_mismatch")
        if graph.snapshot_id != decision.dependency_graph_snapshot_id:
            raise ValueError("decision_graph_snapshot_mismatch")
        ids = {item.evidence_id for item in graph.evidence}
        if not set((*decision.evidence_snapshot_ids, *decision.limiting_evidence, *decision.contradicting_evidence)) <= ids:
            raise ValueError("decision_evidence_snapshot_missing")
        if maturity.evaluation_id != decision.maturity_snapshot_id or maturity.finding_id != decision.finding_id:
            raise ValueError("decision_maturity_snapshot_mismatch")
        if maturity.level != decision.maturity_at_decision or set(maturity.relevant_evidence_ids) != set(decision.evidence_snapshot_ids):
            raise ValueError("decision_maturity_evidence_mismatch")
        # Validate the historical boundary independently of evaluator replay,
        # including imported evaluations with valid content IDs.
        graph.validate_available_at(maturity.evaluated_at)
        replay = (replay_maturity(maturity, graph) if isinstance(maturity, MaturityEvaluationV2) else evaluate_maturity(
            finding_id=maturity.finding_id, relevant_evidence_ids=maturity.relevant_evidence_ids,
            graph=graph, persistence=maturity.persistence, evaluated_at=maturity.evaluated_at,
            source_run_id=maturity.source_run_id,
        ))
        if replay != maturity:
            raise ValueError("maturity_replay_mismatch")
        if (self.lifecycle.event_id != decision.lifecycle_event_id
                or self.lifecycle.finding_id != decision.finding_id
                or self.lifecycle.state != decision.lifecycle_state_at_decision):
            raise ValueError("decision_lifecycle_snapshot_mismatch")
        if not set(self.lifecycle.evidence_ids) <= ids:
            raise ValueError("lifecycle_evidence_snapshot_missing")
        if datetime.fromisoformat(self.lifecycle.effective_at) > datetime.fromisoformat(decision.decision_timestamp):
            raise ValueError("decision_lifecycle_not_yet_effective")
        for reference, kind in (
            (decision.policy_snapshot_id, "policy"), (decision.context_snapshot_id, "context"),
            (decision.active_model_before, "model"), (decision.candidate_model, "model"),
            (decision.active_model_after, "model"),
        ):
            if reference is None:
                continue
            if reference not in snapshots or snapshots[reference].kind != kind:
                raise ValueError(f"decision_{kind}_snapshot_missing:{reference}")
        for evidence in graph.evidence:
            for reference in evidence.context_refs:
                if reference not in snapshots or snapshots[reference].kind != "context":
                    raise ValueError(f"evidence_context_snapshot_missing:{reference}")
        policy = snapshots[decision.policy_snapshot_id]
        if (policy.object_id, policy.version) != (decision.policy_id, decision.policy_version):
            raise ValueError("decision_policy_version_mismatch")
        known_times = [item.created_at for item in (*self.snapshots, *graph.evidence)]
        known_times.extend(
            item.source_window.ended_at for item in (*graph.evidence, *graph.observations)
            if item.source_window.ended_at is not None
        )
        known_times.extend((maturity.evaluated_at, self.lifecycle.recorded_at))
        if decision.human_review.reviewed_at:
            known_times.append(decision.human_review.reviewed_at)
        if any(datetime.fromisoformat(value) > datetime.fromisoformat(decision.decision_timestamp) for value in known_times):
            raise ValueError("decision_basis_contains_later_knowledge")


def _basis_objects(basis: dict) -> dict[str, dict]:
    """Preserve identity binding even for externally assigned observation/event IDs."""
    objects: dict[str, dict] = {}
    entries = [("snapshot_id", item) for item in basis["snapshots"]]
    entries.extend(("evidence_id", item) for item in basis["graph"]["evidence"])
    entries.extend(("observation_id", item) for item in basis["graph"]["observations"])
    entries.extend((("snapshot_id", basis["graph"]), ("evaluation_id", basis["maturity"]),
                    ("event_id", basis["lifecycle"])))
    if basis.get("schema_version") == "authority-decision-basis-v2":
        entries.extend((("policy_record_id", basis["policy"]), ("evaluation_id", basis["policy_evaluation"])))
        entries.extend(("context_id", item) for item in basis["context"]["records"])
    for field, item in entries:
        identifier = item[field]
        if identifier in objects and objects[identifier] != item:
            raise AuthorityRecordConflict(f"immutable_basis_identity_conflict:{identifier}")
        objects[identifier] = item
    return objects


class AuthorityDecisionStore(ABC):
    """Scope is authenticated server context, passed separately from record data."""

    @abstractmethod
    def _read(self, key: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def _mutate(self, key: str, update: Callable[[Any], dict]) -> dict:
        raise NotImplementedError

    @staticmethod
    def _key(scope: AuthenticatedPhase4Scope, system_scope: str) -> str:
        if not isinstance(scope, AuthenticatedPhase4Scope):
            raise ValueError("authenticated_scope_required")
        if not isinstance(system_scope, str) or not system_scope.strip():
            raise ValueError("system_scope_required")
        return f"evidence_governance_ledger_v1::{scope.scope_digest}::{content_id('system', system_scope)}"

    @staticmethod
    def _ledger(raw: Any, scope: AuthenticatedPhase4Scope, system_scope: str) -> dict:
        if raw is None:
            return {"schema_version": "authority-ledger-v1", "authenticated_scope": scope.as_dict(),
                    "system_scope": system_scope, "records": []}
        if (not isinstance(raw, dict) or raw.get("schema_version") != "authority-ledger-v1"
                or raw.get("authenticated_scope") != scope.as_dict() or raw.get("system_scope") != system_scope
                or not isinstance(raw.get("records"), list)):
            raise ValueError("authority_ledger_scope_or_schema_mismatch")
        return deepcopy(raw)

    def append_decision(self, scope: AuthenticatedPhase4Scope, decision: AuthorityDecision, basis: DecisionBasis) -> AuthorityDecision:
        # Revalidate defensive serialized copies, including nested payload IDs.
        decision = parse_decision(decision.as_dict())
        basis = parse_basis(basis.as_dict())
        if isinstance(decision, AuthorityDecisionV2) != isinstance(basis, DecisionBasisV2):
            raise ValueError("decision_basis_schema_mismatch")
        basis.validate_for(decision)
        key = self._key(scope, decision.system_scope)

        def update(raw: Any) -> dict:
            ledger = self._ledger(raw, scope, decision.system_scope)
            records = ledger["records"]
            candidate = {"decision": decision.as_dict(), "basis": basis.as_dict()}
            existing = next((item for item in records if item["decision"]["decision_id"] == decision.decision_id), None)
            if existing is not None:
                if existing != candidate:
                    raise AuthorityRecordConflict("immutable_decision_conflict")
                return ledger
            candidate_objects = _basis_objects(candidate["basis"])
            for prior in records:
                prior_objects = _basis_objects(prior["basis"])
                for identifier in prior_objects.keys() & candidate_objects.keys():
                    if prior_objects[identifier] != candidate_objects[identifier]:
                        raise AuthorityRecordConflict(f"immutable_basis_identity_conflict:{identifier}")
            previous_id = decision.supersedes_decision_id
            if previous_id:
                previous = next((item["decision"] for item in records if item["decision"]["decision_id"] == previous_id), None)
                if previous is None:
                    raise AuthorityRecordConflict("superseded_decision_missing")
                if (previous["finding_id"], previous["requested_operation"]) != (decision.finding_id, decision.requested_operation):
                    raise AuthorityRecordConflict("supersession_finding_or_operation_mismatch")
                if datetime.fromisoformat(decision.decision_timestamp) < datetime.fromisoformat(previous["decision_timestamp"]):
                    raise AuthorityRecordConflict("supersession_precedes_predecessor_decision")
                if any(item["decision"]["supersedes_decision_id"] == previous_id for item in records):
                    raise AuthorityRecordConflict("superseded_decision_already_has_successor")
            records.append(candidate)
            return ledger

        self._mutate(key, update)
        return parse_decision(decision.as_dict())

    def history(self, scope: AuthenticatedPhase4Scope, system_scope: str, *, finding_id: str | None = None) -> list[AuthorityDecision]:
        """Ordered by atomic append sequence, independent of effective time."""
        key = self._key(scope, system_scope)
        ledger = self._ledger(self._read(key), scope, system_scope)
        return [parse_decision(item["decision"]) for item in ledger["records"]
                if finding_id is None or item["decision"]["finding_id"] == finding_id]

    def get_record(self, scope: AuthenticatedPhase4Scope, system_scope: str, decision_id: str) -> dict | None:
        key = self._key(scope, system_scope)
        ledger = self._ledger(self._read(key), scope, system_scope)
        return next((deepcopy(item) for item in ledger["records"] if item["decision"]["decision_id"] == decision_id), None)


class InMemoryAuthorityDecisionStore(AuthorityDecisionStore):
    def __init__(self) -> None:
        self._lock = RLock()
        self._state: dict[str, dict] = {}

    def _read(self, key: str) -> Any:
        with self._lock:
            return deepcopy(self._state.get(key))

    def _mutate(self, key: str, update: Callable[[Any], dict]) -> dict:
        with self._lock:
            result = update(deepcopy(self._state.get(key)))
            self._state[key] = deepcopy(result)
            return deepcopy(result)


class RuntimeAuthorityDecisionStore(AuthorityDecisionStore):
    """No cache or non-atomic fallback; repository transactions serialize writers."""
    def _read(self, key: str) -> Any:
        from app.services.runtime_db import read_latest_payload
        try:
            return read_latest_payload(key)
        except Exception as exc:
            raise AuthorityStorageUnavailable("authority_ledger_read_failed") from exc

    def _mutate(self, key: str, update: Callable[[Any], dict]) -> dict:
        from app.services.runtime_db import mutate_latest_payload
        try:
            return mutate_latest_payload(key, update)
        except ValueError:
            raise
        except Exception as exc:
            raise AuthorityStorageUnavailable("authority_ledger_append_failed") from exc


# v2 requires evaluator replay; legacy v1 remains an inert historical record.


class AuthorityDecisionV2(AuthorityDecision):
    schema_version: Literal["authority-decision-v2"] = "authority-decision-v2"
    policy_evaluation_id: Text
    tier_classification: Literal["tier_a", "tier_b", "unclassified"] | None
    execution_authorized: Literal[False] = False


class DecisionBasisV2(DecisionBasis):
    schema_version: Literal["authority-decision-basis-v2"] = "authority-decision-basis-v2"
    context: ContextBasis
    policy: AuthorityPolicy
    policy_evaluation: PolicyEvaluation

    def validate_for(self, decision: AuthorityDecision) -> None:
        if not isinstance(decision, AuthorityDecisionV2):
            raise ValueError("phase2_decision_schema_required")
        super().validate_for(decision)
        snapshots = {item.snapshot_id: item for item in self.snapshots}
        if snapshots[decision.context_snapshot_id].payload != self.context.as_dict():
            raise ValueError("decision_context_contents_mismatch")
        if snapshots[decision.policy_snapshot_id].payload != self.policy.as_dict():
            raise ValueError("decision_policy_contents_mismatch")
        if (self.policy.policy_id, str(self.policy.policy_version)) != (decision.policy_id, decision.policy_version):
            raise ValueError("decision_policy_contract_mismatch")
        if self.context.evaluated_at != decision.decision_timestamp or self.context.relevant_at != decision.decision_timestamp:
            raise ValueError("decision_context_timestamp_mismatch")
        if isinstance(self.maturity, MaturityEvaluationV2) and self.maturity.context_basis:
            original = self.maturity.context_basis
            if not {item.context_id for item in original.records} <= {item.context_id for item in self.context.records}:
                raise ValueError("decision_context_omits_maturity_history")
        replay = evaluate_policy(policy=self.policy, graph=self.graph, maturity=self.maturity,
            lifecycle_state=self.lifecycle.state, context=self.context, requested_operation=decision.requested_operation,
            evaluated_at=decision.decision_timestamp)
        if replay != self.policy_evaluation or decision.policy_evaluation_id != replay.evaluation_id:
            raise ValueError("policy_replay_mismatch")
        tier = replay.classification.tier if replay.classification else None
        if (decision.decision_outcome != replay.outcome or decision.decision_reasons != replay.reasons
                or decision.limiting_evidence != replay.limiting_evidence or decision.tier_classification != tier
                or decision.contradicting_evidence != replay.contradicting_evidence):
            raise ValueError("decision_policy_result_mismatch")
        if decision.active_model_before is None:
            raise ValueError("phase2_active_model_basis_required")
        model = snapshots[decision.active_model_before]
        if any(not isinstance(model.payload.get(key), str) or not model.payload[key].strip()
               for key in ("model_ref", "baseline_ref")):
            raise ValueError("phase2_immutable_model_and_baseline_refs_required")
        if decision.active_model_after != decision.active_model_before:
            raise ValueError("phase2_model_transition_inactive")
        required = replay.outcome.value == "human_review_required"
        if decision.human_review.as_dict() != {"required": required, "status": "pending" if required else "not_required",
            "reviewer_identity": None, "reviewed_at": None, "rationale": None}:
            raise ValueError("phase2_review_completion_inactive")


def parse_decision(raw):
    cls = AuthorityDecisionV2 if raw.get("schema_version") == "authority-decision-v2" else AuthorityDecision
    return cls.model_validate(raw)


def parse_basis(raw):
    cls = DecisionBasisV2 if raw.get("schema_version") == "authority-decision-basis-v2" else DecisionBasis
    result = cls.model_validate(raw)
    if not isinstance(result, DecisionBasisV2) and isinstance(result.maturity, MaturityEvaluationV2):
        raise ValueError("phase2_basis_schema_required")
    return result


def create_policy_decision(*, graph, maturity, lifecycle, context, policy,
                           requested_operation, decision_timestamp, source_run_id,
                           active_model, candidate_model=None, supersedes_decision_id=None):
    """Build an evaluable, non-executing decision and its complete frozen basis.

    active_model is an immutable audit snapshot containing model/baseline refs.
    No live model is loaded, changed or saved by this function.
    """
    evaluation = evaluate_policy(policy=policy, graph=graph, maturity=maturity, lifecycle_state=lifecycle.state,
        context=context, requested_operation=requested_operation, evaluated_at=decision_timestamp)
    policy_snapshot = AuditSnapshot(kind="policy", object_id=policy.policy_id, version=str(policy.policy_version),
        system_scope=graph.system_scope, created_at=policy.created_at, provenance=policy.provenance, payload=policy.as_dict())
    context_snapshot = AuditSnapshot(kind="context", object_id="context-basis", version="1", system_scope=graph.system_scope,
        created_at=context.evaluated_at, provenance=context.facts_provenance, payload=context.as_dict())
    snapshots = (policy_snapshot, context_snapshot, active_model) + ((candidate_model,) if candidate_model else ())
    required = evaluation.outcome.value == "human_review_required"
    decision = AuthorityDecisionV2(finding_id=maturity.finding_id, system_scope=graph.system_scope,
        decision_timestamp=decision_timestamp, effective_timestamp=decision_timestamp,
        policy_id=policy.policy_id, policy_version=str(policy.policy_version), policy_snapshot_id=policy_snapshot.snapshot_id,
        evidence_snapshot_ids=maturity.relevant_evidence_ids, context_snapshot_id=context_snapshot.snapshot_id,
        dependency_graph_snapshot_id=graph.snapshot_id, maturity_at_decision=maturity.level,
        maturity_snapshot_id=maturity.evaluation_id, lifecycle_state_at_decision=lifecycle.state, lifecycle_event_id=lifecycle.event_id,
        requested_operation=requested_operation, decision_outcome=evaluation.outcome, decision_reasons=evaluation.reasons,
        limiting_evidence=evaluation.limiting_evidence, contradicting_evidence=evaluation.contradicting_evidence,
        active_model_before=active_model.snapshot_id,
        candidate_model=candidate_model.snapshot_id if candidate_model else None, active_model_after=active_model.snapshot_id,
        human_review={"required": required, "status": "pending" if required else "not_required"},
        supersedes_decision_id=supersedes_decision_id, source_run_id=source_run_id,
        policy_evaluation_id=evaluation.evaluation_id,
        tier_classification=evaluation.classification.tier if evaluation.classification else None)
    basis = DecisionBasisV2(graph=graph, maturity=maturity, lifecycle=lifecycle, snapshots=snapshots,
                           context=context, policy=policy, policy_evaluation=evaluation)
    basis.validate_for(decision)
    # Return detached, validated copies, even when callers mutate nested JSON.
    return parse_decision(decision.as_dict()), parse_basis(basis.as_dict())
