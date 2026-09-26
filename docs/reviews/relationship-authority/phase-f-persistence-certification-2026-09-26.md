# Phase F governed temporal-state persistence certification

**Repository:** `/home/ubuntu/Neraium-1.0`
**Branch:** `fix/deterministic-governed-output`
**Baseline:** `bb6cd928d36ea52692816356a8ba3ea0e7646465`
**Decision:** `PHASE_F_PERSISTENCE_CERTIFIED_FOR_COMMIT`
**Analytical freeze:** `ANALYTICAL_MATH_CHANGED: NO`

## Independent certification

The Phase F integration point is reached only for production evaluation with a temporal repository. Discovery runs first inside the Phase E persistence-suppression context; Phase F persistence is not called there. The authoritative evaluation then receives only Phase D-approved prior state, if any. A non-dict or `status == failed` authoritative result exits before the write gate. The write gate runs after those checks and catches storage errors without changing the completed result.

The writer obtains candidates and evidence exclusively from the authoritative result's compatibility relationship model and result-local finalized evidence registry. It resolves each candidate against the authenticated scope, verifies the producer-issued lineage descriptor, and checks exact tenant, workspace, resource scope, system, and asset bindings. It requires producer-owned temporal observations, source reference, governed interval, and a bounded history. Fallback, missing or tampered registry/lineage/evidence, and incompatible stored state fail closed. No heuristic, presentation, ranking, group, primary, persistent-column, or runtime identity is used.

The only persistence operation is the Phase C `PostgreSQLTelemetryRepository.compare_and_swap_relationship_temporal_state`. The first head uses expected revision `0` and no expected head. Continuations use the revision and head read from the exact state key. The Phase C transaction takes a PostgreSQL transaction advisory lock for the full identity (including absent keys), locks existing rows with `FOR UPDATE`, checks revision and head, rejects non-increasing event time and conflicting interval evidence, and updates under a revision predicate. Exact event/time/compatibility/reducer replay returns idempotently without revision advance. Competing writers from one expected head cannot both advance.

Phase D compatibility is recomputed from the finalized evidence and certified lineage, including semantic, reducer, identity, parameter, reference, and context bindings. An existing state with a different compatibility digest is not written over. The eight-observation bound is enforced by the projection gate, Phase C repository envelope, and Phase D read validator.

Current-run evidence and result-local ownership remain authoritative. The diff adds no relationship math, thresholds, eligibility, context/quality, ranking, consequence, telemetry admission, governance, or presentation behavior.

## Verification

Focused unit run:

```text
PYTHONPATH=backend .venv/bin/python -m pytest -q \
  tests/test_relationship_temporal_persistence_phase_f.py \
  tests/test_relationship_temporal_continuation.py
```

Result: 10 passed; 1 skipped because no PostgreSQL DSN was configured for that initial run.

Real PostgreSQL 16 run used a disposable TLS-enabled container and unique temporary databases created and dropped by the tests:

```text
PYTHONPATH=backend .venv/bin/python -m pytest -q \
  tests/test_relationship_temporal_persistence_phase_f.py \
  tests/test_relationship_temporal_state_postgres.py \
  tests/test_relationship_temporal_continuation.py
```

Result: 12 passed, 2 warnings. This exercised real Phase F first write, continuation, replay, rejection cases, exact-key isolation, stale CAS, out-of-order behavior, and competing PostgreSQL writers. The disposable PostgreSQL container was stopped after the run. `git diff --check` passed.

## Exact commit allowlist

- `backend/app/services/relationship_temporal_state.py`
- `backend/app/services/telemetry_analysis_window.py`
- `tests/test_relationship_temporal_persistence_phase_f.py`
- `tests/test_relationship_temporal_continuation.py`
- `docs/reviews/relationship-authority/phase-f-persistence-certification-2026-09-26.md`

**Suggested commit subject:** `Persist governed relationship temporal state`
