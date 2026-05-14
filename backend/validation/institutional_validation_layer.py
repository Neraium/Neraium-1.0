from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class InstitutionalValidationReport:
    validation_dataset: str
    replay_integrity: str
    evidence_lineage_completeness: str
    topology_divergence_timing: Any
    propagation_visibility_timing: Any
    auditability_coverage: str
    operator_explanation_consistency: str
    domain_certification_readiness: str
    ontology_coverage: str
    validation_gaps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InstitutionalValidationLayer:
    def build(
        self,
        *,
        intelligence: dict[str, Any],
        validation: dict[str, Any],
        trust: dict[str, Any],
    ) -> dict[str, Any]:
        vr = validation.get("validation_report", {})
        lineage = intelligence.get("evidence_lineage", {}).get("lineages", [])
        ontology = intelligence.get("structural_ontology", {}).get("archetype_nodes", [])
        report = InstitutionalValidationReport(
            validation_dataset=intelligence.get("structural_progression_dataset", {}).get("dataset_id", "dataset-unavailable"),
            replay_integrity=vr.get("replay_consistency", "MODERATE"),
            evidence_lineage_completeness="HIGH" if len(lineage) >= 4 else "MODERATE" if len(lineage) >= 2 else "LOW",
            topology_divergence_timing=vr.get("structural_visibility_timing", {}).get("first_topology_divergence_frame"),
            propagation_visibility_timing=vr.get("structural_visibility_timing", {}).get("first_propagation_visibility_frame"),
            auditability_coverage="HIGH" if int(intelligence.get("operational_audit", {}).get("audit_record", {}).get("replay_reference_count", 0)) >= 12 else "MODERATE",
            operator_explanation_consistency=trust.get("trust_factors", {}).get("explanation_consistency", "MODERATE"),
            domain_certification_readiness=certification_readiness(intelligence),
            ontology_coverage="HIGH" if len(ontology) >= 8 else "MODERATE",
            validation_gaps=validation_gaps(vr, lineage),
        )
        return {
            "institutional_validation_report": report.to_dict(),
            "validation_posture": "defensible" if not report.validation_gaps else "developing",
        }


def certification_readiness(intelligence: dict[str, Any]) -> str:
    packs = intelligence.get("industry_certification_packs", {}).get("certification_packs", [])
    if len(packs) >= 5:
        return "READY_FOR_REVIEW"
    if packs:
        return "PARTIAL_READINESS"
    return "NOT_READY"


def validation_gaps(validation_report: dict[str, Any], lineage: list[dict[str, Any]]) -> list[str]:
    gaps = []
    if validation_report.get("evidence_integrity") == "LOW":
        gaps.append("increase evidence lineage completeness")
    if validation_report.get("replay_consistency") == "LOW":
        gaps.append("improve canonical replay phase continuity")
    if len(lineage) < 2:
        gaps.append("insufficient lineage targets for institutional review")
    return gaps

