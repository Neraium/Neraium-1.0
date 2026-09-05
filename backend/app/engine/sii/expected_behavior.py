from __future__ import annotations

import math
from copy import deepcopy
from hashlib import sha256
from statistics import median
from typing import Any

from app.engine.sii.common import (
    EPSILON,
    clamp,
    finite_number,
    median_absolute_deviation,
    quantile,
    timestamp_statistics,
)


from app.engine.sii.expected_rate_evidence import expected_rate_observations


MODEL_TYPE = "robust_theil_sen_linear_response"
MODEL_VERSION = "v2"
DEFAULT_CONFIG = {
    "minimum_training_samples": 12,
    "minimum_evaluation_samples": 5,
    "maximum_training_samples": 160,
    "maximum_models_per_target": 1,
    "residual_evidence_threshold": 3.0,
    "maximum_validation_relative_mad": 0.75,
    "candidate_lags_samples": (0, 1, 2, 3),
    "validation_fraction": 0.20,
    "minimum_validation_samples": 5,
}


def train_expected_behavior_models(
    *,
    rows: list[dict[str, Any]],
    relationship_memory: dict[str, Any],
    operating_mode: str,
    timestamp_column: str | None,
    source_run_id: str,
    training_time: str,
    config: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Fit inspectable single-predictor robust models with fixed settings."""

    cfg = {**DEFAULT_CONFIG, **(config or {})}
    output: dict[str, dict[str, Any]] = {}
    for relationship_id, relationship in sorted(relationship_memory.items()):
        if not isinstance(relationship, dict) or relationship.get("status") in {"inactive", "retired"}:
            continue
        modes = [str(item) for item in relationship.get("operating_modes_observed", [])]
        if operating_mode not in modes:
            continue
        strength = abs(float(relationship.get("current_strength") or 0.0))
        if strength < 0.45:
            continue
        source = str(relationship.get("source_signal") or "")
        target = str(relationship.get("target_signal") or "")
        if not source or not target:
            continue
        for predictor, response in ((source, target), (target, source)):
            pairs = _pairs(rows, predictor, response)
            model = _fit_model(
                pairs=pairs,
                predictor=predictor,
                target=response,
                relationship_id=relationship_id,
                operating_mode=operating_mode,
                timestamp_column=timestamp_column,
                rows=rows,
                source_run_id=source_run_id,
                training_time=training_time,
                config=cfg,
            )
            if model is not None:
                output[model["model_id"]] = model
    return dict(sorted(output.items()))


def evaluate_expected_behavior(
    *,
    active_model: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    operating_mode: str,
    data_quality: dict[str, Any],
    sensor_health: dict[str, Any],
    source_model_version: str | None,
    evaluation_time: str,
    timestamp_column: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    limitations: list[str] = []
    if not isinstance(active_model, dict):
        return _limited("active_behavioral_model_unavailable")
    models = active_model.get("expected_behavior_models")
    if not isinstance(models, dict) or not models:
        return _limited("no_active_expected_behavior_models")
    quality_ok, quality_reasons = _acceptable_data_quality(data_quality)
    if not quality_ok:
        return _limited("data_quality_not_acceptable", limitations=quality_reasons)

    health = _health_by_signal(sensor_health)
    candidates_by_target: dict[str, list[dict[str, Any]]] = {}
    for model in models.values():
        if not isinstance(model, dict) or not model.get("validation", {}).get("passed"):
            continue
        if str(model.get("operating_mode")) != operating_mode:
            continue
        candidates_by_target.setdefault(str(model.get("target_signal")), []).append(model)

    expected_values: list[dict[str, Any]] = []
    residual_evidence: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for target, candidates in sorted(candidates_by_target.items()):
        selected = sorted(
            candidates,
            key=lambda item: (
                -int(item.get("sample_support") or 0),
                str(item.get("model_id")),
            ),
        )[: int(cfg["maximum_models_per_target"])]
        for model in selected:
            predictor = str((model.get("predictor_signals") or [""])[0])
            reasons = []
            for signal in (target, predictor):
                if signal not in health:
                    reasons.append(f"sensor_health_unavailable:{signal}")
                elif health[signal] not in {"healthy", "good"}:
                    reasons.append(f"sensor_health_not_acceptable:{signal}:{health[signal]}")
            lag_samples = max(
                0,
                int(model.get("model_parameters", {}).get("lag_samples") or 0),
            )
            pairs = _lagged_pairs(rows, predictor, target, lag_samples)
            if len(pairs) < int(cfg["minimum_evaluation_samples"]):
                reasons.append("insufficient_predictor_coverage")
            if reasons:
                unavailable.append(
                    {
                        "target_signal": target,
                        "predictor_signals": [predictor],
                        "status": "limited",
                        "reasons": reasons,
                        "source_model_version": source_model_version,
                    }
                )
                limitations.extend(reasons)
                continue
            recent_pairs = pairs[-max(int(cfg["minimum_evaluation_samples"]), int(len(pairs) * 0.3)) :]
            predictor_value = float(median(pair[0] for pair in recent_pairs))
            observed_value = float(median(pair[1] for pair in recent_pairs))
            parameters = model["model_parameters"]
            expected_value = float(parameters["intercept"]) + float(parameters["slope"]) * predictor_value
            residual = observed_value - expected_value
            distribution = model.get("historical_residual_distribution", {})
            residual_distribution = list(distribution.get("quantile_values") or [])
            residual_scale = float(distribution.get("robust_scale") or 0.0)
            residual_center = float(distribution.get("center") or 0.0)
            interval_offsets = distribution.get("interval_offsets") or [-residual_scale, residual_scale]
            parameter_interval = _parameter_prediction_interval(parameters, predictor_value)
            expected_interval = [
                parameter_interval[0] + float(interval_offsets[0]),
                parameter_interval[1] + float(interval_offsets[1]),
            ]
            normalized = (residual - residual_center) / max(residual_scale, EPSILON)
            confidence = _expected_confidence(model, len(recent_pairs), health)
            item = {
                "status": "complete",
                "target_signal": target,
                "predictor_signals": [predictor],
                "predictor_values": {predictor: round(predictor_value, 6)},
                "operating_mode": operating_mode,
                "model_type": model.get("model_type"),
                "model_version": model.get("model_version"),
                "model_parameters": deepcopy(parameters),
                "training_window": deepcopy(model.get("training_window")),
                "sample_support": int(model.get("sample_support") or 0),
                "evaluation_sample_support": len(recent_pairs),
                "historical_support_duration": model.get("historical_support_duration"),
                "expected_value": round(expected_value, 6),
                "expected_interval": [
                    round(expected_interval[0], 6),
                    round(expected_interval[1], 6),
                ],
                "observed_value": round(observed_value, 6),
                "residual": round(residual, 6),
                "normalized_residual": round(normalized, 6),
                "historical_residual_distribution": {
                    **deepcopy(model.get("historical_residual_distribution", {})),
                    "quantile_values": residual_distribution,
                },
                "confidence": confidence,
                "uncertainty": {
                    "residual_scale": round(residual_scale, 6),
                    "residual_center": round(residual_center, 6),
                    "data_uncertainty": {
                        "evaluation_sample_support": len(recent_pairs),
                        "predictor_coverage_factor": round(clamp(len(recent_pairs) / 20.0), 6),
                    },
                    "model_uncertainty": {
                        "slope_interval": deepcopy(parameters.get("slope_interval")),
                        "intercept_interval": deepcopy(parameters.get("intercept_interval")),
                        "parameter_only_prediction_interval": [
                            round(parameter_interval[0], 6),
                            round(parameter_interval[1], 6),
                        ],
                        "validation": deepcopy(model.get("validation", {})),
                    },
                    "relationship_uncertainty": {
                        "source_relationships": list(model.get("source_relationships") or []),
                        "lag_samples": lag_samples,
                        "lag_seconds": parameters.get("lag_seconds"),
                    },
                    "not_probability": True,
                    "interpretation": "Expected intervals combine empirical robust residual bounds with inspectable Theil-Sen parameter ranges; they are not probability intervals.",
                },
                "limitations": list(model.get("limitations") or []),
                "source_relationships": list(model.get("source_relationships") or []),
                "source_model_version": source_model_version,
                "processing_trace": {
                    "model_id": model.get("model_id"),
                    "evaluation_time": evaluation_time,
                    "selection_method": "highest_sample_support_then_model_id",
                    "prediction_method": "median_recent_lag_aligned_predictor_response",
                    "lag_samples": lag_samples,
                    "causal_interpretation": False,
                },
            }
            item["observations"] = expected_rate_observations(
                rows, predictor=predictor, target=target, parameters=parameters,
                timestamp_column=timestamp_column,
            )
            item["max_gap_seconds"] = cfg.get("max_gap_seconds", 3600.0)
            item["observation_methodology"] = "validated_model_timestamp_aligned_response_v1"
            expected_values.append(item)
            if abs(normalized) >= float(cfg["residual_evidence_threshold"]):
                residual_evidence.append(
                    {
                        "evidence_id": f"expected_behavior:{model['model_id']}:{evaluation_time}",
                        "classification": "Supporting",
                        "originating_module": "expected_behavior",
                        "observation": "Observed behavior departed from the active model's robust expected interval.",
                        "target_signal": target,
                        "source_relationships": list(model.get("source_relationships") or []),
                        "normalized_residual": round(normalized, 6),
                        "expected_interval": [
                            round(expected_interval[0], 6),
                            round(expected_interval[1], 6),
                        ],
                        "observed_value": round(observed_value, 6),
                        "source_model_version": source_model_version,
                        "failure_claim": False,
                        "diagnosis": None,
                    }
                )

    status = "complete" if expected_values else "limited"
    if not expected_values and not unavailable:
        limitations.append("No validated model matched the current operating mode.")
    return {
        "status": status,
        "reason": None if status == "complete" else "no_valid_expected_behavior_evaluations",
        "models_evaluated": len(expected_values),
        "signals_evaluated": sorted({item["target_signal"] for item in expected_values}),
        "expected_values": expected_values,
        "residual_evidence": residual_evidence,
        "unavailable_models": unavailable,
        "uncertainty": {
            "not_probability": True,
            "residual_evidence_threshold": float(cfg["residual_evidence_threshold"]),
            "model_selection_count_per_target": int(cfg["maximum_models_per_target"]),
        },
        "limitations": list(dict.fromkeys(limitations)),
        "processing_trace": {
            "active_models_available": len(models),
            "mode_compatible_models": sum(len(items) for items in candidates_by_target.values()),
            "models_evaluated": len(expected_values),
            "residuals_generated": len(expected_values),
            "unexpected_residuals": len(residual_evidence),
            "opaque_models_used": False,
        },
    }


def _fit_model(
    *,
    pairs: list[tuple[float, float]],
    predictor: str,
    target: str,
    relationship_id: str,
    operating_mode: str,
    timestamp_column: str | None,
    rows: list[dict[str, Any]],
    source_run_id: str,
    training_time: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    if len(pairs) < int(config["minimum_training_samples"]):
        return None
    lag_candidates = _lag_candidates(config.get("candidate_lags_samples"))
    candidate_results = []
    for lag_samples in lag_candidates:
        lagged = _lagged_pairs(rows, predictor, target, lag_samples)
        validation_count = max(
            int(config["minimum_validation_samples"]),
            int(math.ceil(len(lagged) * float(config["validation_fraction"]))),
        )
        training_count = len(lagged) - validation_count
        if training_count < int(config["minimum_training_samples"]):
            continue
        fitted = _theil_sen_fit(
            lagged[:training_count],
            maximum=int(config["maximum_training_samples"]),
        )
        if fitted is None:
            continue
        validation_residuals = [
            y - (fitted["intercept"] + fitted["slope"] * x)
            for x, y in lagged[training_count:]
        ]
        validation_error = float(median(abs(value) for value in validation_residuals))
        validation_target = [value[1] for value in lagged[training_count:]]
        validation_scale = max(
            1.4826 * median_absolute_deviation(validation_target),
            EPSILON,
        )
        candidate_results.append(
            {
                "lag_samples": lag_samples,
                "validation_count": len(validation_residuals),
                "training_count": training_count,
                "validation_median_absolute_error": validation_error,
                "validation_relative_mad": validation_error / validation_scale,
            }
        )
    if not candidate_results:
        fitted = _theil_sen_fit(
            pairs,
            maximum=int(config["maximum_training_samples"]),
        )
        if fitted is None:
            return None
        selected = {
            "lag_samples": 0,
            "validation_count": 0,
            "training_count": len(pairs),
            "validation_median_absolute_error": None,
            "validation_relative_mad": None,
        }
    else:
        selected = min(
            candidate_results,
            key=lambda item: (
                float(item["validation_relative_mad"]),
                int(item["lag_samples"]),
            ),
        )
        selected_pairs = _lagged_pairs(
            rows,
            predictor,
            target,
            int(selected["lag_samples"]),
        )
        fitted = _theil_sen_fit(
            selected_pairs,
            maximum=int(config["maximum_training_samples"]),
        )
        if fitted is None:
            return None
        pairs = selected_pairs
    slope = float(fitted["slope"])
    intercept = float(fitted["intercept"])
    slopes = list(fitted["slopes"])
    intercepts = list(fitted["intercepts"])
    if not slopes:
        return None
    residuals = [y - (intercept + slope * x) for x, y in pairs]
    residual_center = float(median(residuals))
    residual_mad = median_absolute_deviation(residuals)
    robust_scale = max(1.4826 * residual_mad, EPSILON)
    target_values = [pair[1] for pair in pairs]
    target_scale = max(1.4826 * median_absolute_deviation(target_values), EPSILON)
    relative_mad = robust_scale / target_scale
    holdout_relative_mad = selected.get("validation_relative_mad")
    validation_passed = bool(
        math.isfinite(slope)
        and math.isfinite(intercept)
        and relative_mad <= float(config["maximum_validation_relative_mad"])
        and (
            holdout_relative_mad is None
            or float(holdout_relative_mad)
            <= float(config["maximum_validation_relative_mad"])
        )
    )
    model_seed = f"{operating_mode}|{predictor}|{target}|{relationship_id}"
    model_id = f"expected:{sha256(model_seed.encode('utf-8')).hexdigest()[:20]}"
    start = _timestamp(rows[0], timestamp_column) if rows else None
    end = _timestamp(rows[-1], timestamp_column) if rows else None
    interval_offsets = [quantile(residuals, 0.05), quantile(residuals, 0.95)]
    timestamp_profile = timestamp_statistics(rows, timestamp_column)
    median_interval = timestamp_profile.get("median_interval_seconds")
    lag_samples = int(selected["lag_samples"])
    lag_seconds = (
        round(float(median_interval) * lag_samples, 6)
        if median_interval is not None and timestamp_profile.get("reliable")
        else None
    )
    return {
        "model_id": model_id,
        "target_signal": target,
        "predictor_signals": [predictor],
        "operating_mode": operating_mode,
        "model_type": MODEL_TYPE,
        "model_version": MODEL_VERSION,
        "model_parameters": {
            "slope": round(slope, 9),
            "intercept": round(intercept, 9),
            "slope_interval": [
                round(quantile(slopes, 0.10), 9),
                round(quantile(slopes, 0.90), 9),
            ],
            "intercept_interval": [
                round(quantile(intercepts, 0.10), 9),
                round(quantile(intercepts, 0.90), 9),
            ],
            "lag_samples": lag_samples,
            "lag_seconds": lag_seconds,
            "fixed_settings": {
                "maximum_training_samples": int(config["maximum_training_samples"]),
                "pairwise_slope_aggregation": "median",
                "intercept_aggregation": "median",
                "lag_selection": "minimum_time_ordered_holdout_relative_median_absolute_error_then_smallest_lag",
            },
        },
        "training_window": {"start": start, "end": end, "source_run_id": source_run_id},
        "sample_support": len(pairs),
        "historical_support_duration": _duration_label(start, end),
        "historical_residual_distribution": {
            "method": "median_absolute_deviation_and_empirical_quantiles",
            "center": round(residual_center, 6),
            "robust_scale": round(robust_scale, 6),
            "quantiles": [0.05, 0.25, 0.5, 0.75, 0.95],
            "quantile_values": [round(quantile(residuals, item), 6) for item in (0.05, 0.25, 0.5, 0.75, 0.95)],
            "interval_offsets": [round(float(item), 6) for item in interval_offsets],
        },
        "validation": {
            "passed": validation_passed,
            "method": "time_ordered_holdout_and_relative_robust_residual_scale",
            "relative_residual_mad": round(relative_mad, 6),
            "holdout_relative_mad": (
                round(float(holdout_relative_mad), 6)
                if holdout_relative_mad is not None
                else None
            ),
            "holdout_median_absolute_error": (
                round(float(selected["validation_median_absolute_error"]), 6)
                if selected["validation_median_absolute_error"] is not None
                else None
            ),
            "training_sample_count": int(selected["training_count"]),
            "validation_sample_count": int(selected["validation_count"]),
            "lag_candidates": [
                {
                    **item,
                    "validation_median_absolute_error": round(
                        float(item["validation_median_absolute_error"]), 6
                    ),
                    "validation_relative_mad": round(
                        float(item["validation_relative_mad"]), 6
                    ),
                }
                for item in candidate_results
            ],
            "maximum_relative_residual_mad": float(config["maximum_validation_relative_mad"]),
        },
        "confidence": {
            "not_probability": True,
            "sample_sufficiency": round(clamp(len(pairs) / 60.0), 6),
            "residual_stability": round(clamp(1.0 - relative_mad), 6),
        },
        "limitations": [
            "This transparent association model estimates expected response; it does not establish causal direction.",
            "Lag selection is a deterministic predictive-alignment comparison and is not causal evidence.",
            "The robust empirical and parameter interval is not a probability interval.",
        ],
        "source_relationships": [relationship_id],
        "source_run_id": source_run_id,
        "trained_at": training_time,
    }


def _pairs(rows: list[dict[str, Any]], predictor: str, target: str) -> list[tuple[float, float]]:
    output = []
    for row in rows:
        left = finite_number(row.get(predictor))
        right = finite_number(row.get(target))
        if left is not None and right is not None:
            output.append((left, right))
    return output


def _lagged_pairs(
    rows: list[dict[str, Any]],
    predictor: str,
    target: str,
    lag_samples: int,
) -> list[tuple[float, float]]:
    lag = max(0, int(lag_samples))
    output = []
    for target_index in range(lag, len(rows)):
        predictor_value = finite_number(rows[target_index - lag].get(predictor))
        target_value = finite_number(rows[target_index].get(target))
        if predictor_value is not None and target_value is not None:
            output.append((predictor_value, target_value))
    return output


def _lag_candidates(value: Any) -> list[int]:
    candidates = value if isinstance(value, (list, tuple)) else (0,)
    output = sorted(
        {
            max(0, int(item))
            for item in candidates
            if isinstance(item, (int, float)) and math.isfinite(float(item))
        }
    )
    return output or [0]


def _theil_sen_fit(
    pairs: list[tuple[float, float]],
    *,
    maximum: int,
) -> dict[str, Any] | None:
    sampled = _bounded_sample(pairs, maximum)
    slopes = []
    for left_index, (x_left, y_left) in enumerate(sampled):
        for x_right, y_right in sampled[left_index + 1 :]:
            delta = x_right - x_left
            if abs(delta) > EPSILON:
                slopes.append((y_right - y_left) / delta)
    if not slopes:
        return None
    slope = float(median(slopes))
    intercepts = [y - slope * x for x, y in sampled]
    return {
        "slope": slope,
        "intercept": float(median(intercepts)),
        "slopes": slopes,
        "intercepts": intercepts,
    }


def _parameter_prediction_interval(
    parameters: dict[str, Any], predictor_value: float
) -> tuple[float, float]:
    slopes = parameters.get("slope_interval")
    intercepts = parameters.get("intercept_interval")
    if not isinstance(slopes, list) or len(slopes) != 2:
        slopes = [parameters.get("slope"), parameters.get("slope")]
    if not isinstance(intercepts, list) or len(intercepts) != 2:
        intercepts = [parameters.get("intercept"), parameters.get("intercept")]
    candidates = [
        float(intercept) + float(slope) * predictor_value
        for intercept in intercepts
        for slope in slopes
        if finite_number(intercept) is not None and finite_number(slope) is not None
    ]
    expected = float(parameters["intercept"]) + float(parameters["slope"]) * predictor_value
    return (
        min(candidates, default=expected),
        max(candidates, default=expected),
    )


def _bounded_sample(pairs: list[tuple[float, float]], maximum: int) -> list[tuple[float, float]]:
    if len(pairs) <= maximum:
        return list(pairs)
    indices = sorted({round(index * (len(pairs) - 1) / (maximum - 1)) for index in range(maximum)})
    return [pairs[index] for index in indices]


def _acceptable_data_quality(data_quality: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    if str(data_quality.get("readiness") or "").lower() == "not_ready":
        reasons.append("data_quality_readiness_not_ready")
    rating = str((data_quality.get("data_confidence") or {}).get("rating") or "").lower()
    if rating in {"low", "not_reliable"}:
        reasons.append(f"data_confidence_{rating}")
    return not reasons, reasons


def _health_by_signal(sensor_health: dict[str, Any]) -> dict[str, str]:
    return {
        str(item.get("signal")): str(item.get("health") or "unavailable").lower()
        for item in sensor_health.get("signals", [])
        if isinstance(item, dict) and item.get("signal")
    }


def _expected_confidence(
    model: dict[str, Any], evaluation_samples: int, health: dict[str, str]
) -> dict[str, Any]:
    target = str(model.get("target_signal"))
    predictors = [str(item) for item in model.get("predictor_signals", [])]
    factors = {
        "historical_sample_sufficiency": round(clamp(int(model.get("sample_support") or 0) / 60.0), 6),
        "current_predictor_coverage": round(clamp(evaluation_samples / 20.0), 6),
        "residual_stability": round(
            clamp(1.0 - float(model.get("validation", {}).get("relative_residual_mad") or 1.0)), 6
        ),
        "sensor_health_consistency": 1.0 if all(health.get(item) in {"healthy", "good"} for item in [target, *predictors]) else 0.0,
        "operating_mode_consistency": 1.0,
    }
    compatibility = sum(factors.values()) / len(factors)
    return {
        "compatibility": round(compatibility, 6),
        "not_probability": True,
        "factors": factors,
        "method": "unweighted_deterministic_factor_mean_for_compatibility_display",
    }


def _limited(reason: str, limitations: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": "limited",
        "reason": reason,
        "models_evaluated": 0,
        "signals_evaluated": [],
        "expected_values": [],
        "residual_evidence": [],
        "unavailable_models": [],
        "uncertainty": {"not_probability": True},
        "limitations": list(limitations or [reason]),
        "processing_trace": {
            "models_evaluated": 0,
            "residuals_generated": 0,
            "unexpected_residuals": 0,
            "opaque_models_used": False,
        },
    }


def _timestamp(row: dict[str, Any], timestamp_column: str | None) -> str | None:
    if not timestamp_column:
        return None
    value = row.get(timestamp_column)
    return str(value) if value is not None else None


def _duration_label(start: str | None, end: str | None) -> str | None:
    if not start or not end:
        return None
    try:
        from datetime import datetime

        seconds = max(0.0, (datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds())
        return f"PT{round(seconds, 6)}S"
    except (TypeError, ValueError):
        return None
