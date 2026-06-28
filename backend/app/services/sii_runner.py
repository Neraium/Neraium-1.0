from __future__ import annotations

import inspect
import json
import os
import time
from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.data_quality import parse_numeric_value
from app.services.runtime_db import read_latest_payload, upsert_latest_payload
from app.services.telemetry_normalization import SENTINEL

import numpy as np


RUNNER_MODULE = "app.services.sii_runner.BackendSiiRunner"
RUNNER_CALLABLE = "app.services.sii_runner.BackendSiiRunner.ingest"
CORE_ENGINE = "app.engine.analysis.run_engine_analysis"
VALIDATION_RUNNER = None
STATE_PATH = get_settings().runtime_dir / "latest_sii_state.json"
STATE_REQUIRED_FIELDS = {
    "facility_state",
    "rooms",
    "priority_room",
    "neraium_score",
    "primary_driver",
    "supporting_evidence",
    "structural_explanation",
    "confidence_basis",
    "last_processed_at",
    "source",
}
MIN_COVARIANCE_BASELINE_ROWS = 8
COVARIANCE_REGULARIZATION_FRACTION = 0.05
COVARIANCE_REGULARIZATION_FLOOR = 1e-3

_IMPORT_ERROR: str | None = None
_SII_ENGINE_ADAPTER: Any = None
MAX_RUNNER_VECTOR_ROWS = max(0, int(os.getenv("NERAIUM_SII_MAX_VECTOR_ROWS", "4096") or "0"))
RECENT_VECTOR_TAIL = max(100, int(os.getenv("NERAIUM_SII_RECENT_VECTOR_TAIL", "512") or "512"))

def configure_runtime_dir(runtime_dir: Path) -> None:
    global STATE_PATH
    STATE_PATH = runtime_dir / "latest_sii_state.json"


class BackendSiiRunner:
    """Backend-native telemetry runner used by production uploads and readiness checks."""

    def __init__(self, *, baseline_window: int = 12, recent_window: int = 12) -> None:
        self.baseline_window = max(2, baseline_window)
        self.recent_window = max(2, recent_window)
        self._history: deque[np.ndarray] = deque(maxlen=self.baseline_window + self.recent_window)
        self._history_count = 0
        self._instability_history: deque[float] = deque(maxlen=20)
        self._velocity_history: deque[float] = deque(maxlen=20)
        self._distance_history: deque[float] = deque(maxlen=20)
        self._distance_velocity_history: deque[float] = deque(maxlen=20)
        self._regime_history: deque[str] = deque(maxlen=20)

    def ingest(
        self,
        *,
        sensor_vector: np.ndarray,
        timestamp: float,
        asset_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        vector = np.asarray(sensor_vector, dtype=float)
        self._history.append(vector)
        self._history_count += 1

        baseline_vectors, recent_vectors = self._windowed_history()
        baseline_mean = _nanmean_columns(baseline_vectors)
        recent_mean = _nanmean_columns(recent_vectors)
        safe_baseline = np.where(np.abs(baseline_mean) < 1e-6, 1.0, np.abs(baseline_mean))
        normalized_delta = np.abs(recent_mean - baseline_mean) / safe_baseline
        fallback_structural_drift = float(np.clip(np.nan_to_num(np.nanmean(normalized_delta), nan=0.0), 0.0, 1.5))

        if len(self._history) >= 2:
            last_step = np.abs(np.nan_to_num(self._history[-1], nan=0.0) - np.nan_to_num(self._history[-2], nan=0.0)) / safe_baseline
            fallback_transition_pressure = float(np.clip(np.nan_to_num(np.nanmean(last_step), nan=0.0), 0.0, 1.5))
        else:
            fallback_transition_pressure = 0.0

        variability = float(np.nan_to_num(np.nanstd(recent_vectors), nan=0.0)) if recent_vectors.size else 0.0
        fallback_variability_pressure = float(np.clip(variability / max(float(np.nanmean(safe_baseline)), 1.0), 0.0, 1.0))
        fallback_score = float(
            np.clip(
                fallback_structural_drift * 0.55
                + fallback_transition_pressure * 0.3
                + fallback_variability_pressure * 0.15,
                0.0,
                1.0,
            )
        )

        covariance_valid = False
        structural_drift = fallback_structural_drift
        transition_pressure = fallback_transition_pressure
        structural_drift_score = float(np.clip(fallback_structural_drift, 0.0, 1.0))
        mahalanobis_distance = fallback_score
        drift_velocity = 0.0
        drift_acceleration = 0.0
        covariance_shift = 0.0
        trajectory_curvature = 0.0
        persistence_condition = False
        accumulation_condition = False
        accumulation = 0.0
        dynamic_threshold = 0.0

        current_vector = np.nan_to_num(vector, nan=0.0)
        baseline_matrix = np.nan_to_num(np.asarray(baseline_vectors, dtype=float), nan=0.0)
        recent_matrix = np.nan_to_num(np.asarray(recent_vectors, dtype=float), nan=0.0)
        previous_distance = self._distance_history[-1] if self._distance_history else 0.0
        previous_velocity = self._distance_velocity_history[-1] if self._distance_velocity_history else 0.0

        baseline_completeness = _matrix_completeness(baseline_vectors)
        recent_completeness = _matrix_completeness(recent_vectors)
        enough_baseline_for_covariance = (
            len(baseline_matrix) >= MIN_COVARIANCE_BASELINE_ROWS
            and baseline_completeness >= 0.65
            and current_vector.shape[0] > 0
        )

        try:
            if not enough_baseline_for_covariance:
                raise ValueError("insufficient baseline for covariance scoring")
            baseline_covariance = _regularized_covariance_matrix(baseline_matrix)
            baseline_covariance = np.nan_to_num(baseline_covariance, nan=0.0)
            expected_shape = (current_vector.shape[0], current_vector.shape[0])
            if baseline_covariance.shape != expected_shape:
                baseline_covariance = np.eye(current_vector.shape[0], dtype=float)
            covariance_inverse = np.linalg.pinv(baseline_covariance)
            centered_vector = np.nan_to_num(current_vector - baseline_mean, nan=0.0)
            mahalanobis_sq = float(centered_vector.T @ covariance_inverse @ centered_vector)
            mahalanobis_distance = float(np.sqrt(max(mahalanobis_sq, 0.0)))
            covariance_valid = bool(np.isfinite(mahalanobis_distance))
            if not covariance_valid:
                mahalanobis_distance = fallback_score
        except Exception:
            covariance_valid = False
            mahalanobis_distance = fallback_score

        if covariance_valid:
            baseline_distances = _baseline_mahalanobis_distances(baseline_matrix, baseline_mean, covariance_inverse)
            baseline_distance_center = float(np.mean(baseline_distances)) if baseline_distances else 0.0
            baseline_distance_spread = float(np.std(baseline_distances)) if baseline_distances else 0.0
            baseline_distance_limit = max(baseline_distance_center + baseline_distance_spread * 3.0, 1.0)
            excess_distance = max(0.0, mahalanobis_distance - baseline_distance_limit)
            structural_drift_score = float(np.clip(excess_distance / baseline_distance_limit, 0.0, 1.0))
            drift_velocity = float(mahalanobis_distance - previous_distance)
            drift_acceleration = float(drift_velocity - previous_velocity)
            recent_covariance = _regularized_covariance_matrix(recent_matrix)
            recent_covariance = np.nan_to_num(recent_covariance, nan=0.0)
            if recent_covariance.shape == baseline_covariance.shape:
                baseline_norm = float(np.linalg.norm(baseline_covariance, ord="fro"))
                covariance_shift = float(
                    np.linalg.norm(recent_covariance - baseline_covariance, ord="fro") / max(baseline_norm, 1e-6)
                )
            else:
                covariance_shift = 0.0
            trajectory_curvature = float(np.clip(abs(drift_acceleration) / max(abs(drift_velocity), 1e-6), 0.0, 1.0))
            if fallback_structural_drift < 0.08 and covariance_shift < 0.8:
                structural_drift_score = 0.0

            distance_history = list(self._distance_history) + [mahalanobis_distance]
            dynamic_threshold = float(np.mean(distance_history) + np.std(distance_history)) if distance_history else 0.0
            distance_window = distance_history[-min(self.recent_window, len(distance_history)) :]
            if len(distance_window) >= 3:
                persistence_condition = bool(sum(value > dynamic_threshold for value in distance_window) >= 3)
            accumulation = float(np.sum(distance_window)) if distance_window else 0.0
            accumulation_condition = bool(len(distance_window) >= 3 and accumulation >= dynamic_threshold * 3.0)
            corroborated_drift = persistence_condition and accumulation_condition and structural_drift_score >= 0.08
            motion_gate = max(structural_drift_score, min(covariance_shift, 1.0) * 0.25 if corroborated_drift else 0.0)

            technical_score = float(
                np.clip(
                    structural_drift_score * 0.45
                    + min(abs(drift_velocity), 1.0) * motion_gate * 0.20
                    + min(abs(drift_acceleration), 1.0) * motion_gate * 0.15
                    + min(covariance_shift, 1.0) * (1.0 if corroborated_drift else 0.25) * 0.15
                    + min(trajectory_curvature, 1.0) * motion_gate * 0.05,
                    0.0,
                    1.0,
                )
            )
            if not (persistence_condition and accumulation_condition):
                technical_score = min(technical_score, 0.19)
            fallback_adjusted_score = fallback_score
            if not corroborated_drift and fallback_structural_drift < 0.08:
                fallback_adjusted_score = min(fallback_adjusted_score, 0.20)
            instability_score = float(max(fallback_adjusted_score * 0.35, technical_score))
            structural_drift = structural_drift_score
            transition_pressure = float(np.clip((abs(drift_velocity) + abs(drift_acceleration)) * motion_gate, 0.0, 1.0))
            if not corroborated_drift:
                transition_pressure = min(transition_pressure, 0.27)
        else:
            instability_score = fallback_score

        instability_components = {
            "drift": round(float(np.clip(structural_drift, 0.0, 1.0)), 6),
            "relationship_degradation": round(float(np.clip(transition_pressure, 0.0, 1.0)), 6),
            "entropy_growth": round(float(np.clip(fallback_variability_pressure, 0.0, 1.0)), 6),
            "fallback_score": round(float(np.clip(fallback_score, 0.0, 1.0)), 6),
            "structural_drift_score": round(float(np.clip(structural_drift_score, 0.0, 1.0)), 6),
            "mahalanobis_distance": round(float(max(mahalanobis_distance, 0.0)), 6),
            "drift_velocity": round(float(drift_velocity), 6),
            "drift_acceleration": round(float(drift_acceleration), 6),
            "covariance_shift": round(float(max(covariance_shift, 0.0)), 6),
            "trajectory_curvature": round(float(np.clip(trajectory_curvature, 0.0, 1.0)), 6),
            "persistence_condition": persistence_condition,
            "accumulation_condition": accumulation_condition,
            "accumulation": round(float(max(accumulation, 0.0)), 6),
            "dynamic_threshold": round(float(max(dynamic_threshold, 0.0)), 6),
            "fallback_normalized_drift": round(float(np.clip(fallback_structural_drift, 0.0, 1.0)), 6),
            "fallback_transition_pressure": round(float(np.clip(fallback_transition_pressure, 0.0, 1.0)), 6),
            "fallback_variability_pressure": round(float(np.clip(fallback_variability_pressure, 0.0, 1.0)), 6),
            "baseline_completeness": round(float(np.clip(baseline_completeness, 0.0, 1.0)), 6),
            "recent_completeness": round(float(np.clip(recent_completeness, 0.0, 1.0)), 6),
        }
        velocity = instability_score - (self._instability_history[-1] if self._instability_history else instability_score)

        regime, urgency = classify_state(self._history_count, instability_score, transition_pressure)
        confidence = confidence_from_history(self._history_count, vector, recent_vectors=recent_vectors)

        self._instability_history.append(instability_score)
        self._velocity_history.append(float(velocity))
        self._distance_history.append(float(max(mahalanobis_distance, 0.0)))
        self._distance_velocity_history.append(float(drift_velocity))
        self._regime_history.append(regime)

        return {
            "asset_id": asset_id,
            "run_id": run_id,
            "timestamp": timestamp,
            "regime": regime,
            "urgency": urgency,
            "instability_score": round(instability_score, 6),
            "instability_components": instability_components,
            "structural_drift": round(structural_drift, 6),
            "transition_pressure": round(transition_pressure, 6),
            "confidence": round(confidence, 6),
            "instability_history": [round(value, 6) for value in self._instability_history],
            "velocity_history": [round(value, 6) for value in self._velocity_history],
            "regime_history": list(self._regime_history),
        }

    def _windowed_history(self) -> tuple[np.ndarray, np.ndarray]:
        history = list(self._history)
        if len(history) == 1:
            only = np.vstack(history)
            return only, only

        recent_count = min(self.recent_window, len(history))
        recent_vectors = np.vstack(history[-recent_count:])
        baseline_source = history[:-recent_count]
        if not baseline_source:
            split_index = max(1, len(history) // 2)
            baseline_source = history[:split_index]
        baseline_vectors = np.vstack(baseline_source[-self.baseline_window :])
        return baseline_vectors, recent_vectors


def _covariance_matrix(matrix: np.ndarray) -> np.ndarray:
    with np.errstate(all="ignore"):
        covariance = np.cov(matrix, rowvar=False, bias=True)
    covariance = np.atleast_2d(covariance)
    return np.nan_to_num(covariance, nan=0.0)


def _regularized_covariance_matrix(matrix: np.ndarray) -> np.ndarray:
    covariance = _covariance_matrix(matrix)
    dimension = covariance.shape[0]
    diagonal = np.diag(covariance) if covariance.ndim == 2 and covariance.shape[0] == covariance.shape[1] else np.array([])
    positive_diagonal = diagonal[diagonal > 0]
    variance_scale = float(np.mean(positive_diagonal)) if positive_diagonal.size else 1.0
    regularization = max(variance_scale * COVARIANCE_REGULARIZATION_FRACTION, COVARIANCE_REGULARIZATION_FLOOR)
    return covariance + (np.eye(dimension, dtype=float) * regularization)


def _baseline_mahalanobis_distances(
    baseline_matrix: np.ndarray,
    baseline_mean: np.ndarray,
    covariance_inverse: np.ndarray,
) -> list[float]:
    distances: list[float] = []
    for baseline_vector in baseline_matrix:
        centered = np.nan_to_num(baseline_vector - baseline_mean, nan=0.0)
        distance_sq = float(centered.T @ covariance_inverse @ centered)
        if np.isfinite(distance_sq):
            distances.append(float(np.sqrt(max(distance_sq, 0.0))))
    return distances


def _nanmean_columns(matrix: np.ndarray) -> np.ndarray:
    values = np.asarray(matrix, dtype=float)
    if values.size == 0:
        return np.asarray([], dtype=float)
    valid_counts = np.sum(~np.isnan(values), axis=0)
    sums = np.nansum(values, axis=0)
    return np.divide(sums, valid_counts, out=np.zeros(values.shape[1], dtype=float), where=valid_counts > 0)


def _matrix_completeness(matrix: np.ndarray) -> float:
    values = np.asarray(matrix, dtype=float)
    if values.size == 0:
        return 0.0
    return float(np.mean(~np.isnan(values)))


def _try_import_runner() -> None:
    global _IMPORT_ERROR, _SII_ENGINE_ADAPTER
    if _SII_ENGINE_ADAPTER is not None or _IMPORT_ERROR is not None:
        return

    _SII_ENGINE_ADAPTER = BackendSiiRunner
    _IMPORT_ERROR = None


def runner_available() -> bool:
    _try_import_runner()
    return _SII_ENGINE_ADAPTER is not None


def runner_import_error() -> str | None:
    _try_import_runner()
    return _IMPORT_ERROR


def build_runner_status() -> dict[str, Any]:
    state = read_latest_sii_state()
    identity = runner_identity()
    last_processed_at = state.get("last_processed_at") if state else None
    parsed_last_processed_at = parse_state_timestamp(last_processed_at)
    state_age_seconds = None
    if parsed_last_processed_at is not None:
        state_age_seconds = max(0, int((datetime.now(UTC) - parsed_last_processed_at).total_seconds()))
    return {
        "runner_available": runner_available(),
        "runner_module": identity["runner_module"],
        "runner_file": identity["runner_file"],
        "core_engine": identity["core_engine"],
        "core_engine_file": identity["core_engine_file"],
        "validation_runner": identity["validation_runner"],
        "validation_runner_file": identity["validation_runner_file"],
        "state_available": state is not None,
        "last_processed_at": last_processed_at,
        "state_timestamp_valid": last_processed_at is None or parsed_last_processed_at is not None,
        "state_age_seconds": state_age_seconds,
        "source": state.get("source") if state else "none",
        "same_engine_family_as_validation": False,
        "same_exact_fd004_validation_runner": False,
        "note": (
            "Production uploads use the backend-native SII runner. "
            "Legacy FD004 validation code has been removed from the production tree."
        ),
        "import_error": runner_import_error(),
    }


def runner_identity() -> dict[str, str | None]:
    _try_import_runner()
    core_file = validation_file = runner_file = None
    if _SII_ENGINE_ADAPTER is not None:
        runner_file = inspect.getsourcefile(_SII_ENGINE_ADAPTER)
        try:
            core_file = inspect.getsourcefile(BackendSiiRunner)
        except Exception:
            core_file = None
    return {
        "runner_module": RUNNER_MODULE,
        "runner_callable": RUNNER_CALLABLE,
        "runner_file": runner_file,
        "core_engine": CORE_ENGINE,
        "core_engine_file": core_file,
        "validation_runner": VALIDATION_RUNNER,
        "validation_runner_file": validation_file,
    }


def run_sii_runner(
    *,
    columns: list[str],
    rows: list[list[str]],
    numeric_profiles: list[dict[str, Any]],
    timestamp_column: str | None,
    primary_room: str,
    driver_attribution: dict[str, Any],
    engine_result: dict[str, Any],
    processing_trace: dict[str, Any],
) -> dict[str, Any]:
    _try_import_runner()
    base_result: dict[str, Any] = {
        "runner_used": False,
        "runner_module": RUNNER_MODULE,
        "core_engine": CORE_ENGINE,
        "rows_processed": 0,
        "rows_received": 0,
        "rows_excluded": 0,
        "columns_used": [],
        "sensor_vector_count": 0,
        "output_summary": {},
        "latest_state": None,
        "evidence": [],
        "errors": [],
    }
    if _SII_ENGINE_ADAPTER is None:
        base_result["errors"].append(runner_import_error() or "SII runner is not importable.")
        return base_result

    vector_rows = build_sensor_vectors(columns, rows, numeric_profiles)
    source_vector_count = len(vector_rows["vectors"])
    vector_rows = limit_runner_vectors(vector_rows)
    retained_vector_count = len(vector_rows["vectors"])
    base_result["columns_used"] = vector_rows["columns_used"]
    base_result["sensor_vector_count"] = retained_vector_count
    base_result["sensor_vector_source_count"] = source_vector_count
    base_result["sampling_applied"] = bool(vector_rows.get("sampling_applied"))
    base_result["rows_received"] = len(rows)
    base_result["rows_excluded"] = max(0, len(rows) - source_vector_count)
    if not vector_rows["vectors"]:
        base_result["errors"].append("No complete numeric sensor vectors were available for SII runner ingestion.")
        return base_result

    baseline_window = min(50, max(2, min(48, retained_vector_count // 2 or 2)))
    adapter = _SII_ENGINE_ADAPTER(baseline_window=baseline_window, recent_window=baseline_window)
    states: list[dict[str, Any]] = []
    run_id = f"upload-{datetime.now(UTC).timestamp()}"

    try:
        for index, vector in enumerate(vector_rows["vectors"]):
            timestamp = parse_timestamp(columns, rows[vector_rows["row_indexes"][index]], timestamp_column, index)
            state = adapter.ingest(
                sensor_vector=np.asarray(vector, dtype=float),
                timestamp=timestamp,
                asset_id=primary_room or "uploaded_facility",
                run_id=run_id,
            )
            states.append(to_plain_dict(state))
    except Exception as exc:
        base_result["errors"].append(f"{type(exc).__name__}: {exc}")
        return base_result

    latest_state = states[-1]
    projected_hours = project_time_to_failure_hours_from_state(latest_state)
    instability_index = build_instability_index(latest_state)
    latest_state = {
        **latest_state,
        "instability_index": instability_index,
        "review_window_hours": projected_hours,
        "review_window": format_review_window_hours(projected_hours),
        "projected_time_to_failure_hours": projected_hours,
        "projected_time_to_failure": format_review_window_hours(projected_hours),
    }
    evidence = build_runner_evidence(latest_state, vector_rows["columns_used"], driver_attribution, engine_result)
    output_summary = summarize_runner_outputs(states)
    processing_trace = {
        **processing_trace,
        "sii_runner_ran": True,
        "sii_runner_module": RUNNER_MODULE,
        "sii_core_engine": CORE_ENGINE,
        "sensor_vector_count": len(states),
        "sensor_vector_source_count": source_vector_count,
        "sii_sampling_applied": bool(vector_rows.get("sampling_applied")),
        "sii_vector_rows_processed": len(states),
        "sii_vector_rows_source_count": source_vector_count,
        "sii_rows_received": len(rows),
        "sii_rows_excluded": max(0, len(rows) - source_vector_count),
        "sii_columns_used": list(vector_rows["columns_used"]),
    }

    base_result.update(
        {
            "runner_used": True,
            "rows_processed": len(states),
            "rows_received": len(rows),
            "rows_excluded": max(0, len(rows) - source_vector_count),
            "sensor_vector_source_count": source_vector_count,
            "sampling_applied": bool(vector_rows.get("sampling_applied")),
            "processing_trace": processing_trace,
            "output_summary": output_summary,
            "latest_state": latest_state,
            "evidence": evidence,
        }
    )
    write_latest_sii_state(
        build_runtime_state(
            latest_state=latest_state,
            primary_room=primary_room,
            evidence=evidence,
            driver_attribution=driver_attribution,
            processing_trace=processing_trace,
            output_summary=output_summary,
        )
    )
    return base_result


def build_sensor_vectors(
    columns: list[str],
    rows: list[list[str]],
    numeric_profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    numeric_columns = [
        profile["column"]
        for profile in numeric_profiles
        if profile.get("column") in columns
    ]
    column_indexes = [columns.index(column) for column in numeric_columns]
    vectors: list[list[float]] = []
    row_indexes: list[int] = []
    for row_index, row in enumerate(rows):
        values: list[float] = []
        for column_index in column_indexes:
            raw_value = row[column_index].strip() if column_index < len(row) else ""
            parsed_value = parse_numeric_value(raw_value)
            if parsed_value is None:
                values.append(float("nan"))
            elif parsed_value == SENTINEL:
                values.append(float("nan"))
            else:
                values.append(parsed_value)
        if values and not all(np.isnan(value) for value in values):
            vectors.append(values)
            row_indexes.append(row_index)
    return {
        "columns_used": numeric_columns,
        "vectors": vectors,
        "row_indexes": row_indexes,
    }


def limit_runner_vectors(vector_rows: dict[str, Any]) -> dict[str, Any]:
    vectors = list(vector_rows.get("vectors") or [])
    row_indexes = list(vector_rows.get("row_indexes") or [])
    total_vectors = len(vectors)
    if MAX_RUNNER_VECTOR_ROWS <= 0 or total_vectors <= MAX_RUNNER_VECTOR_ROWS:
        return {
            **vector_rows,
            "sampling_applied": False,
            "source_vector_count": total_vectors,
            "retained_vector_count": total_vectors,
        }

    retained_tail = min(total_vectors, max(100, min(RECENT_VECTOR_TAIL, MAX_RUNNER_VECTOR_ROWS // 2 or 100)))
    prefix_count = max(0, total_vectors - retained_tail)
    prefix_budget = max(0, MAX_RUNNER_VECTOR_ROWS - retained_tail)

    if prefix_budget <= 0 or prefix_count <= 0:
        retained_indexes = list(range(max(0, total_vectors - MAX_RUNNER_VECTOR_ROWS), total_vectors))
    elif prefix_budget >= prefix_count:
        retained_indexes = list(range(total_vectors))
    else:
        prefix_indexes = np.linspace(0, prefix_count - 1, num=prefix_budget, dtype=int).tolist()
        retained_indexes = list(dict.fromkeys(prefix_indexes + list(range(prefix_count, total_vectors))))

    sampled_vectors = [vectors[index] for index in retained_indexes]
    sampled_row_indexes = [row_indexes[index] for index in retained_indexes]
    return {
        **vector_rows,
        "vectors": sampled_vectors,
        "row_indexes": sampled_row_indexes,
        "sampling_applied": True,
        "source_vector_count": total_vectors,
        "retained_vector_count": len(sampled_vectors),
    }


def parse_timestamp(columns: list[str], row: list[str], timestamp_column: str | None, fallback_index: int) -> float:
    if timestamp_column and timestamp_column in columns:
        column_index = columns.index(timestamp_column)
        raw_value = row[column_index].strip() if column_index < len(row) else ""
        if raw_value:
            numeric_value = parse_numeric_value(raw_value)
            if numeric_value is not None:
                return numeric_value
            try:
                parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=UTC)
                return parsed.timestamp()
            except ValueError:
                pass
    return float(fallback_index + 1)


def summarize_runner_outputs(states: list[dict[str, Any]]) -> dict[str, Any]:
    latest = states[-1] if states else {}
    scores = [float(state.get("instability_score", 0.0)) for state in states]
    return {
        "frames_processed": len(states),
        "latest_regime": latest.get("regime"),
        "latest_urgency": latest.get("urgency"),
        "latest_instability_score": latest.get("instability_score"),
        "latest_instability_components": latest.get("instability_components", {}),
        "max_instability_score": round(max(scores), 6) if scores else 0.0,
        "latest_structural_drift": latest.get("structural_drift"),
        "latest_confidence": latest.get("confidence"),
    }


def build_runtime_state(
    *,
    latest_state: dict[str, Any],
    primary_room: str,
    evidence: list[str],
    driver_attribution: dict[str, Any],
    processing_trace: dict[str, Any],
    output_summary: dict[str, Any],
) -> dict[str, Any]:
    urgency = normalize_urgency(str(latest_state.get("urgency", "NOMINAL")))
    score = max(0, min(100, round(100 - float(latest_state.get("instability_score", 0.0)) * 100)))
    room_state = room_state_from_regime(str(latest_state.get("regime", "WARMUP")))
    primary_driver = driver_attribution.get("likely_driver") or "SII structural telemetry pattern"
    structural_explanation = [
        f"SII regime is {latest_state.get('regime', 'unknown')} with urgency {latest_state.get('urgency', 'unknown')}.",
        f"Structural drift score is {round(float(latest_state.get('structural_drift', 0.0)), 4)}.",
        f"Transition pressure is {round(float(latest_state.get('transition_pressure', 0.0)), 4)}.",
    ]
    room = {
        "room": primary_room,
        "room_state": room_state,
        "urgency": urgency,
        "intervention_window": window_from_urgency(urgency),
        "primary_driver": primary_driver,
        "supporting_evidence": evidence,
        "relationship_evidence": evidence[:2],
        "structural_explanation": structural_explanation,
        "confidence_basis": confidence_basis(latest_state),
        "recommended_operator_review": driver_attribution.get("next_operator_move") or next_move_from_urgency(urgency),
        "what_to_check": driver_attribution.get("what_to_check", []) or [next_move_from_urgency(urgency)],
        "why_flagged": evidence[0] if evidence else "SII runner processed uploaded telemetry.",
        "baseline_comparison": f"SII latest structural drift: {output_summary.get('latest_structural_drift', 0.0)}",
        "observed_persistence": f"SII processed {output_summary.get('frames_processed', 0)} telemetry frames.",
        "review_window": format_review_window_hours(project_time_to_failure_hours_from_state(latest_state)),
        "review_window_hours": project_time_to_failure_hours_from_state(latest_state),
        "projected_time_to_failure": format_review_window_hours(project_time_to_failure_hours_from_state(latest_state)),
        "projected_time_to_failure_hours": project_time_to_failure_hours_from_state(latest_state),
        "last_updated": now_iso(),
        "confidence": round(float(latest_state.get("confidence", 0.0)) * 100),
    }
    instability_index = (
        latest_state.get("instability_index")
        if isinstance(latest_state.get("instability_index"), dict)
        else build_instability_index(latest_state)
    )
    return {
        "source": "uploaded",
        "mode": "live",
        "facility_state": room_state,
        "room_state": room_state,
        "urgency": urgency,
        "rooms": [room],
        "priority_room": primary_room,
        "primary_room": primary_room,
        "neraium_score": score,
        "primary_driver": primary_driver,
        "structural_explanation": structural_explanation,
        "supporting_evidence": evidence,
        "relationship_evidence": evidence[:2],
        "intervention_window": room["intervention_window"],
        "confidence_basis": room["confidence_basis"],
        "recommended_operator_review": room["recommended_operator_review"],
        "next_operator_move": room["recommended_operator_review"],
        "what_to_check": room["what_to_check"],
        "why_flagged": room["why_flagged"],
        "baseline_comparison": room["baseline_comparison"],
        "observed_persistence": room["observed_persistence"],
        "review_window": room["review_window"],
        "review_window_hours": room["review_window_hours"],
        "projected_time_to_failure": room["projected_time_to_failure"],
        "projected_time_to_failure_hours": room["projected_time_to_failure_hours"],
        "runner_module": RUNNER_MODULE,
        "core_engine": CORE_ENGINE,
        "latest_state": latest_state,
        "instability_index": instability_index,
        "last_updated": room["last_updated"],
        "last_processed_at": room["last_updated"],
        "processing_trace": processing_trace,
    }


def build_instability_index(latest_state: dict[str, Any]) -> dict[str, Any]:
    components = latest_state.get("instability_components", {}) if isinstance(latest_state, dict) else {}
    drift = float(
        components.get(
            "structural_drift_score",
            components.get("drift", latest_state.get("structural_drift", 0.0)),
        )
    )
    relationship = float(
        latest_state.get(
            "transition_pressure",
            components.get("relationship_degradation", 0.0),
        )
    )
    if "transition_pressure" not in latest_state:
        relationship = float(components.get("relationship_degradation", 0.0))
    entropy = float(components.get("covariance_shift", components.get("entropy_growth", 0.0)))
    runner_score = float(latest_state.get("instability_score", 0.0))
    causal = float(np.clip(latest_state.get("confidence", 0.0), 0.0, 1.0) * np.clip(runner_score, 0.0, 1.0))
    if "covariance_shift" in components or "trajectory_curvature" in components:
        topology = float(
            np.clip(
                (float(components.get("covariance_shift", 0.0)) * 0.7)
                + (float(components.get("trajectory_curvature", 0.0)) * 0.3),
                0.0,
                1.0,
            )
        )
    else:
        topology = float(np.clip((drift * 0.6) + (relationship * 0.4), 0.0, 1.0))
    score = float(np.clip((drift * 0.35) + (relationship * 0.25) + (entropy * 0.15) + (causal * 0.15) + (topology * 0.10), 0.0, 1.0))
    return {
        "score": round(score, 6),
        "components": {
            "drift": round(float(np.clip(drift, 0.0, 1.0)), 6),
            "relationship_degradation": round(float(np.clip(relationship, 0.0, 1.0)), 6),
            "entropy_growth": round(float(np.clip(entropy, 0.0, 1.0)), 6),
            "causal_evidence": round(float(np.clip(causal, 0.0, 1.0)), 6),
            "topology_propagation": round(float(np.clip(topology, 0.0, 1.0)), 6),
        },
        "model": {"name": "sii_instability_index", "version": "phase1-v1"},
    }


def build_runner_evidence(
    latest_state: dict[str, Any],
    columns_used: list[str],
    driver_attribution: dict[str, Any],
    engine_result: dict[str, Any],
) -> list[str]:
    evidence = [
        f"Backend SII runner ingested {len(columns_used)} numeric telemetry channels.",
        f"Backend SII runner reported {latest_state.get('regime', 'unknown')} regime and {latest_state.get('urgency', 'unknown')} urgency.",
        f"Instability score {round(float(latest_state.get('instability_score', 0.0)), 4)} with structural drift {round(float(latest_state.get('structural_drift', 0.0)), 4)}.",
    ]
    if driver_attribution.get("driver_category"):
        evidence.append(f"Driver attribution category: {driver_attribution['driver_category']}.")
    for item in engine_result.get("evidence", [])[:2]:
        if item.get("type"):
            evidence.append("Environmental coupling is less consistent than the room's recent baseline.")
    return evidence


def read_latest_sii_state() -> dict[str, Any] | None:
    try:
        persisted = read_latest_payload("latest_sii_state")
        if isinstance(persisted, dict) and is_valid_latest_sii_state(persisted):
            return persisted
    except Exception:
        pass
    if not STATE_PATH.exists():
        return None
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return state if is_valid_latest_sii_state(state) else None


def write_latest_sii_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    last_error: OSError | None = None
    for attempt in range(6):
        try:
            temp_path.replace(STATE_PATH)
            try:
                upsert_latest_payload("latest_sii_state", state)
            except Exception:
                pass
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.02 * (attempt + 1))
    if last_error is not None:
        raise last_error


def reset_latest_sii_state() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        STATE_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def is_valid_latest_sii_state(state: Any) -> bool:
    if not isinstance(state, dict):
        return False
    if not STATE_REQUIRED_FIELDS <= set(state):
        return False
    if not isinstance(state.get("rooms"), list):
        return False
    if not isinstance(state.get("supporting_evidence"), list):
        return False
    if not isinstance(state.get("structural_explanation"), list):
        return False
    return True


def to_plain_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return dict(value)


def now_iso() -> str: 
    return datetime.now(UTC).isoformat() 
 
 
def parse_state_timestamp(raw_value: Any) -> datetime | None: 
    if not raw_value: 
        return None 
    try: 
        parsed = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00")) 
    except ValueError: 
        return None 
    if parsed.tzinfo is None: 
        parsed = parsed.replace(tzinfo=UTC) 
    return parsed.astimezone(UTC) 


def classify_state(history_length: int, instability_score: float, transition_pressure: float) -> tuple[str, str]: 
    if history_length < 3: 
        return "WARMUP", "NOMINAL" 
    if instability_score >= 0.72 or transition_pressure >= 0.9: 
        return "LOCK_IN", "CRITICAL" 
    if instability_score >= 0.52 or transition_pressure >= 0.62:
        return "UNSTABLE", "ALERT"
    if instability_score >= 0.24 or transition_pressure >= 0.28:
        return "TRANSITION", "WATCH"
    return "STABLE", "NOMINAL"


def confidence_from_history(history_length: int, vector: np.ndarray, *, recent_vectors: np.ndarray | None = None) -> float:
    current_completeness = float(np.mean(~np.isnan(vector))) if vector.size else 0.0
    recent_completeness = _matrix_completeness(recent_vectors) if recent_vectors is not None else current_completeness
    history_factor = min(history_length / 36.0, 1.0)
    raw_confidence = 0.20 + history_factor * 0.26 + current_completeness * 0.18 + recent_completeness * 0.18
    quality_cap = 0.90 if min(current_completeness, recent_completeness) >= 0.995 else 0.55 + min(current_completeness, recent_completeness) * 0.35
    if history_length < 8:
        quality_cap = min(quality_cap, 0.42)
    elif history_length < 16:
        quality_cap = min(quality_cap, 0.58)
    elif history_length < 24:
        quality_cap = min(quality_cap, 0.58)
    elif history_length < 36:
        quality_cap = min(quality_cap, 0.72)
    return float(np.clip(raw_confidence, 0.18, quality_cap))


def normalize_urgency(urgency: str) -> str: 
    normalized = urgency.lower()
    if normalized == "critical":
        return "unstable"
    if normalized == "alert":
        return "elevated"
    if normalized == "watch":
        return "review"
    return "nominal"


def room_state_from_regime(regime: str) -> str:
    return {
        "LOCK_IN": "Needs action",
        "UNSTABLE": "Needs action",
        "TRANSITION": "Drift observed",
        "STABLE": "Stable",
        "WARMUP": "Monitoring",
    }.get(regime, "Monitoring")


def window_from_urgency(urgency: str) -> str:
    return {
        "unstable": "8 hours",
        "elevated": "2 days",
        "review": "6 days",
        "nominal": "3 weeks",
    }.get(urgency, "Monitoring")


def next_move_from_urgency(urgency: str) -> str:
    if urgency == "unstable":
        return "Escalate room review"
    if urgency in {"elevated", "review"}:
        return "Review SII runner evidence"
    return "Continue monitoring"


def confidence_basis(latest_state: dict[str, Any]) -> str:
    confidence = round(float(latest_state.get("confidence", 0.0)) * 100)
    return f"Backend SII runner confidence {confidence}% from baseline and telemetry history depth."


def project_time_to_failure_hours_from_state(latest_state: dict[str, Any]) -> int:
    urgency = normalize_urgency(str(latest_state.get("urgency", "NOMINAL")))
    base_hours = {"unstable": 8, "elevated": 36, "review": 72, "nominal": 504}.get(urgency, 72)
    instability_score = float(latest_state.get("instability_score", 0.0))
    structural_drift = float(latest_state.get("structural_drift", 0.0))
    transition_pressure = float(latest_state.get("transition_pressure", 0.0))
    risk_factor = instability_score * 0.5 + structural_drift * 0.3 + transition_pressure * 0.2
    scaled = int(base_hours * max(0.25, 1.0 - min(max(risk_factor, 0.0), 0.9)))
    return max(4, scaled)


def format_review_window_hours(hours: int) -> str:
    if hours <= 12:
        return f"Review within approximately {hours} hours if trajectory persists"
    if hours <= 72:
        return f"Review within approximately {max(1, round(hours / 24))} days if trajectory persists"
    return f"Continue monitoring; review within {max(1, round(hours / 168))} weeks if trajectory persists"


def format_projected_time_to_failure_hours(hours: int) -> str:
    return format_review_window_hours(hours)
