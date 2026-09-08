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
