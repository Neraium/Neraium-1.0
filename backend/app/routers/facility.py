from typing import Any

from fastapi import APIRouter, Depends, Query
from app.core.security import require_api_access
from api.cognition_contracts import build_canonical_cognition_state_response
from app.services.domain_mode import detect_domain_mode, domain_profile, normalize_domain_mode, read_domain_mode
from app.services.engine_identity import build_engine_identity
from app.services.sii_intelligence import REQUIRED_INTELLIGENCE_FIELDS, build_empty_intelligence_status, build_intelligence_status
from app.services.sii_runner import build_runner_status, read_latest_sii_state
from app.services.upload_state import has_active_session_artifact
from app.services.upload_state_repository import read_current_upload_result

router = APIRouter(tags=["facility"], dependencies=[Depends(require_api_access)])


@router.get("/facility/systems")
def read_facility_systems(include_persisted: bool = Query(True), domain_mode: str | None = Query(default=None)) -> dict[str, Any]:
    detection = detect_domain_mode()
    selected_mode = normalize_domain_mode(domain_mode) if domain_mode else read_domain_mode()
    profile = domain_profile(selected_mode)
    latest_result = read_current_upload_result() if include_persisted else None
    intelligence = resolve_uploaded_intelligence(latest_result, include_persisted=include_persisted)
    has_active_analysis = has_active_session_artifact(latest_result)
    return {
        "systems": profile["systems"] if has_active_analysis else [],
        "driver_categories": profile["driver_categories"] if has_active_analysis else [],
        "domain_mode": selected_mode,
        "domain_source": detection["source"],
        "domain_confidence": detection["confidence"],
        "domain_evidence": detection["evidence"],
        "intelligence": intelligence,
        "adaptive_learning": {},
        "integration_stubs": profile["integration_stubs"] if has_active_analysis else [],
        "intelligence_status": build_intelligence_status(intelligence) if intelligence else build_empty_intelligence_status(),
    }


@router.get("/intelligence/status")
def read_intelligence_status(include_persisted: bool = Query(True)) -> dict[str, Any]:
    latest_result = read_current_upload_result() if include_persisted else None
    intelligence = resolve_uploaded_intelligence(latest_result, include_persisted=include_persisted)
    return build_intelligence_status(intelligence) if intelligence else build_empty_intelligence_status()


@router.get("/facility/cognition-state")
def read_cognition_state(include_persisted: bool = Query(True)) -> dict[str, Any]:
    latest_result = read_current_upload_result() if include_persisted else None
    intelligence = resolve_uploaded_intelligence(latest_result, include_persisted=include_persisted)
    if not intelligence:
        return {
            "cognition_state": "Baseline Pending",
            "structural_stability": "BASELINE_PENDING",
            "active_archetypes": [],
            "propagation_pathways": [],
            "evidence_lineage": {},
            "structural_memory_matches": [],
            "continuation_windows": {"window": "Monitoring", "structural_pathways": [], "uncertainty_range": []},
            "replay_summary": {"frame_count": 0, "canonical_flow": [], "active_frame": {}},
            "recovery_convergence": {},
            "operator_explanation": "No active telemetry session is available yet.",
            "source_mode": "live",
        }
    response = build_canonical_cognition_state_response(intelligence)
    response["source_mode"] = "live"
    return response


def resolve_uploaded_intelligence(latest_result: dict[str, Any] | None, *, include_persisted: bool = False) -> dict[str, Any] | None:
    if not include_persisted or not has_active_session_artifact(latest_result):
        return None
    intelligence = read_latest_sii_state()
    result_intel = latest_result.get("sii_intelligence") if isinstance(latest_result, dict) and isinstance(latest_result.get("sii_intelligence"), dict) else {}
    result_rooms = result_intel.get("rooms") if isinstance(result_intel.get("rooms"), list) else []
    persisted_rooms = intelligence.get("rooms") if isinstance(intelligence, dict) and isinstance(intelligence.get("rooms"), list) else []

    if is_valid_persisted_intelligence(result_intel):
        if not is_valid_persisted_intelligence(intelligence):
            return result_intel
        if len(result_rooms) >= len(persisted_rooms):
            return result_intel
    if is_valid_persisted_intelligence(intelligence):
        if isinstance(latest_result, dict):
            result_room_summary = latest_result.get("room_summary") if isinstance(latest_result.get("room_summary"), dict) else {}
            if not isinstance(intelligence.get("room_summary"), dict):
                fallback_summary = result_intel.get("room_summary") if isinstance(result_intel.get("room_summary"), dict) else result_room_summary
                if isinstance(fallback_summary, dict) and fallback_summary:
                    intelligence = {**intelligence, "room_summary": fallback_summary}
        return intelligence
    return None


def is_valid_persisted_intelligence(candidate: Any) -> bool:
    if not isinstance(candidate, dict):
        return False
    if candidate.get("source") not in {"uploaded", "rest_poll"}:
        return False
    return isinstance(candidate.get("rooms"), list) or isinstance(candidate.get("room_summary"), dict)


@router.get("/intelligence/engine-identity")
def read_engine_identity() -> dict[str, Any]:
    return build_engine_identity()


@router.get("/intelligence/runner-status")
def read_runner_status() -> dict[str, Any]:
    return build_runner_status()
