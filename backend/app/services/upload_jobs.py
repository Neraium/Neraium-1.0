from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
from pathlib import Path
from typing import Any
from app.core.path_safety import safe_upload_suffix
from app.services.analysis_explanations import build_analysis_explanation
from app.services.analysis_provenance import canonical_digest, file_digest
from app.services.analysis_result_contract import attach_analysis_result, build_normalized_telemetry
from app.services.condition_corroboration import ConditionCorroborationService
from app.services.baseline_contracts import (
    WORKFLOW_ANALYZE_NEW_DATA,
    WORKFLOW_LEGACY_ANALYSIS,
    is_baseline_workflow,
    normalize_workflow,
)
from app.services.baseline_analysis_repository import persist_completed_analysis, stamp_comparison_analysis_identity
from app.services.baseline_analysis import build_baseline_analysis
from app.services.behavioral_baseline import build_behavioral_baseline
from app.services.behavioral_model_repository import (
    read_active_behavioral_model,
    read_baseline_result,
)
from app.services.cultivation_mapping import map_cultivation_columns
from app.services.data_quality import build_data_quality, detect_timestamp_column, parse_numeric_value, parse_timestamp, profile_numeric_columns, profile_timestamps
from app.services.driver_attribution import build_driver_attribution
from app.services.facility_context import read_facility_context
from app.services.operator_report import build_operator_report
from app.services.notifications import dispatch_observation_notification
from app.services.sii_intelligence import build_upload_intelligence
from app.services.sii_runner import RUNNER_MODULE, read_latest_sii_state
from app.services.runtime_db import claim_next_upload_job, mark_queue_job_failed, upsert_upload_job, read_upload_job, enqueue_upload_job, complete_upload_queue_job, touch_upload_queue_job
from app.services.upload_completion import build_partial_upload_artifacts
from app.services.upload_evidence import build_evidence_record_from_result, build_traceability_packet
from app.services.upload_parser import json_payload_to_csv_text
from app.services.upload_pipeline import run_structural_analysis_pipeline
from app.services.upload_persistence import project_result_for_transport
from app.services.upload_persistence import read_upload_history as read_upload_history_from_runtime
from app.services.upload_persistence import summarize_result as summarize_result_payload
from app.services.upload_queue_lifecycle import UploadQueueLifecycleService
from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE
from app.services.dataset_scope import attach_dataset_scope, current_dataset_scope, dataset_scope_from_payload
from app.services.upload_lifecycle import VISIBLE_UPLOAD_STATES, canonical_stage_payload
from app.services.upload_state_repository import (
    cache_latest_upload_payload,
    clear_reset_block_persisted,
    configure_runtime_dir as configure_runtime_state_dir,
    delete_upload_source,
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
    restore_upload_source,
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
from app.domain_interpretation import DomainInterpretationContext, attach_domain_interpretations
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
JOB_RUNTIME_DIRS: dict[str, Path] = {}
LATEST_UPLOAD_CACHE = UPLOAD_RUNTIME_STATE.latest_upload_cache
MAX_ANALYSIS_ROWS = None
MAX_SII_ROWS = None
MAX_INGESTION_ANALYSIS_ROWS = 100_000
CSV_PROGRESS_UPDATE_EVERY = int(os.getenv("NERAIUM_CSV_PROGRESS_UPDATE_EVERY", "5000"))
CSV_CHUNK_SIZE_ROWS = int(os.getenv("NERAIUM_CSV_CHUNK_SIZE_ROWS", "5000"))
logger = logging.getLogger(__name__)


def _comparison_relationship_changes(
    active_model: dict[str, Any] | None,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare current correlations with the exact persisted behavioral model."""
    edges = ((active_model or {}).get("relationship_graph") or {}).get("edges") or []
    changes: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("mode_id") != "all_operation":
            continue
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        pairs = [
            (parse_numeric_value(row.get(source)), parse_numeric_value(row.get(target)))
            for row in rows
        ]
        pairs = [(left, right) for left, right in pairs if left is not None and right is not None]
        if len(pairs) < 20:
            continue
        left = [pair[0] for pair in pairs]
        right = [pair[1] for pair in pairs]
        left_mean, right_mean = sum(left) / len(left), sum(right) / len(right)
        numerator = sum((a - left_mean) * (b - right_mean) for a, b in pairs)
        denominator = math.sqrt(
            sum((a - left_mean) ** 2 for a in left)
            * sum((b - right_mean) ** 2 for b in right)
        )
        current = numerator / denominator if denominator else 0.0
        baseline = float(edge.get("correlation") or edge.get("strength") or 0.0)
        delta = abs(current - baseline)
        if delta < 0.25:
            continue
        changes.append({
            "id": edge.get("edge_id"),
            "columns": [source, target],
            "relationship_type": "linear_correlation",
            "change_type": "weakened" if abs(current) < abs(baseline) else "strengthened",
            "baseline_strength": round(abs(baseline), 6),
            "current_strength": round(abs(current), 6),
            "baseline_correlation": round(baseline, 6),
            "recent_correlation": round(current, 6),
            "correlation_delta": round(delta, 6),
            "signed_correlation_delta": round(current - baseline, 6),
            "baseline_sample_size": int(edge.get("sample_count") or 0),
            "recent_sample_size": len(pairs),
            "confidence_score": min(0.99, 0.75 + min(len(pairs), 500) / 2500),
            "persistence_score": 1.0,
            "relationship_importance_score": round(delta * 100, 3),
            "relationship_importance_rationale": (
                f"The persistent {source} / {target} relationship moved outside the exact learned baseline."
            ),
        })
    # One physical degradation can disturb several correlated signals. Surface
    # the strongest independent relationship rather than duplicating one event
    # into multiple operator findings.
    return sorted(changes, key=lambda item: item["correlation_delta"], reverse=True)[:1]


def _log_processing_event(event: str, job_id: str, *, filename: str | None = None, **fields: Any) -> None:
    scope = current_dataset_scope()
    normalized = {
        "event": event,
        "correlation_id": job_id,
        "dataset_id": fields.get("dataset_id") or job_id,
        "upload_id": fields.get("upload_id") or job_id,
        "user_id": scope.user_id,
        "organization_id": scope.tenant_id,
        "job_id": job_id,
        "source_filename": filename,
        **fields,
    }
    logger.info(
        "upload_processing_event %s",
        " ".join(
            f"{key}={str(value).replace(chr(10), ' ').replace(chr(13), ' ')[:500]}"
            for key, value in normalized.items()
            if value is not None
        ),
    )


_STAGE_TIMING_PHASES = {
    "reading_csv": "validation",
    "parsing_telemetry": "validation",
    "detecting_schema_signals": "validation",
    "cleaning_imputing_data": "validation",
    "profiling_data_quality": "validation",
    "building_baseline": "baseline_creation",
    "scoring_drift_relationships": "mapping",
    "building_fingerprint": "comparison",
    "generating_findings_evidence": "evidence_generation",
    "writing_result_replay": "persistence",
    "saving_result": "persistence",
    "finalizing_report": "persistence",
    "complete": "persistence",
}
_JOB_TIMING_CONTEXTS: dict[str, dict[str, Any]] = {}
_JOB_TIMING_LOCK = threading.Lock()


def _begin_job_timing(job_id: str, initial_timings: dict[str, Any] | None = None) -> None:
    now = time.perf_counter()
    with _JOB_TIMING_LOCK:
        _JOB_TIMING_CONTEXTS[str(job_id)] = {
            "started_perf": now,
            "phase": None,
            "phase_started_perf": now,
            "durations_ms": {
                key: float(value)
                for key, value in dict(initial_timings or {}).items()
                if key.endswith("_ms") and isinstance(value, (int, float))
            },
        }


def _timing_snapshot_locked(context: dict[str, Any], now: float) -> dict[str, Any]:
    durations = dict(context.get("durations_ms") or {})
    phase = context.get("phase")
    if phase:
        key = f"{phase}_ms"
        durations[key] = round(
            float(durations.get(key, 0.0)) + max(0.0, now - float(context["phase_started_perf"])) * 1000,
            3,
        )
    durations["total_job_ms"] = round(max(0.0, now - float(context["started_perf"])) * 1000, 3)
    durations["parse_seconds"] = round(float(durations.get("validation_ms", 0.0)) / 1000, 6)
    durations["baseline_build_seconds"] = round(float(durations.get("baseline_creation_ms", 0.0)) / 1000, 6)
    structural_ms = sum(float(durations.get(key, 0.0)) for key in ("mapping_ms", "comparison_ms", "evidence_generation_ms"))
    durations["structural_scoring_seconds"] = round(structural_ms / 1000, 6)
    durations["total_job_seconds"] = round(float(durations["total_job_ms"]) / 1000, 6)
    return durations


def _advance_job_timing(job_id: str, stage: str) -> tuple[dict[str, Any], str | None, float | None]:
    now = time.perf_counter()
    phase = _STAGE_TIMING_PHASES.get(str(stage), str(stage))
    with _JOB_TIMING_LOCK:
        context = _JOB_TIMING_CONTEXTS.setdefault(
            str(job_id),
            {"started_perf": now, "phase": None, "phase_started_perf": now, "durations_ms": {}},
        )
        previous_phase = context.get("phase")
        completed_ms = None
        if previous_phase != phase:
            if previous_phase:
                key = f"{previous_phase}_ms"
                completed_ms = max(0.0, now - float(context["phase_started_perf"])) * 1000
                context["durations_ms"][key] = round(
                    float(context["durations_ms"].get(key, 0.0)) + completed_ms,
                    3,
                )
            context["phase"] = phase
            context["phase_started_perf"] = now
        return _timing_snapshot_locked(context, now), previous_phase if previous_phase != phase else None, completed_ms


def _job_timing_snapshot(job_id: str) -> dict[str, Any]:
    now = time.perf_counter()
    with _JOB_TIMING_LOCK:
        context = _JOB_TIMING_CONTEXTS.get(str(job_id))
        return _timing_snapshot_locked(context, now) if context else {}


def _finish_job_timing(job_id: str, *, completion_write_ms: float = 0.0) -> dict[str, Any]:
    now = time.perf_counter()
    with _JOB_TIMING_LOCK:
        context = _JOB_TIMING_CONTEXTS.pop(str(job_id), None)
        if not context:
            return {"completion_write_ms": round(max(0.0, completion_write_ms), 3)}
        snapshot = _timing_snapshot_locked(context, now)
    snapshot["completion_write_ms"] = round(max(0.0, completion_write_ms), 3)
    return snapshot



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
    from app.services.evidence_store import configure_runtime_dir as configure_evidence_dir
    from app.services.runtime_db import configure_runtime_dir as configure_runtime_db_dir, init_runtime_db

    configure_evidence_dir(RUNTIME_DIR)
    configure_runtime_db_dir(RUNTIME_DIR)
    init_runtime_db()
    _invalidate_router_latest_cache()


def _read_upload_status_from_recorded_runtime(job_id: str) -> dict[str, Any] | None:
    runtime_dir = JOB_RUNTIME_DIRS.get(str(job_id))
    if runtime_dir is None:
        return None
    path = Path(runtime_dir) / f"upload_status_{job_id}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def read_upload_status(job_id: str) -> dict[str, Any] | None:
    status = repository_read_upload_status(job_id)
    if isinstance(status, dict):
        return status
    status = _read_upload_status_from_recorded_runtime(str(job_id))
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
    existing = read_upload_status(job_id) or {}
    scope = dataset_scope_from_payload(existing) or current_dataset_scope()
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
    dataset_id = existing.get("dataset_id") or job_id
    payload["session_scope"] = build_session_scope(
        job_id,
        filename=payload.get("filename"),
        status=str(status).lower(),
        dataset_scope=scope,
        dataset_id=dataset_id,
    )
    payload = attach_dataset_scope(payload, scope=scope, dataset_id=dataset_id)
    UPLOAD_RUNTIME_STATE.cache_job(job_id, payload)
    JOB_RUNTIME_DIRS[job_id] = RUNTIME_DIR
    while len(JOB_RUNTIME_DIRS) > UPLOAD_RUNTIME_STATE.max_cached_jobs:
        JOB_RUNTIME_DIRS.pop(next(iter(JOB_RUNTIME_DIRS)))
    repository_write_upload_status_progress(job_id, payload, latest_summary=payload, keep_result=False)
    cache_latest_upload_payload("summary", payload)
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
    UPLOAD_RUNTIME_STATE.cache_job(job_id, summary)
    cache_latest_upload_payload("result", project_result_for_transport(result) or result)
    cache_latest_upload_payload("summary", {**summary, "transport_result_available": True})

    try:
        upsert_upload_job(summary)
    except Exception:
        pass

    return summary


def _persist_completed_upload(job_id: str, *, result: dict[str, Any], summary: dict[str, Any]) -> None:
    # write_upload_completion already publishes the job status, latest summary,
    # result, and canonical record. Repeating write_upload_status_progress here
    # doubled the largest persistence payload and added avoidable commits.
    repository_write_upload_completion(job_id, result=result, summary=summary)
    try:
        complete_upload_queue_job(job_id, "completed")
    except Exception:
        pass
    UPLOAD_RUNTIME_STATE.cache_job(job_id, summary)
    cache_latest_upload_payload("result", project_result_for_transport(result) or result)
    cache_latest_upload_payload("summary", {**summary, "transport_result_available": True})



REQUIRED_SII_COMPLETION_ARTIFACTS = (
    "evidence_persisted",
    "relationships_persisted",
    "behavioral_structure_persisted",
    "baseline_persisted",
    "final_result_persisted",
    "terminal_backend_state_published",
)


def _artifact_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _relationship_model_persisted(result: dict[str, Any]) -> bool:
    relationship_model = result.get("relationship_model") if isinstance(result.get("relationship_model"), dict) else {}
    baseline = result.get("baseline_analysis") if isinstance(result.get("baseline_analysis"), dict) else {}
    return bool(
        isinstance(relationship_model, dict)
        and (
            "relationship_graph" in relationship_model
            or "baseline_relationships" in relationship_model
            or "top_relationship_changes" in relationship_model
        )
    ) or bool(
        isinstance(baseline, dict)
        and (
            "relationship_graph" in baseline
            or "baseline_relationships" in baseline
            or "top_relationship_changes" in baseline
        )
    )


def _build_sii_completion_artifacts(
    result: dict[str, Any],
    *,
    evidence_persisted: bool,
    final_result_persisted: bool = False,
    terminal_backend_state_published: bool = False,
    compatibility_mode: bool = False,
) -> dict[str, bool]:
    baseline = result.get("baseline_analysis") if isinstance(result.get("baseline_analysis"), dict) else {}
    analysis_result = result.get("analysis_result") if isinstance(result.get("analysis_result"), dict) else {}
    processing_trace = result.get("processing_trace") if isinstance(result.get("processing_trace"), dict) else {}
    return {
        "evidence_persisted": bool(evidence_persisted),
        "relationships_persisted": _relationship_model_persisted(result),
        "behavioral_structure_persisted": bool(result.get("sii_intelligence") and result.get("engine_result") and analysis_result.get("fingerprint")),
        "baseline_persisted": bool(baseline and ("baseline_window_rows" in baseline or "columns_analyzed" in baseline or "relationship_graph" in baseline)),
        "final_result_persisted": bool(final_result_persisted),
        "terminal_backend_state_published": bool(terminal_backend_state_published),
        "intelligence_present": bool(result.get("sii_intelligence")),
        "processing_trace_present": bool(processing_trace),
        "engine_result_present": bool(result.get("engine_result")),
        "analysis_result_present": bool(analysis_result),
        "compatibility_mode": bool(compatibility_mode),
    }


def _missing_sii_completion_artifacts(artifacts: dict[str, Any]) -> list[str]:
    return [key for key in REQUIRED_SII_COMPLETION_ARTIFACTS if not _artifact_bool(artifacts.get(key))]

def _finalize_completed_upload(
    *,
    job_id: str,
    filename: str,
    now: str,
    initiated_by: str,
    baseline_reliable: bool,
    row_count_total: int,
    result: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    finalized_result = dict(result)
    if str(finalized_result.get("workflow") or "") == WORKFLOW_ANALYZE_NEW_DATA:
        stamp_comparison_analysis_identity(finalized_result)
    finalized_summary = dict(summary)
    finalization = {
        "state": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "label": "Finalizing report...",
        "non_blocking": True,
        "errors": [],
    }
    finalized_result["report_finalization"] = dict(finalization)
    finalized_summary["report_finalization"] = dict(finalization)

    try:
        latest_sii = read_latest_sii_state()
        if isinstance(latest_sii, dict):
            _write_shared_state("latest_sii_state", latest_sii)
    except Exception as exc:
        finalization["errors"].append(f"latest_sii_state: {exc}")

    evidence_persisted = False
    try:
        from app.services.evidence_store import read_evidence_run, upsert_evidence_run

        record = upsert_evidence_run(
            build_evidence_record_from_result(
                run_id=job_id,
                filename=filename,
                source_type="csv_upload",
                result=finalized_result,
                created_at=now,
                completed_at=now,
                status="completed",
                initiated_by=initiated_by,
                rows_received=finalized_result["ingestion_report"]["rows_received"],
                rows_accepted=row_count_total,
                rows_rejected=finalized_result["ingestion_report"]["rows_dropped"],
            )
        )
        persisted_record = read_evidence_run(job_id)
        evidence_persisted = bool(persisted_record and persisted_record.get("run_id") == job_id)
        finalized_result["evidence_persistence"] = {
            **dict(finalized_result.get("evidence_persistence") or {}),
            "persisted": evidence_persisted,
            "record_status": persisted_record.get("status") if persisted_record else None,
        }
        finalized_summary["evidence_persisted"] = evidence_persisted
        if isinstance(record, dict):
            dispatch_observation_notification(record)
    except Exception as exc:
        finalization["errors"].append(f"evidence_persistence: {exc}")

    if not evidence_persisted:
        raise RuntimeError("evidence_persistence_failed")

    finalization["completed_at"] = datetime.now(timezone.utc).isoformat()
    finalization["state"] = "complete" if not finalization["errors"] else "degraded"
    finalized_result["report_finalization"] = dict(finalization)
    finalized_summary["report_finalization"] = dict(finalization)
    finalized_result["sii_reliable_enough_to_show"] = bool(baseline_reliable)
    finalized_summary["sii_reliable_enough_to_show"] = bool(baseline_reliable)

    artifacts = _build_sii_completion_artifacts(
        finalized_result,
        evidence_persisted=evidence_persisted,
        final_result_persisted=True,
        terminal_backend_state_published=True,
        compatibility_mode=False,
    )
    missing_artifacts = _missing_sii_completion_artifacts(artifacts)
    if missing_artifacts:
        raise RuntimeError(f"sii_completion_artifacts_missing:{','.join(missing_artifacts)}")

    processing_trace = finalized_result.get("processing_trace") if isinstance(finalized_result.get("processing_trace"), dict) else {}
    processing_trace = {**processing_trace, "sii_completed": True, "completed_at": finalization["completed_at"]}
    finalized_result["processing_trace"] = processing_trace
    finalized_result["sii_completed"] = True
    finalized_result["sii_completion_artifacts"] = artifacts
    finalized_result["status"] = "COMPLETE"
    finalized_result["processing_state"] = "complete"
    finalized_summary.update({
        "status": "COMPLETE",
        "processing_state": "complete",
        "percent": 100,
        "progress": 100,
        "progress_label": "Analysis ready.",
        "message": "Analysis ready.",
        "propagation_stage": "complete",
        "propagation_progress": 100,
        "propagation_label": "Analysis ready.",
        "result_available": True,
        "first_usable_available": True,
        "sii_completed": True,
        "evidence_persisted": True,
        "sii_completion_artifacts": artifacts,
    })
    finalized_summary["result_summary"] = {
        **dict(finalized_summary.get("result_summary") or {}),
        "filename": filename,
        "sii_completed": True,
        "sii_completion_artifacts": artifacts,
        "runner_errors": [],
    }
    finalized_summary.update(canonical_stage_payload(legacy_stage="complete", status="COMPLETE", progress=100, label="Analysis ready."))
    terminal_stage_changed_at = datetime.now(timezone.utc).isoformat()
    finalized_summary["stage_changed_at"] = terminal_stage_changed_at
    finalized_summary["updated_at"] = terminal_stage_changed_at
    finalized_result["stage_changed_at"] = terminal_stage_changed_at
    timing_snapshot = _job_timing_snapshot(job_id)
    finalized_summary["timings"] = {**dict(finalized_summary.get("timings") or {}), **timing_snapshot}
    processing_stats = dict(finalized_result.get("processing_stats") or {})
    processing_stats["timings"] = {**dict(processing_stats.get("timings") or {}), **timing_snapshot}
    finalized_result["processing_stats"] = processing_stats
    persistence_started = time.perf_counter()
    _persist_completed_upload(job_id, result=finalized_result, summary=finalized_summary)
    persist_completed_analysis(finalized_result)
    completion_write_ms = (time.perf_counter() - persistence_started) * 1000
    completed_timings = _finish_job_timing(job_id, completion_write_ms=completion_write_ms)
    logger.info(
        "upload_stage_timing event=job_completed job_id=%s total_job_ms=%s validation_ms=%s mapping_ms=%s baseline_creation_ms=%s comparison_ms=%s evidence_generation_ms=%s persistence_ms=%s completion_write_ms=%s",
        job_id,
        completed_timings.get("total_job_ms"),
        completed_timings.get("validation_ms"),
        completed_timings.get("mapping_ms"),
        completed_timings.get("baseline_creation_ms"),
        completed_timings.get("comparison_ms"),
        completed_timings.get("evidence_generation_ms"),
        completed_timings.get("persistence_ms"),
        completed_timings.get("completion_write_ms"),
    )


def _start_optional_upload_finalization(**kwargs: Any) -> None:
    if os.getenv("PYTEST_CURRENT_TEST") is not None:
        _finalize_completed_upload(**kwargs)
        return
    thread = threading.Thread(
        target=_finalize_completed_upload,
        kwargs=kwargs,
        daemon=True,
        name=f"neraium-upload-finalize-{str(kwargs.get('job_id') or '')[:8]}",
    )
    thread.start()


def _set_propagation_stage(job_id: str, *, stage: str, progress: int, label: str) -> None:
    timings, completed_phase, completed_ms = _advance_job_timing(job_id, stage)
    current = read_job(job_id) or read_upload_status(job_id) or {"job_id": job_id}
    bounded_progress = int(max(0, min(100, progress)))
    stage_changed_at = datetime.now(timezone.utc).isoformat()
    pending_stages = {"queued", "accepted", "reading_csv"}
    payload = {
        **current,
        "job_id": job_id,
        "status": "PROCESSING" if stage not in {*pending_stages, "complete"} else ("PENDING" if stage in pending_stages else "COMPLETE"),
        "processing_state": stage,
        "percent": bounded_progress,
        "progress": bounded_progress,
        "progress_label": label,
        "message": label,
        "propagation_stage": stage,
        "propagation_progress": bounded_progress,
        "propagation_label": label,
        "updated_at": stage_changed_at,
        "stage_changed_at": stage_changed_at,
        "timings": {**dict(current.get("timings") or {}), **timings},
    }
    payload.update(canonical_stage_payload(legacy_stage=stage, status=payload["status"], progress=progress, label=label))
    persistence_started = time.perf_counter()
    write_job(payload)
    stage_persist_ms = (time.perf_counter() - persistence_started) * 1000
    logger.info(
        "upload_stage_timing event=stage_entered dataset_id=%s job_id=%s request_id=%s stage=%s phase=%s previous_phase=%s previous_phase_ms=%s stage_persist_ms=%.3f total_job_ms=%s",
        current.get("dataset_id") or job_id,
        job_id,
        current.get("request_id"),
        stage,
        _STAGE_TIMING_PHASES.get(stage, stage),
        completed_phase,
        round(completed_ms, 3) if completed_ms is not None else None,
        stage_persist_ms,
        timings.get("total_job_ms"),
    )


def _progress_label(stage: str, *, row_count: int | None = None, signal_count: int | None = None) -> str:
    if stage == "reading_csv":
        return "Validating CSV..."
    if stage == "parsing_telemetry":
        return f"Normalizing telemetry... {row_count:,} rows read." if row_count else "Normalizing telemetry..."
    if stage == "detecting_schema_signals":
        return "Validating CSV..."
    if stage == "cleaning_imputing_data":
        return "Normalizing telemetry..."
    if stage == "profiling_data_quality":
        return "Normalizing telemetry..."
    if stage == "building_baseline":
        return "Identifying systems..."
    if stage == "scoring_drift_relationships":
        return "Mapping relationships..."
    if stage == "building_fingerprint":
        return "Building fingerprint..."
    if stage == "generating_findings_evidence":
        return "Generating insights..."
    if stage in {"writing_result_replay", "saving_result"}:
        return "Saving result..."
    if stage == "finalizing_report":
        return "Finalizing report..."
    if stage == "complete":
        return "Analysis ready."
    return "Still processing..."


def _detect_delimiter(sample: str) -> str:
    return detect_delimiter(sample)


def _row_tokens(line: str, delimiter: str) -> list[str]:
    return row_tokens(line, delimiter)


def _looks_like_header(tokens: list[str]) -> bool:
    return looks_like_header(tokens)


def _normalized_columns(tokens: list[str], *, header_present: bool) -> list[str]:
    return normalized_columns(tokens, header_present=header_present)


def _stream_csv_snapshot(path: Path, *, max_analysis_rows: int | None, job_id: str | None = None) -> dict[str, Any]:
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
                "relationship_type": item.get("relationship_type"),
                "change_type": item.get("change_type"),
                "strength": item.get("strength"),
                "baseline_strength": item.get("baseline_strength"),
                "current_strength": item.get("current_strength"),
                "change_percentage": item.get("change_percentage"),
                "confidence_score": item.get("confidence_score"),
                "confidence_level": item.get("confidence_level"),
                "coupling_strength": item.get("coupling_strength"),
                "baseline_sample_size": item.get("baseline_sample_size"),
                "recent_sample_size": item.get("recent_sample_size"),
                "supporting_metric_pairs": item.get("supporting_metric_pairs"),
                "time_window": item.get("time_window"),
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
    job_context = read_job(job_id) or {}
    initiated_by = job_context.get("initiated_by", "anonymous")
    request_id = job_context.get("request_id")
    upload_session_id = job_context.get("upload_session_id") or job_id
    _set_propagation_stage(job_id, stage="cleaning_imputing_data", progress=45, label=_progress_label("cleaning_imputing_data"))
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

    _set_propagation_stage(job_id, stage="profiling_data_quality", progress=55, label=_progress_label("profiling_data_quality"))
    workflow = normalize_workflow(job_context.get("workflow") or WORKFLOW_LEGACY_ANALYSIS)
    if is_baseline_workflow(workflow):
        baseline_result = build_behavioral_baseline(
            job_id=job_id,
            filename=filename,
            columns=columns,
            rows=rows,
            numeric_columns=numeric_columns,
            timestamp_column=timestamp_column,
            row_count_total=row_count_total,
            numeric_profiles=numeric_profiles,
            ingestion_report=ingestion_report,
            workflow=workflow,
            approval_required=bool(job_context.get("approval_required", True)),
            active_model=read_active_behavioral_model(),
            stage_notifier=_set_propagation_stage,
            dataset_id=job_context.get("dataset_id") or job_id,
        )
        candidate = baseline_result["candidate_model"]
        suitability = baseline_result["baseline_suitability"]
        activation = baseline_result["activation"]
        now = baseline_result["completed_at"]
        summary = {
            "job_id": job_id,
            "run_id": job_id,
            "upload_id": job_id,
            "dataset_id": job_context.get("dataset_id") or job_id,
            "upload_session_id": upload_session_id,
            "request_id": request_id,
            "status_url": f"/api/data/upload-status/{job_id}",
            "baseline_result_url": f"/api/data/baselines/jobs/{job_id}",
            "status": "COMPLETE",
            "processing_state": "complete",
            "analysis_state": "completed",
            "workflow": workflow,
            "workflow_state": activation.get("state"),
            "percent": 100,
            "progress": 100,
            "progress_label": "Behavioral baseline candidate ready.",
            "message": "Behavioral baseline candidate ready.",
            "propagation_stage": "complete",
            "propagation_progress": 100,
            "propagation_label": "Behavioral baseline candidate ready.",
            "result_available": True,
            "baseline_result_available": True,
            "baseline_candidate_created": True,
            "baselineId": baseline_result.get("baselineId"),
            "workspacePath": baseline_result.get("workspacePath"),
            "createdAt": baseline_result.get("createdAt") or now,
            "jobId": job_id,
            "datasetId": job_context.get("dataset_id") or job_id,
            "baseline_model_id": candidate.get("model_id"),
            "baseline_model_version": candidate.get("version"),
            "baseline_activation_state": activation.get("state"),
            "baseline_suitability": {
                "decision": suitability.get("decision"),
                "score": suitability.get("score"),
                "eligible_for_activation": suitability.get("eligible_for_activation"),
            },
            "sii_completed": False,
            "sii_engine_invoked": False,
            "runner_used": False,
            "replay_ready": False,
            "replay_frame_count": 0,
            "evidence_persisted": False,
            "last_processed_at": now,
            "completed_at": now,
            "filename": filename,
            "row_count": row_count_total,
            "rows_processed": row_count_total,
            "columns_detected": len(columns),
            "initiated_by": initiated_by,
        }
        summary.update(
            canonical_stage_payload(
                legacy_stage="complete",
                status="COMPLETE",
                progress=100,
                label="Behavioral baseline candidate ready.",
            )
        )
        job_scope = dataset_scope_from_payload(job_context) or current_dataset_scope()
        summary["session_scope"] = build_session_scope(
            job_id,
            filename=filename,
            status="complete",
            dataset_scope=job_scope,
            dataset_id=job_context.get("dataset_id") or job_id,
        )
        summary = attach_dataset_scope(summary, scope=job_scope, dataset_id=job_context.get("dataset_id") or job_id)
        # Persist a non-terminal visibility state. The queue lifecycle reads
        # the committed result, then publishes this terminal summary atomically.
        write_job({
            **summary,
            "status": "PROCESSING",
            "processing_state": "saving_result",
            "analysis_state": "baseline_creation",
            "job_state": "processing",
            "terminal": False,
            "result_available": False,
            "baseline_result_available": False,
            "progress_label": "Verifying committed baseline result...",
            "message": "Verifying committed baseline result...",
            "propagation_stage": "saving_result",
            "propagation_progress": 99,
            "propagation_label": "Verifying committed baseline result...",
        })
        _finish_job_timing(job_id)
        return summary

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

    pipeline = run_structural_analysis_pipeline(
        job_id=job_id,
        filename=filename,
        columns=columns,
        rows=rows,
        numeric_columns=numeric_columns,
        timestamp_column=timestamp_column,
        row_count_total=row_count_total,
        matrix_rows_for_profiles=matrix_rows_for_profiles,
        numeric_profiles=numeric_profiles,
        room_summary=room_summary,
        room_intelligence=room_intelligence,
        room_names=room_names,
        overall_urgency=overall_urgency,
        telemetry_profile=telemetry_profile,
        telemetry_profile_confidence=telemetry_profile_confidence,
        telemetry_profile_signals=telemetry_profile_signals,
        operational_profile=operational_profile,
        operational_profile_confidence=operational_profile_confidence,
        operational_profile_signals=operational_profile_signals,
        operational_modality=operational_modality,
        ingestion_report=ingestion_report,
        chunk_count=chunk_count,
        memory_estimate_bytes=memory_estimate_bytes,
        processing_started_at=processing_started_at,
        build_replay=_build_replay,
        minimal_replay=_minimal_replay,
        build_upload_engine_result=_build_upload_engine_result,
        stage_notifier=_set_propagation_stage,
    )
    sii_result = pipeline["sii_result"]
    replay = pipeline["replay"]
    frame_count = pipeline["frame_count"]
    now = pipeline["now"]
    timestamp_profile = pipeline["timestamp_profile"]
    baseline_analysis = pipeline["baseline_analysis"]
    telemetry_signal_catalog = pipeline.get("telemetry_signal_catalog", {})
    cultivation_mapping = pipeline["cultivation_mapping"]
    baseline_reliable = pipeline["baseline_reliable"]
    data_quality = pipeline["data_quality"]
    reliability_warning = pipeline["reliability_warning"]
    room_assessments = pipeline["room_assessments"]
    engine_result = pipeline["engine_result"]
    driver_attribution = pipeline["driver_attribution"]
    operator_report = pipeline["operator_report"]
    sii_intelligence = pipeline["sii_intelligence"]
    processing_time_seconds = pipeline["processing_time_seconds"]
    processing_trace = pipeline["processing_trace"]
    processing_trace["analysis_sample_rows"] = len(rows)
    processing_trace["analysis_population_rows"] = row_count_total
    processing_trace["analysis_sampling_applied"] = len(rows) < row_count_total
    processing_trace["analysis_sample_stride"] = int((ingestion_report or {}).get("analysis_sample_stride") or 1)
    runner_result = pipeline["runner_result"]
    latest_runner_state = pipeline["latest_runner_state"]
    relationship_model = pipeline["relationship_model"]
    mode_aware_suppressed = bool(
        (processing_trace.get("mode_aware_authority") or {}).get("applied")
    )
    effective_urgency = "nominal" if mode_aware_suppressed else overall_urgency

    job_scope = dataset_scope_from_payload(job_context) or current_dataset_scope()
    facility_context = read_facility_context()
    baseline_id = str(job_context.get("active_baseline_model_id") or "").strip() or None
    baseline_dataset_id = str(job_context.get("active_baseline_dataset_id") or "").strip() or None
    comparison_dataset_id = str(job_context.get("dataset_id") or "").strip() or None
    configured_systems = [
        item for item in facility_context.get("systems", []) if isinstance(item, dict)
    ]
    site_id = str(facility_context.get("site_id") or job_scope.workspace_id).strip()
    system_id = str(
        job_context.get("active_baseline_system_id")
        or (configured_systems[0].get("system_id") if configured_systems else None)
        or job_scope.workspace_id
    ).strip()
    active_baseline_model = read_active_behavioral_model()
    active_baseline_hash = (
        canonical_digest(active_baseline_model)
        if isinstance(active_baseline_model, dict)
        and str(active_baseline_model.get("model_id") or "") == str(baseline_id or "")
        else None
    )
    if workflow == WORKFLOW_ANALYZE_NEW_DATA and isinstance(active_baseline_model, dict):
        exact_baseline_changes = _comparison_relationship_changes(active_baseline_model, rows)
        if exact_baseline_changes:
            relationship_model = {
                **(relationship_model if isinstance(relationship_model, dict) else {}),
                "top_relationship_changes": exact_baseline_changes,
                "baseline_relationships": (active_baseline_model.get("relationship_graph") or {}).get("edges", []),
            }
            baseline_analysis = {
                **(baseline_analysis if isinstance(baseline_analysis, dict) else {}),
                "relationship_drift": exact_baseline_changes,
                "top_relationship_changes": exact_baseline_changes,
                "baseline_model_id": active_baseline_model.get("model_id"),
            }
    if workflow == WORKFLOW_ANALYZE_NEW_DATA:
        if not baseline_id or not baseline_dataset_id or not comparison_dataset_id:
            raise ValueError("analysis_identity_incomplete")
        if comparison_dataset_id == baseline_dataset_id:
            raise ValueError("comparison_dataset_matches_baseline_dataset")
    comparison_identity = (
        {
            "baseline_id": baseline_id,
            "baseline_dataset_id": baseline_dataset_id,
            "comparison_dataset_id": comparison_dataset_id,
            "comparison_analysis_id": job_id,
            "analysis_run_id": job_id,
        }
        if workflow == WORKFLOW_ANALYZE_NEW_DATA
        else {}
    )
    result = {
        "job_id": job_id,
        "run_id": job_id,
        "upload_id": job_id,
        "organization_id": job_scope.tenant_id,
        "portfolio_id": job_scope.workspace_id,
        "site_id": site_id,
        "system_id": system_id,
        "facility_context_reference": {
            "contract_version": facility_context.get("contract_version"),
            "site_id": site_id,
            "site_name": facility_context.get("site_name"),
            "system_id": system_id,
            "signal_mapping_count": len(facility_context.get("signal_mappings") or []),
            "updated_at": facility_context.get("updated_at"),
        },
        **comparison_identity,
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
            "schema_detection": dict(ingestion_report.get("schema_detection") or {}),
            "analysis_gate_state": ingestion_report.get("analysis_gate_state"),
            "data_quality_messages": list(ingestion_report.get("data_quality_messages") or []),
            "sample_interval_seconds": ingestion_report.get("sample_interval_seconds"),
            "imputation_report": dict(ingestion_report.get("imputation_report") or {}),
            "delimiter": ingestion_report.get("delimiter", ","),
            "header_present": bool(ingestion_report.get("header_present", True)),
            "input_hash": ingestion_report.get("input_hash"),
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
        "sii_result": sii_result,
        "baseline_analysis": baseline_analysis,
        "telemetry_signal_catalog": telemetry_signal_catalog,
        "telemetry_signals": list(telemetry_signal_catalog.values()) if isinstance(telemetry_signal_catalog, dict) else telemetry_signal_catalog,
        "cultivation_mapping": cultivation_mapping,
        "operator_report": operator_report,
        "engine_result": engine_result,
        "relationship_model": relationship_model,
        "driver_attribution": driver_attribution,
        "operating_state": "Baseline-aligned" if effective_urgency == "nominal" else ("Structural drift observed" if effective_urgency == "review" else "Persistent structural drift observed"),
        "drift_status": "info" if effective_urgency == "nominal" else ("review" if effective_urgency == "review" else "unstable"),
        "sii_intelligence": sii_intelligence,
        "sii_runner_result": runner_result,
        "processing_trace": processing_trace,
        "processing_stats": {
            "used_streaming": True,
            "sampled_rows": len(rows),
            "analysis_population_rows": row_count_total,
            "analysis_sampling_applied": len(rows) < row_count_total,
            "analysis_sample_stride": int((ingestion_report or {}).get("analysis_sample_stride") or 1),
            "chunk_count": chunk_count,
            "memory_estimate_bytes": memory_estimate_bytes,
            "processing_time_seconds": processing_time_seconds,
        },
        "room_summary": room_summary,
        "ingestion_metadata": {"source_type": "csv_upload"},
        "source_type": "csv",
        "replay_timeline": replay,
        "replay_ready": frame_count > 0,
        "replay_frame_count": frame_count,
        "last_processed_at": now,
        "completed_at": now,
        "request_id": request_id,
        "upload_session_id": upload_session_id,
        "workflow": workflow,
        "active_baseline_reference": (
            {
                "model_id": job_context.get("active_baseline_model_id"),
                "version": job_context.get("active_baseline_version"),
                "dataset_id": job_context.get("active_baseline_dataset_id"),
                "model_hash": active_baseline_hash,
            }
            if workflow != WORKFLOW_LEGACY_ANALYSIS
            else None
        ),
    }
    result["initiated_by"] = initiated_by
    result["session_scope"] = build_session_scope(
        job_id,
        filename=filename,
        status="active",
        dataset_scope=job_scope,
        dataset_id=job_context.get("dataset_id") or job_id,
    )
    result = attach_dataset_scope(result, scope=job_scope, dataset_id=job_context.get("dataset_id") or job_id)
    result["traceability"] = build_traceability_packet(job_id=job_id, filename=filename, result=result)
    result["decision_integrity"] = dict(result["traceability"])
    if isinstance(latest_runner_state, dict):
        result["sii_intelligence"]["sii_runner_latest_state"] = latest_runner_state
        result["sii_intelligence"]["instability_index"] = latest_runner_state.get("instability_index")
        result["sii_intelligence"]["review_window"] = latest_runner_state.get("review_window") or latest_runner_state.get("projected_time_to_failure")
        result["sii_intelligence"]["review_window_hours"] = latest_runner_state.get("review_window_hours") or latest_runner_state.get("projected_time_to_failure_hours")
        result["sii_intelligence"]["projected_time_to_failure"] = result["sii_intelligence"]["review_window"]
        result["sii_intelligence"]["projected_time_to_failure_hours"] = result["sii_intelligence"]["review_window_hours"]
    result["sii_intelligence"]["decision_integrity"] = dict(result["traceability"])
    normalized_telemetry = build_normalized_telemetry(
        rows=rows,
        columns=columns,
        numeric_columns=numeric_columns,
        timestamp_column=timestamp_column,
        timestamp_profile=timestamp_profile,
        data_quality=data_quality,
        ingestion_report=result["ingestion_report"],
        source_file=filename,
        telemetry_signal_catalog=telemetry_signal_catalog,
    )
    result = attach_domain_interpretations(
        result,
        DomainInterpretationContext(
            columns=columns,
            engine_result=engine_result,
            relationship_model=relationship_model if isinstance(relationship_model, dict) else {},
            baseline_analysis=baseline_analysis,
            normalized_telemetry=normalized_telemetry,
            telemetry_signal_catalog=telemetry_signal_catalog,
            timestamp_profile=timestamp_profile,
            data_quality=data_quality,
            operating_mode=data_quality.get("operating_mode") if isinstance(data_quality, dict) else None,
            upload_id=job_id,
            analysis_id=job_id,
        ),
    )
    result["analysis_explanation"] = build_analysis_explanation(result)
    result["conditions"] = ConditionCorroborationService().build_conditions(
        relationships=result["analysis_explanation"].get("relationships", []),
        findings=result["analysis_explanation"].get("insights", []),
        rows=rows,
        timestamp_column=timestamp_column,
        baseline_analysis=baseline_analysis,
        data_quality=data_quality,
        operating_mode=data_quality.get("operating_mode"),
        telemetry_signal_catalog=telemetry_signal_catalog,
        site_name=result.get("facility_name") or result.get("site_name"),
        generated_at=now,
    )
    result["analysis_explanation"]["conditions"] = result["conditions"]
    result["analysis_explanation"]["primary_object"] = "condition" if result["conditions"] else "finding"
    result["analysis"] = result["analysis_explanation"]
    result = attach_analysis_result(result, normalized_telemetry=normalized_telemetry)

    result["sii_reliable_enough_to_show"] = bool(baseline_reliable)
    result["report_finalization"] = {
        "state": "pending",
        "label": _progress_label("finalizing_report"),
        "non_blocking": True,
    }

    summary = {"job_id": job_id, "run_id": job_id, "upload_id": job_id, "upload_session_id": upload_session_id, "request_id": request_id, "status_url": f"/api/data/upload-status/{job_id}", "status": "COMPLETE", "processing_state": "complete", "percent": 100, "progress": 100, "propagation_stage": "complete", "propagation_progress": 100, "propagation_label": "Analysis ready.", "message": "Analysis ready.", "progress_label": "Analysis ready.", "result_available": True, "first_usable_available": True, "sii_completed": True, "replay_ready": frame_count > 0, "replay_frame_count": frame_count, "latest_replay_frames": frame_count, "replay_source": "persisted", "last_processed_at": now, "filename": filename, "row_count": row_count_total, "rows_received": result["ingestion_report"]["rows_received"], "rows_used": row_count_total, "rows_dropped": result["ingestion_report"]["rows_dropped"], "drop_reasons": result["ingestion_report"]["drop_reasons"], "processing_time_seconds": processing_time_seconds, "quality_warning": result["quality_warning"], "sii_reliable_enough_to_show": bool(baseline_reliable), "column_count": len(columns), "rows_processed": row_count_total, "columns_detected": len(columns), "chunk_count": chunk_count, "runner_used": bool((runner_result or {}).get("runner_used")), "runner_module": RUNNER_MODULE, "core_engine": (runner_result or {}).get("core_engine"), "sii_completion_artifacts": {"runner_used": True, "intelligence_present": True, "processing_trace_present": True, "engine_result_present": True}, "result_summary": {"filename": filename, "sii_completed": True, "sii_completion_artifacts": {"runner_used": True, "intelligence_present": True, "processing_trace_present": True, "engine_result_present": True}, "runner_errors": []}, "evidence_persisted": False, "report_finalization": dict(result["report_finalization"]) }
    summary.update(canonical_stage_payload(legacy_stage="complete", status="COMPLETE", progress=100, label="Analysis ready."))
    summary["initiated_by"] = initiated_by
    summary["workflow"] = workflow
    summary["active_baseline_reference"] = result.get("active_baseline_reference")
    summary["organization_id"] = result.get("organization_id")
    summary["portfolio_id"] = result.get("portfolio_id")
    summary["site_id"] = result.get("site_id")
    summary["system_id"] = result.get("system_id")
    summary["facility_context_reference"] = result.get("facility_context_reference")
    summary.update(comparison_identity)
    summary["session_scope"] = build_session_scope(
        job_id,
        filename=filename,
        status="active",
        dataset_scope=job_scope,
        dataset_id=job_context.get("dataset_id") or job_id,
    )
    summary = attach_dataset_scope(summary, scope=job_scope, dataset_id=job_context.get("dataset_id") or job_id)
    summary["traceability"] = dict(result["traceability"])
    summary["decision_integrity"] = dict(result["traceability"])

    _set_propagation_stage(job_id, stage="saving_result", progress=95, label=_progress_label("saving_result"))
    summary.update(canonical_stage_payload(legacy_stage="complete", status="COMPLETE", progress=100, label=_progress_label("complete")))
    _finalize_completed_upload(
        job_id=job_id,
        filename=filename,
        now=now,
        initiated_by=initiated_by,
        baseline_reliable=baseline_reliable,
        row_count_total=row_count_total,
        result=result,
        summary=summary,
    )
    return read_upload_status(job_id) or summary


def process_upload_bytes(filename: str, content: bytes, *, job_id: str | None = None) -> dict[str, Any]:
    if not content.strip():
        raise ValueError("CSV file is empty.")
    with NamedTemporaryFile(delete=False, suffix=safe_upload_suffix(filename)) as temp:
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
    water_tokens = (
        "pool",
        "spa",
        "orp",
        "chlorine",
        "ph_",
        "turbidity",
        "conductivity",
        "sanitizer",
        "filter",
        "filtration",
        "makeup_water",
        "chilled_water",
        "chw_",
        "delta_t",
        "chiller",
        "cooling_tower",
        "tower",
        "basin",
        "blowdown",
    )
    if any(token in col for col in lowered for token in water_tokens):
        signals = [col for col in columns if any(token in col.lower() for token in water_tokens)][:6]
        return ("commercial_water_systems", "high", signals or ["flow_rate"])
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
    water_tokens = (
        "flow_rate",
        "totalized_flow",
        "water_pressure",
        "tank_level",
        "turnover",
        "filter_pressure",
        "differential_pressure",
        "chilled_water",
        "chw_",
        "chiller",
        "turbidity",
        "conductivity",
        "cooling_tower",
        "blowdown",
    )
    if any(token in col for col in lowered for token in water_tokens):
        signals = [col for col in columns if any(token in col.lower() for token in water_tokens)][:6]
        return ("commercial_water_systems", "high", signals or ["flow_rate"], "continuous")
    if any(token in col for col in lowered for token in ("discharge_pressure", "bearing_temperature", "shaft_vibration", "vfd_frequency")):
        signals = [col for col in columns if any(token in col.lower() for token in ("pump", "pressure", "bearing", "vibration", "vfd"))][:5]
        return ("mechanical_systems", "high", signals or ["pump_amperage"], "continuous")
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

def _purge_local_upload_job_records() -> None:
    UPLOAD_RUNTIME_STATE.jobs.clear()
    JOB_RUNTIME_DIRS.clear()
    for pattern in ("upload_status_*.json", "upload_result_*.json"):
        for path in RUNTIME_DIR.glob(pattern):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    for directory in (JOB_DIR, LEGACY_JOB_DIR):
        for path in directory.glob("*.json"):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _purge_upload_runtime_tables() -> None:
    try:
        from app.services.runtime_db import clear_upload_runtime_tables

        clear_upload_runtime_tables()
    except Exception:
        logger.exception("reset_latest_upload_state_runtime_table_clear_failed")


def reset_latest_upload_state(*, purge_job_records: bool = False) -> None:
    reset_upload_state()
    if not purge_job_records:
        return
    _purge_local_upload_job_records()
    _purge_upload_runtime_tables()


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
    UPLOAD_QUEUE_LIFECYCLE.read_baseline_result = read_baseline_result
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


def _normalize_job_write_args(args: tuple[Any, ...]) -> tuple[str, dict[str, Any]]:
    if len(args) == 1 and isinstance(args[0], dict):
        payload = dict(args[0])
        job_id = str(payload.get("job_id") or uuid.uuid4().hex)
    else:
        job_id = str(args[0])
        payload = dict(args[1])
    payload["job_id"] = job_id
    return job_id, payload


def _scope_job_payload(job_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    existing = repository_read_upload_status(job_id) or {}
    scope = dataset_scope_from_payload(payload) or dataset_scope_from_payload(existing) or current_dataset_scope()
    clear_reset_block_persisted(scope)
    payload["run_id"] = job_id
    payload["upload_id"] = job_id
    payload.setdefault("upload_session_id", job_id)
    lifecycle_status = str(payload.get("processing_state") or payload.get("status") or "active").lower()
    dataset_id = str(payload.get("dataset_id") or existing.get("dataset_id") or job_id)
    payload["session_scope"] = build_session_scope(
        job_id,
        filename=payload.get("filename"),
        status=lifecycle_status,
        dataset_scope=scope,
        dataset_id=dataset_id,
    )
    return attach_dataset_scope(payload, scope=scope, dataset_id=dataset_id), scope


def _cache_job_payload(job_id: str, payload: dict[str, Any]) -> None:
    UPLOAD_RUNTIME_STATE.cache_job(job_id, payload)
    JOB_RUNTIME_DIRS[job_id] = RUNTIME_DIR
    while len(JOB_RUNTIME_DIRS) > UPLOAD_RUNTIME_STATE.max_cached_jobs:
        JOB_RUNTIME_DIRS.pop(next(iter(JOB_RUNTIME_DIRS)))


def _job_updates_latest(status_text: str, processing_state: str) -> bool:
    visible_statuses = {"PENDING", "QUEUED", "PROCESSING", "RUNNING_SII", "COMPLETE", "FAILED"}
    return status_text in visible_statuses or processing_state in VISIBLE_UPLOAD_STATES


def _latest_job_summary(job_id: str, payload: dict[str, Any], scope: Any, status_text: str, processing_state: str) -> dict[str, Any]:
    latest_summary = dict(payload)
    lifecycle_status = processing_state or status_text.lower() or "active"
    latest_summary.setdefault(
        "session_scope",
        build_session_scope(
            job_id,
            filename=latest_summary.get("filename"),
            status=lifecycle_status,
            dataset_scope=scope,
            dataset_id=latest_summary.get("dataset_id"),
        ),
    )
    latest_summary.setdefault("status_url", f"/api/data/upload-status/{job_id}")
    latest_summary.setdefault("percent", latest_summary.get("progress", 0))
    latest_summary.setdefault("progress", latest_summary.get("percent", 0))
    latest_summary.setdefault("result_available", status_text == "COMPLETE")
    latest_summary.setdefault("sii_completed", status_text == "COMPLETE")
    if status_text == "COMPLETE":
        latest_summary["transport_result_available"] = True
    latest_summary.setdefault("replay_ready", False)
    latest_summary.setdefault("replay_frame_count", 0)
    latest_summary.setdefault("latest_replay_frames", latest_summary.get("replay_frame_count", 0))
    latest_summary.setdefault("propagation_stage", processing_state or "queued")
    latest_summary.setdefault("propagation_progress", latest_summary.get("progress", 0))
    latest_summary.setdefault("propagation_label", latest_summary.get("message") or "Queued.")
    latest_summary.update(
        canonical_stage_payload(
            legacy_stage=latest_summary.get("propagation_stage"),
            status=latest_summary.get("status"),
            progress=latest_summary.get("propagation_progress"),
            label=latest_summary.get("propagation_label"),
        )
    )
    return latest_summary


def _persist_job_record(job_id: str, payload: dict[str, Any]) -> None:
    try:
        upsert_upload_job(payload)
    except Exception:
        pass
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    (JOB_DIR / f"{job_id}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def write_job(*args) -> None:
    job_id, payload = _normalize_job_write_args(args)
    payload, scope = _scope_job_payload(job_id, payload)
    _cache_job_payload(job_id, payload)
    status_text = str(payload.get("status") or "").upper()
    processing_state = str(payload.get("processing_state") or "").lower()
    if is_baseline_workflow(payload.get("workflow")):
        # Baseline construction has its own latest-candidate/active-model state.
        # Its progress must never replace the latest SII analysis snapshot.
        write_upload_status(job_id, payload)
    elif _job_updates_latest(status_text, processing_state):
        latest_summary = _latest_job_summary(job_id, payload, scope, status_text, processing_state)
        repository_write_upload_status_progress(
            job_id,
            payload,
            latest_summary=latest_summary,
            keep_result=status_text == "COMPLETE",
        )
        cache_latest_upload_payload("summary", latest_summary)
    else:
        write_upload_status(job_id, payload)
    _persist_job_record(job_id, payload)


def read_job(job_id: str) -> dict[str, Any] | None:
    return read_upload_status(job_id)


async def create_upload_job(upload_file: Any = None, filename: str = "upload.csv", **kwargs) -> dict[str, Any]:
    max_size_bytes = int(kwargs.get("max_size_bytes", 10 * 1024 * 1024 * 1024))
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
        "percent": 5,
        "progress": 5,
        "progress_label": "Worker starting...",
        "message": "Worker starting...",
        "propagation_stage": "queued",
        "propagation_progress": 5,
        "propagation_label": "Worker starting...",
    }
    payload.update(canonical_stage_payload(legacy_stage="queued", status=payload["status"], progress=5, label="Worker starting..."))
    write_job(job_id, payload)
    return payload


def process_csv_content(content: str | bytes, filename: str = "upload.csv", **kwargs) -> dict[str, Any]:
    if isinstance(content, str):
        content = content.encode("utf-8")
    summary = process_upload_bytes(filename, content, job_id=kwargs.get("job_id"))
    if is_baseline_workflow(summary.get("workflow")):
        return read_baseline_result(summary["job_id"]) or {}
    return read_upload_result_by_job_id(summary["job_id"]) or read_current_upload_result() or {}


def process_csv_file(path: str | os.PathLike[str], **kwargs) -> dict[str, Any]:
    p = Path(kwargs.pop("file_path", path))
    filename = kwargs.pop("filename", None) or p.name
    job_id = str(kwargs.pop("job_id", None) or uuid.uuid4().hex)

    if not p.exists():
        raise FileNotFoundError(str(p))

    input_hash = file_digest(p)

    snapshot: dict[str, Any] | None = None
    processing_started_at = time.perf_counter()
    existing_job = read_job(job_id) or {}
    baseline_workflow = is_baseline_workflow(existing_job.get("workflow"))
    _begin_job_timing(job_id, dict(existing_job.get("timings") or {}))

    if job_id:
        _set_propagation_stage(job_id, stage="reading_csv", progress=10, label=_progress_label("reading_csv"))

    try:
        trace_fields = {
            "dataset_id": existing_job.get("dataset_id") or job_id,
            "request_id": existing_job.get("request_id"),
        }
        _log_processing_event("parsing_started", job_id, filename=filename, processing_stage="csv_parsing", **trace_fields)
        _log_processing_event("validation_started", job_id, filename=filename, processing_stage="validation", **trace_fields)
        snapshot = _stream_csv_snapshot(
            p,
            max_analysis_rows=parse_positive_int_env(
                "NERAIUM_MAX_INGESTION_ANALYSIS_ROWS",
                MAX_INGESTION_ANALYSIS_ROWS,
            ),
            job_id=job_id,
        )

        _log_processing_event(
            "parsing_completed",
            job_id,
            filename=filename,
            processing_stage="csv_parsing",
            **trace_fields,
            row_count=snapshot.get("row_count"),
            column_count=len(snapshot.get("columns") or []),
        )
        _log_processing_event(
            "validation_completed",
            job_id,
            filename=filename,
            processing_stage="validation",
            **trace_fields,
            row_count=snapshot.get("row_count"),
            column_count=len(snapshot.get("columns") or []),
        )

        _set_propagation_stage(
            job_id,
            stage="detecting_schema_signals",
            progress=35,
            label=_progress_label("detecting_schema_signals", signal_count=len(snapshot["columns"])),
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
                "schema_detection": snapshot.get("schema_detection", {}),
                "analysis_gate_state": snapshot.get("analysis_gate_state"),
                "data_quality_messages": snapshot.get("data_quality_messages", []),
                "sample_interval_seconds": snapshot.get("sample_interval_seconds"),
                "imputation_report": snapshot.get("imputation_report", {}),
                "analysis_sample_rows": snapshot.get("analysis_sample_rows"),
                "analysis_population_rows": snapshot.get("analysis_population_rows"),
                "analysis_sampling_applied": snapshot.get("analysis_sampling_applied", False),
                "analysis_sample_stride": snapshot.get("analysis_sample_stride", 1),
                "delimiter": snapshot["delimiter"],
                "header_present": snapshot["header_present"],
                "input_hash": input_hash,
            },
            processing_started_at,
        )

        if is_baseline_workflow(summary.get("workflow")):
            return summary
        return read_upload_result_by_job_id(summary["job_id"]) or read_current_upload_result() or {}

    except Exception as exc:
        logger.exception(
            "CSV upload processing failed dataset_id=%s job_id=%s request_id=%s stage=%s exception_type=%s filename=%s",
            existing_job.get("dataset_id") or job_id,
            job_id,
            existing_job.get("request_id"),
            (read_upload_status(job_id) or {}).get("processing_state") or "import",
            exc.__class__.__name__,
            filename,
        )
        failed_timings = _finish_job_timing(job_id)
        logger.info(
            "upload_stage_timing event=job_failed job_id=%s total_job_ms=%s validation_ms=%s baseline_creation_ms=%s mapping_ms=%s comparison_ms=%s evidence_generation_ms=%s persistence_ms=%s",
            job_id,
            failed_timings.get("total_job_ms"),
            failed_timings.get("validation_ms"),
            failed_timings.get("baseline_creation_ms"),
            failed_timings.get("mapping_ms"),
            failed_timings.get("comparison_ms"),
            failed_timings.get("evidence_generation_ms"),
            failed_timings.get("persistence_ms"),
        )

        if snapshot and not baseline_workflow:
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
    read_baseline_result=read_baseline_result,
    read_upload_status=read_upload_status,
    write_job=write_job,
    process_json_payload=process_json_payload,
    process_csv_file=process_csv_file,
    restore_upload_source=restore_upload_source,
    delete_upload_source=delete_upload_source,
)
