from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

EPSILON = 1e-9


@dataclass(frozen=True)
class SiiStructuralV2Result:
    structural_drift_score: float
    stability_state: str
    urgency: str
    dynamic_threshold: float
    persistence_count: int
    rolling_accumulation: float
    drift_velocity: float
    drift_acceleration: float
    covariance_shift: float
    trajectory_curvature: float
    transition_pressure: float
    multi_signal_confirmation: float
    components: dict[str, float]
    raw: dict[str, Any]
    dominant_driver_index: int | None


def compute_sii_structural_v2(
    history: list[np.ndarray],
    *,
    baseline_window: int,
    recent_window: int,
    persistence_k: int = 3,
    accumulation_window: int = 6,
) -> SiiStructuralV2Result:
    matrix = _clean_matrix(history)
    baseline, recent = _split_baseline_recent(matrix, baseline_window, recent_window)
    if matrix.size == 0 or baseline.size == 0 or recent.size == 0:
        return _empty_result()

    mu, cov = _baseline_distribution(baseline)
    drift_series = np.array([_mahalanobis(row, mu, cov) for row in matrix], dtype=float)
    current_drift = float(drift_series[-1]) if drift_series.size else 0.0
    drift_velocity = _last_first_difference(drift_series)
    drift_acceleration = _last_second_difference(drift_series)
    covariance_shift = _covariance_shift(baseline, recent)
    trajectory_curvature = _trajectory_curvature(matrix)
    transition_pressure = _transition_pressure(drift_velocity, drift_acceleration, trajectory_curvature)
    multi_signal_confirmation = _multi_signal_confirmation(matrix, baseline, recent)

    threshold = _dynamic_threshold(drift_series, baseline.shape[1])
    rolling_values = drift_series[-max(1, accumulation_window):]
    rolling_accumulation = float(np.sum(rolling_values))
    accumulation_threshold = threshold * min(accumulation_window, drift_series.size) * 0.85
    persistence_count = _recent_persistence_count(drift_series, threshold)
    persistent = persistence_count >= persistence_k
    accumulated = rolling_accumulation >= accumulation_threshold
    directional = drift_velocity > 0 or drift_acceleration > 0

    structural_drift_score = _structural_drift_score(
        current_drift=current_drift,
        threshold=threshold,
        drift_velocity=drift_velocity,
        drift_acceleration=drift_acceleration,
        covariance_shift=covariance_shift,
        trajectory_curvature=trajectory_curvature,
        multi_signal_confirmation=multi_signal_confirmation,
    )
    stability_state, urgency = _classify_state(
        history_length=matrix.shape[0],
        score=structural_drift_score,
        persistent=persistent,
        accumulated=accumulated,
        directional=directional,
        transition_pressure=transition_pressure,
    )
    components = {
        "mahalanobis_drift": _normalize_ratio(current_drift, threshold),
        "drift_velocity": _saturating(abs(drift_velocity)),
        "drift_acceleration": _saturating(abs(drift_acceleration)),
        "covariance_shift": covariance_shift,
        "trajectory_curvature": trajectory_curvature,
        "multi_signal_confirmation": multi_signal_confirmation,
        "persistence_gate": 1.0 if persistent else persistence_count / max(float(persistence_k), 1.0),
        "accumulation_gate": _clip01(rolling_accumulation / (accumulation_threshold + EPSILON)),
    }
    return SiiStructuralV2Result(
        structural_drift_score=round(structural_drift_score, 6),
        stability_state=stability_state,
        urgency=urgency,
        dynamic_threshold=round(float(threshold), 6),
        persistence_count=int(persistence_count),
        rolling_accumulation=round(rolling_accumulation, 6),
        drift_velocity=round(float(drift_velocity), 6),
        drift_acceleration=round(float(drift_acceleration), 6),
        covariance_shift=round(float(covariance_shift), 6),
        trajectory_curvature=round(float(trajectory_curvature), 6),
        transition_pressure=round(float(transition_pressure), 6),
        multi_signal_confirmation=round(float(multi_signal_confirmation), 6),
        components={key: round(_clip01(value), 6) for key, value in components.items()},
        raw={
            "model": {"name": "sii_structural_instability", "version": "technical-overview-v2"},
            "current_mahalanobis_drift": round(current_drift, 6),
            "drift_series_tail": [round(float(value), 6) for value in drift_series[-20:].tolist()],
            "accumulation_threshold": round(float(accumulation_threshold), 6),
            "persistence_required": int(persistence_k),
            "persistence_condition_met": bool(persistent),
            "accumulation_condition_met": bool(accumulated),
            "directional_condition_met": bool(directional),
            "baseline_window_used": int(baseline.shape[0]),
            "recent_window_used": int(recent.shape[0]),
            "dimension_count": int(matrix.shape[1]),
        },
        dominant_driver_index=_dominant_driver_index(mu, cov, matrix[-1]),
    )


def _empty_result() -> SiiStructuralV2Result:
    return SiiStructuralV2Result(0.0, "WARMUP", "NOMINAL", 0.0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {}, {"model": {"name": "sii_structural_instability", "version": "technical-overview-v2"}}, None)


def _clean_matrix(history: list[np.ndarray]) -> np.ndarray:
    if not history:
        return np.empty((0, 0), dtype=float)
    matrix = np.vstack([np.asarray(row, dtype=float) for row in history])
    if matrix.ndim == 1:
        matrix = matrix.reshape(-1, 1)
    column_means = np.nanmean(matrix, axis=0)
    column_means = np.where(np.isfinite(column_means), column_means, 0.0)
    bad = np.where(~np.isfinite(matrix))
    if bad[0].size:
        matrix = matrix.copy()
        matrix[bad] = np.take(column_means, bad[1])
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
        baseline_source = matrix[: max(1, matrix.shape[0] // 2)]
    baseline_count = min(max(2, baseline_window), baseline_source.shape[0])
    baseline = baseline_source[-baseline_count:]
    return baseline, recent


def _baseline_distribution(baseline: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mu = np.mean(baseline, axis=0)
    cov = np.cov(baseline, rowvar=False) if baseline.shape[0] >= 2 else np.eye(baseline.shape[1], dtype=float)
    if cov.ndim == 0:
        cov = np.array([[float(cov)]], dtype=float)
    return mu, cov + np.eye(cov.shape[0], dtype=float) * 1e-4


def _mahalanobis(vector: np.ndarray, mu: np.ndarray, cov: np.ndarray) -> float:
    delta = np.asarray(vector, dtype=float) - mu
    inv_cov = np.linalg.pinv(cov)
    return float(np.sqrt(max(float(delta.T @ inv_cov @ delta), 0.0)))


def _dynamic_threshold(drift_series: np.ndarray, dimensions: int) -> float:
    if drift_series.size < 4:
        return max(1.0, float(np.sqrt(max(dimensions, 1))))
    baseline_slice = drift_series[: max(3, drift_series.size // 2)]
    median = float(np.median(baseline_slice))
    mad = float(np.median(np.abs(baseline_slice - median)))
    return max(float(np.sqrt(max(dimensions, 1))), median + 3.0 * 1.4826 * mad, 1.0)


def _recent_persistence_count(drift_series: np.ndarray, threshold: float) -> int:
    count = 0
    for value in reversed(drift_series.tolist()):
        if value >= threshold:
            count += 1
        else:
            break
    return count


def _last_first_difference(values: np.ndarray) -> float:
    return float(values[-1] - values[-2]) if values.size >= 2 else 0.0


def _last_second_difference(values: np.ndarray) -> float:
    return float(values[-1] - 2.0 * values[-2] + values[-3]) if values.size >= 3 else 0.0


def _covariance_shift(baseline: np.ndarray, recent: np.ndarray) -> float:
    if baseline.shape[0] < 2 or recent.shape[0] < 2:
        return 0.0
    cov_base = np.cov(baseline, rowvar=False)
    cov_recent = np.cov(recent, rowvar=False)
    if cov_base.ndim == 0:
        cov_base = np.array([[float(cov_base)]], dtype=float)
    if cov_recent.ndim == 0:
        cov_recent = np.array([[float(cov_recent)]], dtype=float)
    return _clip01(float(np.linalg.norm(cov_recent - cov_base, ord="fro")) / (float(np.linalg.norm(cov_base, ord="fro")) + 1.0))


def _trajectory_curvature(matrix: np.ndarray) -> float:
    if matrix.shape[0] < 3:
        return 0.0
    prev_v = matrix[-2] - matrix[-3]
    now_v = matrix[-1] - matrix[-2]
    denom = float(np.linalg.norm(prev_v) * np.linalg.norm(now_v) + EPSILON)
    angle = float(np.arccos(np.clip(float(np.dot(prev_v, now_v) / denom), -1.0, 1.0)))
    return _clip01(angle / np.pi)


def _transition_pressure(velocity: float, acceleration: float, curvature: float) -> float:
    return _clip01(_saturating(max(0.0, velocity)) * 0.50 + _saturating(max(0.0, acceleration)) * 0.30 + curvature * 0.20)


def _multi_signal_confirmation(matrix: np.ndarray, baseline: np.ndarray, recent: np.ndarray) -> float:
    baseline_mean = np.mean(baseline, axis=0)
    recent_mean = np.mean(recent, axis=0)
    baseline_std = np.std(baseline, axis=0) + 1.0
    z_like = np.abs(recent_mean - baseline_mean) / (baseline_std + EPSILON)
    dimension_confirmation = float(np.mean(z_like >= 1.0)) if z_like.size else 0.0
    if matrix.shape[1] < 2 or recent.shape[0] < 3:
        return _clip01(dimension_confirmation)
    corr_recent = np.nan_to_num(np.corrcoef(recent, rowvar=False), nan=0.0)
    if corr_recent.ndim == 0:
        corr_recent = np.array([[float(corr_recent)]])
    coupling = float(np.mean(np.abs(_upper_triangle(corr_recent)))) if corr_recent.shape[0] > 1 else 0.0
    return _clip01(dimension_confirmation * 0.70 + coupling * 0.30)


def _structural_drift_score(*, current_drift: float, threshold: float, drift_velocity: float, drift_acceleration: float, covariance_shift: float, trajectory_curvature: float, multi_signal_confirmation: float) -> float:
    return _clip01(_normalize_ratio(current_drift, threshold) * 0.40 + _saturating(max(0.0, drift_velocity)) * 0.18 + _saturating(max(0.0, drift_acceleration)) * 0.12 + covariance_shift * 0.14 + trajectory_curvature * 0.08 + multi_signal_confirmation * 0.08)


def _classify_state(*, history_length: int, score: float, persistent: bool, accumulated: bool, directional: bool, transition_pressure: float) -> tuple[str, str]:
    if history_length < 3:
        return "WARMUP", "NOMINAL"
    if persistent and accumulated and score >= 0.68:
        return "ALERT", "CRITICAL"
    if (persistent or accumulated) and directional and (score >= 0.38 or transition_pressure >= 0.35):
        return "WATCH", "WATCH"
    return "STABLE", "NOMINAL"


def _dominant_driver_index(mu: np.ndarray, cov: np.ndarray, current: np.ndarray) -> int | None:
    if current.size == 0:
        return None
    std = np.sqrt(np.maximum(np.diag(cov), EPSILON))
    contribution = np.abs(current - mu) / (std + EPSILON)
    return int(np.argmax(contribution)) if contribution.size else None


def _upper_triangle(matrix: np.ndarray) -> np.ndarray:
    if matrix.shape[0] < 2:
        return np.array([], dtype=float)
    return matrix[np.triu_indices(matrix.shape[0], k=1)]


def _normalize_ratio(value: float, reference: float) -> float:
    return _clip01(float(value) / (float(reference) + EPSILON))


def _saturating(value: float) -> float:
    return float(1.0 - np.exp(-max(0.0, float(value))))


def _clip01(value: float) -> float:
    return float(np.clip(np.nan_to_num(value, nan=0.0, posinf=1.0, neginf=0.0), 0.0, 1.0))
