from typing import Any

from fastapi import APIRouter, Body, Query

from app.services.domain_mode import domain_profile, normalize_domain_mode, read_domain_mode, write_domain_mode

router = APIRouter(tags=["app"])


@router.get("/app")
def read_app_metadata(domain_mode: str | None = Query(default=None)) -> dict[str, str]:
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
    selected_mode = read_domain_mode()
    profile = domain_profile(selected_mode)
    return {
        "mode": selected_mode,
        "supported_modes": sorted(["aquatic", "cultivation"]),
        "profile": {
            "subtitle": profile["app_subtitle"],
            "description": profile["app_description"],
            "replay_demo_mode": profile["replay_demo_mode"],
        },
    }


@router.post("/domain/mode")
def update_domain_mode(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    selected_mode = normalize_domain_mode(payload.get("mode"))
    updated = write_domain_mode(selected_mode, actor="operator")
    profile = domain_profile(selected_mode)
    return {
        "mode": updated["mode"],
        "updated_at": updated["updated_at"],
        "profile": {
            "subtitle": profile["app_subtitle"],
            "description": profile["app_description"],
            "replay_demo_mode": profile["replay_demo_mode"],
        },
    }
