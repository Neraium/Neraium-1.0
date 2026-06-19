from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.core.security import _strict_auth_mode
from app.services.auth_store import (
    authenticate_user,
    create_session,
    delete_session,
    get_user_by_session,
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
    email: str
    password: str


def _apply_session_cookie(response: Response, session_id: str, request: Request) -> None:
    secure = request.url.scheme == "https"
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
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


def _client_ip(request: Request) -> str:
    forwarded_for = str(request.headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
    if forwarded_for:
        return forwarded_for
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
    return {"authenticated": bool(user), "user": user}


@router.post("/auth/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    retry_after = _enforce_login_rate_limit(request, payload.email)
    if retry_after is not None:
        raise HTTPException(status_code=429, detail="Too many login attempts. Retry later.", headers={"Retry-After": str(retry_after)})
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
    session_id = create_session(user["email"])
    _apply_session_cookie(response, session_id, request)
    _record_auth_event(
        actor=user["email"],
        action="auth.login.succeeded",
        request=request,
        detail={"client_ip": _client_ip(request), "role": user.get("role", "operator")},
    )
    return {"authenticated": True, "user": user}


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
