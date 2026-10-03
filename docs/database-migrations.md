# Database migrations and production safety

## Supported schema states

The runtime SQLite database supports two starting states: an empty database and the unversioned runtime schema shipped before `runtime_schema_migrations`. The authentication database supports an empty SQLite/PostgreSQL database and the unversioned authentication schema shipped before `auth_schema_migrations`. The explicit release command applies pending migrations and records their IDs. API, worker, repository initialization, and local development startup only verify existing schema. Missing or incompatible schema fails closed; startup never repairs it.

Downgrades are intentionally unsupported. Restore a database backup taken before deployment if application rollback requires the older schema. Forward migration is idempotent and is exercised from every supported prior state in `tests/test_schema_migrations.py`.

## Migration behavior

`001_queue_integrity` rebuilds only `upload_queue` on legacy SQLite databases to add its foreign key and status/attempt constraints. Queue helpers also validate allowed processing and terminal operations before writing, including when the S3 queue backend is selected. Queue records are retention-bounded operational work, not durable evidence. Orphaned rows and invalid statuses are discarded; `queued` is normalized to `pending`, and negative attempt counts become zero. The rebuild runs in one `BEGIN IMMEDIATE` transaction. Operators should still apply it during a quiet deployment because it takes a SQLite writer lock proportional to the bounded queue size.

`002_query_indexes` adds indexes used by queue aging, evidence status/history, polling, and authentication-session queries. It also keeps only the newest active legacy session per user before adding the partial unique index.

Authentication migration `001_auth_integrity` normalizes unknown legacy roles to `operator` and installs equivalent role/email constraints for SQLite and PostgreSQL. `002_single_active_session` revokes all but the newest active legacy session per email and adds a partial unique index. PostgreSQL constraints are added `NOT VALID` and then validated, avoiding a table rewrite; validation still scans `auth_users` and briefly takes the documented PostgreSQL validation lock.

## Dialect and lifecycle notes

SQLite stores application timestamps as timezone-aware UTC ISO 8601 text because lexical ordering is part of current query behavior. Fresh PostgreSQL authentication schemas use `TIMESTAMPTZ`; psycopg values are normalized back to UTC ISO 8601 at the service boundary. Legacy PostgreSQL auth tables retain their prior text timestamp columns to avoid an automatic unbounded rewrite. Their application values remain timezone-aware UTC, but converting those columns to `TIMESTAMPTZ` requires a separately scheduled production migration.

SQLite foreign keys are enabled on every connection. PostgreSQL enforces the same authentication foreign key natively. The runtime store is single-tenant: no tenant column or tenant cascade exists, so it must not be used as a shared multi-tenant database. Upload-job deletion cascades only to the queue row with the same primary key; authentication user deletion cascades only to that user's sessions.

Legacy evidence JSON is imported exactly once into SQLite in one transaction, capped at the compatibility store's 500-row retention bound. A database marker makes SQLite authoritative after import, preventing retention deletes from resurrecting stale rows from the compatibility mirror.

The S3 upload queue is used for split-process production deployments. S3 object replacement does not provide the same atomic claim guarantee as the SQLite queue; deployments with more than one worker require an external single-consumer guarantee until conditional object writes or a database-backed distributed queue are implemented.

## Production telemetry schema

Ongoing production telemetry does not use the single-tenant runtime SQLite store or the S3 upload queue. API and worker processes coordinate through the additive PostgreSQL `telemetry` schema described in [Production Telemetry Connections](TELEMETRY_CONNECTIONS.md).

The telemetry migrations are forward-only and must run in this exact order:

1. `002_create_telemetry_connection_tables` from `backend/db/migrations/create_telemetry_connection_tables.py`
2. `003_seed_telemetry_canonical_signal_concepts_v1` from `backend/db/migrations/seed_telemetry_canonical_signal_concepts.py`
3. `004_extend_telemetry_ingestion_runtime` from `backend/db/migrations/extend_telemetry_ingestion_runtime.py`
4. `005_persist_canonical_analysis_results`
5. `006_preserve_telemetry_source_representation`
6. `007_create_relationship_temporal_state`
7. `008_create_relationship_lineage_v2_artifacts`
8. `009_create_endpoint_analysis_executions_v2`
9. `010_allow_same_concept_physical_endpoints`

`backend/db/migrations/apply_telemetry.py` remains the authoritative ordering for these nine existing migrations.

Migration 002 creates the scoped connection, secret-binding, signal, mapping, ingestion, checkpoint, observation/rejection, health, audit, and analysis-window tables. Migration 003 inserts the immutable v1 canonical concept identities. Migration 004 adds durable retry/backfill lineage, worker and analysis claims, authority snapshots, constraints, and indexes. Migration 004 refuses to run until 002 and 003 are recorded.

Application startup never applies these migrations. When `NERAIUM_TELEMETRY_DATABASE_URL` is configured, startup runs the expected-schema catalog contract and the applicable structural verifiers and fails readiness/startup if the ledger, required tables, columns, indexes, constraints, or canonical catalog are incomplete.

### Separately approved production migration procedure

Do not run this procedure without database-change approval and a verified target. The commands intentionally do not print the DSN.

Preconditions:

1. Confirm `NERAIUM_TELEMETRY_DATABASE_URL` names the intended shared PostgreSQL database, requires TLS, and is available only through an approved secret-injection/session mechanism.
2. Take and identify a restorable database snapshot/backup according to the production change plan.
3. Confirm no telemetry worker is running and no production connection is enabled. The initial rollout should occur before the telemetry UI/provider is exposed.
4. Use a dedicated migration identity with only the DDL rights needed to create/alter the `telemetry` schema and its objects. Do not use an RDS master credential in application task definitions.
5. Run the repository migration tests and a disposable PostgreSQL rehearsal first. Set `NERAIUM_TEST_POSTGRES_DSN` only in the controlled test environment.

Apply and immediately verify telemetry through the release-only identity:

```bash
# Inject NERAIUM_TELEMETRY_MIGRATION_DSN securely into the release process.
PYTHONPATH=backend ./.venv/bin/python -m db.migrations.apply_runtime --component telemetry
```

The legacy `python -m db.migrations.apply_telemetry` entrypoint now also requires
`NERAIUM_TELEMETRY_MIGRATION_DSN`; it never falls back to the runtime URL.

Then switch to the least-privilege application identity and run verification only:

```bash
PYTHONPATH=backend ./.venv/bin/python - <<'PY'
import os
import psycopg

from db.migrations.create_telemetry_connection_tables import verify as verify_002
from db.migrations.seed_telemetry_canonical_signal_concepts import verify as verify_003
from db.migrations.extend_telemetry_ingestion_runtime import verify as verify_004

with psycopg.connect(os.environ["NERAIUM_TELEMETRY_DATABASE_URL"], connect_timeout=5) as connection:
    for verify in (verify_002, verify_003, verify_004):
        verify(connection)
print("telemetry application identity verified")
PY
```

Record only the migration IDs, timestamp, database identity, operator/change reference, and successful verifier output. Do not record or paste the DSN.

### Rollback posture

Production rollback is forward-fix plus application disablement:

1. stop the telemetry worker from claiming more work;
2. disable connections through the scoped API while the current application/database remain available;
3. deploy the previously approved API/worker/frontend revision or remove the telemetry database configuration from the replacement tasks;
4. preserve the additive schema, canonical observations, lineage, audit events, and Secrets Manager entries;
5. diagnose and apply a reviewed forward migration before re-enabling ingestion.

Do not drop the production schema, delete observations, rewrite checkpoints, or infer tenant ownership for legacy/global rows. `rollback_empty_schema_for_tests(...)` accepts the literal confirmation `DROP_EMPTY_TEST_TELEMETRY_SCHEMA` and refuses nonempty schemas; it is only for disposable tests and is not a production downgrade mechanism.

### Required migration validation

Run:

```bash
PYTHONPATH=backend ./.venv/bin/pytest -q \
  tests/test_telemetry_migrations.py \
  tests/test_canonical_signal_catalog.py \
  tests/test_telemetry_ingestion_repository.py \
  tests/test_telemetry_repository.py
```

For real PostgreSQL execution and concurrency coverage, provide the separately managed test DSN and rerun the repository's PostgreSQL-gated tests. A skip caused by an unset `NERAIUM_TEST_POSTGRES_DSN` is not production migration evidence.


## PostgreSQL normalization schema

`backend/db/migrations/create_normalization_tables.py` now owns a PostgreSQL migration ledger and supports empty-schema installation and idempotent re-entry. It does not install extensions: infrastructure must install TimescaleDB explicitly. If TimescaleDB is already installed, hypertable creation uses `migrate_data => FALSE`, so startup cannot trigger an unbounded data rewrite.

The earlier unversioned normalization table keyed telemetry by `(time, signal_id)` and could collapse two sources with the same signal name. The corrected key is `(time, source_id, signal_id)`. Automatically converting a populated legacy table would require an unbounded rewrite and long lock, so the migration fails closed when it detects that unversioned table. Production operators must create the corrected table separately, copy in bounded batches while dual-writing or during a maintenance window, validate counts, swap names, and then stamp `001_create_normalization_tables`. This legacy conversion is the principal outstanding migration risk.

## Runtime and migration separation

The release command reuses the existing ledgers, without another migration system:

```bash
# Supply separate release-only DSNs, never API/worker credentials.
# NERAIUM_RUNTIME_MIGRATION_DSN
# NERAIUM_AUTH_MIGRATION_DSN
# NERAIUM_TELEMETRY_MIGRATION_DSN
PYTHONPATH=backend ./.venv/bin/python -m db.migrations.apply_runtime --component all
```

It validates all required inputs before making changes, then migrates shared
runtime, auth, and telemetry in that order. Nonzero exit status must stop the
release before runtime deployment. Auth and runtime apply in transactions with
their existing advisory locks; telemetry keeps its existing forward-only,
per-migration transactions. A partially completed telemetry release is resumed
explicitly; runtime refuses intermediate V2 ledger states.

Shared PostgreSQL v1 creation moved unchanged to
`backend/db/migrations/runtime_postgres_v1.sql`, invoked only by
`backend/db/migrations/runtime_postgres.py`. The authoritative ledger is
`neraium_runtime.postgres_runtime_migrations` with version 1. The empty
`runtime_schema_migrations` table in that schema is retained for compatibility;
it is not the PostgreSQL version authority. Already migrated v1 databases need
no new DDL or version stamp. Incompatible populated/unversioned targets fail;
there is no automatic catalog adoption or repair.

SQLite keeps the 001–014 runtime ledger and 001–003 auth ledger, with their
existing upgrade logic in `runtime_sqlite.py` and `auth_schema.py`. Run migration
before local API/worker startup or tests that allocate a new runtime directory:

```bash
PYTHONPATH=backend ./.venv/bin/python -m db.migrations.apply_runtime --sqlite-dir /path/to/runtime
```

The separate connector executor's existing unversioned replay database is also
initialized explicitly through the same command:

```bash
PYTHONPATH=backend ./.venv/bin/python -m db.migrations.apply_runtime --connector-replay-db /path/to/replay.sqlite3
```

The replay store retains its existing table, index and replay semantics. This
local preparation is required on each new executor storage volume before the
executor starts. No new replay migration ledger is introduced.

Reviewed expected-schema contracts live under
`backend/app/services/schema_contracts/`. They describe migration-built fixture
state, not an inspected production catalog. PostgreSQL verification checks
required columns (types, nullability, identity/generated state and defaults),
index definitions and validity, validated constraints, sequence types/ownership
links, function signatures/bodies/security-definer state, and enabled trigger
definitions. SQLite verification checks columns, key/index definitions, foreign
keys, integrity triggers and ledger IDs. SQLite opens with `mode=ro` and
`query_only`; PostgreSQL startup verification uses read-only transactions.
Supported legacy auth text timestamps are explicit in the contract.

Required object or ledger mismatches raise `SchemaIncompatibilityError` with a
`schema_incompatible:<schema>:<object-kind>:<object>` diagnostic. Version ledgers
must match a supported complete release state. Extra non-required objects are
allowed. V1 telemetry can use the completed V1 or completed V2 schema; requesting
V2 requires all nine telemetry migrations. No verification step performs DDL,
ledger writes, sequence advancement or schema repair. Runtime URLs never resolve
migration DSNs. Existing auth production identity restrictions remain enforced.

See [runtime DDL elimination qualification](runtime-ddl-elimination.md) for the
startup trace, disposable database results and scope limitations.
