"""Focused authority-boundary cases; analytical producers are unchanged."""
from copy import deepcopy
import json
import subprocess

import pytest

from app.services.analysis_explanations import build_analysis_explanation, build_relationship_findings
from app.services.analysis_result_contract import build_analysis_result, ensure_analysis_result
from app.services.condition_corroboration import ConditionCorroborationService
from app.services.relationship_authority import (
    FINDINGS, VERSION, VERSION_FIELD, relationship_persistence,
)
from app.services.relationship_evidence_binding import SOURCE, REF, REGISTRY, finalize, source_evidence
from app.services.resource_relationship_binding import ownership
from app.services.measurable_consequence import build_measurable_consequence
from test_relationship_temporal_persistence import edge, analyze
from resource_binding_cases import assessment
from test_measurable_consequence import fixture


def produce(kind='persistent', columns=('flow', 'load')):
    deltas = {
        'persistent': [-.22] * 8, 'stable': [.001] * 8,
        'transient': [-.22], 'alternating': [-.22, .22] * 4,
        'sparse': [-.22] * 8, 'abrupt': [.6],
    }[kind]
    state = None
    for day, delta in enumerate(deltas, 1):
        raw = edge(day, delta, columns=list(columns), correlation_delta=abs(delta), signed_correlation_delta=delta)
        if kind == 'sparse':
            raw.update(baseline_sample_count=2, current_sample_count=2)
        raw[SOURCE] = source_evidence(raw, columns=columns,
            baseline_rows=[{columns[0]: 1, columns[1]: 2, 't': 0}],
            current_rows=[{columns[0]: 2, columns[1]: 1, 't': day}], timestamp_column='t')
        graph = analyze(raw, state)
        state = graph['relationship_persistence_state']
    model = {'relationship_graph': {'edges': [raw]}, 'top_relationship_changes': [deepcopy(raw)]}
    registry = finalize(model, graph, scope='authority-test')
    entry = model['top_relationship_changes'][0]
    entry.update(change_type=graph['edges'][0]['change_type'], baseline_sample_size=raw['baseline_sample_count'],
                 recent_sample_size=raw['current_sample_count'], confidence_score=.9,
                 data_confidence={'rating': 'high'},
                 operating_mode={'match': 'strong', 'confidence': 'high'})
    return entry, registry, graph


def source(*produced):
    registry = deepcopy(produced[0][1])
    entries = []
    for entry, item_registry, *_ in produced:
        assert registry['scope'] == item_registry['scope']
        registry['records'].update(deepcopy(item_registry['records']))
        entries.append(deepcopy(entry))
    return {
        'analysis_id': 'authority-test',
        'relationship_model': {'top_relationship_changes': entries},
        'sii_result': {REGISTRY: registry, VERSION_FIELD: VERSION},
        'data_quality': {'reliability_rating': 'high', 'data_confidence': {'rating': 'high'},
                         'operating_mode': {'match': 'strong', 'confidence': 'high'}},
        'engine_result': {'persistence_assessment': {'persistent_columns': []}},
    }


def scoped(result):
    return {item[REF]: item for item in build_relationship_findings(result['relationship_model'], result)}


def assert_group_unqualified(result):
    explanation = build_analysis_explanation(result)
    for item in explanation['insights']:
        if item.get('contributing_relationships'):
            assert item['persistence']['persistent'] is False
            assert ownership(item) is None
            assert item['classification']['type'] != 'unexplained_systemic_change'
    conditions = ConditionCorroborationService().build_conditions(
        relationships=explanation['relationships'], findings=list(scoped(result).values()),
        data_quality=result['data_quality'], operating_mode={'match': 'strong', 'confidence': 'high'},
        baseline_analysis={'drift_trajectory': {'persistent_columns': ['flow', 'load']}},
        relationship_authority=True,
    )
    assert all(item['classification']['type'] != 'unexplained_systemic_change' for item in conditions)
    return explanation, conditions


# Mandatory cases 1–7. Actual frozen reducers establish each assessment.
@pytest.mark.parametrize('members', [(), ('stable',), ('transient',), ('alternating',),
                                    ('sparse',), ('persistent',), ('stable', 'transient', 'alternating', 'sparse')])
def test_members_cannot_suppress_or_promote(members):
    a = produce()
    baseline = scoped(source(a))[a[0][REF]]
    assert baseline['persistence']['persistent'] is True
    assert baseline['classification']['type'] == 'unexplained_systemic_change'
    others = [produce(kind, ('flow', f'other_{index}')) for index, kind in enumerate(members)]
    result = source(a, *others)
    before = deepcopy(result)
    actual = scoped(result)
    assert actual[a[0][REF]] == baseline
    for kind, other in zip(members, others):
        assert actual[other[0][REF]]['persistence']['persistent'] is (kind == 'persistent')
    assert_group_unqualified(result)
    assert result == before


def test_recurrence_and_abrupt_promotion_are_not_persistence():
    # Cases 8–9: recurrence has no authority and single-window promotion is insufficient.
    transient = produce('transient')
    transient[0]['recurrence_evidence'] = {'supported': True, 'episode_count': 9}
    a = scoped(source(transient))[transient[0][REF]]
    assert not a['persistence']['persistent']
    abrupt = produce('abrupt')
    assert abrupt[2]['edges'][0]['promoted_changed_edge']
    assert not scoped(source(abrupt))[abrupt[0][REF]]['persistence']['persistent']


def test_context_quality_and_health_remain_independent():
    # Case 10: scope retains persistence while independent ceilings limit classification.
    a = produce()
    for field, value, expected in [
        ('operating_mode', {'match': 'weak', 'confidence': 'high'}, 'context_limited_relationship_change'),
        ('data_confidence', {'rating': 'low'}, 'insufficient_evidence'),
        ('sensor_health', [{'signal': 'flow', 'health': 'suspect', 'conditions': [{'type': 'flatline_or_stuck', 'severity': 'review', 'evidence': 'Repeated readings'}]}], 'possible_instrumentation_issue'),
    ]:
        changed = deepcopy(a)
        changed[0][field] = value
        finding = scoped(source(changed))[a[0][REF]]
        assert finding['persistence']['persistent']
        assert finding['classification']['type'] == expected


@pytest.mark.parametrize('failure', [False, True])
def test_global_and_failure_fallback(failure):
    # Cases 11–12: global fallback may own temporal evidence; graph failure cannot.
    entry, _, graph = produce()
    model = {'relationship_graph': {'edges': [entry]}, 'top_relationship_changes': [deepcopy(entry)]}
    if failure:
        graph = {'edge_basis': 'global_relationship_model_failure_fallback', 'edges': [entry]}
    registry = finalize(model, graph, scope='authority-test',
                        mode_conditioned={'status': 'insufficient_data', 'used_global_fallback': True})
    entry = model['top_relationship_changes'][0]
    assert relationship_persistence(entry, registry)['persistent'] is (not failure)
    assert_group_unqualified(source((entry, registry, graph)))


def test_grouping_ranking_and_primary_mutations(monkeypatch):
    # Cases 13–14: the whole scoped record, including qualification, stays equal.
    result = source(produce(), produce('stable', ('flow', 'other')))
    baseline = scoped(result)
    import app.services.analysis_explanations as explanations
    for grouped in (True, False):
        monkeypatch.setattr(explanations, 'cluster_relationship_changes',
                            lambda entries: [entries] if grouped else [[item] for item in entries])
        for reverse in (True, False):
            entries = result['relationship_model']['top_relationship_changes']
            if reverse:
                entries.reverse()
            for index, item in enumerate(entries):
                item.update(primary=index == 0, group='changed', relationship_importance_score=index * 100)
            assert scoped(result) == baseline
            assert {item[REF]: item for item in assert_group_unqualified(result)[0][FINDINGS]} == baseline


def test_condition_overlap_cannot_copy_classification():
    # Case 15: even a highly ranked, signal-overlapping persistent finding is not a condition owner.
    result = source(produce('abrupt'))
    donor = next(iter(scoped(source(produce())).values()))
    explanation = build_analysis_explanation(result)
    conditions = ConditionCorroborationService().build_conditions(
        relationships=explanation['relationships'], findings=[donor],
        data_quality=result['data_quality'], operating_mode={'match': 'strong'},
        relationship_authority=True,
    )
    assert conditions
    assert all(c['classification']['type'] != donor['classification']['type'] for c in conditions)
    assert all(ownership(c) is None for c in conditions)


def test_consequence_exact_owner_and_mismatch():
    # Case 16: use certified source/resource assignments, never an ID/name join.
    original, expected, catalog = fixture()
    entry, registry = deepcopy(assessment())
    entry.update(source_relationship_ids=original['source_relationship_ids'],
                 baseline_sample_size=48, recent_sample_size=48, confidence_score=.9,
                 data_confidence={'rating': 'high'}, operating_mode={'match': 'strong', 'confidence': 'high'})
    result = source((entry, registry))
    result['sii_result']['expected_behavior'] = expected
    result['telemetry_signal_catalog'] = catalog
    analysis = build_analysis_result(result)
    finding = analysis[FINDINGS][0]
    assert finding['measurable_consequence']['status'] == 'quantified'
    assert finding['measurable_consequence']['cumulative_amount'] == pytest.approx(12840)
    other, other_registry = assessment(columns=('flow', 'other_load'))
    mixed = deepcopy(registry)
    mixed['records'].update(other_registry['records'])
    wrong = deepcopy(finding)
    wrong.update(ownership(other))
    assert build_measurable_consequence(wrong, expected_behavior=expected, signal_catalog=catalog,
        relationship_registry=mixed, authorized_scope=mixed['scope'])['status'] == 'not_quantifiable'
    assert all(c['measurable_consequence']['status'] != 'quantified' for c in analysis['insights'])
    assert ensure_analysis_result({'analysis_result': analysis}) == analysis


def test_identical_signal_persistence_different_relationships():
    # Case 17: identical signal-level persistence cannot substitute for changed structure.
    persistent = source(produce())
    reversing = source(produce('alternating'))
    for result in (persistent, reversing):
        result['engine_result']['persistence_assessment']['persistent_columns'] = ['flow', 'load']
    assert next(iter(scoped(persistent).values()))['persistence']['persistent']
    assert not next(iter(scoped(reversing).values()))['persistence']['persistent']


def test_unbound_or_conflicting_source_cannot_authorize():
    result = source(produce())
    entry = result['relationship_model']['top_relationship_changes'][0]
    entry[SOURCE] = produce('stable')[0][SOURCE]
    assert scoped(result) == {}
    entry.pop(SOURCE)
    entry.pop('relationship_assessment_binding')
    assert scoped(result) == {}


def test_historical_explanation_matches_committed_implementation():
    # No version marker: exact output equality with the baseline implementation.
    result = source(produce())
    result['sii_result'].pop(VERSION_FIELD)
    before = deepcopy(result)
    namespace = {'__name__': 'historical_analysis_explanations'}
    code = subprocess.check_output(['git', 'show', '774892e4:backend/app/services/analysis_explanations.py'], text=True)
    exec(compile(code, 'historical_analysis_explanations.py', 'exec'), namespace)
    assert build_analysis_explanation(result) == namespace['build_analysis_explanation'](result)
    assert result == before
    assert FINDINGS not in build_analysis_result(result)
    assert json.loads(json.dumps(result)) == result


def test_scoped_authority_survives_upload_and_connector_transport():
    from app.services.upload_persistence import project_result_for_transport
    from app.services.telemetry_result_projection import build_canonical_result_projection, canonical_projection_digest
    from test_telemetry_result_projection import _execution, _metadata, _scope

    result = source(produce(), produce('stable', ('flow', 'other')))
    analysis = build_analysis_result(result)
    stored = json.loads(json.dumps({'analysis_result': analysis}))
    assert project_result_for_transport(stored)['analysis_result'][FINDINGS] == analysis[FINDINGS]
    execution = _execution()
    for key in (VERSION_FIELD, FINDINGS):
        execution['analysis_result'][key] = deepcopy(analysis[key])
    before = deepcopy(execution)
    first = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope())
    second = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope())
    for key in (VERSION_FIELD, FINDINGS):
        assert first.product_result['analysis_result'][key] == analysis[key]
    assert canonical_projection_digest(first) == canonical_projection_digest(second)
    assert execution == before


@pytest.mark.parametrize('attack', ['transfer', 'reverse', 'missing', 'tampered'])
def test_canonical_scoped_qualification_does_not_trust_cached_authority(attack):
    a, b = produce(), produce('transient', ('flow', 'other_load'))
    result = source(a, b)
    expected = build_analysis_result(result)[FINDINGS]
    explanation = build_analysis_explanation(result)
    cached = {item[REF]: item for item in explanation[FINDINGS]}
    persistent, transient = cached[a[0][REF]], cached[b[0][REF]]
    assert persistent['persistence']['persistent']
    assert not transient['persistence']['persistent']
    if attack in ('transfer', 'reverse'):
        donor, recipient = ((persistent, transient) if attack == 'transfer'
                            else (transient, persistent))
        owner = ownership(recipient)
        for key in ('persistence', 'classification', 'finding_confidence_v1'):
            recipient[key] = deepcopy(donor[key])
        assert ownership(recipient) == owner
    elif attack == 'missing':
        explanation.pop(FINDINGS)
    else:
        persistent['relationship_assessment_binding'] = 'tampered'
        transient['persistence']['persistent'] = True
        transient['persistence']['status'] = 'persistent'
    result['analysis_explanation'] = explanation
    before = deepcopy(result)
    actual = build_analysis_result(result)[FINDINGS]
    assert actual == expected
    assert result == before


@pytest.mark.parametrize('invalid', ['missing_registry', 'scope', 'binding', 'missing_source'])
def test_cached_authority_cannot_rescue_unavailable_producer_evidence(invalid):
    result = source(produce())
    result['analysis_explanation'] = build_analysis_explanation(result)
    if invalid == 'missing_registry':
        result['sii_result'].pop(REGISTRY)
    elif invalid == 'scope':
        result['sii_result'][REGISTRY]['scope'] = 'different-scope'
    elif invalid == 'binding':
        result['relationship_model']['top_relationship_changes'][0]['relationship_assessment_binding'] = 'tampered'
    else:
        result.pop('relationship_model')
    before = deepcopy(result)
    assert build_analysis_result(result)[FINDINGS] == []
    assert result == before


def test_canonical_requalification_uses_retained_baseline_assertions():
    result = source(produce())
    expected = build_analysis_result(result)[FINDINGS]
    result['baseline_analysis'] = result.pop('relationship_model')
    result['analysis_explanation'] = build_analysis_explanation(result)
    result['analysis_explanation'][FINDINGS] = []
    assert build_analysis_result(result)[FINDINGS] == expected


def test_historical_and_stored_results_do_not_requalify(monkeypatch):
    result = source(produce())
    stored = {'analysis_result': build_analysis_result(result)}
    result['sii_result'].pop(VERSION_FIELD)
    result['analysis_explanation'] = build_analysis_explanation(result)
    before = deepcopy((result, stored))

    def unexpected_requalification(*args, **kwargs):
        pytest.fail('Historical construction or canonical retrieval requalified evidence')

    monkeypatch.setattr('app.services.analysis_result_contract.build_relationship_findings',
                        unexpected_requalification)
    assert FINDINGS not in build_analysis_result(result)
    assert ensure_analysis_result(stored) == stored['analysis_result']
    assert (result, stored) == before
