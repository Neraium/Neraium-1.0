"""Narrow correction: preserve recorded like-mode qualification at presentation boundaries."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.services.output_semantics import canonical_json, semantic_digest
from app.services.relationship_observation_projection import relationship_observations, MAX_BYTES
from app.services.telemetry_result_projection import build_canonical_result_projection
from app.services.upload_persistence import project_result_for_transport
from presentation_phase1_context_case import context_fallback_case, context_invariants
from test_telemetry_result_projection import _execution, _metadata, _scope

EXPECTED = {
    'edge_basis': 'global_relationship_model',
    'mode_conditioned_baseline': {
        'status': 'limited', 'used_global_fallback': True,
        'fallback_reason': 'insufficient_recent_mode_rows',
    },
}


def test_real_engine_fallback_across_all_disclosure_routes_preserves_identity(client, monkeypatch):
    from app.routers import data
    from app.services import telemetry_result_projection
    upload = context_fallback_case()
    original = deepcopy(upload)
    sii = upload['sii_result']
    assert sii['operating_modes']['match'] == 'strong'
    assert sii['operating_modes']['mode_conditioned_baseline']['status'] == 'limited'
    assert sii['operating_modes']['mode_conditioned_baseline']['used_global_fallback'] is True
    assert sii['operating_modes']['mode_conditioned_baseline']['fallback_reason'] == 'insufficient_recent_mode_rows'
    assert sii['relationship_graph']['edge_basis'] == 'global_relationship_model'
    expected = relationship_observations(sii)
    assert expected['comparison_qualification'] == EXPECTED
    assert expected['observations'][0]['operating_context']['match'] == 'strong'

    # No retrieval may rerun analysis or modify the retained result.
    monkeypatch.setattr('app.engine.sii_engine.evaluate_sii', lambda **_: pytest.fail('retrieval reran analysis'))
    compact = project_result_for_transport(upload)
    assert compact['relationship_observations'] == expected
    assert compact['analysis_result'] == original['analysis_result']
    monkeypatch.setattr(data, 'read_completed_analysis_by_id', lambda _: deepcopy(upload))
    monkeypatch.setattr(data, 'read_completed_analysis', lambda *_args, **_kwargs: deepcopy(upload))
    monkeypatch.setattr(data, 'read_evidence_package_by_analysis_id', lambda _: None)
    monkeypatch.setattr(data, '_exact_baseline_detail', lambda *_: {'system_id': 'system1'})
    for path in ('/api/data/analyses/phase1', '/api/data/portfolios/default/systems/system1/baselines/baseline1/analyses/phase1'):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()['relationship_observations'] == expected
        assert response.json()['analysis_result'] == original['analysis_result']

    # Place the same real-engine graph/context inside an existing connector
    # transport identity fixture; keep its independently validated lineage intact.
    execution = _execution()
    execution['sii_result']['relationship_graph'] = deepcopy(sii['relationship_graph'])
    execution['sii_result']['operating_modes'] = deepcopy(sii['operating_modes'])
    saved_execution = deepcopy(execution)
    connector = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope()).product_result
    with monkeypatch.context() as context:
        context.setattr(telemetry_result_projection, 'relationship_observations', lambda _: None)
        before = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope()).product_result
    assert connector['relationship_observations'] == expected
    assert connector['analysis_result'] == before['analysis_result']
    assert connector['identity'] == before['identity']
    assert execution == saved_execution
    assert upload == original
    assert context_invariants(upload) == context_invariants(original)

    retained = json.loads((Path(__file__).resolve().parents[1] / 'frontend/tests/fixtures/presentation-phase1-context-fallback.json').read_text())
    assert expected == retained['evidence']
    assert context_invariants(upload) == retained['invariants']


@pytest.mark.parametrize('conditioned', [{}, {'used_global_fallback': False}, {'status': 'limited'}, {'fallback_reason': None}])
def test_partial_historical_fields_are_never_inferred(conditioned):
    sii = {'relationship_graph': {'edges': []}, 'operating_modes': {'mode_conditioned_baseline': conditioned}}
    result = relationship_observations(sii)
    if conditioned:
        assert result['comparison_qualification'] == {'mode_conditioned_baseline': conditioned}
    else:
        assert 'comparison_qualification' not in result
    # A recorded global basis alone cannot establish whether fallback happened.
    sii['relationship_graph']['edge_basis'] = 'global_relationship_model'
    result = relationship_observations(sii)
    assert result['comparison_qualification'].get('mode_conditioned_baseline', {}) == conditioned


def test_unknown_and_unsafe_qualification_values_are_excluded():
    sii = {'relationship_graph': {'edges': [], 'edge_basis': 'RUNTIME_CANARY'}, 'operating_modes': {
        'mode_conditioned_baseline': {
            'status': 'failed', 'used_global_fallback': True,
            'fallback_reason': 'RuntimeError: credential=SECRET_CANARY database=INTERNAL_CANARY',
            'reason': 'ERROR_CANARY', 'limitations': ['FORENSIC_CANARY'],
            'worker_id': 'WORKER_CANARY', 'authorization': 'AUTH_CANARY',
        },
    }}
    result = relationship_observations(sii)
    assert result['comparison_qualification'] == {'mode_conditioned_baseline': {'status': 'failed', 'used_global_fallback': True}}
    assert 'CANARY' not in json.dumps(result)
    for invalid in ('true', 1, None, {}, []):
        sii['operating_modes']['mode_conditioned_baseline']['used_global_fallback'] = invalid
        assert 'used_global_fallback' not in relationship_observations(sii)['comparison_qualification']['mode_conditioned_baseline']


def test_qualification_serialization_and_bounds_remain_deterministic():
    upload = context_fallback_case()
    sii = upload['sii_result']
    original = deepcopy(sii)
    projected = relationship_observations(sii)
    def reverse(value):
        if isinstance(value, dict):
            return {key: reverse(child) for key, child in reversed(list(value.items()))}
        if isinstance(value, list):
            return [reverse(child) for child in value]
        return value
    altered = reverse(sii)
    altered['runtime_metadata'] = {'worker_id': 'other', 'request_time': '2099', 'retry_id': 'other'}
    assert canonical_json(projected) == canonical_json(relationship_observations(altered))
    assert semantic_digest(sii) == semantic_digest(original)
    edge = sii['relationship_graph']['edges'][0]
    edge['supporting_windows'] = [{
        'observed_at': '2026-07-01T00:01:00Z',
        'source_rows': [{'window': '測' * 64, 'source_row': i, 'timestamp': '測' * 64} for i in range(4)],
    } for _ in range(8)]
    sii['relationship_graph']['edges'] = [deepcopy(edge) for _ in range(20)]
    bounded = relationship_observations(sii)
    assert len(canonical_json(bounded).encode('utf-8')) <= MAX_BYTES
    assert 0 < bounded['coverage']['displayed'] < 12
    assert bounded['coverage']['displayed'] + bounded['coverage']['omitted'] == 20
    assert bounded['comparison_qualification'] == EXPECTED
    assert canonical_json(bounded) == canonical_json(relationship_observations(reverse(sii)))
