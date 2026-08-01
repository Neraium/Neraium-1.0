from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.services import finding_classification, pilot_assessment, relationship_baselines, upload_evidence


def approved_baseline_signals(baseline: dict[str, Any]) -> set[str]:
    schema = baseline.get("telemetry_schema") if isinstance(baseline, dict) else {}
    return {
        str(signal)
        for signal in (schema or {}).get("numeric_columns", [])
        if str(signal).strip()
    }


def eligible_expected_models(
    baseline: dict[str, Any],
    available_signals: set[str],
) -> list[dict[str, Any]]:
    models = []
    for model in baseline.get("expected_behavior_models", []):
        if not isinstance(model, dict):
            continue
        predictor = str(model.get("predictor") or "")
        response = str(model.get("response") or "")
        validation = model.get("validation") or {}
        if (
            model.get("mode_id") == "all_operation"
            and validation.get("accepted") is True
            and predictor in available_signals
            and response in available_signals
        ):
            models.append(model)
    return sorted(models, key=lambda item: str(item.get("model_id") or ""))


def analysis_ready_expected_models(
    baseline: dict[str, Any],
    window: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return expected models with enough paired, varying live observations."""

    models = eligible_expected_models(
        baseline,
        set(window.get("signals_included") or []),
    )
    rows = window.get("rows") or []
    ready: list[dict[str, Any]] = []
    for model in models:
        predictor = str(model["predictor"])
        response = str(model["response"])
        paired = [
            (row.get(predictor), row.get(response))
            for row in rows
            if row.get(predictor) is not None and row.get(response) is not None
        ]
        if len(paired) < pilot_assessment.MIN_MODE_SAMPLES:
            continue
        predictor_values = {float(left) for left, _ in paired}
        response_values = {float(right) for _, right in paired}
        if len(predictor_values) < 2 or len(response_values) < 2:
            continue
        ready.append(model)
    return ready


def _relationship_edge(baseline: dict[str, Any], model: dict[str, Any]) -> dict[str, Any] | None:
    graph = baseline.get("relationship_graph") or {}
    for edge in graph.get("edges", []):
        if (
            isinstance(edge, dict)
            and edge.get("mode_id") == model.get("mode_id")
            and edge.get("source") == model.get("predictor")
            and edge.get("target") == model.get("response")
        ):
            return edge
    return None


def _baseline_fit(baseline: dict[str, Any], model: dict[str, Any]) -> dict[str, float] | None:
    edge = _relationship_edge(baseline, model)
    parameters = model.get("parameters") or {}
    validation = model.get("validation") or {}
    try:
        correlation = float((edge or {}).get("correlation"))
        slope = float(parameters["slope"])
        intercept = float(parameters["intercept"])
        residual_scale = max(
            float(validation.get("rmse") or 0),
            float(validation.get("mae") or 0),
            1e-9,
        )
        sample_count = int(model.get("training_samples") or 0) + int(model.get("validation_samples") or 0)
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (correlation, slope, intercept, residual_scale)):
        return None
    return {
        "correlation": correlation,
        "slope": slope,
        "intercept": intercept,
        "residual_scale": residual_scale,
        "sample_count": sample_count,
    }


def _comparison_frame(window: dict[str, Any]) -> pd.DataFrame:
    frame = pd.DataFrame(window.get("rows") or [])
    if frame.empty or "timestamp" not in frame:
        return pd.DataFrame()
    frame["__timestamp"] = pd.to_datetime(frame.pop("timestamp"), utc=True, errors="coerce")
    frame = frame.dropna(subset=["__timestamp"]).sort_values("__timestamp", kind="mergesort")
    frame["__source_row"] = range(1, len(frame) + 1)
    frame["__mode"] = "all_operation"
    for signal in window.get("signals_included") or []:
        frame[signal] = pd.to_numeric(frame.get(signal), errors="coerce")
    return frame


def _relationship_evidence(
    *,
    model: dict[str, Any],
    baseline_fit: dict[str, float],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    current_fit = evaluation["current_fit"]
    correlation_delta = float(evaluation["correlation_delta"])
    baseline_samples = int(baseline_fit["sample_count"])
    recent_samples = int(current_fit["sample_count"])
    confidence = relationship_baselines._confidence_score(
        baseline_samples,
        recent_samples,
        abs(correlation_delta),
    )
    change_type = relationship_baselines._relationship_change_type(
        float(baseline_fit["correlation"]),
        float(current_fit["correlation"]),
    )
    return {
        "relationship_identity": str(model["model_id"]),
        "columns": [str(model["predictor"]), str(model["response"])],
        "baseline_correlation": round(float(baseline_fit["correlation"]), 6),
        "recent_correlation": round(float(current_fit["correlation"]), 6),
        "correlation_delta": round(correlation_delta, 6),
        "absolute_correlation_change": round(abs(correlation_delta), 6),
        "baseline_slope": round(float(baseline_fit["slope"]), 8),
        "recent_slope": round(float(current_fit["slope"]), 8),
        "slope_change": (
            float(evaluation["slope_change"])
            if math.isfinite(float(evaluation["slope_change"]))
            else None
        ),
        "baseline_sample_size": baseline_samples,
        "recent_sample_size": recent_samples,
        "confidence_score": confidence,
        "change_type": change_type,
        "persistence": evaluation["persistence"],
    }


def _evidence_result(
    *,
    run_id: str,
    system_id: str,
    window: dict[str, Any],
    relationship: dict[str, Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    left, right = relationship["columns"]
    persistence = relationship["persistence"]
    source_rows = [
        {"window": "current_start", "timestamp": window["window_start"]},
        {"window": "current_end", "timestamp": window["window_end"]},
    ]
    relationship_payload = {
        **relationship,
        "source_rows": source_rows,
        "evidence_refs": [
            {
                "column": column,
                "baseline_window": {
                    "baseline_reference": relationship["relationship_identity"],
                    "samples": relationship["baseline_sample_size"],
                },
                "recent_window": {
                    "start": window["window_start"],
                    "end": window["window_end"],
                    "samples": relationship["recent_sample_size"],
                },
                "source_rows": source_rows,
            }
            for column in (left, right)
        ],
    }
    return {
        "run_id": run_id,
        "row_count": window["rows_included"],
        "column_count": len(window["signals_included"]) + 1,
        "columns": ["timestamp", *window["signals_included"]],
        "created_at": window["window_end"],
        "completed_at": window["window_end"],
        "last_processed_at": window["window_end"],
        "timestamp_profile": {
            "first_timestamp": window["window_start"],
            "last_timestamp": window["window_end"],
        },
        "data_quality": {"warnings": list(window.get("warnings") or [])},
        "baseline_analysis": {"top_relationship_changes": [relationship_payload]},
        "sii_intelligence": {
            "primary_room": system_id,
            "facility_state": classification.get("label"),
            "confidence": relationship.get("confidence_score"),
            "observed_persistence": persistence,
            "supporting_evidence": [
                (
                    f"{left} and {right} changed from their approved baseline "
                    f"with correlation delta {relationship['correlation_delta']}."
                )
            ],
        },
    }


def analyze_live_window(
    *,
    run_id: str,
    system_id: str,
    baseline: dict[str, Any],
    window: dict[str, Any],
) -> dict[str, Any]:
    """Adapt approved baseline models and a live window to existing intelligence."""

    frame = _comparison_frame(window)
    models = eligible_expected_models(baseline, set(window.get("signals_included") or []))
    detections: list[dict[str, Any]] = []
    evaluated_relationships: list[str] = []
    aligned_relationships: list[str] = []

    for model in models:
        baseline_fit = _baseline_fit(baseline, model)
        if baseline_fit is None:
            continue
        identity = str(model["model_id"])
        evaluation = pilot_assessment.evaluate_relationship_against_baseline(
            frame,
            str(model["predictor"]),
            str(model["response"]),
            baseline_fit,
        )
        if not evaluation["evaluated"]:
            continue
        evaluated_relationships.append(identity)
        if not evaluation["changed"]:
            aligned_relationships.append(identity)
            continue

        relationship = _relationship_evidence(
            model=model,
            baseline_fit=baseline_fit,
            evaluation=evaluation,
        )
        score_payload = relationship_baselines.score_relationship_importance(
            relationship["columns"],
            relationship,
            telemetry_signal_catalog=(baseline.get("telemetry_schema") or {}).get("signal_catalog"),
        )
        classification = finding_classification.classify_finding(
            data_confidence={
                "rating": "high" if window["overall_coverage"] >= 80 else "low",
                "reasons": [],
            },
            sensor_health=(baseline.get("sensor_health") or {}).get("signals", []),
            operating_mode={
                "match": "strong",
                "confidence": "limited",
                "reasons": ["The approved all-operation expected model was used."],
                "differences": [],
                "known_operational_change": False,
            },
            persistence=relationship["persistence"],
            relationship_evidence=relationship,
        )
        generated = upload_evidence.build_evidence_record_from_result(
            run_id=run_id,
            filename=f"live:{system_id}",
            source_type="live_telemetry",
            result=_evidence_result(
                run_id=run_id,
                system_id=system_id,
                window=window,
                relationship=relationship,
                classification=classification,
            ),
            created_at=window["window_end"],
            completed_at=window["window_end"],
            status="completed",
            initiated_by="live_analysis_worker",
            rows_received=window["rows_included"],
            rows_accepted=window["rows_included"],
            rows_rejected=0,
        )
        detections.append(
            {
                **relationship,
                "classification": classification,
                "severity_score": score_payload["relationship_importance_score"],
                "score": score_payload,
                "latest_evidence": generated,
            }
        )

    return {
        "engine_adapter": "approved_behavioral_model_relationship_adapter_v1",
        "relationship_entry_point": (
            "app.services.pilot_assessment.evaluate_relationship_against_baseline"
        ),
        "persistence_entry_point": (
            "app.services.pilot_assessment.evaluate_relationship_against_baseline"
        ),
        "scoring_entry_point": "app.services.relationship_baselines.score_relationship_importance",
        "classification_entry_point": "app.services.finding_classification.classify_finding",
        "evidence_entry_point": "app.services.upload_evidence.build_evidence_record_from_result",
        "evaluated_relationships": evaluated_relationships,
        "baseline_aligned_relationships": aligned_relationships,
        "detections": detections,
    }

