from typing import Any

from fastapi import APIRouter, Query

from app.services.domain_mode import detect_domain_mode, domain_profile, normalize_domain_mode, read_domain_mode

router = APIRouter(tags=["app"])


@router.get("/app")
def read_app_metadata(domain_mode: str | None = Query(default=None, pattern=r"^(aquatic|cultivation)$")) -> dict[str, str]:
    selected_mode = normalize_domain_mode(domain_mode) if domain_mode else read_domain_mode()
    profile = domain_profile(selected_mode)
    return {
        "name": "Neraium",
        "subtitle": profile["app_subtitle"],
        "description": profile["app_description"],
        "environment": "development",
        "version": "0.1.0",
        "domain_mode": selected_mode,
    }


@router.get("/domain/mode")
def read_domain_mode_status() -> dict[str, Any]:
    detection = detect_domain_mode()
    selected_mode = detection["mode"]
    profile = domain_profile(selected_mode)
    return {
        "mode": selected_mode,
        "source": detection["source"],
        "confidence": detection["confidence"],
        "evidence": detection["evidence"],
        "supported_modes": sorted(["aquatic", "cultivation"]),
        "profile": {
            "subtitle": profile["app_subtitle"],
            "description": profile["app_description"],
            "replay_demo_mode": profile["replay_demo_mode"],
        },
    }
