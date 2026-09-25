"""Controlled contract examples, not customer telemetry or production handoff."""
from copy import deepcopy

from app.services.finding_classification import classify_finding
from app.services.measurable_consequence import build_measurable_consequence
from app.services.output_semantics import semantic_digest
from app.services.product_evidence_contract import product_evidence
from test_relationship_temporal_persistence import analyze, edge, sequence
from test_telemetry_result_projection import _execution


def review_cases():
    cases = {}
    for name, state in [('A', 'stable'), ('B', 'insufficient'), ('C', 'material'), ('D', 'material')]:
        count = 6 if name == 'C' else 1
        observed, _ = sequence([-.2] * count, columns=['synthetic_flow', 'synthetic_pressure'])
        graph = {'edges': [observed[-1]], 'changed_edges': [item for item in observed[-1:] if item['promoted_changed_edge']]}
        if name == 'B':
            graph = analyze(edge(1, columns=['synthetic_flow', 'synthetic_pressure'], current_sample_count=2))
        if name == 'D':
            graph = analyze(edge(1, -.4, baseline=.9, columns=['synthetic_flow', 'synthetic_pressure']))
        mode = {'match': 'weak' if name == 'D' else 'strong', 'status': 'limited' if name == 'D' else 'complete', 'confidence': 'high'}
        graph['edges'][0]['operating_mode_context'] = mode
        persistence = {'persistent': name == 'C', 'status': 'persistent' if name == 'C' else 'observing'}
        relationship_evidence = {'baseline_sample_size': 48, 'recent_sample_size': 2 if name == 'B' else 48, 'confidence_score': .73, 'correlation_delta': .4 if name == 'D' else .2}
        classification = classify_finding(data_confidence={'rating': 'high'}, sensor_health=[], operating_mode=mode, persistence=persistence, relationship_evidence=relationship_evidence)
        execution = _execution(state=state)
        finding = {'id': 'controlled-finding', 'classification': classification, 'persistence': persistence,
                   'operating_mode': mode, 'contributing_relationships': deepcopy(graph['changed_edges'])}
        finding['measurable_consequence'] = build_measurable_consequence(finding)
        execution['analysis_result']['conditions'] = []
        execution['analysis_result']['insights'] = [] if name == 'A' else [finding]
        execution['analysis_result']['relationships'] = deepcopy(graph['changed_edges'])
        execution['sii_result']['relationship_graph'] = graph
        cases[name] = product_evidence(execution)
    return cases


def invariants(execution):
    analysis = execution['analysis_result']
    return {
        'classification': [item['classification']['type'] for item in analysis['insights']],
        'primary_selection': [item['id'] for item in analysis['relationships']],
        'persistence_decision': [item['persistence'] for item in analysis['insights']],
        'measurable_consequence_status': [item['measurable_consequence']['status'] for item in analysis['insights']],
        'analytical_identity': semantic_digest(analysis),
    }


if __name__ == '__main__':
    import json
    from pathlib import Path
    from unittest.mock import patch
    from app.services.telemetry_result_projection import build_canonical_result_projection
    from test_telemetry_result_projection import _metadata, _scope
    root = Path(__file__).resolve().parents[1]
    cases = []
    for name, execution in review_cases().items():
        with patch('app.services.telemetry_result_projection.relationship_observations', return_value=None):
            before = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope()).product_result
        after = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope()).product_result
        assert before['analysis_result'] == after['analysis_result']
        cases.append({
            'case': name, 'data_origin': 'controlled contract fixture; no customer telemetry',
            'before': {'summary': before['analysis_result']['executive_summary'],
                       'primary_relationships': len(before['analysis_result']['relationships']), 'observation_disclosure': False},
            'after': {'summary': after['analysis_result']['executive_summary'],
                      'primary_relationships': len(after['analysis_result']['relationships']),
                      'relationship_observations': after['relationship_observations']},
            'unchanged': invariants(execution),
        })
    (root / 'docs/reviews/presentation-phase1/cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    (root / 'frontend/tests/fixtures/presentation-phase1.json').write_text(json.dumps([
        {'case': item['case'], 'evidence': item['after']['relationship_observations'], 'unchanged': item['unchanged']}
        for item in cases
    ], indent=2) + '\n')
