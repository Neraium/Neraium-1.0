"""Finding-scoped trajectory assertions with conservative support requirements."""
from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.governance.contracts import Contract, EvidenceFamily, SourceWindow, Text, Timestamp
from app.governance.dependencies import DependencyGraph, evaluate_independence
from app.governance.registry import time


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
        from itertools import combinations
        supported = any(evaluate_independence(graph, a, b).independent and {a, b} <= set(supporting_ids)
                        for a, b in combinations(sorted(set(self.evidence_ids)), 2))
        # An unavailable/limited trend cannot masquerade as characterization support.
        usable = all(nodes[item].evidence_family != EvidenceFamily.TREND or (
            nodes[item].payload is not None and nodes[item].payload.get("status") == "available"
        ) for item in self.evidence_ids)
        return supported and usable and self.trajectory != "indeterminate"
