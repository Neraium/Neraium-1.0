from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from app.services.analysis_result_contract import ensure_analysis_result
from app.services.dataset_scope import current_dataset_scope, payload_matches_dataset_scope
from app.services.upload_state import build_session_scope


_TRANSPORT_OMITTED_RESULT_KEYS = {
    # These internal engine artifacts are persisted for audit/replay, but are
    # too large and duplicative for the workspace hydration response.
    "sii_result",
    "analysis",
    "analysis_explanation",
    "relationship_model",
    "normalized_telemetry",
    "conditions",
}


def project_result_for_transport(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    projected = {
        key: value
        for key, value in result.items()
        if key not in _TRANSPORT_OMITTED_RESULT_KEYS
    }
    # Build/upgrade the existing presentation contract while the authoritative
    # SII result is still present; otherwise compact hydration would strip the
    # only source from which the bounded SII evidence projection can be made.
    projected["analysis_result"] = ensure_analysis_result(result)
    baseline = projected.get("baseline_analysis")
    if isinstance(baseline, dict) and "relationship_graph" in baseline:
        projected["baseline_analysis"] = {
            key: value
            for key, value in baseline.items()
            if key != "relationship_graph"
        }
    projected["transport_projection"] = {
        "version": 1,
        "omitted_internal_artifacts": sorted(_TRANSPORT_OMITTED_RESULT_KEYS),
    }
    return projected


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
    scope = current_dataset_scope()
    scoped_root = runtime_dir / "scopes" / scope.storage_id
    candidates: list[tuple[float, Path]] = []
    seen_uploads: set[str] = set()

    # Scoped files are authoritative. The runtime root is a compatibility
    # fallback for older writers, and is accepted only when its embedded scope
    # matches the current server-bound dataset scope.
    for root in (scoped_root, runtime_dir):
        try:
            paths = sorted(
                root.glob("upload_result_*.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            paths = []
        for path in paths:
            try:
                result = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(result, dict) or not payload_matches_dataset_scope(result, scope):
                continue
            upload_identity = str(
                result.get("job_id")
                or result.get("upload_id")
                or result.get("run_id")
                or path.stem
            ).strip()
            if upload_identity in seen_uploads:
                continue
            seen_uploads.add(upload_identity)
            try:
                modified_at = path.stat().st_mtime
            except OSError:
                modified_at = 0.0
            candidates.append((modified_at, path))

    items: list[dict[str, Any]] = []
    for _, path in sorted(candidates, key=lambda item: item[0], reverse=True):
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
