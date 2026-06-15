from __future__ import annotations

import csv
import io
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
from app.services.runtime_db import delete_latest_payload_prefix, read_latest_payload, upsert_latest_payload
from app.services.relationship_baselines import build_relationship_baseline as _build_relationship_baseline
from app.services.upload_completion import build_partial_upload_artifacts
from app.services.upload_parser import json_payload_to_csv_text
from app.services.upload_persistence import read_upload_history as read_upload_history_from_runtime
from app.services.upload_persistence import summarize_result as summarize_result_payload
from app.services.upload_replay import build_replay, detect_numeric_columns, detect_timestamp_column as detect_replay_timestamp_column, minimal_replay, population_std, to_float
from app.services.upload_validator import detect_delimiter, looks_like_header, normalized_columns, row_tokens, stream_csv_snapshot
from app.services.upload_state import (
    build_empty_latest_upload_record,
    build_latest_upload_record,
    build_replay_payload_from_result,
    build_session_scope,
    has_active_session_artifact,
    normalize_upload_identity,
    select_current_upload_result,
)

RUNTIME_DIR = Path("backend/runtime")
UPLOAD_DIR = RUNTIME_DIR / "uploads"
JOB_DIR = RUNTIME_DIR / "upload_jobs"
LEGACY_JOB_DIR = RUNTIME_DIR / "jobs"
JOBS: dict[str, dict[str, Any]] = {}
LATEST_UPLOAD_CACHE: dict[str, Any] = {"summary": None, "result": None, "canonical": None}
_S3_CLIENT: Any | None = None
_RESET_BLOCK_PERSISTED = False
MAX_ANALYSIS_ROWS = int(os.getenv("NERAIUM_MAX_ANALYSIS_ROWS", "10000"))
CSV_PROGRESS_UPDATE_EVERY = int(os.getenv("NERAIUM_CSV_PROGRESS_UPDATE_EVERY", "5000"))
CSV_CHUNK_SIZE_ROWS = int(os.getenv("NERAIUM_CSV_CHUNK_SIZE_ROWS", "5000"))
logger = logging.getLogger(__name__)



def write_latest_upload_record(record: dict[str, Any] | None) -> dict[str, Any]:
    payload = build_empty_latest_upload_record() if not isinstance(record, dict) else dict(record)
    _write_json("latest_upload.json", payload)
    _write_shared_state("latest_upload", payload)
    LATEST_UPLOAD_CACHE["canonical"] = payload
    _invalidate_router_latest_cache()
    return payload


def read_latest_upload_record() -> dict[str, Any] | None:
    persisted = _read_shared_state("latest_upload")
    if isinstance(persisted, dict):
        LATEST_UPLOAD_CACHE["canonical"] = persisted
        return persisted
    cached = LATEST_UPLOAD_CACHE.get("canonical")
    if isinstance(cached, dict):
        return cached
    return _read_json("latest_upload.json")


def read_current_upload_result() -> dict[str, Any] | None:
    return select_current_upload_result(read_latest_upload_record())


def persist_latest_upload_state(
    *,
    summary: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    keep_result: bool = True,
) -> dict[str, Any]:
    evidence_record = None
    job_id, _, _ = normalize_upload_identity(result or summary)
    if job_id:
        try:
            from app.services.evidence_store import read_evidence_run
            evidence_record = read_evidence_run(job_id)
        except Exception:
            evidence_record = None
    record = build_latest_upload_record(
        summary=summary,
        result=result if keep_result else None,
        evidence=evidence_record,
    )
    return write_latest_upload_record(record)


def _upload_state_bucket() -> str:
    return os.getenv("NERAIUM_UPLOAD_STATE_BUCKET", "").strip()


def shared_state_configured() -> bool:
    return bool(_upload_state_bucket())


def upload_state_backend() -> str:
    if shared_state_configured():
        return "s3"
    if _runtime_db_latest_enabled():
        return "runtime_db"
    return "local"


def _upload_state_prefix() -> str:
    prefix = os.getenv("NERAIUM_UPLOAD_STATE_PREFIX", "upload-state/").strip()
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    return prefix


def _shared_key(name: str) -> str:
    return str(name).replace(".json", "")


def _s3_object_key(name: str) -> str:
    return f"{_upload_state_prefix()}{_shared_key(name)}.json"


def _get_s3_client() -> Any | None:
    global _S3_CLIENT
    if _S3_CLIENT is not None:
        return _S3_CLIENT
    if not _upload_state_bucket():
        return None
    try:
        import boto3  # type: ignore
        _S3_CLIENT = boto3.client("s3")
        return _S3_CLIENT
    except Exception:
        return None


def _read_shared_state(name: str) -> dict[str, Any] | None:
    bucket = _upload_state_bucket()
    if bucket:
        client = _get_s3_client()
        if client is not None:
            try:
                response = client.get_object(Bucket=bucket, Key=_s3_object_key(name))
                body = response["Body"].read().decode("utf-8")
                payload = json.loads(body)
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
    if _runtime_db_latest_enabled():
        try:
            payload = read_latest_payload(_shared_key(name))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    return None


def _write_shared_state(name: str, payload: dict[str, Any]) -> None:
    normalized = dict(payload or {})
    try:
        upsert_latest_payload(_shared_key(name), normalized)
    except Exception:
        pass
    bucket = _upload_state_bucket()
    if bucket:
        client = _get_s3_client()
        if client is not None:
            try:
                client.put_object(
                    Bucket=bucket,
                    Key=_s3_object_key(name),
                    Body=json.dumps(normalized, indent=2, default=str).encode("utf-8"),
                    ContentType="application/json",
                )
            except Exception:
                pass

def _runtime_db_latest_enabled() -> bool:
    return os.getenv("PYTEST_CURRENT_TEST") is None and os.getenv("NERAIUM_DISABLE_RUNTIME_DB_LATEST", "0") != "1"



def configure_runtime_dir(path: str | os.PathLike[str]) -> None:
    global RUNTIME_DIR, UPLOAD_DIR, JOB_DIR, LEGACY_JOB_DIR, _RESET_BLOCK_PERSISTED
    next_runtime_dir = Path(path)
    runtime_changed = next_runtime_dir != RUNTIME_DIR
    RUNTIME_DIR = next_runtime_dir
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR = RUNTIME_DIR / "uploads"
    JOB_DIR = RUNTIME_DIR / "upload_jobs"
    LEGACY_JOB_DIR = RUNTIME_DIR / "jobs"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    LEGACY_JOB_DIR.mkdir(parents=True, exist_ok=True)
    JOBS.clear()
    LATEST_UPLOAD_CACHE["summary"] = None
    LATEST_UPLOAD_CACHE["result"] = None
    LATEST_UPLOAD_CACHE["canonical"] = None
    if runtime_changed:
        _RESET_BLOCK_PERSISTED = True
    _invalidate_router_latest_cache()


def warm_latest_upload_cache() -> None:
    LATEST_UPLOAD_CACHE["summary"] = _read_shared_state("latest_upload_summary") or _read_json("latest_upload_summary.json")
    LATEST_UPLOAD_CACHE["result"] = _read_shared_state("latest_upload_result") or _read_json("latest_upload_result.json")
    LATEST_UPLOAD_CACHE["canonical"] = _read_shared_state("latest_upload") or _read_json("latest_upload.json")


def read_latest_upload_result() -> dict[str, Any] | None:
    persisted = _read_shared_state("latest_upload_result")
    if isinstance(persisted, dict):
        LATEST_UPLOAD_CACHE["result"] = persisted
        return persisted
    return LATEST_UPLOAD_CACHE.get("result") or _read_json("latest_upload_result.json")


def read_latest_upload_summary() -> dict[str, Any] | None:
    persisted = _read_shared_state("latest_upload_summary")
    if isinstance(persisted, dict):
        LATEST_UPLOAD_CACHE["summary"] = persisted
        return persisted
    return LATEST_UPLOAD_CACHE.get("summary") or _read_json("latest_upload_summary.json")


def read_upload_result_by_job_id(job_id: str) -> dict[str, Any] | None:
    persisted = _read_shared_state(f"upload_result_{job_id}")
    if isinstance(persisted, dict):
        return persisted
    return _read_json(f"upload_result_{job_id}.json")


def read_upload_status(job_id: str) -> dict[str, Any] | None:
    persisted = _read_shared_state(f"upload_status_{job_id}")
    if isinstance(persisted, dict):
        JOBS[job_id] = persisted
        return persisted
    return JOBS.get(job_id) or _read_json(f"upload_status_{job_id}.json") or read_upload_job(job_id)


def reset_upload_state() -> None:
    global _RESET_BLOCK_PERSISTED
    JOBS.clear()
    for path in RUNTIME_DIR.glob("*upload*"):
        try:
            path.unlink()
        except OSError:
            pass
    LATEST_UPLOAD_CACHE["summary"] = None
    LATEST_UPLOAD_CACHE["result"] = None
    LATEST_UPLOAD_CACHE["canonical"] = None
    try:
        delete_latest_payload_prefix("upload_")
        delete_latest_payload_prefix("latest_upload_")
        delete_latest_payload_prefix("latest_upload")
    except Exception:
        pass
    _RESET_BLOCK_PERSISTED = True


def _invalidate_router_latest_cache() -> None:
    try:
        from app.routers import data as data_router

        data_router.invalidate_latest_upload_cache()
    except Exception:
        pass


def clear_reset_block_persisted() -> None:
    global _RESET_BLOCK_PERSISTED
    _RESET_BLOCK_PERSISTED = False


def reset_block_persisted_active() -> bool:
    return bool(_RESET_BLOCK_PERSISTED)


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
    JOBS[job_id] = payload
    _write_json(f"upload_status_{job_id}.json", payload)
    upsert_upload_job(payload)
    _write_shared_state(f"upload_status_{job_id}", payload)
    _write_shared_state("latest_upload_summary", payload)
    LATEST_UPLOAD_CACHE["summary"] = payload
    persist_latest_upload_state(summary=payload, result=None, keep_result=False)
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

    _write_json(f"upload_result_{job_id}.json", result)
    _write_json(f"upload_status_{job_id}.json", summary)
    _write_json("latest_upload_result.json", result)
    _write_json("latest_upload_summary.json", summary)

    _write_shared_state(f"upload_result_{job_id}", result)
    _write_shared_state(f"upload_status_{job_id}", summary)
    _write_shared_state("latest_upload_result", result)
    _write_shared_state("latest_upload_summary", summary)

    JOBS[job_id] = summary
    LATEST_UPLOAD_CACHE["result"] = result
    LATEST_UPLOAD_CACHE["summary"] = summary
    persist_latest_upload_state(summary=summary, result=result)

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


def _observation_type_from_result(result: dict[str, Any]) -> str:
    relationship_drift = ((result.get("baseline_analysis") or {}).get("relationship_drift")) or []
    column_drift = ((result.get("baseline_analysis") or {}).get("column_drift")) or []
    data_quality = result.get("data_quality") or {}
    if any(isinstance(item, dict) and str(item.get("drift_flag") or "").lower() in {"watch", "review"} for item in relationship_drift):
        return "coupling_change"
    if any(isinstance(item, dict) and str(item.get("drift_flag") or "").lower() in {"watch", "review"} for item in column_drift):
        return "trajectory_drift"
    warnings = (data_quality.get("warnings") or []) if isinstance(data_quality, dict) else []
    if warnings:
        return "data_condition"
    return "baseline_shift"


def _observation_variables_from_result(result: dict[str, Any]) -> list[str]:
    baseline = result.get("baseline_analysis") or {}
    variables: list[str] = []
    relationship_drift = baseline.get("relationship_drift") if isinstance(baseline, dict) else []
    for item in relationship_drift or []:
        if not isinstance(item, dict):
            continue
        columns = item.get("columns")
        if isinstance(columns, list):
            variables.extend(str(column) for column in columns if column)
        refs = item.get("evidence_refs")
        if isinstance(refs, list):
            variables.extend(str(ref.get("column")) for ref in refs if isinstance(ref, dict) and ref.get("column"))
    for item in (baseline.get("column_drift") or []):
        if isinstance(item, dict) and item.get("column"):
            variables.append(str(item.get("column")))
    seen: set[str] = set()
    normalized: list[str] = []
    for value in variables:
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized[:16]


def _data_conditions_from_result(result: dict[str, Any]) -> list[str]:
    conditions: list[str] = []
    data_quality = result.get("data_quality") or {}
    if isinstance(data_quality, dict):
        for item in (data_quality.get("warnings") or [])[:6]:
            if item:
                conditions.append(str(item))
    timestamp_profile = result.get("timestamp_profile") or {}
    if isinstance(timestamp_profile, dict):
        for item in (timestamp_profile.get("warnings") or [])[:4]:
            if item:
                conditions.append(str(item))
    seen: set[str] = set()
    deduped: list[str] = []
    for item in conditions:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped[:8]


def _deformation_started_at(result: dict[str, Any]) -> str | None:
    replay = result.get("replay_timeline") or ((result.get("sii_intelligence") or {}).get("replay_timeline")) or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    if isinstance(timeline, list):
        for frame in timeline:
            if not isinstance(frame, dict):
                continue
            drift_index = frame.get("baseline_distance") or ((frame.get("topology_state") or {}).get("drift_index"))
            try:
                if drift_index is not None and float(drift_index) > 0:
                    return str(frame.get("timestamp_start") or frame.get("timestamp") or frame.get("timestamp_end") or "") or None
            except Exception:
                continue
    profile = result.get("timestamp_profile") or {}
    if isinstance(profile, dict):
        return profile.get("first_timestamp")
    return None



def _source_rows_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    baseline = result.get("baseline_analysis") or {}
    anchors: list[dict[str, Any]] = []
    for item in baseline.get("top_relationship_changes") or baseline.get("relationship_drift") or []:
        if not isinstance(item, dict):
            continue
        for anchor in item.get("source_rows") or []:
            if isinstance(anchor, dict):
                anchors.append(
                    {
                        "window": anchor.get("window"),
                        "source_row": anchor.get("source_row"),
                        "timestamp": anchor.get("timestamp"),
                    }
                )
        for ref in item.get("evidence_refs") or []:
            if not isinstance(ref, dict):
                continue
            for anchor in ref.get("source_rows") or []:
                if isinstance(anchor, dict):
                    anchors.append(
                        {
                            "window": anchor.get("window"),
                            "source_row": anchor.get("source_row"),
                            "timestamp": anchor.get("timestamp"),
                            "column": ref.get("column"),
                        }
                    )
    if not anchors:
        profile = result.get("timestamp_profile") or {}
        first = profile.get("first_timestamp") if isinstance(profile, dict) else None
        last = profile.get("last_timestamp") if isinstance(profile, dict) else None
        if first:
            anchors.append({"window": "upload_start", "timestamp": first})
        if last and last != first:
            anchors.append({"window": "upload_end", "timestamp": last})
    seen: set[tuple[Any, Any, Any, Any]] = set()
    deduped: list[dict[str, Any]] = []
    for anchor in anchors:
        key = (anchor.get("window"), anchor.get("source_row"), anchor.get("timestamp"), anchor.get("column"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(anchor)
    return deduped[:16]


def _evidence_windows_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    baseline = result.get("baseline_analysis") or {}
    windows: list[dict[str, Any]] = []
    for item in baseline.get("top_relationship_changes") or baseline.get("relationship_drift") or []:
        if not isinstance(item, dict):
            continue
        for ref in item.get("evidence_refs") or []:
            if not isinstance(ref, dict):
                continue
            windows.append(
                {
                    "column": ref.get("column"),
                    "baseline_window": ref.get("baseline_window") if not isinstance(ref.get("baseline_window"), (dict, list)) else json.dumps(ref.get("baseline_window"), sort_keys=True, default=str),
                    "recent_window": ref.get("recent_window") if not isinstance(ref.get("recent_window"), (dict, list)) else json.dumps(ref.get("recent_window"), sort_keys=True, default=str),
                }
            )
    replay = result.get("replay_timeline") or ((result.get("sii_intelligence") or {}).get("replay_timeline")) or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    if isinstance(timeline, list):
        for frame in timeline[:8]:
            if not isinstance(frame, dict):
                continue
            windows.append(
                {
                    "frame_index": frame.get("frame_index"),
                    "window_start": frame.get("timestamp_start") or frame.get("timestamp"),
                    "window_end": frame.get("timestamp_end") or frame.get("timestamp"),
                }
            )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for window in windows:
        key = (
            window.get("column"),
            window.get("baseline_window"),
            window.get("recent_window"),
            window.get("frame_index"),
            window.get("window_start"),
            window.get("window_end"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(window)
    return deduped[:16]


def _traceability_timestamps_from_result(result: dict[str, Any]) -> dict[str, Any]:
    profile = result.get("timestamp_profile") or {}
    replay = result.get("replay_timeline") or ((result.get("sii_intelligence") or {}).get("replay_timeline")) or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    first_frame = timeline[0] if isinstance(timeline, list) and timeline else {}
    last_frame = timeline[-1] if isinstance(timeline, list) and timeline else {}
    return {
        "created_at": result.get("created_at") or result.get("completed_at") or result.get("last_processed_at"),
        "completed_at": result.get("completed_at") or result.get("last_processed_at"),
        "processed_at": result.get("last_processed_at") or result.get("completed_at"),
        "upload_start": (profile.get("first_timestamp") if isinstance(profile, dict) else None) or first_frame.get("timestamp_start") or first_frame.get("timestamp"),
        "upload_end": (profile.get("last_timestamp") if isinstance(profile, dict) else None) or last_frame.get("timestamp_end") or last_frame.get("timestamp"),
    }


def build_traceability_packet(*, job_id: str, filename: str, result: dict[str, Any]) -> dict[str, Any]:
    source_rows = _source_rows_from_result(result)
    evidence_windows = _evidence_windows_from_result(result)
    timestamps = _traceability_timestamps_from_result(result)
    return {
        "job_id": str(job_id),
        "run_id": str(job_id),
        "upload_id": str(job_id),
        "source_name": filename,
        "source_rows": source_rows,
        "evidence_windows": evidence_windows,
        "timestamps": timestamps,
        "aligned": True,
        "traceability_complete": bool(
            job_id
            and source_rows
            and evidence_windows
            and timestamps.get("processed_at")
            and timestamps.get("upload_start")
            and timestamps.get("upload_end")
        ),
    }


def build_evidence_record_from_result(
    *,
    run_id: str,
    filename: str,
    source_type: str,
    result: dict[str, Any],
    created_at: str,
    completed_at: str,
    status: str,
    initiated_by: str,
    rows_received: int | None = None,
    rows_accepted: int | None = None,
    rows_rejected: int | None = None,
) -> dict[str, Any]:
    sii = result.get("sii_intelligence") or {}
    replay = result.get("replay_timeline") or (sii.get("replay_timeline")) or {}
    replay_timeline = replay.get("timeline") if isinstance(replay, dict) else []
    latest_frame = replay_timeline[-1] if isinstance(replay_timeline, list) and replay_timeline else {}
    baseline_payload = result.get("baseline_analysis") or {}
    relationship_drift = (baseline_payload.get("relationship_drift") or baseline_payload.get("top_relationship_changes") or [])
    primary_relationship = relationship_drift[0] if isinstance(relationship_drift, list) and relationship_drift else {}
    variables = _observation_variables_from_result(result)
    data_conditions = _data_conditions_from_result(result)
    source_rows = _source_rows_from_result(result)
    observation_type = _observation_type_from_result(result)
    structural_state = str(result.get("operating_state") or sii.get("facility_state") or "Monitoring")
    traceability = build_traceability_packet(job_id=run_id, filename=filename, result=result)
    confidence_score = sii.get("confidence")
    if confidence_score is None:
        confidence_score = ((sii.get("rooms") or [{}])[0] or {}).get("confidence")
    drift_metrics = {
        "neraium_score": (sii.get("neraium_score")),
        "baseline_distance": latest_frame.get("baseline_distance") if isinstance(latest_frame, dict) else None,
        "drift_index": ((latest_frame.get("topology_state") or {}).get("drift_index")) if isinstance(latest_frame, dict) else None,
        "drift_velocity": latest_frame.get("drift_velocity") if isinstance(latest_frame, dict) else None,
        "drift_acceleration": latest_frame.get("drift_acceleration") if isinstance(latest_frame, dict) else None,
        "coupling_delta": primary_relationship.get("correlation_delta") if isinstance(primary_relationship, dict) else None,
        "relationship_change_count": len(relationship_drift) if isinstance(relationship_drift, list) else 0,
        "observed_persistence": sii.get("observed_persistence"),
        "active_observations": 1 if str(status).lower() == "completed" and observation_type != "data_condition" else 0,
        "replay_frame_count": len(replay_timeline) if isinstance(replay_timeline, list) else 0,
    }
    primary_drivers = [str(sii.get("primary_driver"))] if sii.get("primary_driver") else []
    supporting_evidence = [str(item) for item in (sii.get("supporting_evidence") or [])[:6]]
    archetypes = [str(item) for item in (sii.get("structural_archetypes") or [])[:4]]
    return {
        "run_id": run_id,
        "job_id": run_id,
        "upload_id": run_id,
        "source_name": filename,
        "source_type": source_type,
        "source_url": None,
        "status": status,
        "created_at": created_at,
        "completed_at": completed_at,
        "rows_received": rows_received if rows_received is not None else int(result.get("row_count") or 0),
        "rows_accepted": rows_accepted if rows_accepted is not None else int(result.get("row_count") or 0),
        "rows_rejected": rows_rejected if rows_rejected is not None else 0,
        "sensors_detected": max(0, int(result.get("column_count") or 0) - 1),
        "room": ((sii.get("primary_room")) or "Uploaded telemetry"),
        "operating_state": result.get("operating_state"),
        "neraium_score": sii.get("neraium_score"),
        "drift_status": result.get("drift_status"),
        "scenario": None,
        "tick": None,
        "warnings": [],
        "errors": [],
        "primary_drivers": primary_drivers,
        "evidence_summary": supporting_evidence,
        "structural_archetypes": archetypes,
        "adaptive_site_key": "site::default",
        "operator_feedback_history": [],
        "initiated_by": initiated_by,
        "observation_type": observation_type,
        "observation_status": "open" if str(status).lower() == "completed" else str(status).lower(),
        "variables": variables,
        "drift_metrics": drift_metrics,
        "data_conditions": data_conditions,
        "source_rows": source_rows,
        "evidence_windows": traceability["evidence_windows"],
        "timestamps": traceability["timestamps"],
        "traceability": traceability,
        "confidence_score": confidence_score,
        "regime_label": str(sii.get("baseline_regime") or sii.get("regime_label") or "State Group A"),
        "structural_state": structural_state,
        "deformation_started_at": _deformation_started_at(result),
    }


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

    _write_json(f"upload_result_{job_id}.json", result)
    _write_json(f"upload_status_{job_id}.json", summary)
    _write_json("latest_upload_result.json", result)
    upsert_latest_payload("latest_upload_result", result)
    if _runtime_db_latest_enabled():
        upsert_latest_payload("latest_upload_result", result)
    _write_json("latest_upload_summary.json", summary)
    _write_shared_state(f"upload_result_{job_id}", result)
    _write_shared_state(f"upload_status_{job_id}", summary)
    _write_shared_state("latest_upload_result", result)
    _write_shared_state("latest_upload_summary", summary)
    latest_sii = read_latest_sii_state()
    if isinstance(latest_sii, dict):
        _write_shared_state("latest_sii_state", latest_sii)

    JOBS[job_id] = summary
    LATEST_UPLOAD_CACHE["result"] = result
    LATEST_UPLOAD_CACHE["summary"] = summary
    persist_latest_upload_state(summary=summary, result=result)
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
            _write_json(f"upload_result_{job_id}.json", result)
            _write_json("latest_upload_result.json", result)
            _write_json(f"upload_status_{job_id}.json", summary)
            _write_json("latest_upload_summary.json", summary)
            _write_shared_state(f"upload_result_{job_id}", result)
            _write_shared_state("latest_upload_result", result)
            _write_shared_state(f"upload_status_{job_id}", summary)
            _write_shared_state("latest_upload_summary", summary)
            LATEST_UPLOAD_CACHE["result"] = result
            LATEST_UPLOAD_CACHE["summary"] = summary
            persist_latest_upload_state(summary=summary, result=result)
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
    result = read_upload_result_by_job_id(job_id) if job_id else None
    if job_id is None:
        latest_record = read_latest_upload_record() or {}
        latest_result = latest_record.get("result") if isinstance(latest_record.get("result"), dict) else None
        result = latest_result if has_active_session_artifact(latest_result) else {}
    else:
        result = result or {}
    payload = build_replay_payload_from_result(result, job_id=job_id)
    if job_id and not result:
        payload["message"] = "No replay is available for the requested upload job."
    return payload


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
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(name: str, payload: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


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
    clear_reset_block_persisted()
    if len(args) == 2:
        job_id, result = args
        payload = dict(result or {})
        payload["job_id"] = str(job_id)
        payload["run_id"] = str(job_id)
        payload["upload_id"] = str(job_id)
        payload["session_scope"] = build_session_scope(str(job_id), filename=payload.get("filename"), status="active")
        if payload.get("filename"):
            payload["traceability"] = build_traceability_packet(job_id=str(job_id), filename=str(payload.get("filename") or ""), result=payload)
        if isinstance(payload.get("traceability"), dict):
            payload["decision_integrity"] = dict(payload["traceability"])
        _write_json(f"upload_result_{job_id}.json", payload)
        _write_json("latest_upload_result.json", payload)
        _write_shared_state(f"upload_result_{job_id}", payload)
        _write_shared_state("latest_upload_result", payload)
        LATEST_UPLOAD_CACHE["result"] = payload
        latest_summary = summarize_result(payload)
        _write_json("latest_upload_summary.json", latest_summary)
        _write_shared_state("latest_upload_summary", latest_summary)
        _write_shared_state(f"upload_status_{job_id}", latest_summary)
        LATEST_UPLOAD_CACHE["summary"] = latest_summary
        persist_latest_upload_state(summary=latest_summary, result=payload)
        return
    result = args[0] if args else {}
    if isinstance(result, dict):
        result.setdefault("session_scope", build_session_scope(result.get("job_id"), filename=result.get("filename"), status="active"))
    _write_json("latest_upload_result.json", result)
    _write_shared_state("latest_upload_result", result)
    LATEST_UPLOAD_CACHE["result"] = result
    if isinstance(result, dict) and result.get("job_id"):
        latest_summary = summarize_result(result)
        _write_json("latest_upload_summary.json", latest_summary)
        _write_shared_state("latest_upload_summary", latest_summary)
        _write_shared_state(f"upload_status_{result.get('job_id')}", latest_summary)
        LATEST_UPLOAD_CACHE["summary"] = latest_summary
        persist_latest_upload_state(summary=latest_summary, result=result)
    _invalidate_router_latest_cache()


def write_latest_upload_summary(*args, **kwargs) -> None:
    clear_reset_block_persisted()
    if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], dict):
        job_id = args[0]
        summary = args[1]
        payload = dict(summary or {})
        payload["job_id"] = str(job_id)
        payload["run_id"] = str(job_id)
        payload["upload_id"] = str(job_id)
        payload.setdefault("status", "COMPLETE")
        payload["session_scope"] = build_session_scope(str(job_id), filename=payload.get("filename"), status="active")
        if "status_url" not in payload:
            payload["status_url"] = f"/api/data/upload-status/{job_id}"
        _write_json("latest_upload_summary.json", payload)
        _write_shared_state("latest_upload_summary", payload)
        _write_shared_state(f"upload_status_{job_id}", payload)
        LATEST_UPLOAD_CACHE["summary"] = payload
        persist_latest_upload_state(summary=payload, result=read_upload_result_by_job_id(str(job_id)), keep_result=True)
        return
    if len(args) >= 1 and isinstance(args[0], dict):
        summary = args[0]
        summary.setdefault("session_scope", build_session_scope(summary.get("job_id"), filename=summary.get("filename"), status="active"))
        _write_json("latest_upload_summary.json", summary)
        _write_shared_state("latest_upload_summary", summary)
        LATEST_UPLOAD_CACHE["summary"] = summary
        persist_latest_upload_state(summary=summary, result=read_upload_result_by_job_id(str(summary.get("job_id") or "")) if summary.get("job_id") else None, keep_result=True)
        return
    if len(args) == 2:
        job_id, summary = args
        payload = dict(summary or {})
        payload["job_id"] = str(job_id)
        payload["run_id"] = str(job_id)
        payload["upload_id"] = str(job_id)
        payload.setdefault("status", "COMPLETE")
        payload["session_scope"] = build_session_scope(str(job_id), filename=payload.get("filename"), status="active")
        if "status_url" not in payload:
            payload["status_url"] = f"/api/data/upload-status/{job_id}"
        _write_json("latest_upload_summary.json", payload)
        _write_shared_state("latest_upload_summary", payload)
        _write_shared_state(f"upload_status_{job_id}", payload)
        LATEST_UPLOAD_CACHE["summary"] = payload
        persist_latest_upload_state(summary=payload, result=read_upload_result_by_job_id(str(job_id)), keep_result=True)
        return
    summary = args[0] if args else {}
    _write_json("latest_upload_summary.json", summary)
    _write_shared_state("latest_upload_summary", summary)
    LATEST_UPLOAD_CACHE["summary"] = summary
    persist_latest_upload_state(summary=summary if isinstance(summary, dict) else None, result=read_upload_result_by_job_id(str(summary.get("job_id") or "")) if isinstance(summary, dict) and summary.get("job_id") else None, keep_result=True)


def build_upload_result(
    columns: list[str] | None = None,
    rows: list[Any] | None = None,
    filename: str = "telemetry.csv",
    **kwargs,
) -> dict[str, Any]:
    """
    Compatibility entrypoint for live/data-connection code.
    Converts rows into CSV bytes and runs the V2 upload replay pipeline.
    """
    columns = columns or kwargs.get("columns") or []
    rows = rows or kwargs.get("rows") or []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)

    for row in rows:
        if isinstance(row, dict):
            writer.writerow([row.get(col, "") for col in columns])
        else:
            writer.writerow(row)

    summary = process_upload_bytes(filename, output.getvalue().encode("utf-8"))
    result = read_upload_result_by_job_id(summary["job_id"]) or read_current_upload_result() or {}
    return result


def read_upload_history(limit: int = 100) -> list[dict[str, Any]]:
    return read_upload_history_from_runtime(
        RUNTIME_DIR,
        limit=limit,
        current_result=read_current_upload_result(),
    )


def process_next_queued_upload_job() -> bool:
    job_id = claim_next_upload_job()
    if not job_id:
        return False
    metadata = read_job(job_id) or {}
    file_path = metadata.get("file_path")
    if not file_path or not Path(str(file_path)).exists():
        existing_result = read_upload_result_by_job_id(job_id)
        existing_status = read_upload_status(job_id) or {}
        if existing_result or str(existing_status.get("status", "")).upper() == "COMPLETE":
            complete_upload_queue_job(job_id, "completed")
            return True
        mark_queue_job_failed(job_id, "missing_upload_file")
        write_job(
            {
                **metadata,
                "job_id": job_id,
                "status": "FAILED",
                "processing_state": "failed",
                "error_type": "missing_upload_file",
                "error": "missing_upload_file",
                "message": "Upload file could not be found for processing.",
            }
        )
        return False
    try:
        path = Path(str(file_path))
        write_job(
            {
                **metadata,
                "job_id": job_id,
                "status": "PROCESSING",
                "processing_state": "parsing_telemetry",
                "percent": 20,
                "progress": 20,
                "message": "Parsing telemetry.",
                "progress_label": "Parsing telemetry.",
                "propagation_stage": "parsing_telemetry",
                "propagation_progress": 20,
                "propagation_label": "Parsing telemetry.",
            }
        )
        try:
            touch_upload_queue_job(job_id, "processing")
        except Exception:
            pass
        if path.suffix.lower() == ".json":
            result = process_json_payload(path.read_text(encoding="utf-8"), filename=metadata.get("filename") or path.name, job_id=job_id)
        else:
            result = process_csv_file(path, filename=metadata.get("filename") or path.name, job_id=job_id)
        completed = read_upload_status(job_id) or {}
        if metadata.get("runner_used") is False:
            completed["runner_used"] = False
        completed["job_id"] = job_id
        completed["status"] = "COMPLETE"

        if completed.get("processing_state") == "partial_complete":
            completed["result_available"] = True
            completed["first_usable_available"] = True
            completed["sii_completed"] = False
            completed["replay_ready"] = False
            completed["replay_frame_count"] = 0
            completed["percent"] = 100
            completed["progress"] = 100
            completed.setdefault("message", "Upload completed, but full intelligence processing could not finish.")
            completed["propagation_stage"] = "partial_complete"
            completed["propagation_progress"] = 100
            completed["propagation_label"] = "Partial upload complete."
        else:
            completed["processing_state"] = "complete"
            completed["result_available"] = True
            completed["percent"] = 100
            completed["progress"] = 100
            completed["message"] = "Telemetry processing complete."
            completed["propagation_stage"] = "complete"
            completed["propagation_progress"] = 100
            completed["propagation_label"] = "Complete."
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return bool(result)
    except Exception as exc:
        logger.exception("upload_queue_job_failed job_id=%s filename=%s", job_id, metadata.get("filename"))
        current = read_upload_status(job_id) or {}
        error_message = str(exc) or exc.__class__.__name__
        mark_queue_job_failed(job_id, error_message)
        complete_upload_queue_job(job_id, "failed", error_message)
        write_job(
            {
                **metadata,
                **current,
                "job_id": job_id,
                "status": "FAILED",
                "processing_state": "failed",
                "error_type": "processing_error",
                "error": error_message,
                "message": f"Telemetry processing failed: {error_message}",
                "progress_label": "Telemetry processing failed.",
                "result_available": False,
                "first_usable_available": False,
                "replay_ready": False,
                "replay_frame_count": 0,
                "propagation_stage": "failed",
                "propagation_label": "Failed.",
            }
        )
        try:
            from app.services.evidence_store import upsert_evidence_run
            now = datetime.now(timezone.utc).isoformat()
            upsert_evidence_run(
                {
                    "run_id": job_id,
                    "source_name": metadata.get("filename") or "upload.csv",
                    "source_type": "csv_upload",
                    "status": "failed",
                    "created_at": now,
                    "completed_at": now,
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
                    "initiated_by": metadata.get("initiated_by", "anonymous"),
                    "adaptive_site_key": "site::default",
                    "operator_feedback_history": [],
                    "observation_type": "data_condition",
                    "observation_status": "failed",
                    "variables": [],
                    "drift_metrics": {},
                    "data_conditions": [str(exc)],
                    "regime_label": None,
                    "structural_state": "Error",
                    "deformation_started_at": None,
                }
            )
        except Exception:
            pass
        return False


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
    JOBS[job_id] = payload
    _write_json(f"upload_status_{job_id}.json", payload)
    _write_shared_state(f"upload_status_{job_id}", payload)
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

        _write_json("latest_upload_summary.json", latest_summary)
        _write_shared_state("latest_upload_summary", latest_summary)
        LATEST_UPLOAD_CACHE["summary"] = latest_summary
        persist_latest_upload_state(summary=latest_summary, result=None, keep_result=False)
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
