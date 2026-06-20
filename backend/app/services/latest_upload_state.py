from __future__ import annotations

from typing import Any

from app.services.upload_session_service import resolve_latest_upload_session
from app.services.upload_state_repository import read_latest_upload_record


def resolve_latest_upload_payload(*, include_persisted: int | bool = True, request_id: str | None = None) -> dict[str, Any]:
    # Preserve legacy monkeypatch points used by regression tests.
    read_latest_upload_record()
    return resolve_latest_upload_session(include_persisted=include_persisted, request_id=request_id)


__all__ = ["read_latest_upload_record", "resolve_latest_upload_payload"]
