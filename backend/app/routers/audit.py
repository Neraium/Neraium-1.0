from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.security import require_api_access
from app.routers.facility import resolve_uploaded_intelligence
from app.services.sii_intelligence import build_sample_intelligence
from app.services.upload_jobs import has_active_session_artifact, read_latest_upload_result
from audit.operational_audit_engine import OperationalAuditEngine
from replay.structural_replay_engine import StructuralReplayEngine

router = APIRouter(tags=["audit"], dependencies=[Depends(require_api_access)])
_audit_engine = OperationalAuditEngine()
_replay_engine = StructuralReplayEngine()


@router.get("/audit/session/{session_id}")
def read_audit_session(session_id: str) -> dict[str, Any]:
    intelligence = current_intelligence()
    replay = _replay_engine.build_timeline(intelligence=intelligence, intervals=24, replay_compression=1)
    return _audit_engine.build_record(
        session_id=session_id,
        intelligence=intelligence,
        replay_timeline=replay.get("timeline", []),
    )


@router.get("/audit/replay/{session_id}")
def read_audit_replay(session_id: str) -> dict[str, Any]:
    intelligence = current_intelligence()
    replay = _replay_engine.build_timeline(intelligence=intelligence, intervals=24, replay_compression=1)
    return {
        "session_id": session_id,
        "replay": replay.get("timeline", []),
    }


@router.get("/audit/evidence/{session_id}")
def read_audit_evidence(session_id: str) -> dict[str, Any]:
    intelligence = current_intelligence()
    lineages = intelligence.get("evidence_lineage", {}).get("lineages", [])
    return {
        "session_id": session_id,
        "evidence_lineage": lineages,
        "historical_memory_references": [item.get("fingerprint_id") for item in intelligence.get("structural_memory", {}).get("memory_matches", [])],
    }


def current_intelligence() -> dict[str, Any]:
    latest_result = read_latest_upload_result()
    if not has_active_session_artifact(latest_result):
        return build_sample_intelligence()
    intelligence = resolve_uploaded_intelligence(latest_result, include_persisted=True)
    return intelligence or build_sample_intelligence()

