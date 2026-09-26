# Relationship authority A–F closeout certification

**Repository:** `/home/ubuntu/Neraium-1.0`  
**Branch:** `fix/deterministic-governed-output`  
**Certified HEAD:** `4993ef38b712633ad9ab0a216ebb87df49328b54`  
**Decision:** `RELATIONSHIP_TEMPORAL_AUTHORITY_A_F_CERTIFIED`  
**Analytical freeze:** `ANALYTICAL_MATH_CHANGED: NO`

## AUTHORITY CHAIN

Independently inspected the committed A–F implementation and artifacts at the certified HEAD. Phase A projects canonical endpoint identity and mapping provenance from validated observation lineage. Phase B issues deterministic relationship lineage only from authenticated Phase 4 scope, server-bound system/asset identity, endpoint authority, and result-local producer evidence. Resolution checks exact evidence/source/assessment binding and lineage descriptor. No raw-name, ranking, grouping, primary, persistent-column, presentation, runtime, or heuristic identity supplies authority. Fallback lineage remains continuation-ineligible.

## TEMPORAL CHAIN

Phase C keys one bounded `relationship-temporal-state.v1` head by tenant, workspace, resource scope, system, nullable asset, and relationship lineage. Phase D reads the exact key and returns prior reducer state only after authenticated scope, lineage, evidence binding, compatibility, reducer identity, version, bounds, chronology, head, and integrity digest validation. Invalid or incompatible prior state is not used. Phase E derives current evidence through no-prior discovery and passes only certified compatible history to the authoritative reducer. Phase F projects state only from the successful authoritative result's finalized relationship model and result-local registry.

## PHASE 4 ISOLATION

Discovery is enclosed by the Phase 4 persistence-suppression ContextVar, restored in `finally`. The guard prevents behavioral store construction/loading and the resulting model, snapshot, learning-decision, baseline, and event persistence path during discovery. The authoritative evaluation is the sole unsuppressed Phase 4 evaluation. Temporal state is written only afterward through the Phase F gate.

## CAS / CONCURRENCY

The PostgreSQL repository binds every key dimension, validates the versioned bounded envelope and integrity digest, serializes writers with a transaction advisory lock including absent heads, locks existing rows, checks expected revision/head, and applies revision-predicate updates. Real PostgreSQL tests verified independent exact keys and competing writers from one expected head; exactly one writer advanced.

## REPLAY / ORDERING

Exact event/time/compatibility/reducer replay is idempotent without revision or reducer-vote advance. Conflicting same-event replay, conflicting interval evidence, stale revision/head, and out-of-order updates are rejected. Continuation additionally refuses older current evidence and conflicting same-time evidence before supplying prior history.

## FAIL-CLOSED BEHAVIOR

Missing or invalid authority, lineage, compatibility, bounds, or integrity does not admit prior state or persistence. Repository/read failures leave current-run analysis on the no-prior path. Failed authoritative evaluation exits before Phase F. Phase F storage errors are caught after analysis completion and cannot alter the successful result/status. Discovery/read failures likewise retain the normal current-run evaluation.

## OWNERSHIP INVARIANCE

Current-run evidence and assessment ownership remain bound to their exact result-local producer records. No state is borrowed across tenant, workspace, resource scope, system, asset, or lineage. Phase F resolves each candidate against its own evidence and lineage descriptor. Grouping, ranking, primary selection, or sibling evidence does not confer ownership.

## POSTGRESQL VERIFICATION

Ran against a disposable TLS-enabled PostgreSQL 16 container and per-test temporary databases, dropped by the tests:

```text
PYTHONPATH=backend .venv/bin/python -m pytest -q \
  tests/test_relationship_temporal_state_postgres.py \
  tests/test_relationship_temporal_persistence_phase_f.py \
  tests/test_relationship_temporal_continuation.py \
  tests/test_relationship_temporal_state_loading.py
```

**31 passed, 2 warnings**. Covered real migration application, initial write, exact replay, compatible continuation, conflicting replay/interval, stale CAS, out-of-order state, bounded state, exact-key isolation, unchanged persisted state after rejection, and competing writers.

## ANALYTICAL FREEZE

Reviewed the A–F code path and its changes against the committed authority baseline. The chain adds identity, evidence lineage, guarded state loading, discovery suppression, and post-analysis persistence; it does not change relationship calculations, thresholds, eligibility, quality/context semantics, ranking, consequence, telemetry admission, governance, or presentation.

`ANALYTICAL_MATH_CHANGED: NO`

## TEST RESULTS

Focused authority, lineage, state repository, state loading, continuation, persistence, Phase 4 orchestration, authenticated scope, upload identity, evidence binding, and telemetry handoff run:

```text
PYTHONPATH=backend .venv/bin/python -m pytest -q \
  tests/test_relationship_authority.py \
  tests/test_relationship_lineage.py \
  tests/test_relationship_temporal_state_repository.py \
  tests/test_relationship_temporal_state_loading.py \
  tests/test_relationship_temporal_continuation.py \
  tests/test_relationship_temporal_persistence.py \
  tests/test_relationship_temporal_persistence_phase_f.py \
  tests/test_sii_phase4_orchestrator.py \
  tests/test_phase4_authenticated_scope.py \
  tests/test_phase4_upload_system_identity.py \
  tests/test_relationship_evidence_binding.py \
  tests/test_telemetry_analysis_handoff.py
```

**185 passed, 1 skipped, 2 warnings.** The skipped case required PostgreSQL and passed in the real PostgreSQL run above. `git diff --check` passed before creation of this artifact. No LBNL, wastewater, scale, performance, or unrelated campaign was run.

## DEFECTS

No material defects identified. No production code or tests were modified. No staging, commit, push, merge, tag, or deployment was performed.

## CERTIFICATION ARTIFACT

`docs/reviews/relationship-authority/phase-a-f-closeout-certification-2026-09-26.md`

## DECISION

`RELATIONSHIP_TEMPORAL_AUTHORITY_A_F_CERTIFIED`

## NEXT ACTION

A–F relationship temporal authority chain is certified at the stated HEAD. No further action is required for this certification.
