"""Finding-specific versioned L0–L4 evaluation without lifecycle or authority effects."""
from itertools import combinations
from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from app.governance.characterization import TrajectoryCharacterization
from app.governance.context import ContextBasis, ContextQualification, qualify_context
from app.governance.tiers import usable_lineage
from app.governance.contracts import ContentRecord, Contract, MaturityLevel, Text, Timestamp
from app.governance.dependencies import DependencyGraph, IndependenceResult, evaluate_independence


class PersistenceGate(Contract):
    requirement_id: Text
    requirement_version: Text
    basis: Literal["fixed_observations", "elapsed_time"]
    satisfied: StrictBool
    evidence_ids: Annotated[tuple[Text, ...], Field(min_length=1)]
    reasons: Annotated[tuple[Text, ...], Field(min_length=1)]


class PersistenceAssessment(Contract):
    """Explicit applicable gate results, supplied by a finding-scoped adapter.

    No gates means persistence is unknown. All applicable gates must pass.
    Raw analytical scores are deliberately not interpreted here.
    """
    finding_id: Text
    gates: tuple[PersistenceGate, ...]


class MaturityEvaluation(ContentRecord):
    identity_field = "evaluation_id"
    identity_kind = "maturity-evaluation"
    schema_version: Literal["evidence-maturity-v1"] = "evidence-maturity-v1"
    evaluation_id: str = ""
    finding_id: Text
    system_scope: Text
    evaluated_at: Timestamp
    source_run_id: Text
    policy_id: Literal["evidence-maturity-v1"] = "evidence-maturity-v1"
    policy_version: Literal["1"] = "1"
    level: MaturityLevel
    relevant_evidence_ids: tuple[Text, ...]
    supporting_evidence_ids: tuple[Text, ...]
    dependency_graph_snapshot_id: Text
    persistence: PersistenceAssessment
    pair_evaluations: tuple[IndependenceResult, ...]
    reasons: tuple[Text, ...]

    @model_validator(mode="after")
    def supported_schema_level(self):
        if self.schema_version == "evidence-maturity-v1" and self.level in {MaturityLevel.L3, MaturityLevel.L4}:
            raise ValueError("v1_maturity_supports_only_L0_L2")
        return self


def evaluate_maturity(
    *, finding_id: str, relevant_evidence_ids: tuple[str, ...], graph: DependencyGraph,
    persistence: PersistenceAssessment, evaluated_at: str, source_run_id: str,
) -> MaturityEvaluation:
    graph = DependencyGraph.model_validate(graph.as_dict())
    persistence = PersistenceAssessment.model_validate(persistence.as_dict())
    ids = tuple(sorted(set(relevant_evidence_ids)))
    available = {item.evidence_id for item in graph.evidence}
    if not ids or not set(ids) <= available:
        raise ValueError("relevant_evidence_required_for_L0")
    graph.validate_available_at(evaluated_at)
    if finding_id != persistence.finding_id:
        raise ValueError("persistence_finding_mismatch")
    if len({gate.requirement_id for gate in persistence.gates}) != len(persistence.gates):
        raise ValueError("duplicate_persistence_requirement")
    for gate in persistence.gates:
        if not set(gate.evidence_ids) <= set(ids):
            raise ValueError("persistence_support_outside_finding_evidence")
    persistent = bool(persistence.gates) and all(gate.satisfied for gate in persistence.gates)
    pairs = tuple(evaluate_independence(graph, left, right) for left, right in combinations(ids, 2))
    persistent_ids = {item for gate in persistence.gates if gate.satisfied for item in gate.evidence_ids}
    # A corroborating pair must include evidence supporting persistence;
    # unrelated independent extras cannot elevate a third, persistent object.
    qualifying = tuple(pair for pair in pairs if pair.independent and persistent_ids.intersection(pair.evidence_ids))
    level = MaturityLevel.L0
    supporting = set(ids)
    reasons = ["persistence_not_established"]
    if persistent:
        level = MaturityLevel.L2 if qualifying else MaturityLevel.L1
        supporting = persistent_ids | {item for pair in qualifying for item in pair.evidence_ids}
        reasons = ["all_applicable_persistence_gates_satisfied",
                   "independent_corroboration_established" if qualifying else "no_independent_corroboration_of_persistent_evidence"]
    return MaturityEvaluation(
        finding_id=finding_id, system_scope=graph.system_scope,
        evaluated_at=evaluated_at, source_run_id=source_run_id, level=level,
        relevant_evidence_ids=ids, supporting_evidence_ids=tuple(sorted(supporting)),
        dependency_graph_snapshot_id=graph.snapshot_id, persistence=persistence,
        pair_evaluations=pairs, reasons=tuple(reasons),
    )


# Separate record schema preserves the exact v1 content hashes and replay path.


class MaturityEvaluationV2(MaturityEvaluation):
    schema_version: Literal["evidence-maturity-v2"] = "evidence-maturity-v2"
    policy_id: Literal["evidence-maturity-v2"] = "evidence-maturity-v2"
    policy_version: Literal["2"] = "2"
    trajectory: TrajectoryCharacterization | None = None
    context_basis: ContextBasis | None = None
    context_qualification: ContextQualification | None = None


def _available_maturity_support(base, graph):
    level, reasons = base.level, list(base.reasons)
    usable_ids = {item.evidence_id for item in graph.evidence if usable_lineage(graph, item.evidence_id)
                  and (item.evidence_family.value != "trend" or (item.payload or {}).get("status") == "available")}
    persistent_ids = {identifier for gate in base.persistence.gates if gate.satisfied for identifier in gate.evidence_ids}
    if level != MaturityLevel.L0 and not persistent_ids <= usable_ids:
        level = MaturityLevel.L0
        reasons.append("persistence_support_unavailable")
    elif level == MaturityLevel.L2 and not any(pair.independent and set(pair.evidence_ids) <= usable_ids
            and persistent_ids.intersection(pair.evidence_ids) for pair in base.pair_evaluations):
        level = MaturityLevel.L1
        reasons.append("corroborating_support_unavailable")
    if level in {MaturityLevel.L0, MaturityLevel.L1} and base.level == MaturityLevel.L2:
        reasons.remove("independent_corroboration_established")
    return level, reasons, usable_ids


def _validate_current_maturity_context(base, context_basis):
    if context_basis.system_scope != base.system_scope or context_basis.evaluated_at != base.evaluated_at:
        raise ValueError("maturity_context_basis_mismatch")
    # Maturity v2 qualifies current anchors, not expired historical references.
    if context_basis.relevant_at != base.evaluated_at:
        raise ValueError("maturity_requires_current_context")


def evaluate_maturity_v2(*, trajectory: TrajectoryCharacterization | None = None,
                         context_basis: ContextBasis | None = None, **kwargs) -> MaturityEvaluationV2:
    base = evaluate_maturity(**kwargs)
    qualification = None
    graph = kwargs["graph"]
    level, reasons, usable_ids = _available_maturity_support(base, graph)
    if trajectory is not None:
        trajectory = TrajectoryCharacterization.model_validate(trajectory.as_dict())
        supported = trajectory.validate_support(kwargs["graph"], base.finding_id, base.relevant_evidence_ids,
                                                 tuple(sorted(set(base.supporting_evidence_ids) & usable_ids)), base.evaluated_at)
        supported = supported and set(trajectory.evidence_ids) <= usable_ids
        if level == MaturityLevel.L2 and supported:
            level = MaturityLevel.L3
            reasons.append("supported_trajectory_characterization")
        else:
            reasons.append("trajectory_insufficient_or_indeterminate")
    if context_basis is not None:
        context_basis = ContextBasis.model_validate(context_basis.as_dict())
        _validate_current_maturity_context(base, context_basis)
        qualification = qualify_context(context_basis)
        if level == MaturityLevel.L3 and qualification.applicable_context_ids:
            level = MaturityLevel.L4
            reasons.append("verified_external_context_qualification")
        else:
            reasons.append("context_insufficient_or_L3_unavailable")
    body = base.as_dict()
    body.update(evaluation_id="", schema_version="evidence-maturity-v2", policy_id="evidence-maturity-v2",
                policy_version="2", level=level, reasons=reasons, trajectory=trajectory,
                supporting_evidence_ids=tuple(sorted(set(base.supporting_evidence_ids) & usable_ids)),
                context_basis=context_basis, context_qualification=qualification)
    return MaturityEvaluationV2.model_validate(body)


def replay_maturity(maturity, graph):
    kwargs = {"finding_id": maturity.finding_id, "relevant_evidence_ids": maturity.relevant_evidence_ids,
              "graph": graph, "persistence": maturity.persistence, "evaluated_at": maturity.evaluated_at,
              "source_run_id": maturity.source_run_id}
    if isinstance(maturity, MaturityEvaluationV2):
        return evaluate_maturity_v2(trajectory=maturity.trajectory, context_basis=maturity.context_basis, **kwargs)
    return evaluate_maturity(**kwargs)
