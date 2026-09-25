"""Producer binding only: no downstream authority decisions are changed."""
from copy import deepcopy
import json
import pytest

from app.engine.sii_engine import evaluate_sii
from app.engine.sii.mode_conditioned_baseline import _conditioned_edge
from app.services.relationship_evidence_binding import (
    ASSESSMENT_BINDING, SOURCE, OWNER_REF, REF, REGISTRY, VERSION, digest, source_evidence, evidence_record,
    finalize, registry_record, resolve,
)
from app.services.analysis_result_contract import build_analysis_result, ensure_analysis_result
from test_relationship_temporal_persistence import edge, analyze
from test_sii_supplied_reference import contract


def raw(day=1, delta=-.22, columns=('a', 'b')):
    result = edge(day, delta, columns=list(columns))
    result[SOURCE] = source_evidence(result, columns=columns,
        baseline_rows=[{columns[0]: 1., columns[1]: 2., 't': 0}],
        current_rows=[{columns[0]: 2., columns[1]: 1., 't': day}],
        timestamp_column='t', units={c: 'unit' for c in columns})
    return result


def produced(history=1):
    state = None
    for day in range(1, history + 1):
        source = raw(day)
        graph = analyze(source, state)
        state = graph['relationship_persistence_state']
    model = {'relationship_graph': {'edges': [source]}, 'top_relationship_changes': [deepcopy(source)]}
    registry = finalize(model, graph, scope='authorized-site-A')
    return model, graph, registry


def test_retry_serialization_and_read_only_resolution():
    a, graph, registry = produced(8)
    b, _, registry2 = produced(8)
    assert registry == registry2
    assertion = a['top_relationship_changes'][0]
    original = deepcopy(registry)
    record = resolve(assertion, json.loads(json.dumps(registry)), authorized_scope='authorized-site-A', require_temporal=True)
    assert record['temporal']['assessment']['persistent_relationship_change'] is True
    assert assertion[REF] == b['top_relationship_changes'][0][REF]
    assert assertion[ASSESSMENT_BINDING] == b['top_relationship_changes'][0][ASSESSMENT_BINDING]
    assert registry == original


@pytest.mark.parametrize('mutation', ['reference', 'context', 'units', 'history', 'scope'])
def test_authority_scope_changes_id(mutation):
    _, graph, registry = produced(8)
    before = next(iter(registry['records']))
    changed = deepcopy(graph)
    scope = 'authorized-site-A'
    e = changed['edges'][0]
    if mutation == 'reference':
        e['reference_dataset_id'] = 'different-reference'
        next(iter(changed['relationship_persistence_state'].values()))['identity']['reference_dataset_id'] = 'different-reference'
    elif mutation == 'context': e['operating_mode_context'] = {'match': 'weak'}
    elif mutation == 'units':
        e['signal_units'] = {'a': 'other', 'b': 'unit'}
        next(iter(changed['relationship_persistence_state'].values()))['identity']['signal_units'] = e['signal_units']
    elif mutation == 'history':
        next(iter(changed['relationship_persistence_state'].values()))['observations'][0]['source_dataset_id'] = 'different-source'
    else: scope = 'authorized-site-B'
    assert evidence_record(e, changed, scope)['evidence_id'] != before


def test_full_observations_missingness_windows_and_symmetric_identity():
    e = raw()
    kwargs = dict(columns=['a', 'b'], baseline_rows=[{'a': 1, 'b': 2}, {'a': None, 'b': 3}],
                  current_rows=[{'a': 2, 'b': 1}], timestamp_column=None)
    first = source_evidence(e, **kwargs)
    assert first == source_evidence(e, **{**kwargs, 'columns': ['b', 'a']})
    changed = deepcopy(kwargs); changed['baseline_rows'][1]['a'] = 4
    assert first['source_id'] != source_evidence(e, **changed)['source_id']
    changed = deepcopy(e); changed['time_window']['baseline_start'] = '2025-11-01'
    assert first['source_id'] != source_evidence(changed, **kwargs)['source_id']
    renamed = {'columns': ['c', 'b'], 'baseline_rows': [{'c': 1, 'b': 2}], 'current_rows': [{'c': 2, 'b': 1}], 'timestamp_column': None}
    e['display_columns'] = ['duplicate', 'duplicate']
    assert first['source_id'] != source_evidence(e, **renamed)['source_id']


def test_group_primary_rank_and_edge_order_are_not_authority():
    model, graph, original = produced(8)
    expected = model['top_relationship_changes'][0][REF]
    expected_owner = model['top_relationship_changes'][0][OWNER_REF]
    for field, value in [('group', 'other'), ('primary', False), ('relationship_importance_score', 999), ('display_columns', ['other', 'other'])]:
        changed = deepcopy(model)
        changed['top_relationship_changes'][0][field] = value
        changed['top_relationship_changes'].insert(0, {'relationship': 'unrelated'})
        registry = finalize(changed, deepcopy(graph), scope='authorized-site-A')
        assert changed['top_relationship_changes'][1][REF] == expected
        assert changed['top_relationship_changes'][1][OWNER_REF] == expected_owner
        assert registry == original


def test_mode_recalculation_cannot_inherit_global_lineage():
    global_edge = raw()
    conditioned = _conditioned_edge(global_edge, left='a', right='b', baseline_correlation=.9,
        recent_correlation=.5, baseline_count=3, recent_count=3,
        recent_mode={'mode_id': 'running', 'features': {'pump_status': 1}},
        selected_rows=[{'a': i, 'b': i, 't': i} for i in range(3)],
        recent_rows=[{'a': i, 'b': 2-i, 't': 10+i} for i in range(3)], timestamp_column='t')
    assert conditioned[SOURCE]['source_id'] != global_edge[SOURCE]['source_id']
    graph = analyze(conditioned, mode_conditioned_analysis={'used_global_fallback': False, 'mode_relationships': {'edges': [conditioned]}})
    model = {'relationship_graph': {'edges': [global_edge]}, 'top_relationship_changes': [deepcopy(global_edge)]}
    registry = finalize(model, graph, scope='site')
    record = resolve(model['top_relationship_changes'][0], registry, authorized_scope='site')
    assert record['basis'] == 'global_relationship_model'
    assert record['temporal']['status'] == 'unavailable'
    assert record['evidence_id'] != graph['edges'][0]['relationship_evidence_id']
    forged = deepcopy(conditioned); forged[SOURCE] = global_edge[SOURCE]
    with pytest.raises(ValueError): evidence_record(forged, graph, 'site')


def test_failure_fallback_binds_without_temporal_or_errors():
    from presentation_phase1_graph_fallback_case import graph_fallback_case, FAILURE_TEXT
    upload = graph_fallback_case()
    registry = upload['sii_result'][REGISTRY]
    candidate = upload['sii_result']['compatibility']['relationship_model']['top_relationship_changes'][0]
    record = resolve(candidate, registry, authorized_scope=registry['scope'])
    assert record['basis'] == 'global_relationship_model_failure_fallback'
    assert record['temporal'] == {'status': 'unavailable'}
    assert resolve(candidate, registry, authorized_scope=registry['scope'], require_temporal=True) is None
    encoded = json.dumps(registry)
    for canary in ('EXCEPTION_CANARY', 'TRACEBACK_CANARY', 'CREDENTIAL_CANARY', 'PATH_CANARY', 'WORKER_CANARY'):
        assert canary not in encoded


@pytest.mark.parametrize('problem', ['missing_ref', 'missing_record', 'tamper', 'version', 'wrong_scope', 'copied_lineage', 'malformed'])
def test_resolver_fails_closed(problem):
    model, _, registry = produced()
    assertion = deepcopy(model['top_relationship_changes'][0]); scope = 'authorized-site-A'
    if problem == 'missing_ref': assertion.pop(REF)
    elif problem == 'missing_record': registry['records'] = {}
    elif problem == 'tamper': next(iter(registry['records'].values()))['basis'] = 'changed'
    elif problem == 'version': registry['version'] = 'unsupported'
    elif problem == 'wrong_scope': scope = 'other-site'
    elif problem == 'copied_lineage': assertion['recent_correlation'] = .123
    else: assertion[REF] = []
    assert resolve(assertion, registry, authorized_scope=scope) is None


def test_conflicting_duplicate_and_ambiguous_assessment():
    model, graph, registry = produced()
    record = deepcopy(next(iter(registry['records'].values())))
    record['basis'] = 'different'
    with pytest.raises(ValueError): registry_record(registry, record)
    second = deepcopy(graph['edges'][0]); second['operating_mode_context'] = {'match': 'weak'}
    graph['edges'].append(second)
    finalize(model, graph, scope='authorized-site-A')
    assert REF not in model['top_relationship_changes'][0]
    assert ASSESSMENT_BINDING not in model['top_relationship_changes'][0]


def test_real_engine_upload_storage_and_connector_projection(monkeypatch):
    from app.services.upload_persistence import project_result_for_transport
    from app.services.telemetry_result_projection import build_canonical_result_projection
    from test_telemetry_result_projection import _execution, _metadata, _scope
    result = evaluate_sii(**contract(16))
    analysis = result['analysis_result']
    registry = result[REGISTRY]
    assert analysis[REGISTRY] == registry
    assert all(REF in item for item in analysis['relationships'])
    stored = json.loads(json.dumps({'analysis_result': analysis, 'sii_result': result}))
    monkeypatch.setattr('app.engine.sii_engine.evaluate_sii', lambda **_: pytest.fail('retrieval reran engine'))
    assert ensure_analysis_result(stored)[REGISTRY] == registry
    assert project_result_for_transport(stored)['analysis_result'][REGISTRY] == registry
    execution = _execution()
    execution['analysis_result'][REGISTRY] = deepcopy(registry)
    execution['analysis_result']['relationships'] = deepcopy(analysis['relationships'])
    projected = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope()).product_result
    # Bounded customer transport carries references; the full registry remains
    # in the authorized canonical artifact, independent of disclosure limits.
    assert execution['analysis_result'][REGISTRY] == registry
    assert REGISTRY not in projected['analysis_result']
    assert projected['analysis_result']['relationships'] == analysis['relationships']


def test_historical_absence_remains_absent():
    from test_sii_evidence_transport import _canonical_result
    historical = _canonical_result()
    expected = deepcopy(historical)
    assert REGISTRY not in ensure_analysis_result(historical)
    assert historical == expected


def test_source_units_basis_and_current_window_change_identity():
    e = raw()
    kwargs = dict(columns=['a', 'b'], baseline_rows=[{'a': 1, 'b': 2}],
                  current_rows=[{'a': 2, 'b': 1}], timestamp_column=None)
    a = source_evidence(e, **kwargs, units={'a': 'kPa'})
    b = source_evidence(e, **kwargs, units={'a': 'psi'})
    assert a['source_id'] != b['source_id']
    a = evidence_record(e, {'edge_basis': 'global_relationship_model'}, 'site')
    b = evidence_record(e, {'edge_basis': 'global_relationship_model_failure_fallback'}, 'site')
    assert a['evidence_id'] != b['evidence_id']
    e2 = deepcopy(e); e2['time_window']['current_end'] = '2026-01-03T12:00:00+00:00'
    assert source_evidence(e, **kwargs)['source_id'] != source_evidence(e2, **kwargs)['source_id']


def test_security_canaries_and_recurrence_do_not_enter_identity():
    _, graph, _ = produced(8)
    e = graph['edges'][0]
    original = evidence_record(e, graph, 'site')
    for key in ('credentials', 'traceback', 'worker_id', 'process_id', 'retry_id', 'path', 'forensic', 'exception'):
        e[key] = 'RESTRICTED_CANARY'
    e['recurrence_evidence'] = {'supported': True, 'episodes': ['different']}
    assert evidence_record(e, graph, 'site') == original
    assert 'RESTRICTED_CANARY' not in json.dumps(original)


def test_real_connector_generation_retains_registry_and_retries():
    from datetime import datetime, UTC, timedelta
    from app.services.telemetry_analysis_window import build_canonical_analysis_window, run_analysis_window
    from test_telemetry_analysis_handoff import _scope, _identity, _observation, DIGEST, SIGNAL
    scope = _scope()
    start = datetime(2026, 8, 25, tzinfo=UTC)
    signals = [SIGNAL, '4385267d-f840-59c4-ba65-06a6726e3189']
    observations = []
    for i in range(40):
        for j, signal in enumerate(signals):
            value = 80+i if j == 0 else (40+i*.5 if i < 28 else 30+(i*17)%11)
            observations.append({**_observation(i*2+j, signal, start+timedelta(minutes=i), value),
                                 'canonical_signal_name': f'pressure_{j}'})
    window = build_canonical_analysis_window(window_id='window-binding', source_run_id='run-a',
        scope=scope, system_id='system-a', asset_id='asset-a', persisted_authority_digest=DIGEST,
        phase4_system_identity=_identity(scope), observations=observations)
    first = run_analysis_window(window)
    second = run_analysis_window(window)
    assert first.sii_result[REGISTRY] == second.sii_result[REGISTRY]
    assert first.analysis_result[REGISTRY] == first.sii_result[REGISTRY]
    assert first.sii_result[REGISTRY]['scope'] == digest('relationship-scope.v1', scope.as_dict())
    assert first.sii_result[REGISTRY]['records']
    assert first.analysis_result['relationships']
    assert [(r[OWNER_REF], r[REF], r[ASSESSMENT_BINDING]) for r in first.analysis_result['relationships']] == [
        (r[OWNER_REF], r[REF], r[ASSESSMENT_BINDING]) for r in second.analysis_result['relationships']]
    for relationship in first.analysis_result['relationships']:
        assert resolve(relationship, first.analysis_result[REGISTRY],
                       authorized_scope=first.analysis_result[REGISTRY]['scope']) is not None


@pytest.fixture(scope='module')
def authoritative_backend(tmp_path_factory):
    import subprocess
    target = tmp_path_factory.mktemp('binding-baseline')
    archive = target / 'baseline.tar'
    with archive.open('wb') as stream:
        subprocess.run(['git', 'archive', 'f01d5475967eef8b2f7dd0d05a7b631f79586e25', 'backend/app'], stdout=stream, check=True)
    subprocess.run(['tar', '-xf', str(archive), '-C', str(target)], check=True)
    return target / 'backend'


@pytest.mark.parametrize('case', ['paired', 'global_fallback', 'graph_failure', 'mode'])
def test_normalized_analytical_result_equals_authoritative_head(authoritative_backend, case):
    import os
    from pathlib import Path
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    script = '''
import json
from app.engine.sii_engine import evaluate_sii
from test_sii_supplied_reference import contract
from app.services.output_semantics import semantic_content
from app.services.product_evidence_contract import product_evidence
from relationship_evidence_binding_cases import without_binding_metadata
from presentation_phase1_context_case import context_fallback_case
from presentation_phase1_graph_fallback_case import graph_fallback_case
case = CASE
if case == 'mode':
 from datetime import datetime, timedelta, timezone
 start = datetime(2026, 1, 1, tzinfo=timezone.utc)
 rows = [{'timestamp': (start+timedelta(minutes=i)).isoformat(), 'stage': 'A' if i<40 else 'B',
          'flow': float(i), 'pressure': float(2*i+5 if i<70 else 100+(i*17)%11)} for i in range(100)]
 r = evaluate_sii(columns=['timestamp','stage','flow','pressure'], rows=rows, timestamp_column='timestamp',
                  numeric_profiles=[{'column': c, 'constant_or_stuck': False, 'missing_count': 0, 'non_numeric_count': 0} for c in ('flow','pressure')],
                  config={'numeric_columns':['flow','pressure']})
 assert r['relationship_graph']['edge_basis'] == 'mode_conditioned_relationships'
else:
 r = evaluate_sii(**contract(16)) if case == 'paired' else context_fallback_case() if case == 'global_fallback' else graph_fallback_case()
# The authority phase intentionally changes refusal diagnostics. These fixtures
# have no quantified consequence; preserve/assert that status rather than compare
# the old broad-original refusal payload to the new fail-closed refusal payload.
def authority_comparison(value):
 if isinstance(value, dict):
  result = {}
  for key, item in value.items():
   if key in {'resource_relationship_source_ref', 'resource_relationship_binding'}:
    continue
   if key == 'measurable_consequence':
    assert item['status'] == 'not_quantifiable', item
    result[key] = {'status': item['status']}
   else:
    result[key] = authority_comparison(item)
  return result
 if isinstance(value, list):
  return [authority_comparison(item) for item in value]
 return value
print(json.dumps(authority_comparison(without_binding_metadata(semantic_content(product_evidence(r)))), sort_keys=True))
'''.replace('CASE', repr(case))
    outputs = []
    for backend in (authoritative_backend, root / 'backend'):
        env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(backend)+os.pathsep+str(root/'tests')}
        outputs.append(json.loads(subprocess.check_output([sys.executable, '-c', script], env=env, cwd=authoritative_backend.parent)))
    assert outputs[0] == outputs[1]


def test_temporal_identity_mismatch_cannot_supply_proof():
    model, graph, _ = produced(8)
    next(iter(graph['relationship_persistence_state'].values()))['identity']['reference_dataset_id'] = 'wrong'
    with pytest.raises(ValueError, match='temporal_identity_mismatch'):
        evidence_record(graph['edges'][0], graph, 'authorized-site-A')
    registry = finalize(model, graph, scope='authorized-site-A')
    assert resolve(model['top_relationship_changes'][0], registry,
                   authorized_scope='authorized-site-A', require_temporal=True) is None


def test_real_upload_compatibility_path_preserves_binding():
    from app.services.telemetry_analysis_window import run_upload_analysis_compatibility
    args = contract(16)
    execution = run_upload_analysis_compatibility(evaluator=evaluate_sii, evaluation_kwargs=args)
    assert execution[REGISTRY]['records']
    upload = {**execution['compatibility'], 'sii_result': execution}
    analysis = build_analysis_result(upload)
    assert analysis[REGISTRY] == execution[REGISTRY]
    for item in analysis['relationships']:
        assert resolve(item, analysis[REGISTRY], authorized_scope=analysis[REGISTRY]['scope']) is not None


def test_controlled_replay_reducers_are_identical_with_lineage():
    from relationship_evidence_binding_cases import without_binding_metadata
    from app.services.output_semantics import semantic_content
    left_state = right_state = None
    for day, delta in enumerate([-.22] * 8 + [0, -.22], 1):
        bound = raw(day, delta)
        plain = deepcopy(bound); plain.pop(SOURCE)
        left = analyze(plain, left_state)
        right = analyze(bound, right_state)
        assert semantic_content(left) == without_binding_metadata(semantic_content(right))
        left_state = left['relationship_persistence_state']
        right_state = right['relationship_persistence_state']


def test_identity_is_independent_of_runtime_metadata():
    model, graph, registry = produced()
    expected = deepcopy(registry)
    for container in (model['top_relationship_changes'][0], graph['edges'][0]):
        container.update(worker_id='different', process_id=19, request_id='request', retry_id='retry', generated_at='2099-01-01')
    assert finalize(model, graph, scope='authorized-site-A') == expected


@pytest.mark.parametrize(('path', 'function'), [
    ('backend/app/services/relationship_baselines.py', 'build_relationship_baseline'),
    ('backend/app/engine/sii/mode_conditioned_baseline.py', '_conditioned_edge'),
    ('backend/app/engine/sii_engine.py', 'evaluate_sii'),
])
def test_existing_calculation_ast_unchanged_except_binding_metadata(path, function):
    import ast
    from pathlib import Path
    import subprocess
    baseline = ast.parse(subprocess.check_output(['git', 'show', 'f01d5475967eef8b2f7dd0d05a7b631f79586e25:'+path], text=True))
    candidate = ast.parse(Path(path).read_text())
    original = next(n for n in baseline.body if isinstance(n, ast.FunctionDef) and n.name == function)
    current = next(n for n in candidate.body if isinstance(n, ast.FunctionDef) and n.name == function)

    class RemoveBindingOnly(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            if node.name == 'binding_rows':
                return None
            if node.name == 'build_relationship_baseline':
                i = [a.arg for a in node.args.kwonlyargs].index('binding_signal_units')
                node.args.kwonlyargs.pop(i); node.args.kw_defaults.pop(i)
            return self.generic_visit(node)

        def visit_Assign(self, node):
            target = node.targets[0]
            if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Name) and target.slice.id in {'SOURCE', 'REGISTRY'}:
                return None
            if isinstance(target, ast.Name) and target.id == 'evidence_scope':
                return None
            if function == '_conditioned_edge' and isinstance(target, ast.Name) and target.id == 'result':
                return ast.Return(value=node.value)
            return self.generic_visit(node)

        def visit_Return(self, node):
            if function == '_conditioned_edge' and isinstance(node.value, ast.Name) and node.value.id == 'result':
                return None
            return self.generic_visit(node)

        def visit_ImportFrom(self, node):
            return None if node.module in {'app.services.relationship_evidence_binding', 'app.services.resource_relationship_binding'} else node

        def visit_Expr(self, node):
            if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == 'finalize_resources'):
                return None
            return self.generic_visit(node)

        def visit_Call(self, node):
            node.keywords = [k for k in node.keywords if k.arg != 'binding_signal_units']
            return self.generic_visit(node)

        def visit_Dict(self, node):
            pairs = [(k, v) for k, v in zip(node.keys, node.values) if not (isinstance(k, ast.Name) and k.id == 'SOURCE')]
            node.keys = [k for k, _ in pairs]; node.values = [v for _, v in pairs]
            return self.generic_visit(node)

    cleaned = RemoveBindingOnly().visit(current)
    assert ast.dump(cleaned, include_attributes=False) == ast.dump(original, include_attributes=False)


def test_registry_serialization_ignores_mapping_insertion_order():
    model, graph, registry = produced(8)
    source = graph['edges'][0][SOURCE]
    source['units'] = dict(reversed(list(source['units'].items())))
    source['measurement'] = dict(reversed(list(source['measurement'].items())))
    other = finalize(model, graph, scope='authorized-site-A')
    assert json.dumps(other) == json.dumps(registry)
