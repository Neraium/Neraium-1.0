from __future__ import annotations

from typing import Any

from audit.operational_audit_engine import OperationalAuditEngine
from benchmarking.structural_benchmark_engine import StructuralBenchmarkEngine
from case_studies.case_studies import load_case_studies
from cognition.cognition_confidence_engine import CognitionConfidenceEngine
from cognition.deterioration_library import CANONICAL_DETERIORATION_SEQUENCES, sequence_similarity
from cognition.multi_facility_cognition_engine import MultiFacilityCognitionEngine
from cognition.operational_time_engine import OperationalTimeEngine
from cognition.structural_stability_index import StructuralStabilityIndex
from datasets.structural_progression_dataset import build_structural_progression_dataset
from digital_twin.behavioral_twin_engine import BehavioralTwinEngine
from domain_packs import resolve_domain_pack
from evidence.evidence_lineage_engine import EvidenceLineageEngine
from engines.counterfactual_engine import CounterfactualEngine
from engines.facility_cognition_engine import FacilityCognitionEngine
from engines.recovery_convergence_engine import RecoveryConvergenceEngine
from engines.structural_compression_engine import StructuralCompressionEngine
from engines.structural_causality_engine import StructuralCausalityEngine
from engines.structural_memory_engine import StructuralMemoryEngine
from explanations.operator_explanation_engine import OperatorExplanationEngine
from human_factors.operator_interaction_engine import OperatorInteractionEngine
from ontology.structural_ontology import build_structural_ontology
from ontology.archetypes import StructuralArchetypeClassifier
from replay.structural_replay_engine import StructuralReplayEngine
from sii_standard.standard import build_sii_standard
from simulation.operational_cognition_simulator import OperationalCognitionSimulator
from trust.institutional_trust_framework import InstitutionalTrustFramework
from validation.cognition_validation_framework import CognitionValidationFramework


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
    replay_engine = StructuralReplayEngine()
    benchmark_engine = StructuralBenchmarkEngine()
    multi_facility_engine = MultiFacilityCognitionEngine()
    operator_interaction_engine = OperatorInteractionEngine()
    behavioral_twin_engine = BehavioralTwinEngine()
    validation_engine = CognitionValidationFramework()
    audit_engine = OperationalAuditEngine()
    simulator = OperationalCognitionSimulator()
    trust_framework = InstitutionalTrustFramework()

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
    replay_timeline = replay_engine.build_timeline(
        intelligence={
            **driver_attribution,
            **{
                "active_archetypes": archetypes,
                "causality_graph": causality_graph,
                "facility_cognition": facility_cognition,
                "structural_memory": memory_retrieval,
                "counterfactuals": counterfactuals,
                "cognition_confidence": cognition_confidence,
                "evidence_lineage": evidence_lineage,
                "structural_stability_index": stability_index,
                "recovery_convergence": recovery_convergence,
                "structural_compression": structural_compression,
                "operational_time_intelligence": operational_time,
                "last_updated": now_iso_from_driver(driver_attribution),
                "facility_state": driver_attribution.get("state", "Monitoring"),
                "intervention_window": counterfactuals.get("progression_scenarios", [{}])[0].get("window", "Monitoring"),
            },
        },
        intervals=24,
        replay_compression=1,
    )
    replay_frames = replay_timeline.get("timeline", [])
    benchmark = benchmark_engine.benchmark(
        intelligence={
            "evidence_lineage": evidence_lineage,
        },
        replay_timeline=replay_frames,
    )
    domain_pack = resolve_domain_pack("cultivation")
    observed_archetypes = [item.get("name", "") for item in archetypes]
    observed_paths = causality_graph.get("dominant_pathways", [])
    deterioration_library_matches = sequence_similarity(observed_archetypes, observed_paths)
    ontology = build_structural_ontology()
    facilities = build_facility_samples(room_summary, archetypes, observed_paths, stability_index)
    multi_facility = multi_facility_engine.build_graph(facilities=facilities)
    validation = validation_engine.validate(
        intelligence={
            "causality_graph": causality_graph,
            "facility_cognition": facility_cognition,
            "active_archetypes": archetypes,
        },
        replay_timeline=replay_frames,
        evidence_lineage=evidence_lineage,
    )
    simulation = simulator.simulate(
        intelligence={
            "causality_graph": causality_graph,
            "structural_compression": structural_compression,
            "recovery_convergence": recovery_convergence,
        },
    )
    structural_dataset = build_structural_progression_dataset(
        intelligence={
            "primary_room": driver_attribution.get("room"),
            "causality_graph": causality_graph,
            "active_archetypes": archetypes,
            "counterfactuals": counterfactuals,
            "recovery_convergence": recovery_convergence,
            "operational_time_intelligence": operational_time,
            "structural_stability_index": stability_index,
        },
        replay_timeline=replay_frames,
    )
    audit = audit_engine.build_record(
        session_id="latest",
        intelligence={
            "facility_state": driver_attribution.get("state", "Monitoring"),
            "active_archetypes": archetypes,
            "causality_graph": causality_graph,
            "counterfactuals": counterfactuals,
            "evidence_lineage": evidence_lineage,
            "facility_cognition": facility_cognition,
            "structural_memory": memory_retrieval,
        },
        replay_timeline=replay_frames,
    )
    operator_interactions = operator_interaction_engine.analyze(
        interventions=build_operator_interventions(room_summary),
        intelligence={"recovery_convergence": recovery_convergence},
    )
    behavioral_twin = behavioral_twin_engine.build_twin(
        intelligence={
            "primary_room": driver_attribution.get("room"),
            "facility_cognition": facility_cognition,
            "structural_memory": memory_retrieval,
            "causality_graph": causality_graph,
            "recovery_convergence": recovery_convergence,
            "operational_time_intelligence": operational_time,
            "operational_cognition_simulation": simulation,
            "structural_ontology": ontology,
            "evidence_lineage": evidence_lineage,
            "deterioration_library_matches": deterioration_library_matches,
        },
        replay_timeline=replay_frames,
        benchmark=benchmark,
    )
    operator_explanation = explanation_engine.build(
        driver_attribution=driver_attribution,
        archetypes=archetypes,
        causality_graph=causality_graph,
        memory_retrieval=memory_retrieval,
        counterfactuals=counterfactuals,
        facility_cognition=facility_cognition,
    )
    trust = trust_framework.assess(
        intelligence={
            "evidence_lineage": evidence_lineage,
            "operator_explanation_v2": operator_explanation,
        },
        validation=validation,
        audit=audit,
    )
    sii_standard = build_sii_standard()
    case_studies = load_case_studies()
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
        "canonical_deterioration_library": [item.to_dict() for item in CANONICAL_DETERIORATION_SEQUENCES],
        "deterioration_library_matches": deterioration_library_matches,
        "domain_cognition_pack": domain_pack,
        "structural_ontology": ontology,
        "structural_benchmark": benchmark,
        "cognition_validation": validation,
        "operational_audit": audit,
        "domain_validation_case_studies": case_studies,
        "sii_standard": sii_standard,
        "structural_progression_dataset": structural_dataset,
        "operational_cognition_simulation": simulation,
        "institutional_trust": trust,
        "multi_facility_cognition": multi_facility,
        "operator_interaction_model": operator_interactions,
        "behavioral_infrastructure_twin": behavioral_twin,
        "evidence_lineage": evidence_lineage,
        "cognition_confidence": cognition_confidence,
        "operator_explanation_v2": operator_explanation,
    }


def now_iso_from_driver(driver_attribution: dict[str, Any]) -> str:
    return str(driver_attribution.get("timestamp") or "")


def build_facility_samples(
    room_summary: dict[str, Any] | None,
    archetypes: list[dict[str, Any]],
    paths: list[str],
    stability_index: dict[str, Any],
) -> list[dict[str, Any]]:
    rooms = (room_summary or {}).get("rooms", [])
    if not rooms:
        rooms = [{"room": "Facility Alpha"}, {"room": "Facility Beta"}]
    facilities = []
    for idx, room in enumerate(rooms[:4]):
        facilities.append(
            {
                "facility_id": f"facility-{idx + 1}",
                "facility_name": room.get("room", f"Facility {idx + 1}"),
                "active_archetypes": [item.get("name") for item in archetypes[: max(1, min(len(archetypes), 2 + idx % 2))]],
                "dominant_paths": paths[: max(1, min(len(paths), 1 + idx % 3))],
                "topology_state": stability_index.get("state", "WATCH"),
            }
        )
    return facilities


def build_operator_interventions(room_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    rooms = (room_summary or {}).get("rooms", [])
    count = max(1, len(rooms))
    return [
        {
            "response_minutes": 25 + idx * 12,
            "effectiveness": max(0.35, 0.78 - idx * 0.08),
            "propagation_suppressed": idx % 2 == 0,
        }
        for idx in range(min(count, 4))
    ]
