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
) -> None:
    settings = get_settings()
    supplied_access_code = x_neraium_access_code or neraium_access_code
    if settings.app_env != "production" and supplied_access_code is None:
        return
    expected = settings.app_access_code
    if not supplied_access_code or not secrets.compare_digest(supplied_access_code, expected):
        logger.warning(
            "auth_failure path=%s method=%s has_header=%s has_cookie=%s client=%s",
            request.url.path,
            request.method,
            bool(x_neraium_access_code),
            bool(neraium_access_code),
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_type": "auth_session_expired",
                "message": "Telemetry processing session expired.",
            },
        )
