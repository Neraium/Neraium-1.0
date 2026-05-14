from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ExplainabilityRequirement:
    requirement: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExplainabilityAssessment:
    explainability_completeness: str
    missing_evidence: list[str]
    traceability_gaps: list[str]
    replay_support_level: str
    operator_clarity_level: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExplainabilityStandard:
    requirements: list[dict[str, Any]]
    assessment: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_explainability_standard(intelligence: dict[str, Any]) -> dict[str, Any]:
    requirements = [
        ExplainabilityRequirement("replay_explainability", "Every cognition output maps to replay frames."),
        ExplainabilityRequirement("evidence_sufficiency", "Every conclusion includes corroborating evidence lineage."),
        ExplainabilityRequirement("ontology_traceability", "Archetype and primitive usage is traceable."),
        ExplainabilityRequirement("propagation_transparency", "Propagation pathways are inspectable."),
        ExplainabilityRequirement("uncertainty_disclosure", "Non-deterministic uncertainty is explicitly disclosed."),
    ]
    lineage_count = len(intelligence.get("evidence_lineage", {}).get("lineages", []))
    replay_count = len(intelligence.get("replay_timeline", {}).get("timeline", []))
    assessment = ExplainabilityAssessment(
        explainability_completeness="HIGH" if lineage_count >= 3 and replay_count >= 6 else "MODERATE",
        missing_evidence=[] if lineage_count >= 3 else ["additional_corroborating_lineages"],
        traceability_gaps=[] if intelligence.get("structural_ontology") else ["ontology_reference_gap"],
        replay_support_level="STRONG" if replay_count >= 6 else "DEVELOPING",
        operator_clarity_level="STRONG" if intelligence.get("operator_explanation_v2") else "DEVELOPING",
    )
    return ExplainabilityStandard(
        requirements=[item.to_dict() for item in requirements],
        assessment=assessment.to_dict(),
    ).to_dict()

