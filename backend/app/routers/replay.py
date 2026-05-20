from __future__ import annotations

from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.security import require_api_access
from app.routers.facility import resolve_uploaded_intelligence
from app.services.domain_mode import domain_profile, normalize_domain_mode, read_domain_mode
from app.services.sii_intelligence import build_sample_intelligence
from app.services.upload_jobs import read_latest_upload_result
from demo.aquatic_replay_payload import build_aquatic_demo_replay_payload
from demo.canonical_replay_payload import build_canonical_demo_replay_payload
from replay.structural_replay_engine import StructuralReplayEngine

router = APIRouter(tags=["replay"], dependencies=[Depends(require_api_access)])
_engine = StructuralReplayEngine()
MAX_INTERVALS_BY_SOURCE = {
    "sample": 72,
    "uploaded": 120,
    "rest_poll": 96,
}
_TIMELINE_CACHE: OrderedDict[str, dict[str, Any]] = OrderedDict()
_MAX_CACHE_ITEMS = 10


@router.get("/replay/timeline")
def replay_timeline(
    intervals: int = Query(24, ge=6, le=120),
    replay_compression: int = Query(1, ge=1, le=12),
    mode: str = Query("live"),
    domain_mode: str | None = Query(default=None),
) -> dict[str, Any]:
    selected_mode = normalize_domain_mode(domain_mode) if domain_mode else read_domain_mode()
    demo_mode = domain_profile(selected_mode)["replay_demo_mode"]
    if mode == "demo":
        mode = demo_mode
    if mode == "demo":
        return build_canonical_demo_replay_payload(intervals=intervals)
    if mode == "aquatic_demo":
        return build_aquatic_demo_replay_payload(intervals=intervals)
    intelligence = current_intelligence()
    bounded_intervals = min(intervals, max_intervals_for_intelligence(intelligence))
    cache_key = cache_key_for_timeline(
        intelligence=intelligence,
        mode=mode,
        intervals=bounded_intervals,
        replay_compression=replay_compression,
    )
    cached = read_timeline_cache(cache_key)
    if cached is not None:
        return cached
    persisted = (intelligence.get("replay_timeline") if isinstance(intelligence, dict) else None) or {}
    persisted_timeline = persisted.get("timeline") if isinstance(persisted, dict) else None
    if isinstance(persisted_timeline, list) and persisted_timeline:
        payload = {
            "meta": persisted.get("meta", {}),
            "timeline": persisted_timeline,
            "source": intelligence.get("source", "uploaded"),
            "facility_state": intelligence.get("facility_state"),
        }
        write_timeline_cache(cache_key, payload)
        return payload
    payload = _engine.build_timeline(
        intelligence=intelligence,
        intervals=bounded_intervals,
        replay_compression=replay_compression,
    )
    payload["source"] = intelligence.get("source", "sample")
    payload["facility_state"] = intelligence.get("facility_state")
    write_timeline_cache(cache_key, payload)
    return payload


@router.get("/replay/frame/{timestamp}")
def replay_frame(
    timestamp: str,
    intervals: int = Query(24, ge=6, le=120),
    mode: str = Query("live"),
    domain_mode: str | None = Query(default=None),
) -> dict[str, Any]:
    selected_mode = normalize_domain_mode(domain_mode) if domain_mode else read_domain_mode()
    demo_mode = domain_profile(selected_mode)["replay_demo_mode"]
    if mode == "demo":
        mode = demo_mode
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
    domain_mode: str | None = Query(default=None),
) -> dict[str, Any]:
    selected_mode = normalize_domain_mode(domain_mode) if domain_mode else read_domain_mode()
    demo_mode = domain_profile(selected_mode)["replay_demo_mode"]
    if mode == "demo":
        mode = demo_mode
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


def max_intervals_for_intelligence(intelligence: dict[str, Any]) -> int:
    source = str(intelligence.get("source") or "sample")
    return MAX_INTERVALS_BY_SOURCE.get(source, 96)


def cache_key_for_timeline(
    *,
    intelligence: dict[str, Any],
    mode: str,
    intervals: int,
    replay_compression: int,
) -> str:
    marker = (
        intelligence.get("last_processed_at")
        or intelligence.get("last_updated")
        or intelligence.get("filename")
        or "no-marker"
    )
    source = intelligence.get("source", "sample")
    return f"{source}|{marker}|{mode}|{intervals}|{replay_compression}"


def read_timeline_cache(key: str) -> dict[str, Any] | None:
    payload = _TIMELINE_CACHE.get(key)
    if payload is None:
        return None
    _TIMELINE_CACHE.move_to_end(key)
    return payload


def write_timeline_cache(key: str, payload: dict[str, Any]) -> None:
    _TIMELINE_CACHE[key] = payload
    _TIMELINE_CACHE.move_to_end(key)
    while len(_TIMELINE_CACHE) > _MAX_CACHE_ITEMS:
        _TIMELINE_CACHE.popitem(last=False)
