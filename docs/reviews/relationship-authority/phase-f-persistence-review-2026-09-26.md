# Phase F governed temporal-state persistence review

**Repository:** `/home/ubuntu/Neraium-1.0`
**Branch:** `fix/deterministic-governed-output`
**Baseline:** `bb6cd928d36ea52692816356a8ba3ea0e7646465`
**Decision:** `PHASE_F_PERSISTENCE_READY_FOR_REVIEW`
**Analytical freeze:** `ANALYTICAL_MATH_CHANGED: NO`

## Persistence contract

After the authoritative Phase E evaluation passes its success checks, the
Phase F gate reads only the authoritative result's producer-issued relationship
evidence registry and lineage. It derives the bounded state from the existing
temporal reducer observations and uses the Phase C PostgreSQL repository's
compare-and-swap operation. The head event ref commits to the certified lineage,
source evidence ref, and governed interval; its event time is the current
evidence's governed `current_end`.

The repository adapter accepts an existing `TelemetryScopeRef` or converts the
exact authenticated Phase 4 scope to the repository contract, preserving
tenant, workspace, resource scope, and the certified workspace facility.
Phase D reads and state validation use that same exact repository scope.

## Authority, replay, and isolation

The end-to-end test uses real canonical telemetry windows, `evaluate_sii`,
producer evidence finalization, producer lineage issuance and verification, the
Phase F gate, and the Phase C PostgreSQL repository. It verifies first-head
creation, compatible advancement by one revision, exact replay without a new
revision or reducer observation, conflicting replay rejection, stale CAS,
out-of-order rejection, and unchanged state after rejected writes.

Scope, system, asset, and lineage lookups remain isolated. An authentic
producer-finalized graph-failure fallback, missing registry, tampered source or
lineage, and a valid re-finalized state with an incompatible compatibility
digest do not advance state. Presentation, ranking, group, primary, persistent
column, and runtime labels do not select identity. The repository's eight
observation limit is enforced.

Discovery still runs under the Phase E persistence suppression path. The test
observes two evaluations per production continuation: discovery has no prior
state input, and only the successful authoritative evaluation receives
compatible prior state. A failed authoritative evaluation does not write.
Simulated persistence failure leaves the completed analytical result unchanged
(excluding runtime duration metadata).

## Analytical invariance

No relationship reducer, threshold, eligibility, quality/context, ranking,
consequence, telemetry admission, governance, or presentation calculations
changed. Current producer evidence and result-local ownership remain the source
of authority.

## Verification

Using a disposable PostgreSQL 16 container and a unique temporary database
created/dropped by each integration test:

```text
tests/test_relationship_temporal_persistence_phase_f.py
tests/test_relationship_temporal_state_postgres.py
tests/test_relationship_temporal_state_repository.py
tests/test_relationship_temporal_state_loading.py
tests/test_relationship_temporal_continuation.py
tests/test_relationship_evidence_binding.py
tests/test_relationship_binding_ownership.py

91 passed, 2 warnings
git diff --check: passed
```

The original end-to-end attempt exposed a repository scope-type mismatch that
silently prevented Phase F writes; the same mismatch prevented Phase D from
validating stored state for continuation. The adapter correction is covered by
the real create/continue/replay flow above.

## Commit allowlist

- `backend/app/services/relationship_temporal_state.py`
- `backend/app/services/telemetry_analysis_window.py`
- `tests/test_relationship_temporal_persistence_phase_f.py`
- `tests/test_relationship_temporal_continuation.py`
- `docs/reviews/relationship-authority/phase-f-persistence-review-2026-09-26.md`

**Suggested commit subject:** `Persist governed relationship temporal state`
