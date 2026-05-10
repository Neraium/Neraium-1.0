from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.core.security import require_api_access
from app.models.api_models import EvidenceRunResponse, EvidenceRunsListResponse, LatestEvidenceResponse
from app.services.evidence_store import build_evidence_export, latest_evidence_run, list_evidence_runs, read_evidence_run
from app.services.runtime_db import record_audit_event


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
