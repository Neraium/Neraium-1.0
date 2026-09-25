"""Controlled real-engine reproduction of the reviewed comparison limitation."""
from app.engine.sii_engine import evaluate_sii
from app.services.analysis_result_contract import build_analysis_result
from app.services.output_semantics import semantic_digest
from relationship_evidence_binding_cases import without_binding_metadata
from test_sii_supplied_reference import contract


def context_fallback_case():
    args = contract(16)
    rows = args['comparison_rows']
    for row in rows:
        row['pump_status'] = 1
    columns = ['timestamp', 'flow', 'pressure', 'power', 'pump_status']
    sii = evaluate_sii(
        columns=columns, rows=rows,
        numeric_profiles=[*args['numeric_profiles'], {
            'column': 'pump_status', 'constant_or_stuck': True,
            'missing_count': 0, 'non_numeric_count': 0,
        }],
        timestamp_column='timestamp', config={'numeric_columns': columns[1:]},
    )
    upload = {
        **sii['compatibility'], 'sii_result': sii,
        'job_id': 'context-fallback-controlled', 'filename': 'controlled-context.csv',
        'columns': columns, 'row_count': len(rows),
    }
    upload['analysis_result'] = build_analysis_result(upload)
    return upload


def context_invariants(upload):
    analysis, sii = upload['analysis_result'], upload['sii_result']
    graph = sii['relationship_graph']
    return {
        'classification': [item.get('classification') for item in analysis['insights']],
        'primary_selection': [item.get('id') for item in analysis['relationships']],
        'promotion': [item['promoted_changed_edge'] for item in graph['edges']],
        'persistence': [item['persistent_relationship_change'] for item in graph['edges']],
        'finding_persistence': [item.get('persistence') for item in analysis['insights']],
        'measurable_consequence': [item.get('measurable_consequence') for item in analysis['insights']],
        'analytical_digest': semantic_digest(without_binding_metadata(analysis)),
        'graph_digest': semantic_digest(without_binding_metadata(graph)),
    }
