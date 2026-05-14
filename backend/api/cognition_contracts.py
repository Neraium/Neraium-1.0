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


@dataclass(frozen=True)
class CognitionStateCanonicalResponse:
    cognition_state: str
    structural_stability: str
    active_archetypes: list[str]
    propagation_pathways: list[str]
    evidence_lineage: dict[str, Any]
    structural_memory_matches: list[dict[str, Any]]
    continuation_windows: dict[str, Any]
    replay_summary: dict[str, Any]
    recovery_convergence: dict[str, Any]
    operator_explanation: str


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


def build_canonical_cognition_state_response(intelligence: dict[str, Any]) -> dict[str, Any]:
    replay = intelligence.get("replay_timeline", {}) or {}
    timeline = replay.get("timeline", [])
    active_frame = timeline[-1] if timeline else {}
    continuation = intelligence.get("counterfactuals", {}) or {}
    progression = continuation.get("progression_scenarios", [{}])
    structural_memory = intelligence.get("structural_memory", {}) or {}
    evidence_lineage = intelligence.get("evidence_lineage", {}) or {}
    operator_explanation = intelligence.get("operator_explanation_v2", {}) or {}
    payload = CognitionStateCanonicalResponse(
        cognition_state=str(intelligence.get("facility_state", "Monitoring")),
        structural_stability=str(intelligence.get("structural_stability_index", {}).get("state", "WATCH")),
        active_archetypes=[item.get("name", "") for item in intelligence.get("active_archetypes", [])],
        propagation_pathways=intelligence.get("causality_graph", {}).get("dominant_pathways", []),
        evidence_lineage=evidence_lineage,
        structural_memory_matches=structural_memory.get("matches", []),
        continuation_windows={
            "window": str(progression[0].get("window", "Monitoring")),
            "structural_pathways": continuation.get("structural_continuation_pathways", []),
            "uncertainty_range": continuation.get("progression_scenarios", []),
        },
        replay_summary={
            "frame_count": replay.get("meta", {}).get("frame_count", len(timeline)),
            "canonical_flow": replay.get("meta", {}).get("canonical_flow", []),
            "active_frame": active_frame,
        },
        recovery_convergence=intelligence.get("recovery_convergence", {}),
        operator_explanation=str(
            operator_explanation.get("narrative")
            or operator_explanation.get("summary")
            or "Evidence-backed structural cognition is available for operator review."
        ),
    )
    return payload.__dict__
