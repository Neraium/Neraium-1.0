from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import math

import pytest

from app.engine.relationship_change import relationship_change_type
from app.engine.sii.relationship_graph import analyze_relationship_graph
from app.services.relationship_baselines import _relationship_change_type, _should_promote_relationship_change

PAIR = ['Aeration_DO_mgL', 'Effluent_Turbidity_NTU']
BASELINE = -0.668462


def edge(day, delta=-0.22, baseline=BASELINE, columns=PAIR, **extra):
    current = baseline + delta
    start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
    return {
        'id': 'relationship:' + ':'.join(columns),
        'columns': columns,
        'baseline_correlation': baseline,
        'recent_correlation': current,
        'change_type': relationship_change_type(baseline, current),
        'baseline_sample_count': 48,
        'current_sample_count': 48,
        'confidence': 0.73,
        'relationship_context': {'operator_primary_eligible': True},
        'time_window': {'baseline_start': '2025-12-01', 'baseline_end': '2025-12-31',
                        'current_start': start.isoformat(), 'current_end': (start + timedelta(hours=12)).isoformat()},
        'source_rows': [{'window': 'recent_end', 'source_row': day * 48 + 48,
                         'timestamp': (start + timedelta(hours=12)).isoformat()}],
        **extra,
    }


def analyze(raw, state=None, **kwargs):
    return analyze_relationship_graph(
        relationship_model={'relationship_graph': {'edges': [raw]}},
        relationship_persistence_state=state,
        sensor_health=kwargs.pop('sensor_health', {'signals': [{'signal': c, 'health': 'healthy'} for c in raw['columns']]}),
        data_quality=kwargs.pop('data_quality', {'data_confidence': {'rating': 'high'}}),
        **kwargs,
    )


def sequence(deltas, **kwargs):
    state, outputs = None, []
    for day, delta in enumerate(deltas, 1):
        result = analyze(edge(day, delta, **kwargs), state)
        outputs.append(result['edges'][0])
        state = result['relationship_persistence_state']
    return outputs, state


@pytest.mark.parametrize(('baseline', 'current'), [(0.9, 0.2), (0.9, 0.6), (0.9, 0.65), (0.8, -0.8), (0.5, 0.8), (0.2, 0.8)])
def test_abrupt_promotion_is_unchanged_and_shared(baseline, current):
    raw = edge(1, current - baseline, baseline=baseline)
    result = analyze(raw)
    actual = result['edges'][0]
    assert actual['promoted_changed_edge']
    assert not actual['temporal_persistence_supported']
    assert actual['change_type'] == _relationship_change_type(baseline, current)
    assert _should_promote_relationship_change(
        change_type=actual['change_type'], baseline_strength=abs(baseline),
        current_strength=abs(current), drift=abs(current - baseline), relationship_context={},
    )
    assert result['thresholds']['change_inclusion_threshold'] == 0.25


def test_observed_wastewater_trajectory_promotes_with_provenance():
    deltas = [-0.227642, -0.186716, -0.117186, -0.124752, -0.159729, -0.190850,
              -0.195021, -0.232777, -0.246576, -0.213008, -0.192382, -0.221606,
              -0.242339, -0.245376, -0.229255, -0.245006, -0.227194, -0.229069,
              -0.236965, -0.238938, -0.211523, -0.226087, -0.167490]
    outputs, state = sequence(deltas)
    assert not any(e['promoted_changed_edge'] for e in outputs[:7])
    assert all(e['promoted_changed_edge'] for e in outputs[7:])
    latest = outputs[-1]
    assert latest['change_type'] == 'strengthened'
    assert latest['single_window_change_type'] == 'stable'
    assert latest['temporal_persistence_direction'] == -1
    assert latest['temporal_persistence_observations'] == 8
    assert latest['first_supported_observation'] == latest['supporting_windows'][0]['observed_at']
    assert latest['latest_supported_observation'] == latest['supporting_windows'][-1]['observed_at']
    assert all(w['source_rows'] and w['time_window'] and w['edge_confidence'] == 0.73 for w in latest['supporting_windows'])
    assert len(next(iter(state.values()))['observations']) == 8


def test_noisy_directional_displacement_needs_no_monotonicity():
    outputs, _ = sequence([-0.18, -0.23, 0.02, -0.17, -0.22, 0.16, -0.19, -0.21])
    assert outputs[-1]['promoted_changed_edge']
    assert outputs[-1]['temporal_persistence_direction_agreement'] == 0.75
    assert outputs[-1]['temporal_persistence_supporting_observations'] == 6


@pytest.mark.parametrize(('baseline', 'deltas', 'columns'), [
    (0.96, [0.002, -0.003] * 12, ['Blower_Power', 'Blower_Airflow']),
    (BASELINE, [-0.2, 0.2] * 12, PAIR),
    (BASELINE, [-0.14] * 24, PAIR),
    (BASELINE, [-0.22] * 5, PAIR),
])
def test_controls_noise_and_insufficient_evidence_do_not_promote(baseline, deltas, columns):
    outputs, _ = sequence(deltas, baseline=baseline, columns=columns)
    assert not any(e['promoted_changed_edge'] or e['persistent_relationship_change'] for e in outputs)


@pytest.mark.parametrize('block', ['confidence', 'quality', 'sensor_health', 'eligibility', 'samples'])
def test_current_gates_block_temporal_promotion(block):
    _, state = sequence([-0.22] * 7)
    raw = edge(8)
    kwargs = {}
    if block == 'confidence':
        raw['confidence'] = 0.2
    elif block == 'quality':
        kwargs['data_quality'] = {'data_confidence': {'rating': 0.2}}
    elif block == 'sensor_health':
        kwargs['sensor_health'] = {'signals': [{'signal': c, 'health': 'suspect', 'conditions': [{'type': 'flatline_or_stuck'}]} for c in PAIR]}
    elif block == 'eligibility':
        raw['relationship_context']['operator_primary_eligible'] = False
    else:
        raw['current_sample_count'] = 2
    current = analyze(raw, state, **kwargs)['edges'][0]
    assert not current['promoted_changed_edge']
    assert not current['temporal_persistence_supported']


def test_bad_historical_windows_do_not_count_and_support_expires():
    state = None
    for day in range(1, 9):
        result = analyze(edge(day, confidence=0.2 if day < 6 else 0.73), state)
        state = result['relationship_persistence_state']
    assert not result['changed_edges']
    assert result['edges'][0]['temporal_persistence_supporting_observations'] == 3
    _, state = sequence([-0.22] * 8)
    expired = analyze(edge(45), state)
    assert not expired['changed_edges']
    assert expired['edges'][0]['temporal_persistence_observations'] == 1
    recovered, _ = sequence([-0.22] * 8 + [0.0] * 8)
    assert not recovered[-1]['promoted_changed_edge']
    assert not recovered[-1]['supporting_windows']


def test_samples_retries_and_undated_windows_cannot_invent_temporal_support():
    raw = edge(1, baseline_sample_count=100000, current_sample_count=100000)
    state = None
    for _ in range(10):
        result = analyze(raw, state)
        state = result['relationship_persistence_state']
    actual = result['edges'][0]
    assert not actual['promoted_changed_edge']
    assert actual['sample_sufficiency_factor'] == 1.0
    assert actual['temporal_persistence_observations'] == 1
    undated = analyze({**raw, 'time_window': {}})['edges'][0]
    assert undated['temporal_persistence_observations'] == 0
    assert undated['temporal_persistence_status'] == 'limited'
    assert undated['persistence_factor'] == 0


@pytest.mark.parametrize('change', ['baseline', 'basis', 'mode', 'reference', 'units', 'out_of_order', 'conflicting_retry', 'invalid_window', 'invalid_timestamp'])
def test_incompatible_or_nonchronological_observations_do_not_reuse_support(change):
    _, state = sequence([-0.22] * 8)
    raw = edge(9)
    kwargs = {}
    if change == 'baseline':
        raw['baseline_correlation'] -= 0.01
    elif change == 'basis':
        kwargs['mode_conditioned_analysis'] = {'mode_relationships': {'edges': [raw]}}
    elif change == 'mode':
        raw['mode_conditioning'] = {'mode_id': 'new-mode'}
    elif change == 'reference':
        raw['reference_dataset_id'] = 'different-reference'
    elif change == 'units':
        raw['signal_units'] = {PAIR[0]: 'other-unit'}
    elif change == 'invalid_timestamp':
        raw['time_window']['current_start'] = 'not-a-time'
    elif change == 'out_of_order':
        raw = edge(7)
    elif change == 'conflicting_retry':
        raw = edge(8, -0.21)
    else:
        raw['time_window']['current_start'] = '2027-01-01T00:00:00+00:00'
    saved = deepcopy(state)
    result = analyze(raw, state, **kwargs)
    assert not result['changed_edges']
    assert not result['edges'][0]['temporal_persistence_supported']
    assert state == saved


def test_deterministic_read_only_state_and_no_causal_output():
    _, state = sequence([-0.22] * 8)
    raw = edge(9)
    saved = deepcopy((raw, state))
    a, b = analyze(raw, state), analyze(raw, state)
    assert a['edges'] == b['edges']
    assert a['relationship_persistence_state'] == b['relationship_persistence_state']
    assert (raw, state) == saved
    replay = analyze(raw, a['relationship_persistence_state'])
    assert replay['edges'] == a['edges']
    assert replay['relationship_persistence_state'] == a['relationship_persistence_state']
    payload = json.dumps(a['edges']).lower()
    assert all(word not in payload for word in ('diagnosis', 'cause', 'prescri', 'recommend'))


def test_paired_engine_carries_read_only_state_into_governed_evidence(monkeypatch):
    from app.engine.sii_engine import evaluate_sii
    from app.services import sii_runner
    monkeypatch.setattr(sii_runner, 'write_latest_sii_state', lambda *_a, **_k: pytest.fail('read-only evaluation wrote state'))
    def rows(day, correlation):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
        return [{'timestamp': (start + timedelta(minutes=i)).isoformat(),
                 PAIR[0]: 4 + math.sin(2 * math.pi * i / 48),
                 PAIR[1]: 10 + correlation * math.sin(2 * math.pi * i / 48) + math.sqrt(1-correlation**2) * math.cos(2 * math.pi * i / 48)}
                for i in range(48)]
    reference = rows(0, BASELINE)
    state = None
    for day in range(1, 7):
        args = dict(columns=['timestamp', *PAIR], reference_rows=reference,
                    comparison_rows=rows(day, -0.89), timestamp_column='timestamp',
                    numeric_profiles=[{'column': c, 'constant_or_stuck': False, 'missing_count': 0, 'non_numeric_count': 0} for c in PAIR],
                    signal_units={c: None for c in PAIR}, relationship_persistence_state=state)
        saved = deepcopy(args)
        result = evaluate_sii(**args)
        assert args == saved
        assert result['processing_trace']['modules_failed'] == []
        state = result['relationship_graph']['relationship_persistence_state']
    current = result['relationship_graph']['edges'][0]
    assert current['promoted_changed_edge'], current
    governed = result['analysis_result']['sii_evidence']['relationship_changes'][0]
    assert governed['persistent_relationship_change']
    assert governed['supporting_windows'] == current['supporting_windows']
    assert all(w['source_dataset_id'] for w in governed['supporting_windows'])


@pytest.mark.parametrize(('baseline', 'delta', 'expected'), [
    (0.9, -0.2, 'weakened'), (-0.9, 0.2, 'weakened'),
    (0.65, 0.2, 'strengthened'), (-0.65, -0.2, 'strengthened'),
])
def test_temporal_change_classification_uses_strength_for_both_signs(baseline, delta, expected):
    outputs, _ = sequence([delta] * 6, baseline=baseline)
    assert outputs[-1]['change_type'] == expected
    assert outputs[-1]['promoted_changed_edge']


def test_historical_quality_and_legacy_sample_setting_cannot_supply_votes():
    state = None
    for day in range(1, 9):
        result = analyze(edge(day), state, data_quality={'data_confidence': {'rating': 0.2 if day < 6 else 0.9}},
                         config={'minimum_persistence_observations': 1})
        state = result['relationship_persistence_state']
    assert not result['changed_edges']
    assert result['edges'][0]['sample_sufficiency_factor'] == 1
    assert result['edges'][0]['temporal_persistence_supporting_observations'] == 3
