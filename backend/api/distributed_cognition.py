from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.security import require_api_access
from app.routers.facility import resolve_uploaded_intelligence
from app.services.sii_intelligence import build_sample_intelligence
from app.services.upload_jobs import read_latest_upload_result
from archives.infrastructure_behavioral_archive import build_infrastructure_behavior_archive
from behavior_science.behavioral_taxonomy import build_behavioral_taxonomy
from behavior_science.long_horizon_memory import build_long_horizon_memory
from behavior_science.structural_evolution_theory import EvolutionTheoryEngine
from cognition_graph.persistent_graph_memory import PersistentCognitionGraphMemory
from cognition_graph.structural_cognition_graph import build_structural_cognition_graph
from cross_domain.cross_domain_intelligence_engine import CrossDomainIntelligenceEngine
from cultivation.canonical_replays.scenarios import build_cultivation_replay_scenarios
from cultivation.compensation_masking_engine import detect_compensation_masking
from cultivation.multi_room_cognition_engine import build_multi_room_cognition
from cultivation.pilot_validation_mode import build_cultivation_pilot_validation_payload
from cultivation.pre_visibility_engine import build_pre_visibility_state
from cultivation.vpd_relationship_engine import build_vpd_relationship_state
from domain_packs.cultivation.cultivation_ontology import build_cultivation_ontology
from domain_packs.extreme_environment_pack import build_extreme_environment_cognition_profile
from exchange.sii_graph_exchange import build_graph_exchange_packet
from explainability.structural_explainability_standard import build_explainability_standard
from federation.federated_cognition_exchange import build_federated_exchange_payload
from federation.infrastructure_cognition_federation import build_infrastructure_cognition_federation
from governance.autonomous_ontology_governance import build_autonomous_ontology_governance
from governance.distributed_cognition_governance import build_governance_record
from laboratory.behavioral_infrastructure_lab import run_behavior_lab
from mathematics.structural_evolution_math import build_structural_evolution_metrics
from ontology.evolving_ontology_engine import EvolvingOntologyEngine
from primitives.universal_structural_primitives import build_universal_structural_primitives
from reasoning.foundational_reasoning_substrate import build_foundational_reasoning_substrate
from research.behavior_research_engine import run_behavior_research
from research.sii_research_ecosystem import build_sii_research_ecosystem_export
from search.structural_evolution_search import BehavioralSimilaritySearch, StructuralEvolutionQuery
from training.operator_cognition_curriculum import build_operator_cognition_curriculum
from training.operator_cognition_training import build_training_payload

router = APIRouter(tags=["distributed-cognition"], dependencies=[Depends(require_api_access)])
MEMORY = PersistentCognitionGraphMemory()


@router.get("/distributed/memory")
def distributed_memory() -> dict[str, Any]:
    intelligence = current_intelligence()
    graph_snapshot = build_structural_cognition_graph(intelligence).get("snapshot", {})
    snapshot = MEMORY.append_graph_snapshot(
        facility_id="facility-primary",
        graph_snapshot=graph_snapshot,
        intelligence=intelligence,
    )
    similar = MEMORY.retrieve_similar_graph_states(
        archetypes=[item.get("name", "") for item in intelligence.get("active_archetypes", [])],
        pathways=intelligence.get("causality_graph", {}).get("dominant_pathways", []),
    )
    return {
        "latest_snapshot": snapshot.to_dict(),
        "similar_states": similar.to_dict(),
        "recurring_paths": MEMORY.query_recurring_propagation_paths().to_dict(),
    }


@router.get("/distributed/federation")
def distributed_federation() -> dict[str, Any]:
    return build_federated_exchange_payload(current_intelligence())


@router.get("/distributed/ontology")
def distributed_ontology() -> dict[str, Any]:
    engine = EvolvingOntologyEngine()
    candidates = engine.propose_candidates(current_intelligence())
    decisions = [engine.promotion_decision(candidate) for candidate in candidates]
    return {
        "candidates": candidates,
        "promotion_decisions": decisions,
    }


@router.get("/distributed/cross-domain")
def distributed_cross_domain() -> dict[str, Any]:
    return CrossDomainIntelligenceEngine().build_report(current_intelligence())


@router.get("/distributed/search")
def distributed_search() -> dict[str, Any]:
    intelligence = current_intelligence()
    search = BehavioralSimilaritySearch()
    query = StructuralEvolutionQuery(
        text="find propagation patterns involving airflow and thermal lag",
        archetypes=["COMPENSATION_MASKING", "PROPAGATION_ACCELERATION"],
        pathways=["airflow", "thermal", "lag"],
        convergence_terms=["delayed_recovery"],
    )
    return {
        "index": search.build_index(intelligence).to_dict(),
        "result": search.search(query, intelligence).to_dict(),
    }


@router.get("/distributed/training")
def distributed_training() -> dict[str, Any]:
    return build_training_payload(current_intelligence())


@router.get("/distributed/exchange")
def distributed_exchange() -> dict[str, Any]:
    return build_graph_exchange_packet(current_intelligence())


@router.get("/distributed/governance")
def distributed_governance() -> dict[str, Any]:
    intelligence = current_intelligence()
    return build_governance_record(intelligence)


@router.get("/distributed/science/memory")
def behavior_science_memory() -> dict[str, Any]:
    return build_long_horizon_memory(current_intelligence())


@router.get("/distributed/science/taxonomy")
def behavior_science_taxonomy() -> dict[str, Any]:
    return build_behavioral_taxonomy(current_intelligence())


@router.get("/distributed/science/evolution-theory")
def behavior_science_evolution_theory() -> dict[str, Any]:
    intelligence = current_intelligence()
    engine = EvolutionTheoryEngine()
    return {
        "rules": engine.rules(),
        "evaluations": engine.evaluate(intelligence),
    }


@router.get("/distributed/science/research")
def behavior_science_research() -> dict[str, Any]:
    return run_behavior_research(current_intelligence())


@router.get("/distributed/science/explainability")
def behavior_science_explainability() -> dict[str, Any]:
    return build_explainability_standard(current_intelligence())


@router.get("/distributed/science/laboratory")
def behavior_science_laboratory() -> dict[str, Any]:
    return run_behavior_lab(current_intelligence())


@router.get("/distributed/science/federation")
def behavior_science_federation() -> dict[str, Any]:
    return build_infrastructure_cognition_federation(current_intelligence())


@router.get("/distributed/framework/primitives")
def framework_primitives() -> dict[str, Any]:
    return build_universal_structural_primitives()


@router.get("/distributed/framework/mathematics")
def framework_mathematics() -> dict[str, Any]:
    return build_structural_evolution_metrics(current_intelligence())


@router.get("/distributed/framework/ontology-governance")
def framework_ontology_governance() -> dict[str, Any]:
    return build_autonomous_ontology_governance(current_intelligence())


@router.get("/distributed/framework/training-curriculum")
def framework_training_curriculum() -> dict[str, Any]:
    return build_operator_cognition_curriculum(current_intelligence())


@router.get("/distributed/framework/extreme-environment")
def framework_extreme_environment() -> dict[str, Any]:
    return build_extreme_environment_cognition_profile()


@router.get("/distributed/framework/archive")
def framework_archive() -> dict[str, Any]:
    return build_infrastructure_behavior_archive(current_intelligence())


@router.get("/distributed/framework/research-ecosystem")
def framework_research_ecosystem() -> dict[str, Any]:
    intelligence = current_intelligence()
    primitives = build_universal_structural_primitives()
    metrics = build_structural_evolution_metrics(intelligence)
    archive = build_infrastructure_behavior_archive(intelligence)
    return build_sii_research_ecosystem_export(
        primitives=primitives,
        metrics=metrics,
        archive=archive,
        intelligence=intelligence,
    )


@router.get("/distributed/framework/reasoning-substrate")
def framework_reasoning_substrate() -> dict[str, Any]:
    intelligence = current_intelligence()
    primitives = build_universal_structural_primitives()
    metrics = build_structural_evolution_metrics(intelligence)
    archive = build_infrastructure_behavior_archive(intelligence)
    return build_foundational_reasoning_substrate(
        primitives=primitives,
        metrics=metrics,
        archive=archive,
        intelligence=intelligence,
    )


@router.get("/distributed/cultivation/ontology")
def cultivation_ontology() -> dict[str, Any]:
    return build_cultivation_ontology()


@router.get("/distributed/cultivation/vpd")
def cultivation_vpd() -> dict[str, Any]:
    return build_vpd_relationship_state(current_intelligence())


@router.get("/distributed/cultivation/multi-room")
def cultivation_multi_room() -> dict[str, Any]:
    return build_multi_room_cognition(current_intelligence())


@router.get("/distributed/cultivation/compensation-masking")
def cultivation_compensation_masking() -> dict[str, Any]:
    return detect_compensation_masking(current_intelligence())


@router.get("/distributed/cultivation/replays")
def cultivation_replays() -> dict[str, Any]:
    return build_cultivation_replay_scenarios()


@router.get("/distributed/cultivation/pre-visibility")
def cultivation_pre_visibility() -> dict[str, Any]:
    return build_pre_visibility_state()


@router.get("/distributed/cultivation/pilot-mode")
def cultivation_pilot_mode() -> dict[str, Any]:
    return build_cultivation_pilot_validation_payload(current_intelligence())


def current_intelligence() -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = resolve_uploaded_intelligence(latest_result)
    return intelligence or build_sample_intelligence()
