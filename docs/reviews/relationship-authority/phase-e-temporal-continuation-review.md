# Phase E temporal continuation certification

## Scope and decision

The corrected candidate applies compatible prior relationship temporal state through the existing reducer. **Certified for commit review** after inspecting the current diff and the actual Phase 4 store paths.

## Continuation authority

The discovery evaluation produces current-run, producer-owned relationship evidence and lineage. Prior state is read only through `load_prior_relationship_state`, the certified Phase D gate. That gate checks exact authenticated scope, system, asset, evidence and lineage references, lineage authority, compatibility digest, schema, and state digest. It rejects fallback evidence, malformed or tampered state, and histories exceeding eight observations.

Only gate-approved state is converted to the reducer's existing sorted-endpoint key. No names, ranks, primary or grouping flags, persistent columns, presentation fields, runtime metadata, or retry identifiers determine identity.

## Discovery side-effect safety

Discovery runs inside `phase4_persistence_suppressed()`. The context manager sets a `ContextVar` and restores its prior value in `finally`, including exception paths. `evaluate_phase4` checks that context before obtaining the behavioral model store. All Phase 4 store loads and writes use the local store initialized behind that check; discovery therefore cannot load, write, version, snapshot, or mutate that store. No other persistent write path was found in `sii_engine.py` or the other SII engine modules.

The focused regression invokes the real `evaluate_phase4` store path during both passes. It verifies no discovery writes, and that the authoritative pass produces one model version and one snapshot.

## Authoritative evaluation and fail-closed behavior

After discovery and the Phase D read, exactly one normal authoritative evaluation runs. Its inputs equal discovery inputs, with only `relationship_persistence_state` added when compatible prior state is available. Missing, rejected, malformed, or failed reads result in the normal authoritative call without that input. Discovery output is not returned as the analysis result.

Exact same-time replay remains idempotent in the existing reducer. Older or conflicting same-time observations receive no prior state. Phase D and the reducer retain their eight-observation limits.

## Ownership and analytical freeze

Current-run evidence and result-local ownership remain authoritative. No Phase F temporal-state writes were added.

`ANALYTICAL_MATH_CHANGED: NO`. The existing reducer is applied to compatible prior/current evidence; its mathematics, thresholds, eligibility, quality/context, ranking, consequence, telemetry admission, governance, and presentation are unchanged.

## Verification

- `tests/test_relationship_temporal_continuation.py`
- `tests/test_relationship_temporal_state_loading.py`
- `tests/test_sii_phase4_orchestrator.py`
- `git diff --check`

Result: **36 passed**, 2 warnings; diff check clean.
