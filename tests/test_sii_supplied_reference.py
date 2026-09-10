from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math

import pytest

from app.engine.sii_engine import evaluate_sii
from app.engine.supplied_reference import prepare_supplied_reference
from app.engine.temporal_math import evaluate_temporal_math, TemporalMathConfig
from app.services.baseline_analysis import build_baseline_analysis
from app.services.relationship_baselines import build_relationship_baseline
from app.services.sii_runner import BackendSiiRunner
import numpy as np


def contract(count=64):
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    reference, comparison = [], []
    for i in range(count):
        wave = math.sin(i / 4)
        reference.append({'timestamp': (start - timedelta(days=90) + timedelta(minutes=i)).isoformat(),
                          'flow': 80 + wave * 4, 'pressure': 40 + wave * 2, 'power': 20 + wave})
        comparison.append({'timestamp': (start + timedelta(minutes=i)).isoformat(),
                           'flow': 80 + wave * 4, 'pressure': 55 + math.cos(i * 2) * 2, 'power': 28 + wave})
    signals = ['flow', 'pressure', 'power']
    return dict(columns=['timestamp', *signals], reference_rows=reference, comparison_rows=comparison,
                numeric_profiles=[{'column': c, 'constant_or_stuck': False, 'missing_count': 0, 'non_numeric_count': 0} for c in signals],
                timestamp_column='timestamp', signal_units={'flow': None, 'pressure': None, 'power': None})


def prepare(args):
    return prepare_supplied_reference(**args, config={})


def test_real_paired_governed_integration_is_read_only(monkeypatch):
    from app.services import sii_runner
    monkeypatch.setattr(sii_runner, 'write_latest_sii_state', lambda *_a, **_k: pytest.fail('paired evaluation wrote latest state'))
    args = contract()
    original = deepcopy(args)
    result = evaluate_sii(**args)
    assert args == original
    assert result['processing_trace']['modules_failed'] == []
    assert result['signal_drift']['baseline_window_rows'] == 64
    assert result['signal_drift']['recent_window_rows'] == 64
    assert result['temporal_analysis']['baseline_rows'] == 64
    assert result['temporal_analysis']['active_rows'] == 64
    assert result['covariance_analysis']['status'] == 'complete'
    assert result['compatibility']['sii_runner_result']['rows_processed'] == 64
    assert not result['compatibility']['sii_runner_result']['sampling_applied']
    assert result['relationship_graph']['changed_edges']
    assert result['analysis_result']['sii_evidence']['relationship_changes']
    assert result['findings'] == result['analysis_result']['insights']
    assert result['findings']  # Real existing governed construction, not injected findings.
    assert result['analysis_result']['evidence_index']
    persistence = result['persistence_analysis']['adaptive_persistence']
    assert persistence['elapsed_time_available']
    assert persistence['rows_used'] == 64
    onset = result['temporal_analysis']['lead_time_estimate']['timestamp']
    assert onset in [r['timestamp'] for r in args['comparison_rows']]
    provenance = result['supplied_reference']
    assert provenance['reference']['time_start'] == args['reference_rows'][0]['timestamp']
    assert provenance['comparison']['time_end'] == args['comparison_rows'][-1]['timestamp']
    assert provenance['reference']['dataset_id'] != provenance['comparison']['dataset_id']
    assert result['analysis_result']['sii_evidence']['supplied_reference'] == provenance
    assert result['behavioral_model']['status'] == 'limited'


@pytest.mark.parametrize('mutation', [
    lambda a: a['comparison_rows'][0].pop('flow'),
    lambda a: a['reference_rows'][0].update(unexpected=1),
    lambda a: a['reference_rows'][0].update(flow='invalid'),
    lambda a: a['reference_rows'][0].update(flow=float('nan')),
    lambda a: a['comparison_rows'][0].update(flow=True),
    lambda a: a['reference_rows'][0].update(timestamp='2026-01-01'),
    lambda a: a['comparison_rows'][1].update(timestamp=a['comparison_rows'][0]['timestamp']),
    lambda a: a.update(signal_units={'flow': None}),
    lambda a: a.update(reference_rows=a['reference_rows'][:3]),
    lambda a: a.update(columns=['timestamp', 'flow', 'flow', 'power']),
])
def test_malformed_pairs_fail_before_engine(mutation):
    args = contract(16)
    mutation(args)
    with pytest.raises(ValueError):
        evaluate_sii(**args)


def test_rejects_ambiguous_or_persisting_contracts():
    args = contract(16)
    for extra in [{'rows': args['comparison_rows']}, {'operating_mode': {}},
                  {'config': {'row_count_total': 999}}, {'config': {'temporal_config': {'max_rows': 15}}}]:
        with pytest.raises(ValueError):
            evaluate_sii(**args, **extra)


def test_8640_envelope_uses_supported_full_period_limit():
    reference, comparison, cfg, provenance = prepare(contract(8640))
    assert len(reference[0]) == len(comparison[0]) == 8640
    assert cfg['temporal_config'].max_rows == 12000
    assert provenance['comparison']['row_end'] == 8640
    args = contract(16)
    args['comparison_rows'] *= 751
    with pytest.raises(ValueError, match='16_to_12000'):
        prepare(args)


def test_supplied_baseline_stable_and_changed_use_same_existing_math():
    args = contract()
    reference, comparison, _, _ = prepare(args)
    baseline = build_baseline_analysis(args['columns'], comparison[1], args['numeric_profiles'], reference_rows=reference[1])
    assert next(d for d in baseline['column_drift'] if d['column'] == 'power')['baseline_average'] < 21
    stable = build_baseline_analysis(args['columns'], reference[1], args['numeric_profiles'], reference_rows=reference[1])
    assert all(d['absolute_change'] == 0 for d in stable['column_drift'])
    relationships = build_relationship_baseline(reference[0], ['flow', 'pressure', 'power'], reference_rows=reference[0])
    assert not relationships['top_relationship_changes']


def test_comparison_onset_and_persistence_do_not_include_reference_gap():
    from app.engine.sii.adaptive_persistence import evaluate_adaptive_persistence
    args = contract()
    reference, comparison, cfg, _ = prepare(args)
    drift = build_baseline_analysis(args['columns'], comparison[1], args['numeric_profiles'], reference_rows=reference[1])
    persistence = evaluate_adaptive_persistence(rows=comparison[0], timestamp_column='timestamp', baseline_analysis=drift)
    assert persistence['elapsed_time_available']
    assert persistence['rows_used'] == 64
    assert persistence['observed_duration_seconds'] <= 64 * 60
    temporal = evaluate_temporal_math(columns=args['columns'], rows=comparison[1], reference_rows=reference[1],
                                     numeric_profiles=args['numeric_profiles'], timestamp_column='timestamp', config=cfg['temporal_config'])
    assert temporal['active_rows'] == 64
    assert temporal['lead_time_estimate']['timestamp'] in [r['timestamp'] for r in args['comparison_rows']]
    with pytest.raises(ValueError, match='temporal_limit'):
        evaluate_temporal_math(columns=args['columns'], rows=comparison[1], reference_rows=reference[1],
                              numeric_profiles=args['numeric_profiles'], timestamp_column='timestamp', config=TemporalMathConfig(max_rows=20))
    fallback = evaluate_adaptive_persistence(rows=comparison[0], timestamp_column=None, baseline_analysis=drift)
    assert not fallback['elapsed_time_available']


def test_covariance_reference_never_seeds_comparison_history():
    reference = np.array([[1., 2.], [2., 4.], [3., 6.]])
    runner = BackendSiiRunner(reference_vectors=reference)
    runner._history.append(np.array([9., 10.]))
    baseline, recent = runner._windowed_history()
    assert baseline is reference
    assert len(recent) == 1
    assert runner._history_count == 0


def test_governed_windows_keep_independent_bounds_and_no_invented_onset():
    from app.services.analysis_result_contract import build_behavior_windows
    from app.engine.temporal_math import _lead_time_estimate
    _, _, _, provenance = prepare(contract(16))
    result = build_behavior_windows(result={'sii_result': {'supplied_reference': provenance}},
                                    baseline={}, relationships=[], insights=[])
    assert result['stable_window']['start'] == provenance['reference']['time_start']
    assert result['current_state_window']['end'] == provenance['comparison']['time_end']
    assert result['change_onset'] == ''
    onset = _lead_time_estimate(state_drift_series=np.zeros(16), relationship_series=[0.] * 16,
                               entropy_series=np.zeros(16), evidence_series=[0.] * 16,
                               baseline_count=0, timestamp_column='timestamp', columns=['timestamp'],
                               rows=[['2026-07-01T00:00:00Z']] * 16, require_trigger=True)
    assert onset['timestamp'] is None
    assert onset['rows_before_event'] == 0


def test_reference_fitting_and_like_mode_provenance_exclude_comparison():
    from app.engine.sii.empirical_thresholds import estimate_empirical_thresholds
    from app.engine.sii.mode_conditioned_baseline import analyze_mode_conditioned_baseline
    args = contract()
    reference, comparison, _, _ = prepare(args)
    learned = estimate_empirical_thresholds(rows=comparison[0], reference_rows=reference[0], numeric_columns=['power'])
    assert learned['fit_window']['rows'] == 64
    assert learned['fit_window']['active_rows_excluded'] == 64
    assert learned['signal_thresholds']['power']['baseline_center'] < 21
    mode = analyze_mode_conditioned_baseline(rows=comparison[0], reference_rows=reference[0],
                                            numeric_columns=['flow', 'pressure', 'power'], timestamp_column='timestamp')
    assert mode['selection']['historical_end_index_exclusive'] == 64
    assert mode['selection']['recent_start_index'] == 0
    assert mode['selection']['recent_rows'] == 64


def source_clock_contract(count=64, start=datetime(2026, 6, 1)):
    args = contract(count)
    for role, offset in [('reference', -90), ('comparison', 0)]:
        for i, row in enumerate(args[f'{role}_rows']):
            row['timestamp'] = (start + timedelta(days=offset, minutes=15 * i)).strftime('%Y-%m-%d %H:%M:%S')
    return args


def test_source_clock_contract_provenance_and_timing(monkeypatch):
    from app.services import sii_runner
    monkeypatch.setattr(sii_runner, 'write_latest_sii_state', lambda *_a, **_k: pytest.fail('paired evaluation wrote state'))
    args = source_clock_contract()
    original = deepcopy(args)
    reference, comparison, _, provenance = prepare(args)
    assert args == original
    for role, prepared in [('reference', reference), ('comparison', comparison)]:
        supplied = [r['timestamp'] for r in args[f'{role}_rows']]
        assert provenance[role]['source_timestamps'] == supplied
        assert [r['__source_timestamp'] for r in prepared[0]] == supplied
        assert [r[0] for r in prepared[1]] == supplied
    assert provenance['contract_version'] == 'supplied-reference-v1.1'
    assert provenance['timestamp_mode'] == 'naive_historical_source_clock'
    assert provenance['source_timezone'] == {'status': 'timezone_not_supplied', 'value': None}
    assert provenance['timing_basis'] == 'direct_source_clock_datetime_differences'
    assert any('timezone_not_supplied' in s and 'absolute UTC instants' in s
               and 'timezone offset' in s and 'daylight-saving interpretation' in s
               and 'not established' in s for s in provenance['limitations'])
    result = evaluate_sii(**args)
    assert args == original
    assert result['processing_trace']['modules_failed'] == []
    governed = result['analysis_result']['sii_evidence']['supplied_reference']
    assert governed == result['supplied_reference']
    assert {key: governed[key] for key in provenance} == provenance
    persistence = result['persistence_analysis']['adaptive_persistence']
    assert persistence['elapsed_time_available']
    assert persistence['sampling_regular']
    assert persistence['timestamp_profile']['median_interval_seconds'] == 900
    assert persistence['observed_duration_seconds'] == 64 * 900  # Terminal sample credit.
    assert {d['column'] for d in persistence['details']} == {'pressure', 'power'}
    for detail in persistence['details']:
        assert detail['supporting_duration_seconds'] == 64 * 900
        assert detail['longest_continuous_support_seconds'] == 64 * 900
    onset = result['temporal_analysis']['lead_time_estimate']
    supplied = provenance['comparison']['source_timestamps']
    onset_index = supplied.index(onset['timestamp'])
    assert onset['seconds_since_comparison_start'] == onset_index * 900
    assert onset['seconds_to_comparison_end'] == (63 - onset_index) * 900
    runner = result['compatibility']['sii_runner_result']
    assert runner['timestamp_basis'] == 'source_clock_seconds_since_comparison_start'
    assert runner['source_clock_origin'] == supplied[0]
    assert runner['latest_state']['timestamp'] == 63 * 900


@pytest.mark.parametrize('role', ['reference', 'comparison'])
@pytest.mark.parametrize('invalid', [
    '06/01/2026 00:15:00', '01/06/2026 00:15:00', '2026-06-01',
    '2026-06-01T00:15:00', '2026-06-01 00:15:00.000',
    '2026-02-30 00:15:00', '2026-06-01 00:15:00+00:00',
    '1780272900', 1780272900, 1780272900000,
])
def test_source_clock_rejects_invalid_or_mixed_timestamps(role, invalid):
    args = source_clock_contract(16)
    args[f'{role}_rows'][1]['timestamp'] = invalid
    with pytest.raises(ValueError, match=f'paired_{role}_requires_ordered'):
        prepare(args)


@pytest.mark.parametrize('role', ['reference', 'comparison'])
@pytest.mark.parametrize('duplicate', [False, True])
def test_source_clock_rejects_unordered_or_duplicate_timestamps(role, duplicate):
    args = source_clock_contract(16)
    rows = args[f'{role}_rows']
    if duplicate:
        rows[1]['timestamp'] = rows[0]['timestamp']
    else:
        rows[0], rows[1] = rows[1], rows[0]
    with pytest.raises(ValueError, match=f'paired_{role}_requires_ordered'):
        prepare(args)


@pytest.mark.parametrize('naive_role', ['reference', 'comparison'])
def test_pair_rejects_different_timestamp_modes(naive_role):
    args = contract(16)
    args[f'{naive_role}_rows'] = source_clock_contract(16)[f'{naive_role}_rows']
    with pytest.raises(ValueError, match='paired_timestamp_modes_must_match'):
        prepare(args)


def test_aware_contract_keeps_existing_timing_and_provenance():
    args = contract()
    _, _, _, provenance = prepare(args)
    assert provenance['contract_version'] == 'supplied-reference-v1'
    assert 'timestamp_mode' not in provenance
    assert 'source_timezone' not in provenance
    result = evaluate_sii(**args)
    persistence = result['persistence_analysis']['adaptive_persistence']
    assert persistence['timestamp_profile']['median_interval_seconds'] == 60
    assert persistence['observed_duration_seconds'] == 64 * 60
    assert 'seconds_since_comparison_start' not in result['temporal_analysis']['lead_time_estimate']
    runner = result['compatibility']['sii_runner_result']
    assert 'timestamp_basis' not in runner
    assert runner['latest_state']['timestamp'] == datetime.fromisoformat(args['comparison_rows'][-1]['timestamp']).timestamp()


@pytest.mark.parametrize('start', [datetime(2026, 3, 7, 12), datetime(2026, 10, 31, 12)])
def test_source_clock_results_are_host_timezone_independent(monkeypatch, start):
    import os
    import time
    if not hasattr(time, 'tzset'):
        pytest.skip('Requires POSIX tzset')
    args = source_clock_contract(start=start)
    original_tz = os.environ.get('TZ')
    snapshots = []
    try:
        for zone in ['UTC0', 'EST5EDT,M3.2.0/2,M11.1.0/2', 'JST-9']:
            monkeypatch.setenv('TZ', zone)
            time.tzset()
            result = evaluate_sii(**args)
            assert result['processing_trace']['modules_failed'] == []
            persistence = result['persistence_analysis']['adaptive_persistence']
            assert persistence['observed_duration_seconds'] == 64 * 900
            # The six-hour window itself crosses the host's spring/fall transition.
            six_hours = next(s for s in result['multiscale_analysis']['scales'] if s['name'] == '6_hours')
            assert six_hours['active_rows'] == 24
            assert six_hours['baseline_rows'] == 40
            assert six_hours['actual_active_span_seconds'] == 23 * 900
            snapshots.append({
                'provenance': result['supplied_reference'],
                'onset': result['temporal_analysis']['lead_time_estimate'],
                'cadence': persistence['timestamp_profile'],
                'duration': persistence['observed_duration_seconds'],
                'scales': result['multiscale_analysis']['scales'],
                'runner_timestamp': result['compatibility']['sii_runner_result']['latest_state']['timestamp'],
            })
    finally:
        if original_tz is None:
            monkeypatch.delenv('TZ', raising=False)
        else:
            monkeypatch.setenv('TZ', original_tz)
        time.tzset()
    assert snapshots[0] == snapshots[1] == snapshots[2]


def test_source_clock_delayed_onset_uses_comparison_clock_only():
    args = source_clock_contract()
    for i in range(32):
        for column in ['flow', 'pressure', 'power']:
            args['comparison_rows'][i][column] = args['reference_rows'][i][column]
    reference, comparison, cfg, _ = prepare(args)
    result = evaluate_temporal_math(
        columns=args['columns'], rows=comparison[1], reference_rows=reference[1],
        numeric_profiles=args['numeric_profiles'], timestamp_column='timestamp',
        config=cfg['temporal_config'], source_clock=True,
    )
    onset = result['lead_time_estimate']
    assert onset['timestamp'] == '2026-06-01 08:00:00'
    assert onset['seconds_since_comparison_start'] == 32 * 900
    assert onset['seconds_to_comparison_end'] == 31 * 900


@pytest.mark.parametrize('role', ['reference', 'comparison'])
def test_aware_dataset_rejects_naive_timestamp(role):
    args = contract(16)
    args[f'{role}_rows'][1]['timestamp'] = '2026-06-01 00:15:00'
    with pytest.raises(ValueError, match=f'paired_{role}_requires_ordered_timezone_aware_timestamps'):
        prepare(args)
