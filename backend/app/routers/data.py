from __future__ import annotations

import logging
import threading
import asyncio
import json
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
import uuid
from datetime import datetime, timezone
import re

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from app.services import adaptive_learning
from app.services.evidence_store import read_evidence_run, upsert_evidence_run
from app.services import upload_jobs
from app.services.sii_runner import CORE_ENGINE, RUNNER_MODULE
from app.services.runtime_db import record_audit_event
from app.services.runtime_db import enqueue_upload_job
from app.services.runtime_db import queue_metrics as runtime_queue_metrics
from app.services.runtime_db import configure_runtime_dir as configure_runtime_db_dir

router = APIRouter(prefix="/data", tags=["data"])
logger = logging.getLogger(__name__)
UPLOAD_JOB_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)
_UPLOAD_STATUS_CACHE: dict[str, tuple[float, dict]] = {}
_LATEST_UPLOAD_CACHE: tuple[float, dict] | None = None


def _cache_get_status(job_id: str) -> dict | None:
    entry = _UPLOAD_STATUS_CACHE.get(str(job_id))
    if not entry:
        return None
    expires_at, payload = entry
    if time.monotonic() >= expires_at:
        _UPLOAD_STATUS_CACHE.pop(str(job_id), None)
        return None
    return dict(payload)


def _cache_set_status(job_id: str, payload: dict, ttl_seconds: float = 1.5) -> None:
    _UPLOAD_STATUS_CACHE[str(job_id)] = (time.monotonic() + max(0.2, float(ttl_seconds)), dict(payload or {}))


def _cache_get_latest() -> dict | None:
    global _LATEST_UPLOAD_CACHE
    if not _LATEST_UPLOAD_CACHE:
        return None
    expires_at, payload = _LATEST_UPLOAD_CACHE
    if time.monotonic() >= expires_at:
        _LATEST_UPLOAD_CACHE = None
        return None
    return dict(payload)


def _cache_set_latest(payload: dict, ttl_seconds: float = 2.0) -> None:
    global _LATEST_UPLOAD_CACHE
    _LATEST_UPLOAD_CACHE = (time.monotonic() + max(0.2, float(ttl_seconds)), dict(payload or {}))


def _clear_endpoint_caches() -> None:
    global _LATEST_UPLOAD_CACHE
    _UPLOAD_STATUS_CACHE.clear()
    _LATEST_UPLOAD_CACHE = None


def invalidate_latest_upload_cache() -> None:
    _clear_endpoint_caches()


def _run_upload_worker_for_runtime(runtime_dir: Path) -> None:
    try:
        configure_runtime_db_dir(runtime_dir)
        upload_jobs.configure_runtime_dir(runtime_dir)
        upload_jobs.process_next_queued_upload_job()
    except Exception:
        logger.exception("upload_worker_dispatch_failed runtime_dir=%s", runtime_dir)


def _dispatch_upload_worker_for_runtime(runtime_dir: Path) -> None:
    try:
        worker = threading.Thread(
            target=_run_upload_worker_for_runtime,
            args=(runtime_dir,),
            daemon=True,
            name="upload-worker-dispatch",
        )
        worker.start()
    except Exception:
        logger.exception("upload_worker_thread_start_failed runtime_dir=%s", runtime_dir)


def _extract_timeline(result: dict | None, job_id: str | None = None) -> list[dict]:
    replay = (
        (result or {}).get("replay_timeline")
        or ((result or {}).get("sii_intelligence") or {}).get("replay_timeline")
        or {}
    )
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    if timeline:
        return timeline
    fallback = upload_jobs.replay_payload(job_id)
    fallback_timeline = fallback.get("timeline", []) if isinstance(fallback, dict) else []
    return fallback_timeline if isinstance(fallback_timeline, list) else []


def _normalize_instability_percent(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number <= 1.0:
        number *= 100.0
    return round(max(0.0, min(100.0, number)), 2)


def _to_text(value) -> str:
    text = str(value or "").strip()
    return text


def _timeline_events_from_frames(frames: list[dict], snapshot: dict, result: dict) -> list[dict]:
    if frames:
        first = frames[0] or {}
        mid = frames[len(frames) // 2] or {}
        last = frames[-1] or {}

        def _summary(frame: dict) -> str:
            cognition = frame.get("cognition_state") or {}
            relationship_changes = frame.get("relationship_changes") or []
            if isinstance(relationship_changes, list) and relationship_changes:
                first_change = relationship_changes[0]
                if isinstance(first_change, dict):
                    first_change = first_change.get("summary") or first_change.get("relationship") or ""
                return f"{cognition.get('facility_state', 'State')}: {first_change}"
            drift_velocity = frame.get("drift_velocity")
            if drift_velocity is not None:
                return f"{cognition.get('facility_state', 'State')}: drift velocity {round(float(drift_velocity), 3)}"
            return str(cognition.get("facility_state") or "Replay frame available.")

        return [
            {"stage": "onset", "summary": _summary(first)},
            {"stage": "progression", "summary": _summary(mid)},
            {"stage": "escalation", "summary": _summary(last)},
        ]

    first_ts = ((result.get("timestamp_profile") or {}).get("first_timestamp")) if isinstance(result, dict) else None
    last_ts = ((result.get("timestamp_profile") or {}).get("last_timestamp")) if isinstance(result, dict) else None
    return [
        {"stage": "onset", "summary": str(first_ts or snapshot.get("created_at") or "Initial telemetry window captured.")},
        {"stage": "progression", "summary": "Structural relationships remained under review across processing windows."},
        {"stage": "escalation", "summary": str(snapshot.get("status") or result.get("operating_state") or "Current escalation trajectory under active evaluation.")},
    ]


def _normalize_relationship_change_entries(replay_frame: dict[str, Any]) -> list[dict[str, Any]]:
    changes = replay_frame.get("relationship_changes") if isinstance(replay_frame.get("relationship_changes"), list) else []
    refs = replay_frame.get("relationship_change_evidence_refs") if isinstance(replay_frame.get("relationship_change_evidence_refs"), list) else []
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(changes[:5]):
        if isinstance(raw, dict):
            entry = dict(raw)
            entry.setdefault("summary", _to_text(entry.get("summary") or entry.get("relationship")))
            entry.setdefault("evidence_refs", entry.get("evidence_refs") if isinstance(entry.get("evidence_refs"), list) else [])
            normalized.append(entry)
            continue
        evidence_refs: list[dict[str, Any]] = []
        if index < len(refs) and isinstance(refs[index], dict):
            maybe_refs = refs[index].get("evidence_refs")
            if isinstance(maybe_refs, list):
                evidence_refs = maybe_refs
        normalized.append({"summary": _to_text(raw), "evidence_refs": evidence_refs})
    return normalized



def _clamp_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _severity_from_score(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 35:
        return "elevated"
    return "contained"


def _confidence_label(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "moderate"
    return "low"


def _score_relationship_change(entry: dict[str, Any]) -> tuple[float, float, dict[str, Any]]:
    baseline_n = int(entry.get("baseline_sample_size") or 0)
    recent_n = int(entry.get("recent_sample_size") or 0)
    coupling = abs(float(entry.get("coupling_strength") or 0.0))
    delta = abs(float(entry.get("correlation_delta") or 0.0))
    refs = entry.get("evidence_refs") if isinstance(entry.get("evidence_refs"), list) else []
    refs_with_columns = [ref for ref in refs if isinstance(ref, dict) and _to_text(ref.get("column"))]
    evidence_completeness = min(1.0, len(refs_with_columns) / 2.0)

    baseline_factor = min(1.0, baseline_n / 24.0)
    recent_factor = min(1.0, recent_n / 12.0)
    coupling_factor = min(1.0, coupling)
    delta_factor = min(1.0, delta)

    confidence_score = _clamp_score(
        (baseline_factor * 30.0)
        + (recent_factor * 20.0)
        + (coupling_factor * 20.0)
        + (delta_factor * 20.0)
        + (evidence_completeness * 10.0)
    )
    drift_score = _clamp_score((delta_factor * 70.0) + (coupling_factor * 30.0))

    scored = dict(entry)
    scored["relationship_drift_score"] = round(drift_score, 4)
    scored["severity"] = _severity_from_score(drift_score)
    scored["confidence_score"] = round(confidence_score, 4)
    scored["confidence"] = _confidence_label(confidence_score)
    return drift_score, confidence_score, scored


def _build_relationship_divergence_metrics(result: dict[str, Any], replay_frame: dict[str, Any]) -> dict[str, Any]:
    baseline_analysis = result.get("baseline_analysis") if isinstance(result.get("baseline_analysis"), dict) else {}
    baseline_changes = baseline_analysis.get("top_relationship_changes") if isinstance(baseline_analysis.get("top_relationship_changes"), list) else []
    raw_changes = baseline_changes if baseline_changes else _normalize_relationship_change_entries(replay_frame)

    scored_changes: list[dict[str, Any]] = []
    drift_scores: list[float] = []
    confidence_scores: list[float] = []
    for raw in raw_changes[:5]:
        if not isinstance(raw, dict):
            raw = {"summary": _to_text(raw), "evidence_refs": []}
        drift_score, confidence_score, scored = _score_relationship_change(raw)
        scored_changes.append(scored)
        drift_scores.append(drift_score)
        confidence_scores.append(confidence_score)

    aggregate_drift_score = round(sum(drift_scores) / len(drift_scores), 4) if drift_scores else 0.0
    aggregate_confidence_score = round(sum(confidence_scores) / len(confidence_scores), 4) if confidence_scores else 0.0
    return {
        "entries": scored_changes,
        "aggregate_drift_score": aggregate_drift_score,
        "aggregate_confidence_score": aggregate_confidence_score,
        "severity": _severity_from_score(aggregate_drift_score),
        "confidence": _confidence_label(aggregate_confidence_score),
        "from_baseline_analysis": bool(baseline_changes),
    }

def _build_system_interpretation(result: dict | None, summary: dict | None, snapshot: dict | None, frames: list[dict]) -> dict:
    result = result if isinstance(result, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    intelligence = (result.get("sii_intelligence") or {}) if isinstance(result, dict) else {}
    replay_frame = frames[-1] if frames else {}
    cognition_state = replay_frame.get("cognition_state") or {}
    topology_state = replay_frame.get("topology_state") or {}
    propagation_state = replay_frame.get("propagation_state") or {}
    evidence_state = replay_frame.get("evidence_state") or {}
    relationship_changes = replay_frame.get("relationship_changes") if isinstance(replay_frame.get("relationship_changes"), list) else []
    dominant_paths = propagation_state.get("dominant_paths") if isinstance(propagation_state.get("dominant_paths"), list) else []

    has_session = bool(result or summary or snapshot.get("last_filename") or frames)
    raw_facility_state = _to_text(cognition_state.get("facility_state") or intelligence.get("facility_state") or result.get("operating_state") or snapshot.get("status"))
    raw_confidence = _to_text(evidence_state.get("corroboration_strength") or replay_frame.get("confidence_tier") or cognition_state.get("confidence_tier") or intelligence.get("telemetry_profile_confidence"))
    raw_instability = replay_frame.get("instability_score")
    if raw_instability is None:
        raw_instability = topology_state.get("instability_score")
    if raw_instability is None:
        raw_instability = intelligence.get("instability_index")
    if raw_instability is None:
        raw_instability = ((result.get("emerging_instability") or {}).get("instability_score")) if isinstance(result.get("emerging_instability"), dict) else None
    instability_index = _normalize_instability_percent(raw_instability)
    relationship_metrics = _build_relationship_divergence_metrics(result, replay_frame)
    relationship_change_entries = relationship_metrics["entries"]
    relationship_drift_score = relationship_metrics["aggregate_drift_score"]
    if relationship_change_entries:
        instability_index = round(max(instability_index, relationship_drift_score), 4)

    compound_components = [
        1 if len(dominant_paths) > 1 else 0,
        1 if len(relationship_changes) > 2 else 0,
        1 if float(replay_frame.get("drift_velocity") or 0) > 0.35 else 0,
        1 if "degrad" in _to_text(cognition_state.get("canonical_phase")).lower() else 0,
    ]
    compound_systems_score = sum(compound_components)
    propagation_scope = "none"
    if len(dominant_paths) >= 3:
        propagation_scope = "broad"
    elif len(dominant_paths) >= 1:
        propagation_scope = "localized"

    fallback_flags: list[str] = []
    missing_fields: list[str] = []
    engine_native_fields: list[str] = []
    fallback_fields: list[str] = []

    if not has_session:
        fallback_flags.extend(["no_active_session_defaults", "instability_default_zero", "timeline_fallback"])
        missing_fields.extend(["result", "summary", "replay_timeline"])
        fallback_fields.extend(
            [
                "facility_state_enum",
                "facility_state_label",
                "confidence",
                "instability_index",
                "primary_driver",
                "escalation_window",
                "relationship_divergence",
                "relationship_events",
                "evidence_packet",
                "forensic",
            ]
        )
        return {
            "facility_state_enum": "no_active_session",
            "facility_state_label": "No Active Session",
            "confidence": "Calm",
            "instability_index": 0.0,
            "instability_scale": "0-100",
            "primary_driver": "None",
            "escalation_window": "Awaiting telemetry session",
            "state_derivation_reason": "No active upload/live session found.",
            "relationship_divergence": {
                "severity": "contained",
                "confidence": "Calm",
                "affected_systems": [],
                "top_relationship_changes": [],
            },
            "relationship_events": _timeline_events_from_frames([], snapshot, result),
            "compound_systems_score": 0,
            "propagation_scope": "none",
            "evidence_packet": {
                "packet_id": "",
                "filename": "",
                "row_count": 0,
                "column_count": 0,
                "timestamp_start": "",
                "timestamp_end": "",
                "replay_frame_count": 0,
                "processing_trace_summary": "",
                "archived": False,
                "confidence_trace_stored": False,
                "relationship_snapshot_archived": False,
            },
            "forensic": {
                "correlation_matrix_summary": "",
                "temporal_geometry_summary": "",
                "confidence_lineage": "",
                "historical_similarity_matches": [],
            },
            "missing_fields": missing_fields,
            "fallback_flags": fallback_flags,
            "engine_native_fields": [],
            "fallback_fields": sorted(set(filter(None, fallback_fields))),
            "interpretation_quality": {
                "level": "fallback",
                "engine_native_count": 0,
                "fallback_count": 4,
                "summary": "Fallback interpretation: no active session.",
            },
        }

    enum = "stable"
    label = "Stable"
    reason = "Relationships are coherent with no material divergence."
    raw_state_lower = raw_facility_state.lower()
    if "recovery" in raw_state_lower:
        enum = "recovery_state"
        label = "Recovery State"
        reason = "Recovery signal detected in facility state."
        engine_native_fields.append("facility_state_enum")
    elif compound_systems_score >= 3 or instability_index >= 75:
        enum = "cascade_risk"
        label = "Cascade Risk"
        reason = "Multi-path propagation and/or high instability indicate cascade risk."
    elif compound_systems_score >= 2 or instability_index >= 55:
        enum = "structural_degradation"
        label = "Structural Degradation"
        reason = "Compounding subsystem pressure indicates structural degradation."
    elif relationship_changes or dominant_paths or instability_index >= 25:
        enum = "relationship_drift"
        label = "Relationship Drift"
        reason = "Relationship divergence detected in replay/topology evidence."

    if not raw_confidence:
        fallback_flags.append("confidence_fallback_empty")
        missing_fields.append("confidence")
        fallback_fields.append("confidence")
    else:
        engine_native_fields.append("confidence")

    if raw_instability is None:
        fallback_flags.append("instability_fallback_zero")
        missing_fields.append("instability_score")
        fallback_fields.append("instability_index")
    else:
        engine_native_fields.append("instability_index")

    if not raw_facility_state:
        fallback_flags.append("facility_state_fallback")
        missing_fields.append("facility_state")
        fallback_fields.append("facility_state_enum")
    else:
        engine_native_fields.append("facility_state_enum")

    timestamp_profile = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    timestamp_start = _to_text(replay_frame.get("timestamp_start") or timestamp_profile.get("first_timestamp"))
    timestamp_end = _to_text(replay_frame.get("timestamp_end") or timestamp_profile.get("last_timestamp"))
    if not timestamp_start or not timestamp_end:
        missing_fields.append("timestamp_coverage")
        fallback_fields.append("evidence_packet.timestamp_coverage")
    else:
        engine_native_fields.append("evidence_packet.timestamp_coverage")

    processing_trace = result.get("processing_trace") if isinstance(result.get("processing_trace"), dict) else {}
    processing_trace_summary_parts = []
    if processing_trace.get("sii_pipeline_ran") is True:
        processing_trace_summary_parts.append("SII pipeline ran")
    if processing_trace.get("sii_completed") is True:
        processing_trace_summary_parts.append("SII completed")
    if processing_trace.get("rows_processed") is not None:
        processing_trace_summary_parts.append(f"rows_processed={processing_trace.get('rows_processed')}")
    if processing_trace.get("columns_analyzed") is not None:
        processing_trace_summary_parts.append(f"columns_analyzed={processing_trace.get('columns_analyzed')}")
    processing_trace_summary = " | ".join(processing_trace_summary_parts)
    if processing_trace_summary:
        engine_native_fields.append("evidence_packet.processing_trace_summary")
    else:
        fallback_fields.append("evidence_packet.processing_trace_summary")

    evidence_packet_id = _to_text((result.get("evidence_packet") or {}).get("packet_id") if isinstance(result.get("evidence_packet"), dict) else "")
    if not evidence_packet_id:
        evidence_packet_id = _to_text((result.get("decision_integrity") or {}).get("run_id") if isinstance(result.get("decision_integrity"), dict) else "")
    if not evidence_packet_id:
        evidence_packet_id = _to_text(result.get("job_id") or summary.get("job_id"))

    forensic_confidence_lineage = evidence_state.get("lineage_events") or evidence_state.get("confidence_lineage") or processing_trace.get("confidence_lineage") or ""
    historical_matches = ((intelligence.get("structural_memory") or {}).get("memory_matches")) if isinstance(intelligence.get("structural_memory"), dict) else []
    if not isinstance(historical_matches, list):
        historical_matches = []

    replay_frame_count = len(frames or [])

    relationship_divergence = {
        "severity": relationship_metrics["severity"],
        "confidence": relationship_metrics["confidence"],
        "confidence_score": relationship_metrics["aggregate_confidence_score"],
        "relationship_drift_score": relationship_drift_score,
        "affected_systems": [
            _to_text(replay_frame.get("affected_subsystem") or replay_frame.get("affected_area") or intelligence.get("primary_room") or result.get("primary_room"))
        ] if _to_text(replay_frame.get("affected_subsystem") or replay_frame.get("affected_area") or intelligence.get("primary_room") or result.get("primary_room")) else [],
        "top_relationship_changes": relationship_change_entries,
    }

    if relationship_changes or dominant_paths or relationship_change_entries:
        engine_native_fields.append("relationship_divergence")
        if relationship_metrics.get("from_baseline_analysis"):
            engine_native_fields.extend([
                "relationship_divergence.severity",
                "relationship_divergence.confidence",
                "relationship_divergence.relationship_drift_score",
                "relationship_divergence.confidence_score",
                "instability_index",
            ])
    else:
        fallback_fields.append("relationship_divergence")

    if intelligence.get("projected_time_to_failure") or intelligence.get("projected_time_to_failure_hours") or result.get("projected_time_to_failure"):
        engine_native_fields.append("escalation_window")
    else:
        fallback_fields.append("escalation_window")

    if replay_frame.get("affected_subsystem") or replay_frame.get("affected_area") or intelligence.get("primary_driver") or intelligence.get("primary_room") or result.get("primary_room"):
        engine_native_fields.append("primary_driver")
    else:
        fallback_fields.append("primary_driver")

    key_fields = ["facility_state_enum", "instability_index", "confidence", "relationship_divergence"]
    engine_native_set = set(filter(None, engine_native_fields))
    fallback_set = set(filter(None, fallback_fields))
    engine_native_count = sum(1 for field in key_fields if field in engine_native_set)
    fallback_count = sum(1 for field in key_fields if field in fallback_set)
    if engine_native_count == len(key_fields):
        quality_level = "engine_native"
    elif fallback_count >= 3:
        quality_level = "fallback"
    else:
        quality_level = "partial_engine"
    quality_summary = (
        f"{engine_native_count}/{len(key_fields)} key interpretation fields are engine-native; "
        f"{fallback_count} are fallback-derived."
    )

    return {
        "facility_state_enum": enum,
        "facility_state_label": label,
        "confidence": relationship_metrics["confidence"] if relationship_change_entries else (raw_confidence or "unknown"),
        "instability_index": instability_index,
        "instability_scale": "0-100",
        "primary_driver": _to_text(replay_frame.get("affected_subsystem") or replay_frame.get("affected_area") or intelligence.get("primary_driver") or intelligence.get("primary_room") or result.get("primary_room") or "Facility relationship scope"),
        "escalation_window": _to_text(intelligence.get("projected_time_to_failure") or intelligence.get("projected_time_to_failure_hours") or result.get("projected_time_to_failure") or snapshot.get("last_processed_at") or ""),
        "state_derivation_reason": reason,
        "relationship_divergence": relationship_divergence,
        "relationship_events": _timeline_events_from_frames(frames, snapshot, result),
        "compound_systems_score": compound_systems_score,
        "propagation_scope": propagation_scope,
        "evidence_packet": {
            "packet_id": evidence_packet_id,
            "filename": _to_text(result.get("filename") or snapshot.get("last_filename") or summary.get("filename")),
            "row_count": int(result.get("row_count") or result.get("rows_processed") or snapshot.get("rows_processed") or summary.get("row_count") or 0),
            "column_count": int(result.get("column_count") or result.get("columns_detected") or snapshot.get("columns_detected") or summary.get("column_count") or 0),
            "timestamp_start": timestamp_start,
            "timestamp_end": timestamp_end,
            "replay_frame_count": replay_frame_count,
            "processing_trace_summary": processing_trace_summary,
            "archived": bool(evidence_packet_id),
            "confidence_trace_stored": bool(raw_confidence),
            "relationship_snapshot_archived": replay_frame_count > 0,
        },
        "forensic": {
            "correlation_matrix_summary": _to_text(replay_frame.get("correlation_matrix") or topology_state.get("correlation_matrix") or ""),
            "temporal_geometry_summary": _to_text(replay_frame.get("temporal_geometry") or topology_state.get("temporal_geometry") or propagation_state.get("geometry") or ""),
            "confidence_lineage": forensic_confidence_lineage,
            "historical_similarity_matches": historical_matches[:5],
        },
        "missing_fields": sorted(set(filter(None, missing_fields))),
        "fallback_flags": sorted(set(filter(None, fallback_flags))),
        "engine_native_fields": sorted(set(filter(None, engine_native_fields))),
        "fallback_fields": sorted(set(filter(None, fallback_fields))),
        "interpretation_quality": {
            "level": quality_level,
            "engine_native_count": engine_native_count,
            "fallback_count": fallback_count,
            "summary": quality_summary,
        },
    }


def _process_upload_inline(job_id: str, status: dict) -> dict:
    file_path = status.get("file_path")
    if not file_path or not Path(str(file_path)).exists():
        return status
    try:
        path = Path(str(file_path))
        filename = status.get("filename") or path.name
        if path.suffix.lower() == ".json":
            upload_jobs.process_json_payload(path.read_text(encoding="utf-8"), filename=filename, job_id=job_id)
        else:
            upload_jobs.process_csv_file(path, filename=filename, job_id=job_id)
        return upload_jobs.read_upload_status(job_id) or status
    except Exception as exc:
        logger.exception("upload_status_inline_processing_failed job_id=%s", job_id)
        failed = {
            **status,
            "job_id": job_id,
            "status": "FAILED",
            "processing_state": "failed",
            "error_type": "processing_error",
            "error": str(exc),
            "message": "Telemetry processing failed.",
            "progress_label": "Telemetry processing failed.",
            "result_available": False,
        }
        upload_jobs.write_job(failed)
        return failed


def _resolve_upload_status_payload(job_id: str, state_backend: str) -> dict:
    status = upload_jobs.read_upload_status(job_id)
    if status and str(status.get("status", "")).upper() in {"PENDING", "QUEUED", "PROCESSING"}:
        processed = upload_jobs.process_next_queued_upload_job()
        status = upload_jobs.read_upload_status(job_id) or status
        if not processed and str(status.get("status", "")).upper() in {"PENDING", "QUEUED", "PROCESSING"}:
            status = _process_upload_inline(job_id, status)
    if status:
        normalized = normalize_upload_status_payload(status)
        normalized.setdefault("state_backend", state_backend)
        return normalized
    latest_summary = upload_jobs.read_latest_upload_summary() or {}
    if str(latest_summary.get("job_id") or "") == str(job_id):
        normalized = normalize_upload_status_payload(latest_summary)
        normalized.setdefault("state_backend", state_backend)
        return normalized
    latest_result = upload_jobs.read_upload_result_by_job_id(job_id)
    if isinstance(latest_result, dict) and latest_result.get("job_id") == job_id:
        timeline = _extract_timeline(latest_result, job_id)
        return {
            "job_id": job_id,
            "status_url": f"/api/data/upload-status/{job_id}",
            "status": "COMPLETE",
            "processing_state": "complete",
            "percent": 100,
            "progress": 100,
            "result_available": True,
            "first_usable_available": True,
            "sii_completed": True,
            "replay_ready": len(timeline or []) > 0,
            "replay_frame_count": len(timeline or []),
            "latest_replay_frames": len(timeline or []),
            "replay_source": "persisted" if timeline else "unknown",
            "last_processed_at": latest_result.get("last_processed_at") or latest_result.get("completed_at"),
            "filename": latest_result.get("filename"),
            "row_count": latest_result.get("row_count", 0),
            "column_count": latest_result.get("column_count", 0),
            "rows_processed": latest_result.get("row_count", 0),
            "columns_detected": latest_result.get("column_count", 0),
            "progress_label": "Telemetry processing complete.",
            "message": "Telemetry processing complete.",
            "error": None,
            "propagation_stage": "complete",
            "propagation_progress": 100,
            "propagation_label": "Telemetry processing complete.",
            "state_backend": state_backend,
        }
    if UPLOAD_JOB_ID_PATTERN.match(str(job_id or "")):
        return {
            "job_id": job_id,
            "status_url": f"/api/data/upload-status/{job_id}",
            "status": "PENDING",
            "processing_state": "queued",
            "percent": 0,
            "progress": 0,
            "replay_ready": False,
            "replay_frame_count": 0,
            "result_available": False,
            "first_usable_available": False,
            "sii_completed": False,
            "message": "Upload accepted. Waiting for status propagation.",
            "propagation_stage": "queued",
            "propagation_progress": 12,
            "propagation_label": "Upload queued.",
            "state_backend": state_backend,
        }
    return {
        "job_id": job_id,
        "status": "NOT_FOUND",
        "processing_state": "missing",
        "percent": 0,
        "replay_ready": False,
        "replay_frame_count": 0,
        "result_available": False,
        "error_type": "upload_session_missing",
        "error": "upload_session_missing",
        "message": "Upload session expired or was not found.",
        "state_backend": state_backend,
    }


@router.post("/upload", status_code=202)
async def upload_data(request: Request, file: UploadFile = File(...)):
    content = await file.read()
    settings = request.app.state.settings
    filename = file.filename or "upload.csv"
    lowered = filename.lower()
    if not (lowered.endswith(".csv") or lowered.endswith(".json")):
        return JSONResponse(
            status_code=400,
            content={
                "status": "FAILED",
                "processing_state": "failed",
                "message": "Only .csv and .json telemetry files are supported.",
            },
        )
    if lowered.endswith(".csv") and not content.strip():
        return JSONResponse(
            status_code=400,
            content={
                "status": "FAILED",
                "processing_state": "failed",
                "message": "CSV file is empty.",
            },
        )
    max_size_bytes = int(getattr(settings, "max_upload_size_bytes", 250 * 1024 * 1024))
    if len(content) > max_size_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "status": "FAILED",
                "error_type": "upload_too_large",
                "message": f"Upload exceeds maximum allowed size of {max_size_bytes} bytes.",
            },
        )
    metrics = queue_metrics()
    if int(metrics.get("pending", 0)) >= int(getattr(settings, "max_pending_upload_jobs", 3)):
        return JSONResponse(
            status_code=503,
            headers={"retry-after": "30"},
            content={
                "status": "FAILED",
                "error_type": "upload_queue_saturated",
                "message": "Upload queue is saturated. Retry shortly.",
            },
        )
    
    content_type = (file.content_type or "").lower()
    auth_context = getattr(request.state, "auth_context", {})
    actor = (
        auth_context.get("auth_subject")
        or request.headers.get("X-Neraium-User")
        or request.headers.get("X-Authenticated-User")
        or request.headers.get("X-Forwarded-Email")
        or "anonymous"
    )
    try:
        job_id = uuid.uuid4().hex
        with NamedTemporaryFile(delete=False, suffix=Path(filename).suffix or ".csv") as temp:
            temp.write(content)
            temp_path = temp.name
        summary = {
            "job_id": job_id,
            "filename": filename,
            "status_url": f"/api/data/upload-status/{job_id}",
            "status": "PENDING",
            "processing_state": "queued",
            "percent": 0,
            "progress": 0,
            "message": "Upload accepted. Processing is queued.",
            "propagation_stage": "queued",
            "propagation_progress": 12,
            "propagation_label": "Upload queued.",
            "runner_used": False if str(getattr(settings, "process_role", "")).lower() == "api" else True,
            "runner_module": RUNNER_MODULE,
            "core_engine": CORE_ENGINE,
            "file_path": temp_path,
            "file_size_bytes": len(content),
            "content_type": content_type,
            "initiated_by": actor,
        }
        upload_jobs.write_job(summary)
        enqueue_upload_job(job_id)
        _dispatch_upload_worker_for_runtime(request.app.state.settings.runtime_dir)
        record_audit_event(
            actor=actor,
            action="upload.accepted",
            resource_type="upload_job",
            resource_id=str(job_id or "unknown"),
            request_id=auth_context.get("request_id"),
            detail={"filename": filename, "size_bytes": len(content)},
        )
        run_id = summary.get("job_id")
        if run_id:
            record = upsert_evidence_run(
                {
                    "run_id": run_id,
                    "source_name": filename,
                    "source_type": "csv_upload",
                    "status": "queued",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "completed_at": None,
                    "rows_received": 0,
                    "rows_accepted": 0,
                    "rows_rejected": 0,
                    "sensors_detected": summary.get("columns_detected", summary.get("column_count", 0)),
                    "room": "Uploaded telemetry",
                    "operating_state": "Monitoring",
                    "drift_status": "info",
                    "warnings": [],
                    "errors": [],
                    "primary_drivers": [],
                    "evidence_summary": [],
                    "structural_archetypes": [],
                    "initiated_by": actor,
                    "adaptive_site_key": "site::default",
                    "operator_feedback_history": [],
                }
            )
            if record:
                upsert_evidence_run(record)
    except Exception as exc:
        failed_job_id = uuid.uuid4().hex
        failed_at = datetime.now(timezone.utc).isoformat()
        upload_jobs.write_job(
            {
                "job_id": failed_job_id,
                "filename": filename,
                "status": "FAILED",
                "processing_state": "failed",
                "error": str(exc),
                "message": "Telemetry processing failed.",
                "progress_label": "Telemetry processing failed.",
                "result_available": False,
            }
        )
        upsert_evidence_run(
            {
                "run_id": failed_job_id,
                "source_name": filename,
                "source_type": "csv_upload",
                "status": "failed",
                "created_at": failed_at,
                "completed_at": failed_at,
                "rows_received": 0,
                "rows_accepted": 0,
                "rows_rejected": 0,
                "sensors_detected": 0,
                "room": "Uploaded telemetry",
                "operating_state": "error",
                "drift_status": "error",
                "warnings": [],
                "errors": [str(exc)],
                "primary_drivers": [],
                "evidence_summary": [],
                "structural_archetypes": [],
                "initiated_by": actor,
                "adaptive_site_key": "site::default",
                "operator_feedback_history": [],
            }
        )
        summary = {"job_id": failed_job_id}
    return {
        "job_id": summary.get("job_id"),
        "status": "PENDING",
        "filename": filename,
        "message": "Preparing telemetry intake. Upload received and queued for background processing.",
        "status_url": f"/api/data/upload-status/{summary.get('job_id')}",
        "file_size_bytes": len(content),
        "propagation_stage": "accepted",
        "propagation_progress": 5,
        "propagation_label": "Upload received.",
    }


@router.get("/upload-status/{job_id}")
async def upload_status(job_id: str):
    cached = _cache_get_status(job_id)
    if isinstance(cached, dict):
        if str(cached.get("status", "")).upper() == "NOT_FOUND":
            return JSONResponse(status_code=404, content=cached)
        return cached
    state_backend = upload_jobs.upload_state_backend()
    normalized = _resolve_upload_status_payload(job_id, state_backend)
    if str(normalized.get("status", "")).upper() == "NOT_FOUND":
        logger.warning(
            "upload_status_missing polling_job_id=%s validation_failure_reason=upload_session_missing metadata_exists=False",
            job_id,
        )
        _cache_set_status(job_id, normalized, ttl_seconds=1.0)
        return JSONResponse(status_code=404, content=normalized)

    if str(normalized.get("status", "")).upper() in {"COMPLETE", "FAILED"}:
        if str(normalized.get("status", "")).upper() == "COMPLETE":
            existing = read_evidence_run(str(job_id))
            if isinstance(existing, dict) and str(existing.get("status", "")).lower() == "queued":
                now = datetime.now(timezone.utc).isoformat()
                upload_result = upload_jobs.read_upload_result_by_job_id(job_id) or {}
                upsert_evidence_run(
                    {
                        **existing,
                        "status": "completed",
                        "completed_at": now,
                        "rows_received": upload_result.get("row_count", existing.get("rows_received", 0)),
                        "rows_accepted": upload_result.get("row_count", existing.get("rows_accepted", 0)),
                        "sensors_detected": max(0, int(upload_result.get("column_count", existing.get("sensors_detected", 0))) - 1),
                        "room": (((upload_result.get("sii_intelligence") or {}).get("primary_room")) or existing.get("room")),
                    }
                )
        if str(normalized.get("status", "")).upper() == "FAILED":
            existing = read_evidence_run(str(job_id))
            if isinstance(existing, dict) and str(existing.get("status", "")).lower() == "queued":
                now = datetime.now(timezone.utc).isoformat()
                upsert_evidence_run(
                    {
                        **existing,
                        "status": "failed",
                        "completed_at": now,
                        "errors": existing.get("errors") or [str(normalized.get("error") or "processing_error")],
                    }
                )
    terminal = str(normalized.get("status", "")).upper() in {"COMPLETE", "FAILED"}
    _cache_set_status(job_id, normalized, ttl_seconds=4.0 if terminal else 1.5)
    return normalized


@router.get("/upload-stream/{job_id}")
async def upload_stream(job_id: str):
    state_backend = upload_jobs.upload_state_backend()

    async def event_generator():
        # Stream for up to ~12 minutes with heartbeat-like cadence.
        for _ in range(180):
            payload = _resolve_upload_status_payload(job_id, state_backend)
            yield f"data: {json.dumps(payload)}\n\n"
            if str(payload.get("status", "")).upper() in {"COMPLETE", "FAILED"}:
                break
            await asyncio.sleep(4)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/latest-upload")
async def latest_upload(include_persisted: int | bool = True):
    cached = _cache_get_latest()
    if isinstance(cached, dict):
        return cached
    state_backend = upload_jobs.upload_state_backend()
    result = upload_jobs.read_latest_upload_result()
    summary = latest_completed_job_summary() or upload_jobs.read_latest_upload_summary() or {}
    history = upload_jobs.read_upload_history(limit=20)

    if upload_jobs.reset_block_persisted_active():
        summary = {}
        result = None
        history = []

    def _has_persisted_status(job_id: str | None) -> bool:
        if not job_id:
            return False
        status = upload_jobs.read_upload_status(str(job_id))
        return isinstance(status, dict) and bool(status.get("job_id"))

    def _is_rich_persisted_result(candidate: dict | None) -> bool:
        if not isinstance(candidate, dict):
            return False
        if int(candidate.get("row_count") or 0) > 0:
            return True
        if isinstance(candidate.get("data_quality"), dict):
            return True
        if isinstance(candidate.get("room_summary"), dict):
            return True
        return False

    # If latest cache points to an incomplete artifact, refresh from
    # canonical per-job persisted result when available.
    result_job_id = str((result or {}).get("job_id") or "")
    if isinstance(result, dict) and result_job_id and not result.get("filename"):
        by_job_result = upload_jobs.read_upload_result_by_job_id(result_job_id)
        if isinstance(by_job_result, dict) and by_job_result.get("filename"):
            result = by_job_result

    # If latest summary/result are stale or empty, recover from any completed
    # persisted upload status. This keeps latest-upload aligned with
    # upload-status in multi-task ECS deployments.
    if not summary and history:
        for item in history:
            candidate_job_id = str(item.get("job_id") or "") if isinstance(item, dict) else ""
            if not _has_persisted_status(candidate_job_id):
                continue
            if isinstance(item, dict) and (
                item.get("status") == "COMPLETE"
                or item.get("result_available")
                or item.get("sii_completed")
            ):
                summary = dict(item)
                break

    result_job_id = str((result or {}).get("job_id") or "")
    if not summary and not _is_rich_persisted_result(result):
        result = None
    elif summary and not _has_persisted_status(result_job_id) and not _is_rich_persisted_result(result):
        result = None

    # Recovery path for split API/worker containers:
    # if the full result is not visible in this container but a completed
    # upload summary/history is visible, return a non-empty latest-upload
    # snapshot so the frontend stops treating the system as empty.
    if not result and summary:
        job_id = summary.get("job_id")
        by_job = upload_jobs.read_upload_result_by_job_id(str(job_id)) if job_id else None
        result = by_job or None

    preferred_job_id = str((result or {}).get("job_id") or summary.get("job_id") or "")
    if preferred_job_id and history:
        preferred_item = None
        remaining_history = []
        for item in history:
            if not isinstance(item, dict):
                continue
            item_job_id = str(item.get("job_id") or "")
            if item_job_id == preferred_job_id and preferred_item is None:
                preferred_item = item
                continue
            remaining_history.append(item)
        if preferred_item is None:
            preferred_item = next((item for item in remaining_history if str(item.get("job_id") or "") == preferred_job_id), None)
            if preferred_item is not None:
                remaining_history = [item for item in remaining_history if item is not preferred_item]
        if preferred_item is not None:
            history = [preferred_item, *remaining_history]


    if not result and history:
        latest = history[0] if isinstance(history[0], dict) else {}
        latest_job_id = str(latest.get("job_id") or "")
        if latest_job_id and not _has_persisted_status(latest_job_id):
            latest = {}
        if latest.get("status") == "COMPLETE" or latest.get("result_available"):
            result = {
                "job_id": latest.get("job_id"),
                "filename": latest.get("filename"),
                "row_count": latest.get("row_count") or latest.get("rows_processed") or 0,
                "column_count": latest.get("column_count") or latest.get("columns_detected") or 0,
                "replay_timeline": {"timeline": [None] * int(latest.get("replay_frame_count") or latest.get("latest_replay_frames") or 0)},
                "last_processed_at": latest.get("last_processed_at"),
                "sii_completion_artifacts": latest.get("sii_completion_artifacts") or {},
                "result_summary": latest.get("result_summary") or {},
            }
            summary = {**latest, **summary}
    frames = _extract_timeline(result if isinstance(result, dict) else None, summary.get("job_id") if isinstance(summary, dict) else None)
    adaptive = adaptive_learning.build_adaptive_snapshot(result, summary) if isinstance(result, dict) else {}
    if isinstance(adaptive, dict):
        recent_feedback = (((adaptive.get("event_memory") or {}).get("recent_feedback_history")) or [])
        if not recent_feedback:
            fallback_site = adaptive_learning.build_adaptive_snapshot({"room_summary": {"rooms": []}}, {"last_processed_at": snapshot_time(summary)} if isinstance(summary, dict) else {})
            fallback_recent = (((fallback_site.get("event_memory") or {}).get("recent_feedback_history")) or [])
            if fallback_recent:
                adaptive["event_memory"] = adaptive.get("event_memory", {})
                adaptive["event_memory"]["recent_feedback_history"] = fallback_recent
    snapshot = {
        **summary,
        "state_backend": state_backend,
        "source": "uploaded" if result else "none",
        "last_filename": (result or {}).get("filename") or summary.get("filename"),
        "rows_processed": (result or {}).get("row_count") or summary.get("rows_processed") or summary.get("row_count") or 0,
        "columns_detected": (result or {}).get("column_count") or summary.get("columns_detected") or summary.get("column_count") or 0,
        "state_available": bool(result),
        "status": "COMPLETE" if result else summary.get("status", "empty"),
        "processing_state": "complete" if result else summary.get("processing_state", "empty"),
        "result_available": bool(result) or bool(summary.get("result_available")),
        "sii_completed": bool(result) or bool(summary.get("sii_completed")),
        "replay_ready": bool(frames),
        "replay_frame_count": len(frames or []),
        "latest_replay_frames": len(frames or []),
        "replay_source": "persisted" if frames else "unknown",
    }
    if history and snapshot.get("last_filename"):
        history[0]["filename"] = snapshot["last_filename"]
    system_interpretation = _build_system_interpretation(result if isinstance(result, dict) else None, summary if isinstance(summary, dict) else None, snapshot, frames if isinstance(frames, list) else [])
    response_payload = {
        "snapshot": snapshot,
        "latest_result": result,
        "latestResult": result,
        "summary": summary,
        "history": history,
        "adaptive_learning": adaptive,
        "state_backend": state_backend,
        "system_interpretation": system_interpretation,
        **snapshot,
    }
    cache_ttl = 4.0 if bool(result) else 1.5
    _cache_set_latest(response_payload, ttl_seconds=cache_ttl)
    return response_payload


@router.get("/system-interpretation")
async def system_interpretation_contract(include_persisted: int | bool = True):
    payload = await latest_upload(include_persisted=include_persisted)
    interpretation = payload.get("system_interpretation") if isinstance(payload, dict) else None
    raw_source = str((payload or {}).get("source") or (payload or {}).get("snapshot", {}).get("source") or "").lower()
    if raw_source in {"uploaded", "latest_upload"}:
        source = "latest_upload"
    elif raw_source == "live":
        source = "live"
    else:
        source = "none"
    return {
        "system_interpretation": interpretation if isinstance(interpretation, dict) else {},
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/replay/{job_id}")
async def data_replay(job_id: str):
    return upload_jobs.replay_payload(job_id)


@router.get("/intake/{job_id}/result")
async def intake_result(job_id: str):
    result = upload_jobs.read_upload_result_by_job_id(job_id)
    if not result:
        return {
            "job_id": job_id,
            "result_available": False,
            "status": "NOT_FOUND",
            "result": None,
        }
    return {
        "job_id": job_id,
        "result_available": True,
        "status": "COMPLETE",
        "result": result,
    }


@router.post("/reset")
async def reset_data():
    upload_jobs.reset_upload_state()
    _clear_endpoint_caches()
    return {"ok": True, "status": "reset"}


def rebuild_upload_replay_from_source(job_id: str | dict | None = None, *args, **kwargs):
    payload = job_id if isinstance(job_id, dict) else {}
    requested_job_id = str(payload.get("job_id") or job_id or "")
    file_path = payload.get("file_path")
    if not file_path:
        return upload_jobs.replay_payload(requested_job_id or None)

    result = upload_jobs.process_csv_file(Path(file_path))
    replay = result.get("replay_timeline") or {}
    timeline = replay.get("timeline", []) if isinstance(replay, dict) else []
    replay_mode = "minimal_timestamp_fallback"
    try:
        lines = Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
        if lines:
            headers = [h.strip().lower() for h in lines[0].split(",")]
            ts_idx = next((idx for idx, value in enumerate(headers) if "time" in value or "date" in value), 0)
            data_lines = lines[1: min(len(lines), 30)]
            numeric_like = 0
            for row in data_lines:
                cells = [cell.strip() for cell in row.split(",")]
                for idx, cell in enumerate(cells):
                    if idx == ts_idx:
                        continue
                    if any(ch.isdigit() for ch in cell):
                        numeric_like += 1
            if numeric_like >= 8:
                replay_mode = "standard"
    except OSError:
        pass

    return {
        "job_id": requested_job_id or result.get("job_id"),
        "timeline": timeline,
        "frame_count": len(timeline),
        "meta": {**(replay.get("meta", {}) if isinstance(replay, dict) else {}), "replay_mode": replay_mode},
        "message": "Replay reconstructed from the retained source CSV.",
    }


def queue_metrics() -> dict[str, int]:
    return runtime_queue_metrics()


_PROPAGATION_STAGE_DEFAULTS = {
    "accepted": (5, "Upload received."),
    "queued": (12, "Upload queued."),
    "parsing_telemetry": (25, "Parsing telemetry payload."),
    "building_relationship_baselines": (45, "Building relationship baselines."),
    "scoring_relationship_drift": (58, "Scoring relationship drift."),
    "building_propagation_model": (72, "Building propagation model."),
    "generating_system_interpretation": (88, "Generating system interpretation."),
    "complete": (100, "Telemetry processing complete."),
}


def _infer_propagation_stage(payload: dict, normalized_status: str) -> str:
    explicit = str(payload.get("propagation_stage") or "").strip().lower()
    if explicit:
        return explicit
    processing_state = str(payload.get("processing_state") or "").strip().lower()
    if processing_state in _PROPAGATION_STAGE_DEFAULTS:
        return processing_state
    message = f"{payload.get('progress_label') or ''} {payload.get('message') or ''}".lower()
    if normalized_status == "COMPLETE":
        return "complete"
    if "baseline" in message:
        return "building_relationship_baselines"
    if "drift" in message or "scoring" in message or "running sii" in message:
        return "scoring_relationship_drift"
    if "propagation" in message or "replay" in message:
        return "building_propagation_model"
    if "interpretation" in message or "cognition" in message or "writing" in message:
        return "generating_system_interpretation"
    if "parsing" in message:
        return "parsing_telemetry"
    if normalized_status in {"PENDING", "QUEUED"}:
        return "queued"
    if normalized_status in {"PROCESSING", "RUNNING_SII"}:
        return "parsing_telemetry"
    return "queued"


def _with_propagation_fields(normalized: dict, raw_payload: dict, normalized_status: str) -> dict:
    stage = _infer_propagation_stage(raw_payload, normalized_status)
    default_progress, default_label = _PROPAGATION_STAGE_DEFAULTS.get(stage, (0, "Processing telemetry."))
    backend_progress = normalized.get("percent", normalized.get("progress", default_progress))
    try:
        backend_progress = int(max(0, min(100, float(backend_progress))))
    except (TypeError, ValueError):
        backend_progress = default_progress
    if normalized_status == "COMPLETE":
        backend_progress = 100
        stage = "complete"
        default_label = _PROPAGATION_STAGE_DEFAULTS["complete"][1]
    normalized["propagation_stage"] = str(raw_payload.get("propagation_stage") or stage)
    normalized["propagation_progress"] = int(raw_payload.get("propagation_progress") or backend_progress)
    normalized["propagation_label"] = str(raw_payload.get("propagation_label") or normalized.get("progress_label") or normalized.get("message") or default_label)
    return normalized


def normalize_upload_status_payload(payload: dict) -> dict:
    raw_status = str(payload.get("status", "")).upper()
    status = {
        "QUEUED": "PENDING",
        "QUEUE": "PENDING",
        "FAILED": "FAILED",
        "FAILURE": "FAILED",
    }.get(raw_status, raw_status)
    normalized = dict(payload)
    normalized["status"] = status
    normalized.setdefault("job_id", payload.get("job_id"))
    normalized.setdefault("percent", int(payload.get("progress", payload.get("percent", 0)) or 0))
    normalized.setdefault("progress", int(payload.get("percent", payload.get("progress", 0)) or 0))
    if status in {"RUNNING_SII", "PROCESSING", "PENDING", "QUEUED"}:
        normalized.setdefault("message", "Telemetry batch processing in progress.")
    if status == "COMPLETE":
        artifacts = payload.get("sii_completion_artifacts") or (payload.get("result_summary") or {}).get("sii_completion_artifacts") or {}
        sii_completed = bool(payload.get("sii_completed") or (payload.get("result_summary") or {}).get("sii_completed"))
        requires_contract_enforcement = "result_summary" in payload or "result_available" in payload
        if requires_contract_enforcement and (not sii_completed or not artifacts):
            normalized["status"] = "FAILED"
            normalized["sii_completed"] = False
            normalized["error_type"] = "sii_completion_missing"
            normalized["error"] = "sii_completion_missing"
            normalized["message"] = "SII completion artifacts are missing."
            return _with_propagation_fields(normalized, payload, "FAILED")
        normalized.setdefault("progress_label", "Telemetry processing complete.")
        normalized.setdefault("message", "Telemetry processing complete.")
        normalized.setdefault("error", None)
        normalized.setdefault(
            "result_summary",
            {
                "job_id": normalized.get("job_id"),
                "filename": normalized.get("filename"),
                "rows_processed": normalized.get("rows_processed", normalized.get("row_count", 0)),
                "columns_detected": normalized.get("columns_detected", normalized.get("column_count", 0)),
                "runner_errors": [],
            },
        )
    return _with_propagation_fields(normalized, payload, normalized.get("status", status))


def snapshot_time(summary: dict) -> str:
    return str(summary.get("last_processed_at") or summary.get("completed_at") or datetime.now(timezone.utc).isoformat())


def latest_completed_job_summary() -> dict:
    return upload_jobs.read_latest_upload_summary() or {}
