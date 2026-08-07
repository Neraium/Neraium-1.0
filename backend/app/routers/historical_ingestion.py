from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path as ApiPath, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.security import require_api_access, require_operator_role
from app.services.historical_ingestion import (
    CANONICAL_UNITS,
    SUPPORTED_ROLES,
    apply_review,
    canonical_rows_page,
    read_ingestion_record,
)
from app.services.runtime_db import record_audit_event


router = APIRouter(
    prefix="/data/ingestion/v1",
    tags=["historical-ingestion"],
    dependencies=[Depends(require_api_access)],
)
DatasetIdPath = Annotated[
    str,
    ApiPath(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class SignalReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str = Field(min_length=1, max_length=128, pattern=r"^sig_[a-z0-9_]+_[a-f0-9]{8}$")
    mapping_action: Literal["accept", "choose_role", "leave_unresolved", "exclude"] | None = None
    canonical_role: str | None = Field(default=None, max_length=64)
    unit: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def validate_decision(self):
        if self.mapping_action is None and self.unit is None:
            raise ValueError("Each review decision must change a mapping or unit.")
        if self.mapping_action == "choose_role" and self.canonical_role not in SUPPORTED_ROLES:
            raise ValueError("canonical_role must be a supported role when mapping_action is choose_role.")
        if self.mapping_action != "choose_role" and self.canonical_role is not None:
            raise ValueError("canonical_role is only valid with mapping_action choose_role.")
        if self.unit is not None and self.unit not in CANONICAL_UNITS:
            raise ValueError("unit must be a supported source unit.")
        return self


class IngestionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[SignalReviewDecision] = Field(min_length=1, max_length=200)


@router.get(
    "/datasets/{dataset_id}",
    operation_id="getHistoricalIngestionProfileV1",
)
def get_historical_ingestion_profile(dataset_id: DatasetIdPath):
    record = read_ingestion_record(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Historical ingestion profile not found for this dataset.")
    return record


@router.get(
    "/datasets/{dataset_id}/canonical",
    operation_id="getHistoricalCanonicalDatasetV1",
)
def get_historical_canonical_dataset(
    dataset_id: DatasetIdPath,
    offset: int = Query(default=0, ge=0, le=10_000_000),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return canonical_rows_page(dataset_id, offset=offset, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Canonical dataset not found for this dataset.") from exc


@router.patch(
    "/datasets/{dataset_id}/review",
    operation_id="reviewHistoricalIngestionDatasetV1",
    dependencies=[Depends(require_operator_role)],
)
def review_historical_ingestion_dataset(
    request: Request,
    dataset_id: DatasetIdPath,
    payload: IngestionReviewRequest,
):
    auth_context = getattr(request.state, "auth_context", {})
    actor = str(auth_context.get("auth_subject") or "authenticated-operator")
    try:
        record = apply_review(
            dataset_id,
            decisions=[item.model_dump(exclude_none=True) for item in payload.decisions],
            actor=actor,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Historical ingestion profile not found for this dataset.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_audit_event(
        actor=actor,
        action="historical_ingestion.reviewed",
        resource_type="historical_ingestion_dataset",
        resource_id=dataset_id,
        request_id=auth_context.get("request_id"),
        detail={
            "revision": record.get("revision"),
            "dataset_identity": record.get("dataset_identity"),
            "decision_count": len(payload.decisions),
        },
    )
    return record
