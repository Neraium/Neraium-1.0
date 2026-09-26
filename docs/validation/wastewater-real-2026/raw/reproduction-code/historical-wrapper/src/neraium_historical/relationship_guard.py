"""Strict pair accounting for complete-case, global Pearson relationship graphs.

This supervisor check never edits engine evidence or persistence state. Absences
are accepted only when the actual submitted values prove zero variance; all
other omissions fail closed. Counts alone cannot explain a missing edge.
"""
from itertools import combinations
import math


def account_relationship_pairs(result, signals, reference_rows, comparison_rows):
    graph = result['relationship_graph']
    model = result['compatibility']['relationship_model']
    if result['processing_trace'].get('modules_failed'):
        raise ValueError('Failed engine modules')
    if model.get('excluded_structural_columns'):
        raise ValueError('Unexpected structural exclusions')
    if graph['edge_basis'] != 'global_relationship_model':
        raise ValueError('Pair guard requires verified global relationship inputs')
    # Match this harness\'s full-input engine limits; refuse to infer availability
    # from a different population (sampled or mode-conditioned data).
    if not (3 <= len(reference_rows) <= 12000 and 3 <= len(comparison_rows) <= 6000):
        raise ValueError('Unverified relationship input population')
    constants = {}
    for role, rows in [('reference', reference_rows), ('comparison', comparison_rows)]:
        for signal in signals:
            values = [float(row[signal]) for row in rows]
            if not all(math.isfinite(v) for v in values):
                raise ValueError('Pair guard requires finite complete-case inputs')
            if min(values) == max(values):
                constants.setdefault(signal, []).append({
                    'reason': 'zero_variance', 'window': role, 'signal': signal,
                    'constant_value': values[0], 'sample_count': len(values)})
    expected = {tuple(sorted(p)) for p in combinations(signals, 2)}
    actual = set()
    for edge in graph['edges']:
        pair = tuple(sorted(edge['columns']))
        if pair in actual:
            raise ValueError(f'Duplicate relationship pair: {pair}')
        if pair not in expected:
            raise ValueError(f'Unexpected relationship pair: {pair}')
        actual.add(pair)
        if any(s in constants for s in pair):
            raise ValueError(f'Correlation returned for zero-variance pair: {pair}')
        for key in ('baseline_correlation', 'current_correlation', 'signed_correlation_delta'):
            if not math.isfinite(edge[key]):
                raise ValueError(f'Non-finite relationship evidence: {pair}')
    unavailable = []
    for pair in sorted(expected - actual):
        reasons = [reason for s in pair for reason in constants.get(s, [])]
        if not reasons:
            raise ValueError(f'Unexplained missing relationship pair: {pair}')
        unavailable.append({'columns': list(pair), 'status': 'unavailable',
                            'reason': 'undefined_pearson_zero_variance', 'evidence': reasons})
    accounting = model['relationship_pair_accounting']
    if (accounting['pairs_evaluated'] != len(expected)
            or accounting['pairs_deeply_analyzed'] != len(actual)
            or accounting.get('signal_limit_applied')):
        raise ValueError('Incorrect relationship graph construction accounting')
    return {'expected_pairs': len(expected), 'available_pairs': len(actual),
            'unavailable_pairs': unavailable, 'all_pairs_accounted_for': True}
