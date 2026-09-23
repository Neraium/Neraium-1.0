"""Numerical and parsing equivalence against the pre-performance algorithms.

References intentionally retain the old operations: tests guard bit-for-bit
arithmetic, malformed-input semantics, and stable tie ordering during optimization.
"""
from __future__ import annotations
import math
import random
from typing import Any
import numpy as np
import pytest
from app.services import behavioral_baseline, data_quality


def _mean(values):
    return sum(values) / max(1, len(values))


def reference_parse_numeric_value(raw_value: Any) -> float | None:
    normalized = str(raw_value if raw_value is not None else "").strip()
    if not normalized:
        return None
    normalized = normalized.replace(",", "").replace("%", "")
    lowered = normalized.lower()
    if lowered in {"nan", "null", "none", "n/a", "na", "-"}:
        return None
    pieces = normalized.split()
    candidate = pieces[0] if pieces else normalized
    try:
        value = float(candidate)
    except ValueError:
        filtered = "".join(char for char in candidate if char.isdigit() or char in {".", "-", "+"})
        if filtered in {"", "-", "+", ".", "-.", "+."}:
            return None
        try:
            value = float(filtered)
        except ValueError:
            return None
    if not math.isfinite(value):
        return None
    return value

def reference_correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean = _mean(left)
    right_mean = _mean(right)
    covariance = 0.0
    left_variance = 0.0
    right_variance = 0.0
    for left_value, right_value in zip(left, right):
        left_delta = left_value - left_mean
        right_delta = right_value - right_mean
        covariance += left_delta * right_delta
        left_variance += left_delta * left_delta
        right_variance += right_delta * right_delta
    denominator = math.sqrt(left_variance * right_variance)
    if denominator <= 1e-12:
        return None
    return covariance / denominator



def test_numeric_parser_preserves_all_legacy_input_forms():
    examples = [None, True, False, 0, -0.0, 1e30, float('nan'), float('inf'),
                '', ' ', '1,234.5%', '12 kPa', '12 34', 'nan', 'null', 'NONE',
                'n/a', '-', '+.', 'infinity', '-Inf', '1_000', '1e-300',
                '１２.５', '١٢.٥', '12\u00a0kPa', '°12C', '1%2', b'12',
                '1e999', '1e-999', '-0', '-0.0', '+0.0']
    rng = random.Random(412)
    alphabet = '0123456789.,%+-eEnNaA/ _\tµ°１２'
    examples += [''.join(rng.choices(alphabet, k=rng.randrange(1, 25))) for _ in range(3000)]
    for value in examples:
        expected = reference_parse_numeric_value(value)
        actual = data_quality.parse_numeric_value(value)
        assert actual == expected, repr(value)
        if actual is not None:
            assert actual.hex() == expected.hex(), repr(value)


@pytest.mark.parametrize('size', [3, 127, 128, 129, 1024, 4096, 100000])
@pytest.mark.parametrize('offset,scale', [(0., 1.), (1e12, .01), (0., 1e-100), (0., 1e100)])
def test_correlation_preserves_sequential_arithmetic(size, offset, scale):
    rng = np.random.default_rng(119)
    left = (offset + scale*rng.normal(size=size)).tolist()
    right = (offset + scale*rng.normal(size=size)).tolist()
    for candidate in (right, left, left[::-1], [0.] * size):
        expected = reference_correlation(left, candidate)
        actual = behavioral_baseline._correlation(left, candidate)
        assert actual == expected
        if actual is not None:
            assert actual.hex() == expected.hex()


def test_mode_ties_keep_first_seen_signature_and_unretained_membership():
    values = ['b', 'a', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j']
    modes, membership = behavioral_baseline._identify_modes(
        [{'equipment_state': value} for value in values],
        ['equipment_state'], [], {'equipment_state': {'canonical_role': 'equipment_state'}},
    )
    assert [item['label'] for item in modes] == values[:8]
    assert membership['mode_1'] == [0, 8, 9]
    assert list(membership) == [f'mode_{i}' for i in range(1, 9)]
    assert behavioral_baseline._identify_modes([], [], [], {}) == ([], {})


def test_unit_marker_ascii_fast_path_preserves_unicode_rules():
    from app.services.historical_ingestion import _has_unit_marker
    cases = [chr(i) for i in range(128)] + [
        '123.45678', '-12.4e-3', '12 kPa', '12%', '23°C', '12µm', '１２.３',
        '℃', '²', '泵', '12\u00a0kg', '', '\ud800',
    ]
    for value in cases:
        expected = any(char.isalpha() or char in '%°' for char in value)
        assert _has_unit_marker(value) is expected


@pytest.mark.parametrize('rows,columns', [(2, 1), (12, 2), (12, 3), (12, 17), (80, 12)])
def test_cached_mahalanobis_path_matches_original_contraction(rows, columns):
    from app.services.sii_runner import (
        _baseline_mahalanobis_distances, _baseline_distance_contraction_path,
    )
    rng = np.random.default_rng(918)
    matrix = rng.normal(size=(rows, columns))
    mean = np.mean(matrix, axis=0)
    covariance = rng.normal(size=(columns, columns))
    inverse = np.linalg.pinv(covariance @ covariance.T + np.eye(columns))
    centered = np.nan_to_num(np.asarray(matrix, dtype=float) - mean, nan=0.)
    squares = np.einsum('ij,jk,ik->i', centered, inverse, centered, optimize=True)
    expected = np.sqrt(np.clip(squares[np.isfinite(squares)], 0., None)).astype(float).tolist()
    original = matrix.copy()
    _baseline_distance_contraction_path.cache_clear()
    for _ in range(3):
        actual = _baseline_mahalanobis_distances(matrix, mean, inverse)
        assert [x.hex() for x in actual] == [x.hex() for x in expected]
    assert _baseline_distance_contraction_path.cache_info().hits == 2
    assert _baseline_distance_contraction_path.cache_info().maxsize == 64
    np.testing.assert_array_equal(matrix, original)


def test_correlation_keeps_python_float_behavior_under_numpy_error_policy():
    left = [1e308, -1e308] * 64
    right = list(reversed(left))
    expected = reference_correlation(left, right)
    with np.errstate(all='raise'):
        actual = behavioral_baseline._correlation(left, right)
    assert math.isnan(actual) and math.isnan(expected)
