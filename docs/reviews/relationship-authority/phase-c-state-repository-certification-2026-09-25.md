# Phase C relationship temporal-state repository certification

**Candidate:** `fix/deterministic-governed-output` at baseline `2c21dc70e716299112ce81128d0f8c4ab3b1c4bf`
**Decision:** `PHASE_C_STATE_REPOSITORY_CERTIFIED_FOR_COMMIT`
**Analytical freeze:** `ANALYTICAL_MATH_CHANGED: NO`

## State contract

The additive `007_create_relationship_temporal_state` migration creates one current head keyed by resource, tenant, workspace, and facility scope, system, nullable asset, and relationship lineage. The versioned `relationship-temporal-state.v1` envelope is bounded to eight observations and carries a compatibility digest, head event ref/time, integrity digest, and storage revision. The migration does not backfill, inspect, or reconstruct historical records.

## Scope and authorization

Repository reads and writes bind every key dimension. PostgreSQL verification confirmed state is isolated across scope, system, asset, and lineage. Lineage and state digests provide identity/integrity only; they do not authorize access. State is not loaded into the analytical reducer. Temporal continuation and Phase D–F work are absent.

## Transaction and replay verification

Real PostgreSQL tests use a uniquely named temporary database, apply the repository migrations, and drop only that test database. They verified initial creation; exact replay without revision advance; conflicting same-ref/different-time replay; conflicting interval evidence; stale revision and stale head rejection; out-of-order rejection; two competing writers from the same expected head; unchanged persisted state after rejected operations; and independent scope/system/asset/lineage heads.

The first real database run exposed an insert binding defect: the scope values were inserted in a different column order from the read key. The insert parameter order was corrected. The focused transaction suite then passed, including the concurrency and persisted-state assertions.

## Test results

Using the repository's disposable PostgreSQL runner with its unrelated test commands replaced by the focused Phase C command:

```text
22 passed, 2 deselected
```

The deselected cases test unrelated ingestion and result-artifact migrations against a pre-migrated shared database. `git diff --check` passed. No broad regression, LBNL, wastewater, scale, or performance suites were run.

## Exact commit allowlist

- `backend/app/services/telemetry_repository.py`
- `backend/app/services/telemetry_runtime.py`
- `backend/db/migrations/create_relationship_temporal_state.py`
- `tests/test_telemetry_migrations.py`
- `tests/test_relationship_temporal_state_repository.py`
- `tests/test_relationship_temporal_state_postgres.py`
- `docs/reviews/relationship-authority/phase-c-state-repository-certification-2026-09-25.md`

**Suggested commit subject:** `Add scoped relationship temporal state repository`
