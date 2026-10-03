-- CANDIDATE ONLY. Run with the controlled migration identity AFTER backups,
-- schema migration, ownership and effective PUBLIC/inherited grant review.
-- Provision the runtime password/managed secret separately, without logging it.
-- This changes no table ownership, data, or existing runtime credential.
BEGIN;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'neraium_auth_runtime') THEN
    CREATE ROLE neraium_auth_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOREPLICATION NOBYPASSRLS NOINHERIT;
  END IF;
END $$;
ALTER ROLE neraium_auth_runtime NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS NOINHERIT;
REVOKE ALL ON SCHEMA public FROM neraium_auth_runtime;
GRANT USAGE ON SCHEMA public TO neraium_auth_runtime;
REVOKE ALL ON TABLE public.auth_users, public.auth_workspaces,
  public.auth_workspace_members, public.auth_sessions,
  public.auth_schema_migrations FROM neraium_auth_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.auth_users,
  public.auth_workspaces, public.auth_workspace_members,
  public.auth_sessions TO neraium_auth_runtime;
GRANT SELECT ON TABLE public.auth_schema_migrations TO neraium_auth_runtime;
-- PUBLIC grants and SET ROLE memberships can override direct REVOKE; the
-- runtime verifier rejects CREATE, ownership and migration-ledger writes.
COMMIT;
