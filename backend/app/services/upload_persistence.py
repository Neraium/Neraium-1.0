from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from app.services.dataset_scope import payload_matches_dataset_scope
from app.services.upload_state import build_session_scope


def summarize_result(result: dict[str, Any], *, build_scope: Callable[..., dict[str, Any]] = build_session_scope) -> dict[str, Any]:
    replay = (
        result.get("replay_timeline")
        or (result.get("sii_intelligence") or {}).get("replay_timeline")
        or {}
    )
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    return {
        "job_id": result.get("job_id"),
        "run_id": result.get("run_id") or result.get("job_id"),
        "upload_id": result.get("upload_id") or result.get("job_id"),
        "status": "COMPLETE",
        "processing_state": "complete",
        "percent": 100,
        "progress": 100,
        "filename": result.get("filename"),
        "row_count": result.get("row_count", 0),
        "column_count": result.get("column_count", 0),
        "result_available": True,
        "sii_completed": True,
        "sii_completion_artifacts": result.get("sii_completion_artifacts", {}),
        "evidence_persisted": bool((result.get("evidence_persistence") or {}).get("persisted")),
        "replay_ready": len(timeline or []) > 0,
        "replay_frame_count": len(timeline or []),
        "latest_replay_frames": len(timeline or []),
        "replay_source": "persisted" if timeline else "unknown",
        "last_processed_at": result.get("last_processed_at") or result.get("completed_at"),
        "session_scope": result.get("session_scope") if isinstance(result.get("session_scope"), dict) else build_scope(result.get("job_id"), filename=result.get("filename"), status="active"),
        "traceability": result.get("traceability") if isinstance(result.get("traceability"), dict) else {},
    }


def read_upload_history(
    runtime_dir: Path,
    *,
    limit: int = 100,
    current_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        paths = sorted(
            runtime_dir.glob("upload_result_*.json"),
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
        if not payload_matches_dataset_scope(result):
            continue

        replay = (
            result.get("replay_timeline")
            or (result.get("sii_intelligence") or {}).get("replay_timeline")
            or {}
        )
        timeline = replay.get("timeline") if isinstance(replay, dict) else []

        items.append({
            "job_id": result.get("job_id"),
            "run_id": result.get("run_id") or result.get("job_id"),
            "upload_id": result.get("upload_id") or result.get("job_id"),
            "filename": result.get("filename"),
            "status": "COMPLETE",
            "row_count": result.get("row_count", 0),
            "column_count": result.get("column_count", 0),
            "replay_ready": len(timeline or []) > 0,
            "replay_frame_count": len(timeline or []),
            "neraium_score": (result.get("sii_intelligence") or {}).get("neraium_score"),
            "intelligence_metrics": {
                "room_count": 1,
                "flagged_room_count": 0,
                "sparse_room_count": 0,
                "unknown_profile": False,
            },
            "completed_at": result.get("completed_at") or result.get("last_processed_at"),
            "session_scope": result.get("session_scope") if isinstance(result.get("session_scope"), dict) else None,
        })

    latest = current_result
    if latest and not any(item.get("job_id") == latest.get("job_id") for item in items):
        items.insert(0, {
            "job_id": latest.get("job_id"),
            "run_id": latest.get("run_id") or latest.get("job_id"),
            "upload_id": latest.get("upload_id") or latest.get("job_id"),
            "filename": latest.get("filename"),
            "status": "COMPLETE",
            "row_count": latest.get("row_count", 0),
            "column_count": latest.get("column_count", 0),
            "replay_ready": bool((latest.get("replay_timeline") or {}).get("timeline")),
            "replay_frame_count": len((latest.get("replay_timeline") or {}).get("timeline", [])),
            "neraium_score": (latest.get("sii_intelligence") or {}).get("neraium_score"),
            "intelligence_metrics": {
                "room_count": 1,
                "flagged_room_count": 0,
                "sparse_room_count": 0,
                "unknown_profile": False,
            },
            "completed_at": latest.get("completed_at") or latest.get("last_processed_at"),
            "session_scope": latest.get("session_scope") if isinstance(latest.get("session_scope"), dict) else None,
        })

    bounded_items = items[: max(0, int(limit or 100))]
    for index, item in enumerate(bounded_items):
        previous = bounded_items[index + 1] if index + 1 < len(bounded_items) else {}
        current_score = item.get("neraium_score")
        previous_score = previous.get("neraium_score")
        score_delta = None
        if isinstance(current_score, (int, float)) and isinstance(previous_score, (int, float)):
            score_delta = round(float(current_score) - float(previous_score), 2)
        item["diff"] = {
            "previous_filename": previous.get("filename"),
            "previous_processed_at": previous.get("completed_at"),
            "neraium_score_delta": score_delta,
        }
    return bounded_items
