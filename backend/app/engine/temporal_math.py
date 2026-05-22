from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Any

import numpy as np


@dataclass
class TemporalMathConfig:
    baseline_fraction: float = 0.35
    min_baseline_rows: int = 12
    max_rows: int = 5000
    max_lag: int = 8
    evidence_trigger: float = 0.15


def evaluate_temporal_math(
    *,
    columns: list[str],
    rows: list[list[str]],
    numeric_profiles: list[dict[str, Any]],
    timestamp_column: str | None,
    config: TemporalMathConfig | None = None,
) -> dict[str, Any]:
    cfg = config or TemporalMathConfig()
    matrix, used_columns = _build_numeric_matrix(columns=columns, rows=rows, numeric_profiles=numeric_profiles, max_rows=cfg.max_rows)
    if matrix.shape[0] < max(8, cfg.min_baseline_rows + 4) or matrix.shape[1] < 1:
        return _empty_result(reason="insufficient_numeric_history")

    baseline_count = max(cfg.min_baseline_rows, int(matrix.shape[0] * cfg.baseline_fraction))
    baseline_count = min(max(4, baseline_count), matrix.shape[0] - 2)
    baseline = matrix[:baseline_count]
    active = matrix[baseline_count:]
    if active.shape[0] < 2:
        return _empty_result(reason="insufficient_active_window")

    state_drift_series = _state_drift_series(baseline, active)
    variance_growth_series = _variance_growth_series(baseline, active)
    entropy_growth_series = _entropy_growth_series(baseline, active)
    rate_metrics = _rate_of_change(state_drift_series)
    correlation_drift = _correlation_drift(baseline, active)
    relationship_drift = correlation_drift["score"]
    mi_drift = _mutual_information_drift(baseline, active)
    lag_drift = _lag_relationship_drift(baseline, active, max_lag=cfg.max_lag)
    regime = _regime_change(state_drift_series)
    topology = _topology_propagation_score(correlation_drift, lag_drift)

    evidence_vector = {
        "state_drift": float(np.clip(np.nanmean(state_drift_series), 0.0, 1.0)),
        "relationship_drift": relationship_drift,
        "variance_growth": float(np.clip(np.nanmean(variance_growth_series), 0.0, 1.0)),
        "entropy_growth": float(np.clip(np.nanmean(entropy_growth_series), 0.0, 1.0)),
        "acceleration": float(np.clip(abs(rate_metrics["acceleration"]), 0.0, 1.0)),
        "mutual_information_drift": mi_drift["score"],
        "lag_relationship_drift": lag_drift["score"],
        "regime_shift": regime["score"],
        "topology_propagation": topology,
    }
    evidence = _evidence_accumulation(evidence_vector, trigger=cfg.evidence_trigger)
    confidence = _confidence_score(
        evidence,
        sample_count=int(matrix.shape[0]),
        feature_count=int(matrix.shape[1]),
        consistency=_consistency_score(evidence_vector),
    )
    instability_index = _instability_index(evidence_vector, confidence)
    state = _decision_state(
        instability_index["score"],
        active_indicator_count=int(evidence.get("active_indicator_count", 0)),
        persistence_score=float(evidence.get("persistence_score", 0.0)),
    )
    uncertainty = _uncertainty_summary(evidence=evidence, confidence=confidence)
    lead_time = _lead_time_estimate(
        state_drift_series=state_drift_series,
        relationship_series=correlation_drift["series"],
        entropy_series=entropy_growth_series,
        evidence_series=evidence["timeline"],
        baseline_count=baseline_count,
        timestamp_column=timestamp_column,
        rows=rows[-matrix.shape[0]:],
        columns=columns,
    )

    return {
        "engine": {"name": "temporal_math_engine", "version": "v1"},
        "columns_used": used_columns,
        "baseline_rows": baseline_count,
        "active_rows": int(active.shape[0]),
        "state_drift": {"score": evidence_vector["state_drift"], "series": _round_series(state_drift_series)},
        "relationship_drift": {"score": relationship_drift, "series": _round_series(correlation_drift["series"])},
        "rate_of_change": {
            "velocity": round(rate_metrics["velocity"], 6),
            "acceleration": round(rate_metrics["acceleration"], 6),
        },
        "variance_growth": {"score": evidence_vector["variance_growth"], "series": _round_series(variance_growth_series)},
        "entropy_growth": {"score": evidence_vector["entropy_growth"], "series": _round_series(entropy_growth_series)},
        "correlation_drift": correlation_drift,
        "mutual_information_drift": mi_drift,
        "lagged_relationships": lag_drift,
        "regime_changes": regime,
        "topology_propagation": {"score": round(topology, 6)},
        "evidence_accumulation": evidence,
        "confidence_scoring": confidence,
        "uncertainty_summary": uncertainty,
        "instability_index": instability_index,
        "decision_thresholding": {"state": state},
        "lead_time_estimate": lead_time,
    }


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "engine": {"name": "temporal_math_engine", "version": "v1"},
        "status": "limited",
        "reason": reason,
        "instability_index": {
            "score": 0.0,
            "components": {
                "state_drift": 0.0,
                "relationship_drift": 0.0,
                "entropy_growth": 0.0,
                "variance_growth": 0.0,
                "acceleration": 0.0,
                "causal_evidence": 0.0,
                "topology_propagation": 0.0,
            },
            "model": {"name": "temporal_math_engine", "version": "v1"},
        },
        "decision_thresholding": {"state": "Normal"},
        "lead_time_estimate": {"rows_before_event": 0, "timestamp": None, "confidence": "low"},
    }


def _build_numeric_matrix(*, columns: list[str], rows: list[list[str]], numeric_profiles: list[dict[str, Any]], max_rows: int) -> tuple[np.ndarray, list[str]]:
    numeric_columns = [profile["column"] for profile in numeric_profiles if profile.get("column") in columns]
    idx = [columns.index(c) for c in numeric_columns]
    tail_rows = rows[-max_rows:] if len(rows) > max_rows else rows
    vectors: list[list[float]] = []
    for row in tail_rows:
        vals: list[float] = []
        valid = False
        for i in idx:
            raw = row[i].strip() if i < len(row) else ""
            try:
                v = float(raw)
                vals.append(v)
                valid = True
            except ValueError:
                vals.append(float("nan"))
        if valid and vals:
            vectors.append(vals)
    if not vectors:
        return np.empty((0, 0)), []
    matrix = np.asarray(vectors, dtype=float)
    col_means = np.nanmean(matrix, axis=0)
    col_means = np.where(np.isnan(col_means), 0.0, col_means)
    inds = np.where(np.isnan(matrix))
    matrix[inds] = np.take(col_means, inds[1])
    return matrix, numeric_columns


def _state_drift_series(baseline: np.ndarray, active: np.ndarray) -> np.ndarray:
    b_mean = np.mean(baseline, axis=0)
    b_std = np.std(baseline, axis=0)
    b_std = np.where(b_std < 1e-6, 1.0, b_std)
    z = np.abs((active - b_mean) / b_std)
    return np.clip(np.mean(z, axis=1) / 4.0, 0.0, 1.0)


def _variance_growth_series(baseline: np.ndarray, active: np.ndarray) -> np.ndarray:
    b_var = np.var(baseline, axis=0)
    b_var = np.where(b_var < 1e-6, 1e-6, b_var)
    window = max(6, min(24, active.shape[0] // 3))
    out: list[float] = []
    for i in range(active.shape[0]):
        s = max(0, i - window + 1)
        w = active[s : i + 1]
        ratio = np.var(w, axis=0) / b_var
        out.append(float(np.clip(np.mean(np.maximum(ratio - 1.0, 0.0)) / 3.0, 0.0, 1.0)))
    return np.asarray(out, dtype=float)


def _entropy_growth_series(baseline: np.ndarray, active: np.ndarray) -> np.ndarray:
    baseline_entropy = np.mean([_column_entropy(baseline[:, i]) for i in range(baseline.shape[1])])
    baseline_entropy = max(baseline_entropy, 1e-6)
    out = []
    window = max(6, min(24, active.shape[0] // 3))
    for i in range(active.shape[0]):
        s = max(0, i - window + 1)
        w = active[s : i + 1]
        e = np.mean([_column_entropy(w[:, j]) for j in range(w.shape[1])])
        out.append(float(np.clip(max(e - baseline_entropy, 0.0) / (baseline_entropy + 1.0), 0.0, 1.0)))
    return np.asarray(out, dtype=float)


def _column_entropy(series: np.ndarray, bins: int = 12) -> float:
    if series.size < 3:
        return 0.0
    hist, _ = np.histogram(series, bins=bins, density=False)
    p = hist.astype(float)
    s = np.sum(p)
    if s <= 0:
        return 0.0
    p = p / s
    return -sum(float(pi * log(pi + 1e-12, 2)) for pi in p if pi > 0)


def _correlation_drift(baseline: np.ndarray, active: np.ndarray) -> dict[str, Any]:
    if baseline.shape[1] < 2:
        return {"score": 0.0, "series": [], "changed_pairs": []}
    b_corr = np.corrcoef(baseline, rowvar=False)
    window = max(8, min(32, active.shape[0] // 2))
    series = []
    for i in range(active.shape[0]):
        s = max(0, i - window + 1)
        w = active[s : i + 1]
        if w.shape[0] < 3:
            series.append(0.0)
            continue
        w_corr = np.corrcoef(w, rowvar=False)
        delta = np.abs(w_corr - b_corr)
        series.append(float(np.clip(np.nanmean(delta) / 1.5, 0.0, 1.0)))
    return {"score": round(float(np.mean(series)), 6), "series": _round_series(np.asarray(series)), "changed_pairs": []}


def _mutual_information_drift(baseline: np.ndarray, active: np.ndarray) -> dict[str, Any]:
    if baseline.shape[1] < 2:
        return {"score": 0.0}
    pair_count = min(6, baseline.shape[1] - 1)
    deltas = []
    for i in range(pair_count):
        j = i + 1
        b = _mutual_information(baseline[:, i], baseline[:, j])
        a = _mutual_information(active[:, i], active[:, j])
        denom = max(abs(b), 1e-6)
        deltas.append(abs(a - b) / (denom + 1.0))
    return {"score": round(float(np.clip(np.mean(deltas), 0.0, 1.0)), 6)}


def _mutual_information(x: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    c_xy, _, _ = np.histogram2d(x, y, bins=bins)
    p_xy = c_xy / np.sum(c_xy)
    p_x = np.sum(p_xy, axis=1)
    p_y = np.sum(p_xy, axis=0)
    mi = 0.0
    for i in range(p_xy.shape[0]):
        for j in range(p_xy.shape[1]):
            if p_xy[i, j] > 0:
                mi += p_xy[i, j] * log(p_xy[i, j] / (p_x[i] * p_y[j] + 1e-12) + 1e-12, 2)
    return float(max(mi, 0.0))


def _lag_relationship_drift(baseline: np.ndarray, active: np.ndarray, *, max_lag: int) -> dict[str, Any]:
    if baseline.shape[1] < 2:
        return {"score": 0.0, "dominant_lag_shift": 0}
    b_lag = _best_lag(baseline[:, 0], baseline[:, 1], max_lag=max_lag)
    a_lag = _best_lag(active[:, 0], active[:, 1], max_lag=max_lag)
    shift = abs(a_lag - b_lag)
    return {"score": round(float(np.clip(shift / max(max_lag, 1), 0.0, 1.0)), 6), "dominant_lag_shift": int(a_lag - b_lag)}


def _best_lag(x: np.ndarray, y: np.ndarray, *, max_lag: int) -> int:
    best_lag = 0
    best_corr = -1.0
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            xs, ys = x[:lag], y[-lag:]
        elif lag > 0:
            xs, ys = x[lag:], y[:-lag]
        else:
            xs, ys = x, y
        if xs.size < 4 or ys.size < 4:
            continue
        corr = np.corrcoef(xs, ys)[0, 1]
        corr = abs(float(np.nan_to_num(corr, nan=0.0)))
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    return best_lag


def _regime_change(state_drift_series: np.ndarray) -> dict[str, Any]:
    if state_drift_series.size < 10:
        return {"score": 0.0, "change_points": []}
    w = max(4, state_drift_series.size // 10)
    points = []
    for i in range(w, state_drift_series.size - w):
        left = float(np.mean(state_drift_series[i - w : i]))
        right = float(np.mean(state_drift_series[i : i + w]))
        if right - left > 0.12:
            points.append(i)
    score = float(np.clip(min(len(points), 3) / 3, 0.0, 1.0))
    return {"score": round(score, 6), "change_points": points[:5]}


def _topology_propagation_score(correlation_drift: dict[str, Any], lag_drift: dict[str, Any]) -> float:
    corr = float(correlation_drift.get("score", 0.0))
    lag = float(lag_drift.get("score", 0.0))
    return float(np.clip((corr * 0.6) + (lag * 0.4), 0.0, 1.0))


def _evidence_accumulation(evidence_vector: dict[str, float], *, trigger: float) -> dict[str, Any]:
    keys = [k for k in evidence_vector if k not in {"topology_propagation"}]
    timeline = [float(evidence_vector[k]) for k in keys]
    active = [k for k in keys if evidence_vector[k] >= trigger]
    # Persistence guardrail: require sustained indicator pressure, not one-off peaks.
    persistence_hits = [k for k in keys if evidence_vector[k] >= max(trigger, 0.22)]
    persistence_score = float(np.clip(len(persistence_hits) / max(len(keys), 1), 0.0, 1.0))
    score = float(np.clip((len(active) / max(len(keys), 1)) * 0.7 + (np.mean(timeline) if timeline else 0.0) * 0.3, 0.0, 1.0))
    return {
        "score": round(score, 6),
        "active_indicators": active,
        "active_indicator_count": len(active),
        "persistence_score": round(persistence_score, 6),
        "timeline": _round_series(np.asarray(timeline)),
    }


def _confidence_score(evidence: dict[str, Any], *, sample_count: int, feature_count: int, consistency: float) -> dict[str, Any]:
    sufficiency = float(np.clip((sample_count / 240.0) * 0.7 + (feature_count / 24.0) * 0.3, 0.0, 1.0))
    score = float(
        np.clip(
            0.15
            + (float(evidence.get("score", 0.0)) * 0.45)
            + (sufficiency * 0.25)
            + (float(np.clip(consistency, 0.0, 1.0)) * 0.15),
            0.0,
            1.0,
        )
    )
    band = "low"
    if score >= 0.8:
        band = "high"
    elif score >= 0.6:
        band = "medium"
    return {
        "score": round(score, 6),
        "band": band,
        "data_sufficiency": round(sufficiency, 6),
        "consistency": round(float(np.clip(consistency, 0.0, 1.0)), 6),
    }


def _instability_index(evidence_vector: dict[str, float], confidence: dict[str, Any]) -> dict[str, Any]:
    components = {
        "state_drift": float(np.clip(evidence_vector.get("state_drift", 0.0), 0.0, 1.0)),
        "relationship_drift": float(np.clip(evidence_vector.get("relationship_drift", 0.0), 0.0, 1.0)),
        "entropy_growth": float(np.clip(evidence_vector.get("entropy_growth", 0.0), 0.0, 1.0)),
        "variance_growth": float(np.clip(evidence_vector.get("variance_growth", 0.0), 0.0, 1.0)),
        "acceleration": float(np.clip(evidence_vector.get("acceleration", 0.0), 0.0, 1.0)),
        "causal_evidence": float(np.clip(confidence.get("score", 0.0), 0.0, 1.0)),
        "topology_propagation": float(np.clip(evidence_vector.get("topology_propagation", 0.0), 0.0, 1.0)),
    }
    score = (
        components["state_drift"] * 0.23
        + components["relationship_drift"] * 0.17
        + components["entropy_growth"] * 0.12
        + components["variance_growth"] * 0.14
        + components["acceleration"] * 0.11
        + components["causal_evidence"] * 0.13
        + components["topology_propagation"] * 0.10
    )
    return {"score": round(float(np.clip(score, 0.0, 1.0)), 6), "components": {k: round(v, 6) for k, v in components.items()}, "model": {"name": "temporal_math_engine", "version": "v1"}}


def _decision_state(score: float, *, active_indicator_count: int, persistence_score: float) -> str:
    # Guardrail 1: minimum persistence before escalation.
    if persistence_score < 0.28:
        return "Watch" if score >= 0.32 else "Normal"
    # Guardrail 2: multi-indicator agreement for higher escalation.
    if active_indicator_count < 2:
        return "Watch" if score >= 0.32 else "Normal"
    if score >= 0.85 and active_indicator_count >= 4 and persistence_score >= 0.55:
        return "Critical"
    if score >= 0.70 and active_indicator_count >= 3 and persistence_score >= 0.42:
        return "Act"
    if score >= 0.52 and active_indicator_count >= 2 and persistence_score >= 0.32:
        return "Investigate"
    if score >= 0.32:
        return "Watch"
    return "Normal"


def _uncertainty_summary(*, evidence: dict[str, Any], confidence: dict[str, Any]) -> dict[str, Any]:
    active_count = int(evidence.get("active_indicator_count", 0))
    confidence_score = float(confidence.get("score", 0.0))
    persistence_score = float(evidence.get("persistence_score", 0.0))
    consistency = float(confidence.get("consistency", 0.0))
    weak = confidence_score < 0.5 or persistence_score < 0.3
    conflicting = active_count >= 3 and (confidence_score < 0.6 or consistency < 0.45)
    return {
        "explicit_uncertainty": conflicting or weak,
        "weak_signals": weak,
        "conflicting_signals": conflicting,
        "summary": (
            "Signals are mixed; monitor accumulation before escalation."
            if conflicting
            else ("Evidence is currently limited." if weak else "Uncertainty is bounded by current evidence.")
        ),
    }


def _consistency_score(evidence_vector: dict[str, float]) -> float:
    values = np.asarray(list(evidence_vector.values()), dtype=float)
    if values.size <= 1:
        return 0.5
    mean_val = float(np.mean(values))
    if mean_val <= 1e-6:
        return 0.5
    dispersion = float(np.std(values) / (mean_val + 1e-6))
    return float(np.clip(1.0 - (dispersion / 2.0), 0.0, 1.0))


def _lead_time_estimate(
    *,
    state_drift_series: np.ndarray,
    relationship_series: list[float],
    entropy_series: np.ndarray,
    evidence_series: list[float],
    baseline_count: int,
    timestamp_column: str | None,
    rows: list[list[str]],
    columns: list[str],
) -> dict[str, Any]:
    rel = np.asarray(relationship_series, dtype=float) if relationship_series else np.zeros_like(state_drift_series)
    ent = entropy_series if entropy_series.size else np.zeros_like(state_drift_series)
    comb = (state_drift_series * 0.45) + (rel[: state_drift_series.size] * 0.3) + (ent[: state_drift_series.size] * 0.25)
    idx = 0
    for i, v in enumerate(comb):
        if v >= 0.22:
            idx = i
            break
    rows_before = int(max(0, (state_drift_series.size - idx)))
    ts = None
    if timestamp_column and timestamp_column in columns:
        ts_idx = columns.index(timestamp_column)
        row_idx = min(len(rows) - 1, baseline_count + idx)
        if row_idx >= 0 and row_idx < len(rows) and ts_idx < len(rows[row_idx]):
            ts = rows[row_idx][ts_idx]
    conf = "medium" if np.mean(evidence_series) >= 0.45 else "low"
    if np.mean(evidence_series) >= 0.7:
        conf = "high"
    return {"rows_before_event": rows_before, "timestamp": ts, "confidence": conf}


def _rate_of_change(series: np.ndarray) -> dict[str, float]:
    if series.size < 3:
        return {"velocity": 0.0, "acceleration": 0.0}
    vel = float(series[-1] - series[-2])
    acc = float((series[-1] - series[-2]) - (series[-2] - series[-3]))
    return {"velocity": vel, "acceleration": acc}


def _round_series(series: np.ndarray | list[float]) -> list[float]:
    if isinstance(series, np.ndarray):
        values = series.tolist()
    else:
        values = list(series)
    return [round(float(x), 6) for x in values]
