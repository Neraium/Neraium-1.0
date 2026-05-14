from benchmarking.structural_benchmark_engine import StructuralBenchmarkEngine
from cognition.deterioration_library import sequence_similarity
from cognition.multi_facility_cognition_engine import MultiFacilityCognitionEngine
from digital_twin.behavioral_twin_engine import BehavioralTwinEngine
from domain_packs import resolve_domain_pack
from human_factors.operator_interaction_engine import OperatorInteractionEngine
from ontology.structural_ontology import build_structural_ontology


def test_domain_pack_and_ontology_are_available() -> None:
    pack = resolve_domain_pack("data_centers")
    ontology = build_structural_ontology()

    assert pack["domain"] == "data_centers"
    assert pack["subsystem_types"]
    assert ontology["vocabulary"]
    assert ontology["archetype_nodes"]


def test_deterioration_sequence_similarity_returns_ranked_matches() -> None:
    matches = sequence_similarity(
        observed_archetypes=["STRUCTURAL_COMPRESSION", "PROPAGATION_ACCELERATION"],
        observed_paths=["airflow imbalance", "thermal lag"],
    )

    assert matches
    assert matches[0]["similarity"] >= matches[-1]["similarity"]


def test_multi_facility_and_operator_interaction_models() -> None:
    graph = MultiFacilityCognitionEngine().build_graph(
        facilities=[
            {
                "facility_id": "a",
                "facility_name": "Facility A",
                "active_archetypes": ["STRUCTURAL_COMPRESSION", "RELATIONSHIP_DECAY"],
                "dominant_paths": ["airflow -> thermal"],
                "topology_state": "WATCH",
            },
            {
                "facility_id": "b",
                "facility_name": "Facility B",
                "active_archetypes": ["STRUCTURAL_COMPRESSION"],
                "dominant_paths": ["airflow -> thermal"],
                "topology_state": "DETERIORATING",
            },
        ]
    )
    interactions = OperatorInteractionEngine().analyze(
        interventions=[
            {"response_minutes": 20, "effectiveness": 0.72, "propagation_suppressed": True},
            {"response_minutes": 45, "effectiveness": 0.61, "propagation_suppressed": False},
        ],
        intelligence={"recovery_convergence": {"convergence_quality": "HIGH_CONVERGENCE"}},
    )

    assert graph["facility_cognition_graph"]["nodes"]
    assert graph["recurring_deterioration_pathways"]
    assert interactions["intervention_effectiveness_trends"] in {"improving", "mixed", "limited"}


def test_behavioral_twin_and_benchmark_have_operational_fields() -> None:
    timeline = [
        {
            "topology_state": {"drift_index": 0.2, "fragmentation_indicator": 0.3},
            "propagation_state": {"activation_intensity": 0.4},
            "active_archetypes": [{"name": "RELATIONSHIP_DECAY"}],
            "continuation_window": {"window": "6-10 operational days"},
            "cognition_state": {"operational_phase": "relationship_weakening", "canonical_phase": "relationship_weakening"},
        },
        {
            "topology_state": {"drift_index": 0.6, "fragmentation_indicator": 0.7},
            "propagation_state": {"activation_intensity": 0.7},
            "active_archetypes": [{"name": "PROPAGATION_ACCELERATION"}, {"name": "STRUCTURAL_COMPRESSION"}],
            "continuation_window": {"window": "5-8 operational days"},
            "cognition_state": {"operational_phase": "propagation_acceleration", "canonical_phase": "propagation_activation"},
        },
    ]
    benchmark = StructuralBenchmarkEngine().benchmark(intelligence={"evidence_lineage": {"lineages": [{}, {}]}}, replay_timeline=timeline)
    twin = BehavioralTwinEngine().build_twin(
        intelligence={
            "primary_room": "Room A",
            "facility_cognition": {"subsystem_pressure": {"subsystems": {"thermal_control": 0.4}}},
            "structural_memory": {"memory_matches": []},
            "causality_graph": {"dominant_pathways": ["a->b"]},
            "recovery_convergence": {},
            "operational_time_intelligence": {},
        },
        replay_timeline=timeline,
        benchmark=benchmark,
    )

    assert benchmark["cognition_quality_metrics"]["replay_fidelity"] in {"high", "moderate", "limited"}
    assert twin["replayable_deterioration_behavior"]
