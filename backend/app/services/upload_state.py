from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.dataset_scope import DatasetScope, attach_dataset_scope, current_dataset_scope, dataset_scope_from_payload
from app.services.upload_lifecycle import ACTIVE_UPLOAD_STATUSES


def build_session_scope(
    job_id: str | None,
    *,
    filename: str | None = None,
    status: str = "active",
    dataset_scope: DatasetScope | dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_job_id = str(job_id or "").strip()
    if isinstance(dataset_scope, DatasetScope):
        resolved_scope = dataset_scope
    elif isinstance(dataset_scope, dict):
        resolved_scope = dataset_scope_from_payload({"dataset_scope": dataset_scope}) or dataset_scope_from_payload({"session_scope": dataset_scope}) or current_dataset_scope()
    else:
        resolved_scope = current_dataset_scope()
    return {
        "active": bool(normalized_job_id),
        "status": str(status or "active"),
        "job_id": normalized_job_id,
        "run_id": normalized_job_id,
        "upload_id": normalized_job_id,
        "dataset_id": normalized_job_id or None,
        "source_name": str(filename or "").strip() or None,
        **resolved_scope.as_dict(),
    }


def has_active_session_artifact(candidate: dict[str, Any] | None, *, job_id: str | None = None) -> bool:
    if not isinstance(candidate, dict):
        return False
    scope = candidate.get("session_scope")
    if not isinstance(scope, dict) or scope.get("active") is not True:
        return False
    scope_job_id = str(scope.get("job_id") or candidate.get("job_id") or "").strip()
    expected_job_id = str(job_id or "").strip()
    if expected_job_id and scope_job_id and scope_job_id != expected_job_id:
        return False
    return bool(scope_job_id or expected_job_id)


def build_empty_latest_upload_record(*, status: str = "empty", message: str | None = None) -> dict[str, Any]:
    normalized_status = str(status or "empty").strip().lower() or "empty"
    normalized_message = message or ("No active upload session." if normalized_status == "empty" else None)
    dataset_scope = current_dataset_scope()
    return {
        "version": 1,
        "status": normalized_status,
        "message": normalized_message,
        "job_id": None,
        "run_id": None,
        "upload_id": None,
        "dataset_id": None,
        "dataset_scope": dataset_scope.as_dict(),
        "filename": None,
        "session_scope": {
            "active": False,
            "status": normalized_status,
            "job_id": "",
            "run_id": "",
            "upload_id": "",
            "dataset_id": None,
            "source_name": None,
            **dataset_scope.as_dict(),
        },
        "traceability": {},
        "summary": None,
        "result": None,
        "replay": {
            "job_id": None,
            "run_id": None,
            "upload_id": None,
            "source": "empty",
            "meta": {"lineage": {}},
            "timeline": [],
            "frames": [],
            "frame_count": 0,
            "replay_ready": False,
            "traceability": {},
            "message": normalized_message or "",
        },
        "evidence": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_upload_identity(payload: dict[str, Any] | None) -> tuple[str, str, str]:
    if not isinstance(payload, dict):
        return ("", "", "")
    job_id = str(payload.get("job_id") or "").strip()
    run_id = str(payload.get("run_id") or job_id).strip()
    upload_id = str(payload.get("upload_id") or job_id).strip()
    return (job_id, run_id, upload_id)


def build_replay_payload_from_result(result: dict[str, Any] | None, job_id: str | None = None) -> dict[str, Any]:
    candidate = dict(result or {})
    replay = candidate.get("replay_timeline") or (candidate.get("sii_intelligence") or {}).get("replay_timeline") or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    traceability = candidate.get("traceability") if isinstance(candidate.get("traceability"), dict) else {}
    replay_job_id, replay_run_id, replay_upload_id = normalize_upload_identity(candidate)
    replay_job_id = replay_job_id or str(job_id or "")
    replay_run_id = replay_run_id or replay_job_id
    replay_upload_id = replay_upload_id or replay_job_id
    return {
        "job_id": replay_job_id or None,
        "run_id": replay_run_id or None,
        "upload_id": replay_upload_id or None,
        "source": "persisted" if timeline else "empty",
        "meta": {**(replay.get("meta", {}) if isinstance(replay, dict) else {}), "lineage": traceability},
        "timeline": timeline or [],
        "frames": timeline or [],
        "frame_count": len(timeline or []),
        "replay_ready": len(timeline or []) > 0,
        "traceability": traceability,
        "message": "" if timeline else ("No replay is available for the requested upload job." if job_id else ""),
    }


def build_latest_upload_record(
    *,
    summary: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    status: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    normalized_summary = dict(summary or {}) if isinstance(summary, dict) else None
    normalized_result = dict(result or {}) if isinstance(result, dict) else None
    job_id, run_id, upload_id = normalize_upload_identity(normalized_result or normalized_summary)
    if not job_id and not normalized_result and not normalized_summary:
        return build_empty_latest_upload_record(status=status or "empty", message=message)

    traceability = {}
    if normalized_result and isinstance(normalized_result.get("traceability"), dict):
        traceability = dict(normalized_result.get("traceability") or {})
    elif normalized_summary and isinstance(normalized_summary.get("traceability"), dict):
        traceability = dict(normalized_summary.get("traceability") or {})

    record_status = str(
        status
        or (normalized_summary or {}).get("processing_state")
        or (normalized_summary or {}).get("status")
        or ("active" if normalized_result else "processing")
    ).strip().lower() or "active"
    active = bool(job_id) and (
        has_active_session_artifact(normalized_result, job_id=job_id)
        or has_active_session_artifact(normalized_summary, job_id=job_id)
        or record_status in ACTIVE_UPLOAD_STATUSES
    )
    source_payload = normalized_result or normalized_summary or {}
    session_scope = (
        (normalized_result or {}).get("session_scope")
        if isinstance((normalized_result or {}).get("session_scope"), dict)
        else (
            (normalized_summary or {}).get("session_scope")
            if isinstance((normalized_summary or {}).get("session_scope"), dict)
            else build_session_scope(job_id or None, filename=source_payload.get("filename"), status=record_status)
        )
    )
    resolved_dataset_scope = dataset_scope_from_payload(source_payload) or dataset_scope_from_payload({"session_scope": session_scope}) or current_dataset_scope()
    session_scope = {
        **dict(session_scope or {}),
        "active": active,
        "status": record_status,
        "job_id": job_id,
        "run_id": run_id or job_id,
        "upload_id": upload_id or job_id,
        "dataset_id": source_payload.get("dataset_id") or job_id,
        "source_name": source_payload.get("filename") or session_scope.get("source_name"),
        **resolved_dataset_scope.as_dict(),
    }
    replay_payload = build_replay_payload_from_result(normalized_result, job_id=job_id)
    record = {
        "version": 1,
        "status": record_status,
        "message": message or (normalized_summary or {}).get("message"),
        "job_id": job_id or None,
        "run_id": (run_id or job_id) or None,
        "upload_id": (upload_id or job_id) or None,
        "dataset_id": source_payload.get("dataset_id") or job_id or None,
        "filename": source_payload.get("filename"),
        "session_scope": session_scope,
        "traceability": traceability,
        "summary": normalized_summary,
        "result": normalized_result,
        "replay": replay_payload,
        "evidence": dict(evidence or {}) if isinstance(evidence, dict) else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return attach_dataset_scope(record, scope=resolved_dataset_scope, dataset_id=record.get("dataset_id"))


def select_current_upload_result(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    job_id = str(record.get("job_id") or "").strip()
    result = record.get("result") if isinstance(record.get("result"), dict) else None
    if not has_active_session_artifact(result, job_id=job_id):
        return None
    return result
