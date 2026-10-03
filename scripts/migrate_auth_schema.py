"""Offline auth migration command; keep its identity outside runtime task roles.

Use a controlled migration environment with NERAIUM_AUTH_MIGRATION_DSN supplied
securely. Never pass credentials in CLI arguments or retain them in output.
"""
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.auth_store import _PostgresAuthBackend


def main() -> int:
    dsn = os.environ.get("NERAIUM_AUTH_MIGRATION_DSN", "")
    if not dsn:
        print("auth_migration_identity_required", file=sys.stderr)
        return 1
    try:
        backend = _PostgresAuthBackend(dsn)
        backend.migrate_schema()
        from app.services.schema_verification import verify_postgres
        with backend._connect() as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            verify_postgres(connection, "public", "auth_postgres")
    except Exception:
        # Driver exceptions may include DSNs, hostnames or credentials.
        print("auth_schema_migration_failed", file=sys.stderr)
        return 1
    print("auth_schema_migration_complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
