from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Callable

from app.engine.sii_engine import evaluate_sii
from app.services.cultivation_mapping import map_cultivation_columns
from app.services.driver_attribution import build_driver_attribution
from app.services.operator_report import build_operator_report
from app.services.sii_intelligence import build_upload_intelligence
from app.services.sii_runner import RUNNER_MODULE
from app.services.telemetry_confidence import apply_telemetry_confidence_adjustment


UPLOAD_TEMPORAL_MAX_ROWS = 2048


def _inline_replay_generation_enabled() -> bool:
    configured = os.getenv("NERAIUM_INLINE_REPLAY_GENERATION")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("PYTEST_CURRENT_TEST") is not None


def _empty_optional_replay(job_id: str, reason: str) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "run_id": job_id,
        "upload_id": job_id,
        "source": "not_generated",
        "replay_ready": False,
        "frame_count": 0,
        "meta": {"frame_count": 0, "optional": True, "reason": reason},
        "timeline": [],
    }


def run_structural_analysis_pipeline(
    *,
    job_id: str,
    filename: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    row_count_total: int,
    matrix_rows_for_profiles: list[list[Any]],
    numeric_profiles: list[dict[str, Any]],
    room_summary: dict[str, Any],
    room_intelligence: list[dict[str, Any]],
    room_names: list[str],
    overall_urgency: str,
    telemetry_profile: str,
    telemetry_profile_confidence: str,
    telemetry_profile_signals: list[str],
    operational_profile: str,
    operational_profile_confidence: str,
    operational_profile_signals: list[str],
    operational_modality: str,
    ingestion_report: dict[str, Any] | None,
    chunk_count: int,
    memory_estimate_bytes: int,
    processing_started_at: float | None,
    build_replay: Callable[..., dict[str, Any]],
    minimal_replay: Callable[..., dict[str, Any]],
    build_upload_engine_result: Callable[..., dict[str, Any]],
    stage_notifier: Callable[..., None],
    active_baseline_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stage_notifier(job_id, stage="building_baseline", progress=60, label="Identifying systems...")
    matrix_rows = matrix_rows_for_profiles
    ingestion_report = ingestion_report or {}
    now = datetime.now(timezone.utc).isoformat()

    from app.services.telemetry_normalization import build_normalization_report

    normalization_report = build_normalization_report(
        rows=rows,
        numeric_columns=numeric_columns,
        timestamp_column=timestamp_column,
        source_id=filename or job_id,
    )
    cultivation_mapping = map_cultivation_columns(columns)
    room_assessments = {
        item["room"]: dict(item)
        for item in room_intelligence
        if item.get("room")
    }
    primary_room_assessment = next(
        (
            item
            for item in room_intelligence
            if item.get("room") == (room_names[0] if room_names else "")
        ),
        room_intelligence[0] if room_intelligence else {},
    )

    initial_processing_trace = {
        "sii_pipeline_ran": True,
        "replay_frame_count": 0,
        "rows_processed": row_count_total,
        "columns_analyzed": len(numeric_columns),
        "normalization_layer_ran": True,
        "normalization_window_suppressed": bool(normalization_report.get("window_suppressed")),
        "normalization_source_status": normalization_report.get("status"),
        "active_baseline_loaded": isinstance(active_baseline_model, dict),
        "active_baseline_model_id": (active_baseline_model or {}).get("model_id"),
        "active_baseline_version": (active_baseline_model or {}).get("version"),
    }

    def compatibility_context_factory(context: dict[str, Any]) -> dict[str, Any]:
        baseline_analysis = context.get("baseline_analysis") or {}
        relationship_model = context.get("relationship_model") or {}
        data_quality = context.get("data_quality") or {}
        timestamp_profile = context.get("timestamp_profile") or {}
        engine_result = build_upload_engine_result(
            baseline_analysis=baseline_analysis,
            relationship_model=relationship_model,
            cultivation_mapping=cultivation_mapping,
            overall_urgency=overall_urgency,
        )
        driver_attribution = build_driver_attribution(
            {
                "room": primary_room_assessment.get("room")
                or (room_names[0] if room_names else "State Group A"),
                "state": primary_room_assessment.get("room_state") or "Baseline-aligned",
                "severity": (
                    "action"
                    if overall_urgency == "unstable"
                    else "review"
                    if overall_urgency == "review"
                    else "info"
                ),
            },
            {
                "timestamp_profile": timestamp_profile,
                "data_quality": data_quality,
                "numeric_profiles": numeric_profiles,
                "cultivation_mapping": cultivation_mapping,
                "columns": columns,
                "telemetry_profile": telemetry_profile,
                "telemetry_profile_signals": telemetry_profile_signals,
                "operational_signal_profile": operational_profile,
                "operational_signal_profile_signals": operational_profile_signals,
            },
            {
                "baseline_analysis": baseline_analysis,
                "cultivation_mapping": cultivation_mapping,
            },
            engine_result,
        )
        primary_room = (
            driver_attribution.get("room")
            or (room_names[0] if room_names else "Uploaded telemetry")
        )
        return {
            "engine_result": engine_result,
            "driver_attribution": driver_attribution,
            "primary_room": primary_room,
            "processing_trace": initial_processing_trace,
        }

    stage_notifier(
        job_id,
        stage="scoring_drift_relationships",
        progress=72,
        label="Mapping relationships...",
    )
    sii_result = evaluate_sii(
        columns=columns,
        rows=rows,
        numeric_profiles=numeric_profiles,
        timestamp_column=timestamp_column,
        config={
            "numeric_columns": numeric_columns,
            "row_count_total": row_count_total,
            "header_present": bool(ingestion_report.get("header_present", True)),
            "ingestion_report": ingestion_report,
            "normalization_report": normalization_report,
            "temporal_config": {"max_rows": UPLOAD_TEMPORAL_MAX_ROWS},
            "additional_warnings": [
                *list(ingestion_report.get("warnings") or []),
                *list(cultivation_mapping.get("warnings") or []),
            ],
            "compatibility_context_factory": compatibility_context_factory,
            "processing_trace": initial_processing_trace,
            "source_run_id": job_id,
            "active_behavioral_baseline": active_baseline_model,
            "active_baseline_loaded": isinstance(active_baseline_model, dict),
            "infrastructure_identity": {
                key: ingestion_report.get(key)
                for key in (
                    "organization_id",
                    "facility_id",
                    "system_id",
                    "subsystem_id",
                    "equipment_group_id",
                    "configured_model_id",
                )
                if ingestion_report.get(key)
            },
        },
    )
    compatibility = sii_result.get("compatibility") or {}
    baseline_analysis = compatibility.get("baseline_analysis") or {}
    relationship_model = compatibility.get("relationship_model") or {}
    telemetry_signal_catalog = compatibility.get("telemetry_signal_catalog") or {}
    data_quality = compatibility.get("data_quality") or {}
    timestamp_profile = compatibility.get("timestamp_profile") or {}
    engine_result = compatibility.get("engine_result") or {}
    driver_attribution = compatibility.get("driver_attribution") or {}
    runner_result = compatibility.get("sii_runner_result") or {}
    temporal_math = (
        compatibility.get("temporal_analysis")
        or sii_result.get("temporal_analysis")
        or {}
    )
    engine_result["temporal_math"] = temporal_math

    baseline_reliable = (
        baseline_analysis.get("baseline_window_rows", 0) >= 5
        and baseline_analysis.get("recent_window_rows", 0) >= 1
        and baseline_analysis.get("columns_analyzed", 0) >= 1
        and not normalization_report.get("window_suppressed")
    )
    reliability_warning = None
    if not baseline_reliable:
        reliability_warning = "Insufficient baseline: SII findings are not reliable enough to show."

    replay = _empty_optional_replay(job_id, "inline_replay_disabled")
    if _inline_replay_generation_enabled():
        try:
            replay = (
                minimal_replay(
                    columns,
                    rows,
                    timestamp_column,
                    numeric_columns,
                    job_id,
                    relationship_model,
                )
                if len(rows) < 20 or not timestamp_column or len(numeric_columns) < 3
                else build_replay(
                    rows,
                    timestamp_column,
                    numeric_columns,
                    job_id,
                    relationship_model,
                )
            )
            if not replay.get("timeline"):
                replay = minimal_replay(
                    columns,
                    rows,
                    timestamp_column,
                    numeric_columns,
                    job_id,
                    relationship_model,
                )
        except Exception as exc:
            replay = _empty_optional_replay(
                job_id,
                f"inline_replay_failed:{exc.__class__.__name__}",
            )

    stage_notifier(job_id, stage="building_fingerprint", progress=84, label="Building fingerprint...")
    frame_count = len(replay.get("timeline", []))
    operator_report = build_operator_report(
        data_quality,
        timestamp_profile,
        numeric_profiles,
        baseline_analysis,
        cultivation_mapping,
    )
    sii_intelligence = build_upload_intelligence(
        filename=filename,
        row_count=row_count_total,
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
        operator_report=operator_report,
        timestamp_profile=timestamp_profile,
        room_summary=room_summary,
        room_assessments=room_assessments,
        source_metadata={
            "telemetry_profile": telemetry_profile,
            "telemetry_profile_confidence": telemetry_profile_confidence,
            "telemetry_profile_signals": telemetry_profile_signals,
            "telemetry_modality": "continuous",
            "operational_signal_profile": operational_profile,
            "operational_signal_profile_confidence": operational_profile_confidence,
            "operational_signal_profile_signals": operational_profile_signals,
            "operational_signal_modality": operational_modality,
            "telemetry_integrity": normalization_report.get("source_integrity", {}),
        },
    )
    sii_intelligence["runner_module"] = RUNNER_MODULE
    sii_intelligence["replay_timeline"] = replay
    sii_intelligence["telemetry_integrity"] = normalization_report
    sii_intelligence["temporal_math"] = temporal_math
    sii_intelligence = apply_telemetry_confidence_adjustment(
        sii_intelligence,
        data_quality=data_quality,
    )

    processing_time_seconds = round(
        max(0.0, time.perf_counter() - (processing_started_at or time.perf_counter())),
        6,
    )
    processing_trace = {
        **dict(sii_result.get("processing_trace") or {}),
        "sii_pipeline_ran": True,
        "sii_completed": sii_result.get("status") in {"complete", "limited"},
        "replay_frame_count": frame_count,
        "rows_processed": row_count_total,
        "columns_analyzed": len(numeric_columns),
        "normalization_layer_ran": True,
        "normalization_window_suppressed": bool(normalization_report.get("window_suppressed")),
        "normalization_source_status": normalization_report.get("status"),
        "temporal_math_ran": (
            temporal_math.get("engine", {}).get("name") == "temporal_math_engine"
        ),
        "temporal_math_status": temporal_math.get("status", "complete"),
        "temporal_math_reason": temporal_math.get("reason"),
        "temporal_math_columns_used": list(temporal_math.get("columns_used") or []),
        "temporal_math_baseline_rows": int(temporal_math.get("baseline_rows") or 0),
        "temporal_math_active_rows": int(temporal_math.get("active_rows") or 0),
        "sii_confidence_adjusted_for_telemetry": bool(
            sii_intelligence.get("telemetry_confidence_adjusted")
        ),
        "processing_time_seconds": processing_time_seconds,
        "completed_at": now,
        "sii_runner_ran": bool(runner_result.get("runner_used")),
        "sii_vector_rows_processed": int(runner_result.get("rows_processed") or 0),
        "sii_rows_received": int(runner_result.get("rows_received") or row_count_total),
        "sii_rows_excluded": int(runner_result.get("rows_excluded") or 0),
        "sii_columns_used": list(runner_result.get("columns_used") or []),
    }
    sii_result["processing_trace"] = processing_trace

    stage_notifier(
        job_id,
        stage="generating_findings_evidence",
        progress=90,
        label="Generating insights...",
    )
    stage_notifier(job_id, stage="saving_result", progress=95, label="Saving result...")
    latest_runner_state = runner_result.get("latest_state")
    return {
        "sii_result": sii_result,
        "baseline_analysis": baseline_analysis,
        "telemetry_signal_catalog": telemetry_signal_catalog,
        "baseline_reliable": baseline_reliable,
        "cultivation_mapping": cultivation_mapping,
        "data_quality": data_quality,
        "driver_attribution": driver_attribution,
        "engine_result": engine_result,
        "frame_count": frame_count,
        "latest_runner_state": latest_runner_state,
        "now": now,
        "operator_report": operator_report,
        "processing_time_seconds": processing_time_seconds,
        "processing_trace": processing_trace,
        "relationship_model": relationship_model,
        "reliability_warning": reliability_warning,
        "replay": replay,
        "room_assessments": room_assessments,
        "runner_result": runner_result,
        "sii_intelligence": sii_intelligence,
        "temporal_math": temporal_math,
        "timestamp_profile": timestamp_profile,
        "normalization_report": normalization_report,
        "chunk_count": chunk_count,
        "memory_estimate_bytes": memory_estimate_bytes,
    }
