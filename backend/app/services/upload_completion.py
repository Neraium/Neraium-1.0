from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.services.upload_state import build_session_scope
from app.services.analysis_result_contract import empty_analysis_result


def build_partial_upload_artifacts(
    *,
    job_id: str,
    filename: str,
    error: Exception,
    snapshot: dict[str, Any] | None = None,
    build_traceability_packet: Callable[..., dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
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
        "run_id": job_id,
        "upload_id": job_id,
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

    result["analysis_result"] = empty_analysis_result(
        analysis_id=job_id,
        upload_id=job_id,
        source_file=filename,
        status="failed",
        message="Upload completed, but full intelligence processing could not finish.",
        errors=[error_message],
    )
    result["session_scope"] = build_session_scope(job_id, filename=filename, status="partial_complete")
    result["traceability"] = build_traceability_packet(job_id=job_id, filename=filename, result=result)
    result["decision_integrity"] = dict(result["traceability"])
    summary["session_scope"] = build_session_scope(job_id, filename=filename, status="active")
    summary["traceability"] = dict(result["traceability"])
    summary["decision_integrity"] = dict(result["traceability"])
    return result, summary
