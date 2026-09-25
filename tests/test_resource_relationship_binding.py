from copy import deepcopy
import json
import subprocess

import pytest

from app.engine.sii.expected_behavior import train_expected_behavior_models, evaluate_expected_behavior
from app.engine.sii.phase4 import _provisional_relationship_memory
from app.services.relationship_evidence_binding import (
    OWNER_REF, REF, ASSESSMENT_BINDING, REGISTRY, SOURCE, finalize, registry_record,
)
from app.services.resource_relationship_binding import (
    LINEAGE, BINDING, ownership, finalize_resources, resolve_resource,
)
from app.services.measurable_consequence import (
    build_measurable_consequence, attach_measurable_consequences, recorded_measurable_consequence,
)
from resource_binding_cases import assessment
from test_measurable_consequence import fixture


def calculate(finding, expected, catalog, registry=None):
    registry = registry or assessment()[1]
    return build_measurable_consequence(finding, expected_behavior=expected,
        signal_catalog=catalog, analysis_run_id='run-1', relationship_registry=registry,
        authorized_scope=registry['scope'])


def test_eligible_numerical_and_existing_gate_invariance_against_committed_adapter():
    namespace = {'__name__': 'baseline_consequence'}
    source = subprocess.check_output(['git', 'show',
        'a922c496fa2baeac63b7c882a640d8e6b58caa90:backend/app/services/measurable_consequence.py'], text=True)
    exec(compile(source, 'baseline_consequence.py', 'exec'), namespace)
    for case in ('eligible', 'context', 'persistence', 'gap', 'quality', 'units', 'window'):
        f, e, c = fixture()
        if case == 'context': f['operating_mode'] = {'match': 'weak'}
        if case == 'persistence': f['persistence'] = {'persistent': False}
        if case == 'gap': c['flow']['max_gap_seconds'] = 0
        if case == 'quality': e['expected_values'][0]['observations'][3]['valid'] = False
        if case == 'units': c['flow']['canonical_unit'] = 'unmapped'
        if case == 'window': f['source_time_ranges'] = []
        # This is a fresh producer variant, not a consumer-side repair.
        finalize_resources(e, assessment()[1], authorized_scope='resource-test')
        before = deepcopy((f, e, c))
        actual = calculate(f, e, c)
        old = namespace['build_measurable_consequence'](f, expected_behavior=e,
            signal_catalog=c, analysis_run_id='run-1')
        actual.get('provenance', {}).pop(BINDING, None)
        assert actual == old, case
        assert (f, e, c) == before


@pytest.mark.parametrize('attack', [
    'different_owner', 'only_ref', 'only_seal', 'only_source', 'resource_tamper',
    'missing_resource_binding', 'missing_finding_binding', 'wrong_scope', 'contribution_union', 'raw_source',
])
def test_no_cross_borrowing_or_repair(attack):
    f, e, c = fixture()
    a, r = assessment()
    b, rb = assessment(columns=('flow', 'other_load'))
    r = deepcopy(r)
    for record in rb['records'].values(): registry_record(r, record)
    saved = deepcopy(r)
    if attack == 'different_owner': f.update(ownership(b))
    if attack == 'only_ref': f[REF] = b[REF]
    if attack == 'only_source': f[OWNER_REF] = b[OWNER_REF]
    if attack == 'only_seal': f[ASSESSMENT_BINDING] = b[ASSESSMENT_BINDING]
    if attack == 'raw_source': f[SOURCE] = deepcopy(b[SOURCE])
    if attack == 'resource_tamper': e['expected_values'][0]['observations'][0]['expected'] = 0
    if attack == 'missing_resource_binding': e['expected_values'][0].pop(BINDING)
    if attack == 'missing_finding_binding': f.pop(ASSESSMENT_BINDING)
    if attack == 'wrong_scope': r['scope'] = 'other-scope'; saved = deepcopy(r)
    if attack == 'contribution_union':
        f['source_relationship_ids'] = []
        f['contributing_relationships'] = [{'id': 'rel-1', **ownership(a)}]
    assert calculate(f, e, c, r)['status'] == 'not_quantifiable'
    assert r == saved


def test_multiple_resources_resolve_only_to_their_explicit_owner():
    f, e, c = fixture()
    b, rb = assessment(columns=('flow', 'other_load'))
    r = deepcopy(assessment()[1])
    for record in rb['records'].values(): registry_record(r, record)
    other = deepcopy(e)
    other['expected_values'][0][LINEAGE] = b[OWNER_REF]
    other['expected_values'][0]['predictor_signals'] = ['other_load']
    finalize_resources(other, r, authorized_scope=r['scope'])
    e['expected_values'].extend(other['expected_values'])
    assert calculate(f, e, c, r)['cumulative_amount'] == pytest.approx(12840)
    f.update(ownership(b))
    assert calculate(f, e, c, r)['cumulative_amount'] == pytest.approx(12840)
    # Persistent A cannot quantify a list containing only B's resource.
    f.update(ownership(assessment()[0]))
    assert calculate(f, other, c, r)['status'] == 'not_quantifiable'


def test_group_ranking_primary_mutations_are_inert():
    f, e, c = fixture()
    before = calculate(f, e, c)
    f.update(group='unrelated', primary=False, rank=999, persistent_columns=['other'],
             contributing_relationships=[{'id': 'unrelated'}])
    e['expected_values'][0].update(group='different', rank=-100, primary=True)
    assert calculate(f, e, c) == before | {
        'provenance': {**before['provenance'], 'expected_behavior': e['expected_values'][0]}}
    assert e['expected_values'][0][BINDING] == fixture()[1]['expected_values'][0][BINDING]


@pytest.mark.parametrize('case', ['no_temporal', 'fallback', 'stale_source', 'ambiguous'])
def test_finalization_never_supplies_unavailable_temporal_authority(case):
    f, e, c = fixture()
    a, r = deepcopy(assessment())
    if case == 'no_temporal': a, r = deepcopy(assessment(1))
    elif case == 'fallback':
        raw = deepcopy(a)
        model = {'relationship_graph': {'edges': [raw]}, 'top_relationship_changes': [raw]}
        r = finalize(model, {'edge_basis': 'global_relationship_model_failure_fallback',
                            'edges': [raw]}, scope='resource-test')
        a = model['top_relationship_changes'][0]
    if case in ('no_temporal', 'fallback'):
        f.update(ownership(a)); e['expected_values'][0][LINEAGE] = a[OWNER_REF]
    if case == 'stale_source': e['expected_values'][0][LINEAGE] = 'old-source'
    if case == 'ambiguous':
        other, ro = assessment(1)
        assert other[OWNER_REF] == a[OWNER_REF]
        for record in ro['records'].values(): registry_record(r, record)
    finalize_resources(e, r, authorized_scope=r['scope'])
    assert calculate(f, e, c, r)['status'] == 'not_quantifiable'


@pytest.mark.parametrize('case', ['missing', 'duplicate', 'other_owner', 'unowned_projection', 'context', 'window', 'persistence'])
def test_original_finding_selection_is_narrow(case):
    f, e, c = fixture()
    output = deepcopy(f)
    originals = [f]
    if case == 'missing': originals = []
    if case == 'duplicate': originals = [f, deepcopy(f)]
    if case == 'other_owner': output.update(ownership(assessment(columns=('flow', 'other_load'))[0]))
    if case == 'unowned_projection': output.pop(ASSESSMENT_BINDING)
    if case == 'context': output['operating_mode'] = {'match': 'weak'}
    if case == 'window': output['source_time_ranges'][0]['current_end'] = 99999
    if case == 'persistence': output['persistence'] = {'persistent': False}
    analysis = {'conditions': [output]}
    attach_measurable_consequences(analysis, source={REGISTRY: assessment()[1],
        'sii_result': {'expected_behavior': e}, 'telemetry_signal_catalog': c}, original_findings=originals)
    assert output['measurable_consequence']['status'] == 'not_quantifiable'


@pytest.mark.parametrize('field', ['conditions', 'insights'])
@pytest.mark.parametrize('case', [
    'raw_source', 'weak_context', 'limited_context', 'missing_context',
    'missing_persistence', 'missing_relationship_ids', 'original_raw_source',
])
def test_attachment_cannot_restore_rejected_finding_authority(field, case):
    original, expected, catalog = fixture()
    if case in ('weak_context', 'limited_context', 'missing_context'):
        original.pop('operating_mode')
        original['finding_confidence_v1'] = {'operating_context': {'status': 'supported'}}
    projected = deepcopy(original)
    if case in ('raw_source', 'original_raw_source'):
        target = original if case == 'original_raw_source' else projected
        target[SOURCE] = deepcopy(assessment(columns=('flow', 'other_load'))[0][SOURCE])
    elif case in ('weak_context', 'limited_context'):
        projected['finding_confidence_v1']['operating_context']['status'] = case.split('_')[0]
    elif case == 'missing_context':
        projected.pop('finding_confidence_v1')
    elif case == 'missing_persistence':
        projected.pop('persistence')
    elif case == 'missing_relationship_ids':
        projected.pop('source_relationship_ids')
    rejected = original if case == 'original_raw_source' else projected
    accepted = projected if case == 'original_raw_source' else original
    assert calculate(accepted, expected, catalog)['status'] == 'quantified'
    assert calculate(rejected, expected, catalog)['status'] == 'not_quantifiable'
    before = deepcopy((original, expected, catalog))
    attach_measurable_consequences({field: [projected]}, source={
        REGISTRY: assessment()[1], 'sii_result': {'expected_behavior': expected},
        'telemetry_signal_catalog': catalog,
    }, original_findings=[original])
    assert projected['measurable_consequence']['status'] == 'not_quantifiable'
    assert (original, expected, catalog) == before


@pytest.mark.parametrize('field', ['conditions', 'insights'])
def test_attachment_preserves_eligible_consequence_exactly(field):
    original, expected, catalog = fixture()
    projected = deepcopy(original)
    direct = calculate(original, expected, catalog)
    attach_measurable_consequences({field: [projected]}, source={
        REGISTRY: assessment()[1], 'sii_result': {'expected_behavior': expected},
        'telemetry_signal_catalog': catalog, 'run_id': 'run-1',
    }, original_findings=[original])
    assert projected['measurable_consequence'] == direct
    assert direct['cumulative_amount'] == pytest.approx(12840)


def test_recorded_historical_consequence_is_read_without_binding_or_reconstruction():
    historic = {'id': 'legacy', 'measurable_consequence': {'status': 'quantified', 'cumulative_amount': 17}}
    saved = deepcopy(historic)
    assert recorded_measurable_consequence(historic, {}) == historic['measurable_consequence']
    assert historic == saved
    f, e, c = fixture()
    for key in (OWNER_REF, REF, ASSESSMENT_BINDING): f.pop(key)
    e['expected_values'][0].pop(BINDING)
    before = deepcopy((f,e,c))
    assert calculate(f,e,c)['status'] == 'not_quantifiable'
    assert (f,e,c) == before


def test_actual_producer_lineage_training_evaluation_and_finalization():
    a, registry = assessment()
    memory = _provisional_relationship_memory({'edges': [a]}, 'running')
    assert next(iter(memory.values()))[LINEAGE] == a[OWNER_REF]
    rows = [{'t': i*60, 'load': 10+i, 'flow': 25+2*i} for i in range(40)]
    models = train_expected_behavior_models(rows=rows, relationship_memory=memory,
        operating_mode='running', timestamp_column='t', source_run_id='synthetic', training_time='fixed')
    assert models and all(m[LINEAGE] == a[OWNER_REF] for m in models.values())
    def evaluate(quality=None, data=None):
        return evaluate_expected_behavior(active_model={'expected_behavior_models': models},
            rows=rows if data is None else data, operating_mode='running',
            data_quality=quality or {'readiness': 'ready'},
            sensor_health={'signals': [{'signal': s, 'health': 'healthy'} for s in ('flow','load')]},
            source_model_version='v1', evaluation_time='fixed', timestamp_column='t',
            config={'max_gap_seconds': 3600})
    output = evaluate()
    assert output['expected_values']
    numerical_before = deepcopy(output)
    finalize_resources(output, registry, authorized_scope=registry['scope'])
    for resource in output['expected_values']:
        assert resolve_resource(resource, a, registry, authorized_scope=registry['scope'])
        resource.pop(BINDING)
    assert output == numerical_before
    assert not evaluate({'readiness': 'not_ready'})['expected_values']
    assert not evaluate(data=rows[:2])['expected_values']
    # Legacy producer inputs remain unbound, even with identical signals.
    legacy = deepcopy(a); legacy.pop(SOURCE)
    old_memory = _provisional_relationship_memory({'edges': [legacy]}, 'running')
    assert next(iter(old_memory.values()))[LINEAGE] is None


def test_training_and_evaluation_math_equal_committed_producer():
    namespace = {'__name__': 'baseline_expected_behavior'}
    source = subprocess.check_output(['git', 'show',
        'a922c496fa2baeac63b7c882a640d8e6b58caa90:backend/app/engine/sii/expected_behavior.py'], text=True)
    exec(compile(source, 'baseline_expected_behavior.py', 'exec'), namespace)
    rows = [{'t': i*60, 'load': 10+i, 'flow': 25+2*i} for i in range(40)]
    kwargs = dict(rows=rows,
        relationship_memory=_provisional_relationship_memory({'edges': [assessment()[0]]}, 'running'),
        operating_mode='running', timestamp_column='t', source_run_id='synthetic', training_time='fixed')
    models = train_expected_behavior_models(**kwargs)
    old_models = namespace['train_expected_behavior_models'](**kwargs)
    def without_lineage(value):
        if isinstance(value, dict):
            return {k: without_lineage(v) for k,v in value.items() if k != LINEAGE}
        if isinstance(value, list): return [without_lineage(v) for v in value]
        return value
    assert without_lineage(models) == old_models
    kwargs = dict(rows=rows, operating_mode='running', data_quality={'readiness': 'ready'},
        sensor_health={'signals': [{'signal': s, 'health': 'healthy'} for s in ('flow','load')]},
        source_model_version='v1', evaluation_time='fixed', timestamp_column='t')
    actual = evaluate_expected_behavior(active_model={'expected_behavior_models': models}, **kwargs)
    old = namespace['evaluate_expected_behavior'](active_model={'expected_behavior_models': old_models}, **kwargs)
    assert without_lineage(actual) == old


@pytest.mark.parametrize('key,value', [(LINEAGE, []), ('observations', [{'observed': float('nan')}])])
def test_malformed_resource_metadata_fails_closed_without_failing_analysis(key, value):
    f, e, c = fixture()
    e['expected_values'][0][key] = value
    finalize_resources(e, assessment()[1], authorized_scope='resource-test')
    assert BINDING not in e['expected_values'][0]
    assert calculate(f, e, c)['status'] == 'not_quantifiable'


def test_registry_membership_order_and_json_transport_do_not_change_resource_owner():
    f, e, c = fixture()
    before = deepcopy(e)
    registry = deepcopy(assessment()[1])
    for record in assessment(columns=('flow', 'other_load'))[1]['records'].values():
        registry_record(registry, record)
    registry['records'] = dict(reversed(list(registry['records'].items())))
    finalize_resources(e, registry, authorized_scope=registry['scope'])
    assert e == before
    wire = json.loads(json.dumps(e))
    assert calculate(f, wire, c, registry)['cumulative_amount'] == pytest.approx(12840)
