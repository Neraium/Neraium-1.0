from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.core.config import get_settings
from app.core.security import require_api_access
from app.services.upload_state_repository import read_replay_payload, resolve_upload_artifacts

router = APIRouter(prefix="/replay", tags=["replay"], dependencies=[Depends(require_api_access)])
ReplayMode = Literal["live", "demo", "aquatic_demo", "live_causal"]
ReplayJobId = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]


@router.get("/timeline")
async def replay_timeline(
    mode: ReplayMode = Query(default="live"),
    intervals: int = Query(default=24, ge=1, le=1000),
):
    normalized_mode = str(mode or "live").lower()
    if normalized_mode == "demo":
        timeline = synthetic_timeline(max(8, int(intervals or 8)), prefix="demo")
        return {"source": "demo", "meta": {"frame_count": len(timeline), "mode": "demo"}, "timeline": timeline}
    if normalized_mode == "aquatic_demo":
        timeline = synthetic_timeline(max(18, int(intervals or 18)), prefix="aquatic_demo")
        return {
            "source": "aquatic_demo",
            "meta": {"frame_count": len(timeline), "mode": "aquatic_demo", "domain": "commercial_aquatic_hospitality"},
            "timeline": timeline,
        }

    artifacts = resolve_upload_artifacts()
    canonical_result = artifacts.get("active_result") if isinstance(artifacts.get("active_result"), dict) else None
    replay_payload = artifacts.get("replay") if canonical_result else {}
    timeline = replay_payload.get("timeline", []) if isinstance(replay_payload, dict) else []
    timeline = timeline if isinstance(timeline, list) else []
    source = "uploaded" if timeline else "empty"

    if normalized_mode == "live_causal":
        timeline = [{**frame, "live_causal": {"lookahead_free": True}} for frame in (timeline or []) if isinstance(frame, dict)]
    canonical_flow = [frame.get("cognition_state", {}).get("canonical_phase") for frame in timeline if isinstance(frame, dict)]
    return {
        "source": source,
        "meta": {
            "frame_count": len(timeline),
            "canonical_flow": [value for value in canonical_flow if value],
            "mode": normalized_mode,
            "lookahead_free": normalized_mode == "live_causal",
        },
        "timeline": timeline,
    }


@router.get("/frame/{timestamp}")
async def replay_frame(
    timestamp: Annotated[str, Path(min_length=1, max_length=64)],
    mode: ReplayMode = Query(default="live"),
    intervals: int = Query(default=24, ge=1, le=1000),
):
    timeline_payload = await replay_timeline(mode=mode, intervals=intervals)
    timeline = timeline_payload.get("timeline", [])
    frame = next((item for item in timeline if str(item.get("timestamp")) == str(timestamp)), None)
    if frame is None:
        raise HTTPException(status_code=404, detail="Replay frame was not found.")
    return {"frame": frame, "source": timeline_payload.get("source", "empty")}


@router.get("/range")
async def replay_range(
    start_timestamp: str = Query(min_length=1, max_length=64),
    end_timestamp: str = Query(min_length=1, max_length=64),
    mode: ReplayMode = Query(default="live"),
    intervals: int = Query(default=24, ge=1, le=1000),
):
    start_value = _parse_timestamp(start_timestamp, "start_timestamp")
    end_value = _parse_timestamp(end_timestamp, "end_timestamp")
    if start_value > end_value:
        raise HTTPException(status_code=422, detail="start_timestamp must be before or equal to end_timestamp.")
    timeline_payload = await replay_timeline(mode=mode, intervals=intervals)
    timeline = timeline_payload.get("timeline", [])
    frames = [
        item for item in timeline
        if _timestamp_in_range(item.get("timestamp"), start_value, end_value)
    ]
    return {"frame_count": len(frames), "frames": frames, "source": timeline_payload.get("source", "empty")}


@router.get("/{job_id}")
async def replay_by_job(job_id: ReplayJobId):
    payload = read_replay_payload(job_id)
    if not payload or not payload.get("timeline"):
        raise HTTPException(status_code=404, detail="Replay was not found.")
    return payload


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} must be an ISO 8601 timestamp.") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HTTPException(status_code=422, detail=f"{field} must include a timezone offset.")
    return parsed.astimezone(UTC)


def _timestamp_in_range(value: object, start: datetime, end: datetime) -> bool:
    try:
        parsed = _parse_timestamp(str(value or ""), "timeline timestamp")
    except HTTPException:
        return False
    return start <= parsed <= end


def synthetic_timeline(frame_count: int, prefix: str) -> list[dict]:
    start = datetime.now(UTC) - timedelta(minutes=frame_count)
    timeline = []
    for index in range(frame_count):
        ts = (start + timedelta(minutes=index)).isoformat()
        phase = "stable_topology" if index < frame_count // 3 else ("relationship_weakening" if index < (2 * frame_count // 3) else "propagation_activation")
        timeline.append(
            {
                "timestamp": ts,
                "topology_state": {"phase": phase},
                "subsystem_pressure": {"score": round(index / max(1, frame_count - 1), 3)},
                "active_archetypes": [f"{prefix}_pattern"],
                "propagation_state": {"dominant_paths": ["loop_a"]},
                "evidence_state": {"corroboration_strength": "moderate"},
                "cognition_state": {"canonical_phase": phase},
            }
        )
    return timeline
