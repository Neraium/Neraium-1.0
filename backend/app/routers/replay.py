from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.services import upload_jobs
from app.services.sii_runner import read_latest_sii_state

router = APIRouter(prefix="/replay", tags=["replay"])


@router.get("/timeline")
async def replay_timeline(mode: str = Query(default="live"), intervals: int = Query(default=24)):
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

    state = read_latest_sii_state() or {}
    replay = (state.get("replay_timeline") if isinstance(state, dict) else {}) or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    source = state.get("source", "uploaded") if timeline else "empty"
    if not timeline:
        fallback = upload_jobs.replay_payload()
        timeline = fallback.get("timeline", [])
        fallback_source = fallback.get("source", "empty")
        source = "uploaded" if fallback_source == "persisted" and timeline else fallback_source
    if not timeline and get_settings().app_env.lower() not in {"prod", "production"}:
        timeline = synthetic_timeline(max(6, int(intervals or 12)), prefix="live")
        source = "state_synthesized"

    if normalized_mode == "live_causal":
        timeline = [{**frame, "live_causal": {"lookahead_free": True}} for frame in timeline]
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
async def replay_frame(timestamp: str, mode: str = Query(default="live"), intervals: int = Query(default=24)):
    timeline_payload = await replay_timeline(mode=mode, intervals=intervals)
    timeline = timeline_payload.get("timeline", [])
    frame = next((item for item in timeline if str(item.get("timestamp")) == str(timestamp)), None)
    return {"frame": frame or (timeline[0] if timeline else {}), "source": timeline_payload.get("source", "empty")}


@router.get("/range")
async def replay_range(start_timestamp: str, end_timestamp: str, mode: str = Query(default="live"), intervals: int = Query(default=24)):
    timeline_payload = await replay_timeline(mode=mode, intervals=intervals)
    timeline = timeline_payload.get("timeline", [])
    frames = [item for item in timeline if str(start_timestamp) <= str(item.get("timestamp", "")) <= str(end_timestamp)]
    if not frames and timeline:
        frames = timeline
    return {"frame_count": len(frames), "frames": frames, "source": timeline_payload.get("source", "empty")}


@router.get("/{job_id}")
async def replay_by_job(job_id: str):
    return upload_jobs.replay_payload(job_id)


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
