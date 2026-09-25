"""Preserve the engine's safe graph-fallback basis without exposing its diagnostics."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.services.output_semantics import canonical_json
from app.services.relationship_observation_projection import relationship_observations, MAX_BYTES, LIMIT
from app.services.telemetry_result_projection import build_canonical_result_projection
from app.services.upload_persistence import project_result_for_transport
from presentation_phase1_graph_fallback_case import graph_fallback_case, graph_fallback_invariants
from test_telemetry_result_projection import _execution, _metadata, _scope

BASIS = 'global_relationship_model_failure_fallback'


def test_real_engine_graph_failure_basis_survives_every_transport(client, monkeypatch):
    from app.routers import data
    from app.services import telemetry_result_projection
    upload = graph_fallback_case()
    original = deepcopy(upload)
    sii = upload['sii_result']
    assert sii['relationship_graph']['edge_basis'] == BASIS
    assert sii['relationship_graph']['phase_2_status']['status'] == 'failed'
    assert 'EXCEPTION_CANARY' in json.dumps(sii['relationship_graph']['phase_2_status'])
    expected = relationship_observations(sii)
    assert expected['coverage']['displayed'] == 3
    assert expected['comparison_qualification']['edge_basis'] == BASIS
    encoded = json.dumps(expected)
    for unsafe in ('CANARY', 'RuntimeError', 'phase_2_status', '/internal/', 'traceback'):
        assert unsafe not in encoded

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

    execution = _execution()
    execution['sii_result']['relationship_graph'] = deepcopy(sii['relationship_graph'])
    execution['sii_result']['operating_modes'] = deepcopy(sii['operating_modes'])
    saved = deepcopy(execution)
    connector = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope()).product_result
    with monkeypatch.context() as context:
        context.setattr(telemetry_result_projection, 'relationship_observations', lambda _: None)
        before = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope()).product_result
    assert connector['relationship_observations'] == expected
    assert connector['analysis_result'] == before['analysis_result']
    assert connector['identity'] == before['identity']
    assert execution == saved
    assert upload == original
    assert graph_fallback_invariants(upload) == graph_fallback_invariants(original)
    retained = json.loads((Path(__file__).resolve().parents[1] / 'frontend/tests/fixtures/presentation-phase1-graph-fallback.json').read_text())
    assert expected == retained['evidence']
    assert graph_fallback_invariants(upload) == retained['invariants']


def test_graph_fallback_basis_is_not_inferred_and_remains_bounded_deterministic():
    sii = graph_fallback_case()['sii_result']
    def reverse(value):
        if isinstance(value, dict):
            return {key: reverse(child) for key, child in reversed(list(value.items()))}
        if isinstance(value, list):
            return [reverse(child) for child in value]
        return value
    graph = sii['relationship_graph']
    edge = graph['edges'][0]
    edge['supporting_windows'] = [{
        'observed_at': '2026-07-01T00:01:00Z',
        'source_rows': [{'window': '測' * 64, 'source_row': i, 'timestamp': '測' * 64} for i in range(4)],
    } for _ in range(8)]
    graph['edges'] = [deepcopy(edge) for _ in range(20)]
    projected = relationship_observations(sii)
    assert projected['comparison_qualification']['edge_basis'] == BASIS
    assert len(canonical_json(projected).encode('utf-8')) <= MAX_BYTES == 48 * 1024
    assert 0 < projected['coverage']['displayed'] < LIMIT == 12
    assert projected['coverage']['displayed'] + projected['coverage']['omitted'] == 20
    altered = reverse(sii)
    altered['runtime_metadata'] = {'worker_id': 'other', 'retry_id': 'other', 'request_time': '2099'}
    assert canonical_json(projected) == canonical_json(relationship_observations(altered))
    for unknown in (None, 'unknown_basis', 'RuntimeError: SECRET_CANARY'):
        graph['edge_basis'] = unknown
        assert 'edge_basis' not in relationship_observations(sii)['comparison_qualification']
    del graph['edge_basis']
    assert 'edge_basis' not in relationship_observations(sii)['comparison_qualification']
    assert relationship_observations({}) is None
