from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.security import require_api_access
from app.routers.facility import resolve_uploaded_intelligence
from app.services.sii_intelligence import build_sample_intelligence
from app.services.upload_state_repository import read_current_upload_result
from cognition_graph.graph_evolution_engine import graph_evolution
from cognition_graph.graph_memory_store import build_graph_memory_store
from cognition_graph.graph_query_engine import query_cross_domain_archetype_matches, query_recurring_pathways
from cognition_graph.structural_cognition_graph import build_structural_cognition_graph
from integrations import bms_adapter, digital_twin_adapter, enterprise_reporting_adapter, historian_adapter, scada_adapter
from interoperability.sii_context_model import SIIContextEntity, SIIContextRelationship
from interoperability.sii_export_contracts import SIIEvidenceExport, SIIOntologyExport, SIIReplayFrameExport
from runtime.sii_runtime import SIIRuntime
from simulation.operational_reasoning_simulator import OperationalReasoningSimulator

router = APIRouter(tags=["ecosystem"], dependencies=[Depends(require_api_access)])


@router.get("/ecosystem/runtime/state")
def ecosystem_runtime_state() -> dict[str, Any]:
    intelligence = current_intelligence()
    return SIIRuntime().build_state(intelligence=intelligence, execution_mode="cloud")


@router.get("/ecosystem/context/entities")
def ecosystem_context_entities() -> dict[str, Any]:
    intelligence = current_intelligence()
    entities = [
        SIIContextEntity(entity_id="facility:primary", entity_type="facility", properties={"state": intelligence.get("facility_state")}).to_dict(),
        SIIContextEntity(entity_id="cognition:state", entity_type="cognition_state", properties=intelligence.get("cognition_confidence", {})).to_dict(),
    ]
    return {"entities": entities}


@router.get("/ecosystem/context/relationships")
def ecosystem_context_relationships() -> dict[str, Any]:
    intelligence = current_intelligence()
    relationships = [
        SIIContextRelationship(
            source_id="facility:primary",
            target_id="cognition:state",
            relationship_type="has_cognition_state",
            attributes={"topology_state": intelligence.get("structural_stability_index", {}).get("state")},
        ).to_dict()
    ]
    return {"relationships": relationships}


@router.get("/ecosystem/graph/snapshot")
def ecosystem_graph_snapshot() -> dict[str, Any]:
    intelligence = current_intelligence()
    graph = build_structural_cognition_graph(intelligence)
    store = build_graph_memory_store(graph.get("snapshot", {}))
    return {"snapshot": graph.get("snapshot", {}), "memory_store": store}


@router.get("/ecosystem/graph/evolution")
def ecosystem_graph_evolution() -> dict[str, Any]:
    intelligence = current_intelligence()
    graph = build_structural_cognition_graph(intelligence).get("graph", {})
    return {
        "evolution": graph_evolution(graph),
        "recurring_pathways": query_recurring_pathways(graph),
        "cross_domain_archetype_matches": query_cross_domain_archetype_matches(graph),
    }


@router.get("/ecosystem/replay/export")
def ecosystem_replay_export() -> dict[str, Any]:
    intelligence = current_intelligence()
    replay = intelligence.get("replay_timeline", {}).get("timeline", [])
    return SIIReplayFrameExport(frames=replay).to_dict()


@router.get("/ecosystem/evidence/export")
def ecosystem_evidence_export() -> dict[str, Any]:
    intelligence = current_intelligence()
    return SIIEvidenceExport(lineage=intelligence.get("evidence_lineage", {})).to_dict()


@router.get("/ecosystem/ontology/export")
def ecosystem_ontology_export() -> dict[str, Any]:
    intelligence = current_intelligence()
    return SIIOntologyExport(ontology=intelligence.get("structural_ontology", {})).to_dict()


@router.get("/ecosystem/simulation/scenarios")
def ecosystem_simulation_scenarios() -> dict[str, Any]:
    intelligence = current_intelligence()
    return OperationalReasoningSimulator().simulate(cognition_state=intelligence)


@router.get("/ecosystem/integrations/readiness")
def ecosystem_integrations_readiness() -> dict[str, Any]:
    return {
        "integrations": [
            bms_adapter.readiness(),
            scada_adapter.readiness(),
            historian_adapter.readiness(),
            digital_twin_adapter.readiness(),
            enterprise_reporting_adapter.readiness(),
        ],
        "read_only_integration_status": "enforced",
    }


def current_intelligence() -> dict[str, Any]:
    latest_result = read_current_upload_result()
    intelligence = resolve_uploaded_intelligence(latest_result)
    return intelligence or build_sample_intelligence()
