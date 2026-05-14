from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.security import require_api_access
from app.routers.facility import resolve_uploaded_intelligence
from app.services.sii_intelligence import build_sample_intelligence
from app.services.upload_jobs import read_latest_upload_result
from demo.canonical_replay_payload import build_canonical_demo_replay_payload
from replay.structural_replay_engine import StructuralReplayEngine

router = APIRouter(tags=["replay"], dependencies=[Depends(require_api_access)])
_engine = StructuralReplayEngine()


@router.get("/replay/timeline")
def replay_timeline(
    intervals: int = Query(24, ge=6, le=120),
    replay_compression: int = Query(1, ge=1, le=12),
    mode: str = Query("live"),
) -> dict[str, Any]:
    if mode == "demo":
        return build_canonical_demo_replay_payload(intervals=intervals)
    intelligence = current_intelligence()
    payload = _engine.build_timeline(
        intelligence=intelligence,
        intervals=intervals,
        replay_compression=replay_compression,
    )
    if not payload.get("timeline"):
        return build_canonical_demo_replay_payload(intervals=intervals)
    payload["source"] = intelligence.get("source", "sample")
    payload["facility_state"] = intelligence.get("facility_state")
    return payload


@router.get("/replay/frame/{timestamp}")
def replay_frame(
    timestamp: str,
    intervals: int = Query(24, ge=6, le=120),
    mode: str = Query("live"),
) -> dict[str, Any]:
    if mode == "demo":
        timeline = build_canonical_demo_replay_payload(intervals=intervals).get("timeline", [])
        frame = next((item for item in timeline if str(item.get("timestamp")) == timestamp), timeline[-1] if timeline else {})
        return {"source": "demo", "frame": frame}
    intelligence = current_intelligence()
    frame = _engine.frame_at_timestamp(
        intelligence=intelligence,
        timestamp=timestamp,
        intervals=intervals,
    )
    return {
        "source": intelligence.get("source", "sample"),
        "frame": frame,
    }


@router.get("/replay/range")
def replay_range(
    start_timestamp: str = Query(..., min_length=5),
    end_timestamp: str = Query(..., min_length=5),
    intervals: int = Query(24, ge=6, le=120),
    mode: str = Query("live"),
) -> dict[str, Any]:
    if mode == "demo":
        timeline = build_canonical_demo_replay_payload(intervals=intervals).get("timeline", [])
        frames = [f for f in timeline if start_timestamp <= str(f.get("timestamp")) <= end_timestamp]
        return {"source": "demo", "frames": frames, "frame_count": len(frames)}
    intelligence = current_intelligence()
    window = _engine.frame_range(
        intelligence=intelligence,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        intervals=intervals,
    )
    return {
        "source": intelligence.get("source", "sample"),
        **window,
    }


def current_intelligence() -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    intelligence = resolve_uploaded_intelligence(latest_result)
    return intelligence or build_sample_intelligence()
