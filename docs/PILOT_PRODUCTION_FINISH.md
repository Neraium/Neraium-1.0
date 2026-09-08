# Pilot production finish

Baseline: main `011bda9c`, reviewed against open PR #130 on 2026-09-08.
No production environment was contacted, deployed, seeded, or migrated.

## Already complete on main

- Standalone `neraium-consequence` integration and certification (#125, #128):
  the adapter delegates integration to the pinned package, requires finding-owned
  windows, supported operating context, explicit resource/unit mapping and gap
  bounds, and retains provenance. Insufficient evidence stays not quantifiable.
- Historical attribution projection (#129), immutable result/evidence identity,
  scope checks, and persisted replay reads. Missing replay is not regenerated.
- PostgreSQL auth, rotating RDS credential support, persistent sessions, user
  activation and revocation APIs, and database-enforced single active sessions.
- Governance contracts, append-only human review, and runtime integration
  (#131–134). These remain evidence and review records without actuation.
- Current dashboard language and consequence projection. No dashboard redesign
  or frontend source change is included.

## Gaps closed

1. PR #130 was not merged: its replay sanitizer, evidence schema exclusion, and
   opt-in isolated verification fixture are carried forward. Results with
   `not_generated` / `inline_replay_disabled` and an empty timeline keep their
   legitimate 404s. The fixture verifies HTTP evidence, finding, replay and
   frontend projection against persisted consequence and hashes, with writes
   and analytical recalculation forbidden during reads.
2. Runtime SQLite was local to API/worker mounts. Production now requires
   `NERAIUM_RUNTIME_DATABASE_URL`, pointing every task at the same PostgreSQL
   database with `sslmode=require`, `verify-ca`, or `verify-full`. The dedicated
   `neraium_runtime` schema preserves existing columns, JSON text, constraints,
   append-only triggers and transaction boundaries. Local/test SQLite remains
   the fallback when no URL is configured. The schema includes existing legacy
   tables for compatibility; it creates no new analytical authority.
3. Shared runtime state includes upload job mirrors, evidence and finding
   identity, workflow events, operator outcomes, health-relevance records,
   facility context, behavioral-model and governance ledgers, and audit records.
   Existing S3 upload artifacts, queue objects and worker heartbeats remain in
   S3; production telemetry remains in its existing PostgreSQL repository.
4. PostgreSQL transaction locks serialize runtime mutations and existing S3
   queue transitions across tasks. A second worker cannot claim the same pending
   job. Startup recovery only considers processing records older than the
   configured worker heartbeat timeout; missing or malformed timestamps do not
   establish abandoned ownership. Processing is never automatically recomputed.
5. Behavioral-model reads refresh persisted updates from other workers. Shared
   SII state reads/writes fail on database failure instead of silently falling
   back to a stale task-local file or hiding failed persistence.
6. Auth schema startup is serialized. Session creation rechecks activation under
   the same database lock used by activation/deactivation; deactivation and
   session revocation commit together. Bootstrap creation cannot overwrite a
   concurrently created account, and ordinary restarts preserve deactivation
   and role changes. Reactivation remains an explicit admin operation.
7. Historical product projections also omit obsolete failure-probability and
   remaining-life fields, including facility intelligence. Raw evidence,
   consequence, provenance and human-authored history are preserved.

## Release prerequisites (not performed here)

The current deployment configuration must be updated before deploying this
branch. Startup deliberately fails if production lacks the shared runtime URL.

- Inject `NERAIUM_RUNTIME_DATABASE_URL` as a task secret for **all** API and worker
  tasks. Use an appropriately provisioned database role on the existing RDS
  service; the role must be able to create/migrate `neraium_runtime`. Keep auth
  credentials and its rotating-secret configuration unchanged. Runtime DSN
  secret rotation requires replacing tasks so they receive the new secret.
- Drain writers and take consistent offline SQLite backups from each existing
  runtime mount. Preserve the original backups and S3 objects. Do not run old
  SQLite writers concurrently with the PostgreSQL version.
- Validate each backup using the explicit copy command below, then apply the
  verified copy while writers remain stopped. JSON text, identities, hashes and
  timestamps are copied verbatim; no analysis is invoked. Conflicting target
  rows or legacy rows missing a stable scoped identity abort the transaction.
  Such conflicts require a reviewed migration decision; the tool does not pick
  a winner or invent scope. A dry run rolls back copied rows but may initialize
  an empty target schema. It never alters the source database.

```sh
# DSN must already be injected securely. No credentials in command history.
PYTHONPATH=backend python -m app.services.runtime_postgres_import /backup/runtime.db
PYTHONPATH=backend python -m app.services.runtime_postgres_import /backup/runtime.db --apply
```

- Retain database backups and configure operational monitoring for the runtime
  database and lock timeouts. The pilot preserves single-writer transaction
  semantics; this is not a throughput/scaling claim.
- Require green GitHub CI. After separately authorized deployment, verify
  readiness, cross-task persistence and existing sessions through a restart.
  Follow the [isolated replay runbook](REPLAY_VERIFICATION_FIXTURE.md) only when
  that verification operation is explicitly authorized. Customer history must
  never be reconstructed to manufacture a successful replay.

## Focused verification

The implementation was checked using focused replay/auth/projection/config and
model-store tests, plus an isolated local PostgreSQL server. PostgreSQL checks
cover separate-process runtime mutation, fresh auth backend instances,
concurrent startup/session replacement, revocation and activation, persisted
HTTP replay with S3 artifacts, governance/finding immutability, queue claim and
restart behavior, and verbatim snapshot-copy/rollback/identity-sequence behavior.
The existing CI PostgreSQL script now runs these integration tests as well.
No full suites, historical datasets, browser tests, Docker, AWS, benchmarks,
security scans or deployment validation were run locally.

## Existing open PR disposition

- **#130: CLOSE AS SUPERSEDED** after this PR merges; its complete work is included.
- **#114: KEEP** as optional dashboard cleanup requiring rebase and renewed review
  against the later dashboard redesign. It is not a pilot prerequisite.
- **#44, #36, #35: CLOSE AS SUPERSEDED** by subsequent dashboard/workflow work.
  Their old rollback/repair changes should not be merged into the current UI.
- **#39: CLOSE AS SUPERSEDED**; connector smoke verification is already complete
  and the PR changes no production code.

These are recommendations only. No existing PR was modified or merged.
