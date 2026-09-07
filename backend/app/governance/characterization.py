"""Finding-scoped trajectory assertions with conservative support requirements."""
from typing import Annotated, Literal

from pydantic import Field, StrictFloat, field_validator

from app.governance.contracts import Contract, EvidenceFamily, SourceWindow, Text, Timestamp
from app.governance.dependencies import DependencyGraph, evaluate_independence
from app.governance.registry import time


class PropagationSupport(Contract):
    """Versioned timing/graph adapter assertion, never a selected cause."""
    method: Literal["timing_graph_propagation_v1"]
    path_signals: Annotated[tuple[Text, ...], Field(min_length=2)]
    observed_at: tuple[Timestamp, ...]
    relationship_refs: Annotated[tuple[Text, ...], Field(min_length=1)]
    expected_lag_windows_seconds: tuple[tuple[Annotated[StrictFloat, Field(ge=0)], Annotated[StrictFloat, Field(ge=0)]], ...]
    alternative_explanations: Annotated[tuple[Text, ...], Field(min_length=1)]
    limitations: Annotated[tuple[Text, ...], Field(min_length=1)]
    causal_claim: Literal[False]


def propagation_supported(evidence, horizon):
    try:
        support = PropagationSupport.model_validate((evidence.payload or {}).get("propagation_support"))
        if evidence.evidence_method != support.method or evidence.evidence_family != EvidenceFamily.MULTISCALE:
            return False
        count = len(support.path_signals)
        if (len(set(support.path_signals)) != count or len(support.observed_at) != count
                or len(support.relationship_refs) != count - 1
                or len(support.expected_lag_windows_seconds) != count - 1
                or not set(support.path_signals) <= set(evidence.source_signals)):
            return False
        instants = [time(value) for value in support.observed_at]
        if any(not time(horizon.started_at) <= instant <= time(horizon.ended_at)
               or not time(evidence.source_window.started_at) <= instant <= time(evidence.source_window.ended_at)
               for instant in instants):
            return False
        return all(lower <= (right - left).total_seconds() <= upper
                   for left, right, (lower, upper) in zip(instants, instants[1:], support.expected_lag_windows_seconds))
    except (ValueError, TypeError):
        return False


class TrajectoryCharacterization(Contract):
    trajectory: Literal["step_change", "gradual_drift", "oscillation", "recovery", "sustained_shift",
                        "propagation_candidate", "indeterminate"]
    finding_id: Text
    system_scope: Text
    evaluated_at: Timestamp
    evidence_ids: Annotated[tuple[Text, ...], Field(min_length=2)]
    evidence_families: Annotated[tuple[EvidenceFamily, ...], Field(min_length=2)]
    dependency_graph_snapshot_id: Text
    time_horizon: SourceWindow
    method: Text
    assumptions: Annotated[tuple[Text, ...], Field(min_length=1)]
    limitations: Annotated[tuple[Text, ...], Field(min_length=1)]

    @field_validator("evidence_ids", "evidence_families")
    @classmethod
    def ordered_set(cls, value):
        return tuple(sorted(set(value)))

    def validate_support(self, graph: DependencyGraph, finding_id: str, relevant_ids: tuple[str, ...],
                         supporting_ids: tuple[str, ...], evaluated_at: str) -> bool:
        if (self.finding_id != finding_id or self.system_scope != graph.system_scope
                or self.dependency_graph_snapshot_id != graph.snapshot_id):
            raise ValueError("trajectory_basis_mismatch")
        if (time(self.evaluated_at) > time(evaluated_at) or not self.time_horizon.ended_at
                or time(self.time_horizon.ended_at) > time(self.evaluated_at)):
            raise ValueError("trajectory_time_horizon_unavailable")
        graph.validate_available_at(self.evaluated_at)
        if not set(self.evidence_ids) <= set(relevant_ids):
            raise ValueError("trajectory_evidence_outside_finding")
        nodes = {item.evidence_id: item for item in graph.evidence}
        if set(self.evidence_families) != {nodes[item].evidence_family for item in self.evidence_ids}:
            raise ValueError("trajectory_family_mismatch")
        # Include material ancestors: relabeling a derived window cannot hide
        # disjoint raw observations. No cross-horizon reference contract exists.
        all_nodes = {item.observation_id: item for item in graph.observations} | nodes
        support_ids = set(self.evidence_ids)
        for identifier in self.evidence_ids:
            support_ids.update(graph.lineage(identifier))
        if any(not all_nodes[item].source_window.started_at or not all_nodes[item].source_window.ended_at
               or time(all_nodes[item].source_window.started_at) > time(self.time_horizon.ended_at)
               or time(all_nodes[item].source_window.ended_at) < time(self.time_horizon.started_at)
               for item in support_ids):
            return False
        # Propagation needs timing and graph support, with retained alternatives.
        if self.trajectory == "propagation_candidate" and not any(
            propagation_supported(nodes[item], self.time_horizon)
            for item in self.evidence_ids
        ):
            return False
        from itertools import combinations
        supported = any(evaluate_independence(graph, a, b).independent and {a, b} <= set(supporting_ids)
                        for a, b in combinations(sorted(set(self.evidence_ids)), 2))
        # An unavailable/limited trend cannot masquerade as characterization support.
        usable = all(nodes[item].evidence_family != EvidenceFamily.TREND or (
            nodes[item].payload is not None and nodes[item].payload.get("status") == "available"
        ) for item in self.evidence_ids)
        return supported and usable and self.trajectory != "indeterminate"
