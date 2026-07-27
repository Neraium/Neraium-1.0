from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

import numpy as np

from app.engine.sii.common import numeric_values, timestamp_statistics


DEFAULT_CONFIG = {
    "minimum_samples": 64,
    "minimum_regularity": 0.80,
    "maximum_interval_variability": 0.20,
    "minimum_cycles": 3.0,
    "window": "hann",
}


def analyze_spectral_behavior(
    *,
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    reference: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    timestamp = timestamp_statistics(rows, timestamp_column)
    limitations: list[str] = []
    if len(rows) < int(cfg["minimum_samples"]):
        return _limited("insufficient_spectral_samples", timestamp, cfg)
    if not timestamp.get("reliable") or float(timestamp.get("regularity") or 0.0) < float(cfg["minimum_regularity"]):
        return _limited("sampling_regularity_inadequate", timestamp, cfg)
    if float(timestamp.get("interval_variability") or 0.0) > float(cfg["maximum_interval_variability"]):
        return _limited("sampling_interval_variability_exceeds_safeguard", timestamp, cfg)
    interval = float(timestamp.get("median_interval_seconds") or 0.0)
    if interval <= 0.0:
        return _limited("sampling_interval_unavailable", timestamp, cfg)

    results = []
    for column in numeric_columns:
        values = numeric_values(rows, column)
        if len(values) < int(cfg["minimum_samples"]) or len(values) != len(rows):
            limitations.append(f"spectral_signal_excluded:{column}:incomplete_numeric_coverage")
            continue
        vector = np.asarray(values, dtype=float)
        vector = vector - np.mean(vector)
        if float(np.std(vector)) <= 1e-12:
            limitations.append(f"spectral_signal_excluded:{column}:constant_signal")
            continue
        window = np.hanning(len(vector))
        spectrum = np.abs(np.fft.rfft(vector * window)) ** 2
        frequencies = np.fft.rfftfreq(len(vector), d=interval)
        spectrum[0] = 0.0
        index = int(np.argmax(spectrum))
        dominant_frequency = float(frequencies[index])
        if dominant_frequency <= 0.0:
            limitations.append(f"spectral_signal_excluded:{column}:dominant_frequency_unavailable")
            continue
        duration = (len(vector) - 1) * interval
        cycle_support = duration * dominant_frequency
        if cycle_support < float(cfg["minimum_cycles"]):
            limitations.append(f"spectral_signal_excluded:{column}:minimum_cycle_support_not_met")
            continue
        nyquist = 1.0 / (2.0 * interval)
        aliasing_margin = (nyquist - dominant_frequency) / nyquist
        if aliasing_margin < 0.10:
            limitations.append(f"spectral_signal_excluded:{column}:dominant_frequency_near_nyquist")
            continue
        total_power = float(np.sum(spectrum))
        concentration = float(spectrum[index] / total_power) if total_power > 0 else 0.0
        reference_frequency = _reference_frequency(reference, column)
        shift = dominant_frequency - reference_frequency if reference_frequency is not None else None
        results.append(
            {
                "signal_id": column,
                "dominant_frequency_hz": round(dominant_frequency, 9),
                "dominant_period_seconds": round(1.0 / dominant_frequency, 6),
                "power_concentration": round(concentration, 6),
                "cycle_support": round(cycle_support, 6),
                "nyquist_frequency_hz": round(nyquist, 9),
                "aliasing_margin": round(aliasing_margin, 6),
                "frequency_shift_hz": round(shift, 9) if shift is not None else None,
                "oscillation_emergence": bool(reference_frequency is not None and concentration >= 0.25 and dominant_frequency > reference_frequency * 1.2),
                "periodic_instability": None,
                "harmonic_changes": [],
                "windowing_method": "hann",
                "limitations": [] if reference_frequency is not None else ["No persistent spectral reference was available for frequency-shift comparison."],
            }
        )
    status = "complete" if results else "limited"
    return {
        "status": status,
        "reason": None if status == "complete" else "no_signal_met_spectral_assumptions",
        "method": "detrended_hann_window_rfft_v1",
        "sampling": timestamp,
        "dominant_frequencies": results,
        "oscillation_emergence": [item for item in results if item["oscillation_emergence"]],
        "frequency_shifts": [item for item in results if item["frequency_shift_hz"] is not None],
        "periodic_instability": [],
        "harmonic_changes": [],
        "limitations": limitations,
        "processing_trace": {
            "signals_attempted": len(numeric_columns),
            "signals_completed": len(results),
            "windowing_method": "hann",
            "nyquist_safeguard_applied": True,
            "aliasing_safeguard_applied": True,
        },
    }


def _limited(reason: str, timestamp: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "limited",
        "reason": reason,
        "method": "detrended_hann_window_rfft_v1",
        "sampling": deepcopy(timestamp),
        "dominant_frequencies": [],
        "oscillation_emergence": [],
        "frequency_shifts": [],
        "periodic_instability": [],
        "harmonic_changes": [],
        "limitations": [reason],
        "processing_trace": {
            "signals_attempted": 0,
            "signals_completed": 0,
            "minimum_samples": int(config["minimum_samples"]),
            "nyquist_safeguard_applied": True,
            "aliasing_safeguard_applied": True,
        },
    }


def _reference_frequency(reference: dict[str, Any] | None, column: str) -> float | None:
    if not isinstance(reference, dict):
        return None
    for item in reference.get("dominant_frequencies", []):
        if isinstance(item, dict) and item.get("signal_id") == column:
            value = item.get("dominant_frequency_hz")
            return float(value) if isinstance(value, (int, float)) and math.isfinite(float(value)) else None
    return None
