from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CognitionStateResponse:
    cognition_state: str
    confidence_tier: str
    continuity: str


@dataclass(frozen=True)
class TopologyStateResponse:
    topology_phase: str
    drift_index: float
    coherence_state: str


@dataclass(frozen=True)
class PropagationStateResponse:
    pathways: list[str]
    activation_intensity: float
    acceleration_state: str


@dataclass(frozen=True)
class EvidenceLineageResponse:
    lineage_targets: list[str]
    integrity: str
    completeness: str


@dataclass(frozen=True)
class ReplayFrameResponse:
    timestamp: str
    canonical_phase: str
    continuation_window: str


@dataclass(frozen=True)
class OntologyStateResponse:
    active_archetypes: list[str]
    primitives: list[str]
    ontology_coverage: str


@dataclass(frozen=True)
class ContinuationPathwayResponse:
    pathways: list[str]
    window: str
    coherence: str


@dataclass(frozen=True)
class AuditRecordResponse:
    audit_id: str
    replay_reference_count: int
    evidence_traceability: str


def build_cognition_contract_snapshot(intelligence: dict[str, Any]) -> dict[str, Any]:
    frame = (intelligence.get("replay_timeline", {}) or {}).get("timeline", [{}])[-1] if intelligence.get("replay_timeline") else {}
    cognition_state = CognitionStateResponse(
        cognition_state=str(intelligence.get("facility_state", "Monitoring")),
        confidence_tier=str(intelligence.get("cognition_confidence", {}).get("confidence_tier", "MODERATE_EVIDENCE")),
        continuity=str(intelligence.get("cognition_validation", {}).get("validation_report", {}).get("cognition_continuity_score", "MODERATE_CONTINUITY")),
    )
    topology_state = TopologyStateResponse(
        topology_phase=str(frame.get("topology_state", {}).get("phase", "stable_topology")),
        drift_index=float(frame.get("topology_state", {}).get("drift_index", 0.0)),
        coherence_state=str(frame.get("topology_state", {}).get("stability_state", "WATCH")),
    )
    propagation_state = PropagationStateResponse(
        pathways=frame.get("propagation_state", {}).get("dominant_paths", []),
        activation_intensity=float(frame.get("propagation_state", {}).get("activation_intensity", 0.0)),
        acceleration_state=str(frame.get("cognition_state", {}).get("operational_phase", "relationship_weakening")),
    )
    lineage = intelligence.get("evidence_lineage", {}).get("lineages", [])
    evidence_lineage = EvidenceLineageResponse(
        lineage_targets=[item.get("target", "") for item in lineage],
        integrity=str(intelligence.get("cognition_validation", {}).get("validation_report", {}).get("evidence_integrity", "MODERATE")),
        completeness="HIGH" if len(lineage) >= 3 else "MODERATE" if len(lineage) >= 1 else "LOW",
    )
    replay = ReplayFrameResponse(
        timestamp=str(frame.get("timestamp", "")),
        canonical_phase=str(frame.get("cognition_state", {}).get("canonical_phase", "stable_topology")),
        continuation_window=str(frame.get("continuation_window", {}).get("window", "Monitoring")),
    )
    ontology = OntologyStateResponse(
        active_archetypes=[item.get("name", "") for item in intelligence.get("active_archetypes", [])],
        primitives=intelligence.get("structural_ontology", {}).get("vocabulary", [])[:10],
        ontology_coverage="HIGH" if intelligence.get("structural_ontology") else "LOW",
    )
    continuation = ContinuationPathwayResponse(
        pathways=intelligence.get("counterfactuals", {}).get("structural_continuation_pathways", []),
        window=str(intelligence.get("counterfactuals", {}).get("progression_scenarios", [{}])[0].get("window", "Monitoring")),
        coherence=str(intelligence.get("cognition_validation", {}).get("validation_report", {}).get("replay_consistency", "MODERATE")),
    )
    audit = AuditRecordResponse(
        audit_id=str(intelligence.get("operational_audit", {}).get("audit_record", {}).get("audit_id", "audit-latest")),
        replay_reference_count=int(intelligence.get("operational_audit", {}).get("audit_record", {}).get("replay_reference_count", 0)),
        evidence_traceability=str(intelligence.get("institutional_trust", {}).get("trust_factors", {}).get("replay_traceability", "MODERATE")),
    )
    return {
        "CognitionStateResponse": cognition_state.__dict__,
        "TopologyStateResponse": topology_state.__dict__,
        "PropagationStateResponse": propagation_state.__dict__,
        "EvidenceLineageResponse": evidence_lineage.__dict__,
        "ReplayFrameResponse": replay.__dict__,
        "OntologyStateResponse": ontology.__dict__,
        "ContinuationPathwayResponse": continuation.__dict__,
        "AuditRecordResponse": audit.__dict__,
    }

