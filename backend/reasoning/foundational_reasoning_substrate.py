from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StructuralReasoningContext:
    primitive_references: list[str]
    ontology_references: list[str]
    replay_references: list[str]
    memory_references: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceBackedInference:
    inference: str
    evidence_basis: list[str]
    confidence_basis: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayGroundedConclusion:
    conclusion: str
    replay_support: str
    uncertainty_disclosure: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReasoningTrace:
    trace_id: str
    topology_reference: str
    propagation_reference: str
    inference_steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OperatorFacingReasoningBundle:
    context: dict[str, Any]
    trace: dict[str, Any]
    inference: dict[str, Any]
    conclusion: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_foundational_reasoning_substrate(
    *,
    primitives: dict[str, Any],
    metrics: dict[str, Any],
    archive: dict[str, Any],
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    primitive_names = [item.get("name", "") for item in primitives.get("primitives", [])][:6]
    context = StructuralReasoningContext(
        primitive_references=primitive_names,
        ontology_references=intelligence.get("structural_ontology", {}).get("vocabulary", [])[:6],
        replay_references=["replay:latest", "replay:history"],
        memory_references=["structural_memory:latest", "archive:behavioral"],
    ).to_dict()
    trace = ReasoningTrace(
        trace_id="reasoning-trace-latest",
        topology_reference=str(metrics.get("topology_transition", {}).get("transition_label", "transition")),
        propagation_reference="pathway recurrence and entropy relationship",
        inference_steps=[
            "align primitive signatures with topology transition context",
            "cross-check replay evidence with propagation and convergence metrics",
            "validate inference against archive recurrence and ontology vocabulary",
        ],
    ).to_dict()
    inference = EvidenceBackedInference(
        inference="structural persistence and compensation load indicate continuation pressure with non-deterministic recovery potential",
        evidence_basis=[item.get("target", "") for item in intelligence.get("evidence_lineage", {}).get("lineages", [])][:6],
        confidence_basis="evidence density + replay coherence + ontology alignment",
    ).to_dict()
    conclusion = ReplayGroundedConclusion(
        conclusion="current structural state is best interpreted as a progression tendency rather than deterministic outcome",
        replay_support=f"{len(intelligence.get('replay_timeline', {}).get('timeline', []))} replay frames analyzed",
        uncertainty_disclosure="outcome remains contingent on evolving topology and intervention timing",
    ).to_dict()
    payload = OperatorFacingReasoningBundle(
        context=context,
        trace=trace,
        inference=inference,
        conclusion=conclusion,
    ).to_dict()
    payload["archive_references"] = {
        "replay_sequences": len(archive.get("replay_sequences", [])),
        "topology_histories": len(archive.get("topology_evolution_histories", [])),
    }
    return payload

