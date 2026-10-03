# Runtime DDL elimination and migration separation

Repository decision: **PASS** after disposable qualification. This work starts
from `fa466bb2` on `fix/deterministic-governed-output`. Production was not
contacted, modified, migrated or deployed. Production catalog state, credentials,
ownership and grants remain uninspected; this is repository qualification only.

## Startup trace and classification

| Path before this change | DDL capability and callers | Classification and disposition |
| --- | --- | --- |
| `app.main.app_lifespan` → `runtime_db.init_runtime_db` | Creates SQLite foundations, ledger, indexes, triggers; applies runtime upgrades 001–014, including table rebuilds, ALTER and DROP. Also reached through `upload_jobs.configure_runtime_dir`, evidence/finding/governance repositories, telemetry compatibility helpers and maintenance. | **MIGRATION-ONLY**. Moved to `db.migrations.runtime_sqlite`; all ordinary callers now verify. |
| `app.entrypoint.run_worker`, `app.live_analysis_worker.main` → runtime initialization | Same shared initializer through worker configuration and repository use. | **RUNTIME REQUIRED** verification, **MIGRATION-ONLY** DDL. No migration invocation remains. |
| `runtime_postgres.initialize` | Creates schema when absent; always issues `CREATE TABLE IF NOT EXISTS postgres_runtime_migrations`; installs v1 tables/indexes/sequences/function/triggers and ledger row when absent. Even installed v1 requires CREATE, causing the known SQLSTATE 42501 blocker. | **MIGRATION-ONLY** creation moved to `db.migrations.runtime_postgres`. Runtime uses a read-only catalog/ledger contract with no initialization cache that could conceal damage. |
| `auth_store._get_backend` → `ensure_schema` | Production PostgreSQL previously verified only; SQLite and other environments created foundations/indexes/auth ledger and applied 001–003, ALTER constraints and SQLite triggers. | **MIGRATION-ONLY** code moved to `db.migrations.auth_schema`. Every runtime environment now verifies. Explicit `migrate_schema` remains an offline caller. Failed verification cannot publish a cached backend; API startup also re-verifies cached auth state. |
| `telemetry_runtime.verify_readiness` / repository constructors | Existing structural verifiers only; nine ordered migration implementations already live under `db.migrations`. | **RUNTIME REQUIRED** read-only verification. Added complete V1/V2 catalog contracts, including function and integrity-trigger definitions, in read-only transactions. No telemetry DDL was invoked by startup. |
| Auth bootstrap and legacy auth/evidence JSON import | Inserts/updates existing rows, imports compatibility data, records existing markers. No schema creation or ORM table creation. | **RUNTIME REQUIRED** existing DML semantics retained. |
| Runtime compatibility auth tables, PostgreSQL `runtime_schema_migrations` table, retired connection implementation | Shared v1 preserves compatibility structures. PostgreSQL uses its own version-1 ledger; its compatibility SQLite-named ledger is empty. Legacy connections remain disabled in production. | **LEGACY/OBSOLETE** compatibility objects retained in explicit migration; no analytical/evidence rewrite or schema adoption. |
| `db.migrations.create_normalization_tables` | Explicit PostgreSQL normalization ledger/tables/indexes and optional hypertable operation. No API/worker startup caller; extension installation remains external. | **MIGRATION-ONLY**, existing behavior retained. Legacy populated unversioned conversion still fails closed as documented. |
| `ConnectorExecutionBroker.__init__` | Separate connector executor, outside ordinary API/worker construction; creates local SQLite replay table/index. | **MIGRATION-ONLY** preparation moved to `db.migrations.connector_replay` via the same offline command. Existing unversioned store retained; executor now verifies. |
| Live production schemas, owners, grants, extensions | Not inspected in this task. | **UNKNOWN** live state, not an unresolved repository startup path. |

A search across backend Python/SQL found no remaining CREATE TABLE/SCHEMA/INDEX/
FUNCTION/EXTENSION, ALTER TABLE, DROP TABLE or ORM `create_all` outside the
explicit migration directory. The runtime SQL adapter, advisory transaction
locks, S3 queue coordination and normal repository SQL remain unchanged.

## Explicit migration path and completeness

Run `python -m db.migrations.apply_runtime --component all` with the dedicated
`NERAIUM_RUNTIME_MIGRATION_DSN`, `NERAIUM_AUTH_MIGRATION_DSN`, and
`NERAIUM_TELEMETRY_MIGRATION_DSN`. Inputs are checked before mutation; order is
shared runtime, auth, then the authoritative nine telemetry migrations. Failures
return nonzero and stop the migration release gate. API/worker startup never
invokes this command or resolves these credentials. The existing auth and
telemetry entrypoints also use release-only DSNs and fail on migration errors.
Deployment must be gated on command success; no deployer or task binding was
changed in this repository-only task.

All schema objects required by the inspected API/worker paths are represented
by explicit migrations. Shared v1 SQL was moved byte-for-byte, retaining version
1 and all evidence constraints. SQLite foundations and upgrades and auth
foundations/upgrades were moved without changing row transformations. The replay
store gained explicit offline ownership through the same migration command,
without another ledger. No new production version stamp or inferred live-catalog
migration was added.

Qualification installs from a clean database and re-enters the currently
expected pre-change shared PostgreSQL version-1 schema idempotently. Existing
SQLite unversioned/previous-version upgrade tests still pass. Unknown production
catalogs are not claimed to match these fixtures.

## Expected-schema verification

The seven checked-in contracts cover PostgreSQL shared runtime and auth,
telemetry V1/V2, SQLite runtime/auth, and connector replay. Required columns,
indexes and key definitions, sequences and owning columns, validated PostgreSQL
constraints, functions and enabled integrity triggers are verified structurally,
then complete ledger state is checked. Supported legacy PostgreSQL auth text
timestamps are explicit. V1 telemetry accepts a completed V1 or V2 schema;
partial V2 states fail. Extra non-required objects are allowed.

Missing objects or incompatible definitions raise `SchemaIncompatibilityError`
with an object-level `schema_incompatible` diagnostic. PostgreSQL startup runs
in read-only transactions; SQLite verification opens existing files with
`mode=ro` and `query_only`. Normal SQLite connections require an existing file.
No verifier creates objects, writes ledgers, advances sequences, adopts missing
schema, repairs state, or falls back to release credentials.

## Disposable database results

PostgreSQL **16.15**, `postgres:16-alpine`, network disabled, with local TLS
configured. Tests used only that container's network namespace and the locked
repository virtual environment. Each qualification run created its own database,
a non-superuser migration owner, a distinct restricted runtime role, and a
no-privilege GRANT probe role, then removed them. The PostgreSQL container was
removed after verification. No production DSN or cloud credential was used.

The **26 new least-privilege checks pass**:

- Migration identity installs all required schema from empty state and re-enters
  idempotently using the existing ledgers.
- Actual API lifespan reaches HTTP 200 health and readiness; dedicated worker
  startup performs an ordinary iteration; standalone live-analysis worker runs
  once. Database startup/auth/telemetry code is real. Cloud S3 artifact/heartbeat
  I/O is replaced with a local fake; no cloud persistence claim is made.
- Runtime auth user/password, workspace, session replacement/revocation,
  telemetry connection/discovery/mapping, observation/checkpoint persistence,
  worker claim/completion, shared payload mutation, evidence/finding persistence,
  audit identity sequences and transaction rollback succeed. Stored analytical
  payloads and finding evidence remain exact.
- CREATE TABLE, ALTER TABLE, DROP TABLE, CREATE SCHEMA/ROLE/INDEX/FUNCTION/
  SEQUENCE/TEMP TABLE/EXTENSION and migration-ledger writes are denied with
  SQLSTATE **42501**. Role membership GRANT and table ownership changes are
  denied. Unauthorized table GRANT may complete with PostgreSQL's warning but
  grants no effective privilege; that effect is asserted explicitly.
- A removed required index and renamed-away table/column, and a disabled evidence
  trigger, cause repeated initialization and both API/worker startup to fail.
  Runtime does not recreate or re-enable anything. Function/sequence removal,
  missing ledger state and a missing V2 integrity trigger also fail closed.
  Missing telemetry ledger tables/columns report schema incompatibility through
  API and worker startup and leave the damaged catalog unchanged.
- Schema checks succeed with `default_transaction_read_only=on` and leave
  catalogs unchanged. SQLite authorizer tests reject any writes/DDL during
  verification, and missing databases/objects remain absent.

Existing focused tests report **323 passed**, with two PostgreSQL-gated cases
skipped in that local-only run and seven integration cases deselected. The two
migration cases are subsequently executed against the disposable PostgreSQL
instance, together with bounded shared-storage integration checks.

Two existing PostgreSQL shared-storage cases that build the synthetic consequence
fixture fail before persistence at
`datasets/verification_consequence.py:176` (`status == 'quantified'`). The same
fixture assertion fails from an untouched `git archive fa466bb2` backend. These
analytical fixture failures are pre-existing; analytical code and those cases
were not changed. They are excluded from the final bounded PostgreSQL run;
new restricted-role evidence/finding preservation checks pass independently.

The final disposable PostgreSQL run reports **50 passed, 2 deselected**, with
no skips. It includes all 26 new qualification cases, the bounded existing
shared-storage cases and both previously gated telemetry migration cases. Final
API/worker and verification regression checks report **88 passed, 2 skipped**;
those two skips are the telemetry cases executed in the PostgreSQL run above.

Reproduce the final PostgreSQL checks only against an explicitly disposable
instance, setting both `NERAIUM_TEST_POSTGRES_DSN` and
`NERAIUM_TEST_RUNTIME_POSTGRES_DSN` to that instance's admin test DSN:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q -m 'integration or not integration' \
  tests/test_runtime_least_privilege_postgres.py \
  tests/test_pilot_shared_state.py tests/test_telemetry_migrations.py \
  -k 'not postgres_replay_preserves_exact_artifacts_and_scope and not postgres_finding_and_governance_immutability'
```

The final local startup checks were:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q \
  tests/test_runtime_schema_verification.py tests/test_entrypoint.py \
  tests/test_phase3_auth_runtime.py tests/test_operational_lifecycle.py \
  tests/test_telemetry_scheduler.py tests/test_telemetry_migrations.py
```

The broad focused 323-pass run additionally covers SQLite upgrade and migration
rollback behavior, health-relevance migrations, governance lifecycle/audit
storage boundaries, auth, connector replay/admission, telemetry repositories,
and canonical catalog migration behavior. It runs storage tests affected by
relocation, without changing their analytical assertions.

`git diff --check` passes. No unrelated analytical/certification suite was run.

## Preservation and scope

Shared runtime schema SQL is byte-identical after relocation. Repository
queries, dialect conversion, evidence hashing/projections, analytical engines,
existing authority semantics and transaction locks are unchanged. Only explicit
SQLite migration now wraps foundation creation and upgrades in one transaction.
Tests demonstrate evidence/finding payload preservation, concurrent shared
mutation, session revocation, queue claim, snapshot import/rollback and read-only
schema verification.

The two pre-existing historical-ingestion edits and unrelated untracked
research/evidence were preserved and excluded. No production action, credential
change, push or deployment occurred.

## Exact bounded file manifest

The commit contains these 43 file changes (the shared v1 SQL is one rename).
Historical-ingestion files and unrelated untracked artifacts are excluded.

| Change | Path |
| --- | --- |
| Modified | `README.md` |
| Modified | `backend/app/entrypoint.py` |
| Modified | `backend/app/main.py` |
| Modified | `backend/app/services/auth_store.py` |
| Modified | `backend/app/services/connector_execution.py` |
| Modified | `backend/app/services/runtime_db.py` |
| Modified | `backend/app/services/runtime_postgres.py` |
| Added | `backend/app/services/schema_contracts/auth_postgres.json` |
| Added | `backend/app/services/schema_contracts/auth_sqlite.json` |
| Added | `backend/app/services/schema_contracts/connector_replay.json` |
| Added | `backend/app/services/schema_contracts/runtime_postgres.json` |
| Added | `backend/app/services/schema_contracts/runtime_sqlite.json` |
| Added | `backend/app/services/schema_contracts/telemetry_v1.json` |
| Added | `backend/app/services/schema_contracts/telemetry_v2.json` |
| Added | `backend/app/services/schema_verification.py` |
| Modified | `backend/app/services/telemetry_runtime.py` |
| Added | `backend/db/migrations/apply_runtime.py` |
| Modified | `backend/db/migrations/apply_telemetry.py` |
| Added | `backend/db/migrations/auth_schema.py` |
| Added | `backend/db/migrations/connector_replay.py` |
| Added | `backend/db/migrations/runtime_postgres.py` |
| Renamed unchanged | `backend/app/services/runtime_postgres_v1.sql` → `backend/db/migrations/runtime_postgres_v1.sql` |
| Added | `backend/db/migrations/runtime_sqlite.py` |
| Modified | `docs/PILOT_PRODUCTION_FINISH.md` |
| Modified | `docs/database-migrations.md` |
| Added | `docs/runtime-ddl-elimination.md` |
| Modified | `scripts/migrate_auth_schema.py` |
| Modified | `tests/conftest.py` |
| Modified | `tests/test_connector_execution.py` |
| Modified | `tests/test_connector_executor_body_limit.py` |
| Modified | `tests/test_governance_audit_boundaries.py` |
| Modified | `tests/test_governance_lifecycle.py` |
| Modified | `tests/test_health_relevance_migrations.py` |
| Modified | `tests/test_operational_lifecycle.py` |
| Modified | `tests/test_ot_infrastructure_candidate.py` |
| Modified | `tests/test_ot_readonly_boundary.py` |
| Modified | `tests/test_phase3_auth_runtime.py` |
| Modified | `tests/test_pilot_shared_state.py` |
| Added | `tests/test_runtime_least_privilege_postgres.py` |
| Added | `tests/test_runtime_schema_verification.py` |
| Modified | `tests/test_schema_migrations.py` |
| Modified | `tests/test_telemetry_migrations.py` |
| Modified | `tests/test_telemetry_scheduler.py` |
