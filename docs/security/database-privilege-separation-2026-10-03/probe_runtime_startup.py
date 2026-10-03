"""Disposable-only probe of committed shared-storage startup; no AWS access.

Run in the network namespace of the network-none PostgreSQL fixture AFTER
qualify_local_database.py. The local trust DSNs are fixtures, never production.
"""
import json
import os
import psycopg
from app.services import runtime_postgres

ADMIN = "postgresql://postgres@127.0.0.1/neraium"
MIGRATOR = "postgresql://neraium_storage_migrator@127.0.0.1/neraium"
RUNTIME = "postgresql://neraium_auth_runtime@127.0.0.1/neraium"


def main():
    os.environ["APP_ENV"] = "prod"
    with psycopg.connect(ADMIN) as c:
        version = c.execute("SHOW server_version").fetchone()[0]
        c.execute("CREATE ROLE neraium_storage_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT")
        c.execute("CREATE SCHEMA neraium_runtime AUTHORIZATION neraium_storage_migrator")
        c.execute("CREATE SCHEMA unrelated AUTHORIZATION neraium_storage_migrator")
        c.execute("CREATE TABLE unrelated.private_data (id integer)")
    os.environ["NERAIUM_RUNTIME_DATABASE_URL"] = MIGRATOR
    runtime_postgres.initialize()
    with psycopg.connect(ADMIN) as c:
        c.execute("GRANT USAGE ON SCHEMA neraium_runtime TO neraium_auth_runtime")
        c.execute("GRANT SELECT ON neraium_runtime.postgres_runtime_migrations TO neraium_auth_runtime")
        c.execute("GRANT CONNECT ON DATABASE neraium TO neraium_storage_migrator")

    # Actual SQLSTATE checks, not catalog assertions. Roll every probe back.
    denied = []
    for sql in (
        "DROP SCHEMA unrelated",
        "ALTER TABLE public.auth_users OWNER TO neraium_auth_runtime",
        "GRANT neraium_auth_migrator TO neraium_storage_migrator",
        "CREATE EXTENSION hstore",
        "SELECT * FROM unrelated.private_data",
    ):
        with psycopg.connect(RUNTIME) as c:
            try:
                c.execute(sql)
            except psycopg.errors.InsufficientPrivilege as exc:
                denied.append({"sql": sql, "sqlstate": exc.sqlstate, "result": "DENIED"})
            else:
                raise AssertionError("unexpected authority: " + sql)
            finally:
                c.rollback()

    # PostgreSQL may warn and finish GRANT/REVOKE with no ACL change. Assert the
    # security effect rather than incorrectly treating command completion as a grant.
    acl_probes = []
    target = "neraium_storage_migrator"
    with psycopg.connect(RUNTIME) as c:
        c.execute("GRANT SELECT ON public.auth_users TO neraium_storage_migrator")
        effective = c.execute("SELECT has_table_privilege(%s,'public.auth_users','SELECT')", (target,)).fetchone()[0]
        assert effective is False
        acl_probes.append({"operation": "unauthorized GRANT SELECT", "grantee_select_after": effective, "result": "NO AUTHORITY TRANSFER"})
        c.rollback()
    with psycopg.connect(ADMIN) as c:
        c.execute("GRANT SELECT ON public.auth_users TO neraium_storage_migrator")
    with psycopg.connect(RUNTIME) as c:
        c.execute("REVOKE SELECT ON public.auth_users FROM neraium_storage_migrator")
        effective = c.execute("SELECT has_table_privilege(%s,'public.auth_users','SELECT')", (target,)).fetchone()[0]
        assert effective is True
        acl_probes.append({"operation": "unauthorized REVOKE SELECT", "grantee_select_after": effective, "result": "NO AUTHORITY REMOVAL"})
        c.rollback()

    original = runtime_postgres._open_connection
    ddl = []

    class TracedConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def execute(self, sql, *args, **kwargs):
            if sql.lstrip().split(None, 1)[0].upper() in {"CREATE", "ALTER", "DROP"}:
                ddl.append(sql)
            return self.connection.execute(sql, *args, **kwargs)

    runtime_postgres._open_connection = lambda **kw: TracedConnection(original(**kw))
    os.environ["NERAIUM_RUNTIME_DATABASE_URL"] = RUNTIME
    runtime_postgres._initialized.clear()
    try:
        runtime_postgres.initialize()
    except psycopg.errors.InsufficientPrivilege as exc:
        startup = {"result": "DENIED", "sqlstate": exc.sqlstate}
    else:
        raise AssertionError("startup unexpectedly succeeded without schema CREATE")
    result = {
        "database": "network-none disposable fixture",
        "postgresql_version": version,
        "admin_schema_install": "PASS",
        "runtime_denials": denied,
        "unauthorized_acl_mutations": acl_probes,
        "populated_schema_initialize": startup,
        "populated_schema_startup_ddl": ddl,
        "verification_only_requirement": "FAIL: initialize requires schema CREATE even with version 1 already installed",
        "qualification": "BLOCKED; auth-only checks do not qualify API/worker storage",
        "fixture_grants": "Only storage schema USAGE and storage migration-ledger SELECT; no storage DML granted",
        "production_mutations": 0,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
