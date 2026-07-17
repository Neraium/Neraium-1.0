from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.security import _strict_auth_mode, require_admin_role, require_api_access, require_same_origin_cookie_request
from app.models.api_models import (
    AuthSessionResponse,
    AuthSessionsListResponse,
    AuthUserCreateRequest,
    AuthUserResponse,
    AuthUsersListResponse,
)
from app.services.auth_store import (
    activate_user,
    authenticate_user,
    auth_summary,
    create_session,
    create_user,
    deactivate_user,
    delete_session,
    get_session_record,
    get_user_by_session,
    list_sessions,
    list_users,
    revoke_session,
    session_cookie_name,
)
from app.services.rate_limiter import consume_rate_limit, reset_rate_limit
from app.services.runtime_db import record_audit_event

router = APIRouter(tags=["auth"])
_LOGIN_IP_LIMIT = 5
_LOGIN_IP_WINDOW_SECONDS = 300
_LOGIN_EMAIL_LIMIT = 10
_LOGIN_EMAIL_WINDOW_SECONDS = 900


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class AuthSessionRevokeRequest(BaseModel):
    session_id: str | None = None
    email: str | None = None
    revoke_all_for_user: bool = False


def _session_cookie_secure(request: Request) -> bool:
    settings = getattr(request.app.state, "settings", None)
    environment = str(getattr(settings, "app_env", "")).strip().lower()
    return request.url.scheme == "https" or environment in {"prod", "production"}


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


@router.get("/auth/me")
def read_auth_me(request: Request) -> dict[str, Any]:
    session_id = request.cookies.get(session_cookie_name())
    user = get_user_by_session(session_id)
    session = get_session_record(session_id)
    return {"authenticated": bool(user), "user": user, "session": session}


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
    dependencies=[Depends(require_api_access), Depends(require_admin_role)],
)
def create_auth_user(payload: AuthUserCreateRequest, request: Request) -> AuthUserResponse:
    try:
        user = create_user(payload.email, payload.password, name=payload.name, role=payload.role)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
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
def activate_auth_user(email: str, request: Request) -> AuthUserResponse:
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
def deactivate_auth_user(email: str, request: Request) -> AuthUserResponse:
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
def read_auth_sessions(email: str | None = None, include_revoked: bool = False) -> AuthSessionsListResponse:
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
    user = authenticate_user(payload.email, payload.password)
    if not user:
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
    except ValueError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    _apply_session_cookie(response, session_id, request)
    session = get_session_record(session_id)
    _record_auth_event(
        actor=user["email"],
        action="auth.login.succeeded",
        request=request,
        detail={"client_ip": _client_ip(request), "role": user.get("role", "operator")},
    )
    return {"authenticated": True, "user": user, "session": session}


@router.post("/auth/logout", dependencies=[Depends(require_same_origin_cookie_request)])
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
