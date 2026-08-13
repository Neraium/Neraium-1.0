from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from app.core.security import require_admin_role, require_api_access
from app.models.api_models import (
    WorkspaceCreateRequest,
    WorkspaceMemberAddRequest,
    WorkspaceMemberResponse,
    WorkspaceMembersListResponse,
    WorkspaceSummaryResponse,
    WorkspacesListResponse,
)
from app.services.auth_store import (
    add_workspace_member,
    create_workspace,
    disable_workspace_member,
    get_authorized_workspace,
    list_workspace_members,
    workflow_member,
    workspace_session_summary,
    workspace_summary,
)
from app.services.runtime_db import record_audit_event
from app.services.workspace_authorization import is_explicit_workspace_id


router = APIRouter(
    prefix="/workspaces",
    tags=["workspaces"],
    dependencies=[Depends(require_api_access)],
)
WorkspaceIdPath = Annotated[
    str,
    Path(min_length=39, max_length=39, pattern=r"^ws-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]
MemberEmailPath = Annotated[
    str,
    Path(min_length=5, max_length=320, pattern=r"^[^/\s@]+@[^/\s@]+\.[^/\s@]+$"),
]


def _actor(request: Request) -> str:
    auth_context = getattr(request.state, "auth_context", {})
    return str(auth_context.get("auth_subject") or "").strip().lower()


def _workspace_context(request: Request) -> dict[str, Any]:
    context = getattr(request.state, "workspace_context", {})
    return context if isinstance(context, dict) else {}


def _require_current_workspace(request: Request, workspace_id: str) -> dict[str, Any]:
    actor = _actor(request)
    context = _workspace_context(request)
    if context.get("workspace_id") != workspace_id or not is_explicit_workspace_id(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found.")
    workspace = get_authorized_workspace(workspace_id, actor)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


def _audit(request: Request, action: str, resource_id: str, detail: dict[str, Any]) -> None:
    record_audit_event(
        actor=_actor(request),
        action=action,
        resource_type="workspace_membership",
        resource_id=resource_id,
        request_id=request.headers.get("X-Request-Id"),
        detail=detail,
    )


@router.get("", response_model=WorkspacesListResponse)
def read_workspaces(request: Request) -> WorkspacesListResponse:
    summary = workspace_session_summary(_actor(request))
    return WorkspacesListResponse(**summary)


@router.get("/current/members", response_model=WorkspaceMembersListResponse)
def read_current_workspace_members(request: Request) -> WorkspaceMembersListResponse:
    context = _workspace_context(request)
    workspace_id = str(context.get("workspace_id") or "default")
    if is_explicit_workspace_id(workspace_id):
        members = list_workspace_members(workspace_id)
    else:
        personal_member = workflow_member(_actor(request))
        members = [personal_member] if personal_member else []
    return WorkspaceMembersListResponse(
        workspace_id=workspace_id,
        members=[WorkspaceMemberResponse(**member) for member in members],
    )


@router.post(
    "",
    response_model=WorkspaceSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_role)],
)
def create_facility_workspace(payload: WorkspaceCreateRequest, request: Request) -> WorkspaceSummaryResponse:
    current_scope = getattr(request.state, "dataset_scope", None)
    context = _workspace_context(request)
    if payload.adopt_current_scope and context.get("kind") != "personal":
        raise HTTPException(status_code=409, detail="Only a personal workspace can be adopted.")
    scope_kwargs: dict[str, str] = {}
    if payload.adopt_current_scope and current_scope is not None:
        scope_kwargs = {
            "scope_tenant_id": current_scope.tenant_id,
            "scope_user_id": current_scope.user_id,
            "scope_workspace_id": current_scope.workspace_id,
        }
    try:
        workspace = create_workspace(
            payload.display_name,
            created_by=_actor(request),
            **scope_kwargs,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        # The immutable scope tuple can be adopted only once.
        if "unique" in str(error).lower():
            raise HTTPException(status_code=409, detail="This data scope already belongs to a facility workspace.") from error
        raise
    _audit(
        request,
        "workspace.created",
        workspace["workspace_id"],
        {"display_name": workspace["display_name"], "adopted_current_scope": payload.adopt_current_scope},
    )
    return WorkspaceSummaryResponse(**workspace_summary(workspace))


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    dependencies=[Depends(require_admin_role)],
)
def add_facility_workspace_member(
    workspace_id: WorkspaceIdPath,
    payload: WorkspaceMemberAddRequest,
    request: Request,
) -> WorkspaceMemberResponse:
    _require_current_workspace(request, workspace_id)
    try:
        member = add_workspace_member(workspace_id, payload.email, added_by=_actor(request))
    except ValueError as error:
        message = str(error)
        status_code = 404 if "not found" in message.lower() else 409
        raise HTTPException(status_code=status_code, detail=message) from error
    _audit(request, "workspace.member.added", workspace_id, {"member_id": member["member_id"]})
    return WorkspaceMemberResponse(**member)


@router.post(
    "/{workspace_id}/members/{email}/disable",
    response_model=WorkspaceMemberResponse,
    dependencies=[Depends(require_admin_role)],
)
def disable_facility_workspace_member(
    workspace_id: WorkspaceIdPath,
    email: MemberEmailPath,
    request: Request,
) -> WorkspaceMemberResponse:
    _require_current_workspace(request, workspace_id)
    normalized_email = str(email).strip().lower()
    if normalized_email == _actor(request):
        raise HTTPException(status_code=409, detail="You cannot disable your current workspace membership.")
    try:
        member = disable_workspace_member(workspace_id, normalized_email)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if member is None:
        raise HTTPException(status_code=404, detail="Workspace member not found.")
    _audit(request, "workspace.member.disabled", workspace_id, {"member_id": member["member_id"]})
    return WorkspaceMemberResponse(**member)
