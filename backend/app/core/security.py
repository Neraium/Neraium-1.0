import os
import uuid

from fastapi import HTTPException, Request, Response
from app.services.auth_store import get_user_by_session, session_cookie_name


def require_api_access(request: Request, response: Response) -> None:
    # Read-only frontend polling endpoints should not require the custom access
    # header. Requiring X-Neraium-Access-Code on frequent browser GETs creates
    # CORS preflights and can lock the UI in a retry loop.
    if request.method == "GET" and request.url.path in {
        "/api/health",
        "/api/ready",
        "/api/data/latest-upload",
        "/api/facility/systems",
        "/api/facility/intelligence-status",
        "/api/facility/cognition-state",
        "/latest-upload",
        "/systems",
    }:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.auth_context = {
            "auth_subject": "readonly",
            "auth_role": "viewer",
            "auth_source": "public_readonly_get",
            "has_access_header": False,
            "has_access_cookie": False,
            "has_auth_session_cookie": False,
            "request_id": request_id,
        }
        return

    configured_token = os.getenv("NERAIUM_API_TOKEN", "").strip()
    access_header = request.headers.get("X-Neraium-Access-Code", "").strip()
    bearer_header = request.headers.get("Authorization", "").strip()
    cookie_token = request.cookies.get("neraium_access_code", "").strip() if request.cookies.get("neraium_access_code") else ""
    auth_session_cookie = request.cookies.get(session_cookie_name(), "").strip() if request.cookies.get(session_cookie_name()) else ""
    session_user = get_user_by_session(auth_session_cookie)
    resolved_token = access_header or cookie_token
    if not resolved_token and bearer_header.lower().startswith("bearer "):
        resolved_token = bearer_header.split(" ", 1)[1].strip()
    if configured_token and resolved_token != configured_token and not session_user:
        raise HTTPException(status_code=401, detail="API access token required.")
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = request_id
    user = session_user.get("email") if session_user else (
        request.headers.get("X-Neraium-User")
        or request.headers.get("X-Authenticated-User")
        or request.headers.get("X-Forwarded-Email")
        or "anonymous"
    )
    role = request.headers.get("X-Neraium-Role", "operator")
    request.state.auth_context = {
        "auth_subject": user,
        "auth_role": role,
        "auth_source": "session" if session_user else ("header" if resolved_token else "anonymous"),
        "has_access_header": bool(access_header or bearer_header),
        "has_access_cookie": bool(cookie_token),
        "has_auth_session_cookie": bool(auth_session_cookie),
        "request_id": request_id,
    }
