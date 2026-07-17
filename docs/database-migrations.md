# Database migrations and production safety

## Supported schema states

The runtime SQLite database supports two starting states: an empty database and the unversioned runtime schema shipped before `runtime_schema_migrations`. The authentication database supports an empty SQLite/PostgreSQL database and the unversioned authentication schema shipped before `auth_schema_migrations`. Startup applies all pending migrations transactionally and records their IDs.

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


## PostgreSQL normalization schema

`backend/db/migrations/create_normalization_tables.py` now owns a PostgreSQL migration ledger and supports empty-schema installation and idempotent re-entry. It does not install extensions: infrastructure must install TimescaleDB explicitly. If TimescaleDB is already installed, hypertable creation uses `migrate_data => FALSE`, so startup cannot trigger an unbounded data rewrite.

The earlier unversioned normalization table keyed telemetry by `(time, signal_id)` and could collapse two sources with the same signal name. The corrected key is `(time, source_id, signal_id)`. Automatically converting a populated legacy table would require an unbounded rewrite and long lock, so the migration fails closed when it detects that unversioned table. Production operators must create the corrected table separately, copy in bounded batches while dual-writing or during a maintenance window, validate counts, swap names, and then stamp `001_create_normalization_tables`. This legacy conversion is the principal outstanding migration risk.
