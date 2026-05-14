from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SharedStructuralPrimitive:
    primitive: str
    domains: list[str]
    caution: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DomainTransferEvidence:
    source_domain: str
    target_domain: str
    evidence_overlap: list[str]
    transfer_caution_level: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CrossDomainStructuralMatch:
    source_pattern: str
    target_pattern: str
    topology_similarity: str
    convergence_similarity: str
    transfer_caution_level: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CrossDomainSimilarityReport:
    shared_archetypes: list[str]
    shared_propagation_motifs: list[str]
    matches: list[dict[str, Any]]
    transfer_evidence: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CrossDomainIntelligenceEngine:
    def build_report(self, intelligence: dict[str, Any]) -> dict[str, Any]:
        archetypes = [item.get("name", "") for item in intelligence.get("active_archetypes", [])]
        pathways = intelligence.get("causality_graph", {}).get("dominant_pathways", [])
        matches = [
            CrossDomainStructuralMatch(
                source_pattern=pathways[0] if pathways else "airflow_thermal_lag",
                target_pattern="cooling_loop_fragmentation",
                topology_similarity="high_structural_similarity",
                convergence_similarity="moderate_recovery_alignment",
                transfer_caution_level="domain_context_required",
            ).to_dict()
        ]
        transfer = [
            DomainTransferEvidence(
                source_domain="cultivation",
                target_domain="data_center",
                evidence_overlap=["propagation_acceleration", "response_lag", "compensation_masking"],
                transfer_caution_level="use_structural_similarity_not_failure_equivalence",
            ).to_dict()
        ]
        report = CrossDomainSimilarityReport(
            shared_archetypes=archetypes[:6],
            shared_propagation_motifs=pathways[:6],
            matches=matches,
            transfer_evidence=transfer,
        )
        return report.to_dict()

