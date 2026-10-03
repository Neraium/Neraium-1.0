"""Existing auth migrations; explicit admin path for SQLite and PostgreSQL."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    CREATE TABLE IF NOT EXISTS auth_workspaces (
        workspace_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        scope_tenant_id TEXT NOT NULL,
        scope_user_id TEXT NOT NULL,
        scope_workspace_id TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        disabled_at TEXT,
        created_by TEXT NOT NULL,
        UNIQUE(scope_tenant_id, scope_user_id, scope_workspace_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_workspace_members (
        workspace_id TEXT NOT NULL,
        email TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        added_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        disabled_at TEXT,
        added_by TEXT NOT NULL,
        PRIMARY KEY(workspace_id, email),
        FOREIGN KEY(workspace_id) REFERENCES auth_workspaces(workspace_id) ON DELETE RESTRICT,
        FOREIGN KEY(email) REFERENCES auth_users(email) ON DELETE RESTRICT
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
    """
    CREATE INDEX IF NOT EXISTS idx_auth_workspace_members_email_active
    ON auth_workspace_members(email, is_active)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_auth_workspace_members_workspace_active
    ON auth_workspace_members(workspace_id, is_active)
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
    CREATE TABLE IF NOT EXISTS auth_workspaces (
        workspace_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        scope_tenant_id TEXT NOT NULL,
        scope_user_id TEXT NOT NULL,
        scope_workspace_id TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        disabled_at TIMESTAMPTZ,
        created_by TEXT NOT NULL,
        UNIQUE(scope_tenant_id, scope_user_id, scope_workspace_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_workspace_members (
        workspace_id TEXT NOT NULL,
        email TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        added_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        disabled_at TIMESTAMPTZ,
        added_by TEXT NOT NULL,
        PRIMARY KEY(workspace_id, email),
        FOREIGN KEY(workspace_id) REFERENCES auth_workspaces(workspace_id) ON DELETE RESTRICT,
        FOREIGN KEY(email) REFERENCES auth_users(email) ON DELETE RESTRICT
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
    "CREATE INDEX IF NOT EXISTS idx_auth_workspace_members_email_active ON auth_workspace_members(email, is_active)",
    "CREATE INDEX IF NOT EXISTS idx_auth_workspace_members_workspace_active ON auth_workspace_members(workspace_id, is_active)",
)

AUTH_SCHEMA_MIGRATIONS = (
    "001_auth_integrity",
    "002_single_active_session",
    "003_workspace_membership",
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

    if "003_workspace_membership" not in applied:
        connection.execute(
            f"INSERT INTO auth_schema_migrations (migration_id, applied_at) VALUES ({placeholder}, {placeholder})",
            ("003_workspace_membership", _now_iso()),
        )


def apply(connection: Any, *, dialect: str, placeholder: str) -> None:
    if dialect == "postgresql":
        connection.execute("SELECT pg_advisory_xact_lock(173514001)")
    else:
        connection.execute("BEGIN IMMEDIATE")
    statements = POSTGRES_AUTH_SCHEMA_STATEMENTS if dialect == "postgresql" else AUTH_SCHEMA_STATEMENTS
    for statement in statements:
        connection.execute(statement)
    _apply_auth_schema_migrations(connection, dialect=dialect, placeholder=placeholder)
