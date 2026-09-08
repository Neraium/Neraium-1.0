"""Strict, read-only paired input boundary; no analytical calculations."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any

from app.engine.sii_inputs import normalize_rows
from app.engine.temporal_math import TemporalMathConfig
from app.services.cumulative_counters import is_cumulative_counter_name

MAX_PAIRED_ROWS = 12000


def prepare_supplied_reference(*, columns, reference_rows, comparison_rows,
                               numeric_profiles, timestamp_column, signal_units, config):
    if (not isinstance(columns, list) or not columns
            or any(not isinstance(c, str) or not c or c.startswith('__') for c in columns)
            or len(set(columns)) != len(columns)):
        raise ValueError('paired_columns_must_be_unique_explicit_signal_names')
    signals = [c for c in columns if c != timestamp_column]
    if not 1 <= len(signals) <= 32:
        raise ValueError('paired_requires_1_to_32_numeric_signals')
    if timestamp_column is not None and timestamp_column not in columns:
        raise ValueError('paired_timestamp_column_missing')
    if not isinstance(signal_units, dict) or set(signal_units) != set(signals) or any(
        v is not None and (not isinstance(v, str) or not v.strip()) for v in signal_units.values()
    ):
        raise ValueError('paired_signal_units_required_for_shared_schema_use_null_for_unknown')
    if not isinstance(numeric_profiles, list) or [p.get('column') for p in numeric_profiles if isinstance(p, dict)] != signals:
        raise ValueError('paired_numeric_profiles_must_match_all_signals_in_order')
    if any(is_cumulative_counter_name(c) for c in signals):
        raise ValueError('paired_cumulative_counters_not_supported')
    allowed = {'numeric_columns', 'temporal_config', 'engineering_priors', 'physics_reasoning_config'}
    if set(config) - allowed:
        raise ValueError('unsupported_paired_configuration')
    if config.get('numeric_columns', signals) != signals:
        raise ValueError('paired_numeric_columns_must_match_shared_schema')
    cfg = dict(config)
    temporal = cfg.get('temporal_config')
    if isinstance(temporal, dict):
        temporal = TemporalMathConfig(**temporal)
    if temporal is None:
        temporal = TemporalMathConfig(max_rows=MAX_PAIRED_ROWS)
    if not isinstance(temporal, TemporalMathConfig) or not 1 <= temporal.max_rows <= MAX_PAIRED_ROWS:
        raise ValueError('unsupported_paired_temporal_limit')
    cfg['temporal_config'] = temporal
    cfg['numeric_columns'] = signals
    prepared = []
    provenance: dict[str, Any] = {'contract_version': 'supplied-reference-v1', 'signal_units': dict(signal_units), 'signals': signals}
    for role, rows in [('reference', reference_rows), ('comparison', comparison_rows)]:
        if not isinstance(rows, list) or not 16 <= len(rows) <= min(MAX_PAIRED_ROWS, temporal.max_rows):
            raise ValueError(f'paired_{role}_requires_16_to_{min(MAX_PAIRED_ROWS, temporal.max_rows)}_rows')
        prior_time = None
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(columns):
                raise ValueError(f'paired_{role}_row_schema_mismatch')
            for c in signals:
                value = row[c]
                if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                    raise ValueError(f'paired_{role}_numeric_value_required:{c}')
                try:
                    valid = math.isfinite(float(value))
                except (ValueError, OverflowError):
                    valid = False
                if not valid:
                    raise ValueError(f'paired_{role}_finite_numeric_value_required:{c}')
            if timestamp_column:
                value = row[timestamp_column]
                try:
                    parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else None
                    if parsed is None or parsed.tzinfo is None or (prior_time is not None and parsed <= prior_time):
                        raise ValueError()
                except (ValueError, TypeError):
                    raise ValueError(f'paired_{role}_requires_ordered_timezone_aware_timestamps') from None
                prior_time = parsed
        digest = hashlib.sha256(json.dumps({'columns': columns, 'units': signal_units, 'rows': rows}, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        provenance[role] = {'role': role, 'dataset_id': f'sha256:{digest}', 'input_hash': digest,
                            'row_count': len(rows), 'row_start': 1, 'row_end': len(rows),
                            'time_start': rows[0].get(timestamp_column), 'time_end': rows[-1].get(timestamp_column)}
        dict_rows, matrix = normalize_rows(columns, rows)
        for index, row in enumerate(dict_rows, 1):
            row['__source_row_number'] = index
            row['__source_timestamp'] = row.get(timestamp_column)
        prepared.append((dict_rows, matrix))
    provenance['limitations'] = [
        'Units are caller-declared shared schema; unknown units remain unknown.',
        'Persistent behavioral memory is unavailable in read-only supplied-reference evaluation.',
        'Multiscale evidence describes changes within the comparison period.',
        'Covariance recent windows remain bounded by the existing runner configuration.',
        'Elapsed persistence retains the existing terminal-sample median-interval convention.',
        'Temporal lead-time estimates are heuristic evidence, not a verified event or failure prediction.',
    ]
    if timestamp_column is None:
        provenance['limitations'].append('No timestamps supplied; elapsed persistence and timestamp onset are unavailable.')
    return prepared[0], prepared[1], cfg, provenance
