from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings

_STORE_LOCK = threading.Lock()
_SESSION_COOKIE_NAME = "neraium_session"
_SESSION_TTL_DAYS = 14


def session_cookie_name() -> str:
    return _SESSION_COOKIE_NAME


def _store_path() -> Path:
    runtime_dir = get_settings().runtime_dir
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir / "auth_store.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_store() -> dict[str, Any]:
    return {
        "users": [],
        "sessions": {},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


def _load_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _default_store()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_store()
    if not isinstance(payload, dict):
        return _default_store()
    payload.setdefault("users", [])
    payload.setdefault("sessions", {})
    payload.setdefault("created_at", _now_iso())
    payload["updated_at"] = _now_iso()
    return payload


def _save_store(payload: dict[str, Any]) -> None:
    payload["updated_at"] = _now_iso()
    _store_path().write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return digest.hex()


def _session_expiry_iso() -> str:
    expires = datetime.now(timezone.utc) + timedelta(days=_SESSION_TTL_DAYS)
    return expires.isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def sanitize_user_record(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "created_at": user.get("created_at"),
    }


def create_user(email: str, password: str, name: str | None = None) -> dict[str, Any]:
    normalized_email = _normalize_email(email)
    if "@" not in normalized_email or len(normalized_email) < 5:
        raise ValueError("Enter a valid email address.")
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters.")
    display_name = str(name or "").strip() or normalized_email.split("@", 1)[0]
    with _STORE_LOCK:
        store = _load_store()
        for existing in store["users"]:
            if _normalize_email(existing.get("email")) == normalized_email:
                raise ValueError("An account with this email already exists.")
        salt = secrets.token_hex(16)
        user = {
            "email": normalized_email,
            "name": display_name,
            "salt": salt,
            "password_hash": _hash_password(password, salt),
            "created_at": _now_iso(),
        }
        store["users"].append(user)
        _save_store(store)
        return sanitize_user_record(user)


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    normalized_email = _normalize_email(email)
    with _STORE_LOCK:
        store = _load_store()
        for user in store["users"]:
            if _normalize_email(user.get("email")) != normalized_email:
                continue
            expected_hash = str(user.get("password_hash") or "")
            salt = str(user.get("salt") or "")
            candidate = _hash_password(password, salt)
            if hmac.compare_digest(expected_hash, candidate):
                return sanitize_user_record(user)
            return None
    return None


def create_session(email: str) -> str:
    session_id = secrets.token_urlsafe(48)
    with _STORE_LOCK:
        store = _load_store()
        store["sessions"][session_id] = {
            "email": _normalize_email(email),
            "created_at": _now_iso(),
            "expires_at": _session_expiry_iso(),
        }
        _save_store(store)
    return session_id


def delete_session(session_id: str | None) -> None:
    if not session_id:
        return
    with _STORE_LOCK:
        store = _load_store()
        if session_id in store["sessions"]:
            del store["sessions"][session_id]
            _save_store(store)


def get_user_by_session(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    with _STORE_LOCK:
        store = _load_store()
        session = store["sessions"].get(session_id)
        if not isinstance(session, dict):
            return None
        expires_at = _parse_iso(session.get("expires_at"))
        now = datetime.now(timezone.utc)
        if not expires_at or expires_at <= now:
            del store["sessions"][session_id]
            _save_store(store)
            return None
        email = _normalize_email(session.get("email", ""))
        for user in store["users"]:
            if _normalize_email(user.get("email")) == email:
                return sanitize_user_record(user)
    return None

