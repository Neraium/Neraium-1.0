from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services import runtime_db as runtime_db_module
from app.services.runtime_db import (
    auth_metrics,
    configure_runtime_dir as configure_runtime_db_dir,
    delete_expired_auth_sessions,
    list_auth_sessions,
    list_auth_users,
    read_auth_session,
    read_auth_user,
    revoke_auth_session,
    revoke_auth_sessions_for_email,
    set_auth_user_active_status,
    set_auth_user_login,
    upsert_auth_session,
    upsert_auth_user,
)

_STORE_LOCK = threading.RLock()
_SESSION_COOKIE_NAME = "neraium_session"
_SESSION_TTL_DAYS = 14
_VALID_ROLES = {"viewer", "operator", "admin"}
_AUTH_RUNTIME_KEY: str | None = None


def session_cookie_name() -> str:
    return _SESSION_COOKIE_NAME


def _runtime_dir() -> Path:
    configured = str(os.getenv("NERAIUM_RUNTIME_DIR", "")).strip()
    runtime_dir = Path(configured) if configured else get_settings().runtime_dir
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def _legacy_store_path() -> Path:
    return _runtime_dir() / "auth_store.json"


@contextmanager
def _auth_runtime_db_context():
    runtime_dir = _runtime_dir()
    previous_runtime_dir = runtime_db_module.RUNTIME_DIR
    previous_db_path = runtime_db_module.DB_PATH
    configure_runtime_db_dir(runtime_dir)
    try:
        yield
    finally:
        runtime_db_module.RUNTIME_DIR = previous_runtime_dir
        runtime_db_module.DB_PATH = previous_db_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_role(value: str | None, default: str = "operator") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in _VALID_ROLES:
        return normalized
    return default


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
        "role": normalize_role(user.get("role"), "operator"),
        "created_at": user.get("created_at"),
        "last_login_at": user.get("last_login_at"),
        "is_active": bool(user.get("is_active", True)),
        "deactivated_at": user.get("deactivated_at"),
        "bootstrap_managed": bool(user.get("bootstrap_managed", False)),
    }


def sanitize_session_record(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": str(session.get("session_id") or ""),
        "email": _normalize_email(session.get("email", "")),
        "created_at": session.get("created_at"),
        "expires_at": session.get("expires_at"),
        "last_seen_at": session.get("last_seen_at"),
        "revoked_at": session.get("revoked_at"),
    }


def _upsert_user_record(
    *,
    email: str,
    password_hash: str,
    salt: str,
    name: str,
    role: str,
    created_at: str | None = None,
    last_login_at: str | None = None,
    is_active: bool = True,
    deactivated_at: str | None = None,
    bootstrap_managed: bool = False,
) -> dict[str, Any]:
    payload = {
        "email": email,
        "name": name,
        "role": normalize_role(role, "operator"),
        "salt": salt,
        "password_hash": password_hash,
        "created_at": created_at or _now_iso(),
        "updated_at": _now_iso(),
        "last_login_at": last_login_at,
        "is_active": is_active,
        "deactivated_at": deactivated_at,
        "bootstrap_managed": bootstrap_managed,
    }
    upsert_auth_user(payload)
    stored = read_auth_user(email)
    if not stored:
        raise RuntimeError("auth_user_write_failed")
    return stored


def _ensure_bootstrap_user(*, email: str, password: str, name: str, role: str) -> bool:
    normalized_email = _normalize_email(email)
    if not normalized_email or not password:
        return False
    normalized_role = normalize_role(role, "admin")
    existing = read_auth_user(normalized_email)
    if existing:
        changed = False
        payload = dict(existing)
        if normalize_role(existing.get("role"), normalized_role) != normalized_role:
            payload["role"] = normalized_role
            changed = True
        if not str(existing.get("name") or "").strip() and name:
            payload["name"] = name
            changed = True
        if not bool(existing.get("bootstrap_managed")):
            payload["bootstrap_managed"] = True
            changed = True
        if changed:
            upsert_auth_user(payload)
        return changed
    salt = secrets.token_hex(16)
    _upsert_user_record(
        email=normalized_email,
        password_hash=_hash_password(password, salt),
        salt=salt,
        name=str(name or "").strip() or normalized_email.split("@", 1)[0],
        role=normalized_role,
        bootstrap_managed=True,
    )
    return True


def _apply_bootstrap_users() -> None:
    _ensure_bootstrap_user(
        email=str(os.getenv("NERAIUM_BOOTSTRAP_ADMIN_EMAIL", "")).strip(),
        password=str(os.getenv("NERAIUM_BOOTSTRAP_ADMIN_PASSWORD", "")).strip(),
        name=str(os.getenv("NERAIUM_BOOTSTRAP_ADMIN_NAME", "Admin")).strip(),
        role="admin",
    )
    _ensure_bootstrap_user(
        email=str(os.getenv("NERAIUM_BOOTSTRAP_OPERATOR_EMAIL", "")).strip(),
        password=str(os.getenv("NERAIUM_BOOTSTRAP_OPERATOR_PASSWORD", "")).strip(),
        name=str(os.getenv("NERAIUM_BOOTSTRAP_OPERATOR_NAME", "Operator")).strip(),
        role="operator",
    )


def _migrate_legacy_store_if_needed() -> None:
    path = _legacy_store_path()
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    users = list_auth_users(include_inactive=True, limit=1)
    sessions = list_auth_sessions(include_revoked=True, limit=1)
    if users or sessions:
        return
    migrated = False
    for raw_user in payload.get("users", []):
        email = _normalize_email(raw_user.get("email", ""))
        salt = str(raw_user.get("salt") or "")
        password_hash = str(raw_user.get("password_hash") or "")
        if not email or not salt or not password_hash:
            continue
        _upsert_user_record(
            email=email,
            password_hash=password_hash,
            salt=salt,
            name=str(raw_user.get("name") or email.split("@", 1)[0]).strip(),
            role=normalize_role(raw_user.get("role"), "operator"),
            created_at=raw_user.get("created_at"),
            last_login_at=raw_user.get("last_login_at"),
            is_active=bool(raw_user.get("is_active", True)),
            deactivated_at=raw_user.get("deactivated_at"),
            bootstrap_managed=bool(raw_user.get("bootstrap_managed", False)),
        )
        migrated = True
    for session_id, raw_session in (payload.get("sessions") or {}).items():
        email = _normalize_email((raw_session or {}).get("email", ""))
        expires_at = (raw_session or {}).get("expires_at")
        if not email or not read_auth_user(email):
            continue
        expires = _parse_iso(expires_at)
        if not expires or expires <= datetime.now(timezone.utc):
            continue
        upsert_auth_session(
            {
                "session_id": str(session_id),
                "email": email,
                "created_at": (raw_session or {}).get("created_at") or _now_iso(),
                "expires_at": expires_at,
                "last_seen_at": (raw_session or {}).get("created_at"),
                "revoked_at": None,
            }
        )
        migrated = True
    if migrated:
        migrated_path = path.with_name(f"{path.name}.migrated")
        try:
            if migrated_path.exists():
                migrated_path.unlink()
            path.rename(migrated_path)
        except Exception:
            pass


def _ensure_auth_storage_ready() -> None:
    global _AUTH_RUNTIME_KEY
    runtime_key = str(_runtime_dir().resolve())
    with _STORE_LOCK:
        delete_expired_auth_sessions()
        if _AUTH_RUNTIME_KEY != runtime_key:
            _migrate_legacy_store_if_needed()
            _AUTH_RUNTIME_KEY = runtime_key
        _apply_bootstrap_users()


def create_user(email: str, password: str, name: str | None = None, role: str = "operator") -> dict[str, Any]:
    with _auth_runtime_db_context():
        _ensure_auth_storage_ready()
        normalized_email = _normalize_email(email)
        if "@" not in normalized_email or len(normalized_email) < 5:
            raise ValueError("Enter a valid email address.")
        if len(password or "") < 8:
            raise ValueError("Password must be at least 8 characters.")
        display_name = str(name or "").strip() or normalized_email.split("@", 1)[0]
        normalized_role = normalize_role(role, "operator")
        with _STORE_LOCK:
            if read_auth_user(normalized_email):
                raise ValueError("An account with this email already exists.")
            salt = secrets.token_hex(16)
            user = _upsert_user_record(
                email=normalized_email,
                password_hash=_hash_password(password, salt),
                salt=salt,
                name=display_name,
                role=normalized_role,
            )
            return sanitize_user_record(user)


def list_users(*, include_inactive: bool = True) -> list[dict[str, Any]]:
    with _auth_runtime_db_context():
        _ensure_auth_storage_ready()
        return [sanitize_user_record(user) for user in list_auth_users(include_inactive=include_inactive)]


def activate_user(email: str) -> dict[str, Any] | None:
    with _auth_runtime_db_context():
        _ensure_auth_storage_ready()
        normalized_email = _normalize_email(email)
        with _STORE_LOCK:
            user = set_auth_user_active_status(normalized_email, is_active=True)
        return sanitize_user_record(user) if user else None


def deactivate_user(email: str) -> dict[str, Any] | None:
    with _auth_runtime_db_context():
        _ensure_auth_storage_ready()
        normalized_email = _normalize_email(email)
        with _STORE_LOCK:
            user = set_auth_user_active_status(normalized_email, is_active=False)
            revoke_auth_sessions_for_email(normalized_email)
        return sanitize_user_record(user) if user else None


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    with _auth_runtime_db_context():
        _ensure_auth_storage_ready()
        normalized_email = _normalize_email(email)
        with _STORE_LOCK:
            user = read_auth_user(normalized_email)
            if not user or not bool(user.get("is_active", True)):
                return None
            expected_hash = str(user.get("password_hash") or "")
            salt = str(user.get("salt") or "")
            candidate = _hash_password(password, salt)
            if hmac.compare_digest(expected_hash, candidate):
                return sanitize_user_record(user)
            return None


def create_session(email: str) -> str:
    with _auth_runtime_db_context():
        _ensure_auth_storage_ready()
        session_id = secrets.token_urlsafe(48)
        normalized_email = _normalize_email(email)
        timestamp = _now_iso()
        with _STORE_LOCK:
            user = read_auth_user(normalized_email)
            if not user or not bool(user.get("is_active", True)):
                raise ValueError("Account is inactive or missing.")
            revoke_auth_sessions_for_email(normalized_email, revoked_at=timestamp)
            upsert_auth_session(
                {
                    "session_id": session_id,
                    "email": normalized_email,
                    "created_at": timestamp,
                    "expires_at": _session_expiry_iso(),
                    "last_seen_at": timestamp,
                    "revoked_at": None,
                }
            )
            set_auth_user_login(normalized_email, timestamp)
        return session_id


def delete_session(session_id: str | None) -> None:
    with _auth_runtime_db_context():
        _ensure_auth_storage_ready()
        if not session_id:
            return
        with _STORE_LOCK:
            revoke_auth_session(session_id)


def get_session_record(session_id: str | None) -> dict[str, Any] | None:
    with _auth_runtime_db_context():
        _ensure_auth_storage_ready()
        if not session_id:
            return None
        with _STORE_LOCK:
            session = read_auth_session(session_id)
            if not session:
                return None
            expires_at = _parse_iso(session.get("expires_at"))
            now = datetime.now(timezone.utc)
            if bool(session.get("revoked_at")):
                return None
            if not expires_at or expires_at <= now:
                revoke_auth_session(session_id, revoked_at=now.isoformat())
                return None
            return sanitize_session_record(session)


def get_user_by_session(session_id: str | None) -> dict[str, Any] | None:
    with _auth_runtime_db_context():
        session = get_session_record(session_id)
        if not session:
            return None
        user = read_auth_user(session["email"])
        if not user or not bool(user.get("is_active", True)):
            return None
        return sanitize_user_record(user)


def list_sessions(*, email: str | None = None, include_revoked: bool = False) -> list[dict[str, Any]]:
    with _auth_runtime_db_context():
        _ensure_auth_storage_ready()
        normalized_email = _normalize_email(email or "") or None
        sessions = list_auth_sessions(email=normalized_email, include_revoked=include_revoked)
        now = datetime.now(timezone.utc)
        sanitized: list[dict[str, Any]] = []
        for session in sessions:
            expires_at = _parse_iso(session.get("expires_at"))
            if not include_revoked and (session.get("revoked_at") or not expires_at or expires_at <= now):
                continue
            sanitized.append(sanitize_session_record(session))
        return sanitized


def revoke_session(*, session_id: str | None = None, email: str | None = None, revoke_all_for_user: bool = False) -> int:
    with _auth_runtime_db_context():
        _ensure_auth_storage_ready()
        normalized_email = _normalize_email(email or "")
        with _STORE_LOCK:
            if session_id:
                if not read_auth_session(session_id):
                    return 0
                revoke_auth_session(session_id)
                return 1
            if revoke_all_for_user and normalized_email:
                return revoke_auth_sessions_for_email(normalized_email)
        return 0


def auth_summary() -> dict[str, int]:
    with _auth_runtime_db_context():
        _ensure_auth_storage_ready()
        return auth_metrics()
