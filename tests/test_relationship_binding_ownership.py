"""Regression for borrowed references on real canonical projected assertions."""
from copy import deepcopy
import json

import pytest

from app.engine.sii_engine import evaluate_sii
from app.services.analysis_result_contract import ensure_analysis_result
from app.services.analysis_explanations import build_analysis_explanation, build_relationships
from app.services.relationship_evidence_binding import (
    ASSESSMENT_BINDING, OWNER_REF, SOURCE, REF, REGISTRY, resolve, registry_record, finalize,
)
from test_sii_supplied_reference import contract
from test_relationship_evidence_binding import raw
from test_relationship_temporal_persistence import analyze


@pytest.fixture(scope='module')
def real_result():
    return evaluate_sii(**contract(16))


def owned(assertion, registry, temporal=False):
    return resolve(assertion, registry, authorized_scope=registry['scope'], require_temporal=temporal)


@pytest.mark.parametrize('temporal', [False, True])
def test_real_projected_borrowed_reference_and_reverse_are_rejected(real_result, temporal):
    analysis = real_result['analysis_result']
    registry = analysis[REGISTRY]
    a, b = analysis['relationships'][:2]
    saved = deepcopy((a, b, registry))
    assert a[REF] != b[REF] and a[OWNER_REF] != b[OWNER_REF]
    assert SOURCE not in a and SOURCE not in b
    for original, donor in ((a, b), (b, a)):
        assert owned(original, registry, temporal) is not None
        changed = deepcopy(original)
        changed[REF] = donor[REF]  # The certification attack changes this field only.
        assert {k: v for k, v in changed.items() if k != REF} == {k: v for k, v in original.items() if k != REF}
        assert owned(changed, registry, temporal) is None
        assert owned(original, registry, temporal) is not None
    assert (a, b, registry) == saved


@pytest.mark.parametrize('mutation', ['display', 'rank_group'])
def test_borrowed_ref_cannot_be_rescued_by_presentation_mutations(real_result, mutation):
    registry = real_result[REGISTRY]
    a, b = real_result['analysis_result']['relationships'][:2]
    changed = deepcopy(a)
    changed[REF] = b[REF]
    if mutation == 'display':
        changed['source'], changed['target'] = b['source'], b['target']
        changed['name'] = b.get('name', 'different')
    else:
        changed.update(primary=True, group='other', relationship_importance_score=999)
    assert changed[OWNER_REF] == a[OWNER_REF]
    assert owned(changed, registry) is None


@pytest.mark.parametrize('bad_owner', [None, '', [], {}, 'wrong', 'relationship-source.v1:'+'0'*64])
def test_missing_or_malformed_projected_owner_fails_closed(real_result, bad_owner):
    registry = real_result[REGISTRY]
    changed = deepcopy(real_result['analysis_result']['relationships'][0])
    if bad_owner is None:
        changed.pop(OWNER_REF)
    else:
        changed[OWNER_REF] = bad_owner
    assert owned(changed, registry) is None
    assert owned(changed, registry, True) is None


def test_correct_evidence_with_other_owner_and_correct_owner_with_invalid_evidence(real_result):
    registry = real_result[REGISTRY]
    a, b = real_result['analysis_result']['relationships'][:2]
    changed = deepcopy(a); changed[OWNER_REF] = b[OWNER_REF]
    assert owned(changed, registry) is None
    changed = deepcopy(a); changed[REF] = 'relationship-evidence.v1:'+'0'*64
    assert owned(changed, registry) is None
    # Even a complete raw source payload cannot replace the required owner ref.
    raw_candidate = deepcopy(real_result['compatibility']['relationship_model']['top_relationship_changes'][0])
    assert SOURCE in raw_candidate
    raw_candidate.pop(OWNER_REF)
    assert owned(raw_candidate, registry) is None


def test_same_pair_different_reference_cannot_borrow(real_result):
    args = contract(16)
    for row in args['reference_rows']:
        row['pressure'] += 7  # Same pair/window, different actual reference observations.
    other = evaluate_sii(**args)
    a = real_result['analysis_result']['relationships'][0]
    b = next(item for item in other['analysis_result']['relationships']
             if {item['source'], item['target']} == {a['source'], a['target']})
    registry = deepcopy(real_result[REGISTRY])
    for record in other[REGISTRY]['records'].values():
        registry_record(registry, record)
    assert owned(a, registry)['reference']['reference_dataset_id'] != owned(b, registry)['reference']['reference_dataset_id']
    assert a[OWNER_REF] != b[OWNER_REF]
    saved = deepcopy(registry)
    changed = deepcopy(a); changed[REF] = b[REF]
    assert owned(changed, registry, True) is None
    assert registry == saved


def test_global_projected_owner_cannot_borrow_mode_temporal_reference():
    from app.engine.sii.mode_conditioned_baseline import _conditioned_edge
    source = raw()
    mode = _conditioned_edge(source, left='a', right='b', baseline_correlation=.9,
        recent_correlation=.5, baseline_count=3, recent_count=3,
        recent_mode={'mode_id': 'running', 'features': {'pump_status': 1}},
        selected_rows=[{'a': i, 'b': i, 't': i} for i in range(3)],
        recent_rows=[{'a': i, 'b': 2-i, 't': 10+i} for i in range(3)], timestamp_column='t')
    graph = analyze(mode, mode_conditioned_analysis={'used_global_fallback': False, 'mode_relationships': {'edges': [mode]}})
    model = {'relationship_graph': {'edges': [source]}, 'top_relationship_changes': [deepcopy(source)]}
    registry = finalize(model, graph, scope='site')
    assertion = build_relationships(relationship_model=model)[0]
    assert SOURCE not in assertion
    assert owned(assertion, registry)['temporal']['status'] == 'unavailable'
    mode_ref = graph['edges'][0]['relationship_evidence_id']
    assert registry['records'][mode_ref]['temporal']['status'] == 'available'
    assert assertion[OWNER_REF] != registry['records'][mode_ref]['source']['source_id']
    saved = deepcopy(registry)
    changed = deepcopy(assertion); changed[REF] = mode_ref
    assert owned(changed, registry) is None
    assert owned(changed, registry, True) is None
    assert registry == saved


def test_fallback_projected_owner_cannot_borrow_another_fallback_reference():
    from presentation_phase1_graph_fallback_case import graph_fallback_case
    result = graph_fallback_case()['analysis_result']
    registry = result[REGISTRY]
    a, b = result['relationships'][:2]
    saved = deepcopy(registry)
    for original, donor in ((a, b), (b, a)):
        record = owned(original, registry)
        assert record['basis'] == 'global_relationship_model_failure_fallback'
        assert record['temporal'] == {'status': 'unavailable'}
        assert owned(original, registry, True) is None
        changed = deepcopy(original); changed[REF] = donor[REF]
        assert owned(changed, registry) is None
    assert registry == saved


def test_owner_is_producer_issued_and_copied_through_all_projections(real_result):
    from app.services.upload_persistence import project_result_for_transport
    from app.services.telemetry_result_projection import build_canonical_result_projection
    from test_telemetry_result_projection import _execution, _metadata, _scope
    model = real_result['compatibility']['relationship_model']
    producer_refs = {item[REF]: item[SOURCE]['source_id'] for item in model['top_relationship_changes']}
    assert producer_refs
    producer_bindings = {item[REF]: item[ASSESSMENT_BINDING] for item in model['top_relationship_changes']}
    upload = {**real_result['compatibility'], 'sii_result': real_result, 'analysis_result': real_result['analysis_result']}
    explanation = build_analysis_explanation(upload)
    contributions = [entry for finding in explanation['insights'] for entry in finding.get('contributing_relationships', [])]
    canonical = real_result['analysis_result']
    stored = json.loads(json.dumps(upload))
    transport = project_result_for_transport(stored)
    execution = _execution(); execution['analysis_result']['relationships'] = deepcopy(canonical['relationships'])
    connector = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope()).product_result
    for collection in (model['top_relationship_changes'], explanation['relationships'], contributions,
                       canonical['relationships'], ensure_analysis_result(stored)['relationships'],
                       transport['analysis_result']['relationships'], connector['analysis_result']['relationships']):
        assert collection
        for item in collection:
            assert item[OWNER_REF] == producer_refs[item[REF]]
            assert item[ASSESSMENT_BINDING] == producer_bindings[item[REF]]
    for item in canonical['relationships']:
        assert SOURCE not in item  # No full source payload is added for ownership.


def test_projectors_do_not_reconstruct_missing_owner(real_result):
    from app.services.analysis_explanations import relationship_contribution
    model = deepcopy(real_result['compatibility']['relationship_model'])
    for item in model['top_relationship_changes']:
        item.pop(OWNER_REF)
    projected = build_relationships(relationship_model=model)
    assert all(REF in item and OWNER_REF not in item for item in projected)
    entry = model['top_relationship_changes'][0]
    contribution = relationship_contribution(entry, 0, entry[SOURCE]['columns'])
    assert OWNER_REF not in contribution
    assert owned(projected[0], real_result[REGISTRY]) is None


def test_historical_no_binding_stays_readable_without_reconstruction(monkeypatch):
    from test_sii_evidence_transport import _canonical_result
    historical = _canonical_result()
    saved = deepcopy(historical)
    monkeypatch.setattr('app.services.relationship_evidence_binding.finalize', lambda *a, **kw: pytest.fail('historical finalization'))
    result = ensure_analysis_result(historical)
    assert REGISTRY not in result
    assert all(OWNER_REF not in item and REF not in item for item in result['relationships'])
    assert resolve({'id': 'legacy'}, {REGISTRY: {}}, authorized_scope='result-local') is None
    assert historical == saved


def test_owner_and_evidence_invariant_under_organization_and_retry(real_result):
    original = real_result['analysis_result']['relationships'][0]
    registry = real_result[REGISTRY]
    for changes in ({'group': 'another'}, {'primary': False}, {'relationship_importance_score': -1},
                    {'worker_id': 'other', 'retry_id': 'retry', 'process_id': 5}):
        changed = {**original, **changes}
        assert (changed[OWNER_REF], changed[REF]) == (original[OWNER_REF], original[REF])
        assert owned(changed, registry) == owned(original, registry)
    replay = evaluate_sii(**contract(16))
    assert [(r[OWNER_REF], r[REF]) for r in replay['analysis_result']['relationships']] == [
        (r[OWNER_REF], r[REF]) for r in real_result['analysis_result']['relationships']]
