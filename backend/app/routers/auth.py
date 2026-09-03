from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import StringConstraints, model_validator

from app.contracts import ContractModel, EmailAddress, SecretText

from app.core.security import _strict_auth_mode, require_admin_role, require_api_access
from app.models.api_models import (
    AccountRequestApprovalRequest,
    AccountRequestCreateRequest,
    AccountRequestResponse,
    AccountRequestsListResponse,
    AuthSessionResponse,
    AuthSessionsListResponse,
    AuthUserCreateRequest,
    AuthUserResponse,
    AuthUsersListResponse,
)
from app.services.auth_store import (
    approve_account_request,
    activate_user,
    authenticate_user,
    auth_summary,
    create_account_request,
    create_session,
    create_user,
    deactivate_user,
    delete_session,
    get_session_record,
    get_authorized_workspace,
    get_user_by_session,
    list_account_requests,
    list_sessions,
    list_users,
    pending_account_request_matches,
    reject_account_request,
    revoke_session,
    session_cookie_name,
    workspace_session_summary,
)
from app.services.rate_limiter import consume_rate_limit, reset_rate_limit
from app.services.runtime_db import record_audit_event

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)
_LOGIN_IP_LIMIT = 5
_LOGIN_IP_WINDOW_SECONDS = 300
_LOGIN_EMAIL_LIMIT = 10
_LOGIN_EMAIL_WINDOW_SECONDS = 900
_ACCOUNT_REQUEST_IP_LIMIT = 3
_ACCOUNT_REQUEST_IP_WINDOW_SECONDS = 3600
_ACCOUNT_REQUEST_EMAIL_LIMIT = 3
_ACCOUNT_REQUEST_EMAIL_WINDOW_SECONDS = 86400


class LoginRequest(ContractModel):
    email: EmailAddress
    password: SecretText


class AuthSessionRevokeRequest(ContractModel):
    session_id: Annotated[str, StringConstraints(min_length=16, max_length=256)] | None = None
    email: EmailAddress | None = None
    revoke_all_for_user: bool = False

    @model_validator(mode="after")
    def target_is_unambiguous(self):
        if bool(self.session_id) == bool(self.email):
            raise ValueError("Provide exactly one of session_id or email.")
        if self.email and not self.revoke_all_for_user:
            raise ValueError("revoke_all_for_user must be true when revoking by email.")
        if self.session_id and self.revoke_all_for_user:
            raise ValueError("revoke_all_for_user is only valid with email.")
        return self


EmailPath = Annotated[str, Path(min_length=5, max_length=320, pattern=r"^[^/\s@]+@[^/\s@]+\.[^/\s@]+$")]
AccountRequestIdPath = Annotated[
    str,
    Path(min_length=39, max_length=39, pattern=r"^ar-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]


def _session_cookie_secure(request: Request) -> bool:
    settings = getattr(request.app.state, "settings", None)
    app_env = str(getattr(settings, "app_env", "") or "").strip().lower()
    forwarded_scheme = str(request.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
    return app_env in {"prod", "production"} or request.url.scheme == "https" or forwarded_scheme == "https"


def _apply_session_cookie(response: Response, session_id: str, request: Request) -> None:
    secure = _session_cookie_secure(request)
    expires_at = datetime.now(timezone.utc) + timedelta(days=14)
    response.set_cookie(
        key=session_cookie_name(),
        value=session_id,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        expires=expires_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
    )


def _clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=session_cookie_name(),
        httponly=True,
        secure=_session_cookie_secure(request),
        samesite="lax",
        path="/",
    )


def _client_ip(request: Request) -> str:
    # Trusted proxy middleware may normalize this value. Reading the raw
    # forwarding header here would let direct clients choose their rate-limit
    # bucket and audit identity.
    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"


def _record_auth_event(*, actor: str, action: str, request: Request, detail: dict[str, Any]) -> None:
    record_audit_event(
        actor=actor,
        action=action,
        resource_type="auth_session",
        resource_id=None,
        request_id=request.headers.get("X-Request-Id"),
        detail=detail,
    )


def _record_admin_auth_event(*, actor: str, action: str, request: Request, resource_id: str | None, detail: dict[str, Any]) -> None:
    record_audit_event(
        actor=actor,
        action=action,
        resource_type="auth_admin",
        resource_id=resource_id,
        request_id=request.headers.get("X-Request-Id"),
        detail=detail,
    )


def _request_actor(request: Request) -> str:
    auth_context = getattr(request.state, "auth_context", {})
    return str(auth_context.get("auth_subject") or "admin")


def _enforce_login_rate_limit(request: Request, email: str) -> int | None:
    if not _strict_auth_mode(request):
        return None
    client_ip = _client_ip(request)
    allowed, retry_after = consume_rate_limit(
        "auth.login.ip",
        client_ip,
        limit=_LOGIN_IP_LIMIT,
        window_seconds=_LOGIN_IP_WINDOW_SECONDS,
    )
    if not allowed:
        return retry_after
    allowed, retry_after = consume_rate_limit(
        "auth.login.email",
        str(email or "").strip().lower(),
        limit=_LOGIN_EMAIL_LIMIT,
        window_seconds=_LOGIN_EMAIL_WINDOW_SECONDS,
    )
    if not allowed:
        return retry_after
    return None


def _reset_login_rate_limit(request: Request, email: str) -> None:
    client_ip = _client_ip(request)
    reset_rate_limit("auth.login.ip", client_ip)
    reset_rate_limit("auth.login.email", str(email or "").strip().lower())


def _enforce_account_request_rate_limit(request: Request, email: str) -> int | None:
    if not _strict_auth_mode(request):
        return None
    allowed, retry_after = consume_rate_limit(
        "auth.account_request.ip", _client_ip(request),
        limit=_ACCOUNT_REQUEST_IP_LIMIT, window_seconds=_ACCOUNT_REQUEST_IP_WINDOW_SECONDS,
    )
    if not allowed:
        return retry_after
    allowed, retry_after = consume_rate_limit(
        "auth.account_request.email", str(email or "").strip().lower(),
        limit=_ACCOUNT_REQUEST_EMAIL_LIMIT, window_seconds=_ACCOUNT_REQUEST_EMAIL_WINDOW_SECONDS,
    )
    return None if allowed else retry_after


def _raise_auth_store_unavailable(operation: str, request: Request, error: Exception) -> None:
    logger.exception(
        "auth_store_request_failed",
        extra={
            "event": "auth_store_request_failed",
            "operation": operation,
            "request_id": getattr(request.state, "request_id", None),
        },
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication service temporarily unavailable.",
    ) from error


@router.get("/auth/me")
def read_auth_me(request: Request) -> dict[str, Any]:
    session_id = request.cookies.get(session_cookie_name())
    if not session_id:
        return {"authenticated": False, "user": None, "session": None}
    try:
        user = get_user_by_session(session_id)
        session = get_session_record(session_id)
    except Exception as error:
        _raise_auth_store_unavailable("verify_session", request, error)
    if not user:
        return {"authenticated": False, "user": None, "session": None}
    return {
        "authenticated": True,
        "user": user,
        "session": session,
        **workspace_session_summary(user["email"]),
    }


@router.post(
    "/auth/account-requests",
    response_model=AccountRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_account_request(
    payload: AccountRequestCreateRequest, request: Request
) -> AccountRequestResponse:
    retry_after = _enforce_account_request_rate_limit(request, payload.email)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many account requests. Wait and try again.",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        account_request = create_account_request(
            payload.email,
            payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
        )
    except ValueError as error:
        message = str(error)
        status_code = 409 if "already exists" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from error
    _record_auth_event(
        actor=account_request["email"],
        action="auth.account_request.created",
        request=request,
        detail={"client_ip": _client_ip(request), "request_id": account_request["request_id"]},
    )
    return AccountRequestResponse(**account_request)


@router.get(
    "/auth/account-requests",
    response_model=AccountRequestsListResponse,
    dependencies=[Depends(require_api_access), Depends(require_admin_role)],
)
def read_account_requests() -> AccountRequestsListResponse:
    return AccountRequestsListResponse(
        requests=[AccountRequestResponse(**item) for item in list_account_requests(status="pending")]
    )


@router.post(
    "/auth/account-requests/{request_id}/approve",
    response_model=AccountRequestResponse,
    dependencies=[Depends(require_api_access), Depends(require_admin_role)],
)
def approve_employee_account_request(
    request_id: AccountRequestIdPath,
    payload: AccountRequestApprovalRequest,
    request: Request,
) -> AccountRequestResponse:
    actor = _request_actor(request)
    if not get_authorized_workspace(payload.workspace_id, actor):
        raise HTTPException(status_code=404, detail="Workspace not found.")
    try:
        result = approve_account_request(
            request_id,
            role=payload.role,
            workspace_id=payload.workspace_id,
            reviewed_by=actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not result:
        raise HTTPException(status_code=404, detail="Account request not found.")
    if result["status"] != "approved":
        raise HTTPException(status_code=409, detail="Account request has already been reviewed.")
    _record_admin_auth_event(
        actor=actor,
        action="auth.account_request.approved",
        request=request,
        resource_id=request_id,
        detail={"email": result["email"], "role": payload.role, "workspace_id": payload.workspace_id},
    )
    return AccountRequestResponse(**result)


@router.post(
    "/auth/account-requests/{request_id}/reject",
    response_model=AccountRequestResponse,
    dependencies=[Depends(require_api_access), Depends(require_admin_role)],
)
def reject_employee_account_request(
    request_id: AccountRequestIdPath, request: Request
) -> AccountRequestResponse:
    actor = _request_actor(request)
    result = reject_account_request(request_id, reviewed_by=actor)
    if not result:
        raise HTTPException(status_code=404, detail="Account request not found.")
    if result["status"] != "rejected":
        raise HTTPException(status_code=409, detail="Account request has already been reviewed.")
    _record_admin_auth_event(
        actor=actor,
        action="auth.account_request.rejected",
        request=request,
        resource_id=request_id,
        detail={"email": result["email"]},
    )
    return AccountRequestResponse(**result)


@router.get(
    "/auth/users",
    response_model=AuthUsersListResponse,
    dependencies=[Depends(require_api_access), Depends(require_admin_role)],
)
def read_auth_users(include_inactive: bool = True) -> AuthUsersListResponse:
    return AuthUsersListResponse(users=[AuthUserResponse(**user) for user in list_users(include_inactive=include_inactive)])


@router.post(
    "/auth/users",
    response_model=AuthUserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_access), Depends(require_admin_role)],
)
def create_auth_user(payload: AuthUserCreateRequest, request: Request) -> AuthUserResponse:
    try:
        user = create_user(payload.email, payload.password, name=payload.name, role=payload.role)
    except ValueError as error:
        status_code = 409 if "already exists" in str(error).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(error)) from error
    _record_admin_auth_event(
        actor=_request_actor(request),
        action="auth.user.created",
        request=request,
        resource_id=user["email"],
        detail={"role": user.get("role"), "client_ip": _client_ip(request)},
    )
    return AuthUserResponse(**user)


@router.post(
    "/auth/users/{email}/activate",
    response_model=AuthUserResponse,
    dependencies=[Depends(require_api_access), Depends(require_admin_role)],
)
def activate_auth_user(email: EmailPath, request: Request) -> AuthUserResponse:
    user = activate_user(email)
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")
    _record_admin_auth_event(
        actor=_request_actor(request),
        action="auth.user.activated",
        request=request,
        resource_id=user["email"],
        detail={"client_ip": _client_ip(request)},
    )
    return AuthUserResponse(**user)


@router.post(
    "/auth/users/{email}/deactivate",
    response_model=AuthUserResponse,
    dependencies=[Depends(require_api_access), Depends(require_admin_role)],
)
def deactivate_auth_user(email: EmailPath, request: Request) -> AuthUserResponse:
    user = deactivate_user(email)
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")
    _record_admin_auth_event(
        actor=_request_actor(request),
        action="auth.user.deactivated",
        request=request,
        resource_id=user["email"],
        detail={"client_ip": _client_ip(request)},
    )
    return AuthUserResponse(**user)


@router.get(
    "/auth/sessions",
    response_model=AuthSessionsListResponse,
    dependencies=[Depends(require_api_access), Depends(require_admin_role)],
)
def read_auth_sessions(email: EmailAddress | None = Query(default=None), include_revoked: bool = Query(False)) -> AuthSessionsListResponse:
    sessions = list_sessions(email=email, include_revoked=include_revoked)
    return AuthSessionsListResponse(
        sessions=[AuthSessionResponse(**session) for session in sessions],
        summary=auth_summary(),
    )


@router.post(
    "/auth/sessions/revoke",
    dependencies=[Depends(require_api_access), Depends(require_admin_role)],
)
def revoke_auth_sessions(payload: AuthSessionRevokeRequest, request: Request) -> dict[str, Any]:
    revoked = revoke_session(
        session_id=payload.session_id,
        email=payload.email,
        revoke_all_for_user=payload.revoke_all_for_user,
    )
    if revoked <= 0:
        raise HTTPException(status_code=404, detail="No matching active session was found.")
    _record_admin_auth_event(
        actor=_request_actor(request),
        action="auth.session.revoked",
        request=request,
        resource_id=payload.session_id or str(payload.email or ""),
        detail={
            "client_ip": _client_ip(request),
            "revoked": revoked,
            "revoke_all_for_user": payload.revoke_all_for_user,
        },
    )
    return {"revoked": revoked, "summary": auth_summary()}


@router.post("/auth/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    retry_after = _enforce_login_rate_limit(request, payload.email)
    if retry_after is not None:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait a few minutes and try again.", headers={"Retry-After": str(retry_after)})
    try:
        user = authenticate_user(payload.email, payload.password)
    except Exception as error:
        _raise_auth_store_unavailable("authenticate_user", request, error)
    if not user:
        try:
            awaiting_approval = pending_account_request_matches(payload.email, payload.password)
        except Exception as error:
            _raise_auth_store_unavailable("verify_pending_account_request", request, error)
        if awaiting_approval:
            raise HTTPException(
                status_code=403,
                detail="Your account is awaiting administrator approval.",
            )
        _record_auth_event(
            actor=str(payload.email or "").strip().lower() or "unknown",
            action="auth.login.failed",
            request=request,
            detail={"client_ip": _client_ip(request)},
        )
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    _reset_login_rate_limit(request, payload.email)
    try:
        session_id = create_session(user["email"])
        session = get_session_record(session_id)
    except ValueError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except Exception as error:
        _raise_auth_store_unavailable("create_session", request, error)
    _apply_session_cookie(response, session_id, request)
    _record_auth_event(
        actor=user["email"],
        action="auth.login.succeeded",
        request=request,
        detail={"client_ip": _client_ip(request), "role": user.get("role", "operator")},
    )
    return {
        "authenticated": True,
        "user": user,
        "session": session,
        **workspace_session_summary(user["email"]),
    }


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    session_id = request.cookies.get(session_cookie_name())
    user = get_user_by_session(session_id)
    delete_session(session_id)
    _clear_session_cookie(response, request)
    if user:
        _record_auth_event(
            actor=user.get("email", "operator"),
            action="auth.logout",
            request=request,
            detail={"client_ip": _client_ip(request), "role": user.get("role", "operator")},
        )
    return {"authenticated": False, "message": "Logged out."}
