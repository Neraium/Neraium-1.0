from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.services.auth_store import (
    authenticate_user,
    create_session,
    create_user,
    delete_session,
    get_user_by_session,
    session_cookie_name,
)

router = APIRouter(tags=["auth"])


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str | None = None


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


@router.get("/auth/me")
def read_auth_me(request: Request) -> dict[str, Any]:
    session_id = request.cookies.get(session_cookie_name())
    user = get_user_by_session(session_id)
    return {"authenticated": bool(user), "user": user}


@router.post("/auth/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, request: Request, response: Response) -> dict[str, Any]:
    try:
        user = create_user(payload.email, payload.password, payload.name)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    session_id = create_session(user["email"])
    _apply_session_cookie(response, session_id, request)
    return {"authenticated": True, "user": user}


@router.post("/auth/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
    user = authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    session_id = create_session(user["email"])
    _apply_session_cookie(response, session_id, request)
    return {"authenticated": True, "user": user}


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    session_id = request.cookies.get(session_cookie_name())
    delete_session(session_id)
    _clear_session_cookie(response, request)
    return {"authenticated": False, "message": "Logged out."}

