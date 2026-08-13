from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from app.core.security import require_api_access, require_operator_role
from app.models.api_models import EvidenceRunResponse, EvidenceRunsListResponse, FindingStatusRequest, LatestEvidenceResponse, OperatorFeedbackRequest
from app.services.evidence_store import FEEDBACK_CATEGORIES, build_evidence_export, build_evidence_export_csv, build_evidence_export_payload, build_evidence_package_payload, build_evidence_package_pdf, latest_evidence_run, list_evidence_runs_page, read_evidence_run, record_finding_status, record_operator_feedback, tag_evidence_for_audit
from app.services.runtime_db import now_iso, record_audit_event
from app.routers import data as data_router
from app.services.upload_state_repository import read_evidence_by_identity
from app.services.upload_state_repository import read_upload_result_by_job_id
from app.services.analysis_provenance import result_digest


router = APIRouter(tags=["evidence"], dependencies=[Depends(require_api_access)])
RunIdPath = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")]


@router.get("/evidence/runs", response_model=EvidenceRunsListResponse)
def get_evidence_runs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
) -> dict[str, Any]:
    return list_evidence_runs_page(limit=limit, offset=offset)


@router.get("/evidence/runs/{run_id}", response_model=EvidenceRunResponse)
def get_evidence_run(run_id: RunIdPath) -> dict[str, Any]:
    record = read_evidence_run(run_id) or read_evidence_by_identity(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence run not found.")
    return record


@router.get("/evidence/runs/{run_id}/integrity")
def verify_evidence_run_integrity(run_id: RunIdPath) -> dict[str, Any]:
    record = read_evidence_run(run_id) or read_evidence_by_identity(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence run not found.")
    result = read_upload_result_by_job_id(run_id)
    expected = str(record.get("result_hash") or "")
    actual = result_digest(result) if isinstance(result, dict) else None
    return {
        "run_id": run_id,
        "status": "verified" if expected and actual == expected else "unavailable" if actual is None else "mismatch",
        "result_hash_matches": bool(expected and actual == expected),
        "expected_result_hash": expected or None,
        "actual_result_hash": actual,
        "input_hash_recorded": bool(record.get("input_hash")),
        "baseline_identity_recorded": bool(record.get("baseline_id") and record.get("baseline_dataset_id")),
        "configuration_hash_recorded": bool(record.get("configuration_hash")),
        "build_commit": record.get("build_commit"),
    }


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
def export_evidence_run(request: Request, run_id: RunIdPath, format: Literal["markdown", "json", "csv"] = Query(default="markdown")):
    record = read_evidence_run(run_id) or read_evidence_by_identity(run_id)
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


@router.get("/evidence/package/{run_id}", response_model=None)
async def export_evidence_package(request: Request, run_id: RunIdPath, format: Literal["pdf", "json"] = Query(default="pdf")):
    record = read_evidence_run(run_id) or read_evidence_by_identity(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence run not found.")
    await require_operator_role(request)
    package = build_evidence_package_payload(record)
    auth_context = getattr(request.state, "auth_context", {})
    record_audit_event(
        actor=auth_context.get("auth_subject", record.get("initiated_by", "unknown")),
        action="evidence.package.export",
        resource_type="evidence_run",
        resource_id=run_id,
        request_id=auth_context.get("request_id"),
        detail={"format": format, "raw_telemetry_included": package["governance"]["raw_telemetry_included"]},
    )
    if format == "json":
        return JSONResponse(
            content=package,
            headers={"Content-Disposition": f'attachment; filename="neraium-evidence-{run_id}.json"'},
        )
    return Response(
        content=build_evidence_package_pdf(record),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="neraium-evidence-{run_id}.pdf"'},
    )


@router.post("/evidence/runs/{run_id}/audit-tag", response_model=EvidenceRunResponse)
async def tag_evidence_run_for_audit(request: Request, run_id: RunIdPath) -> dict[str, Any]:
    if read_evidence_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Evidence run not found.")
    await require_operator_role(request)
    auth_context = getattr(request.state, "auth_context", {})
    actor = auth_context.get("auth_subject", "operator")
    try:
        updated = tag_evidence_for_audit(run_id, actor, now_iso())
    except ValueError as error:
        detail = str(error)
        if detail == "evidence_run_not_found":
            raise HTTPException(status_code=404, detail="Evidence run not found.") from None
        raise
    record_audit_event(
        actor=actor,
        action="evidence.audit.tagged",
        resource_type="evidence_run",
        resource_id=run_id,
        request_id=auth_context.get("request_id"),
        detail={"tag_count": len(updated.get("audit_tags") or [])},
    )
    return updated


@router.post("/evidence/runs/{run_id}/feedback", response_model=EvidenceRunResponse)
async def submit_evidence_feedback(request: Request, run_id: RunIdPath, payload: OperatorFeedbackRequest) -> dict[str, Any]:
    if read_evidence_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Evidence run not found.")
    await require_operator_role(request)
    auth_context = getattr(request.state, "auth_context", {})
    actor = auth_context.get("auth_subject", "operator")
    try:
        updated = record_operator_feedback(
            run_id,
            payload.category,
            payload.note,
            actor,
            now_iso(),
            outcome=payload.outcome,
            action_taken=payload.action_taken,
            intervention_at=payload.intervention_at,
            followup_at=payload.followup_at,
            idempotency_key=auth_context.get("request_id"),
        )
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
        detail={
            "category": payload.category,
            "note_present": bool(payload.note),
            "outcome": payload.outcome,
            "action_taken_present": bool(payload.action_taken),
        },
    )
    data_router.invalidate_latest_upload_cache()
    return updated


@router.post("/evidence/runs/{run_id}/status", response_model=EvidenceRunResponse)
async def update_finding_status(request: Request, run_id: RunIdPath, payload: FindingStatusRequest) -> dict[str, Any]:
    if read_evidence_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Evidence run not found.")
    await require_operator_role(request)
    auth_context = getattr(request.state, "auth_context", {})
    actor = auth_context.get("auth_subject", "operator")
    try:
        updated = record_finding_status(
            run_id,
            state=payload.state,
            actor=actor,
            recorded_at=now_iso(),
            note=payload.note,
            owner=payload.owner,
            assignee=payload.assignee,
            work_order_reference=payload.work_order_reference,
            idempotency_key=auth_context.get("request_id"),
        )
    except ValueError as error:
        detail = str(error)
        if detail == "evidence_run_not_found":
            raise HTTPException(status_code=404, detail="Evidence run not found.") from None
        if detail == "assignment_member_required":
            raise HTTPException(status_code=422, detail=detail) from None
        raise
    record_audit_event(
        actor=actor,
        action="finding.status.recorded",
        resource_type="evidence_run",
        resource_id=run_id,
        request_id=auth_context.get("request_id"),
        detail={"state": payload.state, "work_order_reference_present": bool(payload.work_order_reference)},
    )
    data_router.invalidate_latest_upload_cache()
    return updated
