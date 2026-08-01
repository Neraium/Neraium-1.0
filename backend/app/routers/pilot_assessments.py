from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Path, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.security import require_api_access, require_operator_role
from app.services.pilot_assessment import (
    AssessmentError,
    analyze_assessment,
    append_feedback,
    create_assessment,
    exact_records_path,
    list_assessments,
    read_assessment,
    report_html,
    reveal_event,
    update_mapping,
)
from app.services.runtime_db import record_audit_event


router = APIRouter(
    tags=["pilot-assessments"],
    dependencies=[Depends(require_api_access), Depends(require_operator_role)],
)
AssessmentIdPath = Annotated[
    str,
    Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
]
RelationshipIdPath = Annotated[
    str,
    Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventRevealRequest(StrictRequest):
    event_timestamp: str = Field(min_length=1, max_length=80)
    event_label: str = Field(default="Known event", min_length=1, max_length=160)
    repair_timestamp: str | None = Field(default=None, max_length=80)


class AssessmentFeedbackRequest(StrictRequest):
    category: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=4000)
    finding_id: str | None = Field(default=None, max_length=128)


def _actor(request: Request) -> str:
    return str(getattr(request.state, "auth_context", {}).get("auth_subject") or "operator")


def _is_admin(request: Request) -> bool:
    return str(getattr(request.state, "auth_context", {}).get("auth_role") or "").lower() == "admin"


def _require_owner(request: Request, assessment_id: str) -> dict[str, Any]:
    record = read_assessment(assessment_id)
    if record is None or (not _is_admin(request) and str(record.get("created_by") or "") != _actor(request)):
        raise HTTPException(status_code=404, detail="Historical assessment not found.")
    return record


def _translate_error(error: AssessmentError) -> HTTPException:
    detail = str(error)
    status = 400
    if detail in {"assessment_not_found", "relationship_not_found", "exact_records_not_found"}:
        status = 404
    elif detail in {
        "mapping_locked_after_analysis",
        "assessment_not_ready",
        "mapping_incomplete",
        "analysis_must_finish_before_event_reveal",
        "analysis_must_finish_before_feedback",
    }:
        status = 409
    elif detail == "dataset_too_large":
        status = 413
    messages = {
        "assessment_not_found": "Historical assessment not found.",
        "relationship_not_found": "Relationship evidence not found.",
        "exact_records_not_found": "Exact evidence records not found.",
        "mapping_locked_after_analysis": "Signal mapping is locked after analysis starts.",
        "assessment_not_ready": "The assessment is not ready to analyze.",
        "mapping_incomplete": "Complete the timestamp and signal mapping before analysis.",
        "analysis_must_finish_before_event_reveal": "The event timestamp can only be entered after analysis finishes.",
        "analysis_must_finish_before_feedback": "Engineer feedback can only be recorded after analysis finishes.",
        "event_timestamp_timezone_required": "The known event timestamp must include a timezone.",
        "repair_timestamp_timezone_required": "The repair timestamp must include a timezone.",
        "invalid_event_timestamp": "The known event timestamp is invalid.",
        "invalid_repair_timestamp": "The repair timestamp is invalid.",
        "invalid_feedback_category": "The engineer feedback category is invalid.",
        "dataset_too_large": "One of the datasets exceeds the configured upload limit.",
        "empty_dataset": "Both baseline and comparison files must contain data.",
        "dataset_has_no_rows": "Both files must contain at least one data row.",
        "dataset_has_no_columns": "Both files must contain column headers.",
        "csv_parse_failed": "One of the files could not be parsed as CSV telemetry.",
    }
    return HTTPException(status_code=status, detail=messages.get(detail, detail.replace("_", " ").capitalize()))


@router.get("/pilot-assessments")
def get_assessments(request: Request, limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    return {"assessments": list_assessments(limit, actor=None if _is_admin(request) else _actor(request))}


@router.get("/pilot-assessments/{assessment_id}")
def get_assessment(request: Request, assessment_id: AssessmentIdPath) -> dict[str, Any]:
    try:
        record = _require_owner(request, assessment_id)
    except AssessmentError as error:
        raise _translate_error(error) from None
    if record is None:
        raise HTTPException(status_code=404, detail="Historical assessment not found.")
    return record


@router.post("/pilot-assessments/intake", status_code=201)
async def intake_assessment(
    request: Request,
    baseline_file: UploadFile = File(...),
    comparison_file: UploadFile = File(...),
) -> dict[str, Any]:
    settings = request.app.state.settings
    baseline_bytes = await baseline_file.read(settings.max_upload_size_bytes + 1)
    comparison_bytes = await comparison_file.read(settings.max_upload_size_bytes + 1)
    try:
        record = create_assessment(
            baseline_filename=baseline_file.filename or "baseline.csv",
            baseline_bytes=baseline_bytes,
            comparison_filename=comparison_file.filename or "comparison.csv",
            comparison_bytes=comparison_bytes,
            actor=_actor(request),
        )
    except AssessmentError as error:
        raise _translate_error(error) from None
    record_audit_event(
        actor=_actor(request),
        action="pilot_assessment.intake.created",
        resource_type="pilot_assessment",
        resource_id=record["assessment_id"],
        request_id=getattr(request.state, "request_id", None),
        detail={
            "baseline_sha256": record["datasets"]["baseline"]["sha256"],
            "comparison_sha256": record["datasets"]["comparison"]["sha256"],
        },
    )
    return record


@router.put("/pilot-assessments/{assessment_id}/mapping")
def save_mapping(
    request: Request,
    assessment_id: AssessmentIdPath,
    mapping: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    _require_owner(request, assessment_id)
    try:
        record = update_mapping(assessment_id, mapping)
    except AssessmentError as error:
        raise _translate_error(error) from None
    record_audit_event(
        actor=_actor(request),
        action="pilot_assessment.mapping.saved",
        resource_type="pilot_assessment",
        resource_id=assessment_id,
        request_id=getattr(request.state, "request_id", None),
        detail={"ready": record["mapping_validation"]["ready"], "mapped_signals": len(record["mapping"]["signals"])},
    )
    return record


@router.post("/pilot-assessments/{assessment_id}/analyze")
def run_analysis(request: Request, assessment_id: AssessmentIdPath) -> dict[str, Any]:
    _require_owner(request, assessment_id)
    try:
        record = analyze_assessment(assessment_id, actor=_actor(request))
    except AssessmentError as error:
        raise _translate_error(error) from None
    record_audit_event(
        actor=_actor(request),
        action="pilot_assessment.analysis.completed",
        resource_type="pilot_assessment",
        resource_id=assessment_id,
        request_id=getattr(request.state, "request_id", None),
        detail={
            "quality_decision": record["quality_gate"]["decision"],
            "finding_count": record["analysis"]["finding_count"],
            "event_timestamp_used": False,
        },
    )
    return record


@router.post("/pilot-assessments/{assessment_id}/event")
def add_known_event(
    request: Request,
    assessment_id: AssessmentIdPath,
    payload: EventRevealRequest,
) -> dict[str, Any]:
    _require_owner(request, assessment_id)
    try:
        record = reveal_event(
            assessment_id,
            event_timestamp=payload.event_timestamp,
            event_label=payload.event_label,
            repair_timestamp=payload.repair_timestamp,
            actor=_actor(request),
        )
    except AssessmentError as error:
        raise _translate_error(error) from None
    record_audit_event(
        actor=_actor(request),
        action="pilot_assessment.event.revealed",
        resource_type="pilot_assessment",
        resource_id=assessment_id,
        request_id=getattr(request.state, "request_id", None),
        detail={
            "event_timestamp": payload.event_timestamp,
            "analysis_was_blinded": record["event_backtest"]["analysis_was_blinded"],
        },
    )
    return record


@router.post("/pilot-assessments/{assessment_id}/feedback", status_code=201)
def record_feedback(
    request: Request,
    assessment_id: AssessmentIdPath,
    payload: AssessmentFeedbackRequest,
) -> dict[str, Any]:
    _require_owner(request, assessment_id)
    try:
        record = append_feedback(
            assessment_id,
            category=payload.category,
            note=payload.note,
            finding_id=payload.finding_id,
            actor=_actor(request),
        )
    except AssessmentError as error:
        raise _translate_error(error) from None
    record_audit_event(
        actor=_actor(request),
        action="pilot_assessment.feedback.appended",
        resource_type="pilot_assessment",
        resource_id=assessment_id,
        request_id=getattr(request.state, "request_id", None),
        detail={"category": payload.category, "finding_id": payload.finding_id},
    )
    return record


@router.get("/pilot-assessments/{assessment_id}/records/{relationship_id}.csv")
def download_exact_records(
    request: Request,
    assessment_id: AssessmentIdPath,
    relationship_id: RelationshipIdPath,
) -> FileResponse:
    _require_owner(request, assessment_id)
    try:
        path = exact_records_path(assessment_id, relationship_id)
    except AssessmentError as error:
        raise _translate_error(error) from None
    record_audit_event(
        actor=_actor(request),
        action="pilot_assessment.records.exported",
        resource_type="pilot_assessment",
        resource_id=assessment_id,
        request_id=getattr(request.state, "request_id", None),
        detail={"relationship_id": relationship_id},
    )
    return FileResponse(path, media_type="text/csv", filename=f"{assessment_id}-{relationship_id}-records.csv")


@router.get("/pilot-assessments/{assessment_id}/report.html")
def download_report(request: Request, assessment_id: AssessmentIdPath) -> HTMLResponse:
    _require_owner(request, assessment_id)
    try:
        body = report_html(assessment_id)
    except AssessmentError as error:
        raise _translate_error(error) from None
    record_audit_event(
        actor=_actor(request),
        action="pilot_assessment.report.exported",
        resource_type="pilot_assessment",
        resource_id=assessment_id,
        request_id=getattr(request.state, "request_id", None),
        detail={"format": "html"},
    )
    return HTMLResponse(
        body,
        headers={"Content-Disposition": f'attachment; filename="neraium-{assessment_id}-report.html"'},
    )
