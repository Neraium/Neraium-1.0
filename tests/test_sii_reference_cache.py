from app.services.output_semantics import semantic_content
"""Exact sequential runner equivalence and fixed-reference cache boundaries."""
import numpy as np
import pytest

from app.services import sii_runner


@pytest.mark.parametrize('reference_kind', ['varying', 'constant', 'missing', 'short'])
def test_reference_cache_preserves_every_frame(reference_kind):
    rng = np.random.default_rng(41)
    reference = rng.normal(size=(96, 4))
    if reference_kind == 'constant':
        reference[:] = 3.0
    elif reference_kind == 'missing':
        reference[::3, 1] = np.nan
        reference[:, 3] = np.nan
    elif reference_kind == 'short':
        reference = reference[:3]
    original = reference.copy()
    cached = sii_runner.BackendSiiRunner(reference_vectors=reference)
    uncached = sii_runner.BackendSiiRunner(reference_vectors=reference)
    uncached._reference_value = lambda key, calculate: calculate()
    for index, vector in enumerate(rng.normal(size=(55, 4))):
        if index == 20:
            vector[2] = np.nan
        args = dict(sensor_vector=vector, timestamp=float(index), asset_id='asset', run_id='run')
        assert cached.ingest(**args) == uncached.ingest(**args)
    np.testing.assert_array_equal(reference, original)
    assert len(cached._reference_cache) <= 9


def test_fixed_reference_reuse_and_in_place_invalidation(monkeypatch):
    rng = np.random.default_rng(12)
    reference = rng.normal(size=(64, 3))
    cached = sii_runner.BackendSiiRunner(reference_vectors=reference)
    uncached = sii_runner.BackendSiiRunner(reference_vectors=reference)
    uncached._reference_value = lambda key, calculate: calculate()
    distances = sii_runner._baseline_mahalanobis_distances
    calls = []
    def observed(*args):
        calls.append(True)
        return distances(*args)
    monkeypatch.setattr(sii_runner, '_baseline_mahalanobis_distances', observed)
    for index in range(12):
        if index == 6:
            reference[5, 1] += 3.0
        args = dict(sensor_vector=rng.normal(size=3), timestamp=float(index), asset_id='a', run_id='r')
        assert cached.ingest(**args) == uncached.ingest(**args)
    assert len(calls) == 12 + 2


def test_rolling_baselines_are_never_cached():
    runner = sii_runner.BackendSiiRunner()
    for index in range(30):
        runner.ingest(sensor_vector=np.array([index, index+2.0]), timestamp=float(index), asset_id='a', run_id='r')
    assert runner._reference_cache == {}


def test_failed_calculation_is_retried_and_cache_is_instance_local():
    runner = sii_runner.BackendSiiRunner(reference_vectors=np.ones((16, 2)))
    def fail():
        raise ValueError('transient failure')
    with pytest.raises(ValueError):
        runner._reference_value('test', fail)
    assert runner._reference_value('test', lambda: 42) == 42
    fresh = sii_runner.BackendSiiRunner(reference_vectors=np.ones((16, 2)))
    assert fresh._reference_cache == {}


@pytest.mark.parametrize('current_correlation', [-0.89, -0.668462])
def test_cache_preserves_governed_temporal_replay(monkeypatch, current_correlation):
    from copy import deepcopy
    from datetime import datetime, timedelta, timezone
    import math

    from app.engine.sii_engine import evaluate_sii

    columns = ['Aeration_DO_mgL', 'Effluent_Turbidity_NTU']

    def rows(day, correlation):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
        return [
            {'timestamp': (start + timedelta(minutes=i)).isoformat(),
             columns[0]: 4 + math.sin(2 * math.pi * i / 48),
             columns[1]: 10 + correlation * math.sin(2 * math.pi * i / 48)
             + math.sqrt(1 - correlation**2) * math.cos(2 * math.pi * i / 48)}
            for i in range(48)
        ]

    monkeypatch.setattr(sii_runner, 'write_latest_sii_state',
                        lambda *_a, **_k: pytest.fail('read-only replay wrote state'))
    cached_states, uncached_states = None, None
    promotions = []
    for day in range(1, 9):
        args = dict(
            columns=['timestamp', *columns], reference_rows=rows(0, -0.668462),
            comparison_rows=rows(day, current_correlation), timestamp_column='timestamp',
            numeric_profiles=[{'column': c, 'constant_or_stuck': False,
                               'missing_count': 0, 'non_numeric_count': 0} for c in columns],
            signal_units={c: None for c in columns},
        )
        original = deepcopy((args, cached_states, uncached_states))
        cached = evaluate_sii(**args, relationship_persistence_state=cached_states)
        with monkeypatch.context() as patch:
            patch.setattr(sii_runner.BackendSiiRunner, '_reference_value',
                          lambda self, key, calculate: calculate())
            uncached = evaluate_sii(**args, relationship_persistence_state=uncached_states)
        assert (args, cached_states, uncached_states) == original
        for result in (cached, uncached):
            assert result['processing_trace']['modules_failed'] == []
            assert result['compatibility']['sii_runner_result']['rows_processed'] == 48
        assert semantic_content(cached['relationship_graph']) == semantic_content(uncached['relationship_graph'])
        assert cached['analysis_result']['insights'] == uncached['analysis_result']['insights']
        assert cached['analysis_result']['evidence_index'] == uncached['analysis_result']['evidence_index']
        assert cached['analysis_result']['sii_evidence'] == uncached['analysis_result']['sii_evidence']
        assert cached['supplied_reference'] == uncached['supplied_reference']
        cached_states = cached['relationship_graph']['relationship_persistence_state']
        uncached_states = uncached['relationship_graph']['relationship_persistence_state']
        assert cached_states == uncached_states
        promotions.append(cached['relationship_graph']['edges'][0]['promoted_changed_edge'])
    assert promotions == ([False] * 5 + [True] * 3 if current_correlation == -0.89 else [False] * 8)
