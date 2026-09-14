from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path

import pytest

from app.engine.relationship_recurrence import RECURRENCE_RULES
from app.services.analysis_result_contract import build_sii_evidence_projection
from test_relationship_temporal_persistence import analyze, edge, PAIR, BASELINE


def replay(deltas, **kwargs):
    persistence, recurrence, results = None, None, []
    for day, delta in enumerate(deltas, 1):
        result = analyze(edge(day, delta), persistence, relationship_recurrence_state=recurrence, **kwargs)
        persistence = result['relationship_persistence_state']
        recurrence = result['relationship_recurrence_state']
        results.append(result)
    return results


def evidence(result):
    return result['edges'][0]['recurrence_evidence']


@pytest.mark.parametrize(('deltas', 'continuous', 'recurring'), [
    ([-0.22] * 15 + [0.0], True, False),
    (([-0.22] * 3 + [0.0] * 4) * 3, False, True),
    ([0.0] * 4 + [-0.22] * 3 + [0.0] * 12, False, False),
    ([0.0] * 24, False, False),
    ([-0.22] * 3 + [0.0] * 4 + [0.22] * 3 + [0.0] * 4 + [-0.22] * 3 + [0.0], False, False),
])
def test_distinct_evidence_models(deltas, continuous, recurring):
    results = replay(deltas)
    assert any(r['edges'][0]['temporal_persistence_supported'] for r in results) == continuous
    assert any(evidence(r)['supported'] for r in results) == recurring
    if recurring:
        assert all(not r['changed_edges'] for r in results)
        assert evidence(results[-1])['episode_count'] == 3
        assert evidence(results[-1])['direction'] == -1


def test_episode_closes_only_on_gated_neutral_return():
    results = replay([-0.22, -0.22, 0.0] * 2 + [-0.22, -0.22])
    latest = results[-1]
    assert evidence(latest)['episode_count'] == 2
    assert not latest['recurring_edges']
    bad_return = analyze(edge(9, 0.0, confidence=0.1), relationship_recurrence_state=latest['relationship_recurrence_state'])
    assert evidence(bad_return)['episode_count'] == 2
    closed = analyze(edge(10, 0.0), relationship_recurrence_state=bad_return['relationship_recurrence_state'])
    assert evidence(closed)['supported']
    assert evidence(closed)['episodes'][-1]['closing_return']['observed_at'] == edge(10)['time_window']['current_end']
    assert evidence(closed)['episodes'][1]['opening_return'] == evidence(closed)['episodes'][0]['closing_return']
    assert not any(evidence(r)['supported'] for r in replay([-0.22] * 18))


@pytest.mark.parametrize('block', ['confidence', 'quality', 'health', 'eligibility', 'samples'])
def test_gated_windows_do_not_count_or_separate(block):
    recurrence = None
    for day, delta in enumerate([-0.22, -0.22, 0.0] * 3, 1):
        raw, kwargs = edge(day, delta), {}
        if day % 3 == 2:
            if block == 'confidence':
                raw['confidence'] = 0.1
            elif block == 'quality':
                kwargs['data_quality'] = {'data_confidence': {'rating': 0.1}}
            elif block == 'health':
                kwargs['sensor_health'] = {'signals': [{'signal': c, 'health': 'suspect', 'conditions': [{'type': 'flatline_or_stuck'}]} for c in PAIR]}
            elif block == 'eligibility':
                raw['relationship_context']['operator_primary_eligible'] = False
            else:
                raw['current_sample_count'] = 2
        result = analyze(raw, relationship_recurrence_state=recurrence, **kwargs)
        recurrence = result['relationship_recurrence_state']
        assert not evidence(result)['supported']
    assert evidence(result)['episode_count'] == 0


def test_unknown_windows_cannot_create_separate_episodes_or_consecutive_support():
    recurrence = None
    for day in range(1, 13):
        result = analyze(edge(day, confidence=0.1 if day % 3 == 0 else 0.73), relationship_recurrence_state=recurrence)
        recurrence = result['relationship_recurrence_state']
    closed = analyze(edge(13, 0.0), relationship_recurrence_state=recurrence)
    assert evidence(closed)['episode_count'] == 1
    assert not evidence(closed)['supported']
    assert not evidence(replay([-0.22, 0.0] * 8)[-1])['supported']


def test_opposite_supported_open_episode_vetoes_prior_recurrence():
    results = replay([-0.22, -0.22, 0.0] * 3 + [0.22, 0.22])
    assert evidence(results[-3])['supported']
    assert evidence(results[-1])['opposite_direction_veto']
    assert not evidence(results[-1])['supported']


@pytest.mark.parametrize('invalid', ['backward', 'conflict', 'overlap', 'missing', 'invalid', 'zero_length'])
def test_invalid_windows_cannot_manufacture_recurrence(invalid):
    result = replay([-0.22, -0.22, 0.0] * 2)[-1]
    state = result['relationship_recurrence_state']
    saved = deepcopy(state)
    raw = edge(7)
    if invalid == 'backward':
        raw = edge(2)
    elif invalid == 'conflict':
        raw = edge(6)
    elif invalid == 'overlap':
        raw['time_window']['current_start'] = edge(6)['time_window']['current_start']
    elif invalid == 'missing':
        raw['time_window'].pop('current_start')
    elif invalid == 'zero_length':
        raw['time_window']['current_start'] = raw['time_window']['current_end']
    else:
        raw['time_window']['current_end'] = 'not-a-time'
    for _ in range(8):
        result = analyze(raw, relationship_recurrence_state=state)
        assert evidence(result)['status'] == 'limited'
        assert not result['recurring_edges']
        assert result['relationship_recurrence_state'] == saved
        state = result['relationship_recurrence_state']


def test_exact_retries_read_only_and_deterministic():
    result = replay([-0.22, -0.22, 0.0] * 3)[-1]
    state = result['relationship_recurrence_state']
    original = deepcopy(state)
    for _ in range(8):
        retried = analyze(edge(9, 0.0), relationship_recurrence_state=state)
        assert retried['relationship_recurrence_state'] == state
        assert evidence(retried) == evidence(result)
    assert state == original
    payload = json.dumps(evidence(result)).lower()
    assert all(word not in payload for word in ('diagnosis', 'cause', 'prescri', 'recommend'))


@pytest.mark.parametrize('change', ['reference', 'units', 'baseline', 'mode', 'basis', 'pair'])
def test_identity_changes_reset_recurrence(change):
    state = replay([-0.22, -0.22, 0.0] * 3)[-1]['relationship_recurrence_state']
    raw, kwargs = edge(10, 0.0), {}
    if change == 'reference':
        raw['reference_dataset_id'] = 'new'
    elif change == 'units':
        raw['signal_units'] = {PAIR[0]: 'new'}
    elif change == 'baseline':
        raw['baseline_correlation'] += 0.01
    elif change == 'mode':
        raw['mode_conditioning'] = {'mode_id': 'new'}
    elif change == 'pair':
        raw['columns'] = ['other', PAIR[1]]
    else:
        kwargs['mode_conditioned_analysis'] = {'mode_relationships': {'edges': [raw]}}
    result = analyze(raw, relationship_recurrence_state=state, **kwargs)
    assert evidence(result)['episode_count'] == 0
    assert not result['recurring_edges']


def test_horizon_and_capacity_are_bounded_without_losing_veto():
    state = replay([-0.22, -0.22, 0.0] * 3)[-1]['relationship_recurrence_state']
    expired = analyze(edge(45, 0.0), relationship_recurrence_state=state)
    assert evidence(expired)['episode_count'] == 0
    assert not expired['recurring_edges']
    recurrence = None
    for index in range(RECURRENCE_RULES['maximum_observations'] + 1):
        raw = edge(1, 0.0)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index * 2)
        raw['time_window'].update(current_start=start.isoformat(), current_end=(start + timedelta(minutes=1)).isoformat())
        result = analyze(raw, relationship_recurrence_state=recurrence)
        recurrence = result['relationship_recurrence_state']
    assert evidence(result)['status'] == 'limited'
    assert evidence(result)['reason'] == 'observation_capacity_exceeded'
    assert len(next(iter(recurrence.values()))['observations']) == RECURRENCE_RULES['maximum_observations']


def test_neutral_boundary_is_not_delta_summation_and_gates_are_rechecked():
    assert not evidence(replay([-0.149, -0.149, 0.0] * 3)[-1])['supported']
    result = replay([-0.15, -0.15, -0.149] * 3)[-1]
    assert evidence(result)['supported']
    raised = analyze(edge(10, 0.0, confidence=0.95), relationship_recurrence_state=result['relationship_recurrence_state'],
                     config={'minimum_edge_confidence': 0.9})
    assert evidence(raised)['episode_count'] == 0
    assert not evidence(raised)['supported']


def test_mode_conditioned_identity_survives_projection():
    recurrence = None
    for day, delta in enumerate([-0.22, -0.22, 0.0] * 3, 1):
        raw = edge(day, delta, mode_conditioning={'mode_id': 'occupied', 'mode_label': 'Occupied',
                                                 'features': {'load_band': 'typical', 'time_band': 'day'}})
        result = analyze(raw, relationship_recurrence_state=recurrence,
                         mode_conditioned_analysis={'mode_relationships': {'edges': [raw]}})
        recurrence = result['relationship_recurrence_state']
    projected = build_sii_evidence_projection({'sii_result': {'relationship_graph': result}})
    assert projected['relationship_recurrences'][0]['recurrence_evidence'] == evidence(result)


def test_paired_engine_provenance_survives_governed_projection(monkeypatch):
    from app.engine.sii_engine import evaluate_sii
    from app.services import sii_runner
    monkeypatch.setattr(sii_runner, 'write_latest_sii_state', lambda *_a, **_k: pytest.fail('read-only evaluation wrote state'))

    def rows(day, correlation):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
        return [{'timestamp': (start + timedelta(minutes=i)).isoformat(),
                 PAIR[0]: 4 + math.sin(2 * math.pi * i / 48),
                 PAIR[1]: 10 + correlation * math.sin(2 * math.pi * i / 48) + math.sqrt(1-correlation**2) * math.cos(2 * math.pi * i / 48)}
                for i in range(48)]
    recurrence, persistence = None, None
    for day, delta in enumerate([-0.22, -0.22, 0.0] * 3, 1):
        args = dict(columns=['timestamp', *PAIR], reference_rows=rows(0, BASELINE),
                    comparison_rows=rows(day, BASELINE + delta), timestamp_column='timestamp',
                    numeric_profiles=[{'column': c, 'constant_or_stuck': False, 'missing_count': 0, 'non_numeric_count': 0} for c in PAIR],
                    signal_units={c: None for c in PAIR}, relationship_recurrence_state=recurrence,
                    relationship_persistence_state=persistence)
        saved = deepcopy(args)
        result = evaluate_sii(**args)
        assert args == saved
        assert result['processing_trace']['modules_failed'] == []
        graph = result['relationship_graph']
        recurrence, persistence = graph['relationship_recurrence_state'], graph['relationship_persistence_state']
    governed = result['analysis_result']['sii_evidence']
    assert governed['relationship_changes'] == []
    projected = governed['relationship_recurrences'][0]['recurrence_evidence']
    assert projected == evidence(graph)
    assert projected['identity']['reference_dataset_id']
    assert all(w['source_dataset_id'] and w['source_rows'] for ep in projected['episodes'] for w in ep['supporting_windows'])


def test_controlled_chw_campaign_is_one_fixed_validation_fixture():
    fixture = json.loads((Path(__file__).parent / 'fixtures/chw_recurrence_evidence.json').read_text())
    for scenario, series in fixture['scenarios'].items():
        identity = series['identity']
        recurrence, persistence, supported = None, None, False
        for day, window in enumerate(series['windows']):
            raw = edge(day, window['delta'], baseline=identity['baseline_correlation'], columns=identity['columns'],
                       confidence=window['confidence'], reference_dataset_id=identity['reference_dataset_id'],
                       signal_units=identity['signal_units'], source_dataset_id=window['source_dataset_id'],
                       source_rows=window['source_rows'])
            raw['time_window'] = {k: identity[k] for k in ('baseline_start', 'baseline_end')}
            raw['time_window'].update(current_start=window['start'], current_end=window['end'])
            raw['relationship_context']['operator_primary_eligible'] = window['eligible']
            result = analyze(raw, persistence, relationship_recurrence_state=recurrence,
                             operating_mode=identity['mode'],
                             data_quality={'data_confidence': {'rating': window['quality']}},
                             sensor_health={'signals': window['sensor_health_context']})
            persistence, recurrence = result['relationship_persistence_state'], result['relationship_recurrence_state']
            actual = result['edges'][0]
            assert actual['temporal_persistence_supported'] == window['temporal_supported'], (scenario, day)
            assert actual['promoted_changed_edge'] == window['promoted'], (scenario, day)
            supported |= evidence(result)['supported']
            if evidence(result)['supported']:
                projected = build_sii_evidence_projection({'sii_result': {'relationship_graph': result}})
                assert projected['relationship_recurrences'][0]['recurrence_evidence'] == evidence(result)
        assert supported == (scenario == 'B'), scenario
