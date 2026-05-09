from __future__ import annotations

import json
import logging
import csv
import time
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.engine import run_engine_analysis
from app.services.baseline_analysis import build_baseline_analysis
from app.services.csv_parser import parse_csv_content, preview_rows
from app.services.cultivation_mapping import map_cultivation_columns
from app.services.data_quality import (
    build_data_quality,
    build_warnings,
    detect_timestamp_column,
    profile_numeric_columns,
    profile_timestamps,
)
from app.services.driver_attribution import build_driver_attribution
from app.services.engine_identity import VALIDATION_PROVENANCE, build_processing_trace
from app.services.operator_report import build_operator_report
from app.services.sii_intelligence import build_upload_intelligence
from app.services.sii_runner import CORE_ENGINE, RUNNER_MODULE, run_sii_runner


RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
JOB_DIR = RUNTIME_DIR / "upload_jobs"
LEGACY_JOB_DIR = RUNTIME_DIR / "jobs"
CHUNK_SIZE_ROWS = 10_000
MAX_ANALYSIS_ROWS = 50_000
MAX_SII_ROWS = 20_000

logger = logging.getLogger(__name__)

PROGRESS_LABELS = {
    "PENDING": "Telemetry batch received. Processing is queued.",
    "PARSING": "Reading CSV headers, rows, and timestamp context.",
    "BASELINE_MODELING": "Building baseline model from telemetry windows.",
    "RUNNING_SII": "Running SII engine against uploaded telemetry.",
    "GENERATING_EVIDENCE": "Generating evidence and writing facility state.",
    "COMPLETE": "Telemetry processing complete.",
    "FAILED": "Telemetry processing failed.",
}


def ensure_runtime_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    JOB_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def create_upload_job(file: UploadFile) -> dict[str, Any]:
    ensure_runtime_dirs()
    job_id = uuid.uuid4().hex
    filename = Path(file.filename or "telemetry.csv").name
    upload_path = UPLOAD_DIR / f"{job_id}.csv"
    size_bytes = 0
    with upload_path.open("wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            output.write(chunk)

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
        "runner_used": False,
        "runner_module": RUNNER_MODULE,
        "core_engine": CORE_ENGINE,
        "started_at": now_iso(),
        "completed_at": None,
        "error": None,
        "result_summary": None,
    }
    write_job(metadata)
    return metadata


def job_path(job_id: str) -> Path:
    safe_job_id = "".join(character for character in job_id if character.isalnum() or character in {"-", "_"})
    return JOB_DIR / f"{safe_job_id}.json"


def read_job(job_id: str) -> dict[str, Any] | None:
    ensure_runtime_dirs()
    path = job_path(job_id)
    if not path.exists():
        legacy_path = LEGACY_JOB_DIR / path.name
        path = legacy_path if legacy_path.exists() else path
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_job(metadata: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    if "status" in metadata:
        metadata["status"] = normalize_status(str(metadata["status"]))
        metadata["progress_label"] = PROGRESS_LABELS.get(metadata["status"], metadata.get("progress_label"))
    path = job_path(metadata["job_id"])
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    temp_path.replace(path)


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
        "parsing": "PARSING",
        "baseline_modeling": "BASELINE_MODELING",
        "running_sii": "RUNNING_SII",
        "writing_state": "GENERATING_EVIDENCE",
        "generating_evidence": "GENERATING_EVIDENCE",
        "complete": "COMPLETE",
        "failed": "FAILED",
    }
    return aliases.get(status.lower(), status.upper())


def process_upload_job(job_id: str) -> None:
    metadata = read_job(job_id)
    if metadata is None:
        return

    started = time.perf_counter()
    try:
        logger.info(
            "upload_job_started job_id=%s filename=%s size_bytes=%s",
            job_id,
            metadata.get("filename"),
            metadata.get("file_size_bytes"),
        )
        update_job(job_id, status="PARSING")
        result = process_csv_file(
            file_path=Path(metadata["file_path"]),
            filename=metadata["filename"],
            status_callback=lambda status, **updates: update_job(job_id, status=status, **updates),
        )
        update_job(
            job_id,
            status="GENERATING_EVIDENCE",
            rows_processed=result["row_count"],
            columns_detected=result["column_count"],
            runner_used=result["sii_runner_result"]["runner_used"],
            chunk_count=result["processing_stats"]["chunk_count"],
            memory_estimate_bytes=result["processing_stats"]["memory_estimate_bytes"],
            engine_runtime_seconds=result["processing_stats"]["engine_runtime_seconds"],
        )
        completed_at = now_iso()
        summary = summarize_result(result, completed_at)
        duration = round(time.perf_counter() - started, 4)
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
            result_summary=summary,
        )
        write_latest_upload_summary(job_id, summary)
        logger.info(
            "upload_job_complete job_id=%s rows=%s columns=%s chunks=%s duration=%s engine_runtime=%s memory_estimate=%s",
            job_id,
            result["row_count"],
            result["column_count"],
            result["processing_stats"]["chunk_count"],
            duration,
            result["processing_stats"]["engine_runtime_seconds"],
            result["processing_stats"]["memory_estimate_bytes"],
        )
    except Exception as exc:
        logger.exception("upload_job_failed job_id=%s", job_id)
        update_job(
            job_id,
            status="FAILED",
            completed_at=now_iso(),
            processing_duration_seconds=round(time.perf_counter() - started, 4),
            error=f"{type(exc).__name__}: {exc}",
        )


def process_csv_content(
    *,
    content: bytes,
    filename: str,
    status_callback: Any | None = None,
) -> dict[str, Any]:
    columns, data_rows = parse_csv_content(content)
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
        },
    )


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
    )


def stream_csv_windows(
    file_path: Path,
    status_callback: Any | None = None,
) -> tuple[list[str], list[list[str]], int, dict[str, Any]]:
    first_rows: list[list[str]] = []
    tail_rows: deque[list[str]] = deque(maxlen=MAX_ANALYSIS_ROWS // 2)
    total_rows = 0
    malformed_rows = 0
    chunk_count = 0
    columns: list[str] | None = None

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

        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            total_rows += 1
            if len(row) != len(columns):
                malformed_rows += 1
            if len(first_rows) < MAX_ANALYSIS_ROWS // 2:
                first_rows.append(row)
            else:
                tail_rows.append(row)
            if total_rows % CHUNK_SIZE_ROWS == 0:
                chunk_count += 1
                if status_callback:
                    status_callback(
                        "PARSING",
                        rows_processed=total_rows,
                        columns_detected=len(columns),
                        chunk_count=chunk_count,
                        memory_estimate_bytes=estimate_rows_memory(first_rows) + estimate_rows_memory(list(tail_rows)),
                    )

    if total_rows == 0:
        raise ValueError("CSV file is empty.")

    if total_rows % CHUNK_SIZE_ROWS:
        chunk_count += 1

    data_rows = first_rows + list(tail_rows)
    if status_callback:
        status_callback(
            "PARSING",
            rows_processed=total_rows,
            columns_detected=len(columns),
            chunk_count=chunk_count,
            memory_estimate_bytes=estimate_rows_memory(data_rows),
        )

    return columns, data_rows, total_rows, {
        "chunk_count": chunk_count,
        "sampled_rows": len(data_rows),
        "sii_sampled_rows": min(len(data_rows), MAX_SII_ROWS),
        "malformed_rows": malformed_rows,
        "memory_estimate_bytes": estimate_rows_memory(data_rows),
        "used_streaming": True,
        "engine_runtime_seconds": 0,
    }


def build_upload_result(
    *,
    columns: list[str],
    data_rows: list[list[str]],
    total_rows: int,
    filename: str,
    status_callback: Any | None = None,
    processing_stats: dict[str, Any],
) -> dict[str, Any]:
    if status_callback:
        status_callback("PARSING", rows_processed=total_rows, columns_detected=len(columns))
    warnings = build_warnings(columns, data_rows)
    if processing_stats.get("used_streaming") and processing_stats.get("sampled_rows", 0) < total_rows:
        warnings.append(
            f"Large upload was processed with streaming windows: {processing_stats['sampled_rows']} representative rows modeled from {total_rows} total rows."
        )
    if processing_stats.get("malformed_rows"):
        warnings.append(f"{processing_stats['malformed_rows']} rows had a different column count than the header.")
    detected_timestamp_column = detect_timestamp_column(columns)
    if detected_timestamp_column is None:
        warnings.append("No obvious timestamp column detected.")

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
    if status_callback:
        status_callback("BASELINE_MODELING", rows_processed=total_rows, columns_detected=len(columns))
    baseline_analysis = build_baseline_analysis(columns, data_rows, numeric_profiles)
    cultivation_mapping = map_cultivation_columns(columns)
    operator_report = build_operator_report(
        data_quality=data_quality,
        timestamp_profile=timestamp_profile,
        numeric_profiles=numeric_profiles,
        baseline_analysis=baseline_analysis,
        cultivation_mapping=cultivation_mapping,
    )
    if status_callback:
        status_callback("RUNNING_SII", rows_processed=total_rows, columns_detected=len(columns))
    engine_started = time.perf_counter()
    engine_result = run_engine_analysis(
        columns=columns,
        rows=data_rows,
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        cultivation_mapping=cultivation_mapping,
        numeric_profiles=numeric_profiles,
    )
    processing_stats["engine_runtime_seconds"] = round(time.perf_counter() - engine_started, 4)
    driver_attribution = build_driver_attribution(
        room_state={
            "room": primary_room_from_upload(columns, data_rows),
            "state": state_from_assessment(baseline_analysis["overall_assessment"]),
            "severity": severity_from_assessment(baseline_analysis["overall_assessment"]),
        },
        telemetry_context={
            "columns": columns,
            "rows": data_rows,
            "numeric_profiles": numeric_profiles,
            "timestamp_profile": timestamp_profile,
            "data_quality": data_quality,
            "cultivation_mapping": cultivation_mapping,
        },
        baseline_context={
            "baseline_analysis": baseline_analysis,
            "cultivation_mapping": cultivation_mapping,
        },
        engine_result=engine_result,
    )
    sii_intelligence = build_upload_intelligence(
        filename=filename,
        row_count=total_rows,
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
        operator_report=operator_report,
        timestamp_profile=timestamp_profile,
    )
    processing_trace = build_processing_trace(
        engine_result=engine_result,
        driver_attribution=driver_attribution,
        rows_processed=total_rows,
        columns_analyzed=baseline_analysis["columns_analyzed"],
    )
    sii_rows = downsample_rows(data_rows, MAX_SII_ROWS)
    sii_runner_result = run_sii_runner(
        columns=columns,
        rows=sii_rows,
        numeric_profiles=numeric_profiles,
        timestamp_column=detected_timestamp_column,
        primary_room=primary_room_from_upload(columns, data_rows),
        driver_attribution=driver_attribution,
        engine_result=engine_result,
        processing_trace=processing_trace,
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
        "cultivation_mapping": cultivation_mapping,
        "operator_report": operator_report,
        "engine_result": truncate_engine_result(engine_result),
        "driver_attribution": driver_attribution,
        "sii_intelligence": sii_intelligence,
        "sii_runner_result": truncate_runner_result(sii_runner_result),
        "processing_trace": processing_trace,
        "processing_stats": processing_stats,
        "validation_provenance": VALIDATION_PROVENANCE,
    }


def summarize_result(result: dict[str, Any], completed_at: str) -> dict[str, Any]:
    runner = result["sii_runner_result"]
    stats = result.get("processing_stats", {})
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
        "warnings": result["warnings"][:10],
        "runner_errors": runner.get("errors", [])[:5],
    }


def latest_upload_path() -> Path:
    return RUNTIME_DIR / "latest_upload.json"


def write_latest_upload_summary(job_id: str, summary: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    path = latest_upload_path()
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps({"job_id": job_id, **summary}, indent=2), encoding="utf-8")
    temp_path.replace(path)


def read_latest_upload_summary() -> dict[str, Any] | None:
    ensure_runtime_dirs()
    path = latest_upload_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def latest_completed_job_summary() -> dict[str, Any] | None:
    latest = read_latest_upload_summary()
    if latest:
        return latest
    completed_jobs: list[dict[str, Any]] = []
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
    return latest_job.get("result_summary")


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


def primary_room_from_upload(columns: list[str], rows: list[list[str]]) -> str:
    room_columns = [
        index
        for index, column in enumerate(columns)
        if any(token in column.lower() for token in ("room", "zone", "bay"))
    ]
    if not room_columns:
        return "Current room"
    room_index = room_columns[0]
    for row in rows:
        if room_index < len(row) and row[room_index].strip():
            return row[room_index].strip()
    return "Current room"


def state_from_assessment(assessment: str) -> str:
    return "Needs review" if assessment == "needs_review" else "Monitoring"


def severity_from_assessment(assessment: str) -> str:
    return "review" if assessment == "needs_review" else "info"


def downsample_rows(rows: list[list[str]], limit: int) -> list[list[str]]:
    if len(rows) <= limit:
        return rows
    step = len(rows) / limit
    return [rows[min(len(rows) - 1, int(index * step))] for index in range(limit)]


def estimate_rows_memory(rows: list[list[str]]) -> int:
    return sum(sum(len(cell) for cell in row) + len(row) * 8 for row in rows)
