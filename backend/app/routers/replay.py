from __future__ import annotations

from fastapi import APIRouter
from app.services import upload_jobs

router = APIRouter(prefix="/replay", tags=["replay"])


@router.get("/timeline")
async def replay_timeline():
    return upload_jobs.replay_payload()


@router.get("/{job_id}")
async def replay_by_job(job_id: str):
    return upload_jobs.replay_payload(job_id)
