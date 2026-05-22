from __future__ import annotations

import json
import logging
import csv
import os
import time
import uuid
import hashlib
import math
from collections import Counter, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
import numpy as np

from app.connectors.models import NormalizedTelemetryRecord
from app.core.config import get_settings
from app.engine import run_engine_analysis
from app.engine.temporal_math import evaluate_temporal_math
from app.services.baseline_analysis import build_baseline_analysis
from app.services.adaptive_learning import append_event_memory, build_adaptive_snapshot, derive_interpretive_archetypes, derive_site_key, update_site_memory_from_result
from app.services.aquatic_domain import analyze_aquatic_instability, map_aquatic_schema
from app.services.csv_parser import parse_csv_content, preview_rows
from app.services.cultivation_mapping import map_cultivation_columns
from app.services.data_quality import (
    build_data_quality,
    build_warnings,
    detect_timestamp_column,
    parse_numeric_value,
    profile_numeric_columns,
    profile_timestamps,
)
from app.services.driver_attribution import build_driver_attribution
from app.services.engine_identity import VALIDATION_PROVENANCE, build_processing_trace
from app.services.evidence_store import digest_payload, upsert_evidence_run
from app.services.operator_report import build_operator_report
from app.services.runtime_db import (
    claim_next_upload_job,
    clear_upload_runtime_tables,
    complete_upload_queue_job,
    delete_latest_payload_prefix,
    enqueue_upload_job,
    list_upload_jobs,
    mark_queue_job_failed,
    read_latest_payload,
    read_upload_job,
    upsert_latest_payload,
    upsert_upload_job,
)
from app.services.sii_intelligence import build_core_sii_outputs, build_upload_intelligence
from app.services.sii_runner import (
    CORE_ENGINE,
    RUNNER_MODULE,
    build_sensor_vectors,
    parse_timestamp as parse_runner_timestamp,
    read_latest_sii_state,
    run_sii_runner,
    write_latest_sii_state,
)


RUNTIME_DIR = get_settings().runtime_dir
UPLOAD_DIR = RUNTIME_DIR / "uploads"
JOB_DIR = RUNTIME_DIR / "upload_jobs"
LEGACY_JOB_DIR = RUNTIME_DIR / "jobs"
logger = logging.getLogger(__name__)
WRITE_RETRY_ATTEMPTS = 6 
WRITE_RETRY_DELAY_SECONDS = 0.02 
LATEST_UPLOAD_CACHE: dict[str, Any] = {
    "summary": None,
    "result": None,
}
UPLOAD_CACHE_STATS: dict[str, int] = {
    "hash_cache_hits": 0,
    "hash_cache_misses": 0,
}

def configure_runtime_dir(runtime_dir: Path) -> None: 
    global RUNTIME_DIR, UPLOAD_DIR, JOB_DIR, LEGACY_JOB_DIR 
    RUNTIME_DIR = runtime_dir 
    UPLOAD_DIR = RUNTIME_DIR / "uploads" 
    JOB_DIR = RUNTIME_DIR / "upload_jobs" 
    LEGACY_JOB_DIR = RUNTIME_DIR / "jobs" 
    LATEST_UPLOAD_CACHE["summary"] = None
    LATEST_UPLOAD_CACHE["result"] = None


def parse_positive_int_env(name: str, default: int) -> int: 
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("invalid_integer_env name=%s value=%s default=%s", name, raw_value, default)
        return default
    return value if value > 0 else default 


def parse_optional_positive_int_env(name: str) -> int | None:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return None
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("invalid_integer_env name=%s value=%s default=%s", name, raw_value, "none")
        return None
    return value if value > 0 else None


def parse_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


CHUNK_SIZE_ROWS = parse_positive_int_env("NERAIUM_UPLOAD_CHUNK_SIZE_ROWS", 10_000) 
# Default row budget now comfortably covers 180 days at 5-minute cadence (~51,840 rows).
MAX_ANALYSIS_ROWS = parse_positive_int_env("NERAIUM_MAX_ANALYSIS_ROWS", 60_000) 
# Keep SII fidelity substantially higher by default for long-window uploads.
MAX_SII_ROWS = parse_positive_int_env("NERAIUM_MAX_SII_ROWS", 30_000) 
MAX_PARSE_ROWS = parse_optional_positive_int_env("NERAIUM_MAX_PARSE_ROWS")
DISABLE_UPLOAD_HASH_CACHE = parse_bool_env("NERAIUM_DISABLE_UPLOAD_HASH_CACHE", False)

PROGRESS_LABELS = {
    "PENDING": "File accepted. Background intake job is queued.",
    "VALIDATING_SCHEMA": "Validating schema and timestamp context.",
    "PARSING": "Parsing signal matrix with streaming windows.",
    "BASELINE_MODELING": "Building relational baseline.",
    "STRUCTURAL_SCORING": "Computing structural drift and first health state.",
    "COGNITION_READY": "Operator cognition ready. Continuing downstream replay/evidence work.",
    "GENERATING_REPLAY": "Generating replay frames and evidence artifacts.",
    "GENERATING_EVIDENCE": "Writing evidence and facility state.",
    "COMPLETE": "Telemetry processing complete.",
    "FAILED": "Telemetry processing failed.",
}
SUPPORTED_UPLOAD_EXTENSIONS = {".csv", ".json"}


class UploadTooLargeError(ValueError):
    def __init__(self, max_size_bytes: int) -> None:
        super().__init__(f"Upload exceeds max allowed size ({max_size_bytes} bytes).")
        self.max_size_bytes = max_size_bytes


def ensure_runtime_dirs() -> None: 
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    JOB_DIR.mkdir(parents=True, exist_ok=True) 


def upload_hash_cache_key(input_hash: str | None) -> str | None:
    if not input_hash:
        return None
    return f"upload_result_by_hash:{input_hash}"


def delete_upload_file(metadata: dict[str, Any] | None) -> None:
    if not metadata:
        return
    raw_path = metadata.get("file_path")
    if not raw_path:
        return
    try:
        path = Path(raw_path)
        if path.exists() and path.is_file():
            path.unlink()
            logger.info("upload_file_deleted job_id=%s path=%s", metadata.get("job_id"), path.name)
    except OSError:
        logger.warning("upload_file_cleanup_failed job_id=%s", metadata.get("job_id"))


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def upload_job_superseded_by_reset(metadata: dict[str, Any] | None) -> bool:
    reset_marker = read_latest_payload("latest_upload_reset_at")
    reset_at = parse_timestamp(reset_marker) if isinstance(reset_marker, str) else None
    if reset_at is None:
        return False
    started_at = parse_timestamp(str((metadata or {}).get("started_at") or ""))
    if started_at is None:
        return True
    return started_at <= reset_at


async def create_upload_job( 
    file: UploadFile, 
    initiated_by: str = "anonymous", 
    ingest_request_id: str | None = None,
    max_size_bytes: int | None = None, 
) -> dict[str, Any]: 
    ensure_runtime_dirs()
    job_id = uuid.uuid4().hex
    filename = Path(file.filename or "telemetry.csv").name
    upload_path = UPLOAD_DIR / f"{job_id}{Path(filename).suffix.lower() or '.csv'}"
    size_bytes = 0
    hasher = hashlib.sha256()
    upload_started = time.perf_counter()
    save_started = upload_started
    try:
        with upload_path.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if max_size_bytes is not None and size_bytes > max_size_bytes:
                    raise UploadTooLargeError(max_size_bytes)
                hasher.update(chunk)
                output.write(chunk)
    except UploadTooLargeError:
        try:
            upload_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("upload_oversize_cleanup_failed job_id=%s filename=%s", job_id, filename)
        raise

    metadata = {
        "job_id": job_id,
        "filename": filename,
        "file_path": str(upload_path),
        "file_size_bytes": size_bytes,
        "status": "PENDING",
        "progress_label": PROGRESS_LABELS["PENDING"],
        "rows_processed": 0,
        "columns_detected": 0,
        "chunk_count": 0,
        "memory_estimate_bytes": 0,
        "processing_duration_seconds": None,
        "engine_runtime_seconds": None,
        "bytes_processed": 0,
        "warnings": [],
        "errors": [],
        "result_available": False,
        "first_usable_available": False,
        "timings": {"upload_receive_seconds": None, "file_save_seconds": None},
        "runner_used": False,
        "runner_module": RUNNER_MODULE,
        "core_engine": CORE_ENGINE,
        "started_at": now_iso(),
        "completed_at": None,
        "error": None,
        "result_summary": None,
        "input_hash": hasher.hexdigest(),
        "initiated_by": initiated_by, 
        "ingest_request_id": ingest_request_id,
    } 
    upload_duration = round(time.perf_counter() - upload_started, 4)
    metadata["timings"] = {"upload_receive_seconds": upload_duration, "file_save_seconds": round(time.perf_counter() - save_started, 4)}
    write_job(metadata)
    enqueue_upload_job(job_id)
    logger.info(
        "upload_file_received job_id=%s filename=%s size_bytes=%s",
        job_id,
        filename,
        size_bytes,
    )
    upsert_evidence_run(
        {
            "run_id": job_id,
            "source_type": "file_upload",
            "source_name": filename,
            "filename": filename,
            "created_at": metadata["started_at"],
            "completed_at": None,
            "status": "pending",
            "rows_received": 0,
            "rows_accepted": 0,
            "rows_rejected": 0,
            "sensors_detected": 0,
            "system_id": None,
            "room": None,
            "operating_state": None,
            "neraium_score": None,
            "drift_status": None,
            "primary_drivers": [],
            "evidence_summary": [],
            "warnings": [],
            "errors": [],
            "input_hash": metadata["input_hash"],
            "result_hash": None,
            "initiated_by": initiated_by,
        }
    )
    return metadata


def job_path(job_id: str) -> Path:
    safe_job_id = "".join(character for character in job_id if character.isalnum() or character in {"-", "_"})
    return JOB_DIR / f"{safe_job_id}.json"


def read_job(job_id: str) -> dict[str, Any] | None:
    ensure_runtime_dirs()
    db_metadata = read_upload_job(job_id)
    if db_metadata is not None:
        return db_metadata
    path = job_path(job_id)
    if not path.exists():
        legacy_path = LEGACY_JOB_DIR / path.name
        path = legacy_path if legacy_path.exists() else path
    if not path.exists():
        logger.warning(
            "upload_job_metadata_missing job_id=%s job_dir=%s legacy_job_dir=%s validation_failure_reason=%s",
            job_id,
            JOB_DIR,
            LEGACY_JOB_DIR,
            "upload_session_missing",
        )
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "upload_job_metadata_unreadable job_id=%s path=%s validation_failure_reason=%s error_type=%s",
            job_id,
            path,
            "upload_metadata_unreadable",
            type(exc).__name__,
        )
        return None


def write_job(metadata: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    if "status" in metadata:
        metadata["status"] = normalize_status(str(metadata["status"]))
        metadata["progress_label"] = PROGRESS_LABELS.get(metadata["status"], metadata.get("progress_label"))
    upsert_upload_job(metadata)
    path = job_path(metadata["job_id"])
    atomic_write_json(path, metadata)


def update_job(job_id: str, **updates: Any) -> dict[str, Any]:
    metadata = read_job(job_id)
    if metadata is None:
        metadata = {"job_id": job_id, "started_at": now_iso()}
    metadata.update(updates)
    if "status" in updates:
        metadata["status"] = normalize_status(str(updates["status"]))
        metadata["progress_label"] = PROGRESS_LABELS.get(metadata["status"], metadata.get("progress_label"))
    write_job(metadata)
    return metadata


def normalize_status(status: str) -> str:
    aliases = {
        "queued": "PENDING",
        "pending": "PENDING",
        "validating_schema": "VALIDATING_SCHEMA",
        "parsing": "PARSING",
        "baseline_modeling": "BASELINE_MODELING",
        "running_sii": "RUNNING_SII",
        "structural_scoring": "STRUCTURAL_SCORING",
        "cognition_ready": "COGNITION_READY",
        "generating_replay": "GENERATING_REPLAY",
        "writing_state": "GENERATING_EVIDENCE",
        "generating_evidence": "GENERATING_EVIDENCE",
        "complete": "COMPLETE",
        "failed": "FAILED",
    }
    return aliases.get(status.lower(), status.upper())


def record_timing(processing_stats: dict[str, Any], stage: str, started: float) -> None:
    timings = processing_stats.setdefault("timings", {})
    timings[f"{stage}_seconds"] = round(time.perf_counter() - started, 4)


def timed_status(status_callback: Any | None, status: str, processing_stats: dict[str, Any], **updates: Any) -> None:
    if status_callback:
        status_callback(status, timings=processing_stats.get("timings", {}), **updates)


def process_upload_job(job_id: str) -> None: 
    metadata = read_job(job_id)
    if metadata is None:
        logger.warning("upload_job_start_missing_metadata job_id=%s validation_failure_reason=%s", job_id, "upload_session_missing")
        return
    if upload_job_superseded_by_reset(metadata):
        update_job(
            job_id,
            status="FAILED",
            completed_at=now_iso(),
            error="Upload job superseded by runtime reset.",
            errors=["upload_job_superseded_by_reset"],
            result_available=False,
            first_usable_available=False,
        )
        complete_upload_queue_job(job_id, "failed", "upload_job_superseded_by_reset")
        delete_upload_file(metadata)
        return

    started = time.perf_counter() 
    try: 
        hash_cache_key = upload_hash_cache_key(str(metadata.get("input_hash") or ""))
        if hash_cache_key and not DISABLE_UPLOAD_HASH_CACHE:
            cached_payload = read_latest_payload(hash_cache_key)
            if isinstance(cached_payload, dict) and isinstance(cached_payload.get("result"), dict) and isinstance(cached_payload.get("summary"), dict):
                if upload_job_superseded_by_reset(metadata):
                    update_job(
                        job_id,
                        status="FAILED",
                        completed_at=now_iso(),
                        error="Upload job superseded by runtime reset.",
                        errors=["upload_job_superseded_by_reset"],
                        result_available=False,
                        first_usable_available=False,
                    )
                    complete_upload_queue_job(job_id, "failed", "upload_job_superseded_by_reset")
                    delete_upload_file(metadata)
                    return
                UPLOAD_CACHE_STATS["hash_cache_hits"] += 1
                completed_at = now_iso()
                result = cached_payload["result"]
                summary = {**cached_payload["summary"], "last_processed_at": completed_at}
                summary["upload_processing_mode"] = "hash_cache_reused"
                write_latest_upload_summary(job_id, summary)
                write_latest_upload_result(job_id, result, completed_at=completed_at)
                upsert_evidence_run(build_evidence_record(metadata, result, summary, completed_at, "completed"))
                update_job(
                    job_id,
                    status="COMPLETE",
                    rows_processed=summary.get("rows_processed"),
                    columns_detected=summary.get("columns_detected"),
                    completed_at=completed_at,
                    processing_duration_seconds=round(time.perf_counter() - started, 4),
                    result_available=True,
                    first_usable_available=True,
                    sii_completed=True,
                    error=None,
                    result_summary=summary,
                )
                complete_upload_queue_job(job_id, "completed")
                logger.info("upload_job_completed_from_hash_cache job_id=%s input_hash=%s", job_id, metadata.get("input_hash"))
                return
            UPLOAD_CACHE_STATS["hash_cache_misses"] += 1

        logger.info( 
            "upload_job_started job_id=%s filename=%s size_bytes=%s", 
            job_id, 
            metadata.get("filename"),
            metadata.get("file_size_bytes"),
        )
        update_job(job_id, status="PARSING")
        result = process_telemetry_file(
            file_path=Path(metadata["file_path"]),
            filename=metadata["filename"],
            status_callback=lambda status, **updates: update_job(job_id, status=status, **updates),
        )
        sii_artifacts = sii_completion_artifacts(result)
        required_sii_artifacts = {
            key: value for key, value in sii_artifacts.items() if key != "runner_used"
        }
        if not all(required_sii_artifacts.values()):
            raise RuntimeError(f"SII completion artifacts missing: {sii_artifacts}")
        update_job(
            job_id,
            status="GENERATING_EVIDENCE",
            rows_processed=result["row_count"],
            columns_detected=result["column_count"],
            runner_used=result["sii_runner_result"]["runner_used"],
            chunk_count=result["processing_stats"]["chunk_count"],
            memory_estimate_bytes=result["processing_stats"]["memory_estimate_bytes"],
            engine_runtime_seconds=result["processing_stats"]["engine_runtime_seconds"],
            bytes_processed=result.get("processing_stats", {}).get("bytes_processed", metadata.get("file_size_bytes", 0)),
            warnings=result.get("warnings", [])[:10],
            errors=result.get("sii_runner_result", {}).get("errors", [])[:5],
            result_available=True,
            first_usable_available=True,
            sii_completed=True,
            sii_completion_artifacts=sii_artifacts,
            timings=result.get("processing_stats", {}).get("timings", {}),
        )
        completed_at = now_iso()
        if upload_job_superseded_by_reset(metadata):
            update_job(
                job_id,
                status="FAILED",
                completed_at=completed_at,
                processing_duration_seconds=round(time.perf_counter() - started, 4),
                error="Upload job superseded by runtime reset.",
                errors=["upload_job_superseded_by_reset"],
                result_available=False,
                first_usable_available=False,
            )
            complete_upload_queue_job(job_id, "failed", "upload_job_superseded_by_reset")
            delete_upload_file(metadata)
            return
        update_site_memory_from_result(result, completed_at)
        result["adaptive_learning"] = build_adaptive_snapshot(result, {"last_processed_at": completed_at})
        summary = summarize_result(result, completed_at) 
        summary["upload_processing_mode"] = "full_processing"
        latest_state = read_latest_sii_state() or {}
        if latest_state:
            write_latest_sii_state({**latest_state, "adaptive_learning": result["adaptive_learning"]})
        duration = round(time.perf_counter() - started, 4) 
        write_latest_upload_summary(job_id, summary) 
        write_latest_upload_result(job_id, result, completed_at=completed_at) 
        if hash_cache_key and not DISABLE_UPLOAD_HASH_CACHE:
            upsert_latest_payload(hash_cache_key, {"summary": summary, "result": result, "cached_at": completed_at})
        upsert_evidence_run(build_evidence_record(metadata, result, summary, completed_at, "completed")) 
        update_job(
            job_id,
            status="COMPLETE",
            rows_processed=result["row_count"],
            columns_detected=result["column_count"],
            runner_used=result["sii_runner_result"]["runner_used"],
            runner_module=result["sii_runner_result"]["runner_module"],
            core_engine=result["sii_runner_result"]["core_engine"],
            completed_at=completed_at,
            processing_duration_seconds=duration,
            engine_runtime_seconds=result["processing_stats"]["engine_runtime_seconds"],
            error=None,
            warnings=result.get("warnings", [])[:10],
            errors=result.get("sii_runner_result", {}).get("errors", [])[:5],
            result_available=True,
            first_usable_available=True,
            sii_completed=True,
            sii_completion_artifacts=sii_artifacts,
            timings={**metadata.get("timings", {}), **result.get("processing_stats", {}).get("timings", {}), "total_job_seconds": duration},
            result_summary=summary,
        )
        logger.info(
            "upload_job_complete job_id=%s rows=%s columns=%s chunks=%s duration=%s engine_runtime=%s memory_estimate=%s timings=%s",
            job_id,
            result["row_count"],
            result["column_count"],
            result["processing_stats"]["chunk_count"],
            duration,
            result["processing_stats"]["engine_runtime_seconds"],
            result["processing_stats"]["memory_estimate_bytes"],
            {**metadata.get("timings", {}), **result.get("processing_stats", {}).get("timings", {})},
        )
        complete_upload_queue_job(job_id, "completed")
    except Exception as exc:
        logger.exception("upload_job_failed job_id=%s", job_id)
        completed_at = now_iso()
        update_job(
            job_id,
            status="FAILED",
            completed_at=completed_at,
            processing_duration_seconds=round(time.perf_counter() - started, 4),
            error=f"{type(exc).__name__}: {exc}",
            errors=[f"{type(exc).__name__}: {exc}"],
            timings={**metadata.get("timings", {}), "total_job_seconds": round(time.perf_counter() - started, 4)},
        )
        upsert_evidence_run(
            {
                "run_id": job_id,
                "source_type": "file_upload",
                "source_name": metadata.get("filename"),
                "filename": metadata.get("filename"),
                "created_at": metadata.get("started_at"),
                "completed_at": completed_at,
                "status": "failed",
                "rows_received": metadata.get("rows_processed", 0),
                "rows_accepted": 0,
                "rows_rejected": 0,
                "sensors_detected": metadata.get("columns_detected", 0),
                "system_id": None,
                "room": None,
                "operating_state": None,
                "neraium_score": None,
                "drift_status": None,
                "primary_drivers": [],
                "evidence_summary": [],
                "warnings": [],
                "errors": [f"{type(exc).__name__}: {exc}"],
                "input_hash": metadata.get("input_hash"),
                "result_hash": None,
                "initiated_by": metadata.get("initiated_by", "anonymous"),
            }
        )
        complete_upload_queue_job(job_id, "failed", f"{type(exc).__name__}: {exc}")
    finally:
        delete_upload_file(metadata)


def process_next_queued_upload_job() -> None:
    for _ in range(100):
        job_id = claim_next_upload_job()
        if not job_id:
            return
        metadata = read_job(job_id)
        if metadata is None:
            logger.warning("upload_queue_job_missing_metadata job_id=%s", job_id)
            mark_queue_job_failed(job_id, "missing_upload_job_metadata")
            continue
        file_path = metadata.get("file_path")
        if file_path and not Path(file_path).exists():
            logger.warning("upload_queue_job_missing_file job_id=%s file_path=%s", job_id, file_path)
            mark_queue_job_failed(job_id, "missing_upload_file")
            continue
        process_upload_job(job_id)
        return


def process_csv_content(
    *,
    content: bytes,
    filename: str,
    status_callback: Any | None = None,
) -> dict[str, Any]:
    columns, data_rows = parse_csv_content(content)
    room_summary = build_room_summary(columns, data_rows)
    return build_upload_result(
        columns=columns,
        data_rows=data_rows,
        total_rows=len(data_rows),
        filename=filename,
        status_callback=status_callback,
        processing_stats={
            "chunk_count": 1 if data_rows else 0,
            "sampled_rows": len(data_rows),
            "sii_sampled_rows": min(len(data_rows), MAX_SII_ROWS),
            "memory_estimate_bytes": estimate_rows_memory(data_rows),
            "used_streaming": False,
            "engine_runtime_seconds": 0,
            "room_summary": room_summary,
        },
    )


def process_telemetry_file(
    *,
    file_path: Path,
    filename: str,
    status_callback: Any | None = None,
) -> dict[str, Any]:
    if file_path.suffix.lower() == ".json":
        return process_json_file(file_path=file_path, filename=filename, status_callback=status_callback)
    return process_csv_file(file_path=file_path, filename=filename, status_callback=status_callback)


def process_csv_file(
    *,
    file_path: Path,
    filename: str,
    status_callback: Any | None = None,
) -> dict[str, Any]:
    columns, data_rows, total_rows, processing_stats = stream_csv_windows(file_path, status_callback)
    return build_upload_result(
        columns=columns,
        data_rows=data_rows,
        total_rows=total_rows,
        filename=filename,
        status_callback=status_callback,
        processing_stats=processing_stats,
        source_file_path=file_path,
    )


def process_json_file(
    *,
    file_path: Path,
    filename: str,
    status_callback: Any | None = None,
) -> dict[str, Any]:
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("JSON telemetry file could not be parsed.") from exc
    return process_json_payload(payload=payload, filename=filename, status_callback=status_callback)


def process_json_payload(
    *,
    payload: Any,
    filename: str,
    status_callback: Any | None = None,
) -> dict[str, Any]:
    normalized_records, metadata = normalize_uploaded_json_payload(payload, filename)
    columns, data_rows, room_summary = build_rows_from_normalized_records([record.model_dump() for record in normalized_records])
    return build_upload_result(
        columns=columns,
        data_rows=data_rows,
        total_rows=len(data_rows),
        filename=filename,
        status_callback=status_callback,
        processing_stats={
            "chunk_count": 1 if data_rows else 0,
            "sampled_rows": len(data_rows),
            "sii_sampled_rows": min(len(data_rows), MAX_SII_ROWS),
            "memory_estimate_bytes": estimate_rows_memory(data_rows),
            "used_streaming": False,
            "engine_runtime_seconds": 0,
            "room_summary": room_summary,
            "record_count": metadata.get("readings_received", 0),
            "accepted_record_count": metadata.get("readings_accepted", 0),
            "rejected_record_count": metadata.get("readings_rejected", 0),
            "sensors_detected": metadata.get("sensors_detected", 0),
        },
        intelligence_source="uploaded",
        intelligence_mode="live",
        intelligence_source_metadata=metadata,
    )


def stream_csv_windows( 
    file_path: Path,
    status_callback: Any | None = None,
) -> tuple[list[str], list[list[str]], int, dict[str, Any]]:
    parse_started = time.perf_counter()
    file_size_bytes = file_path.stat().st_size if file_path.exists() else 0
    first_rows: list[tuple[int, list[str]]] = []
    tail_rows: deque[tuple[int, list[str]]] = deque()
    middle_reservoir: list[tuple[int, list[str]]] = [] 
    edge_window = MAX_ANALYSIS_ROWS // 3
    middle_capacity = max(1, MAX_ANALYSIS_ROWS - edge_window - edge_window) 
    middle_candidates_seen = 0
    room_counts: Counter[str] = Counter()
    total_rows = 0
    malformed_rows = 0
    chunk_count = 0
    columns: list[str] | None = None
    last_bytes_processed = 0 
    parse_capped = False

    try:
        csv_file = file_path.open("r", encoding="utf-8-sig", newline="")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV file must be UTF-8 encoded.") from exc

    with csv_file:
        reader = csv.reader(csv_file)
        try:
            columns = [column.strip() for column in next(reader)]
        except StopIteration as exc:
            raise ValueError("CSV file is empty.") from exc
        if not any(columns):
            raise ValueError("CSV file must include a header row.")
        if status_callback:
            status_callback(
                "VALIDATING_SCHEMA",
                rows_processed=0,
                columns_detected=len(columns),
                bytes_processed=0,
                file_size_bytes=file_size_bytes,
            )
        room_index = first_room_column_index(columns)

        for row in reader: 
            if not any(cell.strip() for cell in row): 
                continue 
            total_rows += 1 
            if MAX_PARSE_ROWS is not None and total_rows > MAX_PARSE_ROWS:
                parse_capped = True
                total_rows = MAX_PARSE_ROWS
                break
            if room_index is not None and room_index < len(row) and row[room_index].strip(): 
                room_counts[row[room_index].strip()] += 1 
            if len(row) != len(columns):
                malformed_rows += 1
            if len(first_rows) < edge_window: 
                first_rows.append((total_rows - 1, row)) 
            else: 
                tail_rows.append((total_rows - 1, row))
                if len(tail_rows) > edge_window:
                    middle_candidates_seen += 1
                    candidate = tail_rows.popleft()
                    if len(middle_reservoir) < middle_capacity:
                        middle_reservoir.append(candidate)
                    else:
                        reservoir_index = int(np.random.randint(0, middle_candidates_seen))
                        if reservoir_index < middle_capacity:
                            middle_reservoir[reservoir_index] = candidate
            if total_rows % CHUNK_SIZE_ROWS == 0:
                chunk_count += 1
                try:
                    last_bytes_processed = csv_file.buffer.tell()
                except (AttributeError, OSError):
                    last_bytes_processed = min(file_size_bytes, max(last_bytes_processed, int(file_size_bytes * 0.5)))
                if status_callback:
                    status_callback(
                        "PARSING",
                        rows_processed=total_rows,
                        columns_detected=len(columns),
                        chunk_count=chunk_count,
                        memory_estimate_bytes=0,
                        bytes_processed=last_bytes_processed,
                        file_size_bytes=file_size_bytes,
                    )

    if total_rows == 0:
        raise ValueError("CSV file is empty.")

    if total_rows % CHUNK_SIZE_ROWS:
        chunk_count += 1

    last_bytes_processed = file_size_bytes
    merged_rows = first_rows + middle_reservoir + list(tail_rows)
    deduped_by_index: dict[int, list[str]] = {}
    for row_index, row in merged_rows:
        deduped_by_index[row_index] = row
    sampled_row_indexes = sorted(deduped_by_index.keys())
    data_rows = [deduped_by_index[index] for index in sampled_row_indexes]
    if status_callback:
        status_callback(
            "PARSING",
            rows_processed=total_rows,
            columns_detected=len(columns),
            chunk_count=chunk_count,
            memory_estimate_bytes=estimate_rows_memory(data_rows),
            bytes_processed=last_bytes_processed,
            file_size_bytes=file_size_bytes,
        )

    logger.info(
        "upload_rows_parsed filename=%s rows_parsed=%s rows_accepted=%s rows_rejected=%s columns_detected=%s chunks=%s",
        file_path.name,
        total_rows,
        max(total_rows - malformed_rows, 0),
        malformed_rows,
        len(columns),
        chunk_count,
    )

    return columns, data_rows, total_rows, { 
        "chunk_count": chunk_count,
        "sampled_rows": len(data_rows),
        "sii_sampled_rows": min(len(data_rows), MAX_SII_ROWS),
        "malformed_rows": malformed_rows,
        "memory_estimate_bytes": estimate_rows_memory(data_rows),
        "used_streaming": True, 
        "parse_capped": parse_capped,
        "engine_runtime_seconds": 0, 
        "file_size_bytes": file_size_bytes,
        "bytes_processed": last_bytes_processed,
        "timings": {"parse_seconds": round(time.perf_counter() - parse_started, 4)},
        "room_summary": room_summary_from_counts(room_counts, total_rows),
        "sampled_row_indexes": sampled_row_indexes,
    }


def build_upload_result(
    *,
    columns: list[str],
    data_rows: list[list[str]],
    total_rows: int,
    filename: str,
    status_callback: Any | None = None,
    processing_stats: dict[str, Any],
    intelligence_source: str = "uploaded",
    intelligence_mode: str = "live",
    intelligence_source_metadata: dict[str, Any] | None = None,
    source_file_path: Path | None = None,
) -> dict[str, Any]:
    stage_started = time.perf_counter()
    timed_status(status_callback, "VALIDATING_SCHEMA", processing_stats, rows_processed=total_rows, columns_detected=len(columns), bytes_processed=processing_stats.get("bytes_processed", 0))
    warnings = build_warnings(columns, data_rows)
    if processing_stats.get("used_streaming") and processing_stats.get("sampled_rows", 0) < total_rows:
        warnings.append(
            f"Large upload was processed with streaming windows: {processing_stats['sampled_rows']} representative rows modeled from {total_rows} total rows."
        )
    if processing_stats.get("malformed_rows"): 
        warnings.append(f"{processing_stats['malformed_rows']} rows had a different column count than the header.") 
    if processing_stats.get("parse_capped"):
        warnings.append(
            "Upload parse was capped by NERAIUM_MAX_PARSE_ROWS for faster pilot throughput; analysis is based on the capped window."
        )
    detected_timestamp_column = detect_timestamp_column(columns, data_rows)
    if detected_timestamp_column is None:
        warnings.append("No obvious timestamp column detected.")
    sampled_row_indexes = processing_stats.get("sampled_row_indexes")
    data_rows, sampled_row_indexes = order_rows_chronologically(
        columns=columns,
        rows=data_rows,
        timestamp_column=detected_timestamp_column,
        row_indexes=sampled_row_indexes if isinstance(sampled_row_indexes, list) else None,
    )
    if sampled_row_indexes:
        processing_stats["sampled_row_indexes"] = sampled_row_indexes

    numeric_profiles = profile_numeric_columns(columns, data_rows)
    warnings.extend(
        f"{profile['column']} contains {profile['missing_count']} missing numeric values."
        for profile in numeric_profiles
        if profile["missing_count"] > 0
    )
    timestamp_profile = profile_timestamps(columns, data_rows, detected_timestamp_column)
    warnings.extend(timestamp_profile["warnings"])
    warnings.extend(
        profile["range_warning"]
        for profile in numeric_profiles
        if profile["range_warning"] is not None
    )
    data_quality = build_data_quality(
        row_count=total_rows,
        column_count=len(columns),
        numeric_column_count=len(numeric_profiles),
        timestamp_detected=detected_timestamp_column is not None,
        warnings=warnings,
    )
    record_timing(processing_stats, "schema_validation", stage_started)
    stage_started = time.perf_counter()
    timed_status(status_callback, "BASELINE_MODELING", processing_stats, rows_processed=total_rows, columns_detected=len(columns), warnings=warnings[:10])
    baseline_analysis = build_baseline_analysis(columns, data_rows, numeric_profiles)
    schema_mapping = map_cultivation_columns(columns)
    room_summary = processing_stats.get("room_summary") or build_room_summary(columns, data_rows, total_rows)
    primary_room = primary_room_from_summary(room_summary)
    previous_upload_summary = read_upload_history(limit=1)[0] if read_upload_history(limit=1) else None
    operator_report = build_operator_report(
        data_quality=data_quality,
        timestamp_profile=timestamp_profile,
        numeric_profiles=numeric_profiles,
        baseline_analysis=baseline_analysis,
        cultivation_mapping=schema_mapping,
    )
    record_timing(processing_stats, "baseline_build", stage_started)
    stage_started = time.perf_counter()
    timed_status(status_callback, "STRUCTURAL_SCORING", processing_stats, rows_processed=total_rows, columns_detected=len(columns))
    engine_started = time.perf_counter()
    engine_result = run_engine_analysis(
        columns=columns,
        rows=data_rows,
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        cultivation_mapping=schema_mapping,
        numeric_profiles=numeric_profiles,
    )
    temporal_math = evaluate_temporal_math(
        columns=columns,
        rows=data_rows,
        numeric_profiles=numeric_profiles,
        timestamp_column=detected_timestamp_column,
    )
    aquatic_assessment = analyze_aquatic_instability(
        columns=columns,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
    )
    if aquatic_assessment["signals"]:
        engine_result["signals"] = [*engine_result.get("signals", []), *aquatic_assessment["signals"]]
    if aquatic_assessment["evidence"]:
        engine_result["evidence"] = [*engine_result.get("evidence", []), *aquatic_assessment["evidence"]]
    if aquatic_assessment["recommended_checks"]:
        engine_result["recommended_checks"] = list(
            dict.fromkeys([*engine_result.get("recommended_checks", []), *aquatic_assessment["recommended_checks"]])
        )
    processing_stats["engine_runtime_seconds"] = round(time.perf_counter() - engine_started, 4)
    record_timing(processing_stats, "structural_scoring", stage_started)
    stage_started = time.perf_counter()
    driver_attribution = build_driver_attribution(
        room_state={
            "room": primary_room,
            "state": state_from_assessment(baseline_analysis["overall_assessment"]),
            "severity": severity_from_assessment(baseline_analysis["overall_assessment"]),
        },
        telemetry_context={
            "columns": columns,
            "rows": data_rows,
            "numeric_profiles": numeric_profiles,
            "timestamp_profile": timestamp_profile,
            "data_quality": data_quality,
            "cultivation_mapping": schema_mapping,
        },
        baseline_context={
            "baseline_analysis": baseline_analysis,
            "cultivation_mapping": schema_mapping,
        },
        engine_result=engine_result,
    )
    room_assessments = build_room_assessments(
        columns=columns,
        rows=data_rows,
        room_summary=room_summary,
        numeric_profiles=numeric_profiles,
    )
    telemetry_profile = classify_telemetry_profile(
        columns=columns,
        rows=data_rows,
        numeric_profiles=numeric_profiles,
    )
    operational_signal_profile = classify_operational_signal_profile(
        columns=columns,
        rows=data_rows,
        numeric_profiles=numeric_profiles,
    )
    effective_source_metadata = {
        **(intelligence_source_metadata or {}),
        **telemetry_profile,
        **operational_signal_profile,
    }
    sii_intelligence = build_upload_intelligence(
        filename=filename,
        row_count=total_rows,
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
        operator_report=operator_report,
        timestamp_profile=timestamp_profile,
        room_summary=room_summary,
        room_assessments=room_assessments,
        source=intelligence_source,
        mode=intelligence_mode,
        source_metadata=effective_source_metadata,
    )
    sii_intelligence["temporal_math_engine"] = temporal_math
    temporal_instability = temporal_math.get("instability_index", {}) if isinstance(temporal_math, dict) else {}
    if isinstance(temporal_instability, dict):
        sii_intelligence["instability_index"] = temporal_instability
    decision_state = temporal_math.get("decision_thresholding", {}).get("state") if isinstance(temporal_math, dict) else None
    if isinstance(decision_state, str) and decision_state:
        decision_map = {
            "Normal": ("Stable", "nominal"),
            "Watch": ("Drift observed", "review"),
            "Investigate": ("Needs review", "review"),
            "Act": ("Needs action", "elevated"),
            "Critical": ("Needs action", "unstable"),
        }
        sii_intelligence["decision_threshold_state"] = decision_state
        if decision_state in {"Act", "Critical"}:
            mapped_state, mapped_urgency = decision_map.get(decision_state, ("Monitoring", "review"))
            sii_intelligence["facility_state"] = mapped_state
            sii_intelligence["room_state"] = mapped_state
            sii_intelligence["urgency"] = mapped_urgency
            if isinstance(sii_intelligence.get("rooms"), list) and sii_intelligence["rooms"] and isinstance(sii_intelligence["rooms"][0], dict):
                sii_intelligence["rooms"][0]["room_state"] = mapped_state
                sii_intelligence["rooms"][0]["urgency"] = mapped_urgency
    lead_time = temporal_math.get("lead_time_estimate", {}) if isinstance(temporal_math, dict) else {}
    if isinstance(lead_time, dict):
        lead_rows = lead_time.get("rows_before_event")
        lead_ts = lead_time.get("timestamp")
        if isinstance(lead_rows, int) and lead_rows > 0:
            sii_intelligence["lead_time_detected_rows_before_event"] = lead_rows
        if isinstance(lead_ts, str) and lead_ts.strip():
            sii_intelligence["lead_time_detected_at"] = lead_ts
    sii_intelligence["operational_domain"] = "commercial_aquatic_hospitality"
    sii_intelligence["aquatic_schema"] = map_aquatic_schema(columns)
    sii_intelligence["aquatic_instability"] = {
        "admitted_candidates": aquatic_assessment["admitted_candidates"],
        "relationship_map": aquatic_assessment["relationship_map"],
        "integration_stubs": aquatic_assessment["integration_stubs"],
        "explainability": {
            "why_watch_or_alert": [item["relationship_explanation"] for item in aquatic_assessment["admitted_candidates"][:3]],
            "what_changed_relative_to_baseline": [item["timeline"] for item in aquatic_assessment["admitted_candidates"][:3]],
            "confidence_basis": [item["confidence_persistence_score"] for item in aquatic_assessment["admitted_candidates"][:3]],
            "opaque_hidden_scoring": False,
            "autonomous_actions": False,
        },
    }
    processing_trace = build_processing_trace(
        engine_result=engine_result,
        driver_attribution=driver_attribution,
        rows_processed=total_rows,
        columns_analyzed=baseline_analysis["columns_analyzed"],
    )
    record_timing(processing_stats, "cognition_build", stage_started)
    timed_status(status_callback, "COGNITION_READY", processing_stats, rows_processed=total_rows, columns_detected=len(columns), warnings=warnings[:10], result_available=True, first_usable_available=True)
    stage_started = time.perf_counter()
    timed_status(status_callback, "GENERATING_REPLAY", processing_stats, rows_processed=total_rows, columns_detected=len(columns), result_available=True, first_usable_available=True)
    sii_rows = downsample_rows(data_rows, MAX_SII_ROWS)
    replay_rows = data_rows
    replay_row_indexes = processing_stats.get("sampled_row_indexes")
    replay_rows_mode = "sampled_windows"
    if source_file_path is not None and source_file_path.exists() and processing_stats.get("used_streaming"):
        frame_target = replay_target_frames(total_rows)
        replay_rows_target = max(600, min(2400, frame_target * 8))
        full_timeline_rows, full_timeline_indexes = build_replay_rows_from_full_csv(
            file_path=source_file_path,
            columns=columns,
            numeric_profiles=numeric_profiles,
            total_rows=total_rows,
            target_rows=replay_rows_target,
            timestamp_column=detected_timestamp_column,
        )
        if full_timeline_rows:
            replay_rows = full_timeline_rows
            replay_row_indexes = full_timeline_indexes
            replay_rows_mode = "full_timeline"
            processing_stats["replay_rows_source"] = "full_timeline"
            processing_stats["replay_rows_count"] = len(full_timeline_rows)
        else:
            processing_stats["replay_rows_source"] = "sampled_windows"
            processing_stats["replay_rows_count"] = len(replay_rows)
    else:
        processing_stats["replay_rows_source"] = "in_memory_rows"
        processing_stats["replay_rows_count"] = len(replay_rows)
    if replay_rows_mode == "sampled_windows" and processing_stats.get("used_streaming"):
        warnings.append("Replay timeline was generated from sampled windows because full-timeline replay extraction was unavailable.")
    sii_runner_result = run_sii_runner(
        columns=columns,
        rows=sii_rows,
        numeric_profiles=numeric_profiles,
        timestamp_column=detected_timestamp_column,
        primary_room=primary_room,
        driver_attribution=driver_attribution,
        engine_result=engine_result,
        processing_trace=processing_trace,
    )
    replay_timeline = build_structural_replay_timeline(
        columns=columns,
        rows=replay_rows,
        total_rows=total_rows,
        numeric_profiles=numeric_profiles,
        timestamp_column=detected_timestamp_column,
        primary_room=primary_room,
        row_indexes=replay_row_indexes if isinstance(replay_row_indexes, list) else None,
    )
    sii_intelligence["replay_timeline"] = replay_timeline
    processing_trace["replay_frame_count"] = replay_timeline.get("meta", {}).get("frame_count", 0)
    record_timing(processing_stats, "replay_generation", stage_started)
    runner_latest_state = sii_runner_result.get("latest_state") if isinstance(sii_runner_result, dict) else None
    if isinstance(runner_latest_state, dict):
        runner_instability_index = runner_latest_state.get("instability_index")
        if isinstance(runner_instability_index, dict):
            if not isinstance(sii_intelligence.get("instability_index"), dict):
                sii_intelligence["instability_index"] = runner_instability_index
            else:
                sii_intelligence["instability_index_legacy_runner"] = runner_instability_index
        runner_projection_hours = runner_latest_state.get("projected_time_to_failure_hours")
        runner_projection = runner_latest_state.get("projected_time_to_failure")
        if runner_projection:
            sii_intelligence["projected_time_to_failure"] = runner_projection
        if runner_projection_hours is not None:
            sii_intelligence["projected_time_to_failure_hours"] = runner_projection_hours
        if isinstance(sii_intelligence.get("rooms"), list):
            for index, room in enumerate(sii_intelligence["rooms"]):
                if not isinstance(room, dict):
                    continue
                if index == 0:
                    if runner_projection:
                        room["projected_time_to_failure"] = runner_projection
                    if runner_projection_hours is not None:
                        room["projected_time_to_failure_hours"] = runner_projection_hours
                elif "projected_time_to_failure" not in room:
                    room["projected_time_to_failure"] = "Monitoring"
    if "core_sii_outputs" in sii_intelligence:
        sii_intelligence["core_sii_outputs"] = build_core_sii_outputs(sii_intelligence)
    write_latest_sii_state( 
        { 
            **sii_intelligence, 
            "runner_module": sii_runner_result.get("runner_module"), 
            "core_engine": sii_runner_result.get("core_engine"), 
            "runner_used": sii_runner_result.get("runner_used"), 
            "last_processed_at": now_iso(), 
        } 
    )
    logger.info(
        "upload_result_calculated filename=%s rows=%s columns=%s readiness=%s overall_result=%s primary_room=%s",
        filename,
        total_rows,
        len(columns),
        data_quality.get("readiness"),
        engine_result.get("overall_result"),
        primary_room,
    )

    return {
        "filename": filename,
        "row_count": total_rows,
        "column_count": len(columns),
        "columns": columns,
        "preview_rows": preview_rows(columns, data_rows),
        "detected_timestamp_column": detected_timestamp_column,
        "warnings": warnings[:25],
        "numeric_profiles": numeric_profiles[:50],
        "timestamp_profile": timestamp_profile,
        "data_quality": data_quality,
        "baseline_analysis": baseline_analysis,
        "cultivation_mapping": schema_mapping,
        "schema_mapping": schema_mapping,
        "operator_report": operator_report,
        "engine_result": truncate_engine_result(engine_result),
        "temporal_math": temporal_math,
        "driver_attribution": driver_attribution,
        "sii_intelligence": sii_intelligence,
        "sii_runner_result": truncate_runner_result(sii_runner_result),
        "processing_trace": processing_trace,
        "processing_stats": processing_stats,
        "room_summary": room_summary,
        "ingestion_metadata": effective_source_metadata,
        "previous_upload_summary": previous_upload_summary,
        "validation_provenance": VALIDATION_PROVENANCE,
    } 


def summarize_result(result: dict[str, Any], completed_at: str) -> dict[str, Any]:
    runner = result["sii_runner_result"]
    stats = result.get("processing_stats", {})
    intelligence = result.get("sii_intelligence", {})
    ingestion_metadata = result.get("ingestion_metadata", {}) if isinstance(result.get("ingestion_metadata"), dict) else {}
    rooms = intelligence.get("rooms", []) if isinstance(intelligence.get("rooms"), list) else []
    room_count = len([room for room in rooms if isinstance(room, dict)])
    sparse_room_count = len(
        [
            room
            for room in rooms
            if isinstance(room, dict) and str(room.get("room_state", "")).lower() == "insufficient telemetry"
        ]
    )
    flagged_room_count = len(
        [
            room
            for room in rooms
            if isinstance(room, dict) and str(room.get("urgency", "")).lower() in {"review", "unstable"}
        ]
    )
    telemetry_profile = str(intelligence.get("telemetry_profile") or "unknown")
    telemetry_profile_confidence = str(intelligence.get("telemetry_profile_confidence") or "low")
    previous = result.get("previous_upload_summary") or {}
    current_score = intelligence.get("neraium_score")
    previous_score = previous.get("neraium_score")
    score_delta = None
    if isinstance(current_score, (int, float)) and isinstance(previous_score, (int, float)):
        score_delta = round(float(current_score) - float(previous_score), 2)
    artifacts = sii_completion_artifacts(result)
    return {
        "filename": result["filename"],
        "rows_processed": result["row_count"],
        "columns_detected": result["column_count"],
        "chunk_count": stats.get("chunk_count", 0),
        "sampled_rows": stats.get("sampled_rows", result["row_count"]),
        "memory_estimate_bytes": stats.get("memory_estimate_bytes", 0),
        "engine_runtime_seconds": stats.get("engine_runtime_seconds"),
        "last_processed_at": completed_at,
        "runner_used": runner["runner_used"],
        "runner_module": runner["runner_module"],
        "core_engine": runner["core_engine"],
        "source": "uploaded",
        "neraium_score": current_score,
        "operating_state": intelligence.get("facility_state"),
        "primary_room": intelligence.get("primary_room"),
        "drift_status": intelligence.get("urgency"),
        "upload_result_source": "file_upload",
        "sii_completed": all(artifacts.values()),
        "sii_completion_artifacts": artifacts,
        "diff": {
            "previous_filename": previous.get("filename"),
            "previous_processed_at": previous.get("last_processed_at"),
            "neraium_score_delta": score_delta,
        },
        "warnings": result["warnings"][:10],
        "runner_errors": runner.get("errors", [])[:5],
        "room_summary": result.get("room_summary", {}),
        "json_ingestion": {
            "source_type": ingestion_metadata.get("source_type"),
            "readings_received": ingestion_metadata.get("readings_received"),
            "readings_accepted": ingestion_metadata.get("readings_accepted"),
            "readings_rejected": ingestion_metadata.get("readings_rejected"),
            "sensors_detected": ingestion_metadata.get("sensors_detected"),
            "rejection_reasons": ingestion_metadata.get("rejection_reasons", {}),
            "parsing_notes": ingestion_metadata.get("parsing_notes", []),
        },
        "intelligence_metrics": {
            "room_count": room_count,
            "sparse_room_count": sparse_room_count,
            "flagged_room_count": flagged_room_count,
            "telemetry_profile": telemetry_profile,
            "telemetry_profile_confidence": telemetry_profile_confidence,
            "operational_signal_profile": str(intelligence.get("operational_signal_profile") or "unknown"),
            "operational_signal_profile_confidence": str(intelligence.get("operational_signal_profile_confidence") or "low"),
            "unknown_profile": (
                (telemetry_profile == "unknown" or telemetry_profile_confidence == "low")
                and str(intelligence.get("operational_signal_profile") or "unknown") == "unknown"
            ),
        },
        "adaptive_learning": result.get("adaptive_learning", {}),
    }


def sii_completion_artifacts(result: dict[str, Any]) -> dict[str, bool]:
    runner = result.get("sii_runner_result") if isinstance(result, dict) else None
    intelligence = result.get("sii_intelligence") if isinstance(result, dict) else None
    processing_trace = result.get("processing_trace") if isinstance(result, dict) else None
    engine_result = result.get("engine_result") if isinstance(result, dict) else None
    core_outputs = intelligence.get("core_sii_outputs") if isinstance(intelligence, dict) else None
    if isinstance(intelligence, dict) and not isinstance(core_outputs, dict):
        core_outputs = build_core_sii_outputs(intelligence)
        intelligence["core_sii_outputs"] = core_outputs
    emerging_instability_present = isinstance(core_outputs, dict) and isinstance(core_outputs.get("emerging_instability"), dict) and bool(core_outputs.get("emerging_instability", {}).get("state"))
    affected_system_present = isinstance(core_outputs, dict) and isinstance(core_outputs.get("affected_system"), dict) and bool(core_outputs.get("affected_system", {}).get("primary"))
    factors = core_outputs.get("contributing_factors") if isinstance(core_outputs, dict) else None
    contributing_factors_present = isinstance(factors, list) and len([item for item in factors if str(item).strip()]) > 0
    return {
        "runner_used": bool(runner and runner.get("runner_used")),
        "intelligence_present": isinstance(intelligence, dict) and bool(intelligence),
        "processing_trace_present": isinstance(processing_trace, dict) and bool(processing_trace),
        "engine_result_present": isinstance(engine_result, dict) and bool(engine_result),
        "core_emerging_instability_present": emerging_instability_present,
        "core_affected_system_present": affected_system_present,
        "core_contributing_factors_present": contributing_factors_present,
    }


def latest_upload_path() -> Path:
    return RUNTIME_DIR / "latest_upload.json"


def latest_upload_result_path() -> Path:
    return RUNTIME_DIR / "latest_upload_result.json"


def latest_upload_history_path() -> Path:
    return RUNTIME_DIR / "upload_history.json"


def write_latest_upload_summary(job_id: str, summary: dict[str, Any], *, append_history: bool = True) -> None: 
    ensure_runtime_dirs()
    path = latest_upload_path()
    upsert_latest_payload("latest_upload_summary", {"job_id": job_id, **summary}) 
    LATEST_UPLOAD_CACHE["summary"] = {"job_id": job_id, **summary}
    atomic_write_json(path, {"job_id": job_id, **summary}) 
    if append_history:
        append_upload_history({"job_id": job_id, **summary})
    logger.info(
        "upload_result_persisted kind=summary job_id=%s filename=%s rows=%s columns=%s",
        job_id,
        summary.get("filename"),
        summary.get("rows_processed"),
        summary.get("columns_detected"),
    )


def write_latest_upload_result(job_id: str, result: dict[str, Any], *, completed_at: str | None = None) -> None: 
    ensure_runtime_dirs()
    path = latest_upload_result_path()
    persistable = build_persistable_upload_result(job_id, result) 
    if completed_at:
        persistable["completed_at"] = completed_at
        persistable["last_processed_at"] = completed_at
        if isinstance(persistable.get("sii_intelligence"), dict):
            persistable["sii_intelligence"]["last_updated"] = completed_at
    upsert_latest_payload("latest_upload_result", persistable) 
    upsert_latest_payload(upload_result_key(job_id), persistable)
    LATEST_UPLOAD_CACHE["result"] = persistable
    atomic_write_json(path, persistable) 
    logger.info(
        "upload_result_persisted kind=detailed job_id=%s filename=%s rows=%s columns=%s",
        job_id,
        persistable.get("filename"),
        persistable.get("row_count"),
        persistable.get("column_count"),
    )


def upload_result_key(job_id: str) -> str:
    return f"upload_result:{job_id}"


def read_upload_result_by_job_id(job_id: str) -> dict[str, Any] | None:
    if not job_id:
        return None
    payload = read_latest_payload(upload_result_key(job_id))
    if isinstance(payload, dict):
        return payload
    latest = read_latest_upload_result()
    if isinstance(latest, dict) and str(latest.get("job_id")) == str(job_id):
        return latest
    return None


def read_latest_upload_summary() -> dict[str, Any] | None: 
    ensure_runtime_dirs() 
    if isinstance(LATEST_UPLOAD_CACHE.get("summary"), dict):
        if payload_superseded_by_reset(LATEST_UPLOAD_CACHE["summary"], is_summary=True):
            LATEST_UPLOAD_CACHE["summary"] = None
            return None
        return LATEST_UPLOAD_CACHE["summary"]
    db_payload = read_latest_payload("latest_upload_summary") 
    if db_payload is not None: 
        if payload_superseded_by_reset(db_payload, is_summary=True):
            LATEST_UPLOAD_CACHE["summary"] = None
            return None
        LATEST_UPLOAD_CACHE["summary"] = db_payload
        return db_payload 
    path = latest_upload_path()
    if not path.exists():
        return None
    try: 
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload_superseded_by_reset(payload, is_summary=True):
            LATEST_UPLOAD_CACHE["summary"] = None
            return None
        LATEST_UPLOAD_CACHE["summary"] = payload
        return payload
    except (OSError, json.JSONDecodeError): 
        return None 


def read_latest_upload_result() -> dict[str, Any] | None: 
    ensure_runtime_dirs() 
    if isinstance(LATEST_UPLOAD_CACHE.get("result"), dict):
        if payload_superseded_by_reset(LATEST_UPLOAD_CACHE["result"], is_summary=False):
            LATEST_UPLOAD_CACHE["result"] = None
            return None
        return LATEST_UPLOAD_CACHE["result"]
    db_payload = read_latest_payload("latest_upload_result") 
    if db_payload is not None: 
        if payload_superseded_by_reset(db_payload, is_summary=False):
            LATEST_UPLOAD_CACHE["result"] = None
            return None
        LATEST_UPLOAD_CACHE["result"] = db_payload
        return db_payload 
    path = latest_upload_result_path()
    if not path.exists():
        return None
    try: 
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload_superseded_by_reset(payload, is_summary=False):
            LATEST_UPLOAD_CACHE["result"] = None
            return None
        LATEST_UPLOAD_CACHE["result"] = payload
        return payload
    except (OSError, json.JSONDecodeError): 
        return None 


def read_upload_history(limit: int = 5) -> list[dict[str, Any]]:
    ensure_runtime_dirs()
    path = latest_upload_history_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    history = [item for item in payload if isinstance(item, dict)]
    history.sort(key=lambda item: item.get("last_processed_at") or "", reverse=True)
    return history[:limit]


def append_upload_history(summary: dict[str, Any], limit: int = 12) -> None:
    path = latest_upload_history_path()
    existing = read_upload_history(limit=limit)
    filtered = [item for item in existing if item.get("job_id") != summary.get("job_id")]
    atomic_write_json_list(path, [summary, *filtered][:limit])


def build_evidence_record(
    metadata: dict[str, Any],
    result: dict[str, Any],
    summary: dict[str, Any],
    completed_at: str,
    status: str,
) -> dict[str, Any]:
    intelligence = result.get("sii_intelligence", {})
    processing_stats = result.get("processing_stats", {})
    driver = intelligence.get("primary_driver")
    evidence_summary = intelligence.get("supporting_evidence") or []
    rows_received = result.get("row_count", 0)
    rows_rejected = processing_stats.get("malformed_rows", 0)
    rows_accepted = max(rows_received - rows_rejected, 0)
    sensors_detected = len(result.get("numeric_profiles", []))
    room = intelligence.get("primary_room") or primary_room_from_summary(result.get("room_summary", {}))
    record = {
        "run_id": metadata.get("job_id"),
        "adaptive_site_key": derive_site_key(result),
        "source_type": "file_upload",
        "source_name": metadata.get("filename"),
        "filename": metadata.get("filename"),
        "created_at": metadata.get("started_at"),
        "completed_at": completed_at,
        "status": status,
        "rows_received": rows_received,
        "rows_accepted": rows_accepted,
        "rows_rejected": rows_rejected,
        "sensors_detected": sensors_detected,
        "system_id": room,
        "room": room,
        "operating_state": intelligence.get("facility_state"),
        "neraium_score": intelligence.get("neraium_score"),
        "drift_status": intelligence.get("urgency"),
        "primary_drivers": [driver] if driver else [],
        "structural_archetypes": [item["name"] for item in derive_interpretive_archetypes(result)],
        "evidence_summary": evidence_summary[:6],
        "warnings": result.get("warnings", [])[:10],
        "errors": result.get("sii_runner_result", {}).get("errors", [])[:5],
        "input_hash": metadata.get("input_hash"),
        "result_hash": digest_payload(summary),
        "initiated_by": metadata.get("initiated_by", "anonymous"),
    }
    append_event_memory(
        site_key=record["adaptive_site_key"],
        run_id=str(record["run_id"]),
        completed_at=completed_at,
        summary=summary,
        result=result,
    )
    return record


def latest_completed_job_summary() -> dict[str, Any] | None:
    reset_marker = read_latest_payload("latest_upload_reset_at")
    reset_at = parse_timestamp(reset_marker) if isinstance(reset_marker, str) else None
    latest = read_latest_upload_summary()
    if latest:
        latest_completed_at = parse_timestamp(str(latest.get("last_processed_at") or latest.get("completed_at") or ""))
        if reset_at and (latest_completed_at is None or latest_completed_at <= reset_at):
            return None
        return latest
    completed_jobs: list[dict[str, Any]] = [
        metadata for metadata in list_upload_jobs(status="COMPLETE", limit=100)
        if normalize_status(str(metadata.get("status"))) == "COMPLETE"
    ]
    if not completed_jobs:
        for path in JOB_DIR.glob("*.json"):
            try:
                metadata = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if normalize_status(str(metadata.get("status"))) == "COMPLETE":
                completed_jobs.append(metadata)
    if not completed_jobs:
        return None
    completed_jobs.sort(key=lambda item: item.get("completed_at") or "", reverse=True)
    latest_job = completed_jobs[0]
    result_summary = latest_job.get("result_summary")
    if not isinstance(result_summary, dict):
        return None
    summary_completed_at = parse_timestamp(
        str(result_summary.get("last_processed_at") or latest_job.get("completed_at") or ""),
    )
    if reset_at and (summary_completed_at is None or summary_completed_at <= reset_at):
        return None
    return result_summary


def reset_latest_upload_state(*, purge_job_records: bool = False) -> None: 
    """Clear persisted latest upload summary/result/history for runtime reset flows."""
    ensure_runtime_dirs()
    upsert_latest_payload("latest_upload_reset_at", now_iso()) 
    upsert_latest_payload("latest_upload_summary", None) 
    upsert_latest_payload("latest_upload_result", None) 
    delete_latest_payload_prefix("upload_result:")
    LATEST_UPLOAD_CACHE["summary"] = None
    LATEST_UPLOAD_CACHE["result"] = None
    atomic_write_json_list(latest_upload_history_path(), [])
    if purge_job_records:
        clear_upload_runtime_tables()
        for directory in (UPLOAD_DIR, JOB_DIR, LEGACY_JOB_DIR):
            if not directory.exists():
                continue
            for child in directory.iterdir():
                try:
                    if child.is_file():
                        child.unlink(missing_ok=True)
                except OSError:
                    logger.warning("latest_upload_state_reset_job_cleanup_failed path=%s", child)
    for path in (latest_upload_path(), latest_upload_result_path()):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("latest_upload_state_reset_file_cleanup_failed path=%s", path) 


def warm_latest_upload_cache() -> None:
    LATEST_UPLOAD_CACHE["summary"] = read_latest_payload("latest_upload_summary")
    LATEST_UPLOAD_CACHE["result"] = read_latest_payload("latest_upload_result")


def read_upload_cache_stats() -> dict[str, int]:
    return {
        "hash_cache_hits": int(UPLOAD_CACHE_STATS.get("hash_cache_hits", 0)),
        "hash_cache_misses": int(UPLOAD_CACHE_STATS.get("hash_cache_misses", 0)),
    }


def truncate_engine_result(engine_result: dict[str, Any]) -> dict[str, Any]:
    return {
        **engine_result,
        "signals": engine_result.get("signals", [])[:20],
        "evidence": engine_result.get("evidence", [])[:20],
        "audit_trace": engine_result.get("audit_trace", [])[:50],
    }


def truncate_runner_result(runner_result: dict[str, Any]) -> dict[str, Any]:
    latest_state = runner_result.get("latest_state")
    if latest_state:
        latest_state = {
            key: value
            for key, value in latest_state.items()
            if key not in {"instability_history", "regime_history", "velocity_history"}
        }
    return {
        **runner_result,
        "latest_state": latest_state,
        "evidence": runner_result.get("evidence", [])[:10],
        "errors": runner_result.get("errors", [])[:5],
    }


def build_persistable_upload_result(job_id: str, result: dict[str, Any]) -> dict[str, Any]:
    processing_trace = result.get("processing_trace", {}) if isinstance(result.get("processing_trace"), dict) else {}
    sii_intelligence = result.get("sii_intelligence", {}) if isinstance(result.get("sii_intelligence"), dict) else {}
    completed_at = (
        processing_trace.get("completed_at")
        or sii_intelligence.get("last_updated")
        or now_iso()
    )
    return {
        "job_id": job_id,
        "last_processed_at": completed_at,
        "completed_at": completed_at,
        "filename": result["filename"],
        "row_count": result["row_count"],
        "column_count": result["column_count"],
        "columns": result.get("columns", []),
        "preview_rows": result.get("preview_rows", []),
        "detected_timestamp_column": result.get("detected_timestamp_column"),
        "warnings": result.get("warnings", [])[:25],
        "numeric_profiles": result.get("numeric_profiles", [])[:25],
        "timestamp_profile": result.get("timestamp_profile", {}),
        "data_quality": result["data_quality"],
        "baseline_analysis": result.get("baseline_analysis", {}),
        "cultivation_mapping": result["cultivation_mapping"],
        "schema_mapping": result.get("schema_mapping", result["cultivation_mapping"]),
        "aquatic_schema": result.get("aquatic_schema", {}),
        "telemetry_profile": result.get("telemetry_profile"),
        "operational_signal_profile": result.get("operational_signal_profile"),
        "operator_report": result.get("operator_report", {}),
        "engine_result": result["engine_result"],
        "driver_attribution": result.get("driver_attribution", {}),
        "sii_intelligence": result["sii_intelligence"],
        "replay_timeline": sii_intelligence.get("replay_timeline", {}),
        "sii_runner_result": result.get("sii_runner_result", {}),
        "processing_trace": processing_trace,
        "processing_stats": result.get("processing_stats", {}),
        "room_summary": result.get("room_summary", {}),
        "ingestion_metadata": result.get("ingestion_metadata", {}),
        "source_name": result.get("source_name"),
        "source_url": result.get("source_url"),
        "source_type": result.get("source_type"),
        "connection_id": result.get("connection_id"),
        "validation_provenance": result.get("validation_provenance", {}),
        "adaptive_learning": result.get("adaptive_learning", {}),
    }


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def payload_superseded_by_reset(payload: dict[str, Any] | None, *, is_summary: bool) -> bool:
    if not isinstance(payload, dict):
        return False
    reset_marker = read_latest_payload("latest_upload_reset_at")
    reset_at = parse_timestamp(reset_marker) if isinstance(reset_marker, str) else None
    if reset_at is None:
        return False
    completed_at = parse_timestamp(
        str(
            payload.get("last_processed_at")
            or payload.get("completed_at")
            or (
                payload.get("processing_trace", {}).get("completed_at")
                if isinstance(payload.get("processing_trace"), dict)
                else ""
            )
            or (
                payload.get("sii_intelligence", {}).get("last_updated")
                if isinstance(payload.get("sii_intelligence"), dict)
                else ""
            )
        )
    )
    if completed_at is None:
        # If we cannot prove freshness post-reset, treat as superseded.
        return True
    return completed_at <= reset_at


def first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None


def nested_present(mapping: dict[str, Any], dotted_keys: list[str]) -> Any:
    for dotted in dotted_keys:
        current: Any = mapping
        found = True
        for part in dotted.split("."):
            if not isinstance(current, dict) or part not in current:
                found = False
                break
            current = current.get(part)
        if found and current is not None:
            return current
    return None


def coerce_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        raise ValueError("empty_numeric_value")
    if "," in text:
        text = text.replace(",", "")
    pieces = text.split()
    try:
        return float(pieces[0])
    except (ValueError, IndexError) as exc:
        raise ValueError("invalid_numeric_value") from exc


def looks_like_sensor_reading(item: dict[str, Any]) -> bool:
    value = first_present(item, ["value", "val", "reading", "measurement"])
    sensor = first_present(item, ["sensor_id", "sensorId", "sensor_name", "sensorName", "tag", "name", "point_name"])
    return value is not None and sensor is not None


def extract_json_snapshots(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if all(isinstance(item, dict) for item in payload):
            return payload
        raise ValueError("JSON telemetry file array entries must be objects.")
    if not isinstance(payload, dict):
        raise ValueError("JSON telemetry file must contain an object or array of telemetry objects.")

    for key in ["snapshots", "frames", "batches", "events", "payloads"]:
        nested = payload.get(key)
        if isinstance(nested, list) and nested and all(isinstance(item, dict) for item in nested):
            return nested

    direct_records = payload.get("records")
    if isinstance(direct_records, list) and direct_records and all(isinstance(item, dict) for item in direct_records):
        if all(looks_like_sensor_reading(item) for item in direct_records):
            return [{"readings": direct_records, **{k: v for k, v in payload.items() if k != "records"}}]

    return [payload]


def normalize_uploaded_json_payload(payload: Any, filename: str) -> tuple[list[NormalizedTelemetryRecord], dict[str, Any]]:
    snapshots = extract_json_snapshots(payload)

    normalized: list[NormalizedTelemetryRecord] = []
    total_received = 0
    total_rejected = 0
    scenarios: list[str] = []
    ticks: list[Any] = []
    latest_timestamp: str | None = None
    facility_id: str | None = None
    room_id: str | None = None
    source_id: str | None = None
    rejection_reasons: Counter[str] = Counter()
    parsing_notes: list[str] = []

    for snapshot in snapshots:
        records, metadata = normalize_uploaded_json_snapshot(snapshot, filename)
        normalized.extend(records)
        total_received += metadata["readings_received"]
        total_rejected += metadata["readings_rejected"]
        for reason, count in metadata.get("rejection_reasons", {}).items():
            rejection_reasons[reason] += int(count)
        if metadata.get("parsing_notes"):
            parsing_notes.extend(str(note) for note in metadata["parsing_notes"])
        if metadata.get("scenario"):
            scenarios.append(str(metadata["scenario"]))
        if metadata.get("tick") is not None:
            ticks.append(metadata["tick"])
        latest_timestamp = metadata.get("timestamp") or latest_timestamp
        facility_id = metadata.get("facility_id") or facility_id
        room_id = metadata.get("room_id") or room_id
        source_id = metadata.get("source_id") or source_id

    if not normalized:
        raise ValueError("JSON telemetry file did not contain any valid readings.")

    return normalized, {
        "source_id": source_id or filename,
        "facility_id": facility_id,
        "room_id": room_id,
        "timestamp": latest_timestamp,
        "source_type": "uploaded_json",
        "ingestion_type": "json_upload",
        "readings_received": total_received,
        "readings_accepted": len(normalized),
        "readings_rejected": total_rejected,
        "sensors_detected": len({record.sensor_id for record in normalized}),
        "scenario": scenarios[-1] if scenarios else None,
        "tick": ticks[-1] if ticks else None,
        "rejection_reasons": dict(rejection_reasons),
        "parsing_notes": sorted(set(parsing_notes))[:12],
    }


def normalize_uploaded_json_snapshot(snapshot: dict[str, Any], filename: str) -> tuple[list[NormalizedTelemetryRecord], dict[str, Any]]:
    readings = first_present(snapshot, ["readings", "records", "signals", "telemetry", "measurements", "data"])
    if isinstance(readings, dict):
        nested_values = [value for value in readings.values() if isinstance(value, list)]
        if nested_values:
            readings = nested_values[0]
    if not isinstance(readings, list) or not readings:
        raise ValueError("JSON telemetry object must include a non-empty readings/records/signals array.")

    source_id = str(first_present(snapshot, ["source_id", "sourceId", "source", "dataset_id"]) or filename)
    facility_id = str(first_present(snapshot, ["facility_id", "facilityId", "facility", "site_id", "siteId"]) or "uploaded-facility")
    room_id = str(first_present(snapshot, ["room_id", "roomId", "room", "zone", "bay"]) or "uploaded-room")
    scenario = snapshot.get("scenario")
    tick = snapshot.get("tick")
    payload_timestamp = first_present(snapshot, ["timestamp", "time", "ts", "datetime", "recorded_at"])
    normalized: list[NormalizedTelemetryRecord] = []
    rejected_reasons: Counter[str] = Counter()
    parsing_notes: list[str] = []

    for item in readings:
        if not isinstance(item, dict):
            rejected_reasons["non_object_record"] += 1
            continue
        sensor_id = first_present(item, ["sensor_id", "sensorId", "id", "tag_id", "tagId", "point_id"])
        sensor_name = first_present(item, ["sensor_name", "sensorName", "name", "tag", "point_name", "pointName"]) or sensor_id
        raw_value = first_present(item, ["value", "val", "reading", "measurement"])
        if raw_value is None:
            raw_value = nested_present(item, ["payload.value", "data.value", "reading.value"])
        timestamp = first_present(item, ["timestamp", "time", "ts", "datetime", "recorded_at", "at"]) or payload_timestamp
        if not sensor_id:
            rejected_reasons["missing_sensor_id"] += 1
            continue
        if raw_value is None:
            rejected_reasons["missing_value"] += 1
            continue
        if not timestamp:
            rejected_reasons["missing_timestamp"] += 1
            continue
        try:
            numeric_value = coerce_float(raw_value)
        except ValueError:
            rejected_reasons["invalid_numeric_value"] += 1
            continue
        inferred_room = first_present(item, ["room_id", "roomId", "room", "zone", "bay"])
        inferred_facility = first_present(item, ["facility_id", "facilityId", "facility", "site_id", "siteId"])
        inferred_source = first_present(item, ["source_id", "sourceId", "source"])
        effective_room = str(inferred_room or room_id)
        effective_facility = str(inferred_facility or facility_id)
        effective_source = str(inferred_source or source_id)
        normalized.append(
            NormalizedTelemetryRecord(
                source_id=effective_source,
                facility_id=effective_facility,
                room_id=effective_room,
                system_id=effective_facility,
                sensor_id=str(sensor_id),
                sensor_name=str(sensor_name),
                value=numeric_value,
                unit=str(first_present(item, ["unit", "uom"]) or "").strip().lower(),
                timestamp=str(timestamp),
                quality_status=str(first_present(item, ["quality", "status"]) or "good").strip().lower() or "good",
                metadata={
                    "scenario": scenario,
                    "tick": tick,
                    "ingestion_type": "json_upload",
                    "source_type": snapshot.get("source_type") or "uploaded_json",
                },
            )
        )

    if first_present(snapshot, ["records", "signals", "telemetry", "measurements"]):
        parsing_notes.append("Accepted alternate top-level readings key.")
    if any(key in snapshot for key in ["site_id", "siteId", "zone", "bay"]):
        parsing_notes.append("Mapped alternate facility/room keys.")

    rejected = sum(rejected_reasons.values())
    return normalized, {
        "source_id": source_id,
        "facility_id": facility_id,
        "room_id": room_id,
        "timestamp": payload_timestamp or (normalized[-1].timestamp if normalized else None),
        "source_type": snapshot.get("source_type") or "uploaded_json",
        "scenario": scenario,
        "tick": tick,
        "readings_received": len(readings),
        "readings_accepted": len(normalized),
        "readings_rejected": rejected,
        "sensors_detected": len({record.sensor_id for record in normalized}),
        "rejection_reasons": dict(rejected_reasons),
        "parsing_notes": parsing_notes,
    }


def build_rows_from_normalized_records(records: list[dict[str, Any]]) -> tuple[list[str], list[list[str]], dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    sensor_names: set[str] = set()
    room_counts: Counter[str] = Counter()

    for item in records:
        timestamp = str(item.get("timestamp") or "")
        room_id = str(item.get("room_id") or "Current room")
        facility_id = str(item.get("facility_id") or item.get("system_id") or "Current facility")
        sensor_name = str(item.get("sensor_name") or item.get("sensor_id") or "sensor")
        grouped.setdefault((timestamp, room_id, facility_id), {})[sensor_name] = item.get("value")
        room_counts[room_id] += 1
        sensor_names.add(sensor_name)

    ordered_sensors = sorted(sensor_names)
    columns = ["timestamp", "room", "facility_id", *ordered_sensors]
    rows: list[list[str]] = []
    for (timestamp, room_id, facility_id), values in sorted(grouped.items(), key=lambda item: item[0][0]):
        rows.append(
            [
                timestamp,
                room_id,
                facility_id,
                *["" if values.get(sensor_name) is None else str(values.get(sensor_name)) for sensor_name in ordered_sensors],
            ]
        )

    room_summary = {
        "room_count": len(room_counts),
        "rooms": [{"room": room, "row_count": count} for room, count in sorted(room_counts.items(), key=lambda item: (-item[1], item[0].lower()))],
        "total_rows": len(rows),
        "unassigned_rows": 0,
    }
    return columns, rows, room_summary


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    last_error: OSError | None = None
    for attempt in range(WRITE_RETRY_ATTEMPTS):
        try:
            temp_path.replace(path)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(WRITE_RETRY_DELAY_SECONDS * (attempt + 1))
    if last_error is not None:
        raise last_error


def atomic_write_json_list(path: Path, payload: list[dict[str, Any]]) -> None:
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    last_error: OSError | None = None
    for attempt in range(WRITE_RETRY_ATTEMPTS):
        try:
            temp_path.replace(path)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(WRITE_RETRY_DELAY_SECONDS * (attempt + 1))
    if last_error is not None:
        raise last_error


def first_room_column_index(columns: list[str]) -> int | None:
    for index, column in enumerate(columns):
        if any(token in column.lower() for token in ("room", "zone", "bay")):
            return index
    return None


def build_room_summary(columns: list[str], rows: list[list[str]], total_rows: int | None = None) -> dict[str, Any]:
    room_index = first_room_column_index(columns)
    if room_index is None:
        return room_summary_from_counts(Counter(), total_rows if total_rows is not None else len(rows))
    room_counts: Counter[str] = Counter()
    for row in rows:
        if room_index < len(row) and row[room_index].strip():
            room_counts[row[room_index].strip()] += 1
    return room_summary_from_counts(room_counts, total_rows if total_rows is not None else len(rows))


def build_room_assessments(
    *,
    columns: list[str],
    rows: list[list[str]],
    room_summary: dict[str, Any] | None,
    numeric_profiles: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    room_index = first_room_column_index(columns)
    if room_index is None:
        return {}

    numeric_columns = [profile["column"] for profile in numeric_profiles if profile.get("column") in columns]
    if not numeric_columns:
        return {}
    numeric_indexes = [columns.index(column) for column in numeric_columns]

    grouped: dict[str, list[list[float]]] = {}
    for row in rows:
        if room_index >= len(row):
            continue
        room_name = row[room_index].strip()
        if not room_name:
            continue
        values: list[float] = []
        for idx in numeric_indexes:
            raw = row[idx].strip() if idx < len(row) else ""
            parsed = parse_numeric_value(raw)
            if parsed is None:
                values.append(float("nan"))
            else:
                values.append(parsed)
        if values and not all(np.isnan(value) for value in values):
            grouped.setdefault(room_name, []).append(values)

    detail_map = {
        str(item.get("room")): int(item.get("row_count") or 0)
        for item in ((room_summary or {}).get("rooms") or [])
        if isinstance(item, dict) and item.get("room")
    }

    assessments: dict[str, dict[str, Any]] = {}
    for room_name, vectors in grouped.items():
        row_count = detail_map.get(room_name, len(vectors))
        if len(vectors) < 4:
            assessments[room_name] = {
                "urgency": "review",
                "room_state": "Insufficient telemetry",
                "primary_driver": "Insufficient per-room telemetry context",
                "driver_category": "sensor_network",
                "attribution_confidence": "low",
                "why_flagged": "insufficient room-level telemetry to confirm a stable trend",
                "supporting_evidence": [
                    f"Only {len(vectors)} usable numeric row(s) were available for this room.",
                    "Additional room-level telemetry is required to assess drift confidence.",
                ],
                "what_to_check": [
                    "Collect additional room-level telemetry for this system.",
                    "Verify room tags and timestamp consistency for this source.",
                ],
                "recommended_operator_review": "Collect more room telemetry before clearing this system",
                "next_operator_move": "Collect more room telemetry before clearing this system",
                "relationship_evidence": [
                    "Room-level relationship evidence is limited due to sparse telemetry.",
                    "Signal coupling cannot be confirmed until more room samples are available.",
                ],
                "structural_explanation": [
                    "This room does not yet have enough telemetry depth for a structural coupling read.",
                    "Additional readings are required before drift and coupling can be validated.",
                    "Treat this as a telemetry sufficiency alert, not a failure prediction.",
                ],
                "projected_time_to_failure": "Unknown until additional telemetry is available",
                "projected_time_to_failure_hours": None,
                "confidence": 52,
                "confidence_components": {
                    "data_sufficiency": "low",
                    "signal_strength": "low",
                    "relationship_support": "low",
                    "persistence": "low",
                },
            }
            continue

        arr = np.asarray(vectors, dtype=float)
        split = max(2, min(len(arr) // 2, 20))
        baseline = arr[:split]
        recent = arr[-split:]
        baseline_mean = np.nan_to_num(np.nanmean(baseline, axis=0), nan=0.0)
        recent_mean = np.nan_to_num(np.nanmean(recent, axis=0), nan=0.0)
        safe_baseline = np.where(np.abs(baseline_mean) < 1e-6, 1.0, np.abs(baseline_mean))
        normalized_delta = np.abs(recent_mean - baseline_mean) / safe_baseline
        drift_score = float(np.clip(np.nan_to_num(np.nanmean(normalized_delta), nan=0.0), 0.0, 3.0))
        transition = np.abs(recent[-1] - recent[0]) / safe_baseline
        transition_score = float(np.clip(np.nan_to_num(np.nanmean(transition), nan=0.0), 0.0, 3.0))
        variability_score = float(np.clip(np.nan_to_num(np.nanstd(recent), nan=0.0), 0.0, 3.0))

        if drift_score >= 0.3:
            urgency = "unstable"
            state = "Needs action"
            confidence = 86
            why = "room-level telemetry drift is strong relative to this room baseline"
            projected = "Approximately 8 hours at current trajectory"
            projected_hours = 8
            driver_category = "process_timing"
            attribution_confidence = "high"
            confidence_components = {
                "data_sufficiency": "high",
                "signal_strength": "high",
                "relationship_support": "high",
                "persistence": "high",
            }
        elif drift_score >= 0.12:
            urgency = "review"
            state = "Drift observed"
            confidence = 74
            why = "room-level telemetry moved away from baseline and should be reviewed"
            projected = "Approximately 2 days at current trajectory"
            projected_hours = 48
            driver_category = "thermal_control"
            attribution_confidence = "medium"
            confidence_components = {
                "data_sufficiency": "medium",
                "signal_strength": "medium",
                "relationship_support": "medium",
                "persistence": "medium",
            }
        else:
            urgency = "nominal"
            state = "Stable"
            confidence = 66
            why = "room-level telemetry remains near recent operating baseline"
            projected = "More than 3 weeks at current trajectory"
            projected_hours = 504
            driver_category = "stable_monitoring"
            attribution_confidence = "medium"
            confidence_components = {
                "data_sufficiency": "medium",
                "signal_strength": "low",
                "relationship_support": "medium",
                "persistence": "medium",
            }

        if urgency == "unstable":
            relationship_evidence = [
                "Cross-signal room coupling is shifting faster than recent baseline behavior.",
                "Transition-to-recovery timing between room signals is widening.",
            ]
            structural_explanation = [
                "Room-level drift and transition pressure indicate active structural divergence.",
                "Signal relationships are moving in the same direction as the observed room drift.",
                "Intervention timing is likely compressing if this trend persists.",
            ]
        elif urgency == "review":
            relationship_evidence = [
                "Room signal relationships are less synchronized than the recent baseline.",
                "Transition behavior suggests moderate coupling drift that should be reviewed.",
            ]
            structural_explanation = [
                "Room-level drift is present but not yet in an acute range.",
                "Coupling behavior has shifted enough to warrant operator review.",
                "Monitoring continuity is important before trend confirmation.",
            ]
        else:
            relationship_evidence = [
                "Room signal relationships are broadly consistent with baseline behavior.",
                "No meaningful cross-signal decoupling is currently visible.",
            ]
            structural_explanation = [
                "Room topology appears behaviorally stable over recent windows.",
                "Drift remains low and relationship coupling is not degrading.",
                "Continue routine monitoring for any transition changes.",
            ]

        assessments[room_name] = {
            "urgency": urgency,
            "room_state": state,
            "primary_driver": "Room-level telemetry trend",
            "driver_category": driver_category,
            "attribution_confidence": attribution_confidence,
            "why_flagged": why,
            "supporting_evidence": [
                f"Room drift score is {round(drift_score, 4)} from {row_count} telemetry row(s).",
                f"Room transition score is {round(transition_score, 4)} with variability {round(variability_score, 4)}.",
                "Baseline and recent room windows were compared using numeric channel means.",
            ],
            "relationship_evidence": relationship_evidence,
            "structural_explanation": structural_explanation,
            "what_to_check": [
                f"Review {room_name} trend shift against recent facility logs.",
                "Validate room-level sampling consistency and timestamp continuity.",
            ],
            "recommended_operator_review": f"Review {room_name} room-level drift trend",
            "next_operator_move": f"Review {room_name} room-level drift trend",
            "projected_time_to_failure": projected,
            "projected_time_to_failure_hours": projected_hours,
            "confidence": confidence,
            "confidence_components": confidence_components,
        }
    return assessments


def classify_telemetry_profile(
    *,
    columns: list[str],
    rows: list[list[str]],
    numeric_profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    lowered_columns = [str(column).lower().replace("_", " ") for column in columns]
    scorecard: dict[str, int] = {
        "pool_hottub_systems": 0,
        "cultivation_climate": 0,
        "hvac_systems": 0,
        "electrical_systems": 0,
        "energy_schedule": 0,
        "sensor_health": 0,
        "irrigation_events": 0,
    }
    matched_signals: dict[str, list[str]] = {key: [] for key in scorecard}

    keyword_sets = {
        "pool_hottub_systems": [
            "pool",
            "spa",
            "hot tub",
            "hottub",
            "jacuzzi",
            "water temp",
            "orp",
            "chlorine",
            "bromine",
            "ph",
            "alkalinity",
            "circulation",
            "heater",
            "filter pump",
            "sanitizer",
        ],
        "cultivation_climate": [
            "humidity",
            "temperature",
            "co2",
            "vpd",
            "dehumid",
            "hvac",
            "airflow",
            "light",
            "irrigation",
            "substrate",
        ],
        "hvac_systems": [
            "hvac",
            "air handler",
            "ahu",
            "supply temp",
            "return temp",
            "static pressure",
            "damper",
            "compressor",
            "chiller",
            "boiler",
            "ventilation",
            "cfm",
            "duct",
            "coil",
        ],
        "electrical_systems": [
            "voltage",
            "current",
            "amp",
            "kw",
            "kwh",
            "power factor",
            "breaker",
            "phase",
            "transformer",
            "harmonic",
            "frequency",
            "panel",
            "bus",
        ],
        "energy_schedule": [
            "power",
            "kw",
            "kwh",
            "load",
            "demand",
            "voltage",
            "current",
            "schedule",
            "tariff",
            "phase",
        ],
        "sensor_health": [
            "battery",
            "signal",
            "rssi",
            "latency",
            "packet",
            "stale",
            "quality",
            "uptime",
            "status",
        ],
        "irrigation_events": [
            "event",
            "valve",
            "dose",
            "feed",
            "cycle",
            "pulse",
            "on off",
            "irrigation event",
            "pump on",
        ],
    }

    for column in lowered_columns:
        for profile, keywords in keyword_sets.items():
            for keyword in keywords:
                if keyword in column:
                    scorecard[profile] += 1
                    if keyword not in matched_signals[profile]:
                        matched_signals[profile].append(keyword)
                    break

    event_like_columns = estimate_event_like_columns(columns=columns, rows=rows, numeric_profiles=numeric_profiles)
    if event_like_columns > 0:
        scorecard["irrigation_events"] += event_like_columns
        matched_signals["irrigation_events"].append(f"event_like_columns={event_like_columns}")

    ranked = sorted(scorecard.items(), key=lambda item: item[1], reverse=True)
    top_profile, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    if top_score < 2:
        telemetry_profile = "unknown"
        confidence = "low"
    elif top_score >= 4 and top_score >= (second_score + 2):
        telemetry_profile = top_profile
        confidence = "high"
    elif top_score > second_score:
        telemetry_profile = top_profile
        confidence = "medium"
    else:
        telemetry_profile = "unknown"
        confidence = "low"

    modality = "event" if telemetry_profile == "irrigation_events" else "continuous"
    if telemetry_profile == "unknown":
        modality = "unknown"

    profile_signals = matched_signals.get(top_profile, [])
    if telemetry_profile == "unknown":
        profile_signals = []
    return {
        "telemetry_profile": telemetry_profile,
        "telemetry_profile_confidence": confidence,
        "telemetry_profile_signals": profile_signals[:8],
        "telemetry_modality": modality,
    }


def classify_operational_signal_profile(
    *,
    columns: list[str],
    rows: list[list[str]],
    numeric_profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    lowered_columns = [str(column).lower().replace("_", " ") for column in columns]
    scorecard: dict[str, int] = {
        "mechanical_systems": 0,
        "water_systems": 0,
        "pool_aquatics": 0,
        "hvac_systems": 0,
        "electrical_systems": 0,
        "facility_operations": 0,
        "environmental_data": 0,
        "industrial_process_data": 0,
        "utility_infrastructure": 0,
        "network_digital_infrastructure": 0,
        "operational_events": 0,
    }
    matched_signals: dict[str, list[str]] = {key: [] for key in scorecard}

    keyword_sets = {
        "mechanical_systems": ["pump", "motor", "fan", "compressor", "bearing", "vibration", "vfd", "gearbox", "shaft", "lubrication"],
        "water_systems": ["flow", "pressure", "reservoir", "tank", "basin", "sump", "backwash", "filter", "turnover", "water age"],
        "pool_aquatics": ["pool", "spa", "orp", "chlorine", "bromine", "alkalinity", "hardness", "turbidity", "uv", "bather"],
        "hvac_systems": ["hvac", "ahu", "supply air", "return air", "mixed air", "duct", "damper", "chiller", "condenser", "evaporator"],
        "electrical_systems": ["voltage", "current", "frequency", "power factor", "energy", "demand", "transformer", "generator", "ups", "breaker"],
        "facility_operations": ["occupancy", "guest", "visitor", "door", "access", "parking", "elevator", "lighting", "security", "work order"],
        "environmental_data": ["ambient", "rainfall", "wind", "solar", "uv index", "air quality", "particulate", "noise", "groundwater", "flood"],
        "industrial_process_data": ["production", "throughput", "batch", "yield", "reject", "scrap", "cycle time", "downtime", "utilization", "inventory"],
        "utility_infrastructure": ["distribution pressure", "leak", "non-revenue water", "pump station", "lift station", "sewer", "overflow", "treatment", "sludge", "chlorine residual"],
        "network_digital_infrastructure": ["cpu", "memory", "storage", "network throughput", "packet loss", "latency", "api response", "error rate", "database", "authentication"],
        "operational_events": ["alarm", "acknowledg", "suppression", "intervention", "setpoint", "manual override", "maintenance", "inspection", "calibration", "event"],
    }

    for column in lowered_columns:
        for profile, keywords in keyword_sets.items():
            for keyword in keywords:
                if keyword in column:
                    scorecard[profile] += 1
                    if keyword not in matched_signals[profile]:
                        matched_signals[profile].append(keyword)
                    break

    event_like_columns = estimate_event_like_columns(columns=columns, rows=rows, numeric_profiles=numeric_profiles)
    if event_like_columns > 0:
        scorecard["operational_events"] += event_like_columns
        matched_signals["operational_events"].append(f"event_like_columns={event_like_columns}")

    ranked = sorted(scorecard.items(), key=lambda item: item[1], reverse=True)
    top_profile, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    if top_score < 2:
        profile = "unknown"
        confidence = "low"
    elif top_score >= 4 and top_score >= (second_score + 2):
        profile = top_profile
        confidence = "high"
    elif top_score > second_score:
        profile = top_profile
        confidence = "medium"
    else:
        profile = "unknown"
        confidence = "low"

    modality = "event" if profile == "operational_events" else "continuous"
    if profile == "unknown":
        modality = "unknown"

    profile_signals = matched_signals.get(top_profile, [])
    if profile == "unknown":
        profile_signals = []
    return {
        "operational_signal_profile": profile,
        "operational_signal_profile_confidence": confidence,
        "operational_signal_profile_signals": profile_signals[:8],
        "operational_signal_modality": modality,
    }


def estimate_event_like_columns(
    *,
    columns: list[str],
    rows: list[list[str]],
    numeric_profiles: list[dict[str, Any]],
) -> int:
    numeric_columns = [profile["column"] for profile in numeric_profiles if profile.get("column") in columns]
    if not numeric_columns or not rows:
        return 0

    event_name_tokens = ("event", "valve", "cycle", "dose", "feed", "on_off", "on off", "status", "command")
    event_candidate_columns = [
        column
        for column in numeric_columns
        if any(token in column.lower().replace("_", " ") for token in event_name_tokens)
    ]
    if not event_candidate_columns:
        return 0

    column_indexes = [columns.index(column) for column in event_candidate_columns]
    event_like_count = 0
    for idx in column_indexes:
        observed: set[float] = set()
        for row in rows[:250]:
            raw = row[idx].strip() if idx < len(row) else ""
            if not raw:
                continue
            parsed = parse_numeric_value(raw)
            if parsed is None:
                continue
            observed.add(parsed)
            if len(observed) > 3:
                break
        if observed and len(observed) <= 3:
            event_like_count += 1
    return event_like_count


def room_summary_from_counts(room_counts: Counter[str], total_rows: int) -> dict[str, Any]:
    rooms = [
        {"room": room, "row_count": count}
        for room, count in sorted(room_counts.items(), key=lambda item: (-item[1], item[0].lower()))
    ]
    return {
        "room_count": len(rooms),
        "rooms": rooms,
        "total_rows": total_rows,
        "unassigned_rows": max(total_rows - sum(item["row_count"] for item in rooms), 0),
    }


def primary_room_from_summary(room_summary: dict[str, Any]) -> str:
    rooms = room_summary.get("rooms") if isinstance(room_summary, dict) else []
    if isinstance(rooms, list) and rooms:
        first = rooms[0]
        if isinstance(first, dict) and first.get("room"):
            return str(first["room"])
    return "Current room"


def primary_room_from_upload(columns: list[str], rows: list[list[str]]) -> str:
    return primary_room_from_summary(build_room_summary(columns, rows))


def state_from_assessment(assessment: str) -> str:
    return "Needs review" if assessment == "needs_review" else "Monitoring"


def severity_from_assessment(assessment: str) -> str:
    return "review" if assessment == "needs_review" else "info"


def downsample_rows(rows: list[list[str]], limit: int) -> list[list[str]]:
    if len(rows) <= limit:
        return rows
    step = len(rows) / limit
    return [rows[min(len(rows) - 1, int(index * step))] for index in range(limit)]


def order_rows_chronologically(
    *,
    columns: list[str],
    rows: list[list[str]],
    timestamp_column: str | None,
    row_indexes: list[int] | None = None,
) -> tuple[list[list[str]], list[int] | None]:
    if not rows or not timestamp_column:
        return rows, row_indexes
    if timestamp_column not in columns:
        return rows, row_indexes
    indexed: list[tuple[float, int, list[str], int | None]] = []
    for local_index, row in enumerate(rows):
        source_index = row_indexes[local_index] if row_indexes and local_index < len(row_indexes) else local_index
        timestamp_value = parse_runner_timestamp(columns, row, timestamp_column, source_index)
        indexed.append((timestamp_value, local_index, row, source_index))
    indexed.sort(key=lambda item: (item[0], item[1]))
    ordered_rows = [item[2] for item in indexed]
    if row_indexes is None:
        return ordered_rows, None
    ordered_indexes = [int(item[3] or 0) for item in indexed]
    return ordered_rows, ordered_indexes


def build_replay_rows_from_full_csv(
    *,
    file_path: Path,
    columns: list[str],
    numeric_profiles: list[dict[str, Any]],
    total_rows: int,
    target_rows: int,
    timestamp_column: str | None,
) -> tuple[list[list[str]], list[int]]:
    if total_rows <= 0 or target_rows <= 0:
        return [], []
    profile_columns = {str(profile.get("column")) for profile in numeric_profiles if profile.get("column")}
    numeric_indexes = [index for index, name in enumerate(columns) if name in profile_columns]
    if not numeric_indexes:
        return [], []

    bin_count = max(32, min(total_rows, target_rows))
    bin_size = max(1, int(math.ceil(total_rows / bin_count)))
    replay_rows: list[list[str]] = []
    replay_indexes: list[int] = []
    active_bin = -1
    first_row_in_bin: list[str] | None = None
    last_row_in_bin: list[str] | None = None
    last_index = 0
    sums: dict[int, float] = {}
    counts: dict[int, int] = {}
    row_counter = -1

    def flush_bin() -> None:
        nonlocal first_row_in_bin, last_row_in_bin, last_index, sums, counts
        if first_row_in_bin is None or last_row_in_bin is None:
            return
        representative_row = list(last_row_in_bin)
        for column_index in numeric_indexes:
            value_count = counts.get(column_index, 0)
            if value_count <= 0:
                continue
            representative_row[column_index] = f"{(sums.get(column_index, 0.0) / value_count):.6f}"
        if timestamp_column and timestamp_column in columns:
            ts_index = columns.index(timestamp_column)
            if ts_index < len(representative_row) and ts_index < len(last_row_in_bin):
                representative_row[ts_index] = last_row_in_bin[ts_index]
        replay_rows.append(representative_row)
        replay_indexes.append(last_index)
        first_row_in_bin = None
        last_row_in_bin = None
        last_index = 0
        sums = {}
        counts = {}

    try:
        csv_file = file_path.open("r", encoding="utf-8-sig", newline="")
    except UnicodeDecodeError:
        return [], []

    with csv_file:
        reader = csv.reader(csv_file)
        try:
            next(reader)
        except StopIteration:
            return [], []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            row_counter += 1
            bin_index = min(bin_count - 1, row_counter // bin_size)
            if bin_index != active_bin:
                flush_bin()
                active_bin = bin_index
                first_row_in_bin = row
            last_row_in_bin = row
            last_index = row_counter
            for column_index in numeric_indexes:
                if column_index >= len(row):
                    continue
                raw = row[column_index].strip()
                if raw == "":
                    continue
                parsed = parse_numeric_value(raw)
                if parsed is None:
                    continue
                sums[column_index] = sums.get(column_index, 0.0) + parsed
                counts[column_index] = counts.get(column_index, 0) + 1
        flush_bin()

    ordered_rows, ordered_indexes = order_rows_chronologically(
        columns=columns,
        rows=replay_rows,
        timestamp_column=timestamp_column,
        row_indexes=replay_indexes,
    )
    return ordered_rows, ordered_indexes or replay_indexes


def replay_target_frames(total_rows: int) -> int:
    if total_rows < 10_000:
        return 60
    if total_rows < 100_000:
        return 100
    if total_rows <= 500_000:
        return 160
    if total_rows <= 1_000_000:
        return 220
    return 280


def replay_baseline_rows(total_rows: int) -> int:
    return max(10, min(100, total_rows))


def classify_structural_state(
    *,
    baseline_distance: float,
    drift_velocity: float,
    drift_acceleration: float,
    recent_distances: list[float],
) -> str:
    if len(recent_distances) >= 4 and recent_distances[-1] < recent_distances[-2] < recent_distances[-3]:
        if baseline_distance < 0.28:
            return "Recovery / Stabilizing"
    if baseline_distance >= 0.34 or drift_velocity >= 0.05:
        return "Alert"
    if baseline_distance >= 0.22 or drift_velocity >= 0.03:
        return "Drift emerging"
    if baseline_distance >= 0.12 or drift_velocity > 0.0 or drift_acceleration > 0.0:
        return "Watch"
    return "Healthy / Stable"


def replay_state_to_phase(state: str) -> str:
    normalized = state.lower()
    if "alert" in normalized:
        return "structural_fragmentation"
    if "drift" in normalized:
        return "propagation_activation"
    if "watch" in normalized:
        return "relationship_weakening"
    if "recovery" in normalized or "stabiliz" in normalized:
        return "recovery_or_escalation"
    return "stable_topology"


def build_structural_replay_timeline(
    *,
    columns: list[str],
    rows: list[list[str]],
    total_rows: int,
    numeric_profiles: list[dict[str, Any]],
    timestamp_column: str | None,
    primary_room: str,
    row_indexes: list[int] | None = None,
) -> dict[str, Any]:
    vector_rows = build_sensor_vectors(columns, rows, numeric_profiles)
    vectors = vector_rows["vectors"]
    sample_count = len(vectors)
    if sample_count < 4:
        return build_minimal_replay_timeline(
            columns=columns,
            rows=rows,
            total_rows=total_rows,
            timestamp_column=timestamp_column,
            primary_room=primary_room,
            row_indexes=row_indexes,
        )

    baseline_rows_total = replay_baseline_rows(total_rows)
    baseline_count = max(3, min(sample_count - 2, baseline_rows_total))
    available = sample_count - baseline_count
    if available <= 1:
        return build_minimal_replay_timeline(
            columns=columns,
            rows=rows,
            total_rows=total_rows,
            timestamp_column=timestamp_column,
            primary_room=primary_room,
            row_indexes=row_indexes,
        )

    frame_target = replay_target_frames(total_rows)
    frame_count = max(2, min(300, frame_target, available))
    window_size = max(5, min(64, baseline_count // 2))

    vector_matrix = np.asarray(vectors, dtype=float)
    baseline_vectors = vector_matrix[:baseline_count]
    baseline_mean = np.nan_to_num(np.nanmean(baseline_vectors, axis=0), nan=0.0)
    safe_baseline = np.where(np.abs(baseline_mean) < 1e-6, 1.0, np.abs(baseline_mean))
    baseline_filled = np.where(np.isnan(baseline_vectors), np.nanmean(baseline_vectors, axis=0), baseline_vectors)
    baseline_corr = np.corrcoef(np.transpose(np.nan_to_num(baseline_filled, nan=0.0))) if baseline_filled.shape[1] >= 2 else None

    numeric_columns = vector_rows["columns_used"]
    timeline: list[dict[str, Any]] = []
    prev_distance = 0.0
    prev_velocity = 0.0
    distances: list[float] = []

    dense_target = min(1200, available)
    dense_step = max(1, int(math.floor(available / max(dense_target, 1))))
    dense_positions = list(range(baseline_count, sample_count, dense_step))
    if not dense_positions or dense_positions[-1] != sample_count - 1:
        dense_positions.append(sample_count - 1)

    coarse_distances: list[tuple[int, float]] = []
    for sample_index in dense_positions:
        window_start = max(baseline_count, sample_index - window_size + 1)
        window_vectors = vector_matrix[window_start:sample_index + 1]
        window_mean = np.nan_to_num(np.nanmean(window_vectors, axis=0), nan=0.0)
        normalized_delta = np.abs(window_mean - baseline_mean) / safe_baseline
        baseline_distance = float(np.clip(np.nan_to_num(np.nanmean(normalized_delta), nan=0.0), 0.0, 2.0))
        coarse_distances.append((sample_index, baseline_distance))

    significance_candidates: list[tuple[float, int]] = []
    previous_distance = coarse_distances[0][1] if coarse_distances else 0.0
    previous_velocity = 0.0
    previous_state = None
    for sample_index, baseline_distance in coarse_distances:
        velocity = baseline_distance - previous_distance
        acceleration = velocity - previous_velocity
        state = classify_structural_state(
            baseline_distance=baseline_distance,
            drift_velocity=velocity,
            drift_acceleration=acceleration,
            recent_distances=[previous_distance, baseline_distance],
        )
        score = abs(velocity) + (2.0 * abs(acceleration)) + (0.25 if state != previous_state else 0.0)
        significance_candidates.append((score, sample_index))
        previous_distance = baseline_distance
        previous_velocity = velocity
        previous_state = state

    uniform_positions = np.linspace(baseline_count, sample_count - 1, num=frame_count, dtype=int).tolist()
    frame_positions_set = set(uniform_positions)
    for _, sample_index in sorted(significance_candidates, key=lambda item: item[0], reverse=True)[: frame_count * 2]:
        frame_positions_set.add(int(sample_index))
    frame_positions = sorted(frame_positions_set)
    if len(frame_positions) > 300:
        sampled = np.linspace(0, len(frame_positions) - 1, num=300, dtype=int).tolist()
        frame_positions = [frame_positions[index] for index in sampled]

    for frame_index, sample_index in enumerate(frame_positions):
        window_start = max(baseline_count, sample_index - window_size + 1)
        window_vectors = vector_matrix[window_start:sample_index + 1]
        window_mean = np.nan_to_num(np.nanmean(window_vectors, axis=0), nan=0.0)

        normalized_delta = np.abs(window_mean - baseline_mean) / safe_baseline
        baseline_distance = float(np.clip(np.nan_to_num(np.nanmean(normalized_delta), nan=0.0), 0.0, 2.0))
        drift_velocity = baseline_distance - prev_distance if frame_index > 0 else 0.0
        drift_acceleration = drift_velocity - prev_velocity if frame_index > 0 else 0.0

        col_shift = [
            {"column": column, "shift": float(normalized_delta[idx])}
            for idx, column in enumerate(numeric_columns)
            if idx < len(normalized_delta)
        ]
        col_shift.sort(key=lambda item: item["shift"], reverse=True)
        contributors = [item["column"] for item in col_shift[:3] if item["shift"] > 0]

        relationship_drift = None
        dominant_paths: list[str] = []
        if baseline_corr is not None and window_vectors.shape[1] >= 2:
            filled_window = np.where(np.isnan(window_vectors), np.nanmean(window_vectors, axis=0), window_vectors)
            window_corr = np.corrcoef(np.transpose(np.nan_to_num(filled_window, nan=0.0)))
            corr_delta = np.abs(window_corr - baseline_corr)
            relationship_drift = float(np.clip(np.nan_to_num(np.nanmean(corr_delta), nan=0.0), 0.0, 2.0))
            if np.isfinite(corr_delta).any():
                top_pair = np.unravel_index(np.nanargmax(corr_delta), corr_delta.shape)
                if top_pair[0] != top_pair[1] and top_pair[0] < len(numeric_columns) and top_pair[1] < len(numeric_columns):
                    dominant_paths.append(f"{numeric_columns[top_pair[0]]}_{numeric_columns[top_pair[1]]}")

        distances.append(baseline_distance)
        structural_state = classify_structural_state(
            baseline_distance=baseline_distance,
            drift_velocity=drift_velocity,
            drift_acceleration=drift_acceleration,
            recent_distances=distances,
        )
        phase = replay_state_to_phase(structural_state)

        sample_row_position = vector_rows["row_indexes"][sample_index]
        sample_window_position = vector_rows["row_indexes"][window_start]
        if row_indexes and len(row_indexes) == len(rows):
            global_row_start = min(total_rows - 1, max(0, int(row_indexes[sample_window_position])))
            global_row_end = min(total_rows - 1, max(0, int(row_indexes[sample_row_position])))
        else:
            global_row_start = min(total_rows - 1, int(round((sample_window_position / max(len(rows) - 1, 1)) * (total_rows - 1))))
            global_row_end = min(total_rows - 1, int(round((sample_row_position / max(len(rows) - 1, 1)) * (total_rows - 1))))

        start_ts = parse_runner_timestamp(columns, rows[sample_window_position], timestamp_column, sample_window_position)
        end_ts = parse_runner_timestamp(columns, rows[sample_row_position], timestamp_column, sample_row_position)

        confidence = float(np.clip(np.mean(~np.isnan(window_vectors)), 0.0, 1.0)) if window_vectors.size else 0.0

        timeline.append(
            {
                "timestamp": datetime.fromtimestamp(end_ts, tz=UTC).isoformat(),
                "frame_index": frame_index,
                "row_range": {"start": global_row_start + 1, "end": global_row_end + 1},
                "timestamp_range": {
                    "start": datetime.fromtimestamp(start_ts, tz=UTC).isoformat(),
                    "end": datetime.fromtimestamp(end_ts, tz=UTC).isoformat(),
                },
                "topology_state": {
                    "phase": phase,
                    "drift_index": round(baseline_distance, 6),
                    "fragmentation_indicator": round(relationship_drift or baseline_distance, 6),
                    "stability_state": structural_state,
                },
                "subsystem_pressure": {
                    "pressure_score": round(baseline_distance, 6),
                    "volatility_index": round(abs(drift_velocity), 6),
                    "compression_intensity": "HIGH_COMPRESSION" if baseline_distance >= 0.34 else ("MODERATE_COMPRESSION" if baseline_distance >= 0.22 else "LOW_COMPRESSION"),
                },
                "active_archetypes": [{"name": signal} for signal in contributors],
                "propagation_state": {
                    "dominant_paths": dominant_paths,
                    "activation_intensity": round(min(1.0, baseline_distance * 1.8), 6),
                    "propagation_acceleration": round(drift_acceleration, 6),
                    "recovery_convergence": "STABILIZING" if structural_state.startswith("Recovery") else "DIVERGING",
                },
                "evidence_state": {
                    "corroboration_strength": "HIGH" if confidence >= 0.8 else ("MODERATE" if confidence >= 0.6 else "LOW"),
                    "lineage_events": [],
                },
                "cognition_state": {
                    "facility_state": structural_state,
                    "confidence_tier": "STRUCTURAL_EVIDENCE_CONFIRMED" if confidence >= 0.8 else ("RELATIONSHIP_EVIDENCE_PRESENT" if confidence >= 0.6 else "BASELINE_EVIDENCE"),
                    "state_evolution": f"frame_{frame_index + 1}_of_{len(frame_positions)}",
                    "canonical_phase": phase,
                    "operational_phase": phase,
                },
                "memory_similarity": [],
                "continuation_window": {
                    "active_scenario": "Uploaded telemetry replay",
                    "window": structural_state,
                    "timing_window": f"rows {global_row_start + 1}-{global_row_end + 1}",
                },
                "baseline_distance": round(baseline_distance, 6),
                "drift_velocity": round(drift_velocity, 6),
                "drift_acceleration": round(drift_acceleration, 6),
                "relationship_drift": round(relationship_drift, 6) if relationship_drift is not None else None,
                "primary_contributors": contributors,
                "affected_subsystem": primary_room,
                "evidence_confidence": round(confidence, 4),
                "operator_interpretation": (
                    f"{structural_state}. Baseline separation {baseline_distance:.3f}; "
                    f"velocity {drift_velocity:.3f}; acceleration {drift_acceleration:.3f}."
                ),
                "total_frames": len(frame_positions),
                "timestamp_start": datetime.fromtimestamp(start_ts, tz=UTC).isoformat(),
                "timestamp_end": datetime.fromtimestamp(end_ts, tz=UTC).isoformat(),
                "row_start": global_row_start + 1,
                "row_end": global_row_end + 1,
                "structural_state": structural_state,
                "baseline_separation": round(baseline_distance, 6),
                "relationship_changes": dominant_paths,
                "topology_state_label": phase,
                "affected_area": primary_room,
                "operator_focus": "Confirm persistence across recent telemetry windows.",
                "operator_summary": f"{structural_state} across rows {global_row_start + 1}-{global_row_end + 1}.",
            }
        )

        prev_distance = baseline_distance
        prev_velocity = drift_velocity

    return {
        "meta": {
            "frame_count": len(timeline),
            "frame_target": frame_target,
            "baseline_rows": baseline_rows_total,
            "sampled_rows": sample_count,
            "total_rows": total_rows,
            "playback_speeds": [0.5, 1.0, 1.5, 2.0, 4.0],
            "canonical_flow": [
                "stable_topology",
                "relationship_weakening",
                "propagation_activation",
                "structural_fragmentation",
                "recovery_or_escalation",
            ],
        },
        "timeline": timeline,
    }


def build_minimal_replay_timeline(
    *,
    columns: list[str],
    rows: list[list[str]],
    total_rows: int,
    timestamp_column: str | None,
    primary_room: str,
    row_indexes: list[int] | None = None,
) -> dict[str, Any]:
    if not rows:
        return {"meta": {"frame_count": 0, "frame_target": 0}, "timeline": []}

    sample_count = len(rows)
    frame_target = replay_target_frames(max(total_rows, sample_count))
    frame_count = max(2, min(120, frame_target, sample_count))
    frame_positions = sorted(set(np.linspace(0, sample_count - 1, num=frame_count, dtype=int).tolist()))
    if frame_positions[-1] != sample_count - 1:
        frame_positions.append(sample_count - 1)

    timeline: list[dict[str, Any]] = []
    previous_position = 0
    for frame_index, sample_position in enumerate(frame_positions):
        window_start = previous_position if frame_index > 0 else 0
        previous_position = sample_position

        if row_indexes and len(row_indexes) == len(rows):
            global_row_start = min(total_rows - 1, max(0, int(row_indexes[window_start])))
            global_row_end = min(total_rows - 1, max(0, int(row_indexes[sample_position])))
        else:
            global_row_start = min(total_rows - 1, max(0, window_start))
            global_row_end = min(total_rows - 1, max(0, sample_position))

        start_ts = parse_runner_timestamp(columns, rows[window_start], timestamp_column, window_start)
        end_ts = parse_runner_timestamp(columns, rows[sample_position], timestamp_column, sample_position)
        stability_state = "Watch" if frame_index > 0 else "Healthy / Stable"
        phase = replay_state_to_phase(stability_state)

        timeline.append(
            {
                "timestamp": datetime.fromtimestamp(end_ts, tz=UTC).isoformat(),
                "frame_index": frame_index,
                "row_range": {"start": global_row_start + 1, "end": global_row_end + 1},
                "timestamp_range": {
                    "start": datetime.fromtimestamp(start_ts, tz=UTC).isoformat(),
                    "end": datetime.fromtimestamp(end_ts, tz=UTC).isoformat(),
                },
                "topology_state": {
                    "phase": phase,
                    "drift_index": 0.0,
                    "fragmentation_indicator": 0.0,
                    "stability_state": stability_state,
                },
                "subsystem_pressure": {
                    "pressure_score": 0.0,
                    "volatility_index": 0.0,
                    "compression_intensity": "LOW_COMPRESSION",
                },
                "active_archetypes": [],
                "propagation_state": {
                    "dominant_paths": [],
                    "activation_intensity": 0.0,
                    "propagation_acceleration": 0.0,
                    "recovery_convergence": "STABILIZING",
                },
                "evidence_state": {
                    "corroboration_strength": "LOW",
                    "lineage_events": [],
                },
                "cognition_state": {
                    "facility_state": stability_state,
                    "confidence_tier": "BASELINE_EVIDENCE",
                    "state_evolution": f"frame_{frame_index + 1}_of_{len(frame_positions)}",
                    "canonical_phase": phase,
                    "operational_phase": phase,
                },
                "memory_similarity": [],
                "continuation_window": {
                    "active_scenario": "Uploaded telemetry replay",
                    "window": stability_state,
                    "timing_window": f"rows {global_row_start + 1}-{global_row_end + 1}",
                },
                "baseline_distance": 0.0,
                "drift_velocity": 0.0,
                "drift_acceleration": 0.0,
                "relationship_drift": None,
                "primary_contributors": [],
                "affected_subsystem": primary_room,
                "evidence_confidence": 0.5,
                "operator_interpretation": "Replay window captured from uploaded telemetry timeline.",
                "total_frames": len(frame_positions),
                "timestamp_start": datetime.fromtimestamp(start_ts, tz=UTC).isoformat(),
                "timestamp_end": datetime.fromtimestamp(end_ts, tz=UTC).isoformat(),
                "row_start": global_row_start + 1,
                "row_end": global_row_end + 1,
                "structural_state": stability_state,
                "baseline_separation": 0.0,
                "relationship_changes": [],
                "topology_state_label": phase,
                "affected_area": primary_room,
                "operator_focus": "Collect additional numeric signal columns for full structural drift scoring.",
                "operator_summary": f"Replay window rows {global_row_start + 1}-{global_row_end + 1}.",
            }
        )

    return {
        "meta": {
            "frame_count": len(timeline),
            "frame_target": frame_target,
            "baseline_rows": 0,
            "sampled_rows": sample_count,
            "total_rows": total_rows,
            "replay_mode": "minimal_timestamp_fallback",
            "playback_speeds": [0.5, 1.0, 1.5, 2.0, 4.0],
            "canonical_flow": [
                "stable_topology",
                "relationship_weakening",
                "propagation_activation",
                "structural_fragmentation",
                "recovery_or_escalation",
            ],
        },
        "timeline": timeline,
    }


def estimate_rows_memory(rows: list[list[str]]) -> int:
    return sum(sum(len(cell) for cell in row) + len(row) * 8 for row in rows)
