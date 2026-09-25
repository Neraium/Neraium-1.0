"""Controlled existing engine failure branch; never customer telemetry."""
from unittest.mock import patch

from app.engine.sii_engine import evaluate_sii
from app.services.analysis_result_contract import build_analysis_result
from app.services.output_semantics import semantic_digest
from relationship_evidence_binding_cases import without_binding_metadata
from test_sii_supplied_reference import contract

FAILURE_TEXT = ('EXCEPTION_CANARY module=MODULE_CANARY traceback=TRACEBACK_CANARY '
                'worker=WORKER_CANARY process=PROCESS_CANARY retry=RETRY_CANARY '
                'path=/internal/PATH_CANARY credential=CREDENTIAL_CANARY '
                'forensic=FORENSIC_CANARY diagnostic=DIAGNOSTIC_CANARY')


def graph_fallback_case():
    with patch('app.engine.sii_engine.analyze_relationship_graph',
               side_effect=RuntimeError(FAILURE_TEXT)):
        sii = evaluate_sii(**contract(64))
    upload = {**sii['compatibility'], 'sii_result': sii,
              'job_id': 'graph-fallback-controlled', 'filename': 'controlled-graph.csv'}
    upload['analysis_result'] = build_analysis_result(upload)
    return upload


def graph_fallback_invariants(upload):
    analysis, graph = upload['analysis_result'], upload['sii_result']['relationship_graph']
    return {
        'classification': [item.get('classification') for item in analysis['insights']],
        'primary_selection': [item.get('id') for item in analysis['relationships']],
        # Raw fallback edges may lack dynamic evidence: preserve absence, not false.
        'edge_decisions': [{key: edge[key] for key in (
            'promoted_changed_edge', 'persistent_relationship_change',
            'recurrence_evidence', 'temporal_persistence_supported',
        ) if key in edge} for edge in graph['edges']],
        'finding_persistence': [item.get('persistence') for item in analysis['insights']],
        'measurable_consequence': [item.get('measurable_consequence') for item in analysis['insights']],
        'analytical_digest': semantic_digest(without_binding_metadata(analysis)),
        'graph_digest': semantic_digest(without_binding_metadata(graph)),
    }
