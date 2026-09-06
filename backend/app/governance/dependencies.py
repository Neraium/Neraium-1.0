"""Conservative declared-lineage rules; no statistical independence claims."""
from __future__ import annotations

from graphlib import CycleError, TopologicalSorter
from typing import Literal, Self

from pydantic import StrictBool, field_validator, model_validator

from app.governance.contracts import (
    ContentRecord, Contract, EvidenceFamily, EvidenceObject, ObservationReference, Text,
)


def topological_order(upstream: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Reject dangling IDs and cycles; emit a deterministic upstream-first order."""
    for dependencies in upstream.values():
        missing = set(dependencies) - upstream.keys()
        if missing:
            raise ValueError(f"missing_dependency_ids:{sorted(missing)}")
    sorter = TopologicalSorter({key: tuple(sorted(value)) for key, value in sorted(upstream.items())})
    try:
        return tuple(sorter.static_order())
    except CycleError as exc:
        raise ValueError(f"dependency_cycle:{exc.args[1]}") from exc


class DependencyGraph(ContentRecord):
    identity_field = "snapshot_id"
    identity_kind = "dependency-graph"
    schema_version: Literal["evidence-dependency-graph-v1"] = "evidence-dependency-graph-v1"
    snapshot_id: str = ""
    system_scope: Text
    evidence: tuple[EvidenceObject, ...]
    observations: tuple[ObservationReference, ...]

    @field_validator("evidence")
    @classmethod
    def order_evidence(cls, value: tuple[EvidenceObject, ...]) -> tuple[EvidenceObject, ...]:
        return tuple(sorted(value, key=lambda item: item.evidence_id))

    @field_validator("observations")
    @classmethod
    def order_observations(cls, value: tuple[ObservationReference, ...]) -> tuple[ObservationReference, ...]:
        return tuple(sorted(value, key=lambda item: item.observation_id))

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        evidence_ids = {item.evidence_id for item in self.evidence}
        observation_ids = {item.observation_id for item in self.observations}
        if len(evidence_ids | observation_ids) != len(self.evidence) + len(self.observations):
            raise ValueError("duplicate_graph_node_id")
        for item in (*self.evidence, *self.observations):
            if item.system_scope != self.system_scope:
                raise ValueError("graph_system_scope_mismatch")
        for item in self.evidence:
            for ref in item.derived_from:
                ids = evidence_ids if ref.kind == "evidence" else observation_ids
                if ref.dependency_id not in ids:
                    raise ValueError(f"missing_or_wrong_kind_dependency:{ref.dependency_id}")
        topological_order(self.edges())
        return self

    def edges(self) -> dict[str, tuple[str, ...]]:
        return dict(sorted({
            **{item.observation_id: () for item in self.observations},
            **{item.evidence_id: tuple(ref.dependency_id for ref in item.derived_from) for item in self.evidence},
        }.items()))

    def upstream(self, node_id: str) -> tuple[str, ...]:
        return self.edges()[node_id]

    def lineage(self, node_id: str) -> tuple[str, ...]:
        edges = self.edges()
        pending = list(edges[node_id])
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current not in visited:
                visited.add(current)
                pending.extend(edges[current])
        return tuple(sorted(visited))

    def shared_upstream(self, left: str, right: str) -> tuple[str, ...]:
        # Include endpoints so ancestor/descendant pairs cannot corroborate.
        return tuple(sorted(({left, *self.lineage(left)}) & ({right, *self.lineage(right)})))


class IndependenceResult(Contract):
    evidence_ids: tuple[Text, Text]
    independent: StrictBool
    reasons: tuple[Text, ...]
    shared_dependency_ids: tuple[Text, ...]
    shared_source_ids: tuple[Text, ...]
    shared_window_ids: tuple[Text, ...]
    shared_signals: tuple[Text, ...]
    shared_context_ids: tuple[Text, ...]
    shared_assumptions: tuple[Text, ...]
    rule_version: Literal["declared-lineage-independence-v1"] = "declared-lineage-independence-v1"


def evaluate_independence(graph: DependencyGraph, left_id: str, right_id: str) -> IndependenceResult:
    graph = DependencyGraph.model_validate(graph.as_dict())
    evidence = {item.evidence_id: item for item in graph.evidence}
    observations = {item.observation_id: item for item in graph.observations}
    left, right = evidence[left_id], evidence[right_id]
    reasons: list[str] = []
    shared = graph.shared_upstream(left_id, right_id)

    def inputs(item: EvidenceObject) -> tuple[set[str], set[str], set[str], set[str], set[str], set[str], bool]:
        nodes = {item.evidence_id, *graph.lineage(item.evidence_id)}
        signals, sources, contexts, assumptions, covariance = set(), set(), set(), set(), set()
        windows: set[str] = set()
        complete = True
        for node in nodes:
            if node in evidence:
                parent = evidence[node]
                complete &= parent.lineage_complete and bool(parent.derived_from)
                contexts.update(parent.context_refs)
                assumptions.update(parent.assumption_set)
                if parent.evidence_family == EvidenceFamily.COVARIANCE_GEOMETRY or parent.covariance_source_id:
                    complete &= parent.covariance_source_id in nodes
                if parent.covariance_source_id:
                    covariance.add(parent.covariance_source_id)
            else:
                parent = observations[node]
                sources.add(parent.source_id)
            signals.update(parent.source_signals)
            windows.add(parent.source_window.window_id)
        return sources, signals, contexts, assumptions, covariance, windows, complete

    a, b = inputs(left), inputs(right)
    shared_sources, shared_signals, shared_contexts, shared_assumptions, shared_covariance, shared_windows = (
        tuple(sorted(a[index] & b[index])) for index in range(6)
    )
    if left_id == right_id:
        reasons.append("same_evidence_object")
    if left.evidence_family == right.evidence_family:
        reasons.append("same_evidence_family")
    if shared:
        reasons.append("shared_upstream_dependencies")
    if shared_covariance:
        reasons.append("shared_covariance_source")
    if shared_sources:
        reasons.append("shared_observation_source")
    if shared_windows:
        reasons.append("shared_source_window")
    if shared_signals:
        reasons.append("shared_source_signals")
    if shared_contexts:
        reasons.append("shared_context_dependencies")
    if shared_assumptions:
        reasons.append("shared_assumptions_not_established_independent")
    if not a[6] or not b[6]:
        reasons.append("incomplete_declared_lineage")
    return IndependenceResult(
        evidence_ids=tuple(sorted((left_id, right_id))), independent=not reasons,
        reasons=tuple(reasons or ["distinct_families_with_complete_disjoint_declared_inputs"]),
        shared_dependency_ids=tuple(sorted(set(shared) | set(shared_covariance))),
        shared_source_ids=shared_sources, shared_signals=shared_signals,
        shared_window_ids=shared_windows,
        shared_context_ids=shared_contexts, shared_assumptions=shared_assumptions,
    )
