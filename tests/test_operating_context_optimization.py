"""Pre-change complete operating-context contracts; no relaxed comparisons."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import gzip
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.engine.sii import common
from app.engine.sii import mode_conditioned_baseline as conditioned
from app.engine.sii_engine import evaluate_sii
from app.services import operating_modes as modes
from app.services.historical_comparables import ComparableHistoricalEpisodeService
from app.services.output_semantics import semantic_content

FIXTURE = Path(__file__).parent / 'fixtures/operating_context_optimization/before.json.gz'


def exact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def rows(count=40, context=None):
    start = datetime(2026, 7, 3, 5, 45, tzinfo=timezone.utc)
    return [dict(timestamp=(start + timedelta(minutes=15*i)).isoformat(),
                 flow=80 + i % 9, pressure=40 + 2*(i % 9),
                 __source_row_number=i + 1, __source_timestamp=(start + timedelta(minutes=15*i)).isoformat(),
                 **(context or {})) for i in range(count)]


def cases():
    result = {}
    def add(name, data, **kwargs):
        result[name] = {'rows': data, **kwargs}
    add('single_feature', rows(context={'pump_stage': 1}))
    add('multiple_features', rows(context={'pump_stage': 1, 'load_pct': 60, 'ambient_temp': 22, 'schedule': 'occupied'}))
    add('absent_context', rows())
    add('empty', [])
    add('insufficient_recent', rows(5, {'pump_stage': 1}))
    add('missing_context', rows(context={'pump_stage': None, 'load_pct': ''}))
    for column in ['load_pct', 'pump_stage', 'maintenance_state']:
        data = rows(context={column: 1})
        for i, value in enumerate([None, '', 'bad', 'NaN', 'inf', '-inf', float('nan'), float('inf'), '-', 'n/a', 0, -1]):
            data[i][column] = value
        add('invalid_' + column, data)
    data = rows(context={'pump_stage': 1})
    for row in data[28:]: row['pump_stage'] = 2
    add('non_comparable', data)
    data = rows(context={'pump_stage': 1})
    for row in data[10:28]: row.pop('pump_stage')
    add('insufficient_baseline', data)
    data = rows(context={'pump_stage': 1})
    for i, row in enumerate(data): row['pump_stage'] = 1 if i % 2 else 2
    add('majority_tie', data)
    data = rows(context={'load_a': 0, 'load_b': 100})
    for i, row in enumerate(data): row['load_a'], row['load_b'] = i, 40-i
    add('duplicate_role_candidates', data)
    add('reordered_role_candidates', [{**{k:v for k,v in r.items() if not k.startswith('load_')}, 'load_b':r['load_b'], 'load_a':r['load_a']} for r in data])
    add('equivalent_role_candidates', rows(context={'load_a': 50, 'load_b': 50}))
    add('aggregated_equipment', rows(context={'pump_a_status': 1, 'pump_b_status': 0, 'active_unit_count': 7}))
    add('role_hint_precedence', rows(context={'maintenance_load_state': 'off', 'valve_state': 1, 'speed_load': 60}))
    catalog = {'mystery': {'telemetry_classification': {'category': 'scheduled_load_context'}}, 'pump_stage': {'telemetry_classification': {'category': 'setpoint'}}}
    add('catalog_role_override', rows(context={'mystery': 50, 'pump_stage': 2}), catalog=catalog)
    add('catalog_list', rows(context={'mystery': 50}), catalog=[{'source_column': 'mystery', 'telemetry_classification': {'category': 'weather_environment'}}])
    data = rows(context={'load_pct': 50, 'pump_stage': 1})
    add('row_order', data)
    add('reversed_row_order', list(reversed(data)))
    times = ['2026-07-03T05:59:59Z', '2026-07-03T06:00:00Z', '2026-07-03T17:59:59Z', '2026-07-03T18:00:00Z', '2026-07-03T23:59:59Z', '2026-07-04T00:00:00Z', 'bad', None]
    data = rows(context={'pump_stage': 1})
    for i, row in enumerate(data): row['timestamp'] = times[i % len(times)]
    add('time_day_week_boundaries', data)
    for threshold in [math.nextafter(0.7, 0), 0.7, math.nextafter(0.7, 1)]:
        data = rows(10, {'pump_stage': 'on'})
        for row in data[-3:]: row['pump_stage'] = 'off'
        add('purity_' + repr(threshold), data, reference=rows(20, {'pump_stage': 'on'}), config={'minimum_recent_mode_purity': threshold})
    add('reference_qualified', rows(12, {'pump_stage': 1}), reference=rows(20, {'pump_stage': 1}))
    add('empty_reference', rows(12, {'pump_stage': 1}), reference=[])
    add('exact_sample_minima', rows(6, {'pump_stage': 1}), reference=rows(12, {'pump_stage': 1}))
    add('below_sample_minima', rows(5, {'pump_stage': 1}), reference=rows(11, {'pump_stage': 1}))
    return result


CASES = cases()


def primitive_cases():
    result = {}
    for role in ['speed_band', 'load_band', 'outdoor_air_band']:
        for value in [math.nextafter(10., 0), 10., math.nextafter(10., 20), math.nextafter(20., 10), 20., math.nextafter(20., 30)]:
            result[f'{role}_{value!r}'] = {'rows': [{'value': value}], 'signals': [modes.ContextSignal('value', role)], 'references': {'value': (10., 20.)}}
        result[role+'_equal_references'] = {'rows': [{'value': 100}], 'signals': [modes.ContextSignal('value', role)], 'references': {'value': (10., 10.)}}
    for role in ['maintenance_state', 'cleaning_cycle', 'special_event', 'setpoint', 'active_unit_count', 'equipment_state', 'valve_state', 'schedule_state']:
        result[role] = {'rows': [{'value': v} for v in [None, '', 'bad', 'nan', 'inf', -1, -0.0, 0, math.nextafter(0., 1), 1, 2, 'on', 'off']], 'signals': [modes.ContextSignal('value', role)], 'references': {}}
    result['state_lexical_tie'] = {'rows': [{'value': 'z'}, {'value': 'a'}], 'signals': [modes.ContextSignal('value', 'equipment_state')], 'references': {}}
    return result


PRIMITIVES = primitive_cases()


def capture_primitives(case):
    descriptor = modes.describe_mode(case['rows'], case['signals'], case['references'], None)
    projected = {key: descriptor['features'][key] for key in dict.fromkeys(descriptor['explicit_features'])}
    if hasattr(modes, 'explicit_mode_features'):
        features, explicit = modes.explicit_mode_features(case['rows'], case['signals'], case['references'])
        assert exact(features) == exact(projected)
        assert explicit == descriptor['explicit_features']
    return {'descriptor': descriptor, 'explicit_features': projected,
            'signal_summaries': [modes.summarize_signal(case['rows'], signal, case['references'].get(signal.column)) for signal in case['signals']]}


def capture_context(case, monkeypatch):
    # Isolated fixed module timer permits equality of the ENTIRE raw envelope.
    monkeypatch.setattr(conditioned, 'time', SimpleNamespace(perf_counter=lambda: 100.0))
    monkeypatch.setattr(common, 'time', SimpleNamespace(perf_counter=lambda: 100.0))
    original = json.dumps(case, allow_nan=True)
    data = case['rows']; reference = case.get('reference'); catalog = case.get('catalog')
    context = data if reference is None else reference + data
    signals = modes.context_signals(context, 'timestamp', catalog)
    refs = modes.numeric_band_references(context, signals)
    descriptors = [modes.describe_mode([row], signals, refs, 'timestamp') for row in context]
    explicit = [{key: d['features'][key] for key in dict.fromkeys(d['explicit_features'])} for d in descriptors]
    if hasattr(modes, 'explicit_mode_features'):
        for row, descriptor, projection in zip(context, descriptors, explicit):
            features, roles = modes.explicit_mode_features([row], signals, refs)
            assert exact(features) == exact(projection)
            assert roles == descriptor['explicit_features']
    assessment = modes.assess_operating_modes(data, reference_rows=reference, timestamp_column='timestamp', telemetry_signal_catalog=catalog)
    progress = []
    result = conditioned.analyze_mode_conditioned_baseline(
        rows=data, reference_rows=reference, numeric_columns=['flow', 'pressure'], timestamp_column='timestamp',
        telemetry_signal_catalog=catalog, operating_mode=assessment, config=case.get('config'),
        progress_callback=lambda *args: progress.append(list(args)))
    comparable = ComparableHistoricalEpisodeService().retrieve(rows=data, relationship={'columns':['flow','pressure']}, timestamp_column='timestamp', telemetry_signal_catalog=catalog)
    assert json.dumps(case, allow_nan=True) == original
    return {'signals': [asdict(s) for s in signals], 'references': refs, 'row_descriptors': descriptors,
            'row_explicit_features': explicit, 'aggregate_descriptor': modes.describe_mode(context, signals, refs, 'timestamp'),
            'assessment': assessment, 'conditioned': result, 'progress': progress, 'historical_comparables': comparable}


ENGINE_CASES = ['ordinary_batch', 'ordinary_batch_reversed', 'paired_aware', 'paired_source_clock', 'source_clock_reversed_rejected']


def capture_engine(name):
    data = rows(64, {'load_pct': 50, 'pump_stage': 1})
    data = [{k:v for k,v in row.items() if not k.startswith('__')} for row in data]
    numeric = ['flow', 'pressure', 'load_pct', 'pump_stage']
    args = {'columns': ['timestamp', *numeric], 'numeric_profiles': [{'column':c, 'constant_or_stuck':False, 'missing_count':0, 'non_numeric_count':0} for c in numeric], 'timestamp_column':'timestamp'}
    if name.startswith('ordinary_batch'):
        args['rows'] = list(reversed(data)) if name.endswith('reversed') else data
    else:
        reference = deepcopy(data)
        for row in reference:
            row['timestamp'] = (datetime.fromisoformat(row['timestamp']) - timedelta(days=90)).isoformat()
        if 'source_clock' in name:
            for row in data + reference: row['timestamp'] = datetime.fromisoformat(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        if name.endswith('rejected'): data.reverse()
        args.update(reference_rows=reference, comparison_rows=data, signal_units={c:None for c in numeric})
    before = deepcopy(args)
    try:
        first = evaluate_sii(**args)
        assert first['processing_trace']['modules_failed'] == []
        graph = first['relationship_graph']
        second = evaluate_sii(**args, relationship_persistence_state=graph['relationship_persistence_state'], relationship_recurrence_state=graph['relationship_recurrence_state'])
        result = {'first':semantic_content(first), 'sequential':semantic_content(second)}
    except ValueError as exc:
        assert name == 'source_clock_reversed_rejected'
        result = {'error':type(exc).__name__, 'message':str(exc)}
    assert args == before
    return result


def expected():
    with gzip.open(FIXTURE, 'rt') as handle: return json.load(handle)


@pytest.mark.parametrize('name', CASES)
def test_complete_operating_context_matches_prechange(name, monkeypatch):
    assert exact(capture_context(CASES[name], monkeypatch)) == exact(expected()['context'][name])


@pytest.mark.parametrize('name', PRIMITIVES)
def test_complete_primitive_and_descriptor_matches_prechange(name):
    assert exact(capture_primitives(PRIMITIVES[name])) == exact(expected()['primitives'][name])


@pytest.mark.parametrize('name', ENGINE_CASES)
def test_complete_engine_context_and_sequential_state_matches_prechange(name):
    assert exact(capture_engine(name)) == exact(expected()['engine'][name])


def test_purity_boundary_and_catalog_fixtures_cover_the_intended_contract(monkeypatch):
    for threshold, ambiguous in [(math.nextafter(0.7, 0), False), (0.7, False), (math.nextafter(0.7, 1), True)]:
        result = capture_context(CASES['purity_' + repr(threshold)], monkeypatch)['conditioned']
        assert result['selection']['recent_feature_support'] == {'equipment_state': 0.7}
        assert result['selected_operating_mode']['ambiguous'] is ambiguous
        assert result['selection']['selected_historical_indices'] == list(range(20))
    result = capture_context(CASES['catalog_role_override'], monkeypatch)
    assert result['signals'] == [{'column': 'mystery', 'role': 'load_band'}, {'column': 'pump_stage', 'role': 'setpoint'}]
    assert capture_context(CASES['catalog_list'], monkeypatch)['signals'] == [{'column': 'mystery', 'role': 'outdoor_air_band'}]
