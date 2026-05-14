from __future__ import annotations

from typing import Any

from cognition.cognition_confidence_engine import CognitionConfidenceEngine
from cognition.operational_time_engine import OperationalTimeEngine
from cognition.structural_stability_index import StructuralStabilityIndex
from evidence.evidence_lineage_engine import EvidenceLineageEngine
from engines.counterfactual_engine import CounterfactualEngine
from engines.facility_cognition_engine import FacilityCognitionEngine
from engines.recovery_convergence_engine import RecoveryConvergenceEngine
from engines.structural_compression_engine import StructuralCompressionEngine
from engines.structural_causality_engine import StructuralCausalityEngine
from engines.structural_memory_engine import StructuralMemoryEngine
from explanations.operator_explanation_engine import OperatorExplanationEngine
from ontology.archetypes import StructuralArchetypeClassifier


def build_structural_cognition(
    *,
    baseline_analysis: dict[str, Any],
    engine_result: dict[str, Any],
    driver_attribution: dict[str, Any],
    room_summary: dict[str, Any] | None,
    urgency: str,
) -> dict[str, Any]:
    memory_engine = StructuralMemoryEngine()
    causality_engine = StructuralCausalityEngine()
    facility_engine = FacilityCognitionEngine()
    archetype_classifier = StructuralArchetypeClassifier()
    counterfactual_engine = CounterfactualEngine()
    explanation_engine = OperatorExplanationEngine()
    lineage_engine = EvidenceLineageEngine()
    confidence_engine = CognitionConfidenceEngine()
    recovery_engine = RecoveryConvergenceEngine()
    compression_engine = StructuralCompressionEngine()
    stability_engine = StructuralStabilityIndex()
    time_engine = OperationalTimeEngine()

    fingerprint = memory_engine.build_fingerprint(
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
        room_summary=room_summary,
    )
    causality_graph = causality_engine.build_graph(
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
    )
    facility_cognition = facility_engine.build_state(
        room_summary=room_summary,
        driver_attribution=driver_attribution,
        engine_result=engine_result,
        causality_graph=causality_graph,
    )
    memory_retrieval = memory_engine.retrieve(fingerprint=fingerprint)
    propagation_score = float(causality_graph.get("propagation_score", 0.0))
    acceleration = abs(float(fingerprint.get("volatility_acceleration", 0.0)))
    topology_drift = {
        "corroboration_level": engine_result.get("system_evidence", {}).get("corroboration_level", "limited"),
        "meaningful_categories": engine_result.get("system_evidence", {}).get("categories_showing_meaningful_change", 0),
    }
    archetypes = archetype_classifier.classify(
        topology_drift=topology_drift,
        subsystem_pressure=facility_cognition.get("subsystem_pressure", {}),
        relationship_changes=[
            item
            for item in engine_result.get("evidence", [])
            if item.get("type") == "relationship_change"
        ],
        persistence=engine_result.get("persistence_assessment", {}),
        propagation_velocity=propagation_score,
        acceleration=acceleration,
        facility_pressure_score=float(facility_cognition.get("global_structural_pressure_score", 0.0)),
        intervention_history=fingerprint.get("operator_intervention_outcomes", []),
    )
    if archetypes:
        fingerprint["archetypes"] = [item["name"] for item in archetypes[:3]]
    counterfactuals = counterfactual_engine.model(
        memory_retrieval=memory_retrieval,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        causality_graph=causality_graph,
        urgency=urgency,
    )
    recovery_convergence = recovery_engine.model(
        facility_cognition=facility_cognition,
        causality_graph=causality_graph,
        memory_retrieval=memory_retrieval,
        persistence=engine_result.get("persistence_assessment", {}),
    )
    structural_compression = compression_engine.detect(
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        causality_graph=causality_graph,
    )
    stability_index = stability_engine.evaluate(
        topology_consistency=max(0.0, 1.0 - float(causality_graph.get("propagation_score", 0.0))),
        propagation_stability=max(0.0, 1.0 - float(causality_graph.get("propagation_score", 0.0)) * 0.8),
        subsystem_convergence=float(recovery_convergence.get("convergence_index", 0.0)),
        persistence_quality=max(0.0, 1.0 - (len(engine_result.get("persistence_assessment", {}).get("persistent_columns", [])) * 0.2)),
        fragmentation_pressure=float(facility_cognition.get("global_structural_pressure_score", 0.0)),
        recovery_convergence=float(recovery_convergence.get("convergence_index", 0.0)),
        relationship_coherence=max(0.0, 1.0 - min(len(causality_graph.get("edges", [])) * 0.08, 0.9)),
    )
    evidence_lineage = lineage_engine.build(
        intelligence={
            **driver_attribution,
            **{
                "supporting_evidence": driver_attribution.get("supporting_evidence", []),
                "relationship_evidence": [
                    edge.get("explanation")
                    for edge in causality_graph.get("edges", [])
                    if edge.get("explanation")
                ][:4],
                "facility_cognition": facility_cognition,
                "causality_graph": causality_graph,
                "structural_memory": memory_retrieval,
                "active_archetypes": archetypes,
                "urgency": urgency,
                "last_updated": counterfactuals.get("last_updated") or "",
            },
        },
        engine_result=engine_result,
    )
    cognition_confidence = confidence_engine.calibrate(
        intelligence={
            "facility_cognition": facility_cognition,
            "causality_graph": causality_graph,
            "structural_memory": memory_retrieval,
            "active_archetypes": archetypes,
        },
        evidence_lineage=evidence_lineage,
        engine_result=engine_result,
    )
    operational_time = time_engine.model(
        causality_graph=causality_graph,
        compression=structural_compression,
        recovery=recovery_convergence,
        counterfactuals=counterfactuals,
        persistence=engine_result.get("persistence_assessment", {}),
    )
    operator_explanation = explanation_engine.build(
        driver_attribution=driver_attribution,
        archetypes=archetypes,
        causality_graph=causality_graph,
        memory_retrieval=memory_retrieval,
        counterfactuals=counterfactuals,
        facility_cognition=facility_cognition,
    )
    return {
        "structural_memory": memory_retrieval,
        "active_fingerprint": fingerprint,
        "active_archetypes": archetypes,
        "causality_graph": causality_graph,
        "counterfactuals": counterfactuals,
        "facility_cognition": facility_cognition,
        "structural_stability_index": stability_index,
        "recovery_convergence": recovery_convergence,
        "structural_compression": structural_compression,
        "operational_time_intelligence": operational_time,
        "evidence_lineage": evidence_lineage,
        "cognition_confidence": cognition_confidence,
        "operator_explanation_v2": operator_explanation,
    }
