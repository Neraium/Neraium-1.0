"""Final-assessment substitution attacks; records remain intact during attacks."""
from copy import deepcopy
import json
from unittest.mock import patch
import pytest
from app.engine.sii_engine import evaluate_sii
from app.services.relationship_evidence_binding import (
    ASSESSMENT_BINDING, OWNER_REF, REF, REGISTRY, SOURCE, finalize, resolve, registry_record,
)
from test_sii_supplied_reference import contract
from test_relationship_evidence_binding import produced


def check_attacks(a, b, registry):
    saved = deepcopy(registry)
    for original, donor in ((a, b), (b, a)):
        assert resolve(original, registry, authorized_scope=registry['scope'])
        attack = deepcopy(original)
        attack[REF] = donor[REF]
        for temporal in (False, True):
            assert resolve(attack, registry, authorized_scope=registry['scope'], require_temporal=temporal) is None
        assert resolve(original, registry, authorized_scope=registry['scope'])
    assert registry == saved


def test_actual_same_source_success_and_failure_assessment_substitution():
    success = evaluate_sii(**contract(16))
    with patch('app.engine.sii_engine.analyze_relationship_graph', side_effect=RuntimeError('controlled failure')):
        failure = evaluate_sii(**contract(16))
    a = success['analysis_result']['relationships'][0]
    f = next(x for x in failure['analysis_result']['relationships'] if x[OWNER_REF] == a[OWNER_REF])
    assert a[REF] != f[REF] and a[ASSESSMENT_BINDING] != f[ASSESSMENT_BINDING]
    registry = deepcopy(success[REGISTRY])
    for record in failure[REGISTRY]['records'].values():
        registry_record(registry, record)
    assert resolve(a, registry, authorized_scope=registry['scope'], require_temporal=True)
    own = resolve(f, registry, authorized_scope=registry['scope'])
    assert own['basis'] == 'global_relationship_model_failure_fallback'
    assert own['temporal']['status'] == 'unavailable'
    assert resolve(f, registry, authorized_scope=registry['scope'], require_temporal=True) is None
    check_attacks(a, f, registry)
    wrong_seal = deepcopy(a)
    wrong_seal[ASSESSMENT_BINDING] = f[ASSESSMENT_BINDING]
    assert resolve(wrong_seal, registry, authorized_scope=registry['scope']) is None


@pytest.mark.parametrize('mutation', ['reference', 'context', 'units', 'history'])
def test_same_source_different_final_scope_cannot_be_borrowed(mutation):
    model, graph, registry = produced(8)
    changed = deepcopy(graph)
    e = changed['edges'][0]
    state = next(iter(changed['relationship_persistence_state'].values()))
    if mutation == 'reference':
        e['reference_dataset_id'] = 'other-reference'
        state['identity']['reference_dataset_id'] = 'other-reference'
    elif mutation == 'context':
        e['operating_mode_context'] = {'match': 'weak'}
    elif mutation == 'units':
        e['signal_units'] = {'a': 'other', 'b': 'unit'}
        state['identity']['signal_units'] = e['signal_units']
    else:
        state['observations'][0]['source_dataset_id'] = 'different-history-source'
    other_model = deepcopy(model)
    other_registry = finalize(other_model, changed, scope=registry['scope'])
    a, b = model['top_relationship_changes'][0], other_model['top_relationship_changes'][0]
    assert a[OWNER_REF] == b[OWNER_REF]
    assert a[REF] != b[REF] and a[ASSESSMENT_BINDING] != b[ASSESSMENT_BINDING]
    for record in other_registry['records'].values(): registry_record(registry, record)
    check_attacks(a, b, registry)


@pytest.mark.parametrize('bad', [None, '', [], {}, 'wrong', 'relationship-assessment-binding.v1:' + '0'*64])
def test_missing_malformed_or_tampered_seal_fails_closed(bad):
    model, _, registry = produced(8)
    a = deepcopy(model['top_relationship_changes'][0])
    if bad is None: a.pop(ASSESSMENT_BINDING)
    else: a[ASSESSMENT_BINDING] = bad
    assert SOURCE in a  # Full source evidence cannot substitute for the seal.
    assert resolve(a, registry, authorized_scope=registry['scope']) is None
    assert resolve(a, registry, authorized_scope=registry['scope'], require_temporal=True) is None


def test_seal_retry_order_organization_and_projection_absence():
    from app.services.analysis_explanations import build_relationships
    model, graph, registry = produced(8)
    a = model['top_relationship_changes'][0]
    repeated, _, repeated_registry = produced(8)
    assert a == repeated['top_relationship_changes'][0] and registry == repeated_registry
    changed = deepcopy(model)
    changed['top_relationship_changes'][0].update(group='other', primary=False, rank=999)
    changed['top_relationship_changes'].insert(0, {'unrelated': True})
    finalize(changed, graph, scope=registry['scope'])
    for key in (OWNER_REF, REF, ASSESSMENT_BINDING): assert changed['top_relationship_changes'][1][key] == a[key]
    replay = json.loads(json.dumps(dict(reversed(list(a.items())))))
    assert resolve(replay, registry, authorized_scope=registry['scope'])
    legacy = deepcopy(model)
    legacy['top_relationship_changes'][0].pop(ASSESSMENT_BINDING)
    projected = build_relationships(relationship_model=legacy)
    assert all(ASSESSMENT_BINDING not in item for item in projected)
    assert all(resolve(item, registry, authorized_scope=registry['scope']) is None for item in projected)
