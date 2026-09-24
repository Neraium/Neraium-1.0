"""HTTP-only security controls; never transform source or analytical payloads."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders, URL
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.auth_store import session_cookie_name

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
_MULTIPART_PATHS = {"/api/data/upload", "/api/connectors/csv/upload"}
_MULTIPART_OVERHEAD = 1024 * 1024


def security_headers(scope: Scope) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": "default-src 'self'",
    }
    if scope.get("scheme") == "https":
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if scope.get("path", "").startswith("/api/") or scope.get("path") in {"/latest-upload", "/systems"}:
        headers["Cache-Control"] = "no-store"
    return headers


class HttpBoundaryMiddleware:
    def __init__(self, app: ASGIApp, *, settings) -> None:
        self.app = app
        self.settings = settings

    def _trusted_origin(self, origin: str, scope: Scope) -> bool:
        # Reject opaque/malformed origins, credentials and non-origin suffixes.
        try:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                return False
            if parsed.path or parsed.query or parsed.fragment:
                return False
            parsed.port
        except ValueError:
            return False
        same_origin = str(URL(scope=scope)).split("/", 3)[:3]
        if origin == "/".join(same_origin) or origin in self.settings.cors_origins:
            return True
        pattern = self.settings.cors_origin_regex
        return bool(pattern and re.fullmatch(pattern, origin))

    def _unsafe_cookie_origin(self, scope: Scope, headers: Headers) -> bool:
        if scope["method"] not in _MUTATING:
            return False
        cookies = Request(scope).cookies
        cookie_auth = bool(cookies.get(session_cookie_name()) or cookies.get("neraium_access_code"))
        login = scope["path"] == "/api/auth/login"
        if not cookie_auth and not login:
            return False
        origin = headers.get("origin")
        if origin is not None:
            return not self._trusted_origin(origin, scope)
        referer = headers.get("referer")
        if referer:
            try:
                parsed = urlsplit(referer)
                if parsed.username or parsed.password:
                    return True
                origin = f"{parsed.scheme}://{parsed.netloc}"
            except ValueError:
                return True
            return not self._trusted_origin(origin, scope)
        if headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
            return True
        # Browsers send Origin or Referer for cookie writes. Service clients
        # without ambient cookies keep their existing header-auth workflow.
        return cookie_auth and self.settings.app_env in {"staging", "prod", "production"}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def secure_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = MutableHeaders(scope=message)
                for key, value in security_headers(scope).items():
                    if key == "Cache-Control":
                        headers[key] = value
                    else:
                        headers.setdefault(key, value)
            await send(message)

        async def reject(status: int, message: str, kind: str) -> None:
            await JSONResponse(status_code=status, content={"detail": message, "message": message, "error_type": kind})(scope, receive, secure_send)

        headers = Headers(scope=scope)
        if self._unsafe_cookie_origin(scope, headers):
            await reject(403, "Untrusted request origin.", "untrusted_origin")
            return
        limit = 1_048_576
        if scope["path"] == "/api/telemetry/ingest":
            limit = self.settings.telemetry_max_request_size_bytes
        elif scope["path"] in _MULTIPART_PATHS:
            # The endpoint still enforces the file-only cap. Bound aggregate
            # multipart input too, before parsing/spooling consumes excess data.
            limit = self.settings.max_upload_size_bytes + _MULTIPART_OVERHEAD
        lengths = headers.getlist("content-length")
        if len(lengths) > 1 or (lengths and not re.fullmatch(r"[0-9]+", lengths[0])):
            await reject(400, "Invalid Content-Length header.", "invalid_header")
            return
        if lengths and (len(lengths[0]) > 20 or int(lengths[0]) > limit):
            await reject(413, "Request payload exceeds the configured limit.", "payload_too_large")
            return
        received = 0

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # A Starlette HTTPException lets multipart parsing close its
                    # temporary files. Never pass the excess chunk to a parser.
                    raise HTTPException(413, "Request payload exceeds the configured limit.")
            return message

        try:
            await self.app(scope, bounded_receive, secure_send)
        except HTTPException as error:
            if response_started or error.status_code != 413:
                raise
            await reject(413, "Request payload exceeds the configured limit.", "payload_too_large")
