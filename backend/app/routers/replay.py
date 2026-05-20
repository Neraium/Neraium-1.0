from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.security import require_api_access
from app.routers.facility import resolve_uploaded_intelligence
from app.services.sii_intelligence import build_sample_intelligence
from app.services.upload_jobs import read_latest_upload_result
from demo.aquatic_replay_payload import build_aquatic_demo_replay_payload
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
    if mode == "aquatic_demo":
        return build_aquatic_demo_replay_payload(intervals=intervals)
    intelligence = current_intelligence()
    persisted = (intelligence.get("replay_timeline") if isinstance(intelligence, dict) else None) or {}
    persisted_timeline = persisted.get("timeline") if isinstance(persisted, dict) else None
    if isinstance(persisted_timeline, list) and persisted_timeline:
        payload = {
            "meta": persisted.get("meta", {}),
            "timeline": persisted_timeline,
            "source": intelligence.get("source", "uploaded"),
            "facility_state": intelligence.get("facility_state"),
        }
        return payload
    payload = _engine.build_timeline(
        intelligence=intelligence,
        intervals=intervals,
        replay_compression=replay_compression,
    )
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
    if mode == "aquatic_demo":
        timeline = build_aquatic_demo_replay_payload(intervals=intervals).get("timeline", [])
        frame = next((item for item in timeline if str(item.get("timestamp")) == timestamp), timeline[-1] if timeline else {})
        return {"source": "aquatic_demo", "frame": frame}
    intelligence = current_intelligence()
    persisted = (intelligence.get("replay_timeline") if isinstance(intelligence, dict) else None) or {}
    persisted_timeline = persisted.get("timeline") if isinstance(persisted, dict) else None
    if isinstance(persisted_timeline, list) and persisted_timeline:
        frame = next((item for item in persisted_timeline if str(item.get("timestamp")) == timestamp), persisted_timeline[-1])
        return {"source": intelligence.get("source", "uploaded"), "frame": frame}
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
    if mode == "aquatic_demo":
        timeline = build_aquatic_demo_replay_payload(intervals=intervals).get("timeline", [])
        frames = [f for f in timeline if start_timestamp <= str(f.get("timestamp")) <= end_timestamp]
        return {"source": "aquatic_demo", "frames": frames, "frame_count": len(frames)}
    intelligence = current_intelligence()
    persisted = (intelligence.get("replay_timeline") if isinstance(intelligence, dict) else None) or {}
    persisted_timeline = persisted.get("timeline") if isinstance(persisted, dict) else None
    if isinstance(persisted_timeline, list) and persisted_timeline:
        frames = [f for f in persisted_timeline if start_timestamp <= str(f.get("timestamp")) <= end_timestamp]
        return {
            "source": intelligence.get("source", "uploaded"),
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "frame_count": len(frames),
            "frames": frames,
        }
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
    intelligence = resolve_uploaded_intelligence(latest_result, include_persisted=True)
    return intelligence or build_sample_intelligence()
