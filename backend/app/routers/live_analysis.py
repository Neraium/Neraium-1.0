from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.security import require_admin_role, require_api_access, require_operator_role
from app.models.api_models import (
    LiveAnalysisConfigurationCreateRequest,
    LiveAnalysisConfigurationResponse,
    LiveAnalysisConfigurationsListResponse,
    LiveAnalysisConfigurationUpdateRequest,
    LiveAnalysisHealthListResponse,
    LiveAnalysisRunResponse,
    LiveAnalysisRunsListResponse,
    LiveFindingResponse,
    LiveFindingsListResponse,
)
from app.services.live_analysis import (
    LiveAnalysisConflictError,
    LiveAnalysisNotFoundError,
    create_live_analysis_configuration,
    list_live_analysis_configurations,
    list_live_analysis_health,
    list_live_analysis_runs,
    list_live_findings,
    read_live_analysis_configuration,
    read_live_analysis_run,
    read_live_finding,
    set_live_analysis_enabled,
    trigger_live_analysis,
    update_live_analysis_configuration,
)


router = APIRouter(
    prefix="/live-analysis",
    tags=["live-analysis"],
    dependencies=[Depends(require_api_access)],
)

IdentifierPath = Annotated[
    str,
    Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
OptionalIdentifierQuery = Annotated[
    str | None,
    Query(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


@router.post(
    "/configurations",
    response_model=LiveAnalysisConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_role)],
)
def create_configuration(
    payload: LiveAnalysisConfigurationCreateRequest,
) -> dict[str, Any]:
    try:
        return create_live_analysis_configuration(payload.model_dump())
    except LiveAnalysisConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None


@router.get(
    "/configurations",
    response_model=LiveAnalysisConfigurationsListResponse,
)
def read_configurations(enabled: bool | None = None) -> dict[str, Any]:
    return {"configurations": list_live_analysis_configurations(enabled=enabled)}


@router.get(
    "/configurations/{system_id}",
    response_model=LiveAnalysisConfigurationResponse,
)
def read_configuration(system_id: IdentifierPath) -> dict[str, Any]:
    try:
        return read_live_analysis_configuration(system_id)
    except LiveAnalysisNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


@router.put(
    "/configurations/{system_id}",
    response_model=LiveAnalysisConfigurationResponse,
    dependencies=[Depends(require_admin_role)],
)
def update_configuration(
    system_id: IdentifierPath,
    payload: LiveAnalysisConfigurationUpdateRequest,
) -> dict[str, Any]:
    updates = {
        key: value
        for key, value in payload.model_dump().items()
        if key in payload.model_fields_set
    }
    invalid_null = next(
        (
            key
            for key, value in updates.items()
            if key != "approved_baseline_id" and value is None
        ),
        None,
    )
    if invalid_null:
        raise HTTPException(status_code=422, detail=f"{invalid_null} cannot be null.")
    try:
        return update_live_analysis_configuration(system_id, updates)
    except LiveAnalysisNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@router.post(
    "/configurations/{system_id}/enable",
    response_model=LiveAnalysisConfigurationResponse,
    dependencies=[Depends(require_admin_role)],
)
def enable_configuration(system_id: IdentifierPath) -> dict[str, Any]:
    try:
        return set_live_analysis_enabled(system_id, True)
    except LiveAnalysisNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


@router.post(
    "/configurations/{system_id}/disable",
    response_model=LiveAnalysisConfigurationResponse,
    dependencies=[Depends(require_admin_role)],
)
def disable_configuration(system_id: IdentifierPath) -> dict[str, Any]:
    try:
        return set_live_analysis_enabled(system_id, False)
    except LiveAnalysisNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


@router.post(
    "/systems/{system_id}/runs",
    response_model=LiveAnalysisRunResponse,
    dependencies=[Depends(require_operator_role)],
)
def trigger_manual_run(system_id: IdentifierPath) -> dict[str, Any]:
    try:
        return trigger_live_analysis(system_id)
    except LiveAnalysisNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


@router.get("/runs", response_model=LiveAnalysisRunsListResponse)
def read_runs(
    system_id: OptionalIdentifierQuery = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, Any]:
    return {"runs": list_live_analysis_runs(system_id=system_id, limit=limit)}


@router.get("/runs/{run_id}", response_model=LiveAnalysisRunResponse)
def read_run(run_id: IdentifierPath) -> dict[str, Any]:
    try:
        return read_live_analysis_run(run_id)
    except LiveAnalysisNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


@router.get("/findings", response_model=LiveFindingsListResponse)
def read_findings(
    system_id: OptionalIdentifierQuery = None,
    state: Literal["observing", "open", "resolved"] | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, Any]:
    return {
        "findings": list_live_findings(
            system_id=system_id,
            state=state,
            limit=limit,
        )
    }


@router.get("/findings/{finding_id}", response_model=LiveFindingResponse)
def read_finding(finding_id: IdentifierPath) -> dict[str, Any]:
    try:
        return read_live_finding(finding_id)
    except LiveAnalysisNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


@router.get("/health", response_model=LiveAnalysisHealthListResponse)
def read_analysis_health(
    system_id: OptionalIdentifierQuery = None,
) -> dict[str, Any]:
    return {"health": list_live_analysis_health(system_id=system_id)}
