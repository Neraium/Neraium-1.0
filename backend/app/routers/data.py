from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from app.services import upload_jobs

router = APIRouter(prefix="/data", tags=["data"])


@router.post("/upload")
async def upload_data(file: UploadFile = File(...)):
    content = await file.read()
    summary = upload_jobs.process_upload_bytes(file.filename or "upload.csv", content)
    return summary


@router.get("/upload-status/{job_id}")
async def upload_status(job_id: str):
    status = upload_jobs.read_upload_status(job_id)
    if status:
        return status
    return {
        "job_id": job_id,
        "status": "MISSING",
        "processing_state": "missing",
        "percent": 0,
        "replay_ready": False,
        "replay_frame_count": 0,
        "result_available": False,
    }


@router.get("/latest-upload")
async def latest_upload(include_persisted: int | bool = True):
    result = upload_jobs.read_latest_upload_result()
    summary = upload_jobs.read_latest_upload_summary() or {}
    replay = (result or {}).get("replay_timeline") or {}
    frames = replay.get("timeline") if isinstance(replay, dict) else []
    snapshot = {
        **summary,
        "status": summary.get("status", "COMPLETE" if result else "empty"),
        "processing_state": summary.get("processing_state", "complete" if result else "empty"),
        "result_available": bool(result),
        "sii_completed": bool(result),
        "replay_ready": bool(frames),
        "replay_frame_count": len(frames or []),
        "latest_replay_frames": len(frames or []),
        "replay_source": "persisted" if frames else "unknown",
    }
    return {
        "snapshot": snapshot,
        "latest_result": result,
        "latestResult": result,
        "summary": summary,
        **snapshot,
    }


@router.get("/replay/{job_id}")
async def data_replay(job_id: str):
    return upload_jobs.replay_payload(job_id)


@router.post("/reset")
async def reset_data():
    upload_jobs.reset_upload_state()
    return {"ok": True, "status": "reset"}


def rebuild_upload_replay_from_source(job_id: str | None = None, *args, **kwargs):
    return upload_jobs.replay_payload(job_id)
