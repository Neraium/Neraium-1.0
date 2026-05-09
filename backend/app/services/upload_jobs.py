from __future__ import annotations

import json
import uuid
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
JOB_DIR = RUNTIME_DIR / "jobs"

PROGRESS_LABELS = {
    "queued": "Telemetry batch received. Processing is queued.",
    "parsing": "Reading CSV headers, rows, and timestamp context.",
    "running_sii": "Running SII engine against uploaded telemetry.",
    "writing_state": "Writing SII evidence and facility state.",
    "complete": "Telemetry processing complete.",
    "failed": "Telemetry processing failed.",
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
        "status": "queued",
        "progress_label": PROGRESS_LABELS["queued"],
        "rows_processed": 0,
        "columns_detected": 0,
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
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_job(metadata: dict[str, Any]) -> None:
    ensure_runtime_dirs()
    job_path(metadata["job_id"]).write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def update_job(job_id: str, **updates: Any) -> dict[str, Any]:
    metadata = read_job(job_id)
    if metadata is None:
        metadata = {"job_id": job_id, "started_at": now_iso()}
    metadata.update(updates)
    if "status" in updates:
        metadata["progress_label"] = PROGRESS_LABELS.get(str(updates["status"]), metadata.get("progress_label"))
    write_job(metadata)
    return metadata


def process_upload_job(job_id: str) -> None:
    metadata = read_job(job_id)
    if metadata is None:
        return

    try:
        update_job(job_id, status="parsing")
        content = Path(metadata["file_path"]).read_bytes()
        result = process_csv_content(
            content=content,
            filename=metadata["filename"],
            status_callback=lambda status, **updates: update_job(job_id, status=status, **updates),
        )
        update_job(
            job_id,
            status="writing_state",
            rows_processed=result["row_count"],
            columns_detected=result["column_count"],
            runner_used=result["sii_runner_result"]["runner_used"],
        )
        completed_at = now_iso()
        summary = summarize_result(result, completed_at)
        update_job(
            job_id,
            status="complete",
            rows_processed=result["row_count"],
            columns_detected=result["column_count"],
            runner_used=result["sii_runner_result"]["runner_used"],
            runner_module=result["sii_runner_result"]["runner_module"],
            core_engine=result["sii_runner_result"]["core_engine"],
            completed_at=completed_at,
            error=None,
            result_summary=summary,
        )
        write_latest_upload_summary(job_id, summary)
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            completed_at=now_iso(),
            error=f"{type(exc).__name__}: {exc}",
        )


def process_csv_content(
    *,
    content: bytes,
    filename: str,
    status_callback: Any | None = None,
) -> dict[str, Any]:
    columns, data_rows = parse_csv_content(content)
    if status_callback:
        status_callback("parsing", rows_processed=len(data_rows), columns_detected=len(columns))
    warnings = build_warnings(columns, data_rows)
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
        row_count=len(data_rows),
        column_count=len(columns),
        numeric_column_count=len(numeric_profiles),
        timestamp_detected=detected_timestamp_column is not None,
        warnings=warnings,
    )
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
        status_callback("running_sii", rows_processed=len(data_rows), columns_detected=len(columns))
    engine_result = run_engine_analysis(
        columns=columns,
        rows=data_rows,
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        cultivation_mapping=cultivation_mapping,
        numeric_profiles=numeric_profiles,
    )
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
        row_count=len(data_rows),
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
        rows_processed=len(data_rows),
        columns_analyzed=baseline_analysis["columns_analyzed"],
    )
    sii_runner_result = run_sii_runner(
        columns=columns,
        rows=data_rows,
        numeric_profiles=numeric_profiles,
        timestamp_column=detected_timestamp_column,
        primary_room=primary_room_from_upload(columns, data_rows),
        driver_attribution=driver_attribution,
        engine_result=engine_result,
        processing_trace=processing_trace,
    )

    return {
        "filename": filename,
        "row_count": len(data_rows),
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
        "validation_provenance": VALIDATION_PROVENANCE,
    }


def summarize_result(result: dict[str, Any], completed_at: str) -> dict[str, Any]:
    runner = result["sii_runner_result"]
    return {
        "filename": result["filename"],
        "rows_processed": result["row_count"],
        "columns_detected": result["column_count"],
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
    latest_upload_path().write_text(
        json.dumps({"job_id": job_id, **summary}, indent=2),
        encoding="utf-8",
    )


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
        if metadata.get("status") == "complete":
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
