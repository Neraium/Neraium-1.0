import secrets
import logging

from fastapi import Cookie, Header, HTTPException, Request, status

from app.core.config import get_settings

ACCESS_CODE_HEADER = "X-Neraium-Access-Code"
ACCESS_CODE_COOKIE = "neraium_access_code"
logger = logging.getLogger(__name__)


def require_api_access(
    request: Request,
    x_neraium_access_code: str | None = Header(default=None),
    neraium_access_code: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    if request.method == "OPTIONS":
        return

    settings = getattr(request.app.state, "settings", None) or get_settings()
    auth_scheme, bearer_access_code = parse_authorization_access_code(authorization)
    supplied_access_code = x_neraium_access_code or bearer_access_code or neraium_access_code
    log_auth_debug(
        request=request,
        auth_scheme=auth_scheme,
        has_header=bool(x_neraium_access_code),
        has_cookie=bool(neraium_access_code),
        has_authorization=bool(authorization),
        failure_reason=None,
    )
    if settings.app_env != "production" and supplied_access_code is None:
        return
    expected = settings.app_access_code
    if not supplied_access_code or not secrets.compare_digest(supplied_access_code, expected):
        failure_reason = "missing_credentials" if not supplied_access_code else "credential_mismatch"
        log_auth_debug(
            request=request,
            auth_scheme=auth_scheme,
            has_header=bool(x_neraium_access_code),
            has_cookie=bool(neraium_access_code),
            has_authorization=bool(authorization),
            failure_reason=failure_reason,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": "unauthorized",
                "error_type": "auth",
                "message": "Telemetry processing session could not be validated.",
            },
        )


def parse_authorization_access_code(authorization: str | None) -> tuple[str | None, str | None]:
    if not authorization:
        return None, None
    scheme, _, value = authorization.partition(" ")
    normalized_scheme = scheme.lower()
    if normalized_scheme == "bearer" and value.strip():
        return "bearer", value.strip()
    return normalized_scheme or "unknown", None


def log_auth_debug(
    *,
    request: Request,
    auth_scheme: str | None,
    has_header: bool,
    has_cookie: bool,
    has_authorization: bool,
    failure_reason: str | None,
) -> None:
    log_method = logger.warning if failure_reason else logger.debug
    log_method(
        "auth_check path=%s method=%s origin=%s cookies_present=%s has_access_cookie=%s has_access_header=%s has_authorization=%s auth_scheme=%s failure_reason=%s client=%s",
        request.url.path,
        request.method,
        request.headers.get("origin"),
        bool(request.cookies),
        has_cookie,
        has_header,
        has_authorization,
        auth_scheme or "none",
        failure_reason or "none",
        request.client.host if request.client else "unknown",
    )
