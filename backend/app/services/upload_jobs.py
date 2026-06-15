from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
from pathlib import Path
from typing import Any
from app.services.baseline_analysis import build_baseline_analysis
from app.services.cultivation_mapping import map_cultivation_columns
from app.services.data_quality import build_data_quality, detect_timestamp_column, parse_numeric_value, parse_timestamp, profile_numeric_columns, profile_timestamps
from app.services.driver_attribution import build_driver_attribution
from app.services.operator_report import build_operator_report
from app.services.notifications import dispatch_observation_notification
from app.services.sii_intelligence import build_upload_intelligence
from app.services.sii_runner import RUNNER_MODULE, run_sii_runner, read_latest_sii_state
from app.services.runtime_db import claim_next_upload_job, mark_queue_job_failed, upsert_upload_job, read_upload_job, enqueue_upload_job, complete_upload_queue_job, touch_upload_queue_job
from app.services.relationship_baselines import build_relationship_baseline as _build_relationship_baseline
from app.services.upload_completion import build_partial_upload_artifacts
from app.services.upload_evidence import build_evidence_record_from_result, build_traceability_packet
from app.services.upload_parser import json_payload_to_csv_text
from app.services.upload_persistence import read_upload_history as read_upload_history_from_runtime
from app.services.upload_persistence import summarize_result as summarize_result_payload
from app.services.upload_queue_lifecycle import UploadQueueLifecycleService
from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE
from app.services.upload_state_repository import (
    clear_reset_block_persisted,
    configure_runtime_dir as configure_runtime_state_dir,
    persist_latest_upload_state,
    read_current_upload_result,
    read_latest_upload_record,
    read_latest_upload_result,
    read_latest_upload_summary,
    read_local_json as repository_read_local_json,
    read_replay_payload as repository_read_replay_payload,
    read_shared_state as repository_read_shared_state,
    read_upload_result_by_job_id,
    read_upload_status as repository_read_upload_status,
    reset_block_persisted_active,
    reset_upload_state,
    shared_state_configured,
    upload_state_backend,
    warm_latest_upload_cache,
    write_upload_completion as repository_write_upload_completion,
    write_upload_status_progress as repository_write_upload_status_progress,
    write_latest_upload_record as repository_write_latest_upload_record,
    write_latest_upload_result as repository_write_latest_upload_result,
    write_latest_upload_summary as repository_write_latest_upload_summary,
    write_local_json as repository_write_local_json,
    write_shared_state as repository_write_shared_state,
    write_upload_result,
    write_upload_status,
)
from app.services.upload_replay import build_replay, detect_numeric_columns, detect_timestamp_column as detect_replay_timestamp_column, minimal_replay, population_std, to_float
from app.services.upload_validator import detect_delimiter, looks_like_header, normalized_columns, row_tokens, stream_csv_snapshot
from app.services.upload_state import (
    build_empty_latest_upload_record,
    build_session_scope,
    has_active_session_artifact,
)

RUNTIME_DIR = Path("backend/runtime")
UPLOAD_DIR = RUNTIME_DIR / "uploads"
JOB_DIR = RUNTIME_DIR / "upload_jobs"
LEGACY_JOB_DIR = RUNTIME_DIR / "jobs"
JOBS = UPLOAD_RUNTIME_STATE.jobs
LATEST_UPLOAD_CACHE = UPLOAD_RUNTIME_STATE.latest_upload_cache
MAX_ANALYSIS_ROWS = int(os.getenv("NERAIUM_MAX_ANALYSIS_ROWS", "10000"))
CSV_PROGRESS_UPDATE_EVERY = int(os.getenv("NERAIUM_CSV_PROGRESS_UPDATE_EVERY", "5000"))
CSV_CHUNK_SIZE_ROWS = int(os.getenv("NERAIUM_CSV_CHUNK_SIZE_ROWS", "5000"))
logger = logging.getLogger(__name__)



def write_latest_upload_record(record: dict[str, Any] | None) -> dict[str, Any]:
    return repository_write_latest_upload_record(record)


def _upload_state_bucket() -> str:
    return os.getenv("NERAIUM_UPLOAD_STATE_BUCKET", "").strip()


def _upload_state_prefix() -> str:
    prefix = os.getenv("NERAIUM_UPLOAD_STATE_PREFIX", "upload-state/").strip()
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    return prefix


def _shared_key(name: str) -> str:
    return str(name).replace(".json", "")


def _s3_object_key(name: str) -> str:
    return f"{_upload_state_prefix()}{_shared_key(name)}.json"


def _read_shared_state(name: str) -> dict[str, Any] | None:
    return repository_read_shared_state(name)


def _write_shared_state(name: str, payload: dict[str, Any]) -> None:
    repository_write_shared_state(name, payload)


def _runtime_db_latest_enabled() -> bool:
    return os.getenv("PYTEST_CURRENT_TEST") is None and os.getenv("NERAIUM_DISABLE_RUNTIME_DB_LATEST", "0") != "1"


def configure_runtime_dir(path: str | os.PathLike[str]) -> None:
    global RUNTIME_DIR, UPLOAD_DIR, JOB_DIR, LEGACY_JOB_DIR
    configure_runtime_state_dir(path)
    state = UPLOAD_RUNTIME_STATE
    RUNTIME_DIR = state.runtime_dir
    UPLOAD_DIR = state.upload_dir
    JOB_DIR = state.job_dir
    LEGACY_JOB_DIR = state.legacy_job_dir
    _invalidate_router_latest_cache()


def read_upload_status(job_id: str) -> dict[str, Any] | None:
    status = repository_read_upload_status(job_id)
    if isinstance(status, dict):
        return status
    return read_upload_job(job_id)


def _invalidate_router_latest_cache() -> None:
    try:
        from app.routers import data as data_router

        data_router.invalidate_latest_upload_cache()
    except Exception:
        pass


def _set_status(job_id: str, status: str, progress: int = 0, message: str = "") -> dict[str, Any]:
    """
    Persist upload progress so live uploads always have a job id/status.
    This restores the status helper used by process_upload_bytes().
    """
    payload = {
        "job_id": job_id,
        "run_id": job_id,
        "upload_id": job_id,
        "status": status,
        "processing_state": str(status).lower(),
        "percent": progress,
        "progress": progress,
        "message": message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    payload["session_scope"] = build_session_scope(job_id, filename=payload.get("filename"), status=str(status).lower())
    UPLOAD_RUNTIME_STATE.jobs[job_id] = payload
    repository_write_upload_status_progress(job_id, payload, latest_summary=payload, keep_result=False)
    UPLOAD_RUNTIME_STATE.latest_upload_cache["summary"] = payload
    upsert_upload_job(payload)
    return payload


def _complete_with_partial_result(
    *,
    job_id: str,
    filename: str,
    error: Exception,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clear_reset_block_persisted()
    result, summary = build_partial_upload_artifacts(
        job_id=job_id,
        filename=filename,
        error=error,
        snapshot=snapshot,
        build_traceability_packet=build_traceability_packet,
    )
    repository_write_upload_completion(job_id, result=result, summary=summary)
    UPLOAD_RUNTIME_STATE.jobs[job_id] = summary
    UPLOAD_RUNTIME_STATE.latest_upload_cache["result"] = result
    UPLOAD_RUNTIME_STATE.latest_upload_cache["summary"] = summary

    try:
        upsert_upload_job(summary)
    except Exception:
        pass

    return summary

def _set_propagation_stage(job_id: str, *, stage: str, progress: int, label: str) -> None:
    current = read_job(job_id) or read_upload_status(job_id) or {"job_id": job_id}
    payload = {
        **current,
        "job_id": job_id,
        "status": "PROCESSING" if stage not in {"queued", "accepted", "complete"} else ("PENDING" if stage in {"queued", "accepted"} else "COMPLETE"),
        "processing_state": stage if stage not in {"accepted"} else "queued",
        "percent": int(max(0, min(100, progress))),
        "progress": int(max(0, min(100, progress))),
        "progress_label": label,
        "message": label,
        "propagation_stage": stage,
        "propagation_progress": int(max(0, min(100, progress))),
        "propagation_label": label,
    }
    write_job(payload)


def _detect_delimiter(sample: str) -> str:
    return detect_delimiter(sample)


def _row_tokens(line: str, delimiter: str) -> list[str]:
    return row_tokens(line, delimiter)


def _looks_like_header(tokens: list[str]) -> bool:
    return looks_like_header(tokens)


def _normalized_columns(tokens: list[str], *, header_present: bool) -> list[str]:
    return normalized_columns(tokens, header_present=header_present)


def _stream_csv_snapshot(path: Path, *, max_analysis_rows: int, job_id: str | None = None) -> dict[str, Any]:
    return stream_csv_snapshot(
        path,
        max_analysis_rows=max_analysis_rows,
        csv_progress_update_every=CSV_PROGRESS_UPDATE_EVERY,
        csv_chunk_size_rows=CSV_CHUNK_SIZE_ROWS,
        job_id=job_id,
        on_progress=lambda current_job_id, stage, progress, label: _set_propagation_stage(current_job_id, stage=stage, progress=progress, label=label),
    )


def _signal_level_from_drift(item: dict[str, Any]) -> str:
    flag = str(item.get("drift_flag") or "").lower()
    percent_change = abs(float(item.get("percent_change") or 0.0))
    if flag == "review" and percent_change >= 30:
        return "elevated"
    if flag == "review":
        return "review"
    if flag == "watch":
        return "watch"
    return "info"


def _relationship_columns(item: dict[str, Any]) -> list[str]:
    refs = item.get("evidence_refs") if isinstance(item.get("evidence_refs"), list) else []
    columns = [
        str(ref.get("column"))
        for ref in refs
        if isinstance(ref, dict) and ref.get("column")
    ]
    if len(columns) >= 2:
        return columns[:2]
    relationship = str(item.get("relationship") or "")
    if "<->" in relationship:
        return [part.strip() for part in relationship.split("<->", 1)]
    return []


def _category_for_column(column: str, cultivation_mapping: dict[str, Any]) -> str:
    categories = cultivation_mapping.get("categories", {}) if isinstance(cultivation_mapping, dict) else {}
    for category, mapped_columns in categories.items():
        if category == "unknown" or not isinstance(mapped_columns, list):
            continue
        if column in mapped_columns:
            return category
    return "unknown"


def _build_upload_engine_result(
    *,
    baseline_analysis: dict[str, Any],
    relationship_model: dict[str, Any],
    cultivation_mapping: dict[str, Any],
    overall_urgency: str,
) -> dict[str, Any]:
    column_drift = baseline_analysis.get("column_drift", []) if isinstance(baseline_analysis.get("column_drift"), list) else []
    significant_drift = [
        item for item in column_drift
        if isinstance(item, dict) and item.get("drift_flag") in {"watch", "review"}
    ]
    relationship_changes = relationship_model.get("top_relationship_changes", []) if isinstance(relationship_model.get("top_relationship_changes"), list) else []

    evidence: list[dict[str, Any]] = []
    categories: dict[str, dict[str, list[str]]] = {}
    persistent_columns: set[str] = {
        str(item.get("column"))
        for item in significant_drift
        if str(item.get("drift_flag")) == "review" and item.get("column")
    }

    for item in significant_drift:
        column = str(item.get("column") or "")
        category = _category_for_column(column, cultivation_mapping)
        bucket = categories.setdefault(category, {"signals": [], "evidence": []})
        if column and column not in bucket["signals"]:
            bucket["signals"].append(column)

    for item in relationship_changes:
        if not isinstance(item, dict):
            continue
        columns = _relationship_columns(item)
        if len(columns) < 2:
            continue
        evidence.append(
            {
                "type": "relationship_change",
                "columns": columns,
                "change": float(item.get("correlation_delta") or 0.0),
                "summary": item.get("summary"),
                "coupling_strength": item.get("coupling_strength"),
                "baseline_sample_size": item.get("baseline_sample_size"),
                "recent_sample_size": item.get("recent_sample_size"),
                "evidence_refs": item.get("evidence_refs"),
                "source_rows": item.get("source_rows"),
            }
        )
        for column in columns:
            category = _category_for_column(column, cultivation_mapping)
            bucket = categories.setdefault(category, {"signals": [], "evidence": []})
            if column not in bucket["signals"]:
                bucket["signals"].append(column)
            if item.get("summary"):
                bucket["evidence"].append(str(item.get("summary")))
            persistent_columns.add(column)

    corroboration_level = "limited"
    meaningful_categories = sum(
        1
        for details in categories.values()
        if details["signals"] or details["evidence"]
    )
    if relationship_changes and meaningful_categories >= 2:
        corroboration_level = "strong"
    elif relationship_changes or significant_drift:
        corroboration_level = "moderate"

    signals = [
        {
            "column": str(item.get("column")),
            "level": _signal_level_from_drift(item),
            "direction": item.get("direction"),
            "percent_change": item.get("percent_change"),
        }
        for item in significant_drift
        if item.get("column")
    ]
    overall_result = "complete"
    if any(signal["level"] == "elevated" for signal in signals) or overall_urgency == "unstable":
        overall_result = "elevated"
    elif signals or relationship_changes or overall_urgency == "review":
        overall_result = "needs_review"

    return {
        "overall_result": overall_result,
        "signals": signals,
        "evidence": evidence,
        "system_evidence": {
            "corroboration_level": corroboration_level,
            "categories_showing_meaningful_change": meaningful_categories,
            "categories": categories,
        },
        "persistence_assessment": {
            "persistent_columns": sorted(persistent_columns),
        },
    }


def _build_csv_result(
    job_id: str,
    filename: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    row_count_total: int,
    timestamp_column: str | None,
    first_timestamp: Any,
    last_timestamp: Any,
    chunk_count: int,
    memory_estimate_bytes: int,
    ingestion_report: dict[str, Any] | None = None,
    processing_started_at: float | None = None,
) -> dict[str, Any]:
    clear_reset_block_persisted()
    initiated_by = (read_job(job_id) or {}).get("initiated_by", "anonymous")
    numeric_columns = _detect_numeric_columns(rows, columns, exclude={timestamp_column})
    matrix_rows_for_profiles = [[str(row.get(column, "")) for column in columns] for row in rows]
    numeric_profiles = []
    for profile in profile_numeric_columns(columns, matrix_rows_for_profiles):
        if profile.get("column") not in numeric_columns[:50]:
            continue
        numeric_profiles.append(
            {
                **profile,
                "minimum": profile.get("min"),
                "maximum": profile.get("max"),
            }
        )

    room_column = next((col for col in columns if col.lower().strip() in {"room", "zone", "location", "area", "group", "system", "asset"}), None)
    room_counts: dict[str, int] = {}
    room_rows: dict[str, list[dict[str, Any]]] = {}
    if room_column:
        for row in rows:
            room_name = str(row.get(room_column) or "").strip() or "State Group A"
            room_counts[room_name] = room_counts.get(room_name, 0) + 1
            room_rows.setdefault(room_name, []).append(row)
    if not room_counts:
        room_counts = {"State Group A": row_count_total}
        room_rows = {"State Group A": rows}
    room_names = sorted(room_counts.keys())
    room_summary = {"room_count": len(room_names), "rooms": [{"room": name, "row_count": room_counts[name]} for name in room_names]}

    room_intelligence = []
    room_urgency_rank = {"nominal": 0, "review": 1, "unstable": 2}
    max_room_urgency = "nominal"
    max_room_drift = 0.0
    for name in room_names:
        count = room_counts[name]
        sparse = count < 4
        sample_rows = room_rows.get(name, [])
        room_drift = 0.0
        tracked_columns = numeric_columns[: min(4, len(numeric_columns))]
        if sample_rows and tracked_columns:
            per_signal_drifts: list[float] = []
            for key in tracked_columns:
                series = [_to_float(row.get(key)) for row in sample_rows]
                clean = [value for value in series if value is not None]
                if len(clean) < 6:
                    continue
                window_size = max(3, len(clean) // 3)
                baseline_slice = clean[:window_size]
                recent_slice = clean[-window_size:]
                baseline = sum(baseline_slice) / len(baseline_slice)
                recent = sum(recent_slice) / len(recent_slice)
                baseline_std = _population_std(baseline_slice)
                recent_std = _population_std(recent_slice)
                denom = max(abs(baseline), baseline_std * 3.0, 1.0)
                mean_shift = abs(recent - baseline) / denom
                variance_growth = max(0.0, recent_std - baseline_std) / denom
                per_signal_drifts.append(mean_shift + variance_growth * 0.5)
            if per_signal_drifts:
                room_drift = sum(per_signal_drifts) / len(per_signal_drifts)
        if sparse:
            urgency = "review"; driver_category = "sensor_network"; attribution_confidence = "low"; signal_strength = "low"; room_state = "Insufficient telemetry"
            relationship_evidence = [f"{name}: Relationship evidence is limited due to sparse telemetry."]
            structural_explanation = [f"{name}: The system needs more telemetry before its structural state can be interpreted confidently."]
        elif room_drift > 0.25:
            urgency = "unstable"; driver_category = "process_timing"; attribution_confidence = "high"; signal_strength = "high"; room_state = "Persistent structural drift observed"
            relationship_pair = tracked_columns[:2]
            relationship_evidence = [
                f"{name}: Coupling between {relationship_pair[0]} and {relationship_pair[1]} has shifted away from baseline."
                if len(relationship_pair) >= 2
                else f"{name}: Multiple variables are drifting away from the baseline regime."
            ]
            structural_explanation = [f"{name}: Persistent multi-variable drift indicates a deformation in the system's baseline relational structure."]
        elif room_drift > 0.08:
            urgency = "review"; driver_category = "structural_drift"; attribution_confidence = "medium"; signal_strength = "medium"; room_state = "Structural drift observed"
            relationship_evidence = [f"{name}: Variable relationships show moderate movement away from the baseline regime."]
            structural_explanation = [f"{name}: Multi-variable drift warrants review, but the evidence does not yet indicate instability."]
        else:
            urgency = "nominal"; driver_category = "stable_monitoring"; attribution_confidence = "medium"; signal_strength = "low"; room_state = "Baseline-aligned"
            relationship_evidence = [f"{name}: Variable relationships remain inside the baseline regime."]
            structural_explanation = [f"{name}: Structural observations remain aligned with the learned baseline."]
        if room_urgency_rank[urgency] > room_urgency_rank[max_room_urgency]:
            max_room_urgency = urgency
        max_room_drift = max(max_room_drift, room_drift)
        room_intelligence.append({
            "room": name,
            "room_state": room_state,
            "urgency": urgency,
            "driver_category": driver_category,
            "attribution_confidence": attribution_confidence,
            "next_operator_move": "Collect more telemetry before interpreting this segment" if sparse else "Continue monitoring",
            "confidence_components": {"data_sufficiency": "low" if sparse else "high", "signal_strength": signal_strength, "relationship_support": "low" if sparse else "high", "persistence": "low" if sparse else "high"},
            "relationship_evidence": relationship_evidence,
            "structural_explanation": structural_explanation,
            "confidence_basis": f"{name}: Confidence components: data sufficiency, signal strength, relationship support, persistence.",
            "why_flagged": f"{name} is flagged because telemetry coverage is currently sparse." if sparse else f"{name} remains inside the learned baseline regime.",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })

    telemetry_profile, telemetry_profile_confidence, telemetry_profile_signals = classify_telemetry_profile(columns)
    operational_profile, operational_profile_confidence, operational_profile_signals, operational_modality = classify_operational_profile(columns)
    overall_urgency = "unstable" if max_room_urgency == "unstable" else ("review" if max_room_urgency == "review" else "nominal")
    if overall_urgency == "nominal" and max_room_drift > 0.08:
        overall_urgency = "review"

    _set_propagation_stage(job_id, stage="building_relationship_baselines", progress=40, label="Building relationship baselines.")
    relationship_model = _build_relationship_baseline(rows, numeric_columns, total_row_count=row_count_total)
    _set_propagation_stage(job_id, stage="scoring_relationship_drift", progress=60, label="Scoring relationship drift.")
    replay = _minimal_replay(columns, rows, timestamp_column, numeric_columns, job_id, relationship_model) if (len(rows) < 20 or not timestamp_column or len(numeric_columns) < 3) else _build_replay(rows, timestamp_column, numeric_columns, job_id, relationship_model)
    if not replay.get("timeline"):
        replay = _minimal_replay(columns, rows, timestamp_column, numeric_columns, job_id, relationship_model)

    _set_propagation_stage(job_id, stage="building_propagation_model", progress=80, label="Building propagation model.")
    frame_count = len(replay.get("timeline", []))
    now = datetime.now(timezone.utc).isoformat()
    matrix_rows = matrix_rows_for_profiles
    timestamp_profile = profile_timestamps(columns, matrix_rows, timestamp_column)
    baseline_analysis = build_baseline_analysis(columns, matrix_rows, numeric_profiles)
    relationship_baseline = relationship_model if isinstance(relationship_model, dict) else {}
    baseline_analysis = {
        **baseline_analysis,
        "top_relationship_changes": relationship_baseline.get("top_relationship_changes", []),
        "baseline_relationships": relationship_baseline.get("baseline_relationships", []),
        "sampled_for_baseline": bool(relationship_baseline.get("sampled_for_baseline")),
    }
    cultivation_mapping = map_cultivation_columns(columns)
    ingestion_report = ingestion_report or {}
    cleaning_warnings = list(ingestion_report.get("warnings") or [])
    baseline_reliable = (
        baseline_analysis.get("baseline_window_rows", 0) >= 5
        and baseline_analysis.get("recent_window_rows", 0) >= 1
        and baseline_analysis.get("columns_analyzed", 0) >= 1
    )
    stuck_sensor_count = sum(1 for profile in numeric_profiles if profile.get("constant_or_stuck"))
    data_quality = build_data_quality(
        row_count_total,
        len(columns),
        len(numeric_columns),
        bool(timestamp_column),
        list(
            dict.fromkeys(
                [
                    *cleaning_warnings,
                    *timestamp_profile.get("warnings", []),
                    *baseline_analysis.get("warnings", []),
                    *cultivation_mapping.get("warnings", []),
                    *([f"{stuck_sensor_count} numeric sensor(s) appear constant or stuck."] if stuck_sensor_count else []),
                ]
            )
        ),
        {
            "rows_received": ingestion_report.get("rows_received", row_count_total),
            "rows_dropped": ingestion_report.get("rows_dropped", 0),
            "quality_counts": ingestion_report.get("quality_counts", {}),
            "stuck_sensor_count": stuck_sensor_count,
            "irregular_sampling": any("inconsistent" in str(warning).lower() for warning in timestamp_profile.get("warnings", [])),
            "baseline_reliable": baseline_reliable,
        },
    )
    reliability_warning = None
    if not baseline_reliable:
        reliability_warning = "Insufficient baseline: SII findings are not reliable enough to show."
        warnings = list(data_quality.get("warnings", []))
        if row_count_total < 5:
            warnings = [warning for warning in warnings if warning != reliability_warning]
        else:
            warnings.append(reliability_warning)
        data_quality["warnings"] = list(dict.fromkeys(warnings))

    room_assessments = {item["room"]: dict(item) for item in room_intelligence if item.get("room")}
    primary_room_assessment = next((item for item in room_intelligence if item.get("room") == (room_names[0] if room_names else "")), room_intelligence[0] if room_intelligence else {})
    engine_result = _build_upload_engine_result(
        baseline_analysis=baseline_analysis,
        relationship_model=relationship_baseline,
        cultivation_mapping=cultivation_mapping,
        overall_urgency=overall_urgency,
    )
    driver_attribution = build_driver_attribution(
        {
            "room": primary_room_assessment.get("room") or (room_names[0] if room_names else "State Group A"),
            "state": primary_room_assessment.get("room_state") or "Baseline-aligned",
            "severity": "action" if overall_urgency == "unstable" else ("review" if overall_urgency == "review" else "info"),
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
        },
    )
    sii_intelligence["runner_module"] = RUNNER_MODULE
    sii_intelligence["replay_timeline"] = replay
    processing_time_seconds = round(max(0.0, time.perf_counter() - (processing_started_at or time.perf_counter())), 6)
    processing_trace = {"sii_pipeline_ran": True, "sii_completed": True, "replay_frame_count": frame_count, "rows_processed": row_count_total, "columns_analyzed": len(numeric_columns), "processing_time_seconds": processing_time_seconds, "completed_at": now}
    _set_propagation_stage(job_id, stage="generating_system_interpretation", progress=90, label="Generating interpretation.")
    runner_result = run_sii_runner(columns=columns, rows=matrix_rows, numeric_profiles=numeric_profiles, timestamp_column=timestamp_column, primary_room=(driver_attribution.get("room") or room_names[0] if room_names else "Uploaded telemetry"), driver_attribution=driver_attribution, engine_result=engine_result, processing_trace=processing_trace)
    latest_runner_state = runner_result.get("latest_state") if isinstance(runner_result, dict) else None

    result = {
        "job_id": job_id,
        "run_id": job_id,
        "upload_id": job_id,
        "filename": filename,
        "row_count": row_count_total,
        "column_count": len(columns),
        "columns": columns,
        "preview_rows": [{key: value for key, value in row.items() if not str(key).startswith("__")} for row in rows[:10]],
        "detected_timestamp_column": timestamp_column,
        "numeric_profiles": numeric_profiles,
        "timestamp_profile": timestamp_profile,
        "data_quality": data_quality,
        "ingestion_report": {
            "rows_received": int(ingestion_report.get("rows_received", row_count_total)),
            "rows_used": row_count_total,
            "rows_dropped": int(ingestion_report.get("rows_dropped", 0)),
            "drop_reasons": dict(ingestion_report.get("drop_reasons") or {}),
            "quality_counts": dict(ingestion_report.get("quality_counts") or {}),
            "delimiter": ingestion_report.get("delimiter", ","),
            "header_present": bool(ingestion_report.get("header_present", True)),
        },
        "processing_time_seconds": processing_time_seconds,
        "quality_warning": reliability_warning or (data_quality.get("warnings") or [None])[0],
        "sii_reliable_enough_to_show": False,
        "evidence_persistence": {
            "persisted": False,
            "run_id": job_id,
            "source": "uploaded_telemetry",
            "synthetic_fallback_used": False,
        },
        "baseline_analysis": baseline_analysis,
        "cultivation_mapping": cultivation_mapping,
        "operator_report": operator_report,
        "engine_result": engine_result,
        "driver_attribution": driver_attribution,
        "operating_state": "Baseline-aligned" if overall_urgency == "nominal" else ("Structural drift observed" if overall_urgency == "review" else "Persistent structural drift observed"),
        "drift_status": "info" if overall_urgency == "nominal" else ("review" if overall_urgency == "review" else "unstable"),
        "sii_intelligence": sii_intelligence,
        "sii_runner_result": runner_result,
        "processing_trace": processing_trace,
        "processing_stats": {"used_streaming": True, "sampled_rows": len(rows), "chunk_count": chunk_count, "memory_estimate_bytes": memory_estimate_bytes, "processing_time_seconds": processing_time_seconds},
        "room_summary": room_summary,
        "ingestion_metadata": {"source_type": "csv_upload"},
        "source_type": "csv",
        "replay_timeline": replay,
        "replay_ready": frame_count > 0,
        "replay_frame_count": frame_count,
        "last_processed_at": now,
        "completed_at": now,
    }
    result["session_scope"] = build_session_scope(job_id, filename=filename, status="active")
    result["traceability"] = build_traceability_packet(job_id=job_id, filename=filename, result=result)
    result["decision_integrity"] = dict(result["traceability"])
    if isinstance(latest_runner_state, dict):
        result["sii_intelligence"]["sii_runner_latest_state"] = latest_runner_state
        result["sii_intelligence"]["instability_index"] = latest_runner_state.get("instability_index")
        result["sii_intelligence"]["projected_time_to_failure"] = latest_runner_state.get("projected_time_to_failure")
        result["sii_intelligence"]["projected_time_to_failure_hours"] = latest_runner_state.get("projected_time_to_failure_hours")
    result["sii_intelligence"]["decision_integrity"] = dict(result["traceability"])

    summary = {"job_id": job_id, "run_id": job_id, "upload_id": job_id, "status_url": f"/api/data/upload-status/{job_id}", "status": "COMPLETE", "processing_state": "complete", "percent": 100, "progress": 100, "propagation_stage": "complete", "propagation_progress": 100, "propagation_label": "Complete.", "message": "Telemetry processing complete.", "result_available": True, "first_usable_available": True, "sii_completed": True, "replay_ready": frame_count > 0, "replay_frame_count": frame_count, "latest_replay_frames": frame_count, "replay_source": "persisted", "last_processed_at": now, "filename": filename, "row_count": row_count_total, "rows_received": result["ingestion_report"]["rows_received"], "rows_used": row_count_total, "rows_dropped": result["ingestion_report"]["rows_dropped"], "drop_reasons": result["ingestion_report"]["drop_reasons"], "processing_time_seconds": processing_time_seconds, "quality_warning": result["quality_warning"], "sii_reliable_enough_to_show": False, "column_count": len(columns), "rows_processed": row_count_total, "columns_detected": len(columns), "chunk_count": chunk_count, "runner_used": bool((runner_result or {}).get("runner_used")), "runner_module": RUNNER_MODULE, "core_engine": (runner_result or {}).get("core_engine"), "sii_completion_artifacts": {"runner_used": True, "intelligence_present": True, "processing_trace_present": True, "engine_result_present": True}, "result_summary": {"filename": filename, "sii_completed": True, "sii_completion_artifacts": {"runner_used": True, "intelligence_present": True, "processing_trace_present": True, "engine_result_present": True}, "runner_errors": []}}
    summary["session_scope"] = build_session_scope(job_id, filename=filename, status="active")
    summary["traceability"] = dict(result["traceability"])
    summary["decision_integrity"] = dict(result["traceability"])

    repository_write_upload_completion(job_id, result=result, summary=summary)
    latest_sii = read_latest_sii_state()
    if isinstance(latest_sii, dict):
        _write_shared_state("latest_sii_state", latest_sii)

    UPLOAD_RUNTIME_STATE.jobs[job_id] = summary
    UPLOAD_RUNTIME_STATE.latest_upload_cache["result"] = result
    UPLOAD_RUNTIME_STATE.latest_upload_cache["summary"] = summary
    try:
        from app.services.evidence_store import upsert_evidence_run
        record = upsert_evidence_run(
            build_evidence_record_from_result(
                run_id=job_id,
                filename=filename,
                source_type="csv_upload",
                result=result,
                created_at=now,
                completed_at=now,
                status="completed",
                initiated_by=initiated_by,
                rows_received=result["ingestion_report"]["rows_received"],
                rows_accepted=row_count_total,
                rows_rejected=result["ingestion_report"]["rows_dropped"],
            )
        )
        if isinstance(record, dict):
            from app.services.evidence_store import read_evidence_run
            persisted_record = read_evidence_run(job_id)
            evidence_persisted = bool(persisted_record and persisted_record.get("run_id") == job_id)
            result["evidence_persistence"]["persisted"] = evidence_persisted
            result["evidence_persistence"]["record_status"] = persisted_record.get("status") if persisted_record else None
            result["sii_reliable_enough_to_show"] = bool(baseline_reliable and evidence_persisted)
            summary["sii_reliable_enough_to_show"] = result["sii_reliable_enough_to_show"]
            summary["evidence_persisted"] = evidence_persisted
            repository_write_upload_completion(job_id, result=result, summary=summary)
            dispatch_observation_notification(record)
    except Exception:
        pass
    return summary


def process_upload_bytes(filename: str, content: bytes, *, job_id: str | None = None) -> dict[str, Any]:
    if not content.strip():
        raise ValueError("CSV file is empty.")
    with NamedTemporaryFile(delete=False, suffix=Path(filename).suffix or ".csv") as temp:
        temp.write(content)
        temp_path = Path(temp.name)
    try:
        return process_csv_file(temp_path, filename=filename, job_id=job_id)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def replay_payload(job_id: str | None = None) -> dict[str, Any]:
    return repository_read_replay_payload(job_id)


def _detect_timestamp_column(columns: list[str]) -> str | None:
    return detect_replay_timestamp_column(columns)


def _to_float(value: Any) -> float | None:
    return to_float(value)


def _population_std(values: list[float]) -> float:
    return population_std(values)


def _detect_numeric_columns(rows: list[dict[str, Any]], columns: list[str], exclude: set[str | None]) -> list[str]:
    return detect_numeric_columns(rows, columns, exclude)


def _build_replay(
    rows: list[dict[str, Any]],
    timestamp_column: str,
    numeric_columns: list[str],
    job_id: str,
    relationship_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_replay(rows, timestamp_column, numeric_columns, job_id, relationship_model)


def _minimal_replay(columns, rows, timestamp_column, numeric_columns, job_id, relationship_model: dict[str, Any] | None = None):
    return minimal_replay(columns, rows, timestamp_column, numeric_columns, job_id, relationship_model)


def classify_telemetry_profile(columns: list[str]) -> tuple[str, str, list[str]]:
    lowered = [col.lower() for col in columns]
    signals: list[str] = []
    if any("pool" in col or "spa" in col or "orp" in col or "chlorine" in col or "ph_" in col for col in lowered):
        signals = [col for col in columns if any(token in col.lower() for token in ("pool", "spa", "orp", "chlorine", "ph_"))][:5]
        return ("pool_hottub_systems", "high", signals or ["pool_water_temp"])
    if any("temp_air" in col or "rh_" in col or "co2" in col or "dehu" in col for col in lowered):
        signals = [col for col in columns if any(token in col.lower() for token in ("temp_air", "rh_", "co2", "dehu"))][:5]
        return ("cultivation_climate", "medium", signals or ["temp_air"])
    if any("supply_temp" in col or "return_temp" in col or "static_pressure" in col or "compressor" in col for col in lowered):
        signals = [col for col in columns if any(token in col.lower() for token in ("supply_temp", "return_temp", "static_pressure", "compressor"))][:5]
        return ("hvac_systems", "high", signals or ["supply_temp"])
    if any("voltage" in col or "current" in col or "kw_" in col or "power_factor" in col for col in lowered):
        signals = [col for col in columns if any(token in col.lower() for token in ("voltage", "current", "kw_", "power_factor"))][:5]
        return ("electrical_systems", "high", signals or ["voltage"])
    return ("unknown", "low", [])


def classify_operational_profile(columns: list[str]) -> tuple[str, str, list[str], str]:
    lowered = [col.lower() for col in columns]
    if any(token in col for col in lowered for token in ("alarm", "override", "setpoint", "maintenance", "intervention")):
        signals = [col for col in columns if any(token in col.lower() for token in ("alarm", "override", "setpoint", "maintenance", "intervention"))][:5]
        return ("operational_events", "high", signals or ["operator_interventions"], "event")
    if any(token in col for col in lowered for token in ("pump_amperage", "discharge_pressure", "bearing_temperature", "shaft_vibration", "vfd_frequency")):
        signals = [col for col in columns if any(token in col.lower() for token in ("pump", "pressure", "bearing", "vibration", "vfd"))][:5]
        return ("mechanical_systems", "high", signals or ["pump_amperage"], "continuous")
    if any(token in col for col in lowered for token in ("flow_rate", "totalized_flow", "water_pressure", "tank_level", "turnover")):
        signals = [col for col in columns if any(token in col.lower() for token in ("flow", "water", "tank", "turnover"))][:5]
        return ("water_systems", "high", signals or ["flow_rate"], "continuous")
    if any(token in col for col in lowered for token in ("distribution_pressure", "leak_detection", "pump_station", "reservoir", "sewer_flow", "treatment_plant")):
        signals = [col for col in columns if any(token in col.lower() for token in ("distribution", "leak", "pump_station", "reservoir", "sewer", "treatment"))][:5]
        return ("utility_infrastructure", "high", signals or ["distribution_pressure"], "continuous")
    if any(token in col for col in lowered for token in ("cpu_utilization", "memory_utilization", "network_throughput", "packet_loss", "latency", "api_response_time", "error_rate")):
        signals = [col for col in columns if any(token in col.lower() for token in ("cpu", "memory", "network", "packet", "latency", "api_", "error_rate"))][:6]
        return ("network_digital_infrastructure", "high", signals or ["network_throughput"], "continuous")
    return ("unknown", "low", [], "unknown")


def _read_json(name: str) -> dict[str, Any] | None:
    path = RUNTIME_DIR / name
    if not path.exists():
        return None
    try:
        return repository_read_local_json(name)
    except Exception:
        return None


def _write_json(name: str, payload: dict[str, Any]) -> None:
    repository_write_local_json(name, payload)


# Compatibility stubs for older imports.
def read_upload_cache_stats() -> dict[str, int]:
    return {"hash_cache_hits": 0, "hash_cache_misses": 0}

# --- Compatibility layer for existing Neraium imports ---

def reset_latest_upload_state(*, purge_job_records: bool = False) -> None:
    reset_upload_state()
    if purge_job_records:
        try:
            from app.services.runtime_db import clear_upload_runtime_tables

            clear_upload_runtime_tables()
        except Exception:
            logger.exception("reset_latest_upload_state_runtime_table_clear_failed")


def summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    return summarize_result_payload(result)


def write_latest_upload_result(*args) -> None:
    repository_write_latest_upload_result(*args)


def write_latest_upload_summary(*args, **kwargs) -> None:
    repository_write_latest_upload_summary(*args, **kwargs)


def read_upload_history(limit: int = 100) -> list[dict[str, Any]]:
    return read_upload_history_from_runtime(
        RUNTIME_DIR,
        limit=limit,
        current_result=read_current_upload_result(),
    )


def _refresh_queue_lifecycle_callbacks() -> UploadQueueLifecycleService:
    UPLOAD_QUEUE_LIFECYCLE.read_job = read_job
    UPLOAD_QUEUE_LIFECYCLE.read_upload_result_by_job_id = read_upload_result_by_job_id
    UPLOAD_QUEUE_LIFECYCLE.read_upload_status = read_upload_status
    UPLOAD_QUEUE_LIFECYCLE.write_job = write_job
    UPLOAD_QUEUE_LIFECYCLE.process_json_payload = process_json_payload
    UPLOAD_QUEUE_LIFECYCLE.process_csv_file = process_csv_file
    return UPLOAD_QUEUE_LIFECYCLE


def process_next_queued_upload_job() -> bool:
    return _refresh_queue_lifecycle_callbacks().process_next_queued_upload_job()


class UploadTooLargeError(ValueError):
    pass


def parse_positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return value if value > 0 else default
    except Exception:
        return default


def write_job(*args) -> None:
    clear_reset_block_persisted()
    if len(args) == 1 and isinstance(args[0], dict):
        payload = dict(args[0])
        job_id = str(payload.get("job_id") or uuid.uuid4().hex)
        payload["job_id"] = job_id
    else:
        job_id = str(args[0])
        payload = dict(args[1])
        payload["job_id"] = job_id
    payload.setdefault("run_id", job_id)
    payload.setdefault("upload_id", job_id)
    payload.setdefault("session_scope", build_session_scope(job_id, filename=payload.get("filename"), status=str(payload.get("processing_state") or payload.get("status") or "active").lower()))
    UPLOAD_RUNTIME_STATE.jobs[job_id] = payload
    status_text = str(payload.get("status") or "").upper()
    processing_state = str(payload.get("processing_state") or "").lower()
    visible_states = {
    "queued",
    "parsing_telemetry",
    "building_relationship_baselines",
    "scoring_relationship_drift",
    "building_propagation_model",
    "generating_system_interpretation",
    "partial_complete",
    "complete",
    "failed",
}

    if (
        status_text in {"PENDING", "QUEUED", "PROCESSING", "RUNNING_SII", "COMPLETE", "FAILED"}
        or processing_state in visible_states
    ):
        latest_summary = dict(payload)
        latest_summary.setdefault("session_scope", build_session_scope(job_id, filename=latest_summary.get("filename"), status=processing_state or status_text.lower() or "active"))
        latest_summary.setdefault("status_url", f"/api/data/upload-status/{job_id}")
        latest_summary.setdefault("percent", latest_summary.get("progress", 0))
        latest_summary.setdefault("progress", latest_summary.get("percent", 0))
        latest_summary.setdefault("result_available", status_text == "COMPLETE")
        latest_summary.setdefault("sii_completed", status_text == "COMPLETE")
        latest_summary.setdefault("replay_ready", False)
        latest_summary.setdefault("replay_frame_count", 0)
        latest_summary.setdefault("latest_replay_frames", latest_summary.get("replay_frame_count", 0))
        latest_summary.setdefault("propagation_stage", processing_state or "queued")
        latest_summary.setdefault("propagation_progress", latest_summary.get("progress", 0))
        latest_summary.setdefault("propagation_label", latest_summary.get("message") or "Queued.")

        repository_write_upload_status_progress(job_id, payload, latest_summary=latest_summary, keep_result=False)
        UPLOAD_RUNTIME_STATE.latest_upload_cache["summary"] = latest_summary
    else:
        write_upload_status(job_id, payload)
    try:
        upsert_upload_job(payload)
    except Exception:
        pass
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    (JOB_DIR / f"{job_id}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def read_job(job_id: str) -> dict[str, Any] | None:
    return read_upload_status(job_id)


async def create_upload_job(upload_file: Any = None, filename: str = "upload.csv", **kwargs) -> dict[str, Any]:
    max_size_bytes = int(kwargs.get("max_size_bytes", 250 * 1024 * 1024))
    if upload_file is not None and hasattr(upload_file, "read"):
        file_name = getattr(upload_file, "filename", None) or filename
        total = 0
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_size_bytes:
                raise UploadTooLargeError(f"Upload exceeds maximum allowed size of {max_size_bytes} bytes.")
        filename = file_name
    job_id = uuid.uuid4().hex
    payload = {
        "job_id": job_id,
        "filename": filename,
        "status": "QUEUED",
        "processing_state": "queued",
        "percent": 0,
        "progress": 0,
        "propagation_stage": "queued",
        "propagation_progress": 10,
        "propagation_label": "Queued.",
    }
    write_job(job_id, payload)
    return payload


def process_csv_content(content: str | bytes, filename: str = "upload.csv", **kwargs) -> dict[str, Any]:
    if isinstance(content, str):
        content = content.encode("utf-8")
    summary = process_upload_bytes(filename, content, job_id=kwargs.get("job_id"))
    return read_upload_result_by_job_id(summary["job_id"]) or read_current_upload_result() or {}


def process_csv_file(path: str | os.PathLike[str], **kwargs) -> dict[str, Any]:
    p = Path(kwargs.pop("file_path", path))
    filename = kwargs.pop("filename", None) or p.name
    job_id = str(kwargs.pop("job_id", None) or uuid.uuid4().hex)

    if not p.exists():
        raise FileNotFoundError(str(p))

    snapshot: dict[str, Any] | None = None
    processing_started_at = time.perf_counter()

    if job_id:
        _set_propagation_stage(job_id, stage="parsing_telemetry", progress=20, label="Parsing telemetry.")

    try:
        snapshot = _stream_csv_snapshot(
            p,
            max_analysis_rows=MAX_ANALYSIS_ROWS,
            job_id=job_id,
        )

        summary = _build_csv_result(
            job_id,
            filename,
            snapshot["columns"],
            snapshot["sample_rows"],
            int(snapshot["row_count"]),
            snapshot["timestamp_column"],
            snapshot["first_timestamp"],
            snapshot["last_timestamp"],
            int(snapshot["chunk_count"]),
            int(snapshot["memory_estimate_bytes"]),
            {
                "rows_received": snapshot["rows_received"],
                "rows_dropped": snapshot["rows_dropped"],
                "drop_reasons": snapshot["drop_reasons"],
                "quality_counts": snapshot["quality_counts"],
                "warnings": snapshot["cleaning_warnings"],
                "delimiter": snapshot["delimiter"],
                "header_present": snapshot["header_present"],
            },
            processing_started_at,
        )

        return read_upload_result_by_job_id(summary["job_id"]) or read_current_upload_result() or {}

    except Exception as exc:
        logger.exception("CSV upload processing failed job_id=%s filename=%s", job_id, filename)

        if snapshot:
            summary = _complete_with_partial_result(
                job_id=job_id,
                filename=filename,
                error=exc,
                snapshot=snapshot,
            )
            return read_upload_result_by_job_id(summary["job_id"]) or read_current_upload_result() or {}

        raise



def process_json_payload(payload: Any, filename: str = "upload.json", **kwargs) -> dict[str, Any]:
    return process_csv_content(json_payload_to_csv_text(payload), filename=filename, **kwargs)


UPLOAD_QUEUE_LIFECYCLE = UploadQueueLifecycleService(
    runtime_state=UPLOAD_RUNTIME_STATE,
    logger=logger,
    read_job=read_job,
    read_upload_result_by_job_id=read_upload_result_by_job_id,
    read_upload_status=read_upload_status,
    write_job=write_job,
    process_json_payload=process_json_payload,
    process_csv_file=process_csv_file,
)
