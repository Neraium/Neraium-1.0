from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings

try:
    import psycopg  # type: ignore
except Exception:  # pragma: no cover - psycopg is optional in local/test envs
    psycopg = None

_STORE_LOCK = threading.RLock()
_SESSION_COOKIE_NAME = "neraium_session"
_SESSION_TTL_DAYS = 14
_VALID_ROLES = {"viewer", "operator", "admin"}
_AUTH_BACKEND_KEY: tuple[str, str] | None = None
_AUTH_BACKEND: "_BaseAuthBackend" | None = None


AUTH_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS auth_users (
        email TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('viewer', 'operator', 'admin')),
        salt TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_login_at TEXT,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        deactivated_at TEXT,
        bootstrap_managed BOOLEAN NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        session_id TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        last_seen_at TEXT,
        revoked_at TEXT,
        FOREIGN KEY(email) REFERENCES auth_users(email) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auth_users_role_active ON auth_users(role, is_active)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auth_sessions_email ON auth_sessions(email, expires_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auth_sessions_revoked ON auth_sessions(revoked_at, expires_at DESC)
    """,
)

POSTGRES_AUTH_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS auth_users (
        email TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('viewer', 'operator', 'admin')),
        salt TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        last_login_at TIMESTAMPTZ,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        deactivated_at TIMESTAMPTZ,
        bootstrap_managed BOOLEAN NOT NULL DEFAULT FALSE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        session_id TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        last_seen_at TIMESTAMPTZ,
        revoked_at TIMESTAMPTZ,
        FOREIGN KEY(email) REFERENCES auth_users(email) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_auth_users_role_active ON auth_users(role, is_active)",
    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_email ON auth_sessions(email, expires_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_revoked ON auth_sessions(revoked_at, expires_at DESC)",
)

AUTH_SCHEMA_MIGRATIONS = (
    "001_auth_integrity",
    "002_single_active_session",
)


def _apply_auth_schema_migrations(connection: Any, *, dialect: str, placeholder: str) -> None:
    migration_timestamp_type = "TIMESTAMPTZ" if dialect == "postgresql" else "TEXT"
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS auth_schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at {migration_timestamp_type} NOT NULL
        )
        """
    )
    rows = connection.execute("SELECT migration_id FROM auth_schema_migrations").fetchall()
    applied = {str(row[0] if not hasattr(row, "keys") else row["migration_id"]) for row in rows}

    if "001_auth_integrity" not in applied:
        connection.execute(
            "UPDATE auth_users SET role = 'operator' WHERE role NOT IN ('viewer', 'operator', 'admin')"
        )
        if dialect == "sqlite":
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS trg_auth_users_integrity_insert
                BEFORE INSERT ON auth_users
                WHEN NEW.role NOT IN ('viewer', 'operator', 'admin')
                  OR NEW.email = '' OR length(NEW.email) > 320
                BEGIN
                    SELECT RAISE(ABORT, 'auth_user_integrity');
                END
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS trg_auth_users_integrity_update
                BEFORE UPDATE OF email, role ON auth_users
                WHEN NEW.role NOT IN ('viewer', 'operator', 'admin')
                  OR NEW.email = '' OR length(NEW.email) > 320
                BEGIN
                    SELECT RAISE(ABORT, 'auth_user_integrity');
                END
                """
            )
        else:
            connection.execute(
                """
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'ck_auth_users_role' AND conrelid = 'auth_users'::regclass
                    ) THEN
                        ALTER TABLE auth_users ADD CONSTRAINT ck_auth_users_role
                            CHECK (role IN ('viewer', 'operator', 'admin')) NOT VALID;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'ck_auth_users_email_length' AND conrelid = 'auth_users'::regclass
                    ) THEN
                        ALTER TABLE auth_users ADD CONSTRAINT ck_auth_users_email_length
                            CHECK (length(email) BETWEEN 1 AND 320) NOT VALID;
                    END IF;
                END $$
                """
            )
            connection.execute("ALTER TABLE auth_users VALIDATE CONSTRAINT ck_auth_users_role")
            connection.execute("ALTER TABLE auth_users VALIDATE CONSTRAINT ck_auth_users_email_length")
        connection.execute(
            f"INSERT INTO auth_schema_migrations (migration_id, applied_at) VALUES ({placeholder}, {placeholder})",
            ("001_auth_integrity", _now_iso()),
        )

    if "002_single_active_session" not in applied:
        migration_time = _now_iso()
        connection.execute(
            f"""
            UPDATE auth_sessions
            SET revoked_at = {placeholder}
            WHERE revoked_at IS NULL
              AND session_id IN (
                  SELECT session_id FROM (
                      SELECT session_id,
                             ROW_NUMBER() OVER (
                                 PARTITION BY email ORDER BY created_at DESC, session_id DESC
                             ) AS position
                      FROM auth_sessions
                      WHERE revoked_at IS NULL
                  ) ranked
                  WHERE position > 1
              )
            """,
            (migration_time,),
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_sessions_active_email "
            "ON auth_sessions(email) WHERE revoked_at IS NULL"
        )
        connection.execute(
            f"INSERT INTO auth_schema_migrations (migration_id, applied_at) VALUES ({placeholder}, {placeholder})",
            ("002_single_active_session", migration_time),
        )


class _BaseAuthBackend:
    placeholder = "?"

    dialect = "unknown"

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            statements = POSTGRES_AUTH_SCHEMA_STATEMENTS if self.dialect == "postgresql" else AUTH_SCHEMA_STATEMENTS
            for statement in statements:
                connection.execute(statement)
            _apply_auth_schema_migrations(connection, dialect=self.dialect, placeholder=self.placeholder)

    def _connect(self):
        raise NotImplementedError

    def _placeholders(self, count: int) -> str:
        return ", ".join([self.placeholder] * count)

    def _row_to_dict(self, cursor: Any, row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        if isinstance(row, dict):
            return dict(row)
        if hasattr(row, "keys"):
            return {key: row[key] for key in row.keys()}
        columns = [column[0] for column in getattr(cursor, "description", []) or []]
        return {columns[index]: row[index] for index in range(min(len(columns), len(row)))}

    def _fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self._connect() as connection:
            cursor = connection.execute(sql, params)
            return self._row_to_dict(cursor, cursor.fetchone())

    def _fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._connect() as connection:
            cursor = connection.execute(sql, params)
            rows = cursor.fetchall()
            return [self._row_to_dict(cursor, row) for row in rows if self._row_to_dict(cursor, row) is not None]

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self._connect() as connection:
            cursor = connection.execute(sql, params)
            return int(getattr(cursor, "rowcount", 0) or 0)

    def upsert_user(self, payload: dict[str, Any]) -> None:
        sql = f"""
            INSERT INTO auth_users (
                email, name, role, salt, password_hash, created_at, updated_at,
                last_login_at, is_active, deactivated_at, bootstrap_managed
            )
            VALUES ({self._placeholders(11)})
            ON CONFLICT(email) DO UPDATE SET
                name=excluded.name,
                role=excluded.role,
                salt=excluded.salt,
                password_hash=excluded.password_hash,
                updated_at=excluded.updated_at,
                last_login_at=excluded.last_login_at,
                is_active=excluded.is_active,
                deactivated_at=excluded.deactivated_at,
                bootstrap_managed=excluded.bootstrap_managed
        """
        self._execute(
            sql,
            (
                payload["email"],
                payload.get("name") or payload["email"],
                payload.get("role", "operator"),
                payload.get("salt", ""),
                payload.get("password_hash", ""),
                payload.get("created_at") or _now_iso(),
                payload.get("updated_at") or _now_iso(),
                payload.get("last_login_at"),
                bool(payload.get("is_active", True)),
                payload.get("deactivated_at"),
                bool(payload.get("bootstrap_managed")),
            ),
        )

    def insert_user_if_absent(self, payload: dict[str, Any]) -> bool:
        sql = f"""
            INSERT INTO auth_users (
                email, name, role, salt, password_hash, created_at, updated_at,
                last_login_at, is_active, deactivated_at, bootstrap_managed
            )
            VALUES ({self._placeholders(11)})
            ON CONFLICT(email) DO NOTHING
        """
        values = (
            payload["email"], payload.get("name") or payload["email"],
            payload.get("role", "operator"), payload.get("salt", ""),
            payload.get("password_hash", ""), payload.get("created_at") or _now_iso(),
            payload.get("updated_at") or _now_iso(), payload.get("last_login_at"),
            bool(payload.get("is_active", True)), payload.get("deactivated_at"),
            bool(payload.get("bootstrap_managed")),
        )
        return self._execute(sql, values) == 1

    def replace_active_session(self, payload: dict[str, Any]) -> None:
        email = str(payload["email"])
        timestamp = str(payload.get("created_at") or _now_iso())
        with self._connect() as connection:
            if self.dialect == "sqlite":
                connection.execute("BEGIN IMMEDIATE")
            else:
                # Serialize session replacement for one account across API processes.
                connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (email,))
            revoke_sql = (
                "UPDATE auth_sessions SET revoked_at = ? WHERE email = ? AND revoked_at IS NULL"
                if self.placeholder == "?"
                else "UPDATE auth_sessions SET revoked_at = %s WHERE email = %s AND revoked_at IS NULL"
            )
            connection.execute(revoke_sql, (timestamp, email))
            insert_sql = f"""
                INSERT INTO auth_sessions
                    (session_id, email, created_at, expires_at, last_seen_at, revoked_at)
                VALUES ({self._placeholders(6)})
            """
            connection.execute(
                insert_sql,
                (
                    payload["session_id"], email, timestamp,
                    payload.get("expires_at") or _session_expiry_iso(),
                    payload.get("last_seen_at") or timestamp, None,
                ),
            )
            login_sql = (
                "UPDATE auth_users SET last_login_at = ?, updated_at = ? WHERE email = ?"
                if self.placeholder == "?"
                else "UPDATE auth_users SET last_login_at = %s, updated_at = %s WHERE email = %s"
            )
            connection.execute(login_sql, (timestamp, timestamp, email))

    def read_user(self, email: str) -> dict[str, Any] | None:
        return self._fetch_one("SELECT * FROM auth_users WHERE email = ?" if self.placeholder == "?" else "SELECT * FROM auth_users WHERE email = %s", (email,))

    def list_users(self, *, include_inactive: bool = True, limit: int = 500) -> list[dict[str, Any]]:
        sql = "SELECT * FROM auth_users"
        params: list[Any] = []
        if not include_inactive:
            sql += " WHERE is_active"
        sql += f" ORDER BY created_at ASC LIMIT {self.placeholder}"
        params.append(limit)
        return self._fetch_all(sql, tuple(params))

    def set_user_login(self, email: str, logged_in_at: str) -> None:
        sql = (
            "UPDATE auth_users SET last_login_at = ?, updated_at = ? WHERE email = ?"
            if self.placeholder == "?"
            else "UPDATE auth_users SET last_login_at = %s, updated_at = %s WHERE email = %s"
        )
        self._execute(sql, (logged_in_at, logged_in_at, email))

    def set_user_active_status(self, email: str, *, is_active: bool) -> dict[str, Any] | None:
        timestamp = _now_iso()
        deactivated_at = None if is_active else timestamp
        sql = (
            "UPDATE auth_users SET is_active = ?, deactivated_at = ?, updated_at = ? WHERE email = ?"
            if self.placeholder == "?"
            else "UPDATE auth_users SET is_active = %s, deactivated_at = %s, updated_at = %s WHERE email = %s"
        )
        self._execute(sql, (bool(is_active), deactivated_at, timestamp, email))
        return self.read_user(email)

    def upsert_session(self, payload: dict[str, Any]) -> None:
        sql = f"""
            INSERT INTO auth_sessions (session_id, email, created_at, expires_at, last_seen_at, revoked_at)
            VALUES ({self._placeholders(6)})
            ON CONFLICT(session_id) DO UPDATE SET
                email=excluded.email,
                created_at=excluded.created_at,
                expires_at=excluded.expires_at,
                last_seen_at=excluded.last_seen_at,
                revoked_at=excluded.revoked_at
        """
        self._execute(
            sql,
            (
                payload["session_id"],
                payload["email"],
                payload.get("created_at") or _now_iso(),
                payload.get("expires_at") or _session_expiry_iso(),
                payload.get("last_seen_at"),
                payload.get("revoked_at"),
            ),
        )

    def read_session(self, session_id: str) -> dict[str, Any] | None:
        sql = "SELECT * FROM auth_sessions WHERE session_id = ?" if self.placeholder == "?" else "SELECT * FROM auth_sessions WHERE session_id = %s"
        return self._fetch_one(sql, (session_id,))

    def list_sessions(self, *, email: str | None = None, include_revoked: bool = False, limit: int = 500) -> list[dict[str, Any]]:
        sql = "SELECT * FROM auth_sessions"
        params: list[Any] = []
        clauses: list[str] = []
        if email:
            clauses.append("email = ?" if self.placeholder == "?" else "email = %s")
            params.append(email)
        if not include_revoked:
            clauses.append("revoked_at IS NULL")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += f" ORDER BY created_at DESC LIMIT {self.placeholder}"
        params.append(limit)
        return self._fetch_all(sql, tuple(params))

    def revoke_session(self, session_id: str, *, revoked_at: str | None = None) -> None:
        timestamp = revoked_at or _now_iso()
        sql = (
            "UPDATE auth_sessions SET revoked_at = ? WHERE session_id = ?"
            if self.placeholder == "?"
            else "UPDATE auth_sessions SET revoked_at = %s WHERE session_id = %s"
        )
        self._execute(sql, (timestamp, session_id))

    def revoke_sessions_for_email(self, email: str, *, revoked_at: str | None = None) -> int:
        timestamp = revoked_at or _now_iso()
        sql = (
            "UPDATE auth_sessions SET revoked_at = ? WHERE email = ? AND revoked_at IS NULL"
            if self.placeholder == "?"
            else "UPDATE auth_sessions SET revoked_at = %s WHERE email = %s AND revoked_at IS NULL"
        )
        return self._execute(sql, (timestamp, email))

    def delete_expired_sessions(self, now_value: str | None = None) -> int:
        cutoff = now_value or _now_iso()
        sql = (
            "DELETE FROM auth_sessions WHERE expires_at <= ?"
            if self.placeholder == "?"
            else "DELETE FROM auth_sessions WHERE expires_at <= %s"
        )
        return self._execute(sql, (cutoff,))

    def metrics(self) -> dict[str, int]:
        self.delete_expired_sessions()
        users = self._fetch_one(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN is_active THEN 1 ELSE 0 END) AS active FROM auth_users"
        )
        sessions = self._fetch_one(
            (
                "SELECT COUNT(*) AS active_sessions FROM auth_sessions WHERE revoked_at IS NULL AND expires_at > ?"
                if self.placeholder == "?"
                else "SELECT COUNT(*) AS active_sessions FROM auth_sessions WHERE revoked_at IS NULL AND expires_at > %s"
            ),
            (_now_iso(),),
        )
        total_users = int(users["total"] or 0) if users else 0
        active_users = int(users["active"] or 0) if users else 0
        active_sessions = int(sessions["active_sessions"] or 0) if sessions else 0
        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": max(total_users - active_users, 0),
            "active_sessions": active_sessions,
        }


class _SQLiteAuthBackend(_BaseAuthBackend):
    placeholder = "?"
    dialect = "sqlite"

    def __init__(self, db_path: Path):
        self.db_path = db_path

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class _PostgresAuthBackend(_BaseAuthBackend):
    placeholder = "%s"
    dialect = "postgresql"

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _connect(self):
        if psycopg is None:
            raise RuntimeError("psycopg is required when NERAIUM_AUTH_DATABASE_URL is configured.")
        return psycopg.connect(self.dsn)


def session_cookie_name() -> str:
    return _SESSION_COOKIE_NAME


def _runtime_dir() -> Path:
    configured = str(os.getenv("NERAIUM_RUNTIME_DIR", "")).strip()
    runtime_dir = Path(configured) if configured else get_settings().runtime_dir
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def _legacy_store_path() -> Path:
    return _runtime_dir() / "auth_store.json"


def _auth_database_url() -> str:
    # Authentication backend selection must not rebuild/validate unrelated app
    # settings on every request; the DSN has a dedicated environment contract.
    return str(os.getenv("NERAIUM_AUTH_DATABASE_URL", "")).strip()


def _backend_key() -> tuple[str, str]:
    dsn = _auth_database_url()
    if dsn:
        return ("postgres", dsn)
    return ("sqlite", str(_runtime_dir() / "auth_store.db"))


def _get_backend() -> _BaseAuthBackend:
    global _AUTH_BACKEND, _AUTH_BACKEND_KEY
    key = _backend_key()
    with _STORE_LOCK:
        if _AUTH_BACKEND is None or _AUTH_BACKEND_KEY != key:
            if key[0] == "postgres":
                _AUTH_BACKEND = _PostgresAuthBackend(key[1])
            else:
                _AUTH_BACKEND = _SQLiteAuthBackend(Path(key[1]))
            _AUTH_BACKEND.ensure_schema()
            _AUTH_BACKEND_KEY = key
            _migrate_legacy_store_if_needed(_AUTH_BACKEND)
        _AUTH_BACKEND.delete_expired_sessions()
        _apply_bootstrap_users(_AUTH_BACKEND)
        return _AUTH_BACKEND


def initialize_auth_store() -> str:
    """Connect, migrate, and validate the configured authentication store."""
    return _get_backend().dialect


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def normalize_role(value: str | None, default: str = "operator") -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _VALID_ROLES else default


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return digest.hex()


def _session_expiry_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=_SESSION_TTL_DAYS)).isoformat()


def _parse_iso(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _serialize_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def sanitize_user_record(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "email": user.get("email", ""),
        "name": user.get("name", ""),
        "role": normalize_role(user.get("role"), "operator"),
        "created_at": _serialize_timestamp(user.get("created_at")),
        "last_login_at": _serialize_timestamp(user.get("last_login_at")),
        "is_active": bool(user.get("is_active", True)),
        "deactivated_at": _serialize_timestamp(user.get("deactivated_at")),
        "bootstrap_managed": bool(user.get("bootstrap_managed", False)),
    }


def sanitize_session_record(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": str(session.get("session_id") or ""),
        "email": _normalize_email(session.get("email", "")),
        "created_at": _serialize_timestamp(session.get("created_at")),
        "expires_at": _serialize_timestamp(session.get("expires_at")),
        "last_seen_at": _serialize_timestamp(session.get("last_seen_at")),
        "revoked_at": _serialize_timestamp(session.get("revoked_at")),
    }


def _upsert_user_record(
    backend: _BaseAuthBackend,
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
    backend.upsert_user(
        {
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
    )
    stored = backend.read_user(email)
    if not stored:
        raise RuntimeError("auth_user_write_failed")
    return stored


def _ensure_bootstrap_user(backend: _BaseAuthBackend, *, email: str, password: str, name: str, role: str) -> bool:
    normalized_email = _normalize_email(email)
    if not normalized_email or not password:
        return False
    normalized_role = normalize_role(role, "admin")
    existing = backend.read_user(normalized_email)
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
            backend.upsert_user(payload)
        return changed
    salt = secrets.token_hex(16)
    _upsert_user_record(
        backend,
        email=normalized_email,
        password_hash=_hash_password(password, salt),
        salt=salt,
        name=str(name or "").strip() or normalized_email.split("@", 1)[0],
        role=normalized_role,
        bootstrap_managed=True,
    )
    return True


def _apply_bootstrap_users(backend: _BaseAuthBackend) -> None:
    _ensure_bootstrap_user(
        backend,
        email=str(os.getenv("NERAIUM_BOOTSTRAP_ADMIN_EMAIL", "")).strip(),
        password=str(os.getenv("NERAIUM_BOOTSTRAP_ADMIN_PASSWORD", "")).strip(),
        name=str(os.getenv("NERAIUM_BOOTSTRAP_ADMIN_NAME", "Admin")).strip(),
        role="admin",
    )
    _ensure_bootstrap_user(
        backend,
        email=str(os.getenv("NERAIUM_BOOTSTRAP_OPERATOR_EMAIL", "")).strip(),
        password=str(os.getenv("NERAIUM_BOOTSTRAP_OPERATOR_PASSWORD", "")).strip(),
        name=str(os.getenv("NERAIUM_BOOTSTRAP_OPERATOR_NAME", "Operator")).strip(),
        role="operator",
    )


def _migrate_legacy_store_if_needed(backend: _BaseAuthBackend) -> None:
    path = _legacy_store_path()
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if backend.list_users(include_inactive=True, limit=1) or backend.list_sessions(include_revoked=True, limit=1):
        return
    migrated = False
    for raw_user in payload.get("users", []):
        email = _normalize_email(raw_user.get("email", ""))
        salt = str(raw_user.get("salt") or "")
        password_hash = str(raw_user.get("password_hash") or "")
        if not email or not salt or not password_hash:
            continue
        _upsert_user_record(
            backend,
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
        if not email or not backend.read_user(email):
            continue
        expires = _parse_iso(expires_at)
        if not expires or expires <= datetime.now(timezone.utc):
            continue
        backend.upsert_session(
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


def create_user(email: str, password: str, name: str | None = None, role: str = "operator") -> dict[str, Any]:
    backend = _get_backend()
    normalized_email = _normalize_email(email)
    if "@" not in normalized_email or len(normalized_email) < 5:
        raise ValueError("Enter a valid email address.")
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters.")
    display_name = str(name or "").strip() or normalized_email.split("@", 1)[0]
    normalized_role = normalize_role(role, "operator")
    with _STORE_LOCK:
        salt = secrets.token_hex(16)
        timestamp = _now_iso()
        inserted = backend.insert_user_if_absent(
            {
                "email": normalized_email,
                "name": display_name,
                "role": normalized_role,
                "salt": salt,
                "password_hash": _hash_password(password, salt),
                "created_at": timestamp,
                "updated_at": timestamp,
                "is_active": True,
                "bootstrap_managed": False,
            }
        )
        if not inserted:
            raise ValueError("An account with this email already exists.")
        user = backend.read_user(normalized_email)
        if not user:
            raise RuntimeError("auth_user_write_failed")
        return sanitize_user_record(user)


def list_users(*, include_inactive: bool = True) -> list[dict[str, Any]]:
    backend = _get_backend()
    return [sanitize_user_record(user) for user in backend.list_users(include_inactive=include_inactive)]


def activate_user(email: str) -> dict[str, Any] | None:
    backend = _get_backend()
    normalized_email = _normalize_email(email)
    with _STORE_LOCK:
        user = backend.set_user_active_status(normalized_email, is_active=True)
    return sanitize_user_record(user) if user else None


def deactivate_user(email: str) -> dict[str, Any] | None:
    backend = _get_backend()
    normalized_email = _normalize_email(email)
    with _STORE_LOCK:
        user = backend.set_user_active_status(normalized_email, is_active=False)
        backend.revoke_sessions_for_email(normalized_email)
    return sanitize_user_record(user) if user else None


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    backend = _get_backend()
    normalized_email = _normalize_email(email)
    with _STORE_LOCK:
        user = backend.read_user(normalized_email)
        if not user or not bool(user.get("is_active", True)):
            return None
        expected_hash = str(user.get("password_hash") or "")
        salt = str(user.get("salt") or "")
        if hmac.compare_digest(expected_hash, _hash_password(password, salt)):
            return sanitize_user_record(user)
        return None


def create_session(email: str) -> str:
    backend = _get_backend()
    session_id = secrets.token_urlsafe(48)
    normalized_email = _normalize_email(email)
    timestamp = _now_iso()
    with _STORE_LOCK:
        user = backend.read_user(normalized_email)
        if not user or not bool(user.get("is_active", True)):
            raise ValueError("Account is inactive or missing.")
        session_payload = {
            "session_id": session_id,
            "email": normalized_email,
            "created_at": timestamp,
            "expires_at": _session_expiry_iso(),
            "last_seen_at": timestamp,
            "revoked_at": None,
        }
        if hasattr(backend, "replace_active_session"):
            backend.replace_active_session(session_payload)
        else:  # Compatibility for third-party/test backends implementing the legacy protocol.
            backend.revoke_sessions_for_email(normalized_email, revoked_at=timestamp)
            backend.upsert_session(session_payload)
            backend.set_user_login(normalized_email, timestamp)
    return session_id


def delete_session(session_id: str | None) -> None:
    if not session_id:
        return
    backend = _get_backend()
    with _STORE_LOCK:
        backend.revoke_session(session_id)


def get_session_record(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    backend = _get_backend()
    with _STORE_LOCK:
        session = backend.read_session(session_id)
        if not session:
            return None
        if bool(session.get("revoked_at")):
            return None
        expires_at = _parse_iso(session.get("expires_at"))
        now = datetime.now(timezone.utc)
        if not expires_at or expires_at <= now:
            backend.revoke_session(session_id, revoked_at=now.isoformat())
            return None
        return sanitize_session_record(session)


def get_user_by_session(session_id: str | None) -> dict[str, Any] | None:
    session = get_session_record(session_id)
    if not session:
        return None
    backend = _get_backend()
    user = backend.read_user(session["email"])
    if not user or not bool(user.get("is_active", True)):
        return None
    return sanitize_user_record(user)


def list_sessions(*, email: str | None = None, include_revoked: bool = False) -> list[dict[str, Any]]:
    backend = _get_backend()
    normalized_email = _normalize_email(email or "") or None
    sessions = backend.list_sessions(email=normalized_email, include_revoked=include_revoked)
    now = datetime.now(timezone.utc)
    sanitized: list[dict[str, Any]] = []
    for session in sessions:
        expires_at = _parse_iso(session.get("expires_at"))
        if not include_revoked and (session.get("revoked_at") or not expires_at or expires_at <= now):
            continue
        sanitized.append(sanitize_session_record(session))
    return sanitized


def revoke_session(*, session_id: str | None = None, email: str | None = None, revoke_all_for_user: bool = False) -> int:
    backend = _get_backend()
    normalized_email = _normalize_email(email or "")
    with _STORE_LOCK:
        if session_id:
            if not backend.read_session(session_id):
                return 0
            backend.revoke_session(session_id)
            return 1
        if revoke_all_for_user and normalized_email:
            return backend.revoke_sessions_for_email(normalized_email)
    return 0


def auth_summary() -> dict[str, int]:
    backend = _get_backend()
    return backend.metrics()
