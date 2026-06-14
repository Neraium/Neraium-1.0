from __future__ import annotations

import csv
import io
import json
import logging
import math
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

RUNTIME_DIR = Path("backend/runtime")
UPLOAD_DIR = RUNTIME_DIR / "uploads"
JOB_DIR = RUNTIME_DIR / "upload_jobs"
LEGACY_JOB_DIR = RUNTIME_DIR / "jobs"
JOBS: dict[str, dict[str, Any]] = {}
LATEST_UPLOAD_CACHE: dict[str, Any] = {"summary": None, "result": None}
_S3_CLIENT: Any | None = None
_RESET_BLOCK_PERSISTED = False
MAX_ANALYSIS_ROWS = int(os.getenv("NERAIUM_MAX_ANALYSIS_ROWS", "10000"))
CSV_PROGRESS_UPDATE_EVERY = int(os.getenv("NERAIUM_CSV_PROGRESS_UPDATE_EVERY", "5000"))
CSV_CHUNK_SIZE_ROWS = int(os.getenv("NERAIUM_CSV_CHUNK_SIZE_ROWS", "5000"))
logger = logging.getLogger(__name__)


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
    global RUNTIME_DIR, UPLOAD_DIR, JOB_DIR, LEGACY_JOB_DIR
    RUNTIME_DIR = Path(path)
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


def warm_latest_upload_cache() -> None:
    LATEST_UPLOAD_CACHE["summary"] = _read_shared_state("latest_upload_summary") or _read_json("latest_upload_summary.json")
    LATEST_UPLOAD_CACHE["result"] = _read_shared_state("latest_upload_result") or _read_json("latest_upload_result.json")


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
    try:
        delete_latest_payload_prefix("upload_")
        delete_latest_payload_prefix("latest_upload_")
    except Exception:
        pass
    _RESET_BLOCK_PERSISTED = True


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
        "status": status,
        "processing_state": str(status).lower(),
        "percent": progress,
        "progress": progress,
        "message": message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    JOBS[job_id] = payload
    _write_json(f"upload_status_{job_id}.json", payload)
    upsert_upload_job(payload)
    _write_shared_state(f"upload_status_{job_id}", payload)
    _write_shared_state("latest_upload_summary", payload)
    LATEST_UPLOAD_CACHE["summary"] = payload
    return payload
def _complete_with_partial_result(
    *,
    job_id: str,
    filename: str,
    error: Exception,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    snapshot = snapshot or {}

    columns = list(snapshot.get("columns") or [])
    rows = list(snapshot.get("sample_rows") or [])
    row_count = int(snapshot.get("row_count") or 0)
    chunk_count = snapshot.get("chunk_count")
    memory_estimate_bytes = snapshot.get("memory_estimate_bytes")
    error_message = str(error) or error.__class__.__name__

    result = {
        "job_id": job_id,
        "filename": filename,
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns,
        "preview_rows": [{key: value for key, value in row.items() if not str(key).startswith("__")} for row in rows[:10]],
        "detected_timestamp_column": snapshot.get("timestamp_column"),
        "numeric_profiles": [],
        "timestamp_profile": {
            "warnings": ["Full timestamp profiling was skipped because processing completed partially."]
        },
        "data_quality": {
            "status": "partial",
            "warnings": [
                "Upload completed, but full intelligence processing could not finish.",
                error_message,
            ],
        },
        "baseline_analysis": {
            "warnings": ["Full baseline analysis was skipped because processing completed partially."]
        },
        "cultivation_mapping": {"warnings": []},
        "operator_report": {},
        "engine_result": {
            "overall_result": "partial",
            "signals": [],
            "evidence": [],
        },
        "driver_attribution": {},
        "operating_state": "Partial upload processed",
        "drift_status": "partial",
        "sii_intelligence": {
            "sii_completed": False,
            "partial_result": True,
            "warning": "Upload completed with partial processing.",
        },
        "sii_runner_result": {
            "runner_used": False,
            "error": error_message,
        },
        "processing_trace": {
            "sii_pipeline_ran": False,
            "sii_completed": False,
            "completed_with_partial_result": True,
            "error": error_message,
            "rows_processed": row_count,
            "columns_analyzed": len(columns),
            "completed_at": now,
        },
        "processing_stats": {
            "used_streaming": True,
            "sampled_rows": len(rows),
            "chunk_count": chunk_count,
            "memory_estimate_bytes": memory_estimate_bytes,
        },
        "room_summary": {
            "room_count": 1,
            "rooms": [{"room": "Uploaded telemetry", "row_count": row_count}],
        },
        "ingestion_metadata": {"source_type": "csv_upload"},
        "source_type": "csv",
        "replay_timeline": {"meta": {"frame_count": 0}, "timeline": []},
        "replay_ready": False,
        "replay_frame_count": 0,
        "last_processed_at": now,
        "completed_at": now,
    }

    summary = {
        "job_id": job_id,
        "status_url": f"/api/data/upload-status/{job_id}",
        "status": "COMPLETE",
        "processing_state": "partial_complete",
        "percent": 100,
        "progress": 100,
        "result_available": True,
        "first_usable_available": True,
        "sii_completed": False,
        "replay_ready": False,
        "replay_frame_count": 0,
        "latest_replay_frames": 0,
        "replay_source": "partial",
        "last_processed_at": now,
        "filename": filename,
        "row_count": row_count,
        "column_count": len(columns),
        "rows_processed": row_count,
        "columns_detected": len(columns),
        "chunk_count": chunk_count,
        "warning": "Upload completed with partial processing.",
        "error": error_message,
        "message": "Upload completed, but full intelligence processing could not finish.",
        "propagation_stage": "partial_complete",
        "propagation_progress": 100,
        "propagation_label": "Partial upload complete.",
    }

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
    non_blank = [line for line in sample.splitlines() if line.strip()][:20]
    joined = "\n".join(non_blank)
    if not joined:
        raise ValueError("CSV file is empty.")
    try:
        return csv.Sniffer().sniff(joined, delimiters=",\t;|").delimiter
    except csv.Error:
        return "whitespace"


def _row_tokens(line: str, delimiter: str) -> list[str]:
    if delimiter == "whitespace":
        return line.strip().split()
    return next(csv.reader([line], delimiter=delimiter))


def _looks_like_header(tokens: list[str]) -> bool:
    if not tokens:
        return False
    numeric_count = sum(parse_numeric_value(token) is not None for token in tokens)
    timestamp_count = sum(parse_timestamp(token) is not None for token in tokens)
    return numeric_count + timestamp_count < max(1, len(tokens) // 2)


def _normalized_columns(tokens: list[str], *, header_present: bool) -> list[str]:
    if not header_present:
        return [f"column_{index + 1}" for index in range(len(tokens))]
    columns: list[str] = []
    seen: dict[str, int] = {}
    for index, token in enumerate(tokens):
        base = token.strip() or f"column_{index + 1}"
        seen[base] = seen.get(base, 0) + 1
        columns.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return columns


def _stream_csv_snapshot(path: Path, *, max_analysis_rows: int, job_id: str | None = None) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        sample_lines: list[str] = []
        while len(sample_lines) < 20 and sum(len(item) for item in sample_lines) < 65536:
            line = handle.readline()
            if line == "":
                break
            if line.strip():
                sample_lines.append(line.rstrip("\r\n"))

        if not sample_lines:
            raise ValueError("CSV file is empty.")

        delimiter = _detect_delimiter("\n".join(sample_lines))
        first_tokens = _row_tokens(sample_lines[0], delimiter)
        header_present = _looks_like_header(first_tokens)
        columns = _normalized_columns(first_tokens, header_present=header_present)
        if not columns:
            raise ValueError("CSV must include at least one column.")

        timestamp_column = _detect_timestamp_column(columns) if header_present else None
        timestamp_index = columns.index(timestamp_column) if timestamp_column in columns else None

        handle.seek(0)
        saw_header = not header_present
        detection_rows: list[list[str]] = []
        while True:
            line = handle.readline()
            if line == "":
                break
            if not line.strip():
                continue
            if header_present and not saw_header:
                saw_header = True
                continue
            tokens = _row_tokens(line.rstrip("\r\n"), delimiter)
            if len(tokens) != len(columns):
                continue
            row_values = [token.strip() for token in tokens]
            if len(detection_rows) < 1000:
                detection_rows.append(row_values)

        if not detection_rows:
            raise ValueError("CSV must include a header and at least one usable data row.")

        if timestamp_index is None:
            detected = detect_timestamp_column(columns, detection_rows)
            if detected in columns:
                timestamp_column = detected
                timestamp_index = columns.index(detected)

        identity_index = next(
            (
                index
                for index, column in enumerate(columns)
                if column.lower().strip() in {"room", "zone", "location", "area", "group", "system", "asset", "asset name", "zone name"}
            ),
            None,
        )
        excluded_indexes = {index for index in (timestamp_index, identity_index) if index is not None}
        numeric_indexes = [
            index
            for index in range(len(columns))
            if index not in excluded_indexes
            and sum(parse_numeric_value(row[index]) is not None for row in detection_rows)
            >= max(3, int(min(len(detection_rows), 1000) * 0.15))
        ]

        handle.seek(0)
        rows_received = 0
        blank_rows = 0
        malformed_rows = 0
        duplicate_timestamps = 0
        invalid_timestamps = 0
        no_numeric_values = 0
        rows_with_missing_values = 0
        rows_with_invalid_numeric = 0
        invalid_numeric_cells = 0
        seen_timestamps: set[str] = set()
        raw_rows_in_order: list[tuple[Any, dict[str, Any]]] = []
        header_skipped = not header_present

        for line in handle:
            if not line.strip():
                if header_skipped:
                    rows_received += 1
                    blank_rows += 1
                continue

            if not header_skipped:
                header_skipped = True
                continue

            rows_received += 1
            tokens = _row_tokens(line.rstrip("\r\n"), delimiter)
            if len(tokens) != len(columns):
                malformed_rows += 1
                continue

            raw_row = [token.strip() for token in tokens]
            parsed_ts = None
            if timestamp_index is not None:
                parsed_ts = parse_timestamp(raw_row[timestamp_index])
                if parsed_ts is None:
                    invalid_timestamps += 1
                    continue
                identity_value = raw_row[identity_index].strip() if identity_index is not None else ""
                timestamp_key = f"{identity_value}::{parsed_ts.isoformat()}"
                if timestamp_key in seen_timestamps:
                    duplicate_timestamps += 1
                    continue
                seen_timestamps.add(timestamp_key)

            row = {column: raw_row[index] for index, column in enumerate(columns)}
            row["__source_row_number"] = rows_received
            if parsed_ts is not None:
                row["__source_timestamp"] = parsed_ts.isoformat()
            missing_in_row = any(raw_row[index] == "" for index in numeric_indexes)
            invalid_in_row = False
            usable_numeric = 0
            for index in numeric_indexes:
                raw_value = raw_row[index]
                if raw_value == "":
                    continue
                numeric_value = parse_numeric_value(raw_value)
                if numeric_value is None:
                    row[columns[index]] = ""
                    invalid_numeric_cells += 1
                    invalid_in_row = True
                    continue
                row[columns[index]] = str(numeric_value)
                usable_numeric += 1
            if numeric_indexes and usable_numeric == 0:
                no_numeric_values += 1
                continue
            if missing_in_row:
                rows_with_missing_values += 1
            if invalid_in_row:
                rows_with_invalid_numeric += 1
            raw_rows_in_order.append((parsed_ts, row))

        if not raw_rows_in_order:
            raise ValueError("CSV contains no usable telemetry rows after cleaning.")

        rows_used = len(raw_rows_in_order)
        cleaned = sorted(raw_rows_in_order, key=lambda item: item[0]) if timestamp_index is not None else raw_rows_in_order
        sample_rows = [row for _, row in cleaned[:max_analysis_rows]]
        first_timestamp = cleaned[0][1].get(timestamp_column) if timestamp_column else None
        last_timestamp = cleaned[-1][1].get(timestamp_column) if timestamp_column else None
        memory_estimate_bytes = sum(sum(len(str(value or "")) for value in row.values()) for row in sample_rows)
        rows_dropped = rows_received - rows_used
        drop_reasons = {
            key: value
            for key, value in {
                "blank_row": blank_rows,
                "column_count_mismatch": malformed_rows,
                "invalid_timestamp": invalid_timestamps,
                "duplicate_timestamp": duplicate_timestamps,
                "no_usable_numeric_values": no_numeric_values,
            }.items()
            if value
        }
        warnings = []
        if rows_dropped:
            warnings.append(f"{rows_dropped} rows were dropped during safe cleaning.")
        if rows_with_missing_values:
            warnings.append(f"{rows_with_missing_values} rows contain missing numeric values.")
        if rows_with_invalid_numeric:
            warnings.append(f"{rows_with_invalid_numeric} rows contained non-numeric values that were ignored.")
        if delimiter == "whitespace":
            warnings.append("Whitespace-delimited telemetry was detected.")
        if not header_present:
            warnings.append("No header row was detected; generic column names were assigned.")
        if timestamp_index is not None and [item[0] for item in raw_rows_in_order] != [item[0] for item in cleaned]:
            warnings.append("Timestamps were unsorted and were ordered before analysis.")

        if job_id and rows_received >= CSV_PROGRESS_UPDATE_EVERY:
            _set_propagation_stage(job_id, stage="parsing_telemetry", progress=20, label=f"Parsed and cleaned {rows_received:,} rows.")

        return {
            "columns": columns,
            "timestamp_column": timestamp_column,
            "sample_rows": sample_rows,
            "row_count": rows_used,
            "rows_received": rows_received,
            "rows_used": rows_used,
            "rows_dropped": rows_dropped,
            "drop_reasons": drop_reasons,
            "quality_counts": {
                "rows_with_missing_values": rows_with_missing_values,
                "rows_with_invalid_numeric": rows_with_invalid_numeric,
                "invalid_numeric_cells": invalid_numeric_cells,
            },
            "cleaning_warnings": warnings,
            "delimiter": delimiter,
            "header_present": header_present,
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
            "chunk_count": max(1, (rows_received + CSV_CHUNK_SIZE_ROWS - 1) // CSV_CHUNK_SIZE_ROWS),
            "memory_estimate_bytes": int(memory_estimate_bytes),
        }


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
        data_quality["warnings"] = list(dict.fromkeys([*data_quality.get("warnings", []), reliability_warning]))

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
    if isinstance(latest_runner_state, dict):
        result["sii_intelligence"]["sii_runner_latest_state"] = latest_runner_state
        result["sii_intelligence"]["instability_index"] = latest_runner_state.get("instability_index")
        result["sii_intelligence"]["projected_time_to_failure"] = latest_runner_state.get("projected_time_to_failure")
        result["sii_intelligence"]["projected_time_to_failure_hours"] = latest_runner_state.get("projected_time_to_failure_hours")

    summary = {"job_id": job_id, "status_url": f"/api/data/upload-status/{job_id}", "status": "COMPLETE", "processing_state": "complete", "percent": 100, "progress": 100, "propagation_stage": "complete", "propagation_progress": 100, "propagation_label": "Complete.", "message": "Telemetry processing complete.", "result_available": True, "first_usable_available": True, "sii_completed": True, "replay_ready": frame_count > 0, "replay_frame_count": frame_count, "latest_replay_frames": frame_count, "replay_source": "persisted", "last_processed_at": now, "filename": filename, "row_count": row_count_total, "rows_received": result["ingestion_report"]["rows_received"], "rows_used": row_count_total, "rows_dropped": result["ingestion_report"]["rows_dropped"], "drop_reasons": result["ingestion_report"]["drop_reasons"], "processing_time_seconds": processing_time_seconds, "quality_warning": result["quality_warning"], "sii_reliable_enough_to_show": False, "column_count": len(columns), "rows_processed": row_count_total, "columns_detected": len(columns), "chunk_count": chunk_count, "runner_used": bool((runner_result or {}).get("runner_used")), "runner_module": RUNNER_MODULE, "core_engine": (runner_result or {}).get("core_engine"), "sii_completion_artifacts": {"runner_used": True, "intelligence_present": True, "processing_trace_present": True, "engine_result_present": True}, "result_summary": {"filename": filename, "sii_completed": True, "sii_completion_artifacts": {"runner_used": True, "intelligence_present": True, "processing_trace_present": True, "engine_result_present": True}, "runner_errors": []}}

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
    result = result or read_latest_upload_result() or {}
    replay = result.get("replay_timeline") or (result.get("sii_intelligence") or {}).get("replay_timeline") or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    return {
        "job_id": result.get("job_id") or job_id,
        "source": "persisted" if timeline else "empty",
        "meta": replay.get("meta", {}) if isinstance(replay, dict) else {},
        "timeline": timeline or [],
        "frames": timeline or [],
        "frame_count": len(timeline or []),
        "replay_ready": len(timeline or []) > 0,
    }


def _detect_timestamp_column(columns: list[str]) -> str | None:
    hints = ("timestamp", "time", "datetime", "date_time", "logged_at", "recorded_at")
    lowered = {c.lower().strip(): c for c in columns}
    for hint in hints:
        for key, original in lowered.items():
            if hint == key or hint in key:
                return original
    return columns[0] if columns else None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text == "":
        return None
    low = text.lower()
    if low in {"true", "yes", "on"}:
        return 1.0
    if low in {"false", "no", "off"}:
        return 0.0
    try:
        value = float(text)
        if math.isfinite(value):
            return value
    except ValueError:
        return None
    return None


def _population_std(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _detect_numeric_columns(rows: list[dict[str, Any]], columns: list[str], exclude: set[str | None]) -> list[str]:
    event_words = ("event", "status", "fault", "alarm", "override")
    numeric = []
    sample = rows[: min(len(rows), 1000)]
    for col in columns:
        if col in exclude:
            continue
        vals = [_to_float(row.get(col)) for row in sample]
        count = sum(v is not None for v in vals)
        if count >= max(3, int(len(sample) * 0.15)):
            numeric.append(col)
    continuous = [c for c in numeric if not any(w in c.lower() for w in event_words)]
    return continuous if len(continuous) >= 3 else numeric



def _parse_ts(value: Any, fallback_index: int) -> str:
    text = str(value or "").strip()
    if text:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback_index, tz=timezone.utc).isoformat()


def _build_replay(
    rows: list[dict[str, Any]],
    timestamp_column: str,
    numeric_columns: list[str],
    job_id: str,
    relationship_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    frame_target = min(120, max(20, len(rows)))
    positions = sorted(set(round(i * (len(rows) - 1) / max(frame_target - 1, 1)) for i in range(frame_target)))
    baseline_rows = rows[: max(5, min(100, len(rows) // 10))]
    baseline = {}
    for col in numeric_columns:
        vals = [_to_float(r.get(col)) for r in baseline_rows]
        vals = [v for v in vals if v is not None]
        baseline[col] = sum(vals) / len(vals) if vals else 0.0

    timeline = []
    prev_drift = 0.0
    for idx, pos in enumerate(positions):
        row = rows[pos]
        shifts = []
        for col in numeric_columns:
            val = _to_float(row.get(col))
            base = baseline.get(col, 0.0)
            if val is None:
                continue
            denom = abs(base) if abs(base) > 1e-6 else 1.0
            shifts.append((col, abs(val - base) / denom))
        shifts.sort(key=lambda x: x[1], reverse=True)
        drift = sum(v for _, v in shifts[:5]) / max(1, min(5, len(shifts)))
        velocity = drift - prev_drift
        prev_drift = drift
        top = [c for c, _ in shifts[:3]]
        ts = _parse_ts(row.get(timestamp_column), pos)
        phase = "stable_topology" if drift < 0.1 else "relationship_weakening" if drift < 0.25 else "propagation_activation"
        timeline.append({
            "timestamp": ts,
            "frame_index": idx,
            "row_start": max(1, pos),
            "row_end": pos + 1,
            "timestamp_start": ts,
            "timestamp_end": ts,
            "total_frames": len(positions),
            "affected_subsystem": "Uploaded telemetry",
            "affected_area": "Uploaded telemetry",
            "primary_contributors": top,
            "topology_state": {"phase": phase, "drift_index": round(drift, 6), "stability_state": "Monitoring"},
            "cognition_state": {"facility_state": "Monitoring", "canonical_phase": phase, "confidence_tier": "BASELINE_EVIDENCE"},
            "propagation_state": {"dominant_paths": top, "activation_intensity": round(min(1, drift), 6)},
            "evidence_state": {"corroboration_strength": "MODERATE"},
            "drift_velocity": round(velocity, 6),
            "operator_summary": f"Replay frame {idx + 1} of {len(positions)}.",
        })
    top_relationship_changes = (relationship_model or {}).get("top_relationship_changes")
    if timeline and isinstance(top_relationship_changes, list) and top_relationship_changes:
        timeline[-1]["relationship_changes"] = [item.get("summary", "") for item in top_relationship_changes if isinstance(item, dict)]
        timeline[-1]["relationship_change_evidence_refs"] = top_relationship_changes
    return {"meta": {"frame_count": len(timeline), "total_rows": len(rows), "job_id": job_id}, "timeline": timeline}


def _minimal_replay(columns, rows, timestamp_column, numeric_columns, job_id, relationship_model: dict[str, Any] | None = None):
    if not rows:
        return {"meta": {"frame_count": 0}, "timeline": []}
    return _build_replay(rows, timestamp_column or columns[0], numeric_columns or columns[1:4], job_id, relationship_model)


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
    replay = (
        result.get("replay_timeline")
        or (result.get("sii_intelligence") or {}).get("replay_timeline")
        or {}
    )
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    return {
        "job_id": result.get("job_id"),
        "status": "COMPLETE",
        "processing_state": "complete",
        "percent": 100,
        "progress": 100,
        "filename": result.get("filename"),
        "row_count": result.get("row_count", 0),
        "column_count": result.get("column_count", 0),
        "result_available": True,
        "sii_completed": True,
        "replay_ready": len(timeline or []) > 0,
        "replay_frame_count": len(timeline or []),
        "latest_replay_frames": len(timeline or []),
        "replay_source": "persisted" if timeline else "unknown",
        "last_processed_at": result.get("last_processed_at") or result.get("completed_at"),
    }


def write_latest_upload_result(*args) -> None:
    clear_reset_block_persisted()
    if len(args) == 2:
        job_id, result = args
        payload = dict(result or {})
        payload["job_id"] = str(job_id)
        _write_json(f"upload_result_{job_id}.json", payload)
        _write_json("latest_upload_result.json", payload)
        _write_shared_state(f"upload_result_{job_id}", payload)
        _write_shared_state("latest_upload_result", payload)
        LATEST_UPLOAD_CACHE["result"] = payload
        return
    result = args[0] if args else {}
    _write_json("latest_upload_result.json", result)
    _write_shared_state("latest_upload_result", result)
    LATEST_UPLOAD_CACHE["result"] = result


def write_latest_upload_summary(*args, **kwargs) -> None:
    clear_reset_block_persisted()
    if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], dict):
        job_id = args[0]
        summary = args[1]
        payload = dict(summary or {})
        payload["job_id"] = str(job_id)
        payload.setdefault("status", "COMPLETE")
        if "status_url" not in payload:
            payload["status_url"] = f"/api/data/upload-status/{job_id}"
        _write_json("latest_upload_summary.json", payload)
        _write_shared_state("latest_upload_summary", payload)
        _write_shared_state(f"upload_status_{job_id}", payload)
        LATEST_UPLOAD_CACHE["summary"] = payload
        return
    if len(args) >= 1 and isinstance(args[0], dict):
        summary = args[0]
        _write_json("latest_upload_summary.json", summary)
        _write_shared_state("latest_upload_summary", summary)
        LATEST_UPLOAD_CACHE["summary"] = summary
        return
    if len(args) == 2:
        job_id, summary = args
        payload = dict(summary or {})
        payload["job_id"] = str(job_id)
        payload.setdefault("status", "COMPLETE")
        if "status_url" not in payload:
            payload["status_url"] = f"/api/data/upload-status/{job_id}"
        _write_json("latest_upload_summary.json", payload)
        _write_shared_state("latest_upload_summary", payload)
        _write_shared_state(f"upload_status_{job_id}", payload)
        LATEST_UPLOAD_CACHE["summary"] = payload
        return
    summary = args[0] if args else {}
    _write_json("latest_upload_summary.json", summary)
    _write_shared_state("latest_upload_summary", summary)
    LATEST_UPLOAD_CACHE["summary"] = summary


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
    result = read_upload_result_by_job_id(summary["job_id"]) or read_latest_upload_result() or {}
    return result


def read_upload_history(limit: int = 100) -> list[dict[str, Any]]:
    """
    Compatibility helper for observability.
    V2 stores latest upload plus per-job upload_result_*.json files.
    """
    items: list[dict[str, Any]] = []
    try:
        paths = sorted(
            RUNTIME_DIR.glob("upload_result_*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        paths = []

    for path in paths[: max(0, int(limit or 100))]:
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        replay = (
            result.get("replay_timeline")
            or (result.get("sii_intelligence") or {}).get("replay_timeline")
            or {}
        )
        timeline = replay.get("timeline") if isinstance(replay, dict) else []

        items.append({
            "job_id": result.get("job_id"),
            "filename": result.get("filename"),
            "status": "COMPLETE",
            "row_count": result.get("row_count", 0),
            "column_count": result.get("column_count", 0),
            "replay_ready": len(timeline or []) > 0,
            "replay_frame_count": len(timeline or []),
            "intelligence_metrics": {
                "room_count": 1,
                "flagged_room_count": 0,
                "sparse_room_count": 0,
                "unknown_profile": False,
            },
            "completed_at": result.get("completed_at") or result.get("last_processed_at"),
        })

    latest = read_latest_upload_result()
    if latest and not any(item.get("job_id") == latest.get("job_id") for item in items):
        items.insert(0, {
            "job_id": latest.get("job_id"),
            "filename": latest.get("filename"),
            "status": "COMPLETE",
            "row_count": latest.get("row_count", 0),
            "column_count": latest.get("column_count", 0),
            "replay_ready": bool((latest.get("replay_timeline") or {}).get("timeline")),
            "replay_frame_count": len((latest.get("replay_timeline") or {}).get("timeline", [])),
            "intelligence_metrics": {
                "room_count": 1,
                "flagged_room_count": 0,
                "sparse_room_count": 0,
                "unknown_profile": False,
            },
            "completed_at": latest.get("completed_at") or latest.get("last_processed_at"),
        })

    return items[: max(0, int(limit or 100))]


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
    return read_upload_result_by_job_id(summary["job_id"]) or read_latest_upload_result() or {}


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

        return read_upload_result_by_job_id(summary["job_id"]) or read_latest_upload_result() or {}

    except Exception as exc:
        logger.exception("CSV upload processing failed job_id=%s filename=%s", job_id, filename)

        if snapshot:
            summary = _complete_with_partial_result(
                job_id=job_id,
                filename=filename,
                error=exc,
                snapshot=snapshot,
            )
            return read_upload_result_by_job_id(summary["job_id"]) or read_latest_upload_result() or {}

        raise

def process_json_payload(payload: Any, filename: str = "upload.json", **kwargs) -> dict[str, Any]:
    if isinstance(payload, bytes):
        payload = json.loads(payload.decode("utf-8"))
    if isinstance(payload, str):
        payload = json.loads(payload)

    if isinstance(payload, dict) and isinstance(payload.get("readings"), list):
        grouped: dict[str, dict[str, Any]] = {}
        for reading in payload.get("readings", []):
            if not isinstance(reading, dict):
                continue
            ts = str(reading.get("timestamp") or payload.get("timestamp") or "")
            record = grouped.setdefault(ts, {"timestamp": ts})
            sensor_name = str(reading.get("sensor_name") or reading.get("sensor_id") or "value")
            record[sensor_name] = reading.get("value")
        rows = list(grouped.values())
    else:
        rows = payload if isinstance(payload, list) else payload.get("rows") or payload.get("data") or []
        if not rows:
            rows = [payload if isinstance(payload, dict) else {"value": payload}]

    columns = sorted({key for row in rows if isinstance(row, dict) for key in row.keys()})
    if not columns:
        columns = ["timestamp", "value"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        if isinstance(row, dict):
            writer.writerow([row.get(col, "") for col in columns])
        else:
            writer.writerow(["", row])

    return process_csv_content(output.getvalue(), filename=filename, **kwargs)
