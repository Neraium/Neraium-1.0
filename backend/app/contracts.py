from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, StringConstraints


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    detail: str | dict[str, Any]
    message: str
    error_type: str
    errors: list[dict[str, Any]] | None = None


class ContractModel(BaseModel):
    """Request model policy: trim strings and reject undeclared fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
EmailAddress = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=5,
        max_length=320,
        pattern=r"^[^@\s/]+@[^@\s/]+\.[^@\s/]+$",
    ),
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
OptionalNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
SecretText = Annotated[str, StringConstraints(min_length=1, max_length=1024)]


def validate_http_url(value: str, *, allow_empty: bool = False) -> str:
    normalized = str(value or "").strip()
    if allow_empty and not normalized:
        return ""
    if len(normalized) > 2048:
        raise ValueError("URL must not exceed 2048 characters.")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("URL must be an HTTP(S) URL without embedded credentials.")
    return normalized


def validate_utc_timestamp(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip()
    if len(normalized) > 64:
        raise ValueError("Timestamp is too long.")
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Timestamp must be ISO 8601.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone offset.")
    return parsed.astimezone(timezone.utc).isoformat()


async def enforce_query_contract(request: Request) -> None:
    route = request.scope.get("route")
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return
    allowed = {str(param.alias) for param in getattr(dependant, "query_params", [])}
    unknown = sorted(set(request.query_params.keys()) - allowed)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"message": "Unknown query parameter.", "fields": unknown},
        )


def validate_contract_headers(request: Request) -> None:
    limits = {
        "x-request-id": 128,
        "x-upload-session-id": 128,
        "x-neraium-user": 320,
        "x-authenticated-user": 320,
        "x-forwarded-email": 320,
        "authorization": 4096,
        "x-neraium-access-code": 4096,
    }
    for name, limit in limits.items():
        value = request.headers.get(name)
        if value is not None and len(value) > limit:
            raise HTTPException(status_code=400, detail=f"Header {name} exceeds {limit} characters.")
    request_id = request.headers.get("x-request-id")
    if request_id and not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_id):
        raise HTTPException(status_code=400, detail="X-Request-Id contains invalid characters.")
