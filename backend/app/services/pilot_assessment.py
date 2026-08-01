from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


MIN_MODE_SAMPLES = 18


def _fit_relationship(
    rows: pd.DataFrame,
    left: str,
    right: str,
) -> dict[str, float] | None:
    paired = rows[[left, right]].dropna()
    if len(paired) < MIN_MODE_SAMPLES:
        return None
    x = paired[left].to_numpy(dtype=float)
    y = paired[right].to_numpy(dtype=float)
    if float(np.std(x)) <= 1e-12 or float(np.std(y)) <= 1e-12:
        return None
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    residual = y - predicted
    median = float(np.median(residual))
    mad = float(np.median(np.abs(residual - median)))
    scale = max(1.4826 * mad, float(np.std(y)) * 0.05, 1e-9)
    return {
        "correlation": float(np.corrcoef(x, y)[0, 1]),
        "slope": float(slope),
        "intercept": float(intercept),
        "residual_scale": scale,
        "sample_count": len(paired),
    }


def _persistence_windows(
    rows: pd.DataFrame,
    left: str,
    right: str,
    baseline_fit: dict[str, float],
) -> dict[str, Any]:
    paired = (
        rows[["__timestamp", "__source_row", "__mode", left, right]]
        .dropna()
        .sort_values("__timestamp")
    )
    if len(paired) < MIN_MODE_SAMPLES:
        return {
            "persistent": False,
            "windows": [],
            "first_surfaced_at": None,
            "support_fraction": 0,
        }
    window_size = max(8, min(32, len(paired) // 3))
    windows = []
    for start in range(0, len(paired) - window_size + 1, window_size):
        window = paired.iloc[start : start + window_size]
        predicted = (
            baseline_fit["slope"] * window[left].to_numpy(dtype=float)
            + baseline_fit["intercept"]
        )
        score = float(
            np.median(np.abs(window[right].to_numpy(dtype=float) - predicted))
            / baseline_fit["residual_scale"]
        )
        windows.append(
            {
                "start": window["__timestamp"].iloc[0].isoformat(),
                "end": window["__timestamp"].iloc[-1].isoformat(),
                "records": len(window),
                "deviation_score": round(score, 4),
                "supports_change": score >= 3.0,
            }
        )
    support_indexes = [
        index for index, item in enumerate(windows) if item["supports_change"]
    ]
    if not support_indexes:
        return {
            "persistent": False,
            "windows": windows,
            "first_surfaced_at": None,
            "support_fraction": 0,
        }
    first = support_indexes[0]
    later = windows[first:]
    fraction = sum(item["supports_change"] for item in later) / max(1, len(later))
    return {
        "persistent": len(support_indexes) >= 2 and fraction >= 0.6,
        "windows": windows,
        "first_surfaced_at": windows[first]["start"],
        "support_fraction": round(fraction, 4),
    }


def evaluate_relationship_against_baseline(
    rows: pd.DataFrame,
    left: str,
    right: str,
    baseline_fit: dict[str, float],
) -> dict[str, Any]:
    """Apply the production relationship-change and persistence rules."""

    current_fit = _fit_relationship(rows, left, right)
    if current_fit is None:
        return {
            "evaluated": False,
            "changed": False,
            "current_fit": None,
            "correlation_delta": None,
            "slope_change": None,
            "persistence": {
                "persistent": False,
                "windows": [],
                "first_surfaced_at": None,
                "support_fraction": 0,
            },
        }
    correlation_delta = current_fit["correlation"] - baseline_fit["correlation"]
    slope_change = (
        abs(
            (current_fit["slope"] - baseline_fit["slope"])
            / baseline_fit["slope"]
        )
        if abs(baseline_fit["slope"]) > 1e-9
        else math.inf
    )
    persistence = _persistence_windows(rows, left, right, baseline_fit)
    return {
        "evaluated": True,
        "changed": bool(abs(correlation_delta) >= 0.25 or slope_change >= 0.3),
        "current_fit": current_fit,
        "correlation_delta": correlation_delta,
        "slope_change": slope_change,
        "persistence": persistence,
    }
