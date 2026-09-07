"""Finding-specific L0–L2 evaluation; no authority or lifecycle side effects."""
from itertools import combinations
from typing import Annotated, Literal

from pydantic import Field, StrictBool

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
