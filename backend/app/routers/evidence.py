from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.core.security import require_api_access
from app.models.api_models import EvidenceRunResponse, EvidenceRunsListResponse, LatestEvidenceResponse, OperatorFeedbackRequest
from app.services.adaptive_learning import FEEDBACK_CATEGORIES, apply_operator_feedback
from app.services.evidence_store import build_evidence_export, latest_evidence_run, list_evidence_runs, read_evidence_run
from app.services.runtime_db import record_audit_event
from app.routers import data as data_router


router = APIRouter(tags=["evidence"], dependencies=[Depends(require_api_access)])


@router.get("/evidence/runs", response_model=EvidenceRunsListResponse)
def get_evidence_runs() -> dict[str, Any]:
    return {"runs": list_evidence_runs(limit=100)}


@router.get("/evidence/runs/{run_id}", response_model=EvidenceRunResponse)
def get_evidence_run(run_id: str) -> dict[str, Any]:
    record = read_evidence_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence run not found.")
    return record


@router.get("/evidence/latest", response_model=LatestEvidenceResponse)
def get_latest_evidence() -> dict[str, Any]:
    record = latest_evidence_run()
    if record is None:
        return {
            "status": "empty",
            "message": "No evidence trail yet. Connect data or upload telemetry to generate the first evidence record.",
            "run": None,
        }
    return {"status": "ok", "run": record}


@router.get("/evidence/export/{run_id}", response_model=None)
def export_evidence_run(request: Request, run_id: str):
    record = read_evidence_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence run not found.")
    auth_context = getattr(request.state, "auth_context", {})
    record_audit_event(
        actor=auth_context.get("auth_subject", record.get("initiated_by", "unknown")),
        action="evidence.export",
        resource_type="evidence_run",
        resource_id=run_id,
        request_id=auth_context.get("request_id"),
        detail={"source_name": record.get("source_name")},
    )
    body = build_evidence_export(record)
    return PlainTextResponse(
        content=body,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="neraium-evidence-{run_id}.md"'},
    )


@router.post("/evidence/runs/{run_id}/feedback", response_model=EvidenceRunResponse)
def submit_evidence_feedback(request: Request, run_id: str, payload: OperatorFeedbackRequest) -> dict[str, Any]:
    auth_context = getattr(request.state, "auth_context", {})
    actor = auth_context.get("auth_subject", "operator")
    try:
        updated = apply_operator_feedback(run_id, payload.category, payload.note, actor)
    except ValueError as error:
        detail = str(error)
        if detail == "evidence_run_not_found":
            fallback_run = latest_evidence_run()
            fallback_run_id = str((fallback_run or {}).get("run_id") or "")
            if fallback_run_id:
                updated = apply_operator_feedback(fallback_run_id, payload.category, payload.note, actor)
            else:
                raise HTTPException(status_code=404, detail="Evidence run not found.") from None
        elif detail == "invalid_feedback_category":
            raise HTTPException(status_code=400, detail={"allowed_categories": FEEDBACK_CATEGORIES}) from None
        else:
            raise
    record_audit_event(
        actor=actor,
        action="evidence.feedback.recorded",
        resource_type="evidence_run",
        resource_id=run_id,
        request_id=auth_context.get("request_id"),
        detail={"category": payload.category, "note_present": bool(payload.note)},
    )
    data_router.invalidate_latest_upload_cache()
    return updated
