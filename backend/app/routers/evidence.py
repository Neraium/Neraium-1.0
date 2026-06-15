from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from app.core.security import require_api_access
from app.models.api_models import EvidenceRunResponse, EvidenceRunsListResponse, LatestEvidenceResponse, OperatorFeedbackRequest
from app.services.evidence_store import FEEDBACK_CATEGORIES, build_evidence_export, build_evidence_export_csv, build_evidence_export_payload, latest_evidence_run, list_evidence_runs, read_evidence_run, record_operator_feedback
from app.services.runtime_db import now_iso, record_audit_event
from app.routers import data as data_router
from app.services.upload_state_repository import read_evidence_by_identity


router = APIRouter(tags=["evidence"], dependencies=[Depends(require_api_access)])


@router.get("/evidence/runs", response_model=EvidenceRunsListResponse)
def get_evidence_runs() -> dict[str, Any]:
    return {"runs": list_evidence_runs(limit=100)}


@router.get("/evidence/runs/{run_id}", response_model=EvidenceRunResponse)
def get_evidence_run(run_id: str) -> dict[str, Any]:
    record = read_evidence_by_identity(run_id) or read_evidence_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence run not found.")
    return record


@router.get("/evidence/latest", response_model=LatestEvidenceResponse)
def get_latest_evidence() -> dict[str, Any]:
    record = read_evidence_by_identity() or latest_evidence_run()
    if record is None:
        return {
            "status": "empty",
            "message": "No evidence trail yet. Connect data or upload telemetry to generate the first evidence record.",
            "run": None,
        }
    return {"status": "ok", "run": record}


@router.get("/evidence/export/{run_id}", response_model=None)
def export_evidence_run(request: Request, run_id: str, format: str = Query(default="markdown")):
    record = read_evidence_by_identity(run_id) or read_evidence_run(run_id)
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
    normalized_format = str(format or "markdown").strip().lower()
    if normalized_format == "json":
        return JSONResponse(
            content=build_evidence_export_payload(record),
            headers={"Content-Disposition": f'attachment; filename="neraium-evidence-{run_id}.json"'},
        )
    if normalized_format == "csv":
        body = build_evidence_export_csv(record)
        return Response(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="neraium-evidence-{run_id}.csv"'},
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
        updated = record_operator_feedback(run_id, payload.category, payload.note, actor, now_iso())
    except ValueError as error:
        detail = str(error)
        if detail == "evidence_run_not_found":
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
