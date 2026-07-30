from __future__ import annotations

import math
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from app.services.baseline_contracts import (
    BASELINE_RESULT_CONTRACT_VERSION,
    BEHAVIORAL_MODEL_CONTRACT_VERSION,
    WORKFLOW_CREATE_BASELINE,
    WORKFLOW_EXTEND_BASELINE,
    assert_baseline_output_contract,
)
from app.services.behavioral_model_repository import (
    next_model_version,
    persist_candidate,
    read_active_behavioral_model,
    verify_persisted_baseline,
)
from app.services.data_quality import build_data_quality, profile_timestamps
from app.services.dataset_scope import current_dataset_scope
from app.services.sensor_health import assess_sensor_health, build_data_confidence
from app.services.telemetry_classification import build_telemetry_signal_catalog
from app.services.telemetry_normalization import build_normalization_report


StageNotifier = Callable[..., None]


def _notify(
    notifier: StageNotifier | None,
    job_id: str,
    *,
    stage: str,
    progress: int,
    label: str,
) -> None:
    if notifier:
        notifier(job_id, stage=stage, progress=progress, label=label)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(str(value).strip().replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _series(rows: list[dict[str, Any]], column: str) -> list[float]:
    return [
        value
        for row in rows
        if (value := _number(row.get(column))) is not None
    ]


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = max(0.0, min(1.0, fraction)) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _mean(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    average = _mean(values)
    return math.sqrt(sum((value - average) ** 2 for value in values) / len(values))


def _correlation(left: list[float], right: list[float]) -> float | None:
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


def _paired_series(
    rows: list[dict[str, Any]],
    left: str,
    right: str,
    *,
    lag: int = 0,
) -> tuple[list[float], list[float]]:
    pairs = [
        (left_value, right_value)
        for row in rows
        if (left_value := _number(row.get(left))) is not None
        and (right_value := _number(row.get(right))) is not None
    ]
    if lag > 0:
        pairs = [(pairs[index][0], pairs[index + lag][1]) for index in range(len(pairs) - lag)]
    elif lag < 0:
        offset = abs(lag)
        pairs = [(pairs[index + offset][0], pairs[index][1]) for index in range(len(pairs) - offset)]
    return [item[0] for item in pairs], [item[1] for item in pairs]


def _state_columns(
    columns: list[str],
    telemetry_signal_catalog: dict[str, dict[str, Any]],
) -> list[str]:
    state_tokens = ("state", "status", "stage", "mode", "enable", "command", "schedule", "setpoint", "load")
    candidates = []
    for column in columns:
        metadata = telemetry_signal_catalog.get(column, {})
        category = str(metadata.get("category") or "")
        if metadata.get("is_state_signal") or category in {
            "binary_status",
            "equipment_state",
            "setpoint",
            "scheduled_load_context",
        } or any(token in column.lower() for token in state_tokens):
            candidates.append(column)
    return candidates[:3]


def _normalize_state(value: Any) -> str:
    number = _number(value)
    if number is not None:
        return f"{number:.3g}"
    return str(value or "missing").strip().lower()[:40] or "missing"


def _identify_modes(
    rows: list[dict[str, Any]],
    columns: list[str],
    numeric_columns: list[str],
    telemetry_signal_catalog: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[int]]]:
    explicit = _state_columns(columns, telemetry_signal_catalog)
    signatures: list[tuple[str, ...]] = []
    defining_columns: list[str]
    if explicit:
        defining_columns = explicit
        signatures = [
            tuple(_normalize_state(row.get(column)) for column in explicit)
            for row in rows
        ]
    else:
        anchor = next(
            (
                column
                for column in numeric_columns
                if len(set(_series(rows, column))) >= 3
            ),
            None,
        )
        if anchor:
            values = _series(rows, anchor)
            low = _quantile(values, 1 / 3)
            high = _quantile(values, 2 / 3)
            defining_columns = [anchor]
            signatures = []
            for row in rows:
                value = _number(row.get(anchor))
                band = "missing" if value is None else "low" if value <= float(low) else "high" if value >= float(high) else "mid"
                signatures.append((band,))
        else:
            defining_columns = []
            signatures = [("all_operation",) for _ in rows]

    counts = Counter(signatures)
    retained = {signature for signature, _ in counts.most_common(8)}
    membership: dict[str, list[int]] = defaultdict(list)
    public_modes: list[dict[str, Any]] = []
    mode_id_by_signature: dict[tuple[str, ...], str] = {}
    for index, (signature, count) in enumerate(counts.most_common(8), start=1):
        mode_id = f"mode_{index}"
        mode_id_by_signature[signature] = mode_id
        public_modes.append(
            {
                "mode_id": mode_id,
                "label": " / ".join(signature),
                "sample_count": count,
                "sample_fraction": round(count / max(1, len(rows)), 6),
                "defining_conditions": [
                    {"signal": column, "value": value}
                    for column, value in zip(defining_columns, signature)
                ],
                "identification_method": "explicit_operating_state_v1" if explicit else "empirical_load_band_v1",
            }
        )
    for row_index, signature in enumerate(signatures):
        normalized = signature if signature in retained else counts.most_common(1)[0][0]
        membership[mode_id_by_signature[normalized]].append(row_index)
    return public_modes, dict(membership)


def _signal_characteristics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "samples": 0,
            "distribution": {},
            "empirical_thresholds": {},
            "volatility": {},
            "persistence": {},
            "lag_behavior": {},
        }
    ordered = sorted(values)

    def quantile(fraction: float) -> float:
        position = max(0.0, min(1.0, fraction)) * (len(ordered) - 1)
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return ordered[lower]
        weight = position - lower
        return ordered[lower] * (1.0 - weight) + ordered[upper] * weight

    average = _mean(values)
    spread = _std(values)
    differences = [current - previous for previous, current in zip(values, values[1:])]
    median_value = quantile(0.5)
    mad = _quantile([abs(value - median_value) for value in values], 0.5)
    lag_one = _correlation(values[:-1], values[1:]) if len(values) >= 4 else None
    lag_scores = []
    for lag in range(1, min(12, len(values) // 3) + 1):
        correlation = _correlation(values[:-lag], values[lag:])
        if correlation is not None:
            lag_scores.append((lag, correlation))
    strongest_lag = max(lag_scores, key=lambda item: abs(item[1])) if lag_scores else None
    iqr_low = quantile(0.25)
    iqr_high = quantile(0.75)
    within_iqr = [iqr_low <= value <= iqr_high for value in values]
    longest_run = current_run = 0
    for inside in within_iqr:
        current_run = current_run + 1 if inside else 0
        longest_run = max(longest_run, current_run)
    return {
        "samples": len(values),
        "distribution": {
            "minimum": round(min(values), 8),
            "p01": round(quantile(0.01), 8),
            "p05": round(quantile(0.05), 8),
            "p25": round(iqr_low, 8),
            "median": round(float(median_value), 8),
            "mean": round(average, 8),
            "p75": round(iqr_high, 8),
            "p95": round(quantile(0.95), 8),
            "p99": round(quantile(0.99), 8),
            "maximum": round(max(values), 8),
            "standard_deviation": round(spread, 8),
        },
        "empirical_thresholds": {
            "expected_lower": round(quantile(0.01), 8),
            "expected_upper": round(quantile(0.99), 8),
            "central_lower": round(quantile(0.05), 8),
            "central_upper": round(quantile(0.95), 8),
            "method": "empirical_quantiles_v1",
        },
        "volatility": {
            "standard_deviation": round(spread, 8),
            "median_absolute_deviation": round(float(mad), 8),
            "difference_standard_deviation": round(_std(differences), 8),
            "coefficient_of_variation": round(spread / abs(average), 8) if abs(average) > 1e-12 else None,
        },
        "persistence": {
            "lag_one_autocorrelation": round(lag_one, 8) if lag_one is not None else None,
            "longest_central_band_run": longest_run,
            "longest_central_band_fraction": round(longest_run / len(values), 8),
        },
        "lag_behavior": {
            "strongest_self_lag_samples": strongest_lag[0] if strongest_lag else None,
            "strongest_self_lag_correlation": round(strongest_lag[1], 8) if strongest_lag else None,
            "method": "bounded_autocorrelation_v1",
        },
    }


def _learn_distributions(
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    modes: list[dict[str, Any]],
    membership: dict[str, list[int]],
) -> dict[str, dict[str, Any]]:
    learned: dict[str, dict[str, Any]] = {}
    for column in numeric_columns[:50]:
        characteristics = _signal_characteristics(_series(rows, column))
        characteristics["mode_conditioned"] = {
            mode["mode_id"]: _signal_characteristics(
                _series([rows[index] for index in membership.get(mode["mode_id"], [])], column)
            )
            for mode in modes
            if len(membership.get(mode["mode_id"], [])) >= 3
        }
        learned[column] = characteristics
    return learned


def _relationship_edge(
    rows: list[dict[str, Any]],
    left: str,
    right: str,
    *,
    mode_id: str,
) -> dict[str, Any] | None:
    left_values, right_values = _paired_series(rows, left, right)
    correlation = _correlation(left_values, right_values)
    if correlation is None or abs(correlation) < 0.3:
        return None
    lag_candidates = []
    for lag in range(-6, 7):
        if lag > 0:
            lag_left, lag_right = left_values[:-lag], right_values[lag:]
        elif lag < 0:
            offset = abs(lag)
            lag_left, lag_right = left_values[offset:], right_values[:-offset]
        else:
            lag_left, lag_right = left_values, right_values
        lag_correlation = _correlation(lag_left, lag_right)
        if lag_correlation is not None:
            lag_candidates.append((lag, lag_correlation, len(lag_left)))
    strongest = max(lag_candidates, key=lambda item: abs(item[1])) if lag_candidates else (0, correlation, len(left_values))
    return {
        "edge_id": f"{mode_id}:{left}:{right}",
        "source": left,
        "target": right,
        "mode_id": mode_id,
        "correlation": round(correlation, 8),
        "strength": round(abs(correlation), 8),
        "direction": "positive" if correlation >= 0 else "negative",
        "sample_count": len(left_values),
        "lag_behavior": {
            "strongest_lag_samples": strongest[0],
            "strongest_lag_correlation": round(strongest[1], 8),
            "paired_samples": strongest[2],
            "method": "bounded_cross_correlation_v1",
        },
    }


def _learn_relationship_graph(
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    modes: list[dict[str, Any]],
    membership: dict[str, list[int]],
) -> dict[str, Any]:
    selected = numeric_columns[:20]
    edges: list[dict[str, Any]] = []
    row_groups = {"all_operation": rows}
    row_groups.update(
        {
            mode["mode_id"]: [rows[index] for index in membership.get(mode["mode_id"], [])]
            for mode in modes
        }
    )
    for mode_id, mode_rows in row_groups.items():
        if len(mode_rows) < 4:
            continue
        for left_index, left in enumerate(selected):
            for right in selected[left_index + 1 :]:
                edge = _relationship_edge(mode_rows, left, right, mode_id=mode_id)
                if edge:
                    edges.append(edge)
    edges.sort(key=lambda item: (-item["strength"], item["edge_id"]))
    return {
        "nodes": [
            {"signal": column, "type": "telemetry_signal"}
            for column in selected
        ],
        "edges": edges[:200],
        "mode_conditioned": True,
        "construction_method": "empirical_mode_conditioned_correlation_v1",
        "relationships_evaluated": len(selected) * max(0, len(selected) - 1) // 2,
    }


def _fit_linear_model(
    rows: list[dict[str, Any]],
    edge: dict[str, Any],
) -> dict[str, Any] | None:
    left, right = _paired_series(rows, edge["source"], edge["target"])
    if len(left) < 8:
        return None
    split = max(4, min(len(left) - 2, int(len(left) * 0.8)))
    train_x, validate_x = left[:split], left[split:]
    train_y, validate_y = right[:split], right[split:]
    x_mean = _mean(train_x)
    y_mean = _mean(train_y)
    denominator = sum((value - x_mean) ** 2 for value in train_x)
    if denominator <= 1e-12:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(train_x, train_y)) / denominator
    intercept = y_mean - slope * x_mean
    predictions = [intercept + slope * value for value in validate_x]
    residuals = [actual - predicted for actual, predicted in zip(validate_y, predictions)]
    rmse = math.sqrt(_mean([value * value for value in residuals])) if residuals else 0.0
    mae = _mean([abs(value) for value in residuals]) if residuals else 0.0
    validation_mean = _mean(validate_y)
    total_variance = sum((value - validation_mean) ** 2 for value in validate_y)
    residual_variance = sum(value * value for value in residuals)
    r_squared = 1.0 - residual_variance / total_variance if total_variance > 1e-12 else None
    return {
        "model_id": f"expected:{edge['edge_id']}",
        "mode_id": edge["mode_id"],
        "predictor": edge["source"],
        "response": edge["target"],
        "model_type": "ordinary_least_squares_v1",
        "parameters": {
            "slope": round(slope, 10),
            "intercept": round(intercept, 10),
        },
        "training_samples": len(train_x),
        "validation_samples": len(validate_x),
        "validation": {
            "rmse": round(rmse, 10),
            "mae": round(mae, 10),
            "r_squared": round(r_squared, 8) if r_squared is not None else None,
            "accepted": bool(r_squared is None or r_squared >= 0.2),
            "method": "chronological_holdout_v1",
        },
    }


def _fit_expected_models(
    rows: list[dict[str, Any]],
    relationship_graph: dict[str, Any],
    membership: dict[str, list[int]],
) -> list[dict[str, Any]]:
    models = []
    for edge in relationship_graph.get("edges", [])[:50]:
        mode_id = str(edge.get("mode_id"))
        model_rows = rows if mode_id == "all_operation" else [
            rows[index] for index in membership.get(mode_id, [])
        ]
        model = _fit_linear_model(model_rows, edge)
        if model:
            models.append(model)
    return models


def _suitability_report(
    *,
    row_count: int,
    numeric_columns: list[str],
    timestamp_profile: dict[str, Any],
    data_quality: dict[str, Any],
    sensor_health: dict[str, Any],
    modes: list[dict[str, Any]],
    relationship_graph: dict[str, Any],
    expected_models: list[dict[str, Any]],
) -> dict[str, Any]:
    timestamp_score = 100 if timestamp_profile.get("first_timestamp") and timestamp_profile.get("last_timestamp") else 35 if timestamp_profile.get("detected_timestamp_column") else 0
    quality_score = int(data_quality.get("reliability_score") or 0)
    healthy_signals = sum(
        1 for item in sensor_health.get("signals", []) if item.get("health") == "healthy"
    )
    signal_count = max(1, len(sensor_health.get("signals", [])))
    sensor_score = round(healthy_signals / signal_count * 100)
    coverage_score = min(100, round(row_count / 100 * 100))
    relationship_score = min(100, len(relationship_graph.get("edges", [])) * 8)
    model_score = min(
        100,
        sum(1 for model in expected_models if model.get("validation", {}).get("accepted")) * 12,
    )
    score = round(
        timestamp_score * 0.15
        + quality_score * 0.25
        + sensor_score * 0.15
        + coverage_score * 0.15
        + relationship_score * 0.15
        + model_score * 0.15
    )
    blocking_reasons = []
    limitations = []
    if row_count < 12:
        blocking_reasons.append("At least 12 usable telemetry rows are required.")
    if not numeric_columns:
        blocking_reasons.append("No usable numeric telemetry signals were available.")
    if quality_score < 40:
        blocking_reasons.append("Telemetry reliability is below the baseline suitability floor.")
    if not timestamp_profile.get("detected_timestamp_column"):
        limitations.append("No timestamp column was detected; time-dependent baseline characteristics are limited.")
    if not relationship_graph.get("edges"):
        limitations.append("No repeatable signal relationships met the empirical learning floor.")
    if not expected_models:
        limitations.append("No expected-behavior model had enough samples for holdout validation.")
    if blocking_reasons:
        decision = "unsuitable"
    elif score >= 70:
        decision = "suitable"
    else:
        decision = "conditionally_suitable"
    return {
        "contract_version": BASELINE_RESULT_CONTRACT_VERSION,
        "decision": decision,
        "score": score,
        "eligible_for_activation": decision in {"suitable", "conditionally_suitable"},
        "dimensions": {
            "timestamp_quality": timestamp_score,
            "data_quality": quality_score,
            "sensor_health": sensor_score,
            "sample_coverage": coverage_score,
            "relationship_coverage": relationship_score,
            "model_validation": model_score,
            "operating_mode_count": len(modes),
        },
        "blocking_reasons": blocking_reasons,
        "limitations": limitations,
    }


def build_behavioral_baseline(
    *,
    job_id: str,
    filename: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    row_count_total: int,
    numeric_profiles: list[dict[str, Any]],
    ingestion_report: dict[str, Any] | None = None,
    workflow: str = WORKFLOW_CREATE_BASELINE,
    approval_required: bool = True,
    active_model: dict[str, Any] | None = None,
    stage_notifier: StageNotifier | None = None,
    dataset_id: str | None = None,
) -> dict[str, Any]:
    """Build a candidate Behavioral Digital Model without running SII detection."""

    if workflow not in {WORKFLOW_CREATE_BASELINE, WORKFLOW_EXTEND_BASELINE}:
        raise ValueError("build_behavioral_baseline only accepts baseline workflows")
    active_model = active_model or read_active_behavioral_model()
    if workflow == WORKFLOW_EXTEND_BASELINE and not isinstance(active_model, dict):
        raise ValueError("active_behavioral_baseline_required_for_extension")

    started = time.perf_counter()
    dataset_id = str(dataset_id or job_id)
    ingestion_report = ingestion_report or {}
    matrix_rows = [[str(row.get(column, "")) for column in columns] for row in rows]

    _notify(stage_notifier, job_id, stage="baseline_validating", progress=42, label="Validating and normalizing telemetry...")
    timestamp_profile = profile_timestamps(columns, matrix_rows, timestamp_column)
    telemetry_signal_catalog = build_telemetry_signal_catalog(
        columns,
        numeric_profiles=numeric_profiles,
        timestamp_column=timestamp_column,
        header_present=bool(ingestion_report.get("header_present", True)),
    )
    normalization_report = build_normalization_report(
        rows=rows,
        numeric_columns=numeric_columns,
        timestamp_column=timestamp_column,
        source_id=filename or job_id,
    )

    _notify(stage_notifier, job_id, stage="baseline_quality_assessment", progress=55, label="Assessing timestamp, data, and sensor quality...")
    stuck_sensor_count = sum(
        1 for profile in numeric_profiles if profile.get("constant_or_stuck")
    )
    data_quality = build_data_quality(
        row_count_total,
        len(columns),
        len(numeric_columns),
        bool(timestamp_column),
        list(
            dict.fromkeys(
                [
                    *list(ingestion_report.get("warnings") or []),
                    *list(timestamp_profile.get("warnings") or []),
                    *list(normalization_report.get("warnings") or []),
                ]
            )
        ),
        {
            "rows_received": ingestion_report.get("rows_received", row_count_total),
            "rows_dropped": ingestion_report.get("rows_dropped", 0),
            "quality_counts": ingestion_report.get("quality_counts", {}),
            "stuck_sensor_count": stuck_sensor_count,
            "irregular_sampling": timestamp_profile.get("estimated_sample_interval") is None,
            "baseline_reliable": row_count_total >= 12 and bool(numeric_columns),
            "schema_detection": ingestion_report.get("schema_detection", {}),
            "analysis_gate_state": ingestion_report.get("analysis_gate_state"),
            "data_quality_messages": ingestion_report.get("data_quality_messages", []),
            "imputation_report": ingestion_report.get("imputation_report", {}),
            "normalization_report": normalization_report,
        },
    )
    sensor_health = assess_sensor_health(
        rows,
        numeric_columns,
        timestamp_column=timestamp_column,
        numeric_profiles=numeric_profiles,
        normalization_report=normalization_report,
        ingestion_report=ingestion_report,
        timestamp_profile=timestamp_profile,
        relationship_model={},
        telemetry_signal_catalog=telemetry_signal_catalog,
    )
    data_quality["data_confidence"] = build_data_confidence(data_quality, sensor_health)

    _notify(stage_notifier, job_id, stage="baseline_mode_identification", progress=66, label="Identifying operating modes...")
    operating_modes, membership = _identify_modes(
        rows,
        columns,
        numeric_columns,
        telemetry_signal_catalog,
    )

    _notify(stage_notifier, job_id, stage="baseline_relationship_learning", progress=78, label="Learning distributions and mode-conditioned relationships...")
    signal_characteristics = _learn_distributions(
        rows,
        numeric_columns,
        operating_modes,
        membership,
    )
    relationship_graph = _learn_relationship_graph(
        rows,
        numeric_columns,
        operating_modes,
        membership,
    )

    _notify(stage_notifier, job_id, stage="baseline_model_fitting", progress=88, label="Fitting and validating expected behavior...")
    expected_behavior_models = _fit_expected_models(
        rows,
        relationship_graph,
        membership,
    )
    suitability = _suitability_report(
        row_count=row_count_total,
        numeric_columns=numeric_columns,
        timestamp_profile=timestamp_profile,
        data_quality=data_quality,
        sensor_health=sensor_health,
        modes=operating_modes,
        relationship_graph=relationship_graph,
        expected_models=expected_behavior_models,
    )

    _notify(stage_notifier, job_id, stage="baseline_candidate_persistence", progress=96, label="Saving versioned behavioral model candidate...")
    now = datetime.now(timezone.utc).isoformat()
    version = next_model_version()
    model_id = f"bdm-v{version}-{job_id[:8]}"
    eligible = bool(suitability["eligible_for_activation"])
    auto_activate = eligible and not approval_required
    # Eligible models remain candidates until the repository commits the active
    # pointer. Automatic policy promotes them inside the same activation lock.
    status = "unsuitable" if not eligible else "awaiting_approval"
    scope = current_dataset_scope()
    model = {
        "contract_version": BEHAVIORAL_MODEL_CONTRACT_VERSION,
        "model_id": model_id,
        "baseline_id": model_id,
        "baseline_candidate_id": model_id,
        "version": version,
        "status": status,
        "workflow": workflow,
        "created_at": now,
        "source": {
            "job_id": job_id,
            "upload_id": job_id,
            "dataset_id": dataset_id,
            "portfolio_id": scope.workspace_id,
            "system_id": scope.workspace_id,
            "filename": filename,
            "row_count": row_count_total,
            "column_count": len(columns),
            "timestamp_column": timestamp_column,
        },
        "lineage": {
            "parent_model_id": active_model.get("model_id") if isinstance(active_model, dict) else None,
            "parent_version": active_model.get("version") if isinstance(active_model, dict) else None,
            "learning_policy": "controlled_extension_v1" if workflow == WORKFLOW_EXTEND_BASELINE else "initial_baseline_v1",
        },
        "telemetry_schema": {
            "columns": columns,
            "numeric_columns": numeric_columns,
            "signal_catalog": telemetry_signal_catalog,
        },
        "timestamp_quality": timestamp_profile,
        "data_quality": data_quality,
        "sensor_health": sensor_health,
        "operating_modes": operating_modes,
        "signal_characteristics": signal_characteristics,
        "relationship_graph": relationship_graph,
        "expected_behavior_models": expected_behavior_models,
        "suitability": suitability,
        "activation": {
            "eligible": eligible,
            "approval_required": bool(approval_required),
            "state": status,
            "approved_by": None,
            "activated_at": None,
        },
    }
    result = {
        "contract_version": BASELINE_RESULT_CONTRACT_VERSION,
        "job_id": job_id,
        "upload_id": job_id,
        "dataset_id": dataset_id,
        "baseline_candidate_id": model_id,
        "established_baseline_id": model_id,
        "jobId": job_id,
        "datasetId": dataset_id,
        "baselineId": model_id,
        "workspacePath": f"/portfolio/{scope.workspace_id}/baselines/{model_id}",
        "createdAt": now,
        "portfolio_id": scope.workspace_id,
        "system_id": scope.workspace_id,
        "dataset_scope": scope.as_dict(),
        "workflow": workflow,
        "status": "COMPLETE",
        "processing_state": "complete",
        "filename": filename,
        "completed_at": now,
        "candidate_model": model,
        "baseline_suitability": suitability,
        "activation": dict(model["activation"]),
        "processing_trace": {
            "baseline_builder_ran": True,
            "sii_engine_invoked": False,
            "detection_pipeline_invoked": False,
            "evidence_pipeline_invoked": False,
            "replay_generated": False,
            "processing_time_seconds": round(time.perf_counter() - started, 6),
        },
    }
    assert_baseline_output_contract(result)
    persist_candidate(model, result, activate=auto_activate)
    persisted = verify_persisted_baseline(job_id)
    persisted_result = dict(persisted["result"])
    persisted_model = dict(persisted["model"])
    persisted_result["candidate_model"] = persisted_model
    persisted_result["activation"] = dict(persisted_model.get("activation") or {})
    return persisted_result
