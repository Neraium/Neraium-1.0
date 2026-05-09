import secrets

from fastapi import Header, HTTPException, status

from app.core.config import get_settings

ACCESS_CODE_HEADER = "X-Neraium-Access-Code"


def require_api_access(x_neraium_access_code: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.app_env != "production" and x_neraium_access_code is None:
        return
    expected = settings.app_access_code
    if not x_neraium_access_code or not secrets.compare_digest(x_neraium_access_code, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid Neraium access is required.",
        )
