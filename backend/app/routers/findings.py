from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from app.core.security import require_api_access, require_operator_role
from app.models.api_models import (
    FindingActivityResponse,
    FindingCaseResponse,
    FindingCasesListResponse,
    FindingFeedbackRequest,
    FindingResolutionRequest,
    FindingWorkflowUpdateRequest,
)
from app.services.evidence_store import validation_outcome_for_category
from app.services.finding_workflow import (
    FindingNotFoundError,
    FindingWorkflowConflictError,
    finding_activity,
    list_finding_cases,
    read_finding_case,
    record_finding_feedback,
    resolve_finding,
    update_finding_workflow,
)
from app.services.runtime_db import record_audit_event


router = APIRouter(
    prefix="/findings",
    tags=["findings"],
    dependencies=[Depends(require_api_access)],
)
FindingIdPath = Annotated[
    str,
    Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


def _actor(request: Request) -> tuple[str, str | None]:
    context = getattr(request.state, "auth_context", {})
    return str(context.get("auth_subject") or "operator"), context.get("request_id")


def _raise_workflow_error(error: Exception) -> None:
    if isinstance(error, FindingNotFoundError):
        raise HTTPException(status_code=404, detail="Finding not found.") from None
    if isinstance(error, FindingWorkflowConflictError):
        raise HTTPException(
            status_code=409,
            detail={"error": error.reason, "current_version": error.current_version},
        ) from None
    raise error


@router.get("", response_model=FindingCasesListResponse)
def get_findings(
    source_kind: Literal["evidence_run", "live_finding"] | None = None,
    source_run_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    status: Literal["open", "acknowledged", "investigating", "monitoring", "resolved", "dismissed"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> dict[str, Any]:
    return list_finding_cases(
        source_kind=source_kind,
        source_run_id=source_run_id,
        workflow_status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/{finding_id}", response_model=FindingCaseResponse)
def get_finding(finding_id: FindingIdPath) -> dict[str, Any]:
    try:
        return read_finding_case(finding_id)
    except (FindingNotFoundError, FindingWorkflowConflictError) as error:
        _raise_workflow_error(error)
        raise AssertionError("unreachable")


@router.get("/{finding_id}/activity", response_model=FindingActivityResponse)
def get_finding_activity(finding_id: FindingIdPath) -> dict[str, Any]:
    try:
        return finding_activity(finding_id)
    except (FindingNotFoundError, FindingWorkflowConflictError) as error:
        _raise_workflow_error(error)
        raise AssertionError("unreachable")


@router.patch(
    "/{finding_id}/workflow",
    response_model=FindingCaseResponse,
    dependencies=[Depends(require_operator_role)],
)
def patch_finding_workflow(
    request: Request, finding_id: FindingIdPath, payload: FindingWorkflowUpdateRequest
) -> dict[str, Any]:
    actor, request_id = _actor(request)
    fields = payload.model_fields_set - {"expected_version", "idempotency_key"}
    changes: dict[str, Any] = {}
    dumped = payload.model_dump()
    for field in fields:
        value = dumped[field]
        if field == "status" and value is None:
            raise HTTPException(status_code=422, detail="status cannot be null.")
        changes[field] = value
    if not changes:
        raise HTTPException(status_code=422, detail="At least one workflow field is required.")
    try:
        updated = update_finding_workflow(
            finding_id,
            changes=changes,
            expected_version=payload.expected_version,
            actor=actor,
            idempotency_key=payload.idempotency_key,
        )
    except (FindingNotFoundError, FindingWorkflowConflictError) as error:
        _raise_workflow_error(error)
        raise AssertionError("unreachable")
    record_audit_event(
        actor=actor,
        action="finding.workflow.updated",
        resource_type="finding",
        resource_id=finding_id,
        request_id=request_id,
        detail={"fields": sorted(changes), "version": updated["workflow"]["version"]},
    )
    return updated


@router.post(
    "/{finding_id}/feedback",
    response_model=FindingCaseResponse,
    dependencies=[Depends(require_operator_role)],
)
def submit_finding_feedback(
    request: Request, finding_id: FindingIdPath, payload: FindingFeedbackRequest
) -> dict[str, Any]:
    actor, request_id = _actor(request)
    feedback = {
        "category": payload.category,
        "note": payload.note,
        "outcome": payload.outcome or validation_outcome_for_category(payload.category),
        "action_taken": payload.action_taken,
        "intervention_at": payload.intervention_at,
        "followup_at": payload.followup_at,
    }
    try:
        updated = record_finding_feedback(
            finding_id,
            feedback=feedback,
            expected_version=payload.expected_version,
            actor=actor,
            idempotency_key=payload.idempotency_key,
        )
    except (FindingNotFoundError, FindingWorkflowConflictError) as error:
        _raise_workflow_error(error)
        raise AssertionError("unreachable")
    record_audit_event(
        actor=actor,
        action="finding.feedback.recorded",
        resource_type="finding",
        resource_id=finding_id,
        request_id=request_id,
        detail={"category": payload.category, "version": updated["workflow"]["version"]},
    )
    return updated


@router.post(
    "/{finding_id}/resolution",
    response_model=FindingCaseResponse,
    dependencies=[Depends(require_operator_role)],
)
def submit_finding_resolution(
    request: Request, finding_id: FindingIdPath, payload: FindingResolutionRequest
) -> dict[str, Any]:
    actor, request_id = _actor(request)
    try:
        updated = resolve_finding(
            finding_id,
            outcome=payload.outcome,
            note=payload.note,
            expected_version=payload.expected_version,
            actor=actor,
            idempotency_key=payload.idempotency_key,
        )
    except (FindingNotFoundError, FindingWorkflowConflictError) as error:
        _raise_workflow_error(error)
        raise AssertionError("unreachable")
    record_audit_event(
        actor=actor,
        action="finding.resolution.recorded",
        resource_type="finding",
        resource_id=finding_id,
        request_id=request_id,
        detail={"outcome": payload.outcome, "version": updated["workflow"]["version"]},
    )
    return updated
