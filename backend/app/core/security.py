import asyncio
import os
import uuid

from fastapi import HTTPException, Request

from app.services.auth_store import get_user_by_session, normalize_role, session_cookie_name
from app.services.dataset_scope import WORKSPACE_HEADER, dataset_scope_from_auth_context, set_current_dataset_scope

_PUBLIC_READONLY_PATHS = (
    "/api/health",
    "/api/ready",
    "/api/domain/mode",
    "/api/intelligence/engine-identity",
)
_ROLE_ORDER = {"viewer": 0, "operator": 1, "admin": 2}


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or str(uuid.uuid4())


def _is_public_readonly_request(request: Request) -> bool:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        return False
    path = request.url.path
    return any(path.startswith(prefix) for prefix in _PUBLIC_READONLY_PATHS)


def _strict_auth_mode(request: Request) -> bool:
    settings = getattr(request.app.state, "settings", None)
    app_env = str(getattr(settings, "app_env", os.getenv("APP_ENV", "development")) or "").strip().lower()
    return app_env in {"prod", "production"}


def _configured_token_role() -> str:
    return normalize_role(os.getenv("NERAIUM_API_TOKEN_ROLE"), "admin")


def _client_ip(request: Request) -> str:
    forwarded_for = str(request.headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
    if forwarded_for:
        return forwarded_for
    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"


def _set_auth_context(request: Request, *, subject: str, role: str, source: str, has_access_header: bool, has_access_cookie: bool, has_auth_session_cookie: bool, authenticated: bool) -> None:
    request_id = _request_id(request)
    request.state.request_id = request_id
    request.state.auth_context = {
        "auth_subject": subject,
        "auth_role": normalize_role(role, "viewer"),
        "auth_source": source,
        "has_access_header": has_access_header,
        "has_access_cookie": has_access_cookie,
        "has_auth_session_cookie": has_auth_session_cookie,
        "request_id": request_id,
        "client_ip": _client_ip(request),
        "authenticated": authenticated,
    }
    dataset_scope = dataset_scope_from_auth_context(
        request.state.auth_context,
        request.headers.get(WORKSPACE_HEADER),
    )
    request.state.dataset_scope = dataset_scope
    set_current_dataset_scope(dataset_scope)


async def require_api_access(request: Request) -> None:
    await asyncio.sleep(0)
    if _is_public_readonly_request(request):
        _set_auth_context(
            request,
            subject="readonly",
            role="viewer",
            source="public_readonly_get",
            has_access_header=False,
            has_access_cookie=False,
            has_auth_session_cookie=False,
            authenticated=False,
        )
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

    if session_user:
        _set_auth_context(
            request,
            subject=session_user.get("email", "operator"),
            role=session_user.get("role", "operator"),
            source="session",
            has_access_header=bool(access_header or bearer_header),
            has_access_cookie=bool(cookie_token),
            has_auth_session_cookie=bool(auth_session_cookie),
            authenticated=True,
        )
        return

    if configured_token and resolved_token == configured_token:
        _set_auth_context(
            request,
            subject="service-token",
            role=_configured_token_role(),
            source="service_token",
            has_access_header=bool(access_header or bearer_header),
            has_access_cookie=bool(cookie_token),
            has_auth_session_cookie=bool(auth_session_cookie),
            authenticated=True,
        )
        return

    if _strict_auth_mode(request):
        raise HTTPException(status_code=401, detail="Authentication required.")

    user = (
        request.headers.get("X-Neraium-User")
        or request.headers.get("X-Authenticated-User")
        or request.headers.get("X-Forwarded-Email")
        or "anonymous"
    )
    role = request.headers.get("X-Neraium-Role", "operator")
    _set_auth_context(
        request,
        subject=user,
        role=role,
        source="header" if resolved_token else "anonymous",
        has_access_header=bool(access_header or bearer_header),
        has_access_cookie=bool(cookie_token),
        has_auth_session_cookie=bool(auth_session_cookie),
        authenticated=False,
    )


async def _require_minimum_role(request: Request, minimum_role: str) -> None:
    if not hasattr(request.state, "auth_context"):
        await require_api_access(request)
    if not _strict_auth_mode(request):
        return
    auth_context = getattr(request.state, "auth_context", {})
    actual_role = normalize_role(auth_context.get("auth_role"), "viewer")
    if _ROLE_ORDER.get(actual_role, -1) < _ROLE_ORDER.get(minimum_role, 0):
        raise HTTPException(status_code=403, detail=f"{minimum_role.title()} access required.")


async def require_operator_role(request: Request) -> None:
    await _require_minimum_role(request, "operator")


async def require_admin_role(request: Request) -> None:
    await _require_minimum_role(request, "admin")
