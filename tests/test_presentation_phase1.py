"""Presentation-only regressions using controlled data and retained safe contracts."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.engine.sii_engine import evaluate_sii
from app.services.output_semantics import canonical_json, semantic_digest
from app.services.relationship_observation_projection import relationship_observations
from app.services.telemetry_result_projection import build_canonical_result_projection
from app.services.upload_persistence import project_result_for_transport
from test_relationship_temporal_persistence import analyze, edge, sequence
from test_sii_evidence_transport import _canonical_result
from test_sii_supplied_reference import contract
from test_telemetry_result_projection import _execution, _metadata, _scope


def graph_for(deltas):
    observations, _ = sequence(deltas, columns=['synthetic_flow', 'synthetic_pressure'])
    return {'edges': [observations[-1]], 'changed_edges': [item for item in observations[-1:] if item['promoted_changed_edge']]}


@pytest.mark.parametrize('deltas', [[-.2], [-.2] * 6, [-.2, .2] * 4, [-.2] * 6 + [0], [-.14] * 8])
def test_dimensions_are_copied_without_promoting_or_reducing(deltas):
    graph = graph_for(deltas)
    original = deepcopy(graph)
    projected = relationship_observations({'relationship_graph': graph})
    observed = projected['observations'][0]
    for field in ('change_type', 'single_window_change_type', 'persistent_relationship_change',
                  'promoted_changed_edge', 'temporal_persistence_status', 'temporal_persistence_direction',
                  'temporal_persistence_observations', 'temporal_persistence_supporting_observations'):
        assert observed[field] == graph['edges'][0][field]
    assert observed['recurrence']['supported'] == graph['edges'][0]['recurrence_evidence']['supported']
    assert graph == original
    if len(deltas) == 1:
        assert not observed['promoted_changed_edge']
        assert observed['temporal_persistence_supporting_observations'] == 1
        assert not observed['persistent_relationship_change']


@pytest.mark.parametrize('state', ['stable', 'insufficient', 'material'])
def test_both_transports_keep_analysis_selection_consequence_and_identity(state):
    execution = _execution(state=state)
    execution['sii_result']['relationship_graph'] = graph_for([-.2] * (6 if state == 'material' else 1))
    original = deepcopy(execution)
    connector = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope()).product_result
    assert connector['analysis_result']['executive_summary'] == original['analysis_result']['executive_summary']
    for field in ('relationships', 'conditions', 'insights'):
        assert connector['analysis_result'][field] == original['analysis_result'][field]
    assert connector['identity']['payload_digest'] == _metadata()['payload_digest']
    assert connector['product_boundary'] == {'mode': 'read_only', 'control_actions': []}
    assert connector['relationship_observations']['observations']
    assert execution == original
    # Use a retained valid upload contract; loading JSON models a stored-result read.
    upload = _canonical_result()
    upload['sii_result']['relationship_graph'] = execution['sii_result']['relationship_graph']
    # Equal transport inputs must include the same recorded comparison context.
    upload['sii_result']['operating_modes'] = deepcopy(execution['sii_result'].get('operating_modes', {}))
    from app.services.analysis_result_contract import build_analysis_result
    upload['analysis_result'] = build_analysis_result(upload)
    retained = json.loads(json.dumps(upload))
    transported = project_result_for_transport(retained)
    assert transported['analysis_result'] == retained['analysis_result']
    assert transported['relationship_observations'] == connector['relationship_observations']
    assert retained == upload


def test_context_limitation_and_missing_history_remain_explicit():
    graph = analyze(edge(1), operating_mode={'status': 'limited', 'match': 'not_enough_context'})
    projected = relationship_observations({'relationship_graph': graph})
    assert projected['observations'][0]['operating_context']['match'] == 'not_enough_context'
    assert not projected['observations'][0]['promoted_changed_edge']
    assert relationship_observations({}) is None
    assert relationship_observations({'relationship_graph': {'changed_edges': []}}) is None
    assert relationship_observations({'relationship_graph': {'edges': [{}]}})['coverage']['eligible'] is None
    historical = _execution()
    result = build_canonical_result_projection(historical, artifact_metadata=_metadata(), scope=_scope()).product_result
    assert 'relationship_observations' not in result


def test_bounds_selection_provenance_and_unsafe_fields():
    graph = graph_for([-.2])
    graph['edges'] *= 20
    graph = deepcopy(graph)
    item = graph['edges'][0]
    for target in (item, item['time_window'], item['operating_mode_context'], item['recurrence_evidence'], item['supporting_windows'][0], item['supporting_windows'][0]['source_rows'][0]):
        target.update(credentials='CREDENTIAL_CANARY', runtime_metadata={'worker': 'RUNTIME_CANARY'}, forensic_evidence='FORENSIC_CANARY', error='ERROR_CANARY')
    result = relationship_observations({'relationship_graph': graph})
    assert result['coverage']['evaluated'] == 20
    assert result['coverage']['displayed'] == 12
    assert result['coverage']['omitted'] == 8
    assert result['selection'] == 'engine_order_first_12_not_primary_ranking'
    observed = result['observations'][0]
    assert observed['source_path'] == 'sii_result.relationship_graph.edges[0]'
    assert observed['time_window'] == {key: value for key, value in item['time_window'].items() if key in ('baseline_start', 'baseline_end', 'current_start', 'current_end')}
    assert observed['supporting_windows'][0]['source_rows'][0]['source_row'] == item['supporting_windows'][0]['source_rows'][0]['source_row']
    assert 'CANARY' not in json.dumps(result)
    assert 'measurable_consequence' not in json.dumps(result)


def test_determinism_ignores_mapping_order_and_volatile_execution_fields():
    sii = {'relationship_graph': graph_for([-.2] * 6)}
    def reverse(value):
        if isinstance(value, dict):
            return {key: reverse(child) for key, child in reversed(list(value.items()))}
        if isinstance(value, list):
            return [reverse(child) for child in value]
        return value
    changed = reverse(sii)
    changed.update(runtime_metadata={'request_time': '2099', 'worker': 'other'}, retry_id='other')
    assert canonical_json(relationship_observations(sii)) == canonical_json(relationship_observations(changed))


def test_real_engine_classifications_and_semantic_identity_match_retained_baseline():
    retained = json.loads((Path(__file__).parent / 'fixtures/presentation_phase1_invariants.json').read_text())
    for case in retained:
        result = evaluate_sii(**contract(case['rows']))
        before = semantic_digest(result['analysis_result'])
        original = deepcopy(result)
        upload = {'sii_result': result, 'analysis_result': result['analysis_result']}
        transported = project_result_for_transport(upload)
        assert before == case['analytical_digest']
        assert semantic_digest(transported['analysis_result']) == before
        assert result == original
        assert [item['classification']['type'] for item in result['analysis_result']['insights']] == case['classifications']
        assert transported['relationship_observations']['observations']


def test_retained_review_cases_match_transport_and_analytical_invariants(monkeypatch):
    from presentation_phase1_cases import review_cases, invariants
    from app.services import telemetry_result_projection
    root = Path(__file__).resolve().parents[1]
    retained = json.loads((root / 'docs/reviews/presentation-phase1/cases.json').read_text())
    frontend = json.loads((root / 'frontend/tests/fixtures/presentation-phase1.json').read_text())
    for expected, ui, (name, execution) in zip(retained, frontend, review_cases().items(), strict=True):
        original = deepcopy(execution)
        projected = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope()).product_result
        with monkeypatch.context() as context:
            context.setattr(telemetry_result_projection, 'relationship_observations', lambda _: None)
            before = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope()).product_result
        assert projected['analysis_result'] == before['analysis_result']
        assert projected['identity'] == before['identity']
        assert invariants(execution) == expected['unchanged']
        # Preserve the original A-D review artifacts as pre-correction history.
        original_fields = {key: value for key, value in projected['relationship_observations'].items()
                           if key != 'comparison_qualification'}
        assert original_fields == expected['after']['relationship_observations'] == ui['evidence']
        assert execution == original
        if name == 'B':
            assert expected['unchanged']['classification'] == ['insufficient_evidence']
        if name == 'C':
            assert expected['unchanged']['persistence_decision'][0]['persistent'] is True
            assert projected['relationship_observations']['observations'][0]['promoted_changed_edge'] is True
        if name == 'D':
            assert expected['unchanged']['classification'] == ['context_limited_relationship_change']


def test_disclosure_byte_bound_keeps_whole_observations_and_reports_omissions():
    from app.services.relationship_observation_projection import MAX_BYTES
    graph = graph_for([-.2] * 6)
    item = graph['edges'][0]
    item['supporting_windows'] = [deepcopy(item['supporting_windows'][0]) for _ in range(8)]
    for window in item['supporting_windows']:
        window['source_dataset_id'] = '測' * 64
        window['source_rows'] = [{'window': '測' * 64, 'timestamp': '測' * 64, 'source_row': n} for n in range(4)]
    graph['edges'] = [deepcopy(item) for _ in range(12)]
    projected = relationship_observations({'relationship_graph': graph})
    assert len(json.dumps(projected, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()) <= MAX_BYTES
    assert projected['coverage']['omitted'] > 0
    assert projected['coverage']['displayed'] + projected['coverage']['omitted'] == 12
    assert len(projected['observations'][0]['supporting_windows']) == 8


def test_explicit_analysis_routes_expose_observations_without_rewriting_saved_result(client, monkeypatch):
    from app.routers import data
    stored = _canonical_result()
    stored['sii_result']['relationship_graph'] = graph_for([-.2])
    original = deepcopy(stored)
    monkeypatch.setattr(data, 'read_completed_analysis_by_id', lambda _: deepcopy(stored))
    monkeypatch.setattr(data, 'read_completed_analysis', lambda *_args, **_kwargs: deepcopy(stored))
    monkeypatch.setattr(data, 'read_evidence_package_by_analysis_id', lambda _: None)
    monkeypatch.setattr(data, '_exact_baseline_detail', lambda *_: {'system_id': 'system1'})
    for path in ('/api/data/analyses/phase1', '/api/data/portfolios/default/systems/system1/baselines/baseline1/analyses/phase1'):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()['relationship_observations']['observations'][0]['promoted_changed_edge'] is False
    assert stored == original


def test_supported_recurrence_stays_distinct_from_persistence_and_promotion():
    from test_relationship_recurrence import replay
    graph = replay(([-.22] * 3 + [0.0] * 4) * 3)[-1]
    before = deepcopy(graph)
    observed = relationship_observations({'relationship_graph': graph})['observations'][0]
    assert observed['recurrence']['supported'] is True
    assert observed['recurrence']['episode_count'] == 3
    assert observed['temporal_persistence_supported'] is False
    assert observed['persistent_relationship_change'] is False
    assert observed['promoted_changed_edge'] is False
    assert graph == before
