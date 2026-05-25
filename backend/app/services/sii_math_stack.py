from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


EPSILON = 1e-9


@dataclass(frozen=True)
class SiiMathResult:
    score: float
    components: dict[str, float]
    raw: dict[str, Any]
    dominant_driver_index: int | None


def compute_full_sii_math_stack(
    history: list[np.ndarray],
    *,
    baseline_window: int,
    recent_window: int,
    confidence: float,
) -> SiiMathResult:
    """Compute the full SII instability function I(t)=f(D,R,E,C,T).

    This module intentionally uses only numpy so it can run anywhere the backend
    runner already runs. Each component is independently calculated from the
    telemetry history rather than being a display-only proxy.
    """
    matrix = _clean_matrix(history)
    baseline, recent = _split_baseline_recent(matrix, baseline_window, recent_window)

    drift, drift_raw = _state_drift_component(baseline, recent)
    relationship, relationship_raw = _relationship_degradation_component(baseline, recent)
    entropy, entropy_raw = _entropy_growth_component(baseline, recent)
    causal, causal_raw = _causal_evidence_component(matrix, confidence)
    topology, topology_raw = _topology_propagation_component(baseline, recent)

    components = {
        "drift": drift,
        "relationship_degradation": relationship,
        "entropy_growth": entropy,
        "causal_evidence": causal,
        "topology_propagation": topology,
    }
    score = _clip01(
        drift * 0.35
        + relationship * 0.25
        + entropy * 0.15
        + causal * 0.15
        + topology * 0.10
    )
    dominant_driver_index = _dominant_driver_index(baseline, recent)
    return SiiMathResult(
        score=round(score, 6),
        components={key: round(_clip01(value), 6) for key, value in components.items()},
        raw={
            "state_drift": drift_raw,
            "relationship_degradation": relationship_raw,
            "entropy_growth": entropy_raw,
            "causal_evidence": causal_raw,
            "topology_propagation": topology_raw,
            "model": {"name": "sii_instability_index", "version": "full-stack-v1"},
        },
        dominant_driver_index=dominant_driver_index,
    )


def _clean_matrix(history: list[np.ndarray]) -> np.ndarray:
    if not history:
        return np.empty((0, 0), dtype=float)
    matrix = np.vstack([np.asarray(row, dtype=float) for row in history])
    if matrix.ndim == 1:
        matrix = matrix.reshape(-1, 1)
    column_means = np.nanmean(matrix, axis=0)
    column_means = np.where(np.isfinite(column_means), column_means, 0.0)
    indexes = np.where(~np.isfinite(matrix))
    if indexes[0].size:
        matrix = matrix.copy()
        matrix[indexes] = np.take(column_means, indexes[1])
    return np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)


def _split_baseline_recent(matrix: np.ndarray, baseline_window: int, recent_window: int) -> tuple[np.ndarray, np.ndarray]:
    if matrix.size == 0:
        empty = np.empty((0, 0), dtype=float)
        return empty, empty
    if matrix.shape[0] == 1:
        return matrix, matrix
    recent_count = min(max(2, recent_window), matrix.shape[0])
    recent = matrix[-recent_count:]
    baseline_source = matrix[:-recent_count]
    if baseline_source.size == 0:
        split = max(1, matrix.shape[0] // 2)
        baseline_source = matrix[:split]
    baseline_count = min(max(2, baseline_window), baseline_source.shape[0])
    baseline = baseline_source[-baseline_count:]
    return baseline, recent


def _state_drift_component(baseline: np.ndarray, recent: np.ndarray) -> tuple[float, dict[str, Any]]:
    if baseline.size == 0 or recent.size == 0:
        return 0.0, {"mean_delta": 0.0, "trajectory_pressure": 0.0}
    baseline_mean = np.mean(baseline, axis=0)
    recent_mean = np.mean(recent, axis=0)
    baseline_scale = np.maximum(np.abs(baseline_mean), np.std(baseline, axis=0) + 1.0)
    normalized_delta = np.abs(recent_mean - baseline_mean) / (baseline_scale + EPSILON)
    mean_delta = float(np.mean(normalized_delta))
    if recent.shape[0] >= 2:
        velocity = np.diff(recent, axis=0)
        trajectory_pressure = float(np.mean(np.abs(velocity) / (baseline_scale + EPSILON)))
    else:
        trajectory_pressure = 0.0
    score = _saturating(mean_delta * 0.70 + trajectory_pressure * 0.30)
    return score, {
        "mean_delta": round(mean_delta, 6),
        "trajectory_pressure": round(trajectory_pressure, 6),
        "per_channel_delta": [round(float(value), 6) for value in normalized_delta.tolist()],
    }


def _relationship_degradation_component(baseline: np.ndarray, recent: np.ndarray) -> tuple[float, dict[str, Any]]:
    if baseline.shape[0] < 3 or recent.shape[0] < 3 or baseline.shape[1] < 2:
        return 0.0, {"correlation_distance": 0.0, "edge_change_ratio": 0.0}
    corr_base = _safe_corrcoef(baseline)
    corr_recent = _safe_corrcoef(recent)
    delta = np.abs(corr_recent - corr_base)
    upper = _upper_triangle(delta)
    correlation_distance = float(np.mean(upper)) if upper.size else 0.0
    base_edges = np.abs(_upper_triangle(corr_base))
    recent_edges = np.abs(_upper_triangle(corr_recent))
    edge_change_ratio = float(np.mean(np.abs(recent_edges - base_edges))) if base_edges.size else 0.0
    score = _clip01(correlation_distance * 0.70 + edge_change_ratio * 0.30)
    return score, {
        "correlation_distance": round(correlation_distance, 6),
        "edge_change_ratio": round(edge_change_ratio, 6),
    }


def _entropy_growth_component(baseline: np.ndarray, recent: np.ndarray) -> tuple[float, dict[str, Any]]:
    if baseline.size == 0 or recent.size == 0:
        return 0.0, {"baseline_entropy": 0.0, "recent_entropy": 0.0, "entropy_delta": 0.0}
    baseline_entropy = _matrix_entropy(baseline)
    recent_entropy = _matrix_entropy(recent)
    entropy_delta = max(0.0, recent_entropy - baseline_entropy)
    variance_ratio = float(np.mean(np.std(recent, axis=0) / (np.std(baseline, axis=0) + 1.0 + EPSILON)))
    score = _clip01(_saturating(entropy_delta) * 0.65 + _clip01(variance_ratio / 3.0) * 0.35)
    return score, {
        "baseline_entropy": round(baseline_entropy, 6),
        "recent_entropy": round(recent_entropy, 6),
        "entropy_delta": round(entropy_delta, 6),
        "variance_ratio": round(variance_ratio, 6),
    }


def _causal_evidence_component(matrix: np.ndarray, confidence: float) -> tuple[float, dict[str, Any]]:
    if matrix.shape[0] < 4 or matrix.shape[1] < 2:
        return _clip01(confidence * 0.35), {"lagged_directionality": 0.0, "confidence": round(confidence, 6)}
    lagged_scores: list[float] = []
    current = matrix[1:]
    lagged = matrix[:-1]
    for source_idx in range(matrix.shape[1]):
        source = lagged[:, source_idx]
        for target_idx in range(matrix.shape[1]):
            if source_idx == target_idx:
                continue
            target = current[:, target_idx]
            corr = _safe_pair_corr(source, target)
            if corr > 0:
                lagged_scores.append(abs(corr))
    lagged_directionality = float(np.mean(lagged_scores)) if lagged_scores else 0.0
    score = _clip01(lagged_directionality * 0.70 + confidence * 0.30)
    return score, {
        "lagged_directionality": round(lagged_directionality, 6),
        "confidence": round(float(confidence), 6),
        "evidence_pairs": len(lagged_scores),
    }


def _topology_propagation_component(baseline: np.ndarray, recent: np.ndarray) -> tuple[float, dict[str, Any]]:
    if baseline.shape[0] < 3 or recent.shape[0] < 3 or baseline.shape[1] < 2:
        return 0.0, {"spectral_radius_delta": 0.0, "activation_spread": 0.0}
    adj_base = np.abs(_safe_corrcoef(baseline))
    adj_recent = np.abs(_safe_corrcoef(recent))
    np.fill_diagonal(adj_base, 0.0)
    np.fill_diagonal(adj_recent, 0.0)
    radius_base = _spectral_radius(adj_base)
    radius_recent = _spectral_radius(adj_recent)
    spectral_radius_delta = max(0.0, radius_recent - radius_base) / (radius_base + 1.0)
    channel_shift = np.abs(np.mean(recent, axis=0) - np.mean(baseline, axis=0))
    active = channel_shift > (np.std(baseline, axis=0) + EPSILON)
    activation_spread = float(np.mean(active)) if active.size else 0.0
    score = _clip01(_saturating(spectral_radius_delta) * 0.60 + activation_spread * 0.40)
    return score, {
        "spectral_radius_baseline": round(radius_base, 6),
        "spectral_radius_recent": round(radius_recent, 6),
        "spectral_radius_delta": round(float(spectral_radius_delta), 6),
        "activation_spread": round(activation_spread, 6),
    }


def _matrix_entropy(matrix: np.ndarray) -> float:
    if matrix.size == 0:
        return 0.0
    values = np.ravel(matrix.astype(float))
    if values.size < 2 or np.allclose(values, values[0]):
        return 0.0
    hist, _ = np.histogram(values, bins="auto", density=False)
    probs = hist.astype(float) / max(float(np.sum(hist)), 1.0)
    probs = probs[probs > 0]
    return float(-np.sum(probs * np.log2(probs)))


def _safe_corrcoef(matrix: np.ndarray) -> np.ndarray:
    if matrix.shape[1] == 1:
        return np.ones((1, 1), dtype=float)
    corr = np.corrcoef(matrix, rowvar=False)
    if corr.ndim == 0:
        corr = np.array([[float(corr)]], dtype=float)
    return np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)


def _safe_pair_corr(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 2 or b.size < 2 or np.allclose(a, a[0]) or np.allclose(b, b[0]):
        return 0.0
    corr = np.corrcoef(a, b)[0, 1]
    return float(np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0))


def _upper_triangle(matrix: np.ndarray) -> np.ndarray:
    if matrix.shape[0] < 2:
        return np.array([], dtype=float)
    idx = np.triu_indices(matrix.shape[0], k=1)
    return matrix[idx]


def _spectral_radius(matrix: np.ndarray) -> float:
    if matrix.size == 0:
        return 0.0
    try:
        values = np.linalg.eigvals(matrix)
    except np.linalg.LinAlgError:
        return 0.0
    return float(np.max(np.abs(values))) if values.size else 0.0


def _dominant_driver_index(baseline: np.ndarray, recent: np.ndarray) -> int | None:
    if baseline.size == 0 or recent.size == 0:
        return None
    baseline_mean = np.mean(baseline, axis=0)
    recent_mean = np.mean(recent, axis=0)
    scale = np.maximum(np.std(baseline, axis=0), 1.0)
    delta = np.abs(recent_mean - baseline_mean) / (scale + EPSILON)
    if delta.size == 0:
        return None
    return int(np.argmax(delta))


def _saturating(value: float) -> float:
    value = max(0.0, float(value))
    return float(1.0 - np.exp(-value))


def _clip01(value: float) -> float:
    return float(np.clip(np.nan_to_num(value, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0))
