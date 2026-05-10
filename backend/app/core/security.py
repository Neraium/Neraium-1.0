import os
import uuid

from fastapi import HTTPException, Request, Response


def require_api_access(request: Request, response: Response) -> None:
    configured_token = os.getenv("NERAIUM_API_TOKEN", "").strip()
    access_header = request.headers.get("X-Neraium-Access-Code", "").strip()
    bearer_header = request.headers.get("Authorization", "").strip()
    cookie_token = request.cookies.get("neraium_access_code", "").strip() if request.cookies.get("neraium_access_code") else ""
    resolved_token = access_header or cookie_token
    if not resolved_token and bearer_header.lower().startswith("bearer "):
        resolved_token = bearer_header.split(" ", 1)[1].strip()
    if configured_token and resolved_token != configured_token:
        raise HTTPException(status_code=401, detail="API access token required.")
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = request_id
    user = (
        request.headers.get("X-Neraium-User")
        or request.headers.get("X-Authenticated-User")
        or request.headers.get("X-Forwarded-Email")
        or "anonymous"
    )
    role = request.headers.get("X-Neraium-Role", "operator")
    request.state.auth_context = {
        "auth_subject": user,
        "auth_role": role,
        "auth_source": "header" if resolved_token else "anonymous",
        "has_access_header": bool(access_header or bearer_header),
        "has_access_cookie": bool(cookie_token),
        "request_id": request_id,
    }
