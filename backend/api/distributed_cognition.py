from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.security import require_api_access
from app.routers.facility import resolve_uploaded_intelligence
from app.services.sii_intelligence import build_sample_intelligence
from app.services.upload_jobs import read_latest_upload_result
from cognition_graph.persistent_graph_memory import PersistentCognitionGraphMemory
from cognition_graph.structural_cognition_graph import build_structural_cognition_graph
from cross_domain.cross_domain_intelligence_engine import CrossDomainIntelligenceEngine
from exchange.sii_graph_exchange import build_graph_exchange_packet
from federation.federated_cognition_exchange import build_federated_exchange_payload
from governance.distributed_cognition_governance import build_governance_record
from ontology.evolving_ontology_engine import EvolvingOntologyEngine
from search.structural_evolution_search import BehavioralSimilaritySearch, StructuralEvolutionQuery
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


def current_intelligence() -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = resolve_uploaded_intelligence(latest_result)
    return intelligence or build_sample_intelligence()

