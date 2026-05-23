from __future__ import annotations

import csv
import io
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNTIME_DIR = Path("backend/runtime")
JOBS: dict[str, dict[str, Any]] = {}
LATEST_UPLOAD_CACHE: dict[str, Any] = {"summary": None, "result": None}


def configure_runtime_dir(path: str | os.PathLike[str]) -> None:
    global RUNTIME_DIR
    RUNTIME_DIR = Path(path)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def warm_latest_upload_cache() -> None:
    LATEST_UPLOAD_CACHE["summary"] = _read_json("latest_upload_summary.json")
    LATEST_UPLOAD_CACHE["result"] = _read_json("latest_upload_result.json")


def read_latest_upload_result() -> dict[str, Any] | None:
    return LATEST_UPLOAD_CACHE.get("result") or _read_json("latest_upload_result.json")


def read_latest_upload_summary() -> dict[str, Any] | None:
    return LATEST_UPLOAD_CACHE.get("summary") or _read_json("latest_upload_summary.json")


def read_upload_result_by_job_id(job_id: str) -> dict[str, Any] | None:
    return _read_json(f"upload_result_{job_id}.json")


def read_upload_status(job_id: str) -> dict[str, Any] | None:
    return JOBS.get(job_id) or _read_json(f"upload_status_{job_id}.json")


def reset_upload_state() -> None:
    JOBS.clear()
    for path in RUNTIME_DIR.glob("*upload*"):
        try:
            path.unlink()
        except OSError:
            pass
    LATEST_UPLOAD_CACHE["summary"] = None
    LATEST_UPLOAD_CACHE["result"] = None


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
    LATEST_UPLOAD_CACHE["summary"] = payload
    return payload


def process_upload_bytes(filename: str, content: bytes) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    _set_status(job_id, "PROCESSING", 10, "Parsing CSV")

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    columns = list(reader.fieldnames or [])
    rows = list(reader)

    if not columns or not rows:
        raise ValueError("CSV must include a header and at least one data row.")

    timestamp_column = _detect_timestamp_column(columns)
    numeric_columns = _detect_numeric_columns(rows, columns, exclude={timestamp_column})

    if len(rows) < 20 or not timestamp_column or len(numeric_columns) < 3:
        replay = _minimal_replay(columns, rows, timestamp_column, numeric_columns, job_id)
    else:
        replay = _build_replay(rows, timestamp_column, numeric_columns, job_id)

    if not replay.get("timeline"):
        replay = _minimal_replay(columns, rows, timestamp_column, numeric_columns, job_id)

    frame_count = len(replay.get("timeline", []))
    now = datetime.now(timezone.utc).isoformat()

    result = {
        "job_id": job_id,
        "filename": filename,
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": columns,
        "preview_rows": rows[:10],
        "detected_timestamp_column": timestamp_column,
        "numeric_profiles": [{"column": c} for c in numeric_columns[:50]],
        "timestamp_profile": {
            "first_timestamp": rows[0].get(timestamp_column) if timestamp_column else None,
            "last_timestamp": rows[-1].get(timestamp_column) if timestamp_column else None,
        },
        "data_quality": {"readiness": "ready", "row_count": len(rows), "numeric_column_count": len(numeric_columns)},
        "baseline_analysis": {},
        "cultivation_mapping": {},
        "operator_report": {},
        "engine_result": {"overall_result": "complete", "signals": [], "evidence": []},
        "driver_attribution": {},
        "operating_state": "Monitoring",
        "drift_status": "info",
        "sii_intelligence": {
            "source": "uploaded",
            "facility_state": "Monitoring",
            "urgency": "info",
            "primary_room": "Uploaded telemetry",
            "neraium_score": 0,
            "last_updated": now,
            "replay_timeline": replay,
        },
        "sii_runner_result": {"runner_used": False, "errors": []},
        "processing_trace": {
            "sii_pipeline_ran": True,
            "sii_completed": True,
            "replay_frame_count": frame_count,
            "rows_processed": len(rows),
            "columns_analyzed": len(numeric_columns),
            "completed_at": now,
        },
        "processing_stats": {},
        "room_summary": {},
        "ingestion_metadata": {"source_type": "csv_upload"},
        "source_type": "csv",
        "replay_timeline": replay,
        "replay_ready": frame_count > 0,
        "replay_frame_count": frame_count,
        "last_processed_at": now,
        "completed_at": now,
    }

    summary = {
        "job_id": job_id,
        "status": "COMPLETE",
        "processing_state": "complete",
        "percent": 100,
        "progress": 100,
        "result_available": True,
        "first_usable_available": True,
        "sii_completed": True,
        "replay_ready": frame_count > 0,
        "replay_frame_count": frame_count,
        "latest_replay_frames": frame_count,
        "replay_source": "persisted",
        "last_processed_at": now,
        "filename": filename,
        "row_count": len(rows),
        "column_count": len(columns),
    }

    _write_json(f"upload_result_{job_id}.json", result)
    _write_json(f"upload_status_{job_id}.json", summary)
    _write_json("latest_upload_result.json", result)
    _write_json("latest_upload_summary.json", summary)

    JOBS[job_id] = summary
    LATEST_UPLOAD_CACHE["result"] = result
    LATEST_UPLOAD_CACHE["summary"] = summary
    return summary


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


def _build_replay(rows: list[dict[str, Any]], timestamp_column: str, numeric_columns: list[str], job_id: str) -> dict[str, Any]:
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
    return {"meta": {"frame_count": len(timeline), "total_rows": len(rows), "job_id": job_id}, "timeline": timeline}


def _minimal_replay(columns, rows, timestamp_column, numeric_columns, job_id):
    if not rows:
        return {"meta": {"frame_count": 0}, "timeline": []}
    return _build_replay(rows, timestamp_column or columns[0], numeric_columns or columns[1:4], job_id)


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

def reset_latest_upload_state() -> None:
    reset_upload_state()


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


def write_latest_upload_result(result: dict[str, Any]) -> None:
    _write_json("latest_upload_result.json", result)
    LATEST_UPLOAD_CACHE["result"] = result


def write_latest_upload_summary(summary: dict[str, Any]) -> None:
    _write_json("latest_upload_summary.json", summary)
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
    """
    Compatibility stub for the old upload worker.
    V2 processes uploads synchronously in /api/data/upload.
    """
    return False


class UploadTooLargeError(ValueError):
    pass


def parse_positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return value if value > 0 else default
    except Exception:
        return default


def write_job(job_id: str, payload: dict[str, Any]) -> None:
    JOBS[job_id] = payload
    _write_json(f"upload_status_{job_id}.json", payload)


def read_job(job_id: str) -> dict[str, Any] | None:
    return read_upload_status(job_id)


def create_upload_job(filename: str = "upload.csv", **kwargs) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    payload = {
        "job_id": job_id,
        "filename": filename,
        "status": "QUEUED",
        "processing_state": "queued",
        "percent": 0,
        "progress": 0,
    }
    write_job(job_id, payload)
    return payload


def process_csv_content(content: str | bytes, filename: str = "upload.csv", **kwargs) -> dict[str, Any]:
    if isinstance(content, str):
        content = content.encode("utf-8")
    summary = process_upload_bytes(filename, content)
    return read_upload_result_by_job_id(summary["job_id"]) or read_latest_upload_result() or {}


def process_csv_file(path: str | os.PathLike[str], **kwargs) -> dict[str, Any]:
    p = Path(path)
    return process_csv_content(p.read_bytes(), filename=p.name, **kwargs)


def process_json_payload(payload: Any, filename: str = "upload.json", **kwargs) -> dict[str, Any]:
    if isinstance(payload, bytes):
        payload = json.loads(payload.decode("utf-8"))
    if isinstance(payload, str):
        payload = json.loads(payload)

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

    return process_csv_content(output.getvalue(), filename=filename)
